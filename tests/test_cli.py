import contextlib
import io
import subprocess
import sys
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
    def test_real_cli_help_and_demo_subprocess(self):
        for args in (['--help'],['--demo','devices']):
            result=subprocess.run([sys.executable,'-m','open_fire_toolkit',*args],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(result.stdout)

if __name__=='__main__':unittest.main()
