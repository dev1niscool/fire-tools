import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from open_fire_toolkit.adb import DeviceInfo, Device
from open_fire_toolkit.apk import ApkInfo, GOOGLE_SIGNER_SHA256, file_sha256
from open_fire_toolkit.service import Toolkit, ToolConfig, ToolkitError, OPTIONAL_APPS


def info(**kwargs):
    values = dict(serial='SERIAL123', model='KFTUWI', manufacturer='Amazon', fire_os='8.3.3.8', android_release='11', sdk=30, abis=('arm64-v8a','armeabi-v7a'), user_id=0)
    values.update(kwargs)
    return DeviceInfo(**values)


class FakeAdb:
    def __init__(self):
        self.identity = info()
        self.value = '1'
        self.commands = []
        self.installed = []
        self.fail_install = None
        self.disabled = set()
        self.present = set(OPTIONAL_APPS)
        self.before_install = None
        self.ignore_setting = False
    def devices(self): return [Device('SERIAL123','device','KFTUWI')]
    def info(self, serial): return self.identity
    def packages(self, serial, disabled_only=False): return sorted(self.disabled if disabled_only else self.present)
    def shell(self, serial, args, timeout=30):
        args = tuple(args)
        self.commands.append(args)
        if args[:4] == ('settings','--user','0','get'): return self.value
        if args[:4] == ('settings','--user','0','put'):
            if not self.ignore_setting: self.value=args[-1]
            return ''
        if args[:4] == ('settings','--user','0','delete'):
            if not self.ignore_setting: self.value='null'
            return 'Deleted 1 rows'
        if args[:2] == ('pm','disable-user'):
            self.disabled.add(args[-1]); return 'new state: disabled-user'
        if args[:2] == ('pm','enable'):
            self.disabled.discard(args[-1]); return 'new state: enabled'
        raise AssertionError(args)
    def install(self, serial, apk):
        if self.before_install: self.before_install(apk)
        if len(self.installed)==self.fail_install: raise RuntimeError('install rejected')
        self.installed.append(Path(apk).name)
        return 'Success'
    def reboot(self, serial): self.commands.append(('reboot',))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.adb = FakeAdb()
        self.adbpatch = patch('open_fire_toolkit.service.AdbClient',return_value=self.adb)
        self.adbpatch.start()
        self.app = Toolkit(ToolConfig('adb','aapt','apksigner.jar','java'),state_dir=self.root/'state')
    def tearDown(self): self.adbpatch.stop(); self.temp.cleanup()
    def make_apks(self):
        result=[]
        for i,pkg in enumerate(('com.google.android.gsf','com.google.android.gms','com.android.vending')):
            p=self.root/f'{i}.apk';p.write_bytes(b'fake signed APK '+pkg.encode())
            result.append(ApkInfo(p,pkg,1,'1.0',23,(),file_sha256(p),(GOOGLE_SIGNER_SHA256,),False))
        return result
    def verifier(self, apks):
        by_hash={a.sha256:a for a in apks}
        def inspect(p):
            p=Path(p)
            return replace(by_hash[file_sha256(p)],path=p)
        return patch('open_fire_toolkit.service.ApkVerifier',return_value=type('Verifier',(),{'inspect':staticmethod(inspect)})())
    def test_unconfirmed_plan_cannot_write(self):
        plan=self.app.plan_ads('SERIAL123')
        with self.assertRaises(ToolkitError): self.app.execute(plan)
        self.assertFalse(any('put' in c for c in self.adb.commands))

    def test_linked_state_directory_is_refused_before_ads_write(self):
        destination = self.root / 'outside'
        destination.mkdir()
        try:
            self.app.state_dir.symlink_to(destination, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Directory symlinks unavailable')
        with self.assertRaises((ToolkitError, OSError)):
            plan = self.app.plan_ads('SERIAL123')
            self.app.execute(plan, True)
        self.assertEqual(self.adb.value, '1')
        self.assertEqual(list(destination.iterdir()), [])

    @unittest.skipUnless(os.name == 'posix', 'Windows holds directory handles without delete sharing')
    def test_displaced_operation_directory_stops_ads_before_mutation(self):
        plan = self.app.plan_ads('SERIAL123')
        folder = self.app.state_dir
        retired = folder.with_name('retired')
        read_ads = self.app._read_ads
        def read_and_rotate(serial):
            if not retired.exists():
                self.assertTrue((folder / 'operation.lock').exists())
                # The lock owner keeps its handle as another process rotates the directory.
                subprocess.run([sys.executable, '-c',
                                'import os,sys; os.rename(sys.argv[1], sys.argv[2]); os.mkdir(sys.argv[1])',
                                str(folder), str(retired)], check=True, timeout=10)
            return read_ads(serial)
        with patch.object(self.app, '_read_ads', side_effect=read_and_rotate):
            with self.assertRaisesRegex(ToolkitError, 'directory changed'):
                self.app.execute(plan, True)
        self.assertEqual(self.adb.value, '1')
        self.assertEqual(list(folder.iterdir()), [])
        self.assertFalse((retired / 'operation.lock').exists())

    @unittest.skipUnless(os.name == 'posix', 'Windows holds directory handles without delete sharing')
    def test_all_journals_reject_a_different_directory_while_executing(self):
        plan = self.app.plan_ads('SERIAL123')
        folder = self.app.state_dir
        def inspect_journal_boundaries(_):
            folder.rename(folder.with_name('retired'))
            folder.mkdir()
            for reader, args in ((self.app._load_state, ()), (self.app._pkg_undo_record, (plan.device,)),
                                 (self.app._device_undo, (plan.device,)), (self.app._private_dns_state, (plan.device,))):
                with self.subTest(reader=reader.__name__), self.assertRaisesRegex(ToolkitError, 'directory changed'):
                    reader(*args)
            self.app._writable_device(plan.serial)
        with patch.object(self.app, '_apply_ads', side_effect=inspect_journal_boundaries):
            with self.assertRaisesRegex(ToolkitError, 'directory changed'):
                self.app.execute(plan, True)
        self.assertEqual(list(folder.iterdir()), [])

    def test_lock_recovery_message_names_persistent_state_path(self):
        self.app.state_dir.mkdir()
        lock = self.app.state_dir / 'operation.lock'
        lock.write_text('old process')
        plan = self.app.plan_ads('SERIAL123')
        with self.assertRaises(ToolkitError) as error:
            self.app.execute(plan, True)
        self.assertIn(str(lock), str(error.exception))
        self.assertNotIn('/proc/', str(error.exception))
        self.assertTrue(lock.exists())
    def test_ads_suppress_repeat_restore_keeps_original(self):
        for _ in range(2): self.app.execute(self.app.plan_ads('SERIAL123'),True,log=lambda x:None)
        self.assertEqual(self.adb.value,'0')
        self.app.execute(self.app.plan_ads('SERIAL123',restore=True),True,log=lambda x:None)
        self.assertEqual(self.adb.value,'1')
        with self.assertRaises(ToolkitError): self.app.plan_ads('SERIAL123',restore=True)
    def test_absent_setting_restores_by_delete(self):
        self.adb.value='null'
        self.app.execute(self.app.plan_ads('SERIAL123'),True,log=lambda x:None)
        self.app.execute(self.app.plan_ads('SERIAL123',True),True,log=lambda x:None)
        self.assertEqual(self.adb.value,'null')
    def paired_fixture(self, mode='0', value='null'):
        self.adb.kso_mode = mode
        self.adb.value = value
        self.adb.kso_denied = False
        adb_shell = self.adb.shell
        pkg = 'com.amazon.kindle.kso'
        modes = ('default-state', 'enable', 'disable', 'disable-user', 'disable-until-used')
        def shell(serial, args, timeout=30):
            if tuple(args) == ('dumpsys', 'package', pkg):
                return f'  User 0: installed=true stopped=false enabled={self.adb.kso_mode}\n  User 10: installed=true enabled=1'
            if args[0] == 'pm' and args[-1] == pkg:
                self.assertEqual(tuple(args[2:4]), ('--user', '0'))
                self.adb.commands.append(tuple(args))
                if self.adb.kso_denied:
                    return 'Error: Permission Denial'
                self.adb.kso_mode = str(modes.index(args[1]))
                return 'Success'
            return adb_shell(serial, args, timeout)
        self.adb.shell = shell

    def paired(self, restore=False):
        return self.app.plan_ads('SERIAL123', restore=restore, paired=True)

    def apply(self, plan):
        return self.app.execute(plan, True, log=lambda _: None)

    def test_paired_restore_preserves_absent_key_and_default_package_mode(self):
        self.paired_fixture()
        self.apply(self.paired())
        self.assertEqual((self.adb.value, self.adb.kso_mode), ('0', '3'))
        self.apply(self.paired())
        self.apply(self.paired(True))
        self.assertEqual((self.adb.value, self.adb.kso_mode), ('null', '0'))
        self.assertFalse(any('clear' in cmd or 'grant' in cmd for cmd in self.adb.commands))
        with self.assertRaises(ToolkitError):
            self.paired(True)

    def test_paired_preview_explains_v46_restricted_firmware(self):
        self.paired_fixture()
        for version, restricted in (('8.3.3.7', False), ('8.3.3.8', True), ('8.3.12.0', True),
                                    ('7.3.3.8', False), ('unknown', False)):
            self.adb.identity = info(fire_os=version)
            with self.subTest(version=version):
                self.assertEqual('v46' in ' '.join(self.paired().warnings), restricted)

    def test_paired_restore_keeps_previously_disabled_special_offers_disabled(self):
        self.paired_fixture('2', '1')
        self.apply(self.paired())
        self.apply(self.paired(True))
        self.assertEqual((self.adb.value, self.adb.kso_mode), ('1', '2'))
        self.assertFalse(any(cmd[0]=='pm' for cmd in self.adb.commands))

    def test_paired_partial_package_denial_survives_restart_and_allows_undo(self):
        self.paired_fixture('1', '1')
        self.adb.kso_denied = True
        with self.assertRaisesRegex(ToolkitError, 'Completed:'):
            self.apply(self.paired())
        self.assertEqual((self.adb.value, self.adb.kso_mode), ('0', '1'))
        self.app = Toolkit(self.app.config, state_dir=self.app.state_dir)
        self.apply(self.paired(True))
        self.assertEqual((self.adb.value, self.adb.kso_mode), ('1', '1'))

    def test_completing_paired_undo_requires_both_confirmed_settings(self):
        self.paired_fixture('1', '1')
        self.apply(self.paired())
        write = self.adb.shell
        def reset_setting(serial, args, timeout=30):
            result = write(serial, args, timeout)
            if args[:2] == ('pm', 'enable'):
                self.adb.value = '0'
            return result
        self.adb.shell = reset_setting
        with self.assertRaisesRegex(ToolkitError, 'confirm'):
            self.apply(self.paired(True))
        self.apply(self.paired(True))
        self.assertEqual((self.adb.value, self.adb.kso_mode), ('1', '1'))

    def test_paired_undo_with_an_older_setting_only_undo(self):
        self.paired_fixture('1', '1')
        self.apply(self.app.plan_ads('SERIAL123'))
        stale_single = self.app.plan_ads('SERIAL123', restore=True)
        self.apply(self.paired())
        with self.assertRaisesRegex(ToolkitError, '[Pp]aired'):
            self.apply(stale_single)
        self.apply(self.paired(True))
        self.assertEqual((self.adb.value, self.adb.kso_mode), ('0', '1'))
        self.apply(self.app.plan_ads('SERIAL123', restore=True))
        self.assertEqual(self.adb.value, '1')

    def test_paired_refuses_changed_setting_before_first_command(self):
        self.paired_fixture('1', '1')
        plan = self.paired()
        read = self.app._offers_mode
        def change_while_reading(serial):
            self.adb.value = '2'
            return read(serial)
        with patch.object(self.app, '_offers_mode', side_effect=change_while_reading):
            with self.assertRaisesRegex(ToolkitError, '[Cc]hanged'):
                self.apply(plan)
        self.assertEqual((self.adb.value, self.adb.kso_mode), ('2', '1'))
        self.assertFalse(any(cmd[0] == 'pm' or 'put' in cmd for cmd in self.adb.commands))
        self.assertNotIn(self.app._state_key('SERIAL123'), self.app._load_state().get('paired_ads', {}))

    def test_paired_refuses_uninstalled_and_ambiguous_owner_records(self):
        for report in ('Unknown package', '  User 0: installed=false enabled=0',
                       '  User 0: installed=true enabled=0 enabled=1'):
            with self.subTest(report=report), patch.object(self.app, '_pkg_shell', return_value=report):
                with self.assertRaises(ToolkitError):
                    self.paired()
        self.assertFalse(self.app.state_dir.exists())

    def test_paired_preview_rejects_changed_mode_and_saved_setting(self):
        self.paired_fixture('0', '1')
        plan = self.paired()
        self.adb.kso_mode = '1'
        with self.assertRaises(ToolkitError):
            self.apply(plan)
        self.assertEqual(self.adb.value, '1')
        self.apply(self.paired())
        restore = self.paired(True)
        state = self.app._load_state()
        state['paired_ads'][self.app._state_key('SERIAL123')]['value'] = '2'
        self.app._save_state(state)
        with self.assertRaises(ToolkitError):
            self.apply(restore)
        self.assertEqual(self.adb.value, '0')

    def test_changed_device_refused_after_preview(self):
        plan=self.app.plan_ads('SERIAL123'); self.adb.identity=info(model='OTHER')
        with self.assertRaises(ToolkitError): self.app.execute(plan,True)
        self.assertEqual(self.adb.value,'1')
    def test_non_amazon_and_secondary_user_refused(self):
        for change in ({'manufacturer':'Other'},{'user_id':10}):
            self.adb.identity=info(**change)
            with self.assertRaises(ToolkitError): self.app.plan_ads('SERIAL123')
    def test_changed_setting_between_plan_and_execution_refused(self):
        plan=self.app.plan_ads('SERIAL123');self.adb.value='2'
        with self.assertRaises(ToolkitError): self.app.execute(plan,True)
        self.assertEqual(self.adb.value,'2')
    def test_failed_readback_is_not_reported_as_success(self):
        self.adb.ignore_setting=True
        with self.assertRaises(ToolkitError): self.app.execute(self.app.plan_ads('SERIAL123'),True)
    def test_unknown_setting_refused(self):
        self.adb.value='Permission denied'
        with self.assertRaises(ToolkitError):self.app.plan_ads('SERIAL123')
    def test_legacy_package_rejection_is_excluded_from_accepted_progress(self):
        plan = self.app.plan_package('SERIAL123', 'com.amazon.kindle')
        with patch.object(self.adb, 'shell', return_value='Failure [Permission Denial]'):
            with self.assertRaises(ToolkitError) as error:
                self.app.execute(plan, True)
        self.assertIn('Permission Denial', str(error.exception))
        self.assertNotIn('Android accepted', str(error.exception))

    def test_protected_package_refused(self):
        for name in ('com.amazon.firelauncher','com.android.settings','com.amazon.device.software.ota','x;reboot'):
            with self.assertRaises(ToolkitError): self.app.plan_package('SERIAL123',name)
    def test_disable_and_enable_optional_app(self):
        pkg=next(iter(OPTIONAL_APPS))
        self.app.execute(self.app.plan_package('SERIAL123',pkg),True,log=lambda x:None)
        self.assertIn(pkg,self.adb.disabled)
        self.app.execute(self.app.plan_package('SERIAL123',pkg,True),True,log=lambda x:None)
        self.assertNotIn(pkg,self.adb.disabled)
    def test_google_play_inspects_all_before_installing_staged_files(self):
        apks=self.make_apks()
        with self.verifier(apks):
            plan=self.app.plan_google_play('SERIAL123',[a.path for a in reversed(apks)])
            self.assertEqual(len(self.adb.installed),0)
            self.app.execute(plan,True,log=lambda x:None)
        self.assertEqual(len(self.adb.installed),3)
    def test_google_play_sync_validates_dependencies_and_enables_only_selected_provider(self):
        core = self.make_apks()
        provider = 'com.android.providers.contacts'
        calendar = 'com.android.providers.calendar'
        sync_path = self.root / 'contacts.apk'
        sync_path.write_bytes(b'contacts')
        sync = replace(core[0], package='com.google.android.syncadapters.contacts',
                       path=sync_path, sha256=file_sha256(sync_path))
        self.adb.present.update((provider, calendar, *(apk.package for apk in core)))
        self.adb.disabled.update((provider, calendar))
        with self.verifier([sync]):
            self.adb.disabled.add(core[0].package)
            with self.assertRaisesRegex(ToolkitError, 'Framework|com.google.android.gsf'):
                self.app.plan_google_play('SERIAL123', [sync_path])
            self.adb.disabled.remove(core[0].package)
            plan = self.app.plan_google_play('SERIAL123', [sync_path])
            self.assertTrue(any(provider in line and 'Enable' in line for line in plan.details))
            self.adb.disabled.discard(provider)
            with self.assertRaisesRegex(ToolkitError, 'changed'):
                self.app.execute(plan, True, log=lambda _message: None)
            self.assertEqual(self.adb.installed, [])
            self.adb.disabled.add(provider)
            self.app.execute(plan, True, log=lambda _message: None)
        self.assertEqual(self.adb.installed, ['00.apk'])
        self.assertNotIn(provider, self.adb.disabled)
        self.assertIn(calendar, self.adb.disabled)

    def test_sync_apk_preflight_refuses_missing_provider_even_in_complete_batch(self):
        core = self.make_apks()
        sync_path = self.root / 'calendar.apk'
        sync_path.write_bytes(b'calendar')
        sync = replace(core[0], package='com.google.android.syncadapters.calendar',
                       path=sync_path, sha256=file_sha256(sync_path))
        with self.verifier([*core, sync]), self.assertRaisesRegex(ToolkitError, 'com.android.providers.calendar'):
            self.app.plan_google_play('SERIAL123', [*(a.path for a in core), sync_path])
        self.assertEqual(self.adb.installed, [])

    def test_apk_change_after_preview_blocks_all_installs(self):
        apks=self.make_apks()
        with self.verifier(apks):
            plan=self.app.plan_google_play('SERIAL123',[a.path for a in apks])
            apks[0].path.write_bytes(b'tampered')
            with self.assertRaises(ToolkitError):self.app.execute(plan,True)
        self.assertEqual(self.adb.installed,[])
    def test_partial_install_stops_with_factual_completed_list(self):
        apks=self.make_apks();self.adb.fail_install=1
        with self.verifier(apks):
            plan=self.app.plan_google_play('SERIAL123',[a.path for a in apks])
            with self.assertRaises(ToolkitError) as cm:self.app.execute(plan,True,log=lambda x:None)
        self.assertEqual(len(self.adb.installed),1)
        self.assertIn('com.google.android.gsf',str(cm.exception))
        self.assertIn('not rolled back',str(cm.exception))
    def test_mutation_lock_refuses_parallel_operation(self):
        plan=self.app.plan_ads('SERIAL123')
        self.app._operation_lock.acquire()
        try:
            with self.assertRaises(ToolkitError):self.app.execute(plan,True)
        finally:self.app._operation_lock.release()
    def test_foreign_plan_serial_is_refused(self):
        plan=replace(self.app.plan_ads('SERIAL123'),serial='OTHER')
        with self.assertRaises(ToolkitError):self.app.execute(plan,True)
    def test_missing_model_refused_for_writes(self):
        self.adb.identity=info(model='')
        with self.assertRaises(ToolkitError):self.app.plan_ads('SERIAL123')
    def test_package_disappears_after_enable_is_not_success(self):
        pkg=next(iter(OPTIONAL_APPS));self.adb.disabled.add(pkg)
        plan=self.app.plan_package('SERIAL123',pkg,True)
        original=self.adb.shell
        def disappear(serial,args,timeout=30):
            result=original(serial,args,timeout)
            if args[:2]==('pm','enable'):self.adb.present.discard(pkg)
            return result
        self.adb.shell=disappear
        with self.assertRaises(ToolkitError):self.app.execute(plan,True)
    def test_oversized_changed_apk_is_rejected_before_copy(self):
        apks=self.make_apks()
        with self.verifier(apks):
            plan=self.app.plan_google_play('SERIAL123',[a.path for a in apks])
            with apks[0].path.open('wb') as stream:stream.truncate(512*1024*1024+1)
            with patch('pathlib.Path.open', side_effect=AssertionError('must reject before copy')):
                with self.assertRaisesRegex(ToolkitError,'512 MiB'):self.app.execute(plan,True)
        self.assertEqual(self.adb.installed,[])
    def test_restore_cannot_use_a_different_saved_target_than_preview(self):
        self.app.execute(self.app.plan_ads('SERIAL123'),True,log=lambda x:None)
        plan=self.app.plan_ads('SERIAL123',restore=True)
        state=self.app._load_state();state['ads'][self.app._state_key('SERIAL123')]['value']='2'
        self.app._save_state(state)
        with self.assertRaisesRegex(ToolkitError,'saved.*changed'):self.app.execute(plan,True)
        self.assertEqual(self.adb.value,'0')
    def test_later_owner_check_error_reports_partial_install(self):
        apks=self.make_apks()
        def change_user(apk):self.adb.identity=info(user_id=10)
        self.adb.before_install=change_user
        with self.verifier(apks):
            plan=self.app.plan_google_play('SERIAL123',[a.path for a in apks])
            with self.assertRaises(ToolkitError) as cm:self.app.execute(plan,True,log=lambda x:None)
        self.assertIn('Installed com.google.android.gsf',str(cm.exception))
        self.assertIn('not rolled back',str(cm.exception))
        self.assertEqual(len(self.adb.installed),1)
    def test_unreadable_setting_after_write_reports_possible_change(self):
        plan=self.app.plan_ads('SERIAL123');original=self.adb.shell
        def unreadable_after_write(serial,args,timeout=30):
            result=original(serial,args,timeout)
            if 'put' in args:self.adb.value='Permission denied'
            return result
        self.adb.shell=unreadable_after_write
        with self.assertRaises(ToolkitError) as cm:self.app.execute(plan,True)
        self.assertIn('command was issued',str(cm.exception))
        self.assertNotIn('no changes were made',str(cm.exception))
    def test_failed_undo_cleanup_reports_restoration_already_done(self):
        self.app.execute(self.app.plan_ads('SERIAL123'),True,log=lambda x:None)
        plan=self.app.plan_ads('SERIAL123',True)
        with patch.object(self.app,'_save_state',side_effect=OSError('disk full')):
            with self.assertRaises(ToolkitError) as cm:self.app.execute(plan,True)
        self.assertEqual(self.adb.value,'1')
        self.assertIn('restored',str(cm.exception))
        self.assertIn('undo',str(cm.exception))
    def test_corrupt_state_does_not_get_silently_overwritten(self):
        self.app.state_dir.mkdir(parents=True,exist_ok=True)
        (self.app.state_dir/'state.json').write_text('not json')
        with self.assertRaises(ToolkitError):self.app.plan_ads('SERIAL123')
        self.assertEqual(self.adb.value,'1')

if __name__=='__main__': unittest.main()
