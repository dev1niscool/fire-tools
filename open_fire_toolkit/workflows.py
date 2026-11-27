"""Immutable previews shared by the extended device and application tools."""
from dataclasses import dataclass

from .adb import DeviceInfo
from .apk import ApkInfo


@dataclass(frozen=True)
class WorkflowPlan:
    title: str
    serial: str
    details: tuple[str, ...]
    warnings: tuple[str, ...]
    action: str
    device: DeviceInfo
    operation: str
    parameters: tuple[tuple[str, str], ...] = ()
    packages: tuple[str, ...] = ()
    snapshot: tuple[tuple[str, str], ...] = ()
    apks: tuple[ApkInfo, ...] = ()

    @property
    def params(self) -> dict[str, str]:
        return dict(self.parameters)


@dataclass(frozen=True)
class TransportPlan:
    """Connection-only host requests; never authorizes a tablet command."""
    title: str
    details: tuple[str, ...]
    warnings: tuple[str, ...]
    operation: str
    parameters: tuple[tuple[str, str], ...]

    @property
    def params(self) -> dict[str, str]:
        return dict(self.parameters)

    @property
    def action(self) -> str:
        return 'transport'

    @property
    def serial(self) -> str:
        return ''

    @property
    def device(self) -> DeviceInfo:
        return DeviceInfo('', 'ADB transport', 'Host', '', '', 0, (), 0)
