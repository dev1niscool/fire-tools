"""One public feature catalog for desktop forms, CLI discovery and documentation."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    default: str = ''
    choices: tuple[str, ...] = ()
    kind: str = 'text'


@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    category: str
    backend: str
    operation: str
    fields: tuple[Field, ...] = ()
    description: str = ''
    read_only: bool = False
    requires_device: bool = True


PACKAGES = Field('packages', 'Package IDs (one per line or separated by commas)', kind='multiline')
PACKAGE = Field('package', 'Package ID')
COMPONENT = Field('component', 'Installed component (package/.Activity or .Service)')
NAMESPACE = Field('namespace', 'Settings database', 'system', ('system', 'secure', 'global'))
KEY = Field('key', 'Setting key')
LOCAL_NEW = Field('local', 'New destination on this computer', kind='save')
LOCAL_FILE = Field('local', 'Existing file on this computer', kind='file')
LOCAL_DIR = Field('local', 'New destination directory (must not already exist)')
REMOTE = Field('remote', 'Tablet shared-storage path', '/sdcard/Download')
SIGNER = Field('signer', 'Expected source-build signer SHA-256 fingerprint')


def _package(key, label, operation, fields=(), description='', category='Applications', read_only=False):
    return Feature(key, label, category, 'package', operation, fields, description, read_only)


def _device(key, label, operation, fields=(), description='', category='Device tools', read_only=False):
    return Feature(key, label, category, 'device', operation, fields, description, read_only)


def _extra(key, label, operation, fields=(), description='', category='Additional tools', read_only=False, requires_device=True):
    return Feature(key, label, category, 'extra', operation, fields, description, read_only, requires_device)


FEATURES = (
    _package('packages-inventory', 'Browse installed and system apps', 'inventory', (Field('mode', 'Filter', 'all', ('all', 'system', 'third-party', 'disabled', 'uninstalled')),), read_only=True),
    _package('debloat', 'Debloat Amazon apps', 'debloat', (Field('profile', 'Debloat list', 'standard', ('standard', 'complete', 'custom')), Field('list_file', 'Custom list file (custom mode only)', kind='file'), Field('mode', 'Action', 'disable', ('disable', 'uninstall'))), 'Review the exact installed apps first. Removing for the owner keeps data and leaves system images intact.', 'Amazon apps'),
    _package('packages-disable', 'Disable selected apps', 'disable', (PACKAGES,), 'Keeps installed app data.'),
    _package('packages-enable', 'Enable selected apps', 'enable', (PACKAGES,)),
    _package('packages-uninstall', 'Remove selected apps for owner', 'uninstall', (PACKAGES,), 'Uses owner-only removal with kept data. Restoring third-party apps may require the original APK.'),
    _package('packages-restore', 'Restore apps removed for owner', 'restore', (PACKAGES,), 'Reinstalls an existing system/package image for user 0; cannot recover an APK that no longer exists.'),
    _package('packages-undo', 'Undo saved package changes', 'undo', description='Review the saved prior states; firmware may prevent a restore.', category='Amazon apps'),
    _package('packages-clear-data', 'Clear app data', 'clear-data', (PACKAGES,), 'Deletes local account state and app data. This cannot be undone.'),
    _package('packages-stop', 'Force-stop apps', 'force-stop', (PACKAGES,)),
    _package('packages-launch', 'Launch apps', 'launch', (PACKAGES,)),
    _package('sideload', 'Verify and install local APKs', 'sideload', (Field('paths', 'Standalone APK files', kind='files'), Field('signer', 'Expected signer SHA-256 (optional)')), 'Checks signatures, SDK and ABI. Review the actual signer fingerprints; a signature does not prove safe behavior.'),
    _package('system-update', 'Install a system app update', 'system-update', (PACKAGES, Field('paths', 'Standalone APK files', kind='files'), Field('signer', 'Expected signer SHA-256 (optional)')), 'Choose exactly one installed system package. Android enforces signing continuity, but an unsuitable update can break that service.'),
    _package('system-rollback', 'Revert system app updates', 'rollback-system', (PACKAGES,), 'May discard app data or newer app functionality; firmware must support this command.'),
    _package('ads-package-disable', 'Disable Special Offers app', 'ads-disable', description='Experimental: firmware may protect the app. Package state does not establish ad visibility.', category='Lock-screen ads'),
    _package('ads-package-restore', 'Enable Special Offers app', 'ads-restore', category='Lock-screen ads'),
    _device('helper-start', 'Set up the on-tablet ad helper', 'helper-start', (SIGNER,), 'Verify the installed source-built helper, grant its setting permission, then press Enable on the tablet. Firmware may ignore the setting.', 'Lock-screen ads'),
    _device('helper-stop', 'Open helper to stop monitoring', 'helper-stop', description='Opens the helper; press Stop on the tablet. Opening it alone does not stop the service.', category='Lock-screen ads'),
    _device('helper-restore', 'Open helper to restore ad setting', 'helper-restore', (SIGNER,), 'Verify helper identity, then press Restore on the tablet. Uses the original saved value.', 'Lock-screen ads'),
    _package('ota-disable', 'Disable update packages', 'ota-disable', (PACKAGES,), 'Select the installed updater package IDs explicitly. Blocks security updates if accepted. Some Fire OS versions protect these packages; this is not a guarantee that every update route is blocked.', 'System updates'),
    _package('ota-enable', 'Enable update packages', 'ota-enable', (PACKAGES,), category='System updates'),
    _package('launcher-set', 'Set an installed home launcher', 'launcher-set', (COMPONENT, Field('disable_stock', 'Disable Fire launcher after verifying replacement', 'false', ('false', 'true'))), 'Fire OS may refuse default-home changes. Keep a working launcher.', 'Launcher and input'),
    _package('launcher-restore', 'Restore Fire home launcher', 'launcher-restore', category='Launcher and input'),
    _device('home', 'Read current home activity', 'home', category='Launcher and input', read_only=True),
    _device('keyboards', 'List installed input methods', 'keyboards', category='Launcher and input', read_only=True),
    _package('keyboard-set', 'Select an installed keyboard', 'keyboard-set', (COMPONENT,), category='Launcher and input'),
    _device('remote-input', 'Send a key or tap', 'remote-input', (Field('kind', 'Input type', 'keycode', ('keycode', 'tap')), Field('value', 'Key code or x,y coordinates')), category='Launcher and input'),
    _device('settings-list', 'Read settings database', 'settings-list', (NAMESPACE,), category='Settings', read_only=True),
    _device('settings-get', 'Read one setting', 'settings-get', (NAMESPACE, KEY), category='Settings', read_only=True),
    _device('settings-set', 'Change or delete a setting', 'setting', (NAMESPACE, KEY, Field('value', 'New value (__DELETE__ removes the key)')), 'Advanced: an accepted value may still be ignored by Fire OS. Preserve the undo file.', 'Settings'),
    _device('settings-undo', 'Restore a saved setting', 'setting-undo', (NAMESPACE, KEY), category='Settings'),
    _device('settings-export', 'Export settings snapshot', 'settings-export', (LOCAL_NEW,), 'Snapshot may contain personal configuration. Store it privately.', 'Backup and restore'),
    _device('settings-import', 'Restore supported settings from snapshot', 'settings-import', (LOCAL_FILE,), 'Only validated supported keys are restored. This does not replace the entire settings database.', 'Backup and restore'),
    _device('privacy', 'Limit usage and advertising settings', 'privacy', (Field('preset', 'Action', 'limit-tracking', ('limit-tracking', 'restore')),), 'Changes known settings; does not audit or stop all Amazon/Google network traffic.', 'Settings'),
    _device('navigation', 'Navigation and status-bar visibility', 'navigation', (Field('value', 'Immersive policy', 'null', ('null', 'immersive.full=*', 'immersive.navigation=*', 'immersive.status=*')),), 'Availability depends on firmware.', 'Display and sounds'),
    _device('display', 'Screen size and density', 'display', (Field('density', 'Density (120–640, reset, or blank)', ''), Field('size', 'Resolution WxH (or reset, or blank)', '')), 'An unsuitable display size can make controls difficult to reach. Reset restores the device default.', 'Display and sounds'),
    _device('timeout', 'Screen timeout', 'timeout', (Field('value', 'Timeout in milliseconds (15000–1800000)', '60000'),), category='Display and sounds'),
    _device('animation', 'Animation speed', 'animation', (Field('value', 'Animation scale', '1', ('0', '0.5', '1', '1.5', '2')),), category='Display and sounds'),
    _device('rotation', 'Screen rotation', 'rotation', (Field('value', 'Rotation (auto or quarter turns)', 'auto', ('auto', '0', '1', '2', '3')),), category='Display and sounds'),
    _device('sound', 'Notification, alarm or ringtone sound', 'sound', (Field('kind', 'Sound', 'notification', ('notification', 'alarm', 'ringtone')), Field('value', 'Tablet content:// or file:// audio URI')), category='Display and sounds'),
    _device('wallpaper', 'Open tablet wallpaper chooser', 'wallpaper', description='Finish selection on the tablet. This does not bypass Amazon lock-screen wallpaper restrictions.', category='Display and sounds'),
    _device('lockscreen', 'Open tablet security settings', 'lockscreen', (Field('mode', 'Action', 'settings', ('settings',)),), 'Change lock credentials on the tablet. No credential bypass.', 'Settings'),
    _device('parental-settings', 'Open Settings for parental controls', 'parental-settings', (), 'Find parental controls and authenticate on the tablet. Fire OS determines which options are available.', 'Settings'),
    _device('assistant', 'Configure installed voice assistant', 'assistant', (COMPONENT,), 'Requires a compatible installed voice interaction service. Online assistant support is separate.', 'Google and assistants'),
    _device('accessibility', 'Configure an accessibility service', 'accessibility', (COMPONENT, Field('enable', 'Enable', 'true', ('true', 'false'))), 'Enabling opens the tablet settings for your consent. Accessibility can read screen content and act on your behalf. Disabling retains other service bindings.', 'Settings'),
    _device('users', 'List tablet profiles', 'users', category='Profiles', read_only=True),
    _device('user-create', 'Create a tablet profile', 'user-create', (Field('name', 'Profile name'),), 'Amazon parental controls may remove unsupported profiles on reboot.', 'Profiles'),
    _device('user-switch', 'Switch tablet profile', 'user-switch', (Field('user_id', 'Existing profile ID'),), 'Device-changing tools require returning to the owner profile.', 'Profiles'),
    _device('user-remove', 'Delete a tablet profile', 'user-remove', (Field('user_id', 'Profile ID to delete'),), 'Deletes that profile and its app data permanently. Owner/current profile deletion is refused.', 'Profiles'),
    _device('storage-list', 'Browse shared storage', 'storage-list', (REMOTE,), category='Files', read_only=True),
    _device('push', 'Copy a file to the tablet', 'push', (LOCAL_FILE, Field('remote', 'New tablet file path', '/sdcard/Download/')), category='Files'),
    _device('pull', 'Copy a file from the tablet', 'pull', (Field('remote', 'Tablet file path', '/sdcard/Download/'), LOCAL_NEW), category='Files'),
    _device('storage-backup', 'Copy shared-storage folder', 'storage-backup', (REMOTE, LOCAL_DIR), 'Copies only shared files, not app-private data or firmware. May take several minutes.', 'Backup and restore'),
    _device('extract-apk', 'Extract installed APK and splits', 'extract-apk', (PACKAGE, LOCAL_DIR), 'Exports package files, not app data. Keep all split files together.', 'Backup and restore'),
    _device('package-backup', 'Export package-state snapshot', 'package-backup', (LOCAL_NEW,), category='Backup and restore'),
    _device('package-restore', 'Restore supported package states', 'package-restore', (LOCAL_FILE,), 'Restore is limited to supported package changes; missing APKs and private data cannot be recovered.', 'Backup and restore'),
    _device('backup', 'Back up settings and package inventory', 'backup', (LOCAL_DIR,), 'A configuration backup, not a full tablet image. Export APKs and shared storage separately.', 'Backup and restore'),
    _device('restore-backup', 'Restore supported configuration backup', 'restore-backup', (Field('local', 'Backup folder', kind='directory'),), category='Backup and restore'),
    _device('screenshot', 'Save a screenshot', 'screenshot', (LOCAL_NEW,), 'Unlock the tablet first. Protected content may be blank.', 'Screen and diagnostics'),
    _device('screenrecord', 'Record the screen', 'screenrecord', (LOCAL_NEW, Field('seconds', 'Duration in seconds (1–180)', '15')), 'Audio is not recorded. Protected content may be blank.', 'Screen and diagnostics'),
    _device('tasks', 'List running processes', 'tasks', category='Screen and diagnostics', read_only=True),
    _device('logcat', 'Read recent device logs', 'logcat', description='Logs can include personal information. No logs are uploaded.', category='Screen and diagnostics', read_only=True),
    _device('device-stats', 'Battery, memory and storage diagnostics', 'device-stats', category='Screen and diagnostics', read_only=True),
    _device('permissions', 'Read package details and permissions', 'permissions', (PACKAGE,), category='Advanced', read_only=True),
    _device('grant', 'Grant an app permission', 'grant', (PACKAGE, Field('permission', 'Android permission name')), 'Permissions may expose sensitive device data. Signature permissions can be refused.', 'Advanced'),
    _device('revoke', 'Revoke an app permission', 'revoke', (PACKAGE, Field('permission', 'Android permission name')), category='Advanced'),
    _device('appops', 'Set an app operation', 'appops', (PACKAGE, Field('op', 'Operation name'), Field('value', 'Mode', 'default', ('allow', 'deny', 'ignore', 'default'))), category='Advanced'),
    _device('shell', 'Run a device shell command', 'shell', (Field('argv', 'JSON argument array (no host shell)', '["getprop", "ro.product.model"]', kind='multiline'),), 'Expert tool: this can modify or erase tablet data. Commands run with ordinary ADB shell permissions and have no automatic undo.', 'Advanced'),
    _device('power', 'Restart into system, recovery or bootloader', 'reboot', (Field('mode', 'Restart mode', 'system', ('system', 'recovery', 'bootloader')),), 'Recovery and bootloader modes may need physical buttons to exit. No flashing or unlocking is performed.', 'Power'),
    _device('shutdown', 'Power off the tablet', 'shutdown', description='Save your work first. You will need to power it back on manually.', category='Power'),
    _extra('settings-open', 'Open a tablet settings page', 'settings-open', (Field('target', 'Settings page', 'accounts', ('accounts', 'google-account-add', 'security', 'applications', 'accessibility', 'wifi', 'vpn', 'location', 'unknown-sources', 'app-details')), Field('package', 'Package (app-details only)')), 'Complete account sign-in and permission choices on the tablet.', 'Google and assistants'),
    _extra('battery-exemption', 'Change background battery exemption', 'battery-exemption', (Field('package', 'Package ID', 'com.google.android.gms'), Field('enabled', 'Exempt from battery optimizations', 'true', ('true', 'false'))), 'May improve notifications at the cost of battery life.', 'Google and assistants'),
    _extra('widget-bind', 'Allow a launcher to host widgets', 'widget-bind', (PACKAGE, Field('enabled', 'Allow widget binding', 'true', ('true', 'false'))), 'Widget hosts can display data from other apps. Trust the chosen launcher.', 'Launcher and input'),
    _extra('source-catalog', 'FOSS and app source directory', 'source-catalog', description='Official project and store links for optional apps. Download APKs yourself, then use verified sideload. Streaming DRM/HD compatibility is not established.', category='App sources', read_only=True, requires_device=False),
    _extra('wireless-enable', 'Enable legacy Wi-Fi ADB from USB', 'wireless-enable', (Field('port', 'TCP port', '5555'),), 'Use only a trusted private network. This is legacy TCP debugging, not encrypted Android pairing. Re-enable USB when finished.', 'Connection tools'),
    _extra('wireless-usb', 'Return ADB to USB transport', 'wireless-usb', category='Connection tools'),
    _extra('wireless-connect', 'Connect to an ADB endpoint', 'wireless-connect', (Field('endpoint', 'Tablet hostname or IP and port'),), 'Requests a connection only. Scan and explicitly select the connected device afterward.', 'Connection tools', requires_device=False),
    _extra('wireless-disconnect', 'Disconnect an ADB endpoint', 'wireless-disconnect', (Field('endpoint', 'Tablet hostname or IP and port'),), category='Connection tools', requires_device=False),
    _extra('file-mkdir', 'Create a shared-storage folder', 'file-mkdir', (Field('remote', 'New tablet folder path'),), category='Files'),
    _extra('file-rename', 'Rename a shared-storage file or folder', 'file-rename', (Field('remote', 'Existing tablet path'), Field('destination', 'New tablet path')), category='Files'),
    _extra('file-delete', 'Delete a shared-storage file', 'file-delete', (Field('remote', 'Existing tablet file path'),), 'Permanently deletes one file. Folder trees and shared-storage roots are refused.', 'Files'),
    _extra('network-info', 'Read Wi-Fi network metering identifiers', 'network-info', category='Network', read_only=True),
    _extra('private-dns', 'Configure private DNS', 'private-dns', (Field('mode', 'DNS mode', 'opportunistic', ('off', 'opportunistic', 'hostname')), Field('hostname', 'DNS-over-TLS hostname (hostname mode only)')), 'A wrong resolver can break connectivity. Fire OS may not support Android private DNS.', 'Network'),
    _extra('private-dns-undo', 'Restore private DNS configuration', 'private-dns-undo', category='Network'),
    _extra('data-saver', 'Toggle background data saver', 'data-saver', (Field('enabled', 'Enable data saver', 'true', ('true', 'false')),), category='Network'),
    _extra('wifi-metered', 'Set a Wi-Fi network metering override', 'wifi-metered', (Field('network_id', 'Identifier from network-info'), Field('metered', 'Metered override', 'undefined', ('true', 'false', 'undefined'))), 'Metered networks can delay app downloads and updates.', 'Network'),
)

BY_KEY = {feature.key: feature for feature in FEATURES}


def feature_values(feature: Feature, items: list[str]) -> dict[str, str]:
    """Validate CLI parameter names and choices before creating a tool instance."""
    fields = {field.key: field for field in feature.fields}
    result = {field.key: field.default for field in feature.fields}
    seen = set()
    for item in items:
        if '=' not in item:
            raise ValueError('Parameters must use key=value syntax.')
        key, value = item.split('=', 1)
        if key not in fields:
            raise ValueError(f'Unknown parameter {key!r}. Available: {", ".join(fields)}')
        if key in seen:
            raise ValueError(f'Duplicate parameter {key!r}.')
        seen.add(key)
        if fields[key].choices and value not in fields[key].choices:
            raise ValueError(f'{key} must be one of: {", ".join(fields[key].choices)}')
        result[key] = value
    return result


def package_values(value: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r'[\s,]+', value.strip()) if part)


def run_feature(toolkit, serial: str, feature: Feature, values: dict[str, str]):
    """Return a read result or immutable plan. Never confirms a mutation."""
    params = dict(values)
    if feature.key == 'source-catalog':
        from .extra_workflows import source_catalog_text
        return source_catalog_text()
    if feature.backend == 'package':
        if feature.read_only:
            return toolkit.package_inventory(serial, **params)
        packages = package_values(params.pop('packages', ''))
        return toolkit.plan_package_action(serial, feature.operation, packages, **params)
    if feature.backend == 'extra':
        if feature.read_only:
            return toolkit.read_extra_tool(serial, feature.operation, **params)
        return toolkit.plan_extra_action(serial, feature.operation, **params)
    if feature.read_only:
        return toolkit.read_device_tool(serial, feature.operation, **params)
    return toolkit.plan_device_action(serial, feature.operation, **params)
