"""PiNAS v1.0.4 non-destructive configuration recovery checks."""
import ast
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src'/'pinas'

class ConfigurationRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns={'__name__':'pinas_config_recovery_test'}
        exec(compile((SOURCE/'core.py').read_text(encoding='utf-8'),str(SOURCE/'core.py'),'exec'),cls.ns)

    def test_export_excludes_credentials(self):
        ns=self.ns
        original_users,original_shares=ns['nas_user_list'],ns['nas_share_list']
        ns['nas_user_list']=lambda:[{'name':'alice','uid':'1001'}]
        ns['nas_share_list']=lambda:[{'name':'Photos','path':'/mnt/photos'}]
        try:
            backup=ns['configuration_backup']({
                'admin_user':'admin','admin_password':'SECRET_HASH',
                'additional_admins':{'admin2':{'password':'HASH2'}},
                'theme':'dark','font':14,'cpu_interval':5,'cpu_history':30,
                'session_timeout':10,'nas_display_names':{'alice':'Alice'},
                'login_background':'data:image/png;base64,SECRET',
            })
        finally:
            ns['nas_user_list'],ns['nas_share_list']=original_users,original_shares
        self.assertEqual(backup['format'],'pinas-configuration-v1')
        self.assertEqual(backup['restore_scope'],'settings-and-display-names-only')
        self.assertEqual(backup['settings']['theme'],'dark')
        self.assertEqual(backup['accounts'],['alice'])
        self.assertNotIn('SECRET',str(backup))
        self.assertNotIn('admin_password',str(backup))
        self.assertNotIn('login_background',str(backup))

    def test_restore_accepts_only_safe_options(self):
        validate=self.ns['validate_configuration_restore']
        backup={'format':'pinas-configuration-v1','restore_scope':'settings-and-display-names-only',
                'settings':{'theme':'light','font':12,'cpu_interval':5,'cpu_history':30,'session_timeout':5},
                'display_names':{'alice':'Alice'}}
        settings,names=validate(backup)
        self.assertEqual(settings['font'],12)
        self.assertEqual(names['alice'],'Alice')
        # Extra backup inventory never becomes config mutations.
        backup['shares']=[{'name':'should_not_be_recreated'}]
        self.assertEqual(validate(backup)[0],settings)
        for key,value in [('admin_password','hacked'),('font',999),('session_timeout',0),('theme','light-cb')]:
            with self.subTest(key=key):
                altered={**backup,'settings':{**backup['settings'],key:value}}
                with self.assertRaises(ValueError):validate(altered)

    def test_rejects_bad_formats_and_names(self):
        validate=self.ns['validate_configuration_restore']
        good={'format':'pinas-configuration-v1','restore_scope':'settings-and-display-names-only',
              'settings':{'theme':'light'},'display_names':{}}
        for candidate in ({**good,'format':'unknown'},
                          {**good,'display_names':{'bad user':'Name'}},
                          {**good,'display_names':{'alice':'\nmalicious'}},
                          {**good,'restore_scope':'restore-everything'}):
            with self.assertRaises(ValueError):validate(candidate)

    def test_api_requires_admin_and_password(self):
        src=(SOURCE/'http_api.py').read_text(encoding='utf-8')
        admin_guard=src.index("if s.get('role')!='admin':self.json({'error':'Administrator access required'},403);return")
        recovery=src.index("if path in ('/api/config-backup','/api/config-restore'):")
        self.assertLess(admin_guard,recovery)
        self.assertIn("verify(confirmation,(admin_record(cfg,s['username']) or {}).get('password',''))",src)
        self.assertIn("data.get('confirm')!='RESTORE SETTINGS'",src)
        self.assertIn("latest.update(settings)",src)
        self.assertNotIn("create_nas_share(name,volume",src[recovery:src.index("if path=='/api/settings':",recovery)])

    def test_installer_preserves_prior_file(self):
        src=(SOURCE/'installer.py').read_text(encoding='utf-8')
        self.assertIn("previous=target/'pinas.py.previous'",src)
        self.assertIn("os.replace(staged,existing)",src)
        self.assertIn("shutil.copy2(previous,existing)",src)

if __name__=='__main__':
    unittest.main()
