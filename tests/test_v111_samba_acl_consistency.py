"""PiNAS v1.1.1 Samba / POSIX ACL consistency regressions.

Static checks ensure the existing narrow privilege boundary is retained. No
system users, Samba configuration, ACLs or on-disk shares are modified.
"""
import ast
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'src/pinas/core.py').read_text()
API=(ROOT/'src/pinas/http_api.py').read_text()
WEB=(ROOT/'src/pinas/web_ui.py').read_text()
HELPER=ast.literal_eval(next(item.value for item in ast.parse(API).body
    if isinstance(item,ast.Assign)
    and any(isinstance(t,ast.Name) and t.id=='NAS_SHARE_HELPER' for t in item.targets)))
USER_HELPER=ast.literal_eval(next(item.value for item in ast.parse(API).body
    if isinstance(item,ast.Assign)
    and any(isinstance(t,ast.Name) and t.id=='NAS_USER_HELPER' for t in item.targets)))
FILE_HELPER=ast.literal_eval(next(item.value for item in ast.parse(API).body
    if isinstance(item,ast.Assign)
    and any(isinstance(t,ast.Name) and t.id=='NAS_FILES_HELPER' for t in item.targets)))

class PermissionsUnificationTests(unittest.TestCase):
    def test_linux_samba_user_identity_is_provisioned_together(self):
        self.assertIn("'/usr/sbin/useradd','--no-create-home'",USER_HELPER)
        self.assertIn("'/usr/bin/smbpasswd','-s','-a',name",USER_HELPER)
        self.assertIn("'/usr/bin/smbpasswd','-e',name",USER_HELPER)
        self.assertIn("'--gid','pinas-nas'",USER_HELPER)
        self.assertIn("'/usr/sbin/nologin'",USER_HELPER)

    def test_private_home_uses_same_share_and_acl_path(self):
        self.assertIn("create_nas_share(username,home_volume,{username:'rw'})",API)
        self.assertIn("valid users = ",HELPER)
        self.assertIn("write list = ",HELPER)
        self.assertIn("guest ok = no",HELPER)
        self.assertIn("inherit acls = yes",HELPER)
        self.assertIn("if not pathlib.Path('/usr/bin/setfacl').exists()",HELPER)

    def test_public_shares_never_grant_world_writable_filesystem_access(self):
        self.assertNotIn("os.chmod(folder,0o777",HELPER)
        self.assertNotIn("os.chmod(folder,0o777 if public",HELPER)
        self.assertGreaterEqual(HELPER.count("os.chmod(folder,0o700)"),2)
        self.assertIn("'u:nobody:'+('rwx' if public_write else 'r-x')",HELPER)
        self.assertIn("guest only = yes",HELPER)
        self.assertIn("force user = nobody",HELPER)

    def test_share_edits_synchronize_existing_data_automatically(self):
        self.assertIn("def edit_with_acl_sync():",API)
        self.assertIn("edit_nas_share(name,new_name,access,public,public_write)",API)
        self.assertIn("privileged_command('pinas-nas-share','repair'",API)
        self.assertIn("start_job(token,'share-edit-acl',edit_with_acl_sync)",API)
        self.assertIn("Linux ACLs are updated together",WEB)
        self.assertNotIn('name="repair_existing"',WEB)

    def test_repair_removes_stale_grants_and_reapplies_policy(self):
        self.assertIn("managed=sorted(set(managed)|set(access)|{'nobody'})",HELPER)
        self.assertIn("'/usr/bin/setfacl','-R','-P','-x',remove",HELPER)
        self.assertIn("'/usr/bin/setfacl','-R','-P','-m','g::---,o::---,'+",HELPER)
        self.assertIn("'/usr/bin/find',str(folder),'-xdev','-type','d'",HELPER)
        self.assertIn("entry.replace('X','x')",HELPER)
        self.assertIn("if any(point==str(folder)",HELPER)
        self.assertNotIn("os.chmod(folder,0o777",HELPER)
        self.assertIn("run(['/usr/bin/testparm','-s'])",HELPER)
        self.assertIn("run(['/usr/bin/systemctl','reload','smbd'])",HELPER)


    def test_non_pinas_samba_accounts_are_excluded_from_nas_identity(self):
        scope={'__name__':'pinas_user_helper_regression'}
        exec(compile(USER_HELPER,'pinas-nas-user','exec'),scope)
        users={'alice':SimpleNamespace(pw_gid=771,pw_shell='/usr/sbin/nologin',pw_uid=1001),
               'external':SimpleNamespace(pw_gid=332,pw_shell='/usr/sbin/nologin',pw_uid=1002),
               'shelluser':SimpleNamespace(pw_gid=771,pw_shell='/bin/bash',pw_uid=1003)}
        with patch.object(scope['grp'],'getgrnam',return_value=SimpleNamespace(gr_gid=771)), \
             patch.object(scope['pwd'],'getpwnam',side_effect=lambda name:users[name]):
            scope['run']=lambda *args,**kwargs:SimpleNamespace(
                stdout='alice:1001:\nexternal:1002:\nshelluser:1003:\n')
            result=scope['samba_users']()
        self.assertEqual(result,[{'name':'alice','uid':'1001'}])

    def test_web_file_broker_enforces_same_managed_linux_identity(self):
        scope={'__name__':'pinas_file_helper_regression'}
        exec(compile(FILE_HELPER,'pinas-nas-files','exec'),scope)
        self.assertIn("person.pw_gid!=nas_gid",FILE_HELPER)
        with patch.object(scope['grp'],'getgrnam',return_value=SimpleNamespace(gr_gid=771)), \
             patch.object(scope['pwd'],'getpwnam',return_value=SimpleNamespace(
                 pw_gid=332,pw_shell='/usr/sbin/nologin')):
            with self.assertRaisesRegex(ValueError,'PiNAS-managed'):
                scope['valid_user']('external')

    def test_restricted_helper_and_version(self):
        compile(HELPER,'pinas-nas-share','exec')
        compile(USER_HELPER,'pinas-nas-user','exec')
        compile(FILE_HELPER,'pinas-nas-files','exec')
        self.assertRegex(CORE,r"VERSION='1\.1\.[12]'")
        self.assertIn("fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)",HELPER)

if __name__=='__main__':
    unittest.main()
