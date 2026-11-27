"""Offline demonstration: no subprocesses, hardware, file writes or network."""
from pathlib import Path

from .adb import Device, DeviceInfo
from .service import OPTIONAL_APPS, Plan, ToolkitError
from .workflows import TransportPlan, WorkflowPlan


class DemoToolkit:
    def __init__(self):
        self.identity = DeviceInfo('DEMO_FIRE_HD10', 'Fire HD 10 (simulated)', 'Amazon',
                                   '8.3.3.8', '11', 30, ('arm64-v8a', 'armeabi-v7a'), 0)
        self.disabled: set[str] = set()
        self.value = '1'
        self.paired_original: tuple[str, bool] | None = None
        self.original: str | None = None
        self.demo_packages = set(OPTIONAL_APPS) | {'com.amazon.kindle.kso', 'com.amazon.firelauncher', 'com.android.vending', 'com.google.android.gms', 'org.firetools.adshelper'}
        self.removed: set[str] = set()

    def _check(self, serial):
        if serial != self.identity.serial:
            raise ToolkitError('Unknown demo serial. Select DEMO_FIRE_HD10.')

    def devices(self):
        return [Device(self.identity.serial, 'device', 'SIMULATED_Fire_HD_10')]

    def device_info(self, serial):
        self._check(serial)
        return self.identity

    def packages(self, serial, disabled_only=False):
        self._check(serial)
        return sorted(self.disabled if disabled_only else OPTIONAL_APPS)

    def _plan(self, title, serial, action, details, package=''):
        self._check(serial)
        return Plan('SIMULATED — ' + title, serial, tuple(details),
                    ('Demo only: no APK was verified and no device will be changed.',),
                    action, self.identity, package=package, old_value=self.value)

    def plan_google_play(self, serial, paths):
        return self._plan('Google Play installation preview', serial, 'play', (
            'SIMULATED: verify package identities and Google signing certificates.',
            'SIMULATED: sample core order is Account Manager → Framework → Play services → Play Store.',
            'Selected Calendar and Contacts sync adapters follow the core packages in a real installation.',
            'The real workflow requires locally selected genuine APKs and Google build-tools.',
        ))

    def plan_ads(self, serial, restore=False, *, paired=False):
        if paired:
            if restore and self.paired_original is None:
                raise ToolkitError('Demo: try suppression with setting and package first.')
            title = 'Undo setting and package' if restore else 'Suppress with setting and package'
            return self._plan(title, serial, 'ads_paired_restore' if restore else 'ads_paired',
                              ('Simulate changing LOCKSCREEN_AD_ENABLED and com.amazon.kindle.kso together.',
                               'Undo restores both original values.'), 'com.amazon.kindle.kso')
        if restore and self.original is None:
            raise ToolkitError('Demo: try temporary suppression first, then restore it.')
        return self._plan('Restore ad setting' if restore else 'Try temporary ad suppression', serial,
                          'ads_restore' if restore else 'ads',
                          (f'Simulated current setting: {self.value}',
                           'Real firmware may ignore/reset this setting; ads may remain.'))

    def plan_package(self, serial, package, enable=False):
        if package not in OPTIONAL_APPS:
            raise ToolkitError('Package is not on the optional-app allowlist.')
        return self._plan(('Enable ' if enable else 'Disable ') + OPTIONAL_APPS[package], serial,
                          'enable' if enable else 'disable', (f'Simulated package: {package}',), package)

    def plan_reboot(self, serial):
        return self._plan('Restart tablet', serial, 'reboot', ('Simulate a normal restart.',))

    def package_inventory(self, serial, mode='all'):
        self._check(serial)
        if mode not in {'all', 'system', 'third-party', 'disabled', 'uninstalled'}:
            raise ToolkitError('Unknown inventory mode.')
        items = self.disabled if mode == 'disabled' else self.removed if mode == 'uninstalled' else self.demo_packages - self.removed
        return [{'package': package, 'state': 'removed' if package in self.removed else 'disabled' if package in self.disabled else 'enabled', 'label': OPTIONAL_APPS.get(package, package)} for package in sorted(items)]

    def _workflow(self, serial, backend, operation, packages=(), **parameters):
        from .feature_catalog import FEATURES
        self._check(serial)
        feature = next((feature for feature in FEATURES if feature.backend == backend and feature.operation == operation and not feature.read_only), None)
        if feature is None:
            raise ToolkitError('Unknown simulated tool.')
        details = tuple([f'SIMULATED operation: {feature.label}', *(f'{key}: {value}' for key, value in parameters.items()), *(f'Package: {package}' for package in packages)])
        return WorkflowPlan('SIMULATED — ' + feature.label, serial, details,
                            ('Demo only. No commands, file reads/writes, real APK verification or tablet changes occur.', feature.description),
                            backend + '_workflow', self.identity, operation,
                            tuple(parameters.items()), tuple(packages))

    def plan_package_action(self, serial, operation, packages=(), **parameters):
        return self._workflow(serial, 'package', operation, packages, **parameters)

    def plan_device_action(self, serial, operation, **parameters):
        return self._workflow(serial, 'device', operation, **parameters)

    def plan_extra_action(self, serial, operation, **parameters):
        if operation in {'wireless-connect', 'wireless-disconnect'}:
            from .extra_workflows import _endpoint
            if set(parameters) != {'endpoint'}:
                raise ToolkitError('Specify an endpoint for the simulated connection.')
            endpoint = _endpoint(parameters['endpoint'])
            return TransportPlan('SIMULATED — ' + operation, ('Endpoint: ' + endpoint,),
                                 ('Demo only. No network connection is made.',), operation,
                                 (('endpoint', endpoint),))
        return self._workflow(serial, 'extra', operation, **parameters)

    def read_extra_tool(self, serial, operation, **parameters):
        self._check(serial)
        if operation == 'source-catalog':
            return 'SIMULATED: source directory only. F-Droid https://f-droid.org · VLC https://www.videolan.org/vlc/ · NewPipe https://newpipe.net'
        if operation == 'network-info':
            return 'SIMULATED: Example Wi-Fi network; metered=false'
        raise ToolkitError('Unknown simulated read tool.')

    def read_device_tool(self, serial, operation, **parameters):
        from .feature_catalog import FEATURES
        self._check(serial)
        if not any(feature.backend == 'device' and feature.operation == operation and feature.read_only for feature in FEATURES):
            raise ToolkitError('Unknown simulated read tool.')
        samples = {'settings-list': 'screen_off_timeout=60000\n', 'settings-get': '60000', 'users': 'UserInfo{0:Owner:13} running',
                   'keyboards': 'com.amazon.inputmethod/.ImeService', 'tasks': 'USER PID NAME\nu0_a100 4321 com.android.vending',
                   'storage-list': 'Download\nPictures\n', 'home': 'com.amazon.firelauncher/.Launcher',
                   'device-stats': 'Battery: 87%\nShared storage: 20 GiB free', 'logcat': 'Example log output only; no device data read.',
                   'permissions': 'Example package permission report.'}
        return 'SIMULATED: ' + samples.get(operation, 'Sample output for ' + operation)

    def execute(self, plan, confirmed=False, log=print):
        if not confirmed:
            raise ToolkitError('Explicit confirmation is required even in demo mode.')
        if isinstance(plan, TransportPlan):
            if plan.operation not in {'wireless-connect', 'wireless-disconnect'} or plan != self.plan_extra_action('', plan.operation, **plan.params):
                raise ToolkitError('Invalid simulated connection plan.')
            result = ['SIMULATED: connection request completed in memory. No network or tablet was accessed.']
            for message in result:
                log(message)
            return result
        self._check(plan.serial)
        if isinstance(plan, WorkflowPlan):
            if plan.action not in {'package_workflow', 'device_workflow', 'extra_workflow'}:
                raise ToolkitError('Unknown simulated action.')
            if plan.action == 'package_workflow':
                selected = set(plan.packages)
                if plan.operation == 'disable':
                    self.disabled.update(selected)
                elif plan.operation == 'enable':
                    self.disabled.difference_update(selected)
                elif plan.operation == 'uninstall':
                    self.removed.update(selected)
                elif plan.operation == 'restore':
                    self.removed.difference_update(selected)
            result = ['SIMULATED: action completed in memory. No hardware or host files were accessed.']
            for message in result:
                log(message)
            return result
        if plan.action == 'ads':
            if self.original is None:
                self.original = self.value
            self.value = '0'
        elif plan.action == 'ads_restore':
            if self.original is None:
                raise ToolkitError('No simulated restore state.')
            self.value, self.original = self.original, None
        elif plan.action == 'ads_paired':
            if self.paired_original is None:
                self.paired_original = (self.value, plan.package in self.disabled)
            self.value = '0'
            self.disabled.add(plan.package)
        elif plan.action == 'ads_paired_restore':
            if self.paired_original is None:
                raise ToolkitError('No simulated paired restore state.')
            self.value, originally_disabled = self.paired_original
            if not originally_disabled:
                self.disabled.discard(plan.package)
            else:
                self.disabled.add(plan.package)
            self.paired_original = None
        elif plan.action == 'disable':
            self.disabled.add(plan.package)
        elif plan.action == 'enable':
            self.disabled.discard(plan.package)
        elif plan.action not in ('play', 'reboot'):
            raise ToolkitError('Unknown simulated action.')
        result = ['SIMULATED: action completed in memory. No hardware was accessed.']
        for message in result:
            log(message)
        return result
