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
from dataclasses import dataclass, replace
from typing import Callable, Sequence

from .adb import AdbClient, AdbError, DeviceInfo
from .apk import (
    ApkInfo, ApkVerifier, ApkError, MAX_APK_BYTES, PLAY_CORE, PLAY_PACKAGES, SYNC_PROVIDERS,
    file_sha256, google_play_order,
)
from .package_catalog import OFFERS
from .package_workflows import PackageWorkflows
from .device_workflows import DeviceWorkflows, _read_file
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
# Android's PackageManager.COMPONENT_ENABLED_STATE_* values and matching pm verbs.
_OFFERS_MODES = {'0': 'default-state', '1': 'enable', '2': 'disable',
                 '3': 'disable-user', '4': 'disable-until-used'}
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
    providers_to_enable: tuple[str, ...] = ()


@dataclass(frozen=True)
class PairedAdsPlan(Plan):
    package_mode: str = ''
    saved_package_mode: str = ''
    saved_pair_exists: bool = False
    target_package_mode: str = ''


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
        self._require_execution_directory()
        return device

    def _verifier(self, device_sdk: int | None = None) -> ApkVerifier:
        if not all((self.config.aapt_path, self.config.apksigner_jar, self.config.java_path)):
            raise ToolkitError('Select official aapt, apksigner.jar and Java paths before verifying APKs.')
        return ApkVerifier(self.config.aapt_path, self.config.apksigner_jar, self.config.java_path, device_sdk=device_sdk)

    def plan_google_play(self, serial: str, paths: Sequence[str | Path]) -> Plan:
        device = self._writable_device(serial)
        if not paths or len(paths) > len(PLAY_PACKAGES):
            raise ToolkitError('Choose up to six standalone Google APKs. To add sync to an existing Play installation, select only the sync adapters.')
        try:
            verifier = self._verifier(device.sdk)
            apks = google_play_order([verifier.inspect(Path(p)) for p in paths], device.sdk, device.abis)
        except (ApkError, OSError, ValueError) as exc:
            raise ToolkitError(str(exc)) from exc
        providers = self._play_providers_to_enable(serial, apks)
        details = []
        for apk in apks:
            details.append(f'Install {apk.package} {apk.version_name} (SDK {apk.min_sdk}+). '
                           f'File SHA-256 {apk.sha256}. Signer SHA-256 {apk.signer_sha256[0]}.')
            if apk.signer_lineage:
                details.append(f'Verified Google signer rotation from {apk.signer_lineage[0]}.')
            provider = SYNC_PROVIDERS.get(apk.package)
            if provider in providers:
                details.append(f'Enable {provider} for the owner profile after installing the adapter.')
        warnings = [
            'Google Play is not officially supported by Amazon. Some apps and push notifications may not work.',
            'Each APK is staged and verified again before installation. A failure leaves earlier installations in place.',
            'Restart the tablet after successful installation.',
        ]
        names = {apk.package for apk in apks}
        if (device.sdk == 30 and 'arm64-v8a' in device.abis and 'com.android.vending' in names
                and 'com.google.android.gsf.login' not in names):
            warnings.append('For a fresh install on this Android 11 ARM64 tablet, the Toolbox v46 set '
                            'includes Google Account Manager. Select its APK as well if it is missing.')
        return Plan('Install Google Play components', serial, tuple(details), tuple(warnings),
                    'play', device, tuple(apks), providers_to_enable=providers)

    def _play_providers_to_enable(self, serial, apks):
        packages = {apk.package for apk in apks}
        providers = {provider for adapter, provider in SYNC_PROVIDERS.items() if adapter in packages}
        if not providers:
            return ()
        installed = set(self.adb.packages(serial))
        disabled = set(self.adb.packages(serial, disabled_only=True))
        missing = providers - installed
        if missing:
            raise ToolkitError('The selected sync adapter needs an installed owner-profile provider: '
                               + ', '.join(sorted(missing)))
        if packages <= SYNC_PROVIDERS.keys():
            unavailable = set(PLAY_CORE) - (installed - disabled)
            if unavailable:
                raise ToolkitError('Install or enable these core packages before adding sync adapters: '
                                   + ', '.join(sorted(unavailable)))
        return tuple(sorted(providers & disabled))

    def _state_key(self, serial: str) -> str:
        return hashlib.sha256(serial.encode('utf-8')).hexdigest()

    def _load_state(self) -> dict:
        path = self.state_dir / 'state.json'
        try:
            with self._journal_directory() as parent:
                _, content = _read_file(parent / 'state.json', 1024 * 1024, content=True)
            data = json.loads(content)
            if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('ads'), dict):
                raise ValueError('unknown schema')
            for group in ('ads', 'paired_ads'):
                records = data.get(group, {})
                if not isinstance(records, dict):
                    raise ValueError('invalid ad undo records')
                for key, record in records.items():
                    if not re.fullmatch(r'[0-9a-f]{64}', key) or not isinstance(record, dict):
                        raise ValueError('invalid record')
                    value = record['value']
                    if value is not None and (not isinstance(value, str) or not re.fullmatch(r'-?\d{1,9}', value, re.ASCII)):
                        raise ValueError('invalid previous setting')
                    if not isinstance(record.get('model'), str):
                        raise ValueError('missing device identity')
                    if group == 'paired_ads' and record.get('mode') not in _OFFERS_MODES:
                        raise ValueError('invalid Special Offers package state')
            return data
        except FileNotFoundError:
            return {'schema': 1, 'ads': {}}
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ToolkitError(f'Undo state is unreadable: {path}. Preserve it and resolve the error before making changes.') from exc

    def _save_state(self, state: dict) -> None:
        with self._journal_directory(create=True) as parent:
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

    def plan_ads(self, serial: str, restore: bool = False, *, paired: bool = False) -> Plan:
        device = self._writable_device(serial)
        state = self._load_state()
        current = self._read_ads(serial)
        if paired:
            return self._plan_paired_ads(device, state, current, restore)
        if self._state_key(serial) in state.get('paired_ads', {}):
            raise ToolkitError('Restore the paired ad controls first so the two undo operations apply in order.')
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

    def _offers_mode(self, serial):
        # pm list -d collapses default, explicit, and until-used states. Read the
        # owner override so restore can issue the exact corresponding command.
        dump = self._pkg_shell(serial, 'dumpsys', 'package', OFFERS)
        owner = re.findall(r'^\s*User 0:[^\r\n]*', dump, re.M)
        if len(owner) != 1 or not re.search(r'\binstalled=true\b', owner[0]):
            raise ToolkitError('Cannot confirm Special Offers is installed for the owner. Use the setting-only option if available.')
        modes = re.findall(r'\benabled=(\d+)\b', owner[0])
        if len(modes) != 1 or modes[0] not in _OFFERS_MODES:
            raise ToolkitError('Cannot read the owner’s Special Offers package state reliably.')
        return modes[0]

    def _plan_paired_ads(self, device, state, current, restore):
        key = self._state_key(device.serial)
        record = state.get('paired_ads', {}).get(key)
        if record and record['model'] != device.model:
            raise ToolkitError('Saved paired ad undo belongs to a different tablet model.')
        if restore and record is None:
            raise ToolkitError('No saved paired ad controls exist for this tablet.')
        mode = self._offers_mode(device.serial)
        if self._writable_device(device.serial) != device:
            raise ToolkitError('The tablet changed during inspection.')
        original = record['value'] if record else current
        original_mode = record['mode'] if record else mode
        target = original if restore else '0'
        target_mode = original_mode if restore else ('3' if mode in ('0', '1') else mode)
        warnings = ['Fire OS can reject or reset either control. Only the setting and package state can be verified.',
                    'Use the paired restore for this operation. A partial change retains its saved undo.']
        version = re.fullmatch(r'(?:Fire OS\s+)?(8(?:\.[0-9]{1,4}){1,5})', device.fire_os.strip(), re.I)
        if version and tuple(map(int, version[1].split('.'))) > (8, 3, 3, 7):
            warnings.append('Fire Toolbox v46 treats Fire OS 8 above 8.3.3.7 as restricted. '
                            'If Fire OS protects Special Offers, alternatives include the setting-only control, '
                            'the source-built ad helper, and Amazon’s official Special Offers removal.')
        return PairedAdsPlan(
            'Restore ad setting and Special Offers' if restore else 'Suppress ad setting and Special Offers',
            device.serial,
            (f'{ADS_KEY}: {current if current is not None else "absent"} → {target if target is not None else "absent"}.',
             f'{OFFERS} (owner user 0): {_OFFERS_MODES[mode]} → {_OFFERS_MODES[target_mode]}.',
             f'Saved for undo: setting {original if original is not None else "absent"}, package {_OFFERS_MODES[original_mode]}.'),
            tuple(warnings), 'ads_paired_restore' if restore else 'ads_paired', device, old_value=current,
            restore_value=original, package_mode=mode, saved_package_mode=original_mode, saved_pair_exists=record is not None,
            target_package_mode=target_mode)

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
            pinned_state = pinned_handles.enter_context(self._execution_directory())
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
            elif plan.action in ('ads_paired', 'ads_paired_restore'):
                self._apply_paired_ads(plan, completed)
            elif plan.action in ('ads', 'ads_restore'):
                self._apply_ads(plan)
                completed.append('Ad setting restored and read back.' if plan.action == 'ads_restore' else 'Ad setting set to 0 and read back. Actual ad visibility is not verified.')
            elif plan.action in ('enable', 'disable'):
                if plan.package not in OPTIONAL_APPS:
                    raise ToolkitError('Refusing a package outside the optional-app allowlist.')
                if plan.package not in self.adb.packages(plan.serial):
                    raise ToolkitError('Package is no longer installed. Review again.')
                verb = 'enable' if plan.action == 'enable' else 'disable-user'
                self._pkg_write(plan, completed, 'pm', verb, '--user', '0', plan.package)
                if plan.package not in self.adb.packages(plan.serial):
                    raise ToolkitError('Package disappeared during the operation; its state was not confirmed.')
                disabled = plan.package in self.adb.packages(plan.serial, True)
                if disabled != (plan.action == 'disable'):
                    raise ToolkitError('The requested app state was not confirmed; firmware may protect this package.')
                state = 'disabled' if disabled else 'enabled'
                self._pkg_confirm(plan, completed, f'{plan.package}: {state} for owner user 0.')
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
        verifier = self._verifier(plan.device.sdk)
        ordered = google_play_order(plan.apks, plan.device.sdk, plan.device.abis)
        with tempfile.TemporaryDirectory(prefix='open-fire-apks-') as temp:
            staging = Path(temp).resolve(strict=True)
            staged: list[ApkInfo] = []
            for index, apk in enumerate(ordered):
                target = staging / f'{index:02d}.apk'
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
                if checked != replace(apk, path=target):
                    raise ToolkitError('Staged APK verification changed; no APKs were installed.')
                staged.append(checked)
            staged_order = google_play_order(staged, plan.device.sdk, plan.device.abis)
            if self._play_providers_to_enable(plan.serial, staged_order) != plan.providers_to_enable:
                raise ToolkitError('Sync provider state changed since preview. Review again.')
            for apk in staged_order:
                if file_sha256(apk.path) != apk.sha256:
                    raise ToolkitError('Staged APK changed during installation; stopped.')
                self._device_guard(plan)
                self.adb.install(plan.serial, apk.path)
                message = f'Installed {apk.package}'
                completed.append(message)
                log(message)
                provider = SYNC_PROVIDERS.get(apk.package)
                if provider:
                    self._finish_sync_provider(plan, provider, completed, log)

    def _finish_sync_provider(self, plan, provider, completed, log):
        self._device_guard(plan)
        if provider in plan.providers_to_enable:
            self._pkg_write(plan, completed, 'pm', 'enable', '--user', '0', provider)
        if (provider not in self.adb.packages(plan.serial)
                or provider in self.adb.packages(plan.serial, disabled_only=True)):
            raise ToolkitError(f'Could not confirm {provider} is enabled for the owner profile.')
        self._device_guard(plan)
        if provider in plan.providers_to_enable:
            message = f'Enabled {provider} for the owner profile.'
            completed[-1] = message
            log(message)

    def _apply_paired_ads(self, plan, completed):
        restore = plan.action == 'ads_paired_restore'
        state = self._load_state()
        fresh = self._plan_paired_ads(plan.device, state, self._read_ads(plan.serial), restore)
        if fresh != plan or self._read_ads(plan.serial) != plan.old_value:
            raise ToolkitError('The paired ad setting, package or undo state changed since preview. Review again.')

        self._device_guard(plan)
        key = self._state_key(plan.serial)
        saved = {'model': plan.device.model, 'value': plan.restore_value, 'mode': plan.saved_package_mode}
        if not plan.saved_pair_exists:
            state.setdefault('paired_ads', {})[key] = saved
            self._save_state(state)
        target = plan.restore_value if restore else '0'
        mode = plan.package_mode
        target_mode = plan.target_package_mode
        if target != plan.old_value:
            args = ('put', 'global', ADS_KEY, target) if target is not None else ('delete', 'global', ADS_KEY)
            self._pkg_write(plan, completed, 'settings', '--user', '0', *args)
            if self._read_ads(plan.serial) != target:
                raise ToolkitError('Ad setting change could not be confirmed. Paired undo retained.')
            self._pkg_confirm(plan, completed, 'Ad setting change confirmed.')

        if self._offers_mode(plan.serial) != mode:
            raise ToolkitError('Special Offers changed during the operation. Paired undo retained.')
        if mode != target_mode:
            self._pkg_write(plan, completed, 'pm', _OFFERS_MODES[target_mode], '--user', '0', OFFERS)
        self._device_guard(plan)
        if self._offers_mode(plan.serial) != target_mode or self._read_ads(plan.serial) != target:
            raise ToolkitError('Could not confirm both ad controls. Paired undo retained.')
        self._device_guard(plan)
        completed.append('Confirmed the ad setting and Special Offers package state for user 0.')
        if restore:
            state = self._load_state()
            if state.get('paired_ads', {}).get(key) != saved:
                raise ToolkitError('The paired undo record changed during restore and was retained.')
            del state['paired_ads'][key]
            self._save_state(state)

    def _apply_ads(self, plan: Plan) -> None:
        if self._read_ads(plan.serial) != plan.old_value:
            raise ToolkitError('The ad setting changed since preview. Review a fresh plan.')
        state = self._load_state()
        key = self._state_key(plan.serial)
        if key in state.get('paired_ads', {}):
            raise ToolkitError('Paired ad undo was saved since preview. Restore the paired ad controls first.')
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
        self._device_guard(plan)
        self.adb.shell(plan.serial, args)
        try:
            self._device_guard(plan)
            actual = self._read_ads(plan.serial)
            self._device_guard(plan)
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
