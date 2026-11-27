"""Explicit, serial-scoped access to a local ADB server."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
from selectors import DefaultSelector, EVENT_READ
import shlex
import subprocess
from time import monotonic, sleep
from typing import Sequence


class AdbError(Exception):
    """An ADB request could not be performed or verified."""


@dataclass(frozen=True)
class Device:
    serial: str
    state: str
    model: str = ""
    transport_id: int | None = None


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    model: str
    manufacturer: str
    fire_os: str
    android_release: str
    sdk: int
    abis: tuple[str, ...]
    user_id: int
    hardware_serial_sha256: str = ""

    @property
    def state_key(self) -> str:
        # Previous releases keyed USB state by SHA-256 of its serial. When
        # that serial matches the reported hardware ID, both transports can
        # open those records without migrating or exporting the raw ID.
        if self.hardware_serial_sha256:
            return self.hardware_serial_sha256
        return "" if is_network_selector(self.serial) else _serial_digest(self.serial)


_SERIAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_PACKAGE_LINE = re.compile(r"package:([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)")
_PROPERTY = re.compile(r"\[([^\]]+)\]: \[(.*)\]")
_ADB_OVERRIDES = {
    "ADB_SERVER_SOCKET", "ANDROID_ADB_SERVER_ADDRESS", "ANDROID_ADB_SERVER_PORT",
    "ANDROID_SERIAL",
}
_MAX_OUTPUT_BYTES = 1024 * 1024


def is_network_selector(serial: str) -> bool:
    # TCP endpoints and ADB's wireless mDNS service names can be reassigned.
    return ":" in serial or "." in serial or serial.lower().startswith(("adb-", "emulator-"))


def _serial_digest(value: str) -> str:
    if (is_network_selector(value) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value)
            or value.casefold() in {"unknown", "null", "none", "unavailable", "restricted",
                                    "default", "0123456789abcdef", "1234567890abcdef"}
            or len(set(value.casefold())) == 1):
        return ""
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _windows_pipe_availability():
    # Windows selectors accept sockets only. Peek each pipe before reading.
    import ctypes
    from ctypes import wintypes
    import msvcrt

    peek = ctypes.WinDLL("kernel32", use_last_error=True).PeekNamedPipe
    peek.argtypes = (
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD,
        wintypes.LPDWORD, wintypes.LPDWORD,
    )
    peek.restype = wintypes.BOOL

    def available(fd: int) -> int:
        count = wintypes.DWORD()
        if peek(msvcrt.get_osfhandle(fd), None, 0, None, ctypes.byref(count), None):
            return count.value
        error = ctypes.get_last_error()
        if error in {109, 232, 233}:  # Pipe closed or disconnected.
            return -1
        raise ctypes.WinError(error)

    return available


def _read_pipes(process: subprocess.Popen[bytes], deadline: float) -> tuple[str, str]:
    stdout = bytearray()
    stderr = bytearray()
    buffers = {process.stdout.fileno(): stdout, process.stderr.fileno(): stderr}
    windows_available = _windows_pipe_availability() if os.name == "nt" else None
    with DefaultSelector() as selector:
        if windows_available is None:
            for fd in buffers:
                selector.register(fd, EVENT_READ)

        while buffers:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError
            if windows_available is None:
                ready = [(key.fd, 65_536) for key, _ in selector.select(remaining)]
            else:
                ready = [(fd, windows_available(fd)) for fd in buffers]
                if not any(count for _, count in ready):
                    sleep(min(remaining, 0.01))
            for fd, count in ready:
                if count == 0:  # An open Windows pipe currently has no output.
                    continue
                limit = _MAX_OUTPUT_BYTES + 1 - len(stdout) - len(stderr)
                chunk = os.read(fd, min(count, 65_536, limit)) if count > 0 else b""
                if not chunk:
                    if windows_available is None:
                        selector.unregister(fd)
                    del buffers[fd]
                    continue
                buffers[fd].extend(chunk)
                if len(stdout) + len(stderr) > _MAX_OUTPUT_BYTES:
                    raise AdbError("ADB output exceeds the 1 MiB limit.")
    return stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


def _capture(command: list[str], *, env: dict[str, str], timeout: float) -> subprocess.CompletedProcess[str]:
    deadline = monotonic() + timeout
    with subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, shell=False,
    ) as process:
        try:
            stdout, stderr = _read_pipes(process, deadline)
            code = process.wait(timeout=max(0, deadline - monotonic()))
        finally:
            if process.poll() is None:
                process.kill()
    return subprocess.CompletedProcess(command, code, stdout, stderr)


class AdbClient:
    """Run a user-supplied platform-tools executable with bounded requests."""

    def __init__(self, path: str | Path):
        try:
            requested = Path(path)
            if requested.name.lower() not in {"adb", "adb.exe"}:
                raise AdbError("Select the adb or adb.exe executable from Google platform-tools.")
            resolved = requested.resolve(strict=True)
            if resolved.name.lower() not in {"adb", "adb.exe"} or not resolved.is_file():
                raise AdbError("Select the adb or adb.exe executable from Google platform-tools.")
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise AdbError(f"Cannot use the configured adb executable: {exc}") from exc
        self._path = resolved
        self._bound_transport: ContextVar[tuple[str, int] | None] = ContextVar("adb_transport", default=None)

    def _run(self, args: Sequence[str], timeout: float = 30) -> subprocess.CompletedProcess[str]:
        if not math.isfinite(timeout) or timeout <= 0:
            raise AdbError("ADB timeout must be positive and finite.")
        env = {key: value for key, value in os.environ.items() if key.upper() not in _ADB_OVERRIDES}
        command = [str(self._path), "-H", "localhost", "-P", "5037", *args]
        try:
            result = _capture(command, env=env, timeout=timeout)
        except (TimeoutError, subprocess.TimeoutExpired) as exc:
            raise AdbError(f"ADB timed out after {timeout} seconds.") from exc
        except OSError as exc:
            raise AdbError(f"Unable to run ADB: {exc}") from exc
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip()
            raise AdbError(detail or f"ADB exited with status {result.returncode}.")
        return result

    def devices(self) -> list[Device]:
        lines = self._run(["devices", "-l"]).stdout.splitlines()
        if not lines or lines[0].strip() != "List of devices attached":
            raise AdbError("ADB did not return a recognizable device list.")
        devices = []
        transport_ids = set()
        for line in lines[1:]:
            if not line.strip():
                continue
            fields = line.split(maxsplit=2)
            if len(fields) < 2:
                raise AdbError("ADB returned a malformed device entry.")
            serial, state = fields[:2]
            details = fields[2] if len(fields) == 3 else ""
            if state == "no" and (details == "permissions" or details.startswith("permissions ")):
                state = "no permissions"
            model = next((part.removeprefix("model:") for part in details.split()
                          if part.startswith("model:")), "")
            ids = [part.removeprefix("transport_id:") for part in details.split()
                   if part.startswith("transport_id:")]
            transport_id = None
            if ids:
                if len(ids) != 1 or not re.fullmatch(r"[1-9][0-9]{0,19}", ids[0]):
                    raise AdbError("ADB reported a malformed transport ID. Update Platform-Tools and scan again.")
                transport_id = int(ids[0])
                if transport_id >= 2**64 or transport_id in transport_ids:
                    raise AdbError("ADB reported an invalid or duplicate transport ID. Scan again.")
                transport_ids.add(transport_id)
            devices.append(Device(serial, state, model, transport_id))
        return devices

    def _online_device(self, serial: str) -> Device:
        if not isinstance(serial, str) or not _SERIAL.fullmatch(serial):
            raise AdbError("Specify a valid ADB device serial.")
        matches = [device for device in self.devices() if device.serial == serial]
        if len(matches) != 1:
            raise AdbError(f"Expected one connection for {serial}, found {len(matches)}. Scan again.")
        if matches[0].state != "device":
            raise AdbError(f"Device {serial} is {matches[0].state}. Check the USB debugging prompt and connection.")
        return matches[0]

    @contextmanager
    def bind_transport(self, serial: str):
        """Keep every device command in this operation on the same live ADB transport."""
        if self._bound_transport.get() is not None:
            raise AdbError("An ADB transport is already bound to this operation.")
        transport_id = self._online_device(serial).transport_id
        if transport_id is None:
            raise AdbError("ADB did not report a transport ID. Update Platform-Tools or use USB for changes.")
        token = self._bound_transport.set((serial, transport_id))
        try:
            yield
        finally:
            self._bound_transport.reset(token)

    def _run_device(
        self, serial: str, args: Sequence[str], timeout: float = 30,
    ) -> subprocess.CompletedProcess[str]:
        device = self._online_device(serial)
        bound = self._bound_transport.get()
        if bound is not None:
            if (serial, device.transport_id) != bound:
                raise AdbError("The bound ADB transport changed. Reconnect and review the action again.")
            # Address the connection by ID even after checking the current list.
            # A new connection at the same network address receives a new ID.
            return self._run(["-t", str(bound[1]), *args], timeout)
        return self._run(["-s", serial, *args], timeout)

    def shell(self, serial: str, args: Sequence[str], timeout: float = 30) -> str:
        if (
            isinstance(args, str) or not args
            or any(not isinstance(arg, str) or "\0" in arg for arg in args)
            or not args[0]
        ):
            raise AdbError("ADB shell requires a command and valid argument tokens.")
        # ADB joins its shell arguments into a remote shell command. Quote the
        # command name too, so a shell keyword or assignment stays a word.
        command_name = "'" + args[0].replace("'", "'\"'\"'") + "'"
        command = " ".join([command_name, *(shlex.quote(arg) for arg in args[1:])])
        result = self._run_device(serial, ["shell", command], timeout)
        if result.stderr.strip():
            raise AdbError(f"ADB shell reported an error: {result.stderr.strip()}")
        output = result.stdout
        return output.removesuffix("\r\n") if output.endswith("\r\n") else output.removesuffix("\n")

    def info(self, serial: str) -> DeviceInfo:
        properties = {}
        for line in self.shell(serial, ["getprop"]).splitlines():
            match = _PROPERTY.fullmatch(line)
            if match:
                name, value = match.groups()
                if name in properties:
                    raise AdbError(f"ADB returned duplicate device property {name}.")
                properties[name] = value
        sdk = properties.get("ro.build.version.sdk", "")
        if not re.fullmatch(r"[1-9][0-9]{0,8}", sdk):
            raise AdbError("Could not determine the device Android SDK level.")
        user = self.shell(serial, ["am", "get-current-user"]).strip()
        if not re.fullmatch(r"0|[1-9][0-9]{0,9}", user) or int(user) > 2_147_483_647:
            raise AdbError("Could not determine the current user on the Android device.")
        abis = properties.get("ro.product.cpu.abilist") or properties.get("ro.product.cpu.abi", "")
        return DeviceInfo(
            serial=serial,
            model=properties.get("ro.product.model", ""),
            manufacturer=properties.get("ro.product.manufacturer", ""),
            fire_os=properties.get("ro.build.mktg.fireos") or properties.get("ro.build.version.fireos") or properties.get("ro.build.version.name", ""),
            android_release=properties.get("ro.build.version.release", ""),
            sdk=int(sdk),
            abis=tuple(abi.strip() for abi in abis.split(",") if abi.strip()),
            user_id=int(user),
            hardware_serial_sha256=(_serial_digest(properties.get("ro.boot.serialno", ""))
                                    or _serial_digest(properties.get("ro.serialno", ""))),
        )

    def install(self, serial: str, apk: Path) -> str:
        try:
            path = Path(apk).resolve(strict=True)
            if not path.is_file():
                raise AdbError("The APK path must point to a file.")
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise AdbError(f"Cannot use the APK path: {exc}") from exc
        result = self._run_device(serial, ["install", "-r", "--user", "0", str(path)], timeout=300)
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        if re.search(r"\bFailure\b", output, re.IGNORECASE) or "Success" not in output.splitlines():
            raise AdbError(f"ADB did not confirm installation: {output or 'no output'}.")
        return output

    def packages(self, serial: str, disabled_only: bool = False) -> list[str]:
        args = ["pm", "list", "packages", "--user", "0"]
        if disabled_only:
            args.append("-d")
        packages = []
        for line in self.shell(serial, args).splitlines():
            if not line.strip():
                continue
            match = _PACKAGE_LINE.fullmatch(line.strip())
            if not match:
                raise AdbError(f"ADB returned an unexpected package entry: {line}")
            packages.append(match.group(1))
        return packages

    def reboot(self, serial: str) -> None:
        self._run_device(serial, ["reboot"])
