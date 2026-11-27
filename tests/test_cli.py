import contextlib
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from open_fire_toolkit.cli import main
from open_fire_toolkit.demo import DemoToolkit


class CliTests(unittest.TestCase):
    def call(self, args):
        out=io.StringIO();err=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=main(args)
        return code,out.getvalue(),err.getvalue()
    def test_demo_inventory_cannot_execute_subprocesses(self):
        with patch('subprocess.run',side_effect=AssertionError('No subprocess permitted')):
            code,out,err=self.call(['--demo','devices'])
        self.assertEqual(code,0);self.assertIn('DEMO_FIRE_HD10',out);self.assertIn('SIMULATED',out)
    def test_info_keeps_the_hardware_digest_out_of_support_output(self):
        serial = 'DEMO_FIRE_HD10'
        info = replace(DemoToolkit().device_info(serial), hardware_serial_sha256='ab' * 32)
        with patch.object(DemoToolkit, 'device_info', return_value=info):
            code, output, _ = self.call(['--demo', 'info', '--serial', serial])
        self.assertEqual(code, 0)
        self.assertIn(f'serial: {serial}', output)
        self.assertNotIn(info.hardware_serial_sha256, output)
        self.assertNotIn('hardware_serial_sha256', output)

    def test_mutation_defaults_to_preview(self):
        with patch.object(DemoToolkit,'execute',side_effect=AssertionError('must preview')):
            code,out,err=self.call(['--demo','ads','--serial','DEMO_FIRE_HD10'])
        self.assertEqual(code,0);self.assertIn('Preview only',out)
    def test_confirmed_demo_action_reports_simulation(self):
        code,out,err=self.call(['--demo','ads','--serial','DEMO_FIRE_HD10','--yes'])
        self.assertEqual(code,0);self.assertIn('SIMULATED',out)
    def test_missing_adb_produces_actionable_error(self):
        code,out,err=self.call(['devices'])
        self.assertEqual(code,1);self.assertIn('adb',err.lower());self.assertNotIn('Traceback',err)
    def test_unknown_demo_serial_refused(self):
        code,out,err=self.call(['--demo','info','--serial','another'])
        self.assertEqual(code,1);self.assertIn('serial',err.lower())
    def test_source_launcher_isolates_python_and_forwards_arguments(self):
        if os.name != 'nt' and not sys.platform.startswith('linux'):
            self.skipTest('Source launchers target Linux and Windows')
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'source with spaces'
            package = root / 'open_fire_toolkit'
            package.mkdir(parents=True)
            downloads = root.parent / 'Downloads'
            downloads.mkdir()
            filename = 'file with spaces.apk'
            (downloads / filename).write_bytes(b'caller file')
            (root / filename).write_bytes(b'different source file')
            shutil.copy(project / 'open_fire_toolkit' / '__main__.py', package)
            (package / '__init__.py').write_text('', encoding='utf-8')
            (package / 'cli.py').write_text(
                'import json, sys\n'
                'from pathlib import Path\n'
                'def main():\n'
                '    print(json.dumps([sys.flags.isolated, sys.flags.no_site, sys.argv[1:], sys.path, '
                'Path(sys.argv[2]).read_bytes().hex()]))\n'
                '    return 19\n', encoding='utf-8')
            options = ['check-apks', filename]
            if os.name == 'nt':
                # The extracted folder may contain unrelated files with interpreter names.
                for filename in ('py.exe', 'python.exe', 'py.cmd', 'python.cmd'):
                    (root / filename).touch()
                    (downloads / filename).touch()
                shutil.copy(project / 'launch-windows.cmd', root)
                command = [os.environ['COMSPEC'], '/d', '/c', 'call', str(root / 'launch-windows.cmd')]
            else:
                launcher = root / 'launch-linux.sh'
                shutil.copy(project / launcher.name, launcher)
                link = root.parent / 'link to launcher'
                link.symlink_to(launcher)
                command = [str(link)]
            env = dict(os.environ, PYTHONHOME=directory, PYTHONPATH=directory)
            result = subprocess.run([*command, *options], cwd=downloads, env=env, capture_output=True,
                                    text=True, timeout=20)
            self.assertEqual(result.returncode, 19, result.stderr or result.stdout)
            isolated, no_site, received, imports, read_bytes = json.loads(result.stdout)
            self.assertEqual(bytes.fromhex(read_bytes), b'caller file')
            self.assertEqual((isolated, no_site), (1, 1))
            self.assertEqual(received, options)
            self.assertNotIn(str(root), imports)
            self.assertNotIn(directory, imports)

    def test_real_cli_help_and_demo_subprocess(self):
        for args in (['--help'],['--demo','devices']):
            result=subprocess.run([sys.executable,'-m','open_fire_toolkit',*args],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(result.stdout)

    def test_ascii_pipe_preserves_demo_output_and_review_instructions(self):
        for args, expected in ((['--help'], 'usage:'),
                               (['--demo', 'devices'], 'DEMO_FIRE_HD10'),
                               (['tool', 'debloat-presets'], 'Complete Debloat'),
                               (['--demo', 'reboot', '--serial', 'DEMO_FIRE_HD10'], '--yes')):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, '-m', 'open_fire_toolkit', *args],
                                        env=dict(os.environ, PYTHONIOENCODING='ascii'),
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)

    def test_confirmed_operation_can_log_unicode_to_a_legacy_pipe(self):
        def emit_result(toolkit, plan, confirmed, log=print):
            self.assertTrue(confirmed)
            log('Saved to 写真.png')
            return ['Saved to 写真.png']

        buffer = io.BytesIO()
        output = io.TextIOWrapper(buffer, encoding='cp1252')
        with patch.object(DemoToolkit, 'execute', emit_result), contextlib.redirect_stdout(output):
            code = main(['--demo', 'reboot', '--serial', 'DEMO_FIRE_HD10', '--yes'])
            output.flush()
        self.assertEqual(code, 0)
        self.assertIn(b'Saved to ', buffer.getvalue())

if __name__=='__main__':unittest.main()
