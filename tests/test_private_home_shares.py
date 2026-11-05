"""v1.0.10: private NAS home shares and explicit legacy directory migration."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'src/pinas/core.py').read_text()
API=(ROOT/'src/pinas/http_api.py').read_text()
PAGE_SOURCE=(ROOT/'src/pinas/web_ui.py').read_text()
INSTALLER=(ROOT/'src/pinas/installer.py').read_text()

def literal(source,name):
    tree=ast.parse(source)
    return next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets))

SHARES=literal(API,'NAS_SHARE_HELPER')
FILES=literal(API,'NAS_FILES_HELPER')
PAGE=literal(PAGE_SOURCE,'PAGE')

class PrivateHomeShareTests(unittest.TestCase):
    def test_helpers_compiled(self):
        compile(SHARES,'nas-share-helper','exec')
        compile(FILES,'nas-files-helper','exec')

    def test_new_shares_use_lowercase_directory(self):
        self.assertIn("root=mount/'pinas-shares'",SHARES)
        self.assertIn("root.mkdir(mode=0o711,exist_ok=True)",SHARES)
        self.assertIn("folder.mkdir(mode=0o700)",SHARES)
        self.assertIn("valid users = ",SHARES)
        self.assertIn("run(['/usr/bin/setfacl','-m'",SHARES)

    def test_old_paths_preserved_and_authorized(self):
        self.assertIn("item.get('folder') or str(mount/'PiNAS Shares'/name)",SHARES)
        self.assertIn("folder.parent not in (mount/'PiNAS Shares',mount/'pinas-shares')",SHARES)
        self.assertIn("root=pathlib.Path(s.get('folder') or str(mount/'PiNAS Shares'/s['name']))",FILES)
        self.assertIn("root.parent not in (mount/'PiNAS Shares',mount/'pinas-shares')",FILES)

    def test_home_share_security_and_api(self):
        self.assertIn("create_home=data.get('create_home_share',False)",API)
        self.assertIn("create_nas_share(username,home_volume,{username:'rw'})",API)
        self.assertIn("verify(admin_password,(admin_record(cfg,s['username']) or {}).get('password',''))",API)
        self.assertIn("and v.get('persistent') and v.get('mounts')",API)
        self.assertIn("'created_user':True",API)
        self.assertIn("create_home_share:homeCheck.checked",PAGE)
        self.assertIn("name=\"home_volume\"",PAGE)
        self.assertIn("name=\"admin_password\"",PAGE)
        self.assertIn("Create private home folder share",PAGE)

    def test_legacy_migration_is_explicit_and_refuses_overwrite(self):
        self.assertIn("if len(sys.argv)==2 and sys.argv[1]=='migrate':",SHARES)
        self.assertIn("if target_root.is_symlink() or target.exists() or target.is_symlink()",SHARES)
        self.assertIn("if any(point==str(legacy) or point.startswith(str(legacy)+'/')",SHARES)
        self.assertIn("legacy.rename(target)",SHARES)
        self.assertIn("target.rename(legacy)",SHARES)
        self.assertIn("if data.get('confirm')!='MOVE SHARE'",API)
        self.assertIn("migrate_nas_share(name)",API)
        self.assertIn("data-migrate-share",PAGE)
        self.assertIn("admin_password:password",PAGE)

    def test_installer_upgrade_updates_both_helpers(self):
        self.assertGreaterEqual(INSTALLER.count("install_privileged_helper('pinas-nas-share',NAS_SHARE_HELPER"),2)
        self.assertGreaterEqual(INSTALLER.count("install_privileged_helper('pinas-nas-files',NAS_FILES_HELPER"),2)

if __name__=='__main__':
    unittest.main()
