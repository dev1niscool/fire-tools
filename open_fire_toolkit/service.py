"""Auditable, preview-first tablet operations. No network client or updater."""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
from dataclasses import dataclass
from typing import Callable, Sequence

from .adb import AdbClient, AdbError, DeviceInfo
from .apk import ApkInfo, ApkVerifier, ApkError, MAX_APK_BYTES, file_sha256, google_play_order
from .package_workflows import PackageWorkflows
from .device_workflows import DeviceWorkflows, _pinned_directory, _read_file
from .extra_workflows import ExtraWorkflows
from .workflows import TransportPlan

OPTIONAL_APPS = {
    'com.amazon.kindle': 'Kindle books',
    'com.amazon.avod': 'Prime Video',
    'com.audible.application.kindle': 'Audible',
    'com.goodreads.kindle': 'Goodreads',
    'com.amazon.mp3': 'Amazon Music',
    'com.amazon.windowshop': 'Amazon Shopping',
}
ADS_KEY = 'LOCKSCREEN_AD_ENABLED'
AMAZON_DEVICES_URL = 'https://www.amazon.com/hz/mycd/digital-console/alldevices'
PLATFORM_TOOLS_URL = 'https://developer.android.com/tools/releases/platform-tools'
BUILD_TOOLS_URL = 'https://developer.android.com/tools/releases/build-tools'


class ToolkitError(Exception):
    """An expected refusal or an operation failure, with factual progress."""


@dataclass(frozen=True)
class ToolConfig:
    adb_path: str
    aapt_path: str = ''
    apksigner_jar: str = ''
    java_path: str = ''


@dataclass(frozen=True)
class Plan:
    title: str
    serial: str
    details: tuple[str, ...]
    warnings: tuple[str, ...]
    action: str
    device: DeviceInfo
    apks: tuple[ApkInfo, ...] = ()
    package: str = ''
    old_value: str | None = None
    restore_value: str | None = None


def _default_state_dir() -> Path:
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    else:
        base = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local' / 'state')))
    return base / 'open-fire-toolkit'


def _setting_value(raw: str) -> str | None:
    value = raw.strip()
    if value == 'null':
        return None
    if re.fullmatch(r'-?\d{1,9}', value, flags=re.ASCII):
        return value
    raise ToolkitError('Cannot read the ad setting reliably. ' + value[:180])


class Toolkit(PackageWorkflows, DeviceWorkflows, ExtraWorkflows):
    def __init__(self, config: ToolConfig, state_dir: Path | None = None):
        self.config = config
        try:
            self.adb = AdbClient(config.adb_path)
        except (AdbError, ValueError, OSError) as exc:
            raise ToolkitError(str(exc)) from exc
        self.state_dir = Path(state_dir) if state_dir is not None else _default_state_dir()
        self._operation_lock = threading.Lock()

    def devices(self):
        return self.adb.devices()

    def device_info(self, serial: str) -> DeviceInfo:
        return self.adb.info(serial)

    def packages(self, serial: str, disabled_only: bool = False) -> list[str]:
        return self.adb.packages(serial, disabled_only)

    def _writable_device(self, serial: str) -> DeviceInfo:
        device = self.adb.info(serial)
        if device.serial != serial:
            raise ToolkitError('The selected device identity changed. Refresh and review again.')
        if not device.model.strip():
            raise ToolkitError('Cannot establish the tablet model; no changes are allowed.')
        if device.manufacturer.strip().casefold() != 'amazon':
            raise ToolkitError('Changes are supported only on Amazon Fire tablets.')
        if device.user_id != 0:
            raise ToolkitError('Switch the tablet to its primary adult/owner profile (user 0) first.')
        if device.sdk < 23:
            raise ToolkitError('This release supports Android API 23 or newer Fire tablets only.')
        return device

    def _verifier(self) -> ApkVerifier:
        if not all((self.config.aapt_path, self.config.apksigner_jar, self.config.java_path)):
            raise ToolkitError('Select official aapt, apksigner.jar and Java paths before verifying APKs.')
        return ApkVerifier(self.config.aapt_path, self.config.apksigner_jar, self.config.java_path)

    def plan_google_play(self, serial: str, paths: Sequence[str | Path]) -> Plan:
        device = self._writable_device(serial)
        if not paths or len(paths) > 4:
            raise ToolkitError('Select Framework, Play services and Play Store APKs; Account Manager is optional.')
        try:
            verifier = self._verifier()
            apks = google_play_order([verifier.inspect(Path(p)) for p in paths], device.sdk, device.abis)
        except (ApkError, OSError, ValueError) as exc:
            raise ToolkitError(str(exc)) from exc
        details = tuple(f'Install {a.package} {a.version_name} (SDK {a.min_sdk}+), SHA-256 {a.sha256}' for a in apks)
        return Plan('Install Google Play components', serial, details, (
            'Google Play is not officially supported by Amazon. Some apps and push notifications may not work.',
            'All APKs will be staged and verified again before installation. Installation is not atomic; a failed later step does not undo earlier installs.',
            'No downgrade or blanket permission grants are used. Restart the tablet after successful installation.',
        ), 'play', device, tuple(apks))

    def _state_key(self, serial: str) -> str:
        return hashlib.sha256(serial.encode('utf-8')).hexdigest()

    def _load_state(self) -> dict:
        path = self.state_dir / 'state.json'
        try:
            with _pinned_directory(self.state_dir) as parent:
                _, content = _read_file(parent / 'state.json', 1024 * 1024, content=True)
            data = json.loads(content)
            if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('ads'), dict):
                raise ValueError('unknown schema')
            for key, record in data['ads'].items():
                if not re.fullmatch(r'[0-9a-f]{64}', key) or not isinstance(record, dict):
                    raise ValueError('invalid record')
                value = record['value']
                if value is not None and (not isinstance(value, str) or not re.fullmatch(r'-?\d{1,9}', value, re.ASCII)):
                    raise ValueError('invalid previous setting')
                if not isinstance(record.get('model'), str):
                    raise ValueError('missing device identity')
            return data
        except FileNotFoundError:
            return {'schema': 1, 'ads': {}}
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ToolkitError(f'Undo state is unreadable: {path}. Preserve it and resolve the error before making changes.') from exc

    def _save_state(self, state: dict) -> None:
        with _pinned_directory(self.state_dir, create=True) as parent:
            fd, name = tempfile.mkstemp(prefix='.state-', suffix='.json', dir=parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(state, stream, indent=2, sort_keys=True)
                    stream.write('\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, parent / 'state.json')
            finally:
                if os.path.exists(name):
                    os.unlink(name)

    def _read_ads(self, serial: str) -> str | None:
        return _setting_value(self.adb.shell(serial, ('settings', '--user', '0', 'get', 'global', ADS_KEY)))

    def plan_ads(self, serial: str, restore: bool = False) -> Plan:
        device = self._writable_device(serial)
        state = self._load_state()
        current = self._read_ads(serial)
        record = state['ads'].get(self._state_key(serial))
        if record and record['model'] != device.model:
            raise ToolkitError('Saved undo state belongs to a different device model. No changes made.')
        if restore and record is None:
            raise ToolkitError('No saved ad setting exists for this tablet; there is nothing to restore.')
        target = record['value'] if restore else '0'
        return Plan('Restore previous ad setting' if restore else 'Try temporary ad suppression', serial, (
            f'Current {ADS_KEY}: {current if current is not None else "not set"}',
            f'{"Restore" if restore else "Set"} {ADS_KEY}: {target if target is not None else "delete setting"}',
            'No apps, app data, firmware or update settings will be removed.',
        ), (
            'This changes one Android setting. It does not prove that lock-screen ads disappear.',
            'Modern firmware may ignore or reset it. This release does not install Automate or run privilege exploits.',
            'For reliable removal, use Amazon’s official paid Special Offers removal.',
        ), 'ads_restore' if restore else 'ads', device, old_value=current, restore_value=target if restore else None)

    def plan_package(self, serial: str, package: str, enable: bool = False) -> Plan:
        device = self._writable_device(serial)
        if package not in OPTIONAL_APPS:
            raise ToolkitError('That package is not on this release’s optional-app allowlist.')
        if package not in self.adb.packages(serial):
            raise ToolkitError('The selected package is not installed for the owner profile.')
        disabled = package in self.adb.packages(serial, disabled_only=True)
        if disabled == (not enable):
            raise ToolkitError('The package is already in the requested enabled/disabled state.')
        return Plan(('Enable ' if enable else 'Disable ') + OPTIONAL_APPS[package], serial,
                    (f'{"Enable" if enable else "Disable"} {package} for owner user 0; preserve app data.',),
                    ('Other apps or subscriptions may depend on this app. Re-enable it here if needed.',),
                    'enable' if enable else 'disable', device, package=package)

    def plan_reboot(self, serial: str) -> Plan:
        device = self._writable_device(serial)
        return Plan('Restart tablet', serial, ('Restart the selected tablet normally.',),
                    ('Save work on the tablet first. Reconnect after it finishes starting.',), 'reboot', device)

    def execute(self, plan: Plan, confirmed: bool = False, log: Callable[[str], None] = print) -> list[str]:
        if not confirmed:
            raise ToolkitError('Review and explicitly confirm the plan before applying changes.')
        if not self._operation_lock.acquire(blocking=False):
            raise ToolkitError('An operation is already running. Wait for it to finish.')
        lock_path = self.state_dir / 'operation.lock'
        pinned_handles = ExitStack()
        owns_file_lock = False
        completed: list[str] = []
        try:
            pinned_state = pinned_handles.enter_context(_pinned_directory(self.state_dir, create=True))
            lock_path = pinned_state / 'operation.lock'
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                owns_file_lock = True
                with os.fdopen(fd, 'w') as stream:
                    stream.write(str(os.getpid()))
            except FileExistsError as exc:
                recovery_path = self.state_dir / 'operation.lock'
                raise ToolkitError(f'Another toolkit process may be running. If all toolkit processes are closed, remove {recovery_path} and retry.') from exc
            if isinstance(plan, TransportPlan):
                self._execute_transport(plan, completed, log)
                for message in completed:
                    log(message)
                return completed
            if plan.serial != plan.device.serial or self._writable_device(plan.serial) != plan.device:
                raise ToolkitError('Device details changed after preview. Refresh and review the action again.')
            if plan.action == 'play':
                self._install_play(plan, completed, log)
            elif plan.action == 'package_workflow':
                self._execute_package_workflow(plan, completed, log)
            elif plan.action == 'device_workflow':
                self._execute_device_workflow(plan, completed, log)
            elif plan.action == 'extra_workflow':
                self._execute_extra_workflow(plan, completed, log)
            elif plan.action in ('ads', 'ads_restore'):
                self._apply_ads(plan)
                completed.append('Ad setting restored and read back.' if plan.action == 'ads_restore' else 'Ad setting set to 0 and read back. Actual ad visibility is not verified.')
            elif plan.action in ('enable', 'disable'):
                if plan.package not in OPTIONAL_APPS:
                    raise ToolkitError('Refusing a package outside the optional-app allowlist.')
                if plan.package not in self.adb.packages(plan.serial):
                    raise ToolkitError('Package is no longer installed. Review again.')
                verb = 'enable' if plan.action == 'enable' else 'disable-user'
                self.adb.shell(plan.serial, ('pm', verb, '--user', '0', plan.package))
                if plan.package not in self.adb.packages(plan.serial):
                    raise ToolkitError('Package disappeared during the operation; its state was not confirmed.')
                disabled = plan.package in self.adb.packages(plan.serial, True)
                if disabled != (plan.action == 'disable'):
                    raise ToolkitError('The requested app state was not confirmed; firmware may protect this package.')
                completed.append(f'{plan.package}: {"disabled" if disabled else "enabled"} for owner user 0.')
            elif plan.action == 'reboot':
                self.adb.reboot(plan.serial)
                completed.append('Restart command accepted. Wait for the tablet to reconnect.')
            else:
                raise ToolkitError('Unknown action; nothing was executed.')
            if plan.action != 'play':
                for message in completed:
                    log(message)
            return completed
        except (ToolkitError, AdbError, ApkError, OSError, ValueError, RuntimeError) as exc:
            suffix = ''
            if completed:
                suffix = ' Completed: ' + '; '.join(completed) + '. Earlier changes were not rolled back.'
            raise ToolkitError(str(exc) + suffix) from exc
        finally:
            if owns_file_lock:
                try:
                    lock_path.unlink()
                except OSError:
                    pass
            try:
                pinned_handles.close()
            finally:
                self._operation_lock.release()

    def _install_play(self, plan: Plan, completed: list[str], log: Callable[[str], None]) -> None:
        verifier = self._verifier()
        ordered = google_play_order(plan.apks, plan.device.sdk, plan.device.abis)
        with tempfile.TemporaryDirectory(prefix='open-fire-apks-') as temp:
            staged: list[ApkInfo] = []
            for index, apk in enumerate(ordered):
                target = Path(temp) / f'{index:02d}.apk'
                # O_NONBLOCK prevents a replaced FIFO from hanging the worker on POSIX.
                fd = os.open(apk.path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0))
                with os.fdopen(fd, 'rb') as source:
                    source_stat = os.fstat(source.fileno())
                    if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_size > MAX_APK_BYTES:
                        raise ToolkitError('APK must be a regular file of at most 512 MiB; no files were installed.')
                    with target.open('xb') as output:
                        remaining = MAX_APK_BYTES
                        while chunk := source.read(min(1024 * 1024, remaining + 1)):
                            remaining -= len(chunk)
                            if remaining < 0:
                                raise ToolkitError('APK grew beyond 512 MiB during staging; no files were installed.')
                            output.write(chunk)
                if file_sha256(target) != apk.sha256:
                    raise ToolkitError('An APK changed since preview; no APKs were installed. Review the files again.')
                checked = verifier.inspect(target)
                if (checked.package, checked.sha256, checked.signer_sha256) != (apk.package, apk.sha256, apk.signer_sha256):
                    raise ToolkitError('Staged APK verification changed; no APKs were installed.')
                staged.append(checked)
            staged_order = google_play_order(staged, plan.device.sdk, plan.device.abis)
            for apk in staged_order:
                if self._writable_device(plan.serial) != plan.device:
                    raise ToolkitError('Tablet identity changed during installation; stopped.')
                if file_sha256(apk.path) != apk.sha256:
                    raise ToolkitError('Staged APK changed during installation; stopped.')
                self.adb.install(plan.serial, apk.path)
                message = f'Installed {apk.package}'
                completed.append(message)
                log(message)

    def _apply_ads(self, plan: Plan) -> None:
        if self._read_ads(plan.serial) != plan.old_value:
            raise ToolkitError('The ad setting changed since preview. Review a fresh plan.')
        state = self._load_state()
        key = self._state_key(plan.serial)
        record = state['ads'].get(key)
        if record and record['model'] != plan.device.model:
            raise ToolkitError('Undo state device model mismatch.')
        if plan.action == 'ads_restore':
            if record is None:
                raise ToolkitError('The saved previous value is missing. No changes made.')
            target = record['value']
            if target != plan.restore_value:
                raise ToolkitError('The saved restore value changed since preview. Review a fresh plan.')
        else:
            target = '0'
            if record is None:
                state['ads'][key] = {'value': plan.old_value, 'model': plan.device.model}
                self._save_state(state)  # Commit undo information BEFORE the mutation.
        if target is None:
            args = ('settings', '--user', '0', 'delete', 'global', ADS_KEY)
        else:
            args = ('settings', '--user', '0', 'put', 'global', ADS_KEY, target)
        self.adb.shell(plan.serial, args)
        try:
            actual = self._read_ads(plan.serial)
        except (ToolkitError, AdbError) as exc:
            raise ToolkitError('The ad setting command was issued, but readback failed. Undo information was retained; the tablet may have changed. ' + str(exc)) from exc
        if actual != target:
            raise ToolkitError('The setting could not be confirmed. Undo information was retained; actual ad visibility is unknown.')
        if plan.action == 'ads_restore':
            del state['ads'][key]
            try:
                self._save_state(state)
            except OSError as exc:
                raise ToolkitError('The ad setting was restored and read back, but local undo-state cleanup failed. Preserve the state file and resolve the storage error before another change. ' + str(exc)) from exc
