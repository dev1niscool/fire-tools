"""Command-line interface; changes are previews unless --yes is supplied."""
import argparse
import sys
from dataclasses import asdict

from . import __version__
from .adb import AdbError
from .apk import ApkError
from .service import ToolConfig, Toolkit, ToolkitError
from .feature_catalog import BY_KEY, FEATURES, feature_values, run_feature


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Open Fire Toolkit — inspectable tablet utilities. No bundled APKs or tools.')
    p.add_argument('--version', action='version', version=__version__)
    p.add_argument('--adb', default='', help='Full path to official adb/adb.exe')
    p.add_argument('--aapt', default='', help='Full path to official aapt/aapt.exe')
    p.add_argument('--apksigner-jar', default='', help='Full path to Google build-tools lib/apksigner.jar')
    p.add_argument('--java', default='', help='Full path to java/java.exe')
    p.add_argument('--demo', action='store_true', help='Offline simulation; never accesses hardware')
    subs = p.add_subparsers(dest='command')
    gui = subs.add_parser('gui', help='Open the desktop interface (default)')
    gui.add_argument('--demo', dest='gui_demo', action='store_true', help='Offline simulation')
    subs.add_parser('devices', help='List ADB devices without selecting one')
    catalog = subs.add_parser('tools', help='List all tools and their parameters; no device required')
    catalog.add_argument('--feature', choices=sorted(BY_KEY), help='Show parameters for one tool')
    tool = subs.add_parser('tool', help='Preview or run a tool from the catalog')
    tool.add_argument('feature', choices=sorted(BY_KEY))
    tool.add_argument('--serial', default='', help='Required for tablet operations; not for source links or endpoint connection')
    tool.add_argument('--param', action='append', default=[], metavar='KEY=VALUE')
    tool.add_argument('--yes', action='store_true', help='Confirm the displayed action')
    for name, text in (('info', 'Show device identity'), ('play', 'Verify/install local Google Play APKs'),
                       ('ads', 'Preview temporary ad-setting suppression or restore'),
                       ('apps', 'List or enable/disable optional apps'), ('reboot', 'Preview a normal restart')):
        sub = subs.add_parser(name, help=text)
        sub.add_argument('--serial', required=True, help='Explicit ADB serial from devices')
        if name != 'info':
            sub.add_argument('--yes', action='store_true', help='Confirm the displayed changes')
        if name == 'play':
            sub.add_argument('apks', nargs='+', help='Local APK files (three required components, optional Account Manager)')
        if name == 'ads':
            sub.add_argument('--restore', action='store_true', help='Restore the saved original setting')
        if name == 'apps':
            group = sub.add_mutually_exclusive_group()
            group.add_argument('--disable', metavar='PACKAGE')
            group.add_argument('--enable', metavar='PACKAGE')
            sub.add_argument('--disabled-only', action='store_true')
    return p


def _show_plan(plan):
    print(plan.title)
    print(f'Device: {plan.device.model} ({plan.serial})')
    for item in plan.details:
        print('  ' + item)
    for warning in plan.warnings:
        print('Note: ' + warning)


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    demo = args.demo or getattr(args, 'gui_demo', False)
    if args.command == 'tools':
        selected = [BY_KEY[args.feature]] if args.feature else FEATURES
        for feature in selected:
            print(f'{feature.key}: {feature.label} [{feature.category}]')
            if args.feature:
                print(feature.description)
                print('Read only' if feature.read_only else 'Preview first; --yes confirms the action.')
                for field in feature.fields:
                    choices = ' Choices: ' + ', '.join(field.choices) if field.choices else ''
                    print(f'  --param {field.key}=VALUE: {field.label}. Default: {field.default!r}.{choices}')
        return 0
    if args.command in (None, 'gui'):
        try:
            from .gui import main as gui_main
            gui_main(demo=demo)
            return 0
        except (ImportError, RuntimeError) as exc:
            print(f'Cannot start desktop interface: {exc}. Install Python with Tk support, or use --help for CLI commands.', file=sys.stderr)
            return 1
        except Exception as exc:
            # Tk initialization failures (e.g. no graphical display) should be actionable.
            if type(exc).__name__ != 'TclError':
                raise
            print(f'Cannot open a graphical display: {exc}. Use a desktop session or CLI commands.', file=sys.stderr)
            return 1
    try:
        feature = BY_KEY[args.feature] if args.command == 'tool' else None
        values = feature_values(feature, args.param) if feature is not None else None
        if feature is not None and feature.requires_device and not args.serial:
            raise ValueError('Specify --serial for this tablet operation.')
        if feature is not None and feature.key == 'source-catalog':
            print(run_feature(None, '', feature, values))
            return 0
        if demo:
            from .demo import DemoToolkit
            toolkit = DemoToolkit()
            print('SIMULATED DEMO — no hardware commands or APK verification.')
        else:
            toolkit = Toolkit(ToolConfig(args.adb, args.aapt, args.apksigner_jar, args.java))
        if feature is not None:
            result = run_feature(toolkit, args.serial, feature, values)
            if feature.read_only:
                if isinstance(result, list):
                    for row in result:
                        print('\t'.join(f'{key}={value}' for key, value in row.items()))
                else:
                    print(result)
                return 0
            _show_plan(result)
            if not args.yes:
                print('Preview only — no changes made. Run again with --yes to apply this action.')
                return 0
            toolkit.execute(result, confirmed=True)
            return 0
        if args.command == 'devices':
            devices = toolkit.devices()
            if not devices:
                print('No devices. Connect a USB data cable, enable USB debugging and approve the tablet prompt.')
            for device in devices:
                print(f'{device.serial}\t{device.state}\t{device.model}')
            return 0
        if args.command == 'info':
            for key, value in asdict(toolkit.device_info(args.serial)).items():
                print(f'{key}: {value}')
            return 0
        if args.command == 'apps' and not args.disable and not args.enable:
            for package in toolkit.packages(args.serial, args.disabled_only):
                print(package)
            return 0
        if args.command == 'play':
            plan = toolkit.plan_google_play(args.serial, args.apks)
        elif args.command == 'ads':
            plan = toolkit.plan_ads(args.serial, args.restore)
        elif args.command == 'apps':
            plan = toolkit.plan_package(args.serial, args.enable or args.disable, enable=bool(args.enable))
        else:
            plan = toolkit.plan_reboot(args.serial)
        _show_plan(plan)
        if not args.yes:
            print('Preview only — no changes made. Run again with --yes to apply this action.')
            return 0
        toolkit.execute(plan, confirmed=True)
        return 0
    except (ToolkitError, AdbError, ApkError, OSError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Interrupted. A command already accepted by the tablet may have taken effect; check its state before retrying.', file=sys.stderr)
        return 130
