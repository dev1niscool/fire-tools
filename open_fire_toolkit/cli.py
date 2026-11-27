"""Preview tablet operations and confirm the exact reviewed plan."""
import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict

from . import __version__
from .adb import AdbError
from .apk import ApkError
from .service import ToolConfig, Toolkit, ToolkitError
from .feature_catalog import BY_KEY, FEATURES, feature_values, run_feature


def _confirmation_options(command):
    command.add_argument('--yes', action='store_true', help='Apply the reviewed action')
    command.add_argument('--confirm-token', help='Confirmation token from the reviewed preview')


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
    check = subs.add_parser('check-apks', help='Compare local files with documented scan hashes before connecting a tablet')
    check.add_argument('--verify-google', action='store_true', help='Verify standalone Google components with local Android Build Tools and Java')
    check.add_argument('--sdk', type=int, help='Target Android API level for --verify-google, e.g. 30 for a 2023 HD 10')
    check.add_argument('apks', nargs='+', help='Local APK file paths')
    subs.add_parser('devices', help='List ADB devices without selecting one')
    catalog = subs.add_parser('tools', help='List all tools and their parameters; no device required')
    catalog.add_argument('--feature', choices=sorted(BY_KEY), help='Show parameters for one tool')
    tool = subs.add_parser('tool', help='Preview or run a tool from the catalog')
    tool.add_argument('feature', choices=sorted(BY_KEY))
    tool.add_argument('--serial', default='', help='Select a tablet for device operations. Offline references and endpoint connections need no serial.')
    tool.add_argument('--param', action='append', default=[], metavar='KEY=VALUE')
    _confirmation_options(tool)
    for name, text in (('info', 'Show device identity'), ('play', 'Verify/install local Google Play APKs'),
                       ('ads', 'Preview temporary ad-setting suppression or restore'),
                       ('apps', 'List or enable/disable optional apps'), ('reboot', 'Preview a normal restart')):
        sub = subs.add_parser(name, help=text)
        sub.add_argument('--serial', required=True, help='Explicit ADB serial from devices')
        if name != 'info':
            _confirmation_options(sub)
        if name == 'play':
            sub.add_argument('apks', nargs='+', help='Standalone Google APKs: Framework, Play services and Play Store, plus optional Account Manager, Calendar Sync or Contacts Sync. Choose only adapters to add sync to an existing installation.')
        if name == 'ads':
            sub.add_argument('--restore', action='store_true', help='Restore the original state saved by the selected mode')
            sub.add_argument('--with-package', action='store_true',
                             help='Change the ad setting and Special Offers package together')
        if name == 'apps':
            group = sub.add_mutually_exclusive_group()
            group.add_argument('--disable', metavar='PACKAGE')
            group.add_argument('--enable', metavar='PACKAGE')
            sub.add_argument('--disabled-only', action='store_true')
    return p


def _print_report(report):
    try:
        print(report)
    except UnicodeEncodeError as error:
        # Windows pipes can use a legacy code page even with a Unicode-capable console.
        readable = report.replace('→', '->')
        encoding = sys.stdout.encoding or error.encoding
        print(readable.encode(encoding, 'backslashreplace').decode(encoding))


def _show_plan(plan):
    lines = [plan.title, f'Device: {plan.device.model} ({plan.serial})']
    lines.extend('  ' + item for item in plan.details)
    lines.extend('Note: ' + warning for warning in plan.warnings)
    _print_report('\n'.join(lines))


def _confirm_plan(toolkit, plan, args, demo):
    _show_plan(plan)
    # Include every immutable field, even snapshot and signer details that
    # might be abbreviated in the human-readable preview.
    payload = json.dumps([type(plan).__name__, asdict(plan)], sort_keys=True,
                         separators=(',', ':'), default=os.fspath).encode('utf-8')
    token = hashlib.sha256(payload).hexdigest()
    if not args.yes:
        flags = '--yes' if demo else f'--yes --confirm-token {token}'
        print('Preview only — no changes made. After review, repeat with ' + flags)
        return 0
    if not demo and args.confirm_token != token:
        raise ValueError('Confirmation token is missing or the reviewed plan changed. Run a fresh preview and review it.')
    toolkit.execute(plan, confirmed=True)
    return 0


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    demo = args.demo or getattr(args, 'gui_demo', False)
    if args.command == 'check-apks':
        if demo:
            print('Run check-apks without --demo to hash your local files.', file=sys.stderr)
            return 1
        from .apk_checks import check_apk_files, verify_google_apk_files
        try:
            if args.verify_google:
                report, success = verify_google_apk_files(
                    args.apks, sdk=args.sdk, aapt_path=args.aapt, apksigner_jar=args.apksigner_jar,
                    java_path=args.java)
            elif args.sdk is not None:
                raise ApkError('--sdk requires --verify-google.')
            else:
                report, success = check_apk_files(args.apks)
        except (ApkError, OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        _print_report(report)
        return 0 if success else 1
    if args.command == 'tools':
        selected = [BY_KEY[args.feature]] if args.feature else FEATURES
        for feature in selected:
            print(f'{feature.key}: {feature.label} [{feature.category}]')
            if args.feature:
                print(feature.description)
                print('Read only' if feature.read_only else 'Preview first. Apply with --yes and the displayed --confirm-token.')
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
        if feature is not None and feature.backend == 'local':
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
                        _print_report('\t'.join(f'{key}={value}' for key, value in row.items()))
                else:
                    _print_report(result)
                return 0
            return _confirm_plan(toolkit, result, args, demo)
        if args.command == 'devices':
            devices = toolkit.devices()
            if not devices:
                print('No devices. Connect a USB data cable, enable USB debugging and approve the tablet prompt.')
            for device in devices:
                print(f'{device.serial}\t{device.state}\t{device.model}')
            return 0
        if args.command == 'info':
            info = toolkit.device_info(args.serial)
            for key in ('serial', 'model', 'manufacturer', 'fire_os', 'android_release', 'sdk', 'abis', 'user_id'):
                _print_report(f'{key}: {getattr(info, key)}')
            return 0
        if args.command == 'apps' and not args.disable and not args.enable:
            for package in toolkit.packages(args.serial, args.disabled_only):
                print(package)
            return 0
        if args.command == 'play':
            plan = toolkit.plan_google_play(args.serial, args.apks)
        elif args.command == 'ads':
            plan = toolkit.plan_ads(args.serial, args.restore, paired=args.with_package)
        elif args.command == 'apps':
            plan = toolkit.plan_package(args.serial, args.enable or args.disable, enable=bool(args.enable))
        else:
            plan = toolkit.plan_reboot(args.serial)
        return _confirm_plan(toolkit, plan, args, demo)
    except (ToolkitError, AdbError, ApkError, OSError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Interrupted. A command already accepted by the tablet may have taken effect; check its state before retrying.', file=sys.stderr)
        return 130
