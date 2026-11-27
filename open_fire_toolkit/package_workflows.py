"""Owner-scoped package previews, controlled changes and persistent batch undo."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .adb import AdbError
from .apk import ApkError, GOOGLE_SIGNER_SHA256, MAX_APK_BYTES, _open_regular_file, file_sha256
from .package_catalog import APP_LABELS, DEBLOAT_PROFILES, OFFERS, STOCK_HOME, UPDATERS, is_protected
from .workflows import WorkflowPlan

_PACKAGE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*')
_CLASS = re.compile(r'\.?[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*')
_FAILURE = re.compile(r'(?:^|\s)(?:Failure\b|Error(?:\s|:|$)|Permission deni(?:ed|al)|'
                      r'SecurityException|Exception occurred|Unknown (?:command|option)|not allowed)', re.I)
_OWNER = ('--user', '0')
_STATE_OPS = {'disable', 'enable', 'uninstall', 'restore', 'debloat', 'undo',
              'ads-disable', 'ads-restore', 'ota-disable', 'ota-enable'}
_SIMPLE = {'disable', 'enable', 'uninstall', 'restore', 'clear-data', 'force-stop', 'launch', 'rollback-system'}
_APK_OPS = {'sideload', 'system-update'}
_PARAMS = {
    'debloat': {'profile', 'mode', 'list_file'}, 'launcher-set': {'component', 'disable_stock'},
    'keyboard-set': {'component'}, 'sideload': {'paths', 'signer'}, 'system-update': {'paths', 'signer'},
}
_GOOGLE = {'com.google.android.gsf', 'com.google.android.gsf.login', 'com.google.android.gms', 'com.android.vending'}
_STATE_LIMIT = 1024 * 1024
_STATES = {'enabled', 'disabled', 'uninstalled'}


def _error(message):
    from .service import ToolkitError
    return ToolkitError(message)


def _package(name):
    if not isinstance(name, str) or len(name) > 255 or not _PACKAGE.fullmatch(name):
        raise _error('Invalid Android package identifier.')
    return name


def _selection(values):
    if not isinstance(values, (list, tuple)) or len(values) > 256:
        raise _error('Select at most 256 packages.')
    result = tuple(_package(package) for package in values)
    if len(set(result)) != len(result):
        raise _error('Duplicate package selection.')
    return result


def _component(value):
    if not isinstance(value, str) or len(value) > 600 or value.count('/') != 1:
        raise _error('Expected an Android component in package/.Class format.')
    package, cls = value.split('/')
    _package(package)
    if not _CLASS.fullmatch(cls):
        raise _error('Invalid Android component class.')
    return package + '/' + (package + cls if cls.startswith('.') else cls)


def _limited_read(path, limit):
    with _open_regular_file(path) as (stream, size):
        if size > limit:
            raise _error(f'File exceeds {limit} bytes.')
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise _error(f'File exceeds {limit} bytes.')
    return data


def _optional_packages(profile, list_file):
    if profile != 'custom':
        if profile not in DEBLOAT_PROFILES or list_file:
            raise _error('Choose standard, complete or a custom package list.')
        return DEBLOAT_PROFILES[profile]
    if not list_file:
        raise _error('Select a custom package list.')
    text = _limited_read(Path(list_file), 128 * 1024).decode('utf-8-sig')
    entries = [line for raw in text.splitlines() if (line := raw.partition('#')[0].strip())]
    if not entries:
        raise _error('The custom package list is empty.')
    return _selection(entries)


def _state_after(op, before):
    if op in {'disable', 'ota-disable', 'ads-disable'}:
        return 'disabled'
    if op == 'uninstall':
        return 'uninstalled'
    if op == 'restore' and before != 'uninstalled':
        return before
    return 'enabled'


def _guard_selection(name, operation):
    _package(name)
    if operation.startswith('ota-') and name in UPDATERS:
        return
    if operation.startswith('ads-') and name == OFFERS:
        return
    if is_protected(name):
        raise _error(f'Protected infrastructure or dedicated workflow required for {name}.')


class PackageWorkflows:
    def _pkg_shell(self, serial, *args):
        output = self.adb.shell(serial, args)
        if _FAILURE.search(output):
            raise _error(f'Android rejected {args[0]} {args[1]}: {output[:500]}')
        return output.strip()

    def _pkg_device(self, plan):
        if self._writable_device(plan.serial) != plan.device:
            raise _error('Tablet identity or owner profile changed since preview.')

    def _pkg_write(self, plan, *args):
        self._pkg_device(plan)
        return self._pkg_shell(plan.serial, *args)

    def _pkg_list(self, serial, *flags):
        output = self._pkg_shell(serial, 'pm', 'list', 'packages', *_OWNER, *flags)
        names = set()
        for line in output.splitlines():
            if not line.startswith('package:'):
                raise _error('Unexpected Android package inventory response.')
            names.add(_package(line.removeprefix('package:')))
        return names

    def _pkg_states(self, serial):
        installed = self._pkg_list(serial)
        disabled = self._pkg_list(serial, '-d')
        known = self._pkg_list(serial, '-u')
        if not disabled <= installed <= known:
            raise _error('Package lists changed during inspection. Refresh and review again.')
        return {p: ('disabled' if p in disabled else 'enabled' if p in installed else 'uninstalled') for p in known}

    def package_inventory(self, serial, mode='all'):
        if mode not in {'all', 'system', 'third-party', 'disabled', 'uninstalled'}:
            raise _error('Unknown package inventory mode.')
        states = self._pkg_states(serial)
        names = {p for p, state in states.items() if state != 'uninstalled'}
        if mode in {'system', 'third-party'}:
            names &= self._pkg_list(serial, '-s' if mode == 'system' else '-3')
        if mode in {'disabled', 'uninstalled'}:
            names = {p for p, state in states.items() if state == mode}
        return [dict(package=p, label=APP_LABELS.get(p, p), state=states[p]) for p in sorted(names)]

    def _pkg_undo_record(self, device):
        from .device_workflows import _pinned_directory, _read_file
        path = self.state_dir / 'packages-state.json'
        key = self._state_key(device.serial)
        try:
            with _pinned_directory(self.state_dir.absolute()) as directory:
                _, encoded = _read_file(directory / path.name, _STATE_LIMIT, content=True)
            data = json.loads(encoded)
            if data['schema'] != 1 or not isinstance(data['devices'], dict):
                raise ValueError('Unknown package state schema.')
            for digest, record in data['devices'].items():
                if not re.fullmatch('[0-9a-f]{64}', digest) or not isinstance(record['model'], str):
                    raise ValueError('Invalid device record.')
                states, pending = record['states'], record.get('pending', {})
                if not isinstance(states, dict) or not isinstance(pending, dict):
                    raise ValueError('Invalid saved package states.')
                if len(states) > 256 or len(pending) > 1 or not (states or pending):
                    raise ValueError('Invalid saved package count.')
                for p, state in (*states.items(), *pending.items()):
                    _guard_selection(p, 'ota-enable' if p in UPDATERS else 'ads-restore' if p == OFFERS else 'undo')
                    if state not in _STATES:
                        raise ValueError('Invalid saved package state.')
        except FileNotFoundError:
            data = {'schema': 1, 'devices': {}}
        except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
            raise _error(f'Cannot read package undo state at {path}: {exc}') from exc
        record = data['devices'].get(key, {})
        if record and record['model'] != device.model:
            raise _error('The saved package state belongs to a different tablet model.')
        states = record.get('states', {})
        pending = record.get('pending')
        if pending:
            # The process could have stopped on either side of the first write.
            package, before = next(iter(pending.items()))
            if self._pkg_states(device.serial).get(package, 'missing') != before:
                states = pending
        return data, states

    def _pkg_save_undo(self, device, data, states, pending=None):
        from .device_workflows import _pinned_directory
        key = self._state_key(device.serial)
        if states or pending:
            record = {'model': device.model, 'states': states}
            if pending:
                record['pending'] = pending
            data['devices'][key] = record
        else:
            data['devices'].pop(key, None)
        encoded = json.dumps(data, separators=(',', ':')).encode()
        if len(encoded) > _STATE_LIMIT:
            raise _error('Package undo state exceeds the storage limit.')
        with _pinned_directory(self.state_dir.absolute(), create=True) as directory:
            fd, name = tempfile.mkstemp(dir=directory, prefix='.packages-')
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, directory / 'packages-state.json')
            finally:
                Path(name).unlink(missing_ok=True)

    def _pkg_activity(self, serial, category, package=None, include_disabled=False, allow_unresolved=False):
        flags = ('--query-flags', '512') if include_disabled else ()
        target = ('-p', package) if package else ()
        output = self._pkg_shell(serial, 'cmd', 'package', 'resolve-activity', '--brief', *_OWNER, *flags,
                                 '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.' + category, *target)
        if allow_unresolved and output in {'No activity found', 'No activity found.'}:
            return 'No activity found'
        candidate = output.splitlines()[-1] if output else ''
        _component(candidate)
        if package and candidate.split('/')[0] != package:
            raise _error(f'Android did not resolve a {category} activity in {package}.')
        return candidate

    def _pkg_keyboard(self, serial):
        return self._pkg_shell(serial, 'settings', *_OWNER, 'get', 'secure', 'default_input_method')

    def _pkg_guard_active(self, serial, packages, states):
        ime = self._pkg_keyboard(serial)
        if ime not in {'', 'null'} and _component(ime).split('/')[0] in packages:
            raise _error('Choose another active keyboard before changing this package.')
        if states.get(STOCK_HOME) != 'enabled':
            home = self._pkg_activity(serial, 'HOME')
            if home.split('/')[0] in packages:
                raise _error('Switch to another working HOME activity first.')

    def plan_package_action(self, serial, operation, packages=(), **parameters):
        if operation not in _SIMPLE | _STATE_OPS | _APK_OPS | {'launcher-set', 'launcher-restore', 'keyboard-set'}:
            raise _error('Unknown package operation.')
        if parameters.keys() - _PARAMS.get(operation, set()):
            raise _error('Unexpected package operation parameter.')
        if any(not isinstance(value, str) or len(value) > 131072 for value in parameters.values()):
            raise _error('Package options must be bounded text.')
        requested = _selection(packages)
        if operation in _SIMPLE and not requested:
            raise _error('Select one or more packages.')
        if requested and operation not in _SIMPLE | {'ota-enable', 'ota-disable', 'system-update'}:
            raise _error('This operation does not take an explicit package selection.')
        device = self._writable_device(serial)
        plan = WorkflowPlan(title=operation.replace('-', ' ').capitalize(), serial=serial, device=device,
                            operation=operation, action='package_workflow', details=(), warnings=(),
                            parameters=tuple(sorted(parameters.items())))
        try:
            if operation in _APK_OPS:
                return self._pkg_apk_plan(plan, requested)
            states = self._pkg_states(serial)
            if operation in {'launcher-set', 'launcher-restore', 'keyboard-set'}:
                return self._pkg_component_plan(plan, states)
            return self._pkg_select_plan(plan, requested, states)
        except (ValueError, OSError, ApkError, RecursionError) as exc:
            raise _error(str(exc)) from exc

    def _pkg_select_plan(self, plan, requested, states):
        op, params = plan.operation, plan.params
        details, warnings, snapshot, selected = [], [], {}, []
        mode = op
        saved = {}
        if op in _STATE_OPS:
            _, saved = self._pkg_undo_record(plan.device)
            snapshot['undo-digest'] = hashlib.sha256(json.dumps(saved, sort_keys=True).encode()).hexdigest()
        if op == 'debloat':
            mode = params.get('mode', 'disable')
            if mode not in {'disable', 'uninstall'}:
                raise _error('Choose disable or uninstall for debloat.')
            requested = _optional_packages(params.get('profile', 'standard'), params.get('list_file', ''))
        elif op == 'undo':
            if not saved:
                raise _error('No package undo state is available for this tablet.')
            requested = tuple(saved)
        elif op.startswith('ads-'):
            requested = (OFFERS,)
            warnings.append('Only the Special Offers package state is verified. Lock-screen ads depend on firmware.')
        elif op.startswith('ota-'):
            if not requested or any(p not in UPDATERS for p in requested):
                raise _error('Select one or more known Fire OS update packages.')
            warnings.append('Disabling the updater can block security updates. Fire OS may protect these packages.')
        if op == 'clear-data':
            warnings.append('This permanently deletes the selected apps’ owner data, preferences and sign-ins.')
        if mode == 'uninstall':
            warnings.append('Removing apps for user 0 requests retained data. Some apps require the original signed APK to restore.')
        if op == 'rollback-system':
            warnings.append('Restoring factory versions affects all profiles and may irreversibly delete app data.')
            help_text = self._pkg_shell(plan.serial, 'pm', 'help')
            if not re.search(r'^\s*uninstall-system-updates\s+\[<?(?:PACKAGE(?:_NAME)?|package(?:_name)?)>?\]', help_text, re.M):
                raise _error('This firmware does not advertise a package-specific rollback command.')
            system = self._pkg_list(plan.serial, '-s')
        for p in requested:
            guard_op = op
            if op == 'undo' and p in (*UPDATERS, OFFERS):
                guard_op = 'ads-restore' if p == OFFERS else 'ota-enable'
            _guard_selection(p, guard_op)
            before = states.get(p, 'missing')
            if before == 'missing' or before == 'uninstalled' and op not in {'undo', 'restore'}:
                if op == 'undo' and before == 'missing':
                    details.append(f'Skipped {p}: original signed APK required. Its undo record will be kept.')
                    continue
                if op == 'debloat' or op.startswith('ota-'):
                    details.append(f'Skipped {p}: absent for owner user 0.')
                    continue
                raise _error(f'{p} is unavailable for this operation. Restoring a missing app requires its original signed APK.')
            if op in _STATE_OPS:
                target = saved[p] if op == 'undo' else _state_after(mode, before)
                if target == before and op != 'undo':
                    details.append(f'Skipped {p}: already {target}.')
                    continue
                details.append(f'{p}: {before} → {target} for owner user 0.')
            elif op == 'launch':
                if before != 'enabled':
                    raise _error(f'Enable {p} before launching it.')
                snapshot['activity/' + p] = self._pkg_activity(plan.serial, 'LAUNCHER', p)
                details.append('Launch ' + snapshot['activity/' + p] + ' for owner user 0.')
            elif op == 'rollback-system':
                paths = self._pkg_paths(plan.serial, p)
                if p not in system or not all(path.startswith('/data/app/') for path in paths):
                    raise _error(f'{p} has no confirmed installed system update.')
                snapshot['paths/' + p] = '\n'.join(paths)
                details.append(f'Remove installed system updates for {p} and restore its factory version.')
            else:
                details.append(f'{op} {p} for owner user 0.')
            selected.append(p)
            snapshot[p] = before
        if not selected:
            raise _error('No matching packages require this change. ' + ' '.join(details))
        if mode in {'disable', 'uninstall', 'clear-data', 'force-stop', 'rollback-system'}:
            self._pkg_guard_active(plan.serial, selected, states)
        if op in _STATE_OPS:
            warnings.append('Package changes run one at a time. Undo records the previous owner package states.')
        return replace(plan, packages=tuple(selected), details=tuple(details), warnings=tuple(warnings),
                       snapshot=tuple(snapshot.items()))

    def _pkg_paths(self, serial, package):
        lines = self._pkg_shell(serial, 'pm', 'path', *_OWNER, package).splitlines()
        if not lines or any(not re.fullmatch(r'package:/[^\x00-\x1f\x7f]+\.apk', line) for line in lines):
            raise _error(f'Cannot determine installed APK locations for {package}.')
        return tuple(sorted(line.removeprefix('package:') for line in lines))

    def _pkg_component_plan(self, plan, states):
        op, params = plan.operation, plan.params
        snap = {}
        warnings = []
        if op == 'keyboard-set':
            target = params.get('component', '')
            services = self._pkg_shell(plan.serial, 'ime', 'list', '-s', '-a').splitlines()
            if _component(target) not in {_component(s) for s in services}:
                raise _error('The requested keyboard service is not listed by Android.')
            snap['previous'] = self._pkg_keyboard(plan.serial)
            warnings.append('The selected keyboard can read input you type.')
        else:
            snap['previous'] = self._pkg_activity(plan.serial, 'HOME', allow_unresolved=(op == 'launcher-restore'))
            snap['stock'] = states.get(STOCK_HOME, 'missing')
            if op == 'launcher-restore':
                if snap['stock'] not in {'enabled', 'disabled'}:
                    raise _error('The stock Fire launcher is unavailable for owner user 0.')
                target = self._pkg_activity(plan.serial, 'HOME', STOCK_HOME, snap['stock'] == 'disabled')
            else:
                target = params.get('component', '')
                target_pkg = _component(target).split('/')[0]
                if params.get('disable_stock', 'false') not in {'true', 'false'}:
                    raise _error('disable_stock must be true or false.')
                if params.get('disable_stock') == 'true' and (target_pkg == STOCK_HOME or snap['stock'] not in {'disabled', 'enabled'}):
                    raise _error('Disabling stock requires a distinct replacement HOME and an installed Fire launcher.')
                if _component(self._pkg_activity(plan.serial, 'HOME', target_pkg)) != _component(target):
                    raise _error('The selected component must resolve as a HOME activity in its package.')
            warnings.append('Fire OS may refuse the default launcher change. HOME resolution will be checked.')
        package = _component(target).split('/')[0]
        if op != 'launcher-restore' and states.get(package) != 'enabled':
            raise _error('The selected component package must be installed and enabled.')
        snap.update(target=target, package_state=states.get(package, 'missing'))
        details = [f'Current default: {snap["previous"]}', f'Set default to {target} for owner user 0.']
        if op == 'launcher-restore':
            details.append('Enable the Fire launcher first, then resolve and select its HOME activity.')
        if params.get('disable_stock') == 'true':
            details.append('Disable Fire Launcher only after confirming the new HOME resolves.')
        return replace(plan, details=tuple(details), warnings=tuple(warnings), snapshot=tuple(snap.items()))

    def _pkg_apk_plan(self, plan, requested):
        raw_paths = json.loads(plan.params.get('paths') or 'null')
        if not isinstance(raw_paths, list) or not 1 <= len(raw_paths) <= 32:
            raise _error('Choose 1 to 32 local standalone APK files.')
        if any(not isinstance(p, str) or len(p) > 4096 or not Path(p).is_absolute() for p in raw_paths):
            raise _error('Every APK path must be absolute.')
        verifier = self._verifier()
        apks = tuple(verifier.inspect(Path(p)) for p in raw_paths)
        self._pkg_validate_apks(plan, requested, apks)
        states = self._pkg_states(plan.serial)
        snapshot = {apk.package: states.get(apk.package, 'missing') for apk in apks}
        warnings = ['Review the signer certificate for each APK. Installation may replace apps and is not atomic.']
        if plan.operation == 'system-update':
            p = requested[0]
            if p not in self._pkg_list(plan.serial, '-s') or snapshot[p] not in {'enabled', 'disabled'}:
                raise _error('Select an installed system package for the update.')
            snapshot['paths/' + p] = '\n'.join(self._pkg_paths(plan.serial, p))
            warnings.append('Updating a built-in component can affect all profiles and device operation. Android enforces signing continuity.')
        return replace(plan, packages=tuple(apk.package for apk in apks), apks=apks,
                       details=tuple(
                           f'{apk.package} {apk.version_name} (code {apk.version_code}) for user 0. '
                           f'Signer SHA-256: {", ".join(apk.signer_sha256)}. File SHA-256: {apk.sha256}'
                           for apk in apks), warnings=tuple(warnings), snapshot=tuple(snapshot.items()))

    def _pkg_validate_apks(self, plan, requested, apks):
        signer = plan.params.get('signer', '').lower()
        if signer and not re.fullmatch('[0-9a-f]{64}', signer):
            raise _error('Enter a hexadecimal SHA-256 signer certificate digest.')
        names = _selection(tuple(apk.package for apk in apks))
        if plan.operation == 'system-update' and (len(requested) != 1 or names != requested):
            raise _error('A system update requires one APK matching its selected package.')
        for apk in apks:
            if plan.operation == 'sideload':
                _guard_selection(apk.package, 'sideload')
            if apk.split or not 0 < apk.min_sdk <= plan.device.sdk:
                raise _error(f'{apk.package} is split or incompatible with Android SDK {plan.device.sdk}.')
            if apk.abis and not set(apk.abis).intersection(plan.device.abis):
                raise _error(f'{apk.package} does not support this device ABI.')
            if not apk.signer_sha256 or any(not re.fullmatch('[0-9a-f]{64}', s) for s in apk.signer_sha256):
                raise _error(f'Missing verified signing identity for {apk.package}.')
            if signer and set(apk.signer_sha256) != {signer}:
                raise _error(f'Signer mismatch for {apk.package}.')
            if apk.package in _GOOGLE and set(apk.signer_sha256) != {GOOGLE_SIGNER_SHA256}:
                raise _error(f'Google signing certificate mismatch for {apk.package}.')

    def _pkg_install(self, plan, completed):
        self._pkg_validate_apks(plan, plan.packages, plan.apks)
        if not 1 <= len(plan.apks) <= 32 or tuple(apk.package for apk in plan.apks) != plan.packages:
            raise _error('Invalid APK installation plan.')
        verifier = self._verifier()
        with tempfile.TemporaryDirectory(prefix='fire-tools-install-') as staging:
            staged = []
            for index, apk in enumerate(plan.apks):
                target = Path(staging) / f'{index}.apk'
                with _open_regular_file(apk.path) as (source, size):
                    if not 0 < size <= MAX_APK_BYTES:
                        raise _error('Choose a regular APK of at most 512 MiB.')
                    with target.open('xb') as output:
                        remaining = MAX_APK_BYTES
                        while block := source.read(min(1024 * 1024, remaining + 1)):
                            remaining -= len(block)
                            if remaining < 0:
                                raise _error('APK grew beyond 512 MiB during staging.')
                            output.write(block)
                if file_sha256(target) != apk.sha256:
                    raise _error('APK contents changed since preview. Review again.')
                checked = verifier.inspect(target)
                if checked != replace(apk, path=target):
                    raise _error('Staged APK metadata or signer changed since preview.')
                staged.append(checked)
            snap = dict(plan.snapshot)
            current = self._pkg_states(plan.serial)
            if any(current.get(p, 'missing') != snap[p] for p in plan.packages):
                raise _error('Package state changed since preview.')
            for apk in staged:
                if self._pkg_states(plan.serial).get(apk.package, 'missing') != snap[apk.package]:
                    raise _error('Package state changed since preview.')
                if plan.operation == 'system-update':
                    if (apk.package not in self._pkg_list(plan.serial, '-s') or
                            '\n'.join(self._pkg_paths(plan.serial, apk.package)) != snap['paths/' + apk.package]):
                        raise _error('System package changed since preview.')
                if file_sha256(apk.path) != apk.sha256:
                    raise _error('Staged APK changed before installation.')
                self._pkg_device(plan)
                self.adb.install(plan.serial, apk.path)
                completed.append(f'Android accepted the install request for {apk.package}.')
                if apk.package not in self._pkg_list(plan.serial):
                    raise _error(f'{apk.package} was not found in the owner package inventory after installation.')
                paths = self._pkg_paths(plan.serial, apk.package)
                if len(paths) != 1:
                    raise _error(f'Cannot verify a standalone installed APK for {apk.package}.')
                with tempfile.TemporaryDirectory(dir=staging, prefix='readback-') as directory:
                    installed = Path(directory) / 'installed.apk'
                    self._pull_device_file(plan.device, paths[0], installed, expected_size=apk.path.stat().st_size)
                    if file_sha256(installed) != apk.sha256:
                        raise _error(f'The installed bytes for {apk.package} do not match the reviewed APK.')
                # The installed bytes match the signed APK whose manifest supplied this version.
                completed[-1] = f'Verified installed {apk.package} version {apk.version_code} for owner user 0.'

    def _pkg_move(self, plan, p, before, target, completed):
        if target == before:
            return
        if before == 'uninstalled':
            self._pkg_write(plan, 'cmd', 'package', 'install-existing', *_OWNER, p)
            before = self._pkg_states(plan.serial).get(p, 'missing')
            if before not in {'enabled', 'disabled'}:
                raise _error(f'Installation for user 0 could not be confirmed for {p}.')
            if before != target:
                completed.append(f'Reinstalled {p} for user 0 and verified its {before} state.')
        if before != target:
            if target == 'uninstalled':
                self._pkg_write(plan, 'pm', 'uninstall', '-k', *_OWNER, p)
            else:
                self._pkg_write(plan, 'pm', 'disable-user' if target == 'disabled' else 'enable', *_OWNER, p)
            after = self._pkg_states(plan.serial).get(p, 'missing')
            # A third-party package with no other installations can disappear from -u too.
            if after != target and (target, after) != ('uninstalled', 'missing'):
                raise _error(f'Android did not confirm {p} as {target}. Saved undo information was retained.')

    def _pkg_apply_state(self, plan, completed):
        from .service import ToolkitError
        data, previous = self._pkg_undo_record(plan.device)
        recorded = {}
        snapshot = dict(plan.snapshot)
        saved_digest = hashlib.sha256(json.dumps(previous, sort_keys=True).encode()).hexdigest()
        if saved_digest != snapshot['undo-digest']:
            raise _error('The saved package undo state changed since preview.')
        op = plan.operation
        for p in plan.packages:
            before = snapshot[p]
            current = self._pkg_states(plan.serial)
            if current.get(p, 'missing') != before:
                raise _error(f'{p} changed since preview. Review a fresh plan.')
            target = (previous[p] if op == 'undo' else
                      _state_after(plan.params.get('mode', 'disable') if op == 'debloat' else op, before))
            if before != target:
                if target in {'disabled', 'uninstalled'}:
                    self._pkg_guard_active(plan.serial, (p,), current)
                self._pkg_device(plan)
                first_change = op != 'undo' and not recorded
                if op != 'undo':
                    recorded[p] = before
                    if first_change:
                        self._pkg_save_undo(plan.device, data, previous, pending=recorded)
                    else:
                        self._pkg_save_undo(plan.device, data, recorded)
                try:
                    self._pkg_move(plan, p, before, target, completed)
                except (ToolkitError, AdbError, OSError, RuntimeError) as exc:
                    if first_change:
                        try:
                            self._pkg_device(plan)
                            after = self._pkg_states(plan.serial).get(p, 'missing')
                        except (ToolkitError, AdbError, OSError, RuntimeError):
                            raise _error(f'{exc} The first change is unverified. Both undo records were retained.') from exc
                        self._pkg_save_undo(plan.device, data, previous if after == before else recorded)
                    raise
                completed.append(f'{p}: {target} for user 0.')
                if first_change:
                    self._pkg_save_undo(plan.device, data, recorded)
        if op == 'undo':
            remaining = {p: state for p, state in previous.items() if p not in plan.packages}
            self._pkg_save_undo(plan.device, data, remaining)
            completed.append('Previous owner states confirmed for the reviewed packages.')

    def _pkg_apply_component(self, plan, completed):
        snap = dict(plan.snapshot)
        target = snap['target']
        if plan.operation == 'keyboard-set':
            self._pkg_write(plan, 'ime', 'enable', target)
            completed.append(f'Android accepted enabling keyboard {target}.')
            self._pkg_write(plan, 'ime', 'set', target)
            if _component(self._pkg_keyboard(plan.serial)) != _component(target):
                raise _error('Android did not confirm the requested default keyboard.')
            completed.append('Default keyboard confirmed: ' + target)
            return
        if plan.operation == 'launcher-restore' and snap['stock'] == 'disabled':
            self._pkg_write(plan, 'pm', 'enable', *_OWNER, STOCK_HOME)
            if self._pkg_states(plan.serial).get(STOCK_HOME) != 'enabled':
                raise _error('Stock Fire launcher enablement could not be confirmed.')
            completed.append('Enabled the stock Fire launcher.')
        if _component(self._pkg_activity(plan.serial, 'HOME', target.split('/')[0])) != _component(target):
            raise _error('The requested HOME activity no longer resolves.')
        self._pkg_write(plan, 'pm', 'set-home-activity', *_OWNER, target)
        if _component(self._pkg_activity(plan.serial, 'HOME')) != _component(target):
            raise _error('Android did not confirm the requested HOME activity.')
        completed.append('Confirmed HOME activity ' + target)
        if plan.params.get('disable_stock') == 'true' and snap['stock'] == 'enabled':
            if (_component(self._pkg_activity(plan.serial, 'HOME')) != _component(target)
                    or self._pkg_states(plan.serial).get(target.split('/')[0]) != 'enabled'):
                raise _error('Replacement HOME is unavailable. Stock launcher remains enabled.')
            self._pkg_write(plan, 'pm', 'disable-user', *_OWNER, STOCK_HOME)
            if self._pkg_states(plan.serial).get(STOCK_HOME) != 'disabled':
                raise _error('Could not confirm that Fire Launcher is disabled.')
            completed.append('Confirmed the stock Fire launcher is disabled.')

    def _execute_package_workflow(self, plan, completed, log):
        op = plan.operation
        if op in _APK_OPS:
            self._pkg_install(plan, completed)
            return
        explicit = plan.packages if op in _SIMPLE or op.startswith('ota-') else ()
        current = self.plan_package_action(plan.serial, op, explicit, **plan.params)
        if current.snapshot != plan.snapshot or current.packages != plan.packages or current.device != plan.device:
            raise _error('The package selection, saved undo target or device state changed since preview. Review again.')
        if op in _STATE_OPS:
            self._pkg_apply_state(plan, completed)
            return
        if op in {'launcher-set', 'launcher-restore', 'keyboard-set'}:
            self._pkg_apply_component(plan, completed)
            return
        snap = dict(plan.snapshot)
        for p in plan.packages:
            states = self._pkg_states(plan.serial)
            if states.get(p) != snap[p]:
                raise _error(f'{p} changed since preview.')
            if op in {'clear-data', 'force-stop', 'rollback-system'}:
                self._pkg_guard_active(plan.serial, (p,), states)
            if op == 'clear-data':
                output = self._pkg_write(plan, 'pm', 'clear', *_OWNER, p)
                if output != 'Success':
                    raise _error('Android did not confirm clearing app data.')
                completed.append(f'Android confirmed clearing owner data for {p}.')
            elif op == 'force-stop':
                self._pkg_write(plan, 'am', 'force-stop', *_OWNER, p)
                status = self._pkg_shell(plan.serial, 'dumpsys', 'package', p)
                if not re.search(r'^\s*User 0:.*\bstopped=true\b', status, re.M):
                    raise _error(f'Stop command issued but the stopped state could not be verified for {p}.')
                completed.append(f'Confirmed {p} stopped for owner user 0.')
            elif op == 'launch':
                activity = self._pkg_activity(plan.serial, 'LAUNCHER', p)
                if activity != snap['activity/' + p]:
                    raise _error('Launch activity changed since preview.')
                output = self._pkg_write(plan, 'am', 'start', '-W', *_OWNER, '-n', activity)
                if not re.search(r'^Status:\s*ok\s*$', output, re.M):
                    raise _error('Android did not confirm the activity launch.')
                completed.append(f'Android accepted launching {activity}.')
            elif op == 'rollback-system':
                if '\n'.join(self._pkg_paths(plan.serial, p)) != snap['paths/' + p]:
                    raise _error('System APK locations changed since preview.')
                self._pkg_write(plan, 'pm', 'uninstall-system-updates', p)
                paths = self._pkg_paths(plan.serial, p)
                if not all(path.startswith(('/system/', '/product/', '/system_ext/', '/vendor/', '/odm/', '/oem/')) for path in paths):
                    raise _error(f'The factory version of {p} could not be confirmed.')
                completed.append(f'Confirmed factory APK locations for {p}.')
            else:
                raise _error('Unknown package workflow.')
