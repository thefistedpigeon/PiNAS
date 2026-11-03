"""RC16.5 deletion and reauthentication regression checks.

Run: python3 -m unittest discover -s tests -v
These static checks complement, but do not replace, filesystem integration tests.
"""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = '\n'.join((ROOT / 'src' / 'pinas' / name).read_text(encoding='utf-8') for name in ('core.py','web_ui.py','http_api.py','privileged_helpers.py','installer.py'))
TREE = ast.parse(SOURCE)
EMBEDDED = {}
for stmt in TREE.body:
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id in ("NAS_FILES_HELPER", "PAGE"):
                EMBEDDED[target.id] = ast.literal_eval(stmt.value)


class DestructiveOperationChecks(unittest.TestCase):
    def test_embedded_files_helper_compiles(self):
        compile(EMBEDDED["NAS_FILES_HELPER"], "NAS_FILES_HELPER", "exec")

    def test_delete_requires_password_before_dropping_privileges(self):
        code = EMBEDDED["NAS_FILES_HELPER"]
        auth = code.index("if action=='delete':")
        drop = code.index("drop(person)",auth)
        delete = code.index("base_stat=os.lstat(target)")
        self.assertLess(auth, drop)
        self.assertLess(drop, delete)
        self.assertIn("samba_hash(user)", code[auth:drop])
        self.assertIn("hmac.compare_digest", code[auth:drop])

    def test_recursion_has_protection(self):
        code = EMBEDDED["NAS_FILES_HELPER"]
        self.assertIn("if target==root:raise ValueError", code)
        self.assertIn("followlinks=False", code)
        self.assertIn("details.st_dev!=base_stat.st_dev", code)
        self.assertIn("count>10000", code)
        self.assertIn("stat.S_ISREG(details.st_mode)", code)

    def test_ui_uses_masked_password_dialog(self):
        page = EMBEDDED["PAGE"]
        self.assertIn("title:x.dir?'Delete folder and contents':'Delete file'", page)
        self.assertIn("confirmLabel:'Delete permanently',password:true", page)
        self.assertNotIn("confirm('Delete '+x.name", page)

    def test_admin_reauth_uses_logged_in_account(self):
        self.assertNotIn("verify(password,cfg.get('admin_password',''))", SOURCE)
        self.assertIn("admin_record(cfg,s['username'])", SOURCE)


if __name__ == "__main__":
    unittest.main()
