"""Owner-scoped settings, diagnostics, storage transfers and device controls."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager, nullcontext
from contextvars import ContextVar
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import sys
import tempfile
from time import monotonic
import uuid

from .workflows import WorkflowPlan

_EXECUTION_DIRECTORY = ContextVar("execution_directory", default=None)

JSON_LIMIT = 1024 * 1024
FILE_LIMIT = 512 * 1024 * 1024
NAMESPACES = ('global', 'secure', 'system')
PRIVACY = {'limit_ad_tracking': '1', 'USAGE_METRICS_UPLOAD_ENABLED': '0',
           'usage_metrics_marketing_enabled': '0'}
ANIMATIONS = ('window_animation_scale', 'transition_animation_scale', 'animator_duration_scale')
# Backup formats are intentionally selective: a settings database can contain
# account IDs, security policy, privileged component bindings and opaque data.
PORTABLE = {
    'global': {'policy_control', *ANIMATIONS},
    'secure': set(PRIVACY),
    'system': {'screen_off_timeout', 'notification_sound', 'alarm_alert', 'ringtone',
               'accelerometer_rotation', 'user_rotation', 'time_12_24', 'font_scale'},
}
KEY = r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}'
PACKAGE = r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+'
COMPONENT = PACKAGE + r'/\.?[A-Za-z_$][A-Za-z0-9_.$]*'
PROTECTED = re.compile(
    r'adb|debug|developer|development|verifier|verify|verification|install|'
    r'unknown.source|package_verifier|credential|password|lock_pattern|lockscreen.disabled|'
    r'auth|provision|device_admin|device_owner|parental|accessibility|'
    r'enabled_.*(?:service|listener|method)|input_method|voice_interaction|assistant|'
    r'permission|security|restriction|enterprise|trusted|device_policy|usb_config|'
    r'vpn_lockdown|always_on_vpn|oem_unlock|safe_boot|keyguard|user_setup', re.I)
DENIED = re.compile(r'^\s*(?:error\b|failure\b|failed\b|exception\b|securityexception\b|'
                    r'java\.lang\.\w*exception\b|permission deni(?:ed|al)\b|unknown (?:option|command)\b)', re.I | re.M)
SHARED = '/storage/emulated/0'
HELPER = 'org.firetools.adshelper'
HELPER_PERMISSION = 'android.permission.WRITE_SECURE_SETTINGS'


def _fail(message):
    from .service import ToolkitError
    raise ToolkitError(message)


def _text(value, label, limit=4096, empty=False):
    if (not isinstance(value, str) or len(value) > limit or (not value and not empty)
            or any(not ch.isprintable() for ch in value)):
        _fail(f'Invalid or oversized {label}.')
    return value


def _pattern(value, expression, label):
    if not isinstance(value, str) or not re.fullmatch(expression, value, re.ASCII):
        _fail(f'Invalid {label}.')
    return value


def _choice(value, choices, label):
    if value not in choices:
        _fail(f'Invalid {label}. Expected one of {", ".join(choices)}.')
    return value


def _integer(value, low, high, label):
    if not re.fullmatch(r'[0-9]{1,10}', value, re.ASCII) or not low <= int(value) <= high:
        _fail(f'{label} must be an integer between {low} and {high}.')
    return str(int(value))


def _args(params, required=(), optional=()):
    if not set(required) <= params.keys() <= set(required) | set(optional):
        _fail(f'Expected parameters {", ".join(required) or "(none)"}. Optional: {", ".join(optional) or "(none)"}.')
    for name, value in params.items():
        _text(value, name, limit=32768, empty=True)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _load(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _fail('JSON contains a duplicate key.')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, RecursionError) as exc:
        _fail(f'Invalid JSON: {exc}')


def _key(namespace, key, writable=False):
    _choice(namespace, NAMESPACES, 'settings namespace')
    _pattern(key, KEY, 'settings key')
    if writable and PROTECTED.search(key):
        _fail('This security or connection setting requires its dedicated tablet controls.')


def _portable_value(ns, key, value):
    if value is None:
        return
    _text(value, 'settings snapshot value', empty=True)
    if ns == 'secure' or key == 'accelerometer_rotation':
        _choice(value, ('0', '1'), key)
    elif key == 'user_rotation':
        _choice(value, ('0', '1', '2', '3'), key)
    elif key == 'screen_off_timeout':
        _integer(value, 15000, 1800000, key)
    elif key in ANIMATIONS:
        _pattern(value, r'(?:[012](?:\.0+)?|[01]\.50*)', key)
    elif key == 'policy_control':
        _choice(value, ('immersive.full=*', 'immersive.navigation=*', 'immersive.status=*', 'null', ''), key)
    elif key == 'time_12_24':
        _choice(value, ('12', '24'), key)
    elif key == 'font_scale':
        if not re.fullmatch(r'[0-2](?:\.[0-9]{1,3})?', value) or not 0.5 <= float(value) <= 2:
            _fail('Unsupported font scale in snapshot.')
    else:
        _pattern(value, r'(?:content|file)://[^\s]+', 'sound URI')


def _remote(value):
    _text(value, 'shared storage path', 1024)
    if value.endswith('/') and value != '/':
        value = value.rstrip('/')
    if (not value.startswith('/') or any(part in ('', '.', '..') for part in value.split('/')[1:])
            or '\\' in value):
        _fail('Specify an absolute shared storage path without traversal.')
    for root in ('/sdcard', SHARED):
        if value == root or value.startswith(root + '/'):
            return SHARED + value[len(root):]
    _fail('The requested path must be under /sdcard or /storage/emulated/0.')


def _local(value, mode):
    _text(value, 'local path', 4096)
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or not path.name:
        _fail('A local absolute path without traversal is required.')
    for parent in (*reversed(path.parents), path):
        # Windows junctions are reparse points even on Python 3.11.
        if os.path.lexists(parent):
            info = parent.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                _fail('A local path component is a symlink or reparse point.')
    if not path.parent.is_dir():
        _fail('The local parent directory must exist.')
    if mode == 'new' and os.path.lexists(path):
        _fail('The local destination already exists.')
    if mode == 'file' and not path.is_file():
        _fail('The local source must be a regular file.')
    if mode == 'directory' and not path.is_dir():
        _fail('The local source must be a directory.')
    return path


@contextmanager
def _windows_hold(path, *, directory):
    # Denying share-write and share-delete keeps an opened component from
    # being converted into a junction, renamed, or replaced during use.
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    open_file = kernel.CreateFileW
    open_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                          wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    open_file.restype = wintypes.HANDLE
    attributes = kernel.GetFileInformationByHandleEx
    attributes.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    attributes.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    # FILE_READ_ATTRIBUTES, FILE_SHARE_READ, OPEN_EXISTING, and open the
    # reparse point itself, with directory backup semantics.
    handle = open_file(str(path), 0x80, 1, None, 3, 0x00200000 | 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        tag_info = (wintypes.DWORD * 2)()
        if not attributes(handle, 9, ctypes.byref(tag_info), ctypes.sizeof(tag_info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if tag_info[0] & 0x400 or bool(tag_info[0] & 0x10) != directory:
            _fail('Refusing a reparse point or unexpected file type in the local path.')
        yield
    finally:
        close(handle)


def _fd_directory(fd):
    # Linux ADB runs in a child with closed fds; use our PID, not /proc/self.
    candidates = [Path('/proc') / str(os.getpid()) / 'fd' / str(fd), Path('/dev/fd') / str(fd)]
    held = os.fstat(fd)
    for candidate in candidates:
        # A descriptor entry can report the right inode yet reject child
        # lookups. Keep the literal '/.' here since pathlib normalizes it.
        try:
            child = os.stat(f'{candidate}/.')
        except OSError:
            continue
        if os.path.samestat(held, child):
            return candidate
    _fail('This host cannot safely access files through an opened directory. '
          'Use Windows or Linux for operations that save state or files.')


@contextmanager
def _pinned_directory(path, *, create=False):
    """Yield a stable Path for read, staging, publication and cleanup."""
    path = Path(path).absolute()
    if '..' in path.parts:
        _fail('Parent traversal is unsupported for private state or output directories.')
    if os.name == 'nt':
        with ExitStack() as held:
            for current in (*reversed(path.parents), path):
                if create and not os.path.lexists(current):
                    current.mkdir(mode=0o700, exist_ok=True)
                held.enter_context(_windows_hold(current, directory=True))
            yield path
        return
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path.anchor, flags)
    try:
        for name in path.parts[1:]:
            try:
                child = os.open(name, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(name, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(name, flags, dir_fd=fd)
            except OSError as exc:
                if exc.errno in (errno.ENOTDIR, errno.ELOOP):
                    _fail('Refusing a symlink or non-directory component in ' + str(path))
                raise
            os.close(fd)
            fd = child
        yield _fd_directory(fd)
    finally:
        os.close(fd)


def _same_entry(path, expected):
    try:
        return os.path.samestat(path.lstat(), expected)
    except FileNotFoundError:
        return False


@contextmanager
def _private_stage(parent):
    # The parent is pinned, but the random staging name can still be
    # replaced in a shared output directory. Never rmtree that name.
    entry = Path(tempfile.mkdtemp(prefix='.fire-tools-', dir=parent))
    identity = entry.lstat()
    with ExitStack() as held:
        if os.name == 'nt':
            held.enter_context(_windows_hold(entry, directory=True))
            stage = entry
        else:
            fd = os.open(entry, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            held.callback(os.close, fd)
            stage = _fd_directory(fd)
        if not os.path.samestat(stage.stat(), identity) or any(stage.iterdir()):
            _fail('The staging directory changed before use. Its contents were preserved.')
        try:
            yield stage
        finally:
            # Clean only our two output names through the held directory.
            # Nested output is a private tree created for a directory export.
            # When the staging entry has been replaced, preserve both trees.
            if _same_entry(entry, identity):
                for name in ('snapshot', 'output'):
                    item = stage / name
                    try:
                        mode = item.lstat().st_mode
                    except FileNotFoundError:
                        continue
                    if name == 'output' and stat.S_ISDIR(mode):
                        shutil.rmtree(item)
                    elif not stat.S_ISDIR(mode):
                        item.unlink()
            # Windows requires the held handle to be closed before rmdir.
            held.close()
            if _same_entry(entry, identity):
                entry.rmdir()  # non-recursive; a populated replacement survives.


def _read_file(path, limit, output=None, *, content=False):
    hold = _windows_hold(path, directory=False) if os.name == 'nt' else nullcontext()
    with hold:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) |
                     getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            _fail('Expected a regular file within the size limit.')
        digest = hashlib.sha256()
        size = 0
        data = bytearray()
        while block := stream.read(min(limit - size + 1, JSON_LIMIT)):
            size += len(block)
            if size > limit:
                _fail('Local file exceeds the size limit.')
            digest.update(block)
            if output is not None:
                output.write(block)
            if content:
                data.extend(block)
        return digest.hexdigest(), bytes(data)


def _read_local(path, limit, output=None, *, content=False):
    source = _local(str(path), 'file')
    with _pinned_directory(source.parent) as parent:
        return _read_file(parent / source.name, limit, output, content=content)


def _write_json(path, document):
    data = (_json(document) + '\n').encode()
    if len(data) > JSON_LIMIT:
        _fail('Snapshot exceeds the 1 MiB limit.')
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _publish_directory(staged, dest):
    if os.name == 'nt':
        os.rename(staged, dest)  # Windows rename never replaces a destination.
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        code = libc.renameat2(-100, os.fsencode(staged), -100, os.fsencode(dest), 1)
    elif sys.platform == 'darwin' and hasattr(libc, 'renamex_np'):
        code = libc.renamex_np(os.fsencode(staged), os.fsencode(dest), 4)
    else:
        _fail('Atomic no-overwrite directory publication is unavailable on this host.')
    if code != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(dest))


@contextmanager
def _destination(value, directory, on_publish=None):
    dest = _local(value, 'new')
    with _pinned_directory(dest.parent) as parent, _private_stage(parent) as temp:
        target = parent / dest.name
        staged = temp / 'output'
        if directory:
            staged.mkdir(mode=0o700)
        yield staged
        _local(value, 'new')
        if not dest.parent.samefile(parent):
            _fail('The output directory changed during staging.')
        if directory:
            _publish_directory(staged, target)
        else:
            if not stat.S_ISREG(staged.lstat().st_mode):
                _fail('Transfer did not produce a regular file.')
            staged.chmod(0o600)
            if os.name == 'nt':
                os.rename(staged, target)
            else:
                os.link(staged, target)  # Atomic, fails if a destination appeared.
        if on_publish is not None:
            on_publish()


def _identity(device):
    return dict(model=device.model, sdk=device.sdk,
                serial_sha256=device.state_key)


def _command(args):
    return shlex.join(args)


class DeviceWorkflows:
    @contextmanager
    def _execution_directory(self):
        with _pinned_directory(self.state_dir, create=True) as held:
            token = _EXECUTION_DIRECTORY.set((self, held))
            try:
                yield held
            finally:
                _EXECUTION_DIRECTORY.reset(token)

    def _require_execution_directory(self):
        from .service import ToolkitError
        active = _EXECUTION_DIRECTORY.get()
        if active is None or active[0] is not self:
            return None
        held = active[1]
        try:
            with _pinned_directory(self.state_dir) as current:
                if current.samefile(held):
                    return held
        except (OSError, ToolkitError):
            pass
        _fail('The operation state directory changed. Preserve its undo records and review again.')

    @contextmanager
    def _journal_directory(self, *, create=False):
        held = self._require_execution_directory()
        if held is None:
            with _pinned_directory(self.state_dir, create=create) as directory:
                yield directory
        else:
            yield held
            self._require_execution_directory()

    def _device_shell(self, serial, args, timeout=30):
        output = self.adb.shell(serial, args, timeout)
        if DENIED.search(output):
            _fail('Tablet reported an error. ' + output[:512])
        return output

    def _device_guard(self, plan):
        if self._writable_device(plan.serial) != plan.device:
            _fail('The tablet or owner profile changed after preview. Review again.')

    def _device_table(self, serial, namespace):
        rows = {}
        output = self._device_shell(serial, ['settings', '--user', '0', 'list', namespace])
        for line in output.splitlines():
            key, sep, value = line.partition('=')
            if not sep or not key or key in rows:
                _fail(f'Unable to parse the {namespace} settings listing reliably.')
            rows[key] = value
        return rows

    def _storage_path(self, serial, value, kind=None):
        path = _remote(value)
        actual = self._device_shell(serial, ['realpath', path])
        if actual != path:
            _fail('Shared storage path resolved elsewhere or could not be verified.')
        if kind:
            actual_kind = self._device_shell(serial, ['stat', '-c', '%F', path])
            if actual_kind != kind and not (kind == 'regular file' and actual_kind == 'regular empty file'):
                _fail(f'Expected a shared storage {kind}.')
        return path

    def read_device_tool(self, serial, operation, **parameters):
        self._owner_device(serial)
        p = parameters
        commands = {
            'users': ['pm', 'list', 'users'], 'keyboards': ['ime', 'list', '-s', '-a'],
            'tasks': ['ps', '-A'], 'logcat': ['logcat', '-d', '-t', '500'],
            'home': ['cmd', 'package', 'resolve-activity', '--brief', '--user', '0',
                     '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.HOME'],
        }
        if operation in commands:
            _args(p)
            # Logs and process names can contain ordinary words such as Error.
            return self.adb.shell(serial, commands[operation])
        if operation == 'device-stats':
            _args(p)
            return '\n\n'.join(self._device_shell(serial, args) for args in (
                ['dumpsys', 'battery'], ['df', '-h', '/data'], ['cat', '/proc/meminfo']))
        if operation == 'settings-list':
            _args(p, ('namespace',))
            ns = _choice(p['namespace'], NAMESPACES, 'settings namespace')
            return self._device_shell(serial, ['settings', '--user', '0', 'list', ns])
        if operation == 'settings-get':
            _args(p, ('namespace', 'key'))
            _key(p['namespace'], p['key'])
            return self._device_shell(serial, ['settings', '--user', '0', 'get', p['namespace'], p['key']])
        if operation == 'storage-list':
            _args(p, ('remote',))
            remote = self._storage_path(serial, p['remote'], 'directory')
            return self._device_shell(serial, ['ls', '-la', remote])
        if operation == 'permissions':
            _args(p, ('package',))
            return self._device_shell(serial, ['dumpsys', 'package', _pattern(p['package'], PACKAGE, 'package')])
        _fail(f'Unknown device read operation {operation!r}.')

    def _device_undo(self, device, parent=None):
        ident = _identity(device)
        empty = dict(schema='fire-tools.setting-undo.v1', device=ident, values={})
        name = 'device-settings-' + ident['serial_sha256'] + '.json'
        if parent is None:
            try:
                with self._journal_directory() as pinned:
                    return self._device_undo(device, pinned)
            except FileNotFoundError:
                return name, empty
        path = parent / name
        try:
            _, raw = _read_file(path, JSON_LIMIT, content=True)
        except FileNotFoundError:
            return name, empty
        data = _load(raw)
        if (not isinstance(data, dict) or data.get('schema') != 'fire-tools.setting-undo.v1'
                or data.get('device') != ident or not isinstance(data.get('values'), dict)):
            _fail('Undo snapshot is invalid or belongs to a different device.')
        for token, value in data['values'].items():
            ns, _, key = token.partition('/')
            _key(ns, key)
            if value is not None:
                _text(value, 'saved setting', empty=True)
        return name, data

    def _device_save_undo(self, device, updates):
        with self._journal_directory(create=True) as parent:
            name, undo = self._device_undo(device, parent)
            for field, value, forget in updates:
                if forget:
                    undo['values'].pop(field, None)
                else:
                    undo['values'].setdefault(field, value)
            with _private_stage(parent) as temp:
                stage = temp / 'snapshot'
                _write_json(stage, undo)
                stage.chmod(0o600)
                os.replace(stage, parent / name)
            if not self.state_dir.samefile(parent):
                _fail('The undo directory changed before the device mutation. Review again.')

    def _setting_changes(self, device, operation, p):
        value = p.get('value', '')
        if operation in ('setting', 'setting-undo'):
            required = ('namespace', 'key', 'value') if operation == 'setting' else ('namespace', 'key')
            _args(p, required)
            ns, key = p['namespace'], p['key']
            assistant_undo = (operation == 'setting-undo' and ns == 'secure'
                              and key in ('assistant', 'voice_interaction_service'))
            _key(ns, key, writable=not assistant_undo)
            return [(ns, key, None if value == '__DELETE__' else _text(value, 'setting', empty=True))]
        if operation == 'privacy':
            _args(p, ('preset',))
            _choice(p['preset'], ('limit-tracking', 'restore'), 'privacy preset')
            return [('secure', k, v) for k, v in PRIVACY.items()]
        if operation == 'navigation':
            _args(p, ('value',))
            _choice(value, ('immersive.full=*', 'immersive.navigation=*', 'immersive.status=*', 'null'), 'navigation')
            return [('global', 'policy_control', None if value == 'null' else value)]
        if operation == 'timeout':
            _args(p, ('value',))
            return [('system', 'screen_off_timeout', _integer(value, 15000, 1800000, 'timeout'))]
        if operation == 'animation':
            _args(p, ('value',))
            _choice(value, ('0', '0.5', '1', '1.5', '2'), 'animation scale')
            return [('global', key, value) for key in ANIMATIONS]
        if operation == 'rotation':
            _args(p, ('value',))
            _choice(value, ('auto', '0', '1', '2', '3'), 'rotation')
            if value == 'auto':
                return [('system', 'accelerometer_rotation', '1')]
            return [('system', 'accelerometer_rotation', '0'), ('system', 'user_rotation', value)]
        if operation == 'sound':
            _args(p, ('kind', 'value'))
            key = {'notification': 'notification_sound', 'alarm': 'alarm_alert', 'ringtone': 'ringtone'}.get(p['kind'])
            if not key or not re.fullmatch(r'(?:content|file)://[^\s]+', value):
                _fail('Supply a sound kind and an existing content:// or file:// URI.')
            return [('system', key, _text(value, 'sound URI'))]
        if operation in ('assistant', 'accessibility'):
            _args(p, ('component',) if operation == 'assistant' else ('component', 'enable'))
            component = _pattern(p['component'], COMPONENT, 'service component')
            package = component.partition('/')[0]
            if package not in self.adb.packages(device.serial):
                _fail('The requested service package is not installed for the owner.')
            interface = ('android.service.voice.VoiceInteractionService' if operation == 'assistant'
                         else 'android.accessibilityservice.AccessibilityService')
            found = self._device_shell(device.serial, ['cmd', 'package', 'query-services', '--brief',
                                      '--components', '--user', '0', '-a', interface, '-p', package])
            def expanded(name):
                return name.replace('/.', '/' + package + '.', 1)
            if expanded(component) not in {expanded(line.strip()) for line in found.splitlines()}:
                _fail('The specified component was not confirmed as an installed service of the required type.')
            if operation == 'assistant':
                return [('secure', key, component) for key in ('assistant', 'voice_interaction_service')]
            enabled = _choice(p['enable'], ('true', 'false'), 'enable')
            # Granting accessibility access requires consent in tablet Settings.
            if enabled == 'true':
                return []
            current = self._device_table(device.serial, 'secure').get('enabled_accessibility_services', '')
            keep = [entry for entry in current.split(':') if entry and expanded(entry) != expanded(component)]
            return [('secure', 'enabled_accessibility_services', ':'.join(keep))]
        return None

    def _snapshot_settings(self, device, warnings):
        from .service import ToolkitError
        rows, omitted = [], []
        for ns in NAMESPACES:
            table = self._device_table(device.serial, ns)
            for key in sorted(PORTABLE[ns]):
                # Absent keys are included so a restore can reproduce absence.
                value = table.get(key)
                try:
                    _portable_value(ns, key, value)
                except ToolkitError:
                    omitted.append(ns + '/' + key)
                    continue
                rows.append([ns, key, value])
        if omitted:
            warnings.append('Unsupported firmware values omitted from this snapshot: ' + ', '.join(omitted))
        return {'schema': 'fire-tools.settings.v1', 'device': _identity(device), 'settings': rows}

    def _snapshot_packages(self, device):
        packages = self.adb.packages(device.serial)
        disabled = set(self.adb.packages(device.serial, True))
        if len(packages) > 8192 or not disabled <= set(packages):
            _fail('Package inventory changed or exceeded the snapshot limit.')
        return {'schema': 'fire-tools.packages.v1', 'device': _identity(device),
                'packages': {name: ('disabled' if name in disabled else 'enabled') for name in packages}}

    def _import_snapshot(self, path, device, kind):
        digest, raw = _read_local(path, JSON_LIMIT, content=True)
        data = _load(raw)
        if (not isinstance(data, dict) or data.get('schema') != 'fire-tools.' + kind + '.v1'
                or data.get('device') != _identity(device) or set(data) != {'schema', 'device', kind}):
            _fail('Snapshot schema or device identity does not match.')
        if kind == 'settings':
            rows = data[kind]
            if not isinstance(rows, list) or len(rows) > sum(map(len, PORTABLE.values())):
                _fail('Unexpected settings snapshot size.')
            seen = set()
            for row in rows:
                if not isinstance(row, list) or len(row) != 3:
                    _fail('Invalid settings snapshot row.')
                ns, key, value = row
                if (not isinstance(ns, str) or ns not in PORTABLE or not isinstance(key, str)
                        or key not in PORTABLE[ns] or (ns, key) in seen):
                    _fail('Invalid or duplicate settings snapshot key.')
                _portable_value(ns, key, value)
                seen.add((ns, key))
        else:
            if not isinstance(data[kind], dict) or len(data[kind]) > 8192:
                _fail('Invalid package inventory.')
            for package, state in data[kind].items():
                _pattern(package, r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*', 'package')
                _choice(state, ('enabled', 'disabled'), 'package state')
        return digest, data[kind]

    def _apk_paths(self, serial, package):
        _pattern(package, PACKAGE, 'package')
        output = self._device_shell(serial, ['pm', 'path', '--user', '0', package])
        files = []
        for line in output.splitlines():
            prefix, sep, name = line.partition(':')
            if (prefix != 'package' or not sep or not name.startswith('/')
                    or not name.endswith('.apk') or '..' in PurePosixPath(name).parts
                    or not re.fullmatch(r'/[A-Za-z0-9_./+@~=-]+', name) or name in files):
                _fail('Package manager returned an invalid APK path.')
            files.append(name)
        if not 1 <= len(files) <= 128:
            _fail('No usable installed APK set was found.')
        return files

    def _helper_identity(self, device, expected):
        _pattern(expected, r'[A-Fa-f0-9]{64}', 'source-built helper SHA-256 signer fingerprint')
        verifier = self._verifier()
        paths = self._apk_paths(device.serial, HELPER)
        if len(paths) != 1:
            _fail('Expected the single source-built Fire Tools helper APK.')
        with tempfile.TemporaryDirectory(prefix='fire-tools-helper-') as temp:
            apk = Path(temp) / 'helper.apk'
            self._pull_device_file(device, paths[0], apk)
            info = verifier.inspect(apk)
            if (info.package != HELPER or info.split or len(info.signer_sha256) != 1
                    or info.signer_sha256[0].lower() != expected.lower()):
                _fail('Installed helper does not match the expected package and source-build signer.')
            return info.sha256

    def _storage_inventory(self, serial, root):
        deadline = monotonic() + 600
        root = self._storage_path(serial, root, 'directory')
        output = self._device_shell(serial, ['find', root, '-print0'], timeout=60)
        if not output.endswith('\0'):
            _fail('Directory enumeration was incomplete.')
        nodes = output[:-1].split('\0')
        if root not in nodes or len(nodes) > 4096 or len(set(nodes)) != len(nodes):
            _fail('Expected at most 4,096 unique shared storage entries.')
        entries = []
        total = 0
        for name in sorted(nodes):
            _remaining(deadline)
            if name == root:
                continue
            if not name.startswith(root + '/') or _remote(name) != name:
                _fail('Unrecognized path returned by the device.')
            relative = PurePosixPath(name[len(root)+1:])
            for part in relative.parts:
                _host_name(part)
            kind = self._device_shell(serial, ['stat', '-c', '%F', name])
            if kind == 'directory':
                entries.append([str(relative), None])
            elif kind in ('regular file', 'regular empty file'):
                size = self._remote_file_size(serial, name)
                total += size
                if total > 4 * 1024**3:
                    _fail('Select a smaller directory. Shared storage backups support at most 4 GiB.')
                entries.append([str(relative), size])
            else:
                _fail('Shared storage backup accepts only ordinary files and directories.')
        return entries

    def _remote_file_size(self, serial, path):
        value = self._device_shell(serial, ['stat', '-c', '%s', path])
        return int(_integer(value, 0, FILE_LIMIT, 'remote file size'))

    def _pull_device_file(self, device, source, dest, expected_size=None, deadline=None):
        if self._writable_device(device.serial) != device:
            _fail('Device identity changed before transfer.')
        size = self._remote_file_size(device.serial, source)
        if expected_size is not None and size != expected_size:
            _fail('Remote file size changed since preview.')
        # /dev/fd belongs to the current process on macOS. ADB closes
        # inherited descriptors, so pull to private storage and copy into
        # the pinned destination there. Linux uses /proc/<parent pid>/fd.
        external_stage = dest.is_relative_to('/dev/fd')
        temp = tempfile.TemporaryDirectory(prefix='fire-tools-adb-') if external_stage else nullcontext(None)
        with temp as directory:
            target = Path(directory) / 'received' if directory else dest
            self.adb._run_device(device.serial, ['pull', source, str(target)], timeout=_remaining(deadline))
            if self._writable_device(device.serial) != device:
                _fail('Device identity changed during transfer.')
            info = target.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size != size:
                _fail('The destination file type or size could not be verified.')
            if external_stage:
                with dest.open('xb') as output:
                    _read_file(target, size, output)

    def _build_steps(self, device, op, p, steps, warnings, bindings):
        """Resolve operation parameters into reviewed, replayable action descriptions."""
        serial = device.serial
        changes = self._setting_changes(device, op, p)
        if changes is not None:
            if op == 'assistant':
                warnings.append('The voice service may receive assistant requests and personal information.')
            if op == 'accessibility':
                warnings.append('Accessibility services may read screen content and act on your behalf.')
                if not changes:
                    warnings.append('Select and approve the reviewed service on the tablet.')
                    steps.append(['launch', 'android.settings.ACCESSIBILITY_SETTINGS'])
                    return
            if op == 'setting':
                warnings.append('Readback verifies the exact stored value. Its suitability and effect depend on firmware.')
            if op == 'privacy':
                warnings.append('These three settings do not demonstrate a change in server-side telemetry.')
            restoring = op == 'setting-undo' or (op == 'privacy' and p['preset'] == 'restore')
            self._prepare_settings(device, changes, steps, restoring, partial_restore=(op == 'privacy'))
            return

        if op in ('settings-export', 'package-backup', 'backup', 'settings-import',
                  'package-restore', 'restore-backup'):
            _args(p, ('local',))
            importing = op in ('settings-import', 'package-restore', 'restore-backup')
            combined = op in ('backup', 'restore-backup')
            path = _local(p['local'], ('directory' if combined else 'file') if importing else 'new')
            warnings.append('Settings snapshots cover selected UI, sound and privacy keys. Package inventories contain owner enabled/disabled status. Private app data and firmware are excluded.')
            if not importing:
                if combined or op == 'settings-export':
                    steps.append(['export', 'settings', self._snapshot_settings(device, warnings)])
                if combined or op == 'package-backup':
                    steps.append(['export', 'packages', self._snapshot_packages(device)])
                return
            if combined or op == 'settings-import':
                digest, rows = self._import_snapshot(path / 'settings.json' if combined else path, device, 'settings')
                bindings['settings sha256'] = digest
                self._prepare_settings(device, rows, steps, False, only_changed=True)
            if combined or op == 'package-restore':
                from .package_catalog import APP_LABELS, is_protected
                digest, states = self._import_snapshot(path / 'packages.json' if combined else path, device, 'packages')
                bindings['package sha256'] = digest
                _, record = self._pkg_undo_record(device)
                bindings['undo-digest'] = self._pkg_undo_digest(record)
                current = self._snapshot_packages(device)['packages']
                skipped = []
                for name, target in sorted(states.items()):
                    if current.get(name) == target:
                        continue
                    if name not in APP_LABELS or is_protected(name) or name not in current:
                        skipped.append(name)
                    else:
                        if target == 'disabled':
                            self._guard_optional_package(serial, name)
                        steps.append(['package-state', name, current[name], target])
                if skipped:
                    warnings.append('Unavailable or outside the optional-app restore list, skipped: ' + ', '.join(skipped))
            return

        if op in ('push', 'pull', 'storage-backup', 'extract-apk', 'screenshot', 'screenrecord'):
            self._prepare_transfers(device, op, p, steps, warnings)
            return

        if op in ('lockscreen', 'wallpaper', 'parental-settings'):
            if op == 'lockscreen':
                _args(p, ('mode',))
                _choice(p['mode'], ('settings',), 'lockscreen mode')
                action = 'android.settings.SECURITY_SETTINGS'
            elif op == 'parental-settings':
                _args(p)
                action = 'android.settings.SETTINGS'
                warnings.append('Fire OS parental-control visibility has no verified ordinary ADB switch. Locate parental controls and authenticate on the tablet.')
            else:
                _args(p)
                action = 'android.intent.action.SET_WALLPAPER'
                warnings.append('Select a wallpaper and screen on the tablet. Lockscreen support depends on the picker.')
            steps.append(['launch', action])
            return

        if op == 'display':
            _args(p, optional=('density', 'size'))
            overrides = {key: value for key, value in p.items() if value}
            if not overrides:
                _fail('Specify display density, size, or both.')
            for key, value in sorted(overrides.items()):
                if value != 'reset':
                    if key == 'density':
                        value = _integer(value, 120, 640, 'density')
                    else:
                        _pattern(value, r'[0-9]{3,4}x[0-9]{3,4}', 'size WxH')
                        for part in value.split('x'):
                            _integer(part, 320, 3840, 'size dimension')
                original = self._device_shell(serial, ['wm', key])
                _display_state(original, key)
                steps.append(['display', key, value, original])
            warnings.append('An unsuitable size or density may make tablet controls difficult to use. Reset removes the override.')
            return
        if op == 'shell':
            _args(p, ('argv',))
            args = _load(p['argv'])
            if not isinstance(args, list) or not 1 <= len(args) <= 64:
                _fail('Supply a JSON array of 1 to 64 device command tokens.')
            for i, arg in enumerate(args):
                _text(arg, 'shell token', 4096, empty=i > 0)
            warnings.append('Expert device command. Review each token. It may change or erase tablet data without automatic undo.')
            steps.append(['shell', args])
            return
        if op == 'remote-input':
            _args(p, ('kind', 'value'))
            _choice(p['kind'], ('keycode', 'tap'), 'remote input')
            if p['kind'] == 'keycode':
                value = _pattern(p['value'], r'KEYCODE_[A-Z0-9_]{1,48}|[0-9]{1,3}', 'Android keycode')
                args = ['input', 'keyevent', value]
            else:
                coords = p['value'].split(',')
                if len(coords) != 2:
                    _fail('Supply tap coordinates in x,y form.')
                args = ['input', 'tap', *[_integer(n.strip(), 0, 16384, 'tap coordinate') for n in coords]]
            warnings.append('The active tablet screen receives the input.')
            steps.append(['request', args])
            return
        if op in ('helper-start', 'helper-stop', 'helper-restore'):
            _args(p, ('signer',))
            digest = self._helper_identity(device, p['signer'])
            if op != 'helper-stop':
                previous = self._permission_state(serial, HELPER, HELPER_PERMISSION)
                steps.append(['helper-grant', digest, previous])
                if previous is None:
                    warnings.append('The tablet did not expose the prior helper permission state.')
                warnings.append('WRITE_SECURE_SETTINGS grants this installed helper broad settings access. Compare the signer to your own source build.')
            steps.append(['helper-open', digest])
            warnings.append('On the tablet press ' + {'helper-start':'Enable', 'helper-stop':'Stop', 'helper-restore':'Restore'}[op]
                            + '. Opening the activity does not confirm that action.')
            return
        if op in ('grant', 'revoke', 'appops'):
            fields = ('package', 'op', 'value') if op == 'appops' else ('package', 'permission')
            _args(p, fields)
            package = _pattern(p['package'], PACKAGE, 'package')
            if package not in self.adb.packages(serial):
                _fail('Package is not installed for the owner.')
            if op == 'appops':
                name = _pattern(p['op'], r'(?:android:)?[A-Za-z_][A-Za-z0-9_]{0,79}', 'app-op')
                _choice(p['value'], ('allow', 'deny', 'ignore', 'default'), 'app-op mode')
                previous = self._appop_state(serial, package, name)
                steps.append(['appops', package, name, p['value'], previous])
            else:
                permission = _pattern(p['permission'], r'android\.permission\.[A-Z][A-Z_0-9]{1,100}', 'Android permission')
                if (op, package, permission) == ('grant', HELPER, HELPER_PERMISSION):
                    _fail('Use helper-start or helper-restore to verify the installed helper signer before this grant.')
                previous = self._permission_state(serial, package, permission)
                steps.append(['permission', op, package, permission, previous])
            if previous is None:
                warnings.append('The tablet did not expose the owner’s prior state. An intervening change may be undetectable.')
            warnings.append('Permission or app-op changes may expose sensitive data or prevent an app from working.')
            return
        if op == 'reboot':
            _args(p, ('mode',))
            mode = _choice(p['mode'], ('system', 'recovery', 'bootloader'), 'reboot mode')
            warnings.append('Save tablet work. Recovery and bootloader modes may require physical interaction.')
            steps.append(['reboot', mode])
            return
        if op == 'shutdown':
            _args(p)
            warnings.append('Save tablet work. The device may disconnect immediately.')
            steps.append(['request', ['reboot', '-p']])
            return
        if op in ('user-create', 'user-switch', 'user-remove'):
            if op == 'user-create':
                _args(p, ('name',))
                name = _text(p['name'], 'profile name', 64)
                if name.startswith('-') or not name.strip():
                    _fail('Enter a profile name that does not start with a dash.')
                steps.append(['user-create', name])
            else:
                _args(p, ('user_id',))
                user = _integer(p['user_id'], 1, 2147483647, 'non-owner profile ID')
                line = self._profile_line(serial, user)
                if not line:
                    _fail('The requested profile was not found.')
                steps.append([op, user, line])
            warnings.append('Fire OS may remove additional profiles. Switching leaves the owner profile until you switch back on the tablet.')
            if op == 'user-remove':
                warnings.append('Removing this profile permanently deletes its apps, files and settings.')
            return
        _fail(f'Unsupported device operation {op!r}.')

    def _profile_line(self, serial, user):
        lines = self._device_shell(serial, ['pm', 'list', 'users']).splitlines()
        matches = [line.strip() for line in lines if re.search(r'UserInfo\{' + re.escape(user) + ':', line)]
        if len(matches) > 1:
            _fail('Ambiguous user list.')
        return matches[0] if matches else ''

    def _prepare_settings(self, device, changes, steps, restoring, only_changed=False, partial_restore=False):
        _, undo = self._device_undo(device)
        tables = {}
        for ns, key, value in changes:
            if ns not in tables:
                tables[ns] = self._device_table(device.serial, ns)
            old = tables[ns].get(key)
            if old is not None:
                _text(old, 'prior setting', empty=True)
            token = ns + '/' + key
            if restoring:
                if token not in undo['values']:
                    if partial_restore:
                        continue
                    _fail(f'No saved value for {token}.')
                value = undo['values'][token]
            if not only_changed or old != value:
                steps.append(['setting', ns, key, old, value, restoring])
        if restoring and not steps:
            _fail('No saved settings for this restore operation.')

    def _prepare_transfers(self, device, op, p, steps, warnings):
        serial = device.serial
        fields = {'push': ('local', 'remote'), 'pull': ('local', 'remote'),
                  'storage-backup': ('local', 'remote'), 'extract-apk': ('local', 'package'),
                  'screenshot': ('local',), 'screenrecord': ('local', 'seconds')}
        _args(p, fields[op])
        local = _local(p['local'], 'file' if op == 'push' else 'new')
        if op == 'push':
            remote = _remote(p['remote'])
            if remote == SHARED:
                _fail('Specify a new destination filename.')
            self._storage_path(serial, str(PurePosixPath(remote).parent), 'directory')
            self._require_new_remote(serial, remote)
            digest, _ = _read_local(local, FILE_LIMIT)
            steps.append(['push', remote, digest])
        elif op == 'pull':
            remote = self._storage_path(serial, p['remote'], 'regular file')
            steps.append(['pull', remote, self._remote_file_size(serial, remote)])
        elif op == 'storage-backup':
            remote = _remote(p['remote'])
            nodes = self._storage_inventory(serial, remote)
            steps.append(['storage-backup', remote, nodes])
            warnings.append('Only the reviewed shared files and folders are included. App-private data is excluded.')
        elif op == 'extract-apk':
            steps.append(['extract-apk', self._apk_paths(serial, p['package'])])
            warnings.append('The output contains installed base and split APKs. App-private data is excluded.')
        else:
            ext = '.png' if op == 'screenshot' else '.mp4'
            if local.suffix.lower() != ext:
                _fail('Choose a new ' + ext + ' destination.')
            seconds = None if op == 'screenshot' else _integer(p['seconds'], 1, 180, 'recording duration')
            steps.append([op, seconds])
            warnings.append('Screen contents may be private. Capture is saved only to the selected local file.')

    def _require_new_remote(self, serial, remote):
        for flag in ('-e', '-L'):
            self._device_shell(serial, ['test', '!', flag, remote])

    def plan_device_action(self, serial, operation, **parameters):
        device = self._writable_device(serial)
        steps, warnings, bindings = [], [], {}
        self._build_steps(device, operation, parameters, steps, warnings, bindings)
        bindings['steps'] = _json(steps)
        if len(bindings['steps']) > 2 * JSON_LIMIT:
            _fail('Preview exceeds the supported size. Select a smaller operation.')
        details = [_describe_step(step) for step in steps]
        if 'local' in parameters:
            details.insert(0, 'Computer path: ' + parameters['local'])
        for key, value in bindings.items():
            if key != 'steps':
                details.append(key + ': ' + value)
        if not steps:
            details.append('No supported changes are needed.')
        return WorkflowPlan('Device tool: ' + operation, serial, tuple(details), tuple(warnings),
                            'device_workflow', device, operation,
                            tuple(sorted(parameters.items())), snapshot=tuple(sorted(bindings.items())))

    def _execute_device_workflow(self, plan, completed, log):
        # Regenerate plans, including file hashes, previous values and APKs,
        # through the same validation used by the GUI and CLI.
        self._device_guard(plan)
        current = self.plan_device_action(plan.serial, plan.operation, **plan.params)
        if current != plan:
            _fail('Device state or reviewed inputs changed since preview. Review again.')
        steps = _load(dict(current.snapshot)['steps'])
        if plan.operation in ('backup', 'package-backup', 'settings-export'):
            combined = plan.operation == 'backup'
            def published():
                completed.append('Saved the reviewed configuration snapshot.')
            with _destination(plan.params['local'], combined, published) as dest:
                for _, kind, document in steps:
                    self._device_guard(plan)
                    _write_json(dest / (kind + '.json') if combined else dest, document)
            return
        package_changes = []
        for step in steps:
            if step[0] == 'package-state':
                package_changes.append(step[1:])
            else:
                self._device_guard(plan)
                self._apply_device_step(plan, step, completed)
        if 'package sha256' in dict(current.snapshot):
            self._device_guard(plan)
            self._pkg_apply_state(plan, completed, restore_steps=package_changes)
        if not steps:
            completed.append('No supported changes were needed.')

    def _apply_device_step(self, plan, step, completed):
        kind, *values = step
        serial = plan.serial
        if kind == 'setting':
            ns, key, old, target, restoring = values
            if self._device_table(serial, ns).get(key) != old:
                _fail(f'{ns}/{key} changed after preview.')
            self._device_save_undo(plan.device, [(ns+'/'+key, old, False)])
            args = ['delete', ns, key] if target is None else ['put', ns, key, target]
            self._device_guard(plan)
            self._device_shell(serial, ['settings', '--user', '0', *args])
            completed.append(f'Issued {ns}/{key} setting command. Readback pending.')
            self._device_guard(plan)
            if self._device_table(serial, ns).get(key) != target:
                _fail(f'{ns}/{key} readback differs. The undo snapshot was retained.')
            self._device_guard(plan)
            completed[-1] = f'Confirmed {ns}/{key} by settings readback.'
            if restoring:
                self._device_save_undo(plan.device, [(ns+'/'+key, None, True)])
        elif kind in ('push', 'pull', 'screenshot', 'screenrecord', 'extract-apk', 'storage-backup'):
            self._transfer_step(plan, kind, values, completed)
        elif kind == 'display':
            key, value, old = values
            if self._device_shell(serial, ['wm', key]) != old:
                _fail('Display override changed after preview.')
            self._device_guard(plan)
            self._device_shell(serial, ['wm', key, value])
            completed.append(f'Display {key} request accepted. Readback pending.')
            self._device_guard(plan)
            actual = _display_state(self._device_shell(serial, ['wm', key]), key)
            if actual != (None if value == 'reset' else value):
                _fail('Display override was requested but readback did not confirm it.')
            completed[-1] = f'Confirmed display {key} {value}.'
        elif kind in ('request', 'shell'):
            args, = values
            result = self._device_shell(serial, args)
            completed.append((result if result else 'Command accepted.') if kind == 'shell' else 'Tablet accepted the command.')
        elif kind == 'launch' or kind == 'helper-open':
            if kind == 'helper-open':
                if self._helper_identity(plan.device, plan.params['signer']) != values[0]:
                    _fail('Installed helper changed since preview. Refusing to open it.')
                self._device_guard(plan)
                args = ['-n', HELPER + '/.MainActivity']
            else:
                args = ['-a', values[0]]
            self._device_shell(serial, ['am', 'start', '--user', '0', *args])
            completed.append('Activity launch requested. Complete the selection on the tablet.')
        elif kind == 'helper-grant':
            digest, previous = values
            self._permission_step(plan, 'grant', HELPER, HELPER_PERMISSION, previous, completed, helper_digest=digest)
        elif kind == 'permission':
            self._permission_step(plan, *values, completed)
        elif kind == 'appops':
            package, name, value, previous = values
            if package not in self.adb.packages(serial) or self._appop_state(serial, package, name) != previous:
                _fail('Package or owner app-op state changed since preview.')
            self._device_guard(plan)
            self._device_shell(serial, ['cmd', 'appops', 'set', '--user', '0', package, name, value])
            completed.append(f'App-op {name} request accepted for {package}. Readback pending.')
            self._device_guard(plan)
            actual = self._appop_state(serial, package, name)
            if actual is None:
                completed[-1] = f'App-op {name} request accepted. The tablet did not expose the resulting mode.'
            elif any(mode != value for mode in actual.values()):
                _fail(f'App-op readback did not confirm {value} for {name}. Reported {_appop_modes(actual)}.')
            else:
                completed[-1] = f'App-op {name} for {package}: confirmed {_appop_modes(actual)}.'
        elif kind == 'reboot':
            mode = values[0]
            self.adb._run_device(serial, ['reboot'] if mode == 'system' else ['reboot', mode])
            completed.append(f'{mode} reboot request accepted. Device restart has not been observed.')
        elif kind == 'user-create':
            result = self._device_shell(serial, ['pm', 'create-user', values[0]])
            completed.append('Profile creation request accepted. Readback pending.')
            self._device_guard(plan)
            match = re.search(r'Success: created user id (\d+)\b', result, re.I)
            if not match or not self._profile_line(serial, match[1]):
                _fail('Profile creation was requested but the new profile could not be confirmed. Inspect the profile list before retrying.')
            completed[-1] = 'Confirmed profile ID ' + match[1] + ' exists.'
        elif kind in ('user-switch', 'user-remove'):
            user, original = values
            if self._profile_line(serial, user) != original:
                _fail('Profile changed since preview.')
            self._device_guard(plan)
            if kind == 'user-switch':
                self._device_shell(serial, ['am', 'switch-user', user])
                completed.append('Profile switch to ' + user + ' requested. Readback pending.')
                observed = self._device_shell(serial, ['am', 'get-current-user'])
                if observed == user:
                    completed[-1] = 'Confirmed switch to profile ' + user
            else:
                self._device_shell(serial, ['pm', 'remove-user', user])
                completed.append('Profile ' + user + ' removal request accepted. Readback pending.')
                self._device_guard(plan)
                if self._profile_line(serial, user):
                    _fail('Profile removal was requested but the profile is still listed.')
                completed[-1] = 'Confirmed profile ' + user + ' was removed.'
        else:
            _fail('Unrecognized device workflow step.')

    def _guard_optional_package(self, serial, name):
        from .package_catalog import APP_LABELS, is_protected
        if name not in APP_LABELS or is_protected(name):
            _fail('Unsupported package restore.')
        home = self.read_device_tool(serial, 'home')
        ime = self.read_device_tool(serial, 'settings-get', namespace='secure', key='default_input_method')
        homes = [line.strip() for line in home.splitlines() if re.fullmatch(COMPONENT, line.strip())]
        if len(homes) != 1 or (ime not in ('', 'null') and not re.fullmatch(COMPONENT, ime)):
            _fail('Unable to verify the active home and keyboard before disabling a package.')
        if homes[0].startswith(name + '/') or ime.startswith(name + '/'):
            _fail('An active launcher or input method cannot be disabled.')

    def _permission_state(self, serial, package, permission):
        data = self._device_shell(serial, ['dumpsys', 'package', package])
        # Runtime grants belong to a user. Other profiles' grants must never
        # satisfy owner readback. Installation permissions are package-wide.
        sections = re.split(r'(?m)^\s*User (\d+):', data)
        relevant = sections[0]
        for user, block in zip(sections[1::2], sections[2::2]):
            if user == '0':
                relevant += '\n' + block
        flags = set(re.findall(r'^\s*' + re.escape(permission) +
                               r':\s*granted=(true|false)\b', relevant, re.M))
        if len(flags) > 1:
            _fail('The tablet returned conflicting owner permission states.')
        return next(iter(flags), None)

    def _appop_state(self, serial, package, name):
        result = self._device_shell(serial, ['cmd', 'appops', 'get', '--user', '0', package, name])
        pattern = (r'^\s*(?:(Uid mode):\s*)?' + re.escape(name.removeprefix('android:'))
                   + r':\s*([a-z_]+)\b')
        modes = {}
        for uid_prefix, mode in re.findall(pattern, result, re.M | re.I):
            scope = 'UID' if uid_prefix else 'package'
            value = mode.lower()
            if scope in modes and modes[scope] != value:
                _fail(f'The tablet returned conflicting {scope} modes for {name}.')
            modes[scope] = value
        return modes or None

    def _permission_step(self, plan, verb, package, permission, previous, completed, *, helper_digest=None):
        serial = plan.serial
        verified_helper = (verb, package, permission) == ('grant', HELPER, HELPER_PERMISSION)
        if verified_helper:
            if plan.operation not in ('helper-start', 'helper-restore') or not helper_digest:
                _fail('Use helper-start or helper-restore to verify the installed helper signer.')
            if self._helper_identity(plan.device, plan.params['signer']) != helper_digest:
                _fail('Installed helper changed since preview.')
        if self._permission_state(serial, package, permission) != previous:
            _fail('Owner permission state changed since preview.')
        self._device_guard(plan)
        self._device_shell(serial, ['pm', verb, '--user', '0', package, permission])
        completed.append(f'Permission {verb} request accepted for {permission} on {package}. Readback pending.')
        self._device_guard(plan)
        actual = self._permission_state(serial, package, permission)
        if actual == ('true' if verb == 'grant' else 'false'):
            completed[-1] = f'Confirmed {verb} of {permission} for {package}.'
        elif actual is not None or verified_helper:
            _fail('Permission readback did not confirm the requested state.')
        else:
            completed[-1] = f'Permission {verb} of {permission} accepted. The tablet did not expose the resulting state.'

    @contextmanager
    def _device_temp(self, plan, parent):
        self._storage_path(plan.serial, parent, 'directory')
        folder = parent + '/.fire-tools-' + uuid.uuid4().hex
        self._device_guard(plan)
        self._device_shell(plan.serial, ['mkdir', folder])
        remote = folder + '/payload'
        try:
            yield remote
        finally:
            self._device_guard(plan)
            self._device_shell(plan.serial, ['rm', '-f', remote])
            self._device_guard(plan)
            self._device_shell(plan.serial, ['rmdir', folder])

    def _transfer_step(self, plan, kind, values, completed):
        serial, local = plan.serial, plan.params['local']
        if kind == 'push':
            target, digest = values
            with tempfile.TemporaryDirectory(prefix='fire-tools-push-') as temp:
                source = Path(temp) / 'input'
                with source.open('xb') as output:
                    observed, _ = _read_local(local, FILE_LIMIT, output)
                if observed != digest:
                    _fail('The local file changed while staging.')
                parent = str(PurePosixPath(target).parent)
                with self._device_temp(plan, parent) as remote:
                    self._device_guard(plan)
                    self.adb._run_device(serial, ['push', str(source), remote], timeout=600)
                    size = source.stat().st_size
                    source.unlink()
                    self._storage_path(serial, remote, 'regular file')
                    readback = Path(temp) / 'readback'
                    self._pull_device_file(plan.device, remote, readback, expected_size=size)
                    readback_digest, _ = _read_file(readback, size)
                    if readback_digest != digest:
                        _fail('The staged upload SHA-256 differs from the reviewed file.')
                    self._device_guard(plan)
                    self._require_new_remote(serial, target)
                    self._device_guard(plan)
                    self._device_shell(serial, ['mv', '-nT', remote, target])
                    completed.append('Upload publication request accepted for ' + target + '. Verification pending.')
                    self._device_guard(plan)
                    self._require_new_remote(serial, remote)
                    self._storage_path(serial, target, 'regular file')
                    completed[-1] = 'Published the reviewed file to ' + target + '.'
            return
        directory = kind in ('storage-backup', 'extract-apk')
        def published():
            completed.append('Published ' + kind + ' to ' + local + '.')
        with _destination(local, directory, published) as dest:
            if kind == 'pull':
                path, size = values
                self._storage_path(serial, path, 'regular file')
                self._pull_device_file(plan.device, path, dest, size)
            elif kind == 'extract-apk':
                paths, = values
                for index, path in enumerate(paths):
                    name = PurePosixPath(path).name
                    _host_name(name)
                    self._pull_device_file(plan.device, path, dest / f'{index:03d}-{name}')
                if self._apk_paths(serial, plan.params['package']) != paths:
                    _fail('The installed APK paths changed during extraction.')
            elif kind == 'storage-backup':
                root, entries = values
                deadline = monotonic() + 600
                for relative, size in entries:
                    _remaining(deadline)
                    self._device_guard(plan)
                    remote = root + '/' + relative
                    target = dest / Path(*PurePosixPath(relative).parts)
                    self._storage_path(serial, remote, 'directory' if size is None else 'regular file')
                    if size is None:
                        target.mkdir()
                    else:
                        if os.path.lexists(target):
                            _fail('Remote names collide on this host filesystem.')
                        self._pull_device_file(plan.device, remote, target, size, deadline=deadline)
            else:
                with self._device_temp(plan, SHARED + '/Download') as remote:
                    self._device_guard(plan)
                    if kind == 'screenshot':
                        self._device_shell(serial, ['screencap', '-p', remote], timeout=60)
                    else:
                        self._device_shell(serial, ['screenrecord', '--time-limit', values[0], remote],
                                           timeout=int(values[0]) + 30)
                    self._pull_device_file(plan.device, remote, dest)
                    with dest.open('rb') as result:
                        header = result.read(12)
                    if kind == 'screenshot' and not header.startswith(b'\x89PNG\r\n\x1a\n'):
                        _fail('Capture did not produce a recognizable PNG.')
                    if kind == 'screenrecord' and header[4:8] != b'ftyp':
                        _fail('Recording did not produce a recognizable MP4.')
            self._device_guard(plan)


def _remaining(deadline):
    if deadline is None:
        return 600
    seconds = deadline - monotonic()
    if seconds <= 0:
        _fail('Shared storage backup exceeded its 10-minute time limit. Select a smaller directory.')
    return seconds


def _display_state(raw, key):
    pattern = r'[0-9]+' if key == 'density' else r'[0-9]+x[0-9]+'
    if not re.search(r'^Physical ' + key + ': ' + pattern + '$', raw, re.M | re.I):
        _fail('Unrecognized window manager display state.')
    match = re.search(r'^Override ' + key + ': (' + pattern + ')$', raw, re.M | re.I)
    return match[1] if match else None


def _host_name(name):
    if (not name or name in ('.', '..') or any(ch in name for ch in '<>:"|?*\\/')
            or name.rstrip(' .') != name or not name.isprintable()
            or re.fullmatch(r'(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', name, re.I)):
        _fail('A tablet filename cannot safely be created on the host.')


def _appop_modes(state):
    if not state:
        return 'unavailable'
    return ', '.join(f'{scope} {state[scope]}' for scope in ('UID', 'package') if scope in state)


def _describe_step(step):
    kind, *v = step
    if kind == 'setting':
        ns, key, old, target, _ = v
        return f'{ns}/{key}: {_json(old)} → {_json(target)}'
    if kind == 'export':
        return f'Export {len(v[1][v[0]])} {v[0]} entries.'
    if kind == 'storage-backup':
        size = sum(n or 0 for _, n in v[1])
        return f'Copy {len(v[1])} entries from {v[0]} ({size} bytes).'
    if kind == 'extract-apk':
        return 'Pull installed APKs: ' + ', '.join(v[0])
    if kind in ('shell', 'request'):
        return _command(v[0])
    if kind == 'launch':
        return 'Open on the tablet: ' + v[0]
    if kind == 'helper-open':
        return f'Open {HELPER}/.MainActivity after rechecking APK SHA-256 {v[0]}.'
    if kind == 'helper-grant':
        return f'Grant WRITE_SECURE_SETTINGS to the verified helper APK with SHA-256 {v[0]}. Prior grant: {v[1] or "unavailable"}.'
    if kind == 'permission':
        verb, package, permission, previous = v
        return f'{verb} {permission} for {package}. Prior owner grant: {previous or "unavailable"}.'
    if kind == 'appops':
        package, name, target, previous = v
        return f'Set {name} for {package} to {target}. Prior owner modes: {_appop_modes(previous)}.'

    if kind == 'display':
        return _command(['wm', v[0], v[1]]) + ' (current: ' + v[2] + ')'
    return kind + ' ' + ' '.join(str(item) for item in v if item is not None)
