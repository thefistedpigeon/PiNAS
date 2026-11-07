"""Static regression checks for PiNAS's single-file distribution.

Run: python3 -m unittest discover -s tests -v
Node.js is optional; when available it also parses the embedded UI JavaScript.
"""
import ast
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "pinas.py"


class SingleFileRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = '\n'.join((SOURCE.parent / 'src' / 'pinas' / name).read_text(encoding='utf-8') for name in ('core.py','web_ui.py','storage_breakdown.py','http_api.py','privileged_helpers.py','media_server.py','installer.py'))
        cls.tree = ast.parse(cls.source, filename=str(SOURCE))
        cls.constants = {}
        for node in cls.tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {
                        "PAGE", "HOSTNAME_HELPER", "NAS_USER_HELPER", "SMB_RESET_HELPER",
                        "NAS_SHARE_HELPER", "NAS_FILES_HELPER", "APT_INDEX_HELPER",
                        "SMART_HEALTH_HELPER"
                    }:
                        cls.constants[target.id] = ast.literal_eval(node.value)

    def test_embedded_helpers_compile(self):
        for name, source in self.constants.items():
            if name.endswith("_HELPER"):
                with self.subTest(helper=name):
                    compile(source, name, "exec")

    def test_page_has_single_style_and_script(self):
        page = self.constants["PAGE"]
        self.assertEqual(page.count("<style>"), 1)
        self.assertEqual(page.count("</style>"), 1)
        self.assertEqual(page.count("<script>"), 1)
        self.assertEqual(page.count("</script>"), 1)

    def test_admin_confirmation_and_contrast(self):
        page = self.constants["PAGE"]
        self.assertIn("share-remove-confirm", page)
        self.assertIn("background:#b72b3c!important", page)
        self.assertIn("color:#fff!important", page)
        self.assertIn("smb-reset-password", page)
        self.assertNotIn("confirm('Reset Samba configuration?", page)

    def test_public_permissions_guarded(self):
        helper = self.constants["NAS_SHARE_HELPER"]
        self.assertNotIn("os.chmod(folder,0o777", helper)
        self.assertIn("os.chmod(folder,0o700)", helper)
        self.assertIn("'u:nobody:'+('rwx' if public_write else 'r-x')", helper)

    @unittest.skipUnless(shutil.which("node"), "Node.js not installed")
    def test_embedded_javascript_syntax(self):
        script = re.search(r"<script>(.*?)</script>", self.constants["PAGE"], re.S)
        self.assertIsNotNone(script)
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "pinas-ui.js"
            path.write_text(script.group(1), encoding="utf-8")
            result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
