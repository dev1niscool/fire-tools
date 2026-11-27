"""Offline demonstration: no subprocesses, hardware, file writes or network."""
from dataclasses import replace

from .adb import Device, DeviceInfo
from .apk import PLAY_CORE
from .package_catalog import APP_LABELS, STOCK_HOME, UPDATERS
from .package_workflows import PackageWorkflows, _guard_selection, _owner_target, _package
from .service import OPTIONAL_APPS, Plan, ToolkitError, google_status_text
from .workflows import TransportPlan, WorkflowPlan


_EXPLICIT_PACKAGE_CHANGES = {'disable', 'enable', 'uninstall', 'restore', 'ota-disable', 'ota-enable'}


class _DemoPackagePreview(PackageWorkflows):
    """Use the real preset and undo planner with only the simulated tablet's data."""

    def __init__(self, demo):
        self.demo = demo

    def _writable_device(self, serial):
        return self.demo.device_info(serial)

    def _pkg_states(self, serial):
        return {package: self.demo._package_state(package) for package in self.demo.demo_packages}

    def _pkg_owner_mode(self, serial, package):
        return self.demo.updater_modes[package]

    def _pkg_list(self, serial, flag):
        installed = self.demo.demo_packages - self.demo.removed
        if flag == '-s':
            return installed & self.demo.system_packages
        if flag == '-3':
            return installed - self.demo.system_packages
        raise AssertionError(f'Unexpected demo package query: {flag}')

    def _pkg_undo_record(self, device):
        return {}, {'states': self.demo.package_undo}

    def _pkg_keyboard(self, serial):
        return 'com.amazon.inputmethod/.ImeService'

    def _pkg_activity(self, serial, category, package=None, *, allow_unresolved=False):
        if package not in (None, STOCK_HOME):
            raise AssertionError(f'Unexpected demo HOME package: {package}')
        return STOCK_HOME + '/.Launcher'


class DemoToolkit:
    def __init__(self):
        self.identity = DeviceInfo('DEMO_FIRE_HD10', 'Fire HD 10 (simulated)', 'Amazon',
                                   '8.3.3.8', '11', 30, ('arm64-v8a', 'armeabi-v7a'), 0)
        self.disabled: set[str] = {'com.android.calendar'}
        self.value = '1'
        self.paired_original: tuple[str, bool] | None = None
        self.original: str | None = None
        self.system_packages = set(OPTIONAL_APPS) | set(UPDATERS) | {
            'com.amazon.kindle.kso', STOCK_HOME, 'com.amazon.cloud9',
            'com.android.calendar', 'com.amazon.kindle.otter.oobe',
        }
        self.demo_packages = self.system_packages | {
            'com.android.vending', 'com.google.android.gms', 'org.firetools.adshelper',
        }
        self.removed: set[str] = set()
        self.updater_modes = dict.fromkeys(UPDATERS, '0')
        self.package_undo: dict[str, str] = {}

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
        installed = self.demo_packages - self.removed
        return sorted(installed & self.disabled if disabled_only else installed)

    def _plan(self, title, serial, action, details, package=''):
        self._check(serial)
        return Plan('SIMULATED — ' + title, serial, tuple(details),
                    ('Demo only: no APK was verified and no device will be changed.',),
                    action, self.identity, package=package, old_value=self.value)

    def plan_google_play(self, serial, paths):
        return self._plan('Google Play installation preview', serial, 'play', (
            'SIMULATED: verify package identities and Google signing certificates.',
            'SIMULATED: install the four sample packages in order: Account Manager → Framework → Play services → Play Store.',
            'Selected Calendar and Contacts sync adapters follow the core packages in a real installation.',
            'The real workflow requires locally selected genuine APKs and Google build-tools.',
        ))

    def google_status(self, serial):
        self._check(serial)
        return 'SIMULATED\n' + google_status_text({
            package: self._package_state(package) for package in self.demo_packages
        })

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
        return _DemoPackagePreview(self).package_inventory(serial, mode)

    def updater_status(self, serial):
        self._check(serial)
        return _DemoPackagePreview(self).updater_status(serial)

    def package_info(self, serial, package):
        self._check(serial)
        package = _package(package)
        if package not in self.demo_packages:
            state = 'not found in the package inventory'
        elif package in self.removed:
            state = 'uninstalled'
        else:
            state = f'installed, {self._package_state(package)}'
        return (f'SIMULATED\nPackage: {package}\nLabel: {APP_LABELS.get(package, "not reported")}\n'
                f'Owner user 0: {state}\nVersion and SDK metadata are omitted in demo mode.')

    def _package_state(self, package):
        if package in self.removed:
            return 'uninstalled'
        return 'disabled' if package in self.disabled else 'enabled'

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
        if operation in _EXPLICIT_PACKAGE_CHANGES or operation == 'undo':
            selected = self.package_undo if operation == 'undo' else packages
            for package in selected:
                guard = 'ota-enable' if operation == 'undo' and package in UPDATERS else operation
                _guard_selection(package, guard)
        if operation in {'debloat', 'undo', 'ota-disable', 'ota-enable'}:
            self._check(serial)
            if parameters.get('profile') == 'custom' or parameters.get('list_file'):
                raise ToolkitError('Demo mode only simulates built-in presets. Custom lists require reading a local file.')
            plan = _DemoPackagePreview(self).plan_package_action(serial, operation, packages, **parameters)
            return replace(plan, title='SIMULATED — ' + plan.title,
                           warnings=('Demo only. All package states and undo data stay in memory.', *plan.warnings))
        return self._workflow(serial, 'package', operation, packages, **parameters)

    def _apply_package_plan(self, plan):
        explicit = plan.packages if plan.operation in _EXPLICIT_PACKAGE_CHANGES else ()
        if self.plan_package_action(plan.serial, plan.operation, explicit, **plan.params) != plan:
            raise ToolkitError('Simulated package state changed since preview. Review again.')
        undo = plan.operation == 'undo'
        mode = dict(plan.snapshot).get('list-mode', plan.operation)
        previous = {}
        result = []
        for package in plan.packages:
            before = dict(plan.snapshot).get(package, self._package_state(package))
            if before == 'uninstalled' and not undo and mode != 'restore':
                continue
            target = _owner_target(mode, before, self.package_undo.get(package))
            if target == before:
                continue
            if package in self.demo_packages:
                previous[package] = before
            self.disabled.discard(package)
            self.removed.discard(package)
            effective, _, raw = target.partition(':')
            if raw:
                self.updater_modes[package] = raw
            if effective == 'disabled':
                self.disabled.add(package)
            elif effective == 'uninstalled':
                self.removed.add(package)
            result.append(f'SIMULATED: {package} is {self._package_state(package)} for owner user 0.')
        if undo:
            for package in plan.packages:
                self.package_undo.pop(package)
        elif previous:
            self.package_undo = previous
        return result

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
            result = ['SIMULATED: action completed in memory. No hardware or host files were accessed.']
            if plan.action == 'package_workflow' and plan.operation in _EXPLICIT_PACKAGE_CHANGES | {'debloat', 'undo'}:
                result.extend(self._apply_package_plan(plan))
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
        elif plan.action == 'play':
            sample_packages = ('com.google.android.gsf.login', *PLAY_CORE)
            self.demo_packages.update(sample_packages)
            self.removed.difference_update(sample_packages)
        elif plan.action != 'reboot':
            raise ToolkitError('Unknown simulated action.')
        result = ['SIMULATED: action completed in memory. No hardware was accessed.']
        for message in result:
            log(message)
        return result
