"""Offline demonstration: no subprocesses, hardware, file writes or network."""
from pathlib import Path

from .adb import Device, DeviceInfo
from .service import OPTIONAL_APPS, Plan, ToolkitError


class DemoToolkit:
    def __init__(self):
        self.identity = DeviceInfo('DEMO_FIRE_HD10', 'Fire HD 10 (simulated)', 'Amazon',
                                   '8.3.3.8', '11', 30, ('arm64-v8a', 'armeabi-v7a'), 0)
        self.disabled: set[str] = set()
        self.value = '1'
        self.original: str | None = None

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
            'SIMULATED: install Framework → Play services → Play Store.',
            'The real workflow requires locally selected genuine APKs and Google build-tools.',
        ))

    def plan_ads(self, serial, restore=False):
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

    def execute(self, plan, confirmed=False, log=print):
        self._check(plan.serial)
        if not confirmed:
            raise ToolkitError('Explicit confirmation is required even in demo mode.')
        if plan.action == 'ads':
            if self.original is None:
                self.original = self.value
            self.value = '0'
        elif plan.action == 'ads_restore':
            if self.original is None:
                raise ToolkitError('No simulated restore state.')
            self.value, self.original = self.original, None
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
