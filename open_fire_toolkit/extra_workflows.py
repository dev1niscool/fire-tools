"""Preview-first settings, transport, and shared-storage utilities."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from ipaddress import IPv4Address
import os
from pathlib import PurePosixPath
import re
from subprocess import CompletedProcess
from typing import Callable
from uuid import uuid4

from .adb import AdbError, DeviceInfo
from .device_workflows import (
    PACKAGE, _args, _choice, _fail, _identity, _integer, _json, _load, _pattern,
    _pinned_directory, _private_stage, _read_file, _remote, _text, _write_json,
)
from .workflows import TransportPlan, WorkflowPlan


SETTINGS_PAGES = {
    'accounts': 'SYNC_SETTINGS',
    'google-account-add': 'ADD_ACCOUNT_SETTINGS',
    'security': 'SECURITY_SETTINGS',
    'applications': 'APPLICATION_SETTINGS',
    'accessibility': 'ACCESSIBILITY_SETTINGS',
    'wifi': 'WIFI_SETTINGS',
    'vpn': 'VPN_SETTINGS',
    'location': 'LOCATION_SOURCE_SETTINGS',
    'unknown-sources': 'MANAGE_UNKNOWN_APP_SOURCES',
    'app-details': 'APPLICATION_DETAILS_SETTINGS',
}
DNS_KEYS = ('private_dns_specifier', 'private_dns_mode')
DNS_STATE_SCHEMA = 'fire-tools.private-dns-undo.v1'
DNS_STATE_LIMIT = 8192
NETWORK_OVERRIDES = ('undefined', 'true', 'false')
HOST_TRANSPORT_OPERATIONS = {'wireless-connect': 'connect', 'wireless-disconnect': 'disconnect'}
ADB_TRANSPORT_LABELS = {'emu', 'tcp', 'vsock', 'acceptfd', 'local', 'localabstract',
                        'localfilesystem', 'localreserved'}
ADB_STARTUP_NOTICES = {
    '* daemon not running; starting now at tcp:5037',
    '* daemon not running; starting now at tcp:localhost:5037',
    '* daemon started successfully',
}
OPTIONAL_FORM_FIELDS = {
    'settings-open': 'package',
    'battery-exemption': 'package',
    'wireless-enable': 'port',
    'private-dns': 'hostname',
}
SOURCES = (
    ('FOSS', 'F-Droid', 'org.fdroid.fdroid', 'https://f-droid.org/'),
    ('FOSS', 'NewPipe', 'org.schabi.newpipe', 'https://newpipe.net/'),
    ('FOSS', 'VLC', 'org.videolan.vlc', 'https://www.videolan.org/vlc/download-android.html'),
    ('FOSS', 'K-9 Mail', 'com.fsck.k9', 'https://k9mail.app/'),
    ('FOSS', 'Fennec F-Droid', 'org.mozilla.fennec_fdroid',
     'https://f-droid.org/packages/org.mozilla.fennec_fdroid/'),
    ('FOSS', 'Aurora Store', 'com.aurora.store', 'https://auroraoss.com/'),
    ('Browser', 'Firefox', 'org.mozilla.firefox', 'https://www.mozilla.org/firefox/browsers/mobile/android/'),
    ('Launcher', 'Lawnchair', 'app.lawnchair', 'https://lawnchair.app/'),
    ('Launcher', 'KISS Launcher', 'fr.neamar.kiss', 'https://kisslauncher.com/'),
    ('Keyboard', 'HeliBoard', 'helium314.keyboard', 'https://github.com/Helium314/HeliBoard'),
    ('Keyboard', 'AnySoftKeyboard', 'com.menny.android.anysoftkeyboard', 'https://anysoftkeyboard.github.io/'),
    ('Streaming', 'Netflix', 'com.netflix.mediaclient',
     'https://play.google.com/store/apps/details?id=com.netflix.mediaclient'),
    ('Streaming', 'Disney+', 'com.disney.disneyplus',
     'https://play.google.com/store/apps/details?id=com.disney.disneyplus'),
)


def source_catalog_text() -> str:
    return '\n'.join([
        'App sources and official store listings. Compatibility, account sign-in, and streaming playback depend on the tablet and provider.',
        *(f'{group} | {name} | {package}\n{url}' for group, name, package, url in SOURCES),
    ])


def _hostname(value: str, *, dotted: bool = False) -> str:
    _text(value, 'hostname', 253)
    labels = value.split('.')
    if ((dotted and len(labels) < 2)
            or not re.search(r'[A-Za-z]', labels[-1])
            or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
                   for label in labels)):
        _fail('Enter a valid DNS hostname.')
    return value


def _endpoint(value: str) -> str:
    _text(value, 'ADB endpoint', 260)
    host, sep, port = value.partition(':')
    if not sep:
        _fail('Enter an IPv4 address or DNS hostname followed by :port.')
    if re.fullmatch(r'[0-9.]+', host):
        try:
            host = str(IPv4Address(host))
        except ValueError:
            _fail('Enter a valid IPv4 address.')
    else:
        host = _hostname(host).lower()
        if host in ADB_TRANSPORT_LABELS:
            _fail('This hostname is reserved by ADB. Enter an IPv4 address or a qualified DNS name.')
    return f'{host}:{_integer(port, 1, 65535, "Port")}'


def _shared_path(value: str) -> str:
    if (not value.startswith('/sdcard/') or value.endswith('/')
            or any(part.startswith('-') for part in value.split('/')[2:])):
        _fail('Specify a shared file or folder under /sdcard without option-like components.')
    return _remote(value)


def _setting_args(device: DeviceInfo, params: dict[str, str]) -> list[str]:
    target = params['target']
    action = SETTINGS_PAGES[target]
    if target == 'unknown-sources' and device.sdk < 26:
        action = SETTINGS_PAGES['security']
    args = ['am', 'start', '--user', '0', '-a', 'android.settings.' + action]
    if target == 'app-details':
        args.extend(['-d', 'package:' + params['package']])
    if target == 'google-account-add':
        args.extend(['--esa', 'account_types', 'com.google'])
    return args


def _private_dns_values(values: object) -> dict[str, str | None]:
    if not isinstance(values, dict) or set(values) != set(DNS_KEYS):
        _fail('Private DNS snapshot is invalid.')
    for key, value in values.items():
        if value is not None:
            _text(value, key, limit=1024, empty=True)
    return values


@dataclass(frozen=True)
class _PrivateDnsJournal:
    values: dict[str, str | None]
    fingerprint: tuple[int, int, int, str]


def _publish_dns_entry(source, destination):
    if os.name == 'nt':
        os.rename(source, destination)
    else:
        os.link(source, destination, follow_symlinks=False)


def _transport_response(result: CompletedProcess[str], expected: set[str]) -> str:
    output = result.stdout.strip()
    diagnostics = [line for line in result.stderr.strip().splitlines()
                   if line and line not in ADB_STARTUP_NOTICES]
    if result.returncode or diagnostics or output not in expected:
        _fail('ADB did not confirm the transport request. ' + ('\n'.join(diagnostics) or output)[:512])
    return f'ADB transport reported {output}. Scan for tablets to continue.'


class ExtraWorkflows:
    """Additional workflows sharing DeviceWorkflows' storage and owner guards."""

    def read_extra_tool(self, serial: str, operation: str, **parameters: str) -> str:
        _args(parameters)
        if operation == 'source-catalog':
            return source_catalog_text()
        if operation != 'network-info':
            _fail('Unknown utility read operation.')
        from .service import ToolkitError
        device = self._writable_device(serial)
        sections = []
        for label, separator, read in (
            ('Private DNS settings', '=', lambda: self._read_private_dns(device)),
            ('Data Saver', '', lambda: self._read_data_saver(serial)),
            ('Known Wi-Fi networks (identifier;override)', ';', lambda: self._read_metered_networks(serial)),
        ):
            try:
                value = read()
            except (AdbError, ToolkitError):
                sections.append(f'{label}: unavailable on this tablet or connection.')
                continue
            if isinstance(value, dict):
                rows = [f'{key}{separator}{item if item is not None else "(not set)"}'
                        for key, item in value.items()]
                sections.append(f'{label}\n' + ('\n'.join(rows) if rows else '(none)'))
            else:
                sections.append(f'{label}: {"enabled" if value == "true" else "disabled"}')
        return '\n\n'.join(sections)

    def plan_extra_action(
            self, serial: str, operation: str, **parameters: str | bool | int) -> WorkflowPlan | TransportPlan:
        params = {key: 'true' if val is True else 'false' if val is False
                  else str(val) if type(val) is int else val for key, val in parameters.items()}
        if operation in HOST_TRANSPORT_OPERATIONS:
            return self._plan_host_transport(operation, params)
        device = self._writable_device(serial)
        optional = OPTIONAL_FORM_FIELDS.get(operation)
        if optional is not None and params.get(optional) == '':
            del params[optional]
        title, details, warnings, snapshot = self._preview_extra(device, operation, params)
        return WorkflowPlan(title, serial, tuple(details), tuple(warnings), 'extra_workflow',
                            device, operation, tuple(sorted(params.items())),
                            snapshot=tuple(sorted(snapshot.items())))

    def _preview_extra(self, device, operation, params):
        serial = device.serial
        snapshot = {}
        if operation == 'settings-open':
            _args(params, ('target',), ('package',))
            target = _choice(params['target'], tuple(SETTINGS_PAGES), 'settings page')
            if target == 'app-details':
                _args(params, ('target', 'package'))
                self._extra_installed_package(serial, params['package'])
            elif 'package' in params:
                _fail('Only the app details page accepts a package.')
            details = ['Request the tablet Settings page for ' + target + '.']
            if target == 'app-details':
                details.append('Owner package ' + params['package'] + '.')
            if target == 'unknown-sources' and device.sdk < 26:
                details.append('This Android version uses its Security page for unknown-source controls.')
            warnings = ['Complete any settings choices on the tablet.']
            if target in ('accounts', 'google-account-add'):
                warnings.append('Enter account credentials only on the tablet.')
            return 'Open tablet Settings', details, warnings, snapshot

        if operation in ('battery-exemption', 'widget-bind'):
            _args(params, ('enabled',) if operation == 'battery-exemption' else ('enabled', 'package'),
                  ('package',) if operation == 'battery-exemption' else ())
            package = self._extra_installed_package(serial, params.get('package', 'com.google.android.gms'))
            enable = _choice(params['enabled'], ('true', 'false'), 'enabled') == 'true'
            if operation == 'battery-exemption':
                command, current = self._read_battery_exemption(serial, package)
                snapshot.update(backend=command, enabled=str(current))
                details = [f'User battery exemption for {package} is currently {"present" if current else "absent"}.',
                           f'{"Add" if enable else "Remove"} the user battery exemption.']
                return 'Set user battery exemption', details, [
                    'Allowing background work can use more battery. Removing an exemption may delay background tasks and notifications.',
                    'The tablet retains its built-in battery exemptions.',
                ], snapshot
            current = self._read_widget_grant(serial, package)
            snapshot['enabled'] = str(current)
            details = [f'{"Grant" if enable else "Revoke"} widget binding for {package} on user 0.']
            if current is None:
                details.append('The tablet did not expose the current widget grant.')
            return 'Set widget binding permission', details, [
                'A granted host can bind and read information shown by widgets. Grant access only to a widget host you trust.',
            ], snapshot

        if operation in ('wireless-enable', 'wireless-usb'):
            return self._preview_extra_transport(operation, params)

        if operation in ('file-mkdir', 'file-delete', 'file-rename'):
            return self._preview_extra_file(serial, operation, params)

        if operation in ('private-dns', 'private-dns-undo'):
            return self._preview_private_dns(device, operation, params)

        if operation == 'data-saver':
            _args(params, ('enabled',))
            target = _choice(params['enabled'], ('true', 'false'), 'enabled')
            snapshot['enabled'] = self._read_data_saver(serial)
            return 'Set Data Saver', [f'Set the system background-data restriction to {target}.'], [
                'Data Saver can limit background use on metered networks and delay notifications.',
            ], snapshot
        if operation == 'wifi-metered':
            _args(params, ('network_id', 'metered'))
            target = _choice(params['metered'], NETWORK_OVERRIDES, 'metering override')
            network_id = _text(params['network_id'], 'Wi-Fi network identifier', 1024)
            if network_id.startswith('-'):
                _fail('Enter a Wi-Fi identifier from Network information.')
            networks = self._read_metered_networks(serial)
            if network_id not in networks:
                _fail('Copy the Wi-Fi identifier from Network information.')
            snapshot['metered'] = networks[network_id]
            return 'Set Wi-Fi metering override', [f'Change {network_id} from {networks[network_id]} to {target}.'], [
                'Metered networks can delay downloads and restrict background data.',
            ], snapshot
        _fail('Unknown utility action.')

    def _preview_extra_transport(self, operation, params):
        if operation == 'wireless-enable':
            _args(params, optional=('port',))
            port = _integer(params.get('port', '5555'), 1, 65535, 'Port')
            return 'Enable legacy ADB TCP transport', [f'Request the reviewed tablet listen on port {port}.'], [
                'Legacy ADB over TCP does not use encrypted wireless pairing. Use it only on a trusted local network and return to USB when finished.',
                'The tablet may disconnect while ADB restarts.',
            ], {}
        _args(params)
        return 'Return ADB transport to USB', ['Request USB debugging transport on the reviewed tablet.'], [
            'This request can immediately disconnect the tablet from ADB. Reconnect its USB cable to continue.',
        ], {}

    def _plan_host_transport(self, operation: str, params: dict[str, str]) -> TransportPlan:
        if operation not in HOST_TRANSPORT_OPERATIONS:
            _fail('Unknown host ADB transport action.')
        _args(params, ('endpoint',))
        endpoint = _endpoint(params['endpoint'])
        verb = HOST_TRANSPORT_OPERATIONS[operation]
        return TransportPlan(
            title=f'{verb.title()} an ADB endpoint',
            details=(f'Request {verb} for {endpoint} on the local ADB server.',),
            warnings=('Use an endpoint you control. After connecting, scan and explicitly select the intended tablet.',),
            operation=operation,
            parameters=(('endpoint', endpoint),),
        )

    def _extra_installed_package(self, serial, value):
        package = _pattern(_text(value, 'package', 255), PACKAGE, 'Android package ID')
        if package not in self.adb.packages(serial):
            _fail('The package is not installed for owner user 0.')
        return package

    def _read_battery_exemption(self, serial, package, backend=None):
        from .service import ToolkitError
        choices = {'cmd': ['cmd', 'deviceidle'], 'dumpsys': ['dumpsys', 'deviceidle']}
        for name in (backend,) if backend else tuple(choices):
            try:
                raw = self._device_shell(serial, [*choices[name], 'whitelist'])
                rows = raw.splitlines()
                if any(not re.fullmatch(
                    r'(?:system-excidle|system|user),[A-Za-z_][A-Za-z0-9_.]*,[0-9]+', row)
                        for row in rows):
                    _fail('Unable to read the device idle whitelist reliably.')
            except (AdbError, ToolkitError):
                if backend:
                    raise
                continue
            return name, any(row.split(',')[:2] == ['user', package] for row in rows)
        _fail('The tablet did not expose a readable device idle whitelist.')

    def _read_widget_grant(self, serial, package):
        from .service import ToolkitError
        try:
            raw = self._device_shell(serial, ['dumpsys', 'appwidget'])
        except (AdbError, ToolkitError):
            return None
        sections = raw.splitlines()
        headers = [index for index, line in enumerate(sections) if line.strip() == 'Grants:']
        if len(headers) != 1:
            return None
        found = False
        for line in sections[headers[0] + 1:]:
            if not line.strip():
                continue
            match = re.fullmatch(r'\s*\[[0-9]+\] user=([0-9]+) package=([A-Za-z0-9_.]+)\s*', line)
            if not match:
                return None
            found |= match.groups() == ('0', package)
        return found

    def _extra_file_fingerprint(self, serial, path):
        current = self._device_shell(serial, ['stat', '-c', '%d|%i|%f|%s|%y|%z', path])
        timestamps = r'[0-9 Tt:Zz.+-]{10,48}'
        return _pattern(current, rf'[0-9]+\|[0-9]+\|[0-9a-fA-F]+\|[0-9]+\|{timestamps}\|{timestamps}',
                        'shared file metadata')

    def _new_shared_path(self, serial, path):
        parent = self._storage_path(serial, str(PurePosixPath(path).parent), 'directory')
        self._require_new_remote(serial, path)
        return '|'.join(self._extra_file_fingerprint(serial, parent).split('|', 2)[:2])

    def _preview_extra_file(self, serial, operation, params):
        _args(params, ('remote', 'destination') if operation == 'file-rename' else ('remote',))
        path = _shared_path(params['remote'])
        if operation == 'file-mkdir':
            parent = self._new_shared_path(serial, path)
            return 'Create shared folder', [f'Create {params["remote"]}.'], [], {'parent': parent}
        self._storage_path(serial, path, 'regular file' if operation == 'file-delete' else None)
        snapshot = {'source': self._extra_file_fingerprint(serial, path)}
        if operation == 'file-delete':
            return 'Delete shared file', [f'Delete {params["remote"]}.'], [
                'This permanently deletes one regular file from the tablet.',
            ], snapshot
        kind = self._device_shell(serial, ['stat', '-c', '%F', path])
        if kind not in ('regular file', 'regular empty file', 'directory'):
            _fail('Choose a regular file or directory in shared storage.')
        dest = _shared_path(params['destination'])
        if dest == path or dest.startswith(path + '/'):
            _fail('Choose a different destination outside the source.')
        snapshot['parent'] = self._new_shared_path(serial, dest)
        return 'Rename shared file or folder', [f'Move {params["remote"]} to {params["destination"]}.'], [], snapshot

    def _private_dns_state(self, device, parent=None):
        identity = _identity(device)
        name = 'private-dns-' + identity['serial_sha256'] + '.json'
        directory_context = self._journal_directory() if parent is None else nullcontext(parent)
        try:
            with directory_context as directory:
                return name, self._read_private_dns_journal(directory / name, identity)
        except FileNotFoundError:
            return name, None

    def _read_private_dns_journal(self, path, identity):
        before = path.lstat()
        digest, content = _read_file(path, DNS_STATE_LIMIT, content=True)
        after = path.lstat()
        if (not os.path.samestat(before, after) or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            _fail('The Private DNS undo journal changed while being read. Review again.')
        document = _load(content)
        if (not isinstance(document, dict) or document.get('schema') != DNS_STATE_SCHEMA
                or document.get('device') != identity):
            _fail('Private DNS undo state is invalid or belongs to a different tablet.')
        values = _private_dns_values(document.get('values'))
        return _PrivateDnsJournal(values, (after.st_dev, after.st_ino, after.st_mtime_ns, digest))

    def _save_private_dns_state(self, path, device, values):
        identity = _identity(device)
        document = dict(schema=DNS_STATE_SCHEMA, device=identity, values=values)
        if len(_json(document).encode('utf-8')) + 1 > DNS_STATE_LIMIT:
            _fail('Private DNS undo state exceeds its supported size.')
        with _private_stage(path.parent) as directory:
            stage = directory / 'snapshot'
            _write_json(stage, document)
            stage.chmod(0o600)
            journal = self._read_private_dns_journal(stage, identity)
            try:
                _publish_dns_entry(stage, path)
            except FileExistsError:
                _fail('A Private DNS undo journal appeared during publication. Its contents were preserved.')
        return journal

    def _require_private_dns_journal(self, path, identity, expected):
        from .service import ToolkitError
        message = 'The Private DNS undo journal changed or became unreadable. Review again.'
        try:
            observed = self._read_private_dns_journal(path, identity)
        except (OSError, ToolkitError) as exc:
            raise ToolkitError(message) from exc
        if observed != expected:
            _fail(message)

    def _consume_private_dns_journal(self, path, identity, expected):
        from .service import ToolkitError
        self._require_private_dns_journal(path, identity, expected)
        held = path.with_name(f'.{path.name}.consuming-{uuid4().hex}')
        # Move the entry before deleting it so a file arriving at the usual
        # name after the check cannot be unlinked there.
        os.rename(path, held)
        try:
            self._require_private_dns_journal(held, identity, expected)
        except ToolkitError:
            try:
                _publish_dns_entry(held, path)
            except OSError:
                _fail(f'The Private DNS undo journal changed. The moved entry was preserved as {held.name}.')
            if os.name != 'nt':
                held.unlink()
            raise
        held.unlink()

    def _require_private_dns_directory(self, parent):
        from .service import ToolkitError
        try:
            with _pinned_directory(self.state_dir.absolute()) as canonical:
                if canonical.samefile(parent):
                    return
        except (OSError, ToolkitError):
            pass
        _fail('The Private DNS undo directory changed before the device mutation. Review again.')

    def _read_private_dns(self, device):
        if device.sdk < 28:
            _fail('Android Private DNS requires Android 9 or newer.')
        table = self._device_table(device.serial, 'global')
        return _private_dns_values({key: table.get(key) for key in DNS_KEYS})

    def _preview_private_dns(self, device, operation, params):
        current = self._read_private_dns(device)
        _, journal = self._private_dns_state(device)
        if operation == 'private-dns-undo':
            _args(params)
            if journal is None:
                _fail('There is no saved Private DNS configuration to restore.')
            target = journal.values
            title = 'Restore saved Private DNS settings'
        else:
            _args(params, ('mode',), ('hostname',))
            mode = _choice(params['mode'], ('off', 'opportunistic', 'hostname'), 'Private DNS mode')
            if mode == 'hostname':
                _args(params, ('mode', 'hostname'))
                host = _hostname(params['hostname'], dotted=True)
            else:
                if 'hostname' in params:
                    _fail('A resolver hostname applies only to hostname mode.')
                host = current['private_dns_specifier']
            target = dict(private_dns_mode=mode, private_dns_specifier=host)
            title = 'Configure Private DNS'
        details = [f'{key}: {current[key] if current[key] is not None else "(not set)"} → '
                   f'{target[key] if target[key] is not None else "(not set)"}' for key in DNS_KEYS]
        return title, details, [
            'A resolver that is unreachable or lacks DNS-over-TLS can break network access. Readback checks the stored configuration.',
        ], {'current': _json(current), 'target': _json(target),
            'undo': _json(journal.fingerprint if journal is not None else None)}

    def _read_data_saver(self, serial):
        raw = self._device_shell(serial, ['cmd', 'netpolicy', 'get', 'restrict-background'])
        match = re.fullmatch(r'Restrict background status:\s*(enabled|disabled)', raw.strip())
        if not match:
            _fail('Unable to read Data Saver status reliably.')
        return 'true' if match.group(1) == 'enabled' else 'false'

    def _read_metered_networks(self, serial):
        raw = self._device_shell(serial, ['cmd', 'netpolicy', 'list', 'wifi-networks'])
        networks = {}
        for line in raw.splitlines():
            identifier, sep, mode = line.rpartition(';')
            if not sep or mode not in ('none', *NETWORK_OVERRIDES) or identifier in networks:
                _fail('Unable to read Wi-Fi metering overrides reliably.')
            _text(identifier, 'Wi-Fi network identifier', 1024)
            networks[identifier] = 'undefined' if mode == 'none' else mode
        return networks

    def _execute_extra_workflow(
            self, plan: WorkflowPlan, completed: list[str], log: Callable[[str], None]) -> None:
        if type(plan) is not WorkflowPlan or plan.action != 'extra_workflow':
            _fail('Expected a reviewed tablet utility plan.')
        current = self.plan_extra_action(plan.serial, plan.operation, **plan.params)
        if current != plan:
            _fail('The selected tablet, reviewed inputs, or tablet state changed after preview.')
        operation = plan.operation
        serial = plan.serial
        params = plan.params
        snapshot = dict(plan.snapshot)
        self._device_guard(plan)
        if operation == 'settings-open':
            output = self._device_shell(serial, _setting_args(plan.device, params))
            if not any(line.startswith('Starting: Intent {') for line in output.splitlines()):
                _fail('The tablet did not acknowledge the Settings screen request.')
            completed.append('Settings screen requested. Complete the action on the tablet.')
        elif operation == 'battery-exemption':
            enabled = params['enabled'] == 'true'
            package = params.get('package', 'com.google.android.gms')
            backend = snapshot['backend']
            prefix = ['cmd', 'deviceidle'] if backend == 'cmd' else ['dumpsys', 'deviceidle']
            self._device_shell(serial, [*prefix, 'whitelist', ('+' if enabled else '-') + package])
            verb = 'add' if enabled else 'remove'
            completed.append(f'Tablet accepted the request to {verb} the user battery exemption for {package}. '
                             'Verification pending.')
            self._device_guard(plan)
            _, observed = self._read_battery_exemption(serial, package, backend)
            if observed != enabled:
                _fail('The requested user battery exemption was not confirmed.')
            completed[-1] = f'User battery exemption {"present" if enabled else "absent"} for {package}, verified.'
        elif operation == 'widget-bind':
            enabled = params['enabled'] == 'true'
            package = params['package']
            self._device_shell(serial, ['appwidget', 'grantbind' if enabled else 'revokebind',
                                        '--package', package, '--user', '0'])
            verb = 'grant' if enabled else 'revoke'
            completed.append(f'Tablet accepted the request to {verb} widget binding for {package}. '
                             'Verification pending.')
            self._device_guard(plan)
            observed = self._read_widget_grant(serial, package)
            if observed is None:
                completed[-1] = f'Widget binding command accepted for {package}. The tablet did not expose grant readback.'
            elif observed != enabled:
                _fail('The requested widget permission was not confirmed.')
            else:
                completed[-1] = f'Widget binding {"granted" if enabled else "revoked"} for {package}, verified.'
        elif operation in ('wireless-enable', 'wireless-usb'):
            completed.append(self._execute_extra_transport(plan))
        elif operation.startswith('file-'):
            self._execute_extra_file(plan, snapshot, completed)
        elif operation in ('private-dns', 'private-dns-undo'):
            self._execute_private_dns(plan, snapshot, completed)
        elif operation == 'data-saver':
            target = params['enabled']
            status = 'enabled' if target == 'true' else 'disabled'
            self._device_shell(serial, ['cmd', 'netpolicy', 'set', 'restrict-background', target])
            completed.append(f'Tablet accepted the request to set Data Saver to {status}. Verification pending.')
            self._device_guard(plan)
            if self._read_data_saver(serial) != target:
                _fail('The requested Data Saver state was not confirmed.')
            completed[-1] = f'Data Saver {status}, verified.'
        elif operation == 'wifi-metered':
            network, target = params['network_id'], params['metered']
            write_needed = snapshot['metered'] != target
            if write_needed:
                try:
                    self._device_shell(serial, ['cmd', 'netpolicy', 'set', 'metered-network', network, target])
                except AdbError as exc:
                    # Some AOSP releases exit -1 even after writing the override.
                    if str(exc) != 'ADB exited with status 255.':
                        raise
                    completed.append(f'Wi-Fi metering request for {network} to {target} returned ADB status 255 '
                                     'and remains unverified.')
                else:
                    completed.append(f'Tablet accepted the request to set Wi-Fi metering for {network} to {target}. '
                                     'Verification pending.')
            self._device_guard(plan)
            if self._read_metered_networks(serial).get(network) != target:
                _fail('The requested Wi-Fi metering override was not confirmed.')
            message = f'Wi-Fi metering override {target} for {network}, verified.'
            if write_needed:
                completed[-1] = message
            else:
                completed.append(message)

    def _execute_transport(
            self, plan: TransportPlan, completed: list[str], log: Callable[[str], None]) -> None:
        if type(plan) is not TransportPlan or plan != self._plan_host_transport(plan.operation, plan.params):
            _fail('Expected a reviewed host ADB transport plan.')
        endpoint = plan.params['endpoint']
        verb = HOST_TRANSPORT_OPERATIONS[plan.operation]
        self._require_execution_directory()
        result = self.adb._run([verb, endpoint])
        expected = {f'disconnected {endpoint}'} if verb == 'disconnect' else {
            f'connected to {endpoint}', f'already connected to {endpoint}',
        }
        completed.append(_transport_response(result, expected))

    def _execute_extra_transport(self, plan):
        if plan.operation == 'wireless-enable':
            port = _integer(plan.params.get('port', '5555'), 1, 65535, 'Port')
            result = self.adb._run_device(plan.serial, ['tcpip', port])
            expected = {f'restarting in TCP mode port: {port}'}
        else:
            result = self.adb._run_device(plan.serial, ['usb'])
            expected = {'restarting in USB mode'}
        return _transport_response(result, expected)

    def _execute_extra_file(self, plan, snapshot, completed):
        serial = plan.serial
        operation = plan.operation
        remote = plan.params['remote']
        path = _shared_path(remote)
        if operation == 'file-mkdir':
            self._device_shell(serial, ['mkdir', path])
            completed.append(f'Tablet accepted the request to create folder {remote}. Verification pending.')
            self._device_guard(plan)
            self._storage_path(serial, path, 'directory')
            completed[-1] = f'Shared folder {remote} created and verified.'
            return
        if operation == 'file-delete':
            self._device_shell(serial, ['rm', path])
            completed.append(f'Tablet accepted the request to delete {remote}. Verification pending.')
            self._device_guard(plan)
            self._require_new_remote(serial, path)
            completed[-1] = f'Shared file {remote} deleted and absence verified.'
            return
        destination = plan.params['destination']
        dest = _shared_path(destination)
        self._device_shell(serial, ['mv', '-nT', path, dest])
        completed.append(f'Tablet accepted the request to rename {remote} to {destination}. Verification pending.')
        self._device_guard(plan)
        self._require_new_remote(serial, path)
        self._storage_path(serial, dest)
        actual = self._extra_file_fingerprint(serial, dest).split('|', 2)[:2]
        if actual != snapshot['source'].split('|', 2)[:2]:
            _fail('The renamed source could not be verified at the destination.')
        completed[-1] = f'Shared item renamed to {destination} and verified.'

    def _execute_private_dns(self, plan, snapshot, completed):
        current = _load(snapshot['current'])
        target = _load(snapshot['target'])
        restoring = plan.operation == 'private-dns-undo'
        keys = [key for key in DNS_KEYS if current[key] != target[key]]
        if not keys and not restoring:
            completed.append('Reviewed Private DNS values are stored.')
            return
        if target['private_dns_mode'] != 'hostname':
            keys.reverse()
        identity = _identity(plan.device)
        with self._journal_directory(create=not restoring) as parent:
            name, journal = self._private_dns_state(plan.device, parent)
            if _json(journal.fingerprint if journal is not None else None) != snapshot['undo']:
                _fail('The saved Private DNS configuration changed after preview.')
            state = parent / name
            if journal is None:
                journal = self._save_private_dns_state(state, plan.device, current)
            for key in keys:
                self._device_guard(plan)
                if self._read_private_dns(plan.device) != current:
                    _fail('Private DNS settings changed after preview.')
                value = target[key]
                args = ['delete', 'global', key] if value is None else ['put', 'global', key, value]
                self._require_private_dns_directory(parent)
                self._device_guard(plan)
                self._require_private_dns_journal(state, identity, journal)
                self._device_shell(plan.serial, ['settings', '--user', '0', *args])
                requested = f'remove {key}' if value is None else f'set {key} to {value}'
                completed.append(f'Tablet accepted the request to {requested}. Verification pending.')
                self._device_guard(plan)
                observed = self._read_private_dns(plan.device)
                if observed[key] != value:
                    _fail(f'The stored Private DNS setting {key} could not be verified.')
                completed[-1] = f'Stored Private DNS setting {key}, verified.'
                current[key] = value
                if observed != current:
                    _fail('A different Private DNS setting changed during the operation.')
            if restoring:
                self._device_guard(plan)
                if self._read_private_dns(plan.device) != target:
                    _fail('Private DNS settings changed before the undo journal could be consumed.')
                self._consume_private_dns_journal(state, identity, journal)
        completed.append('Saved Private DNS configuration restored.' if restoring
                         else 'Reviewed Private DNS values are stored.')
