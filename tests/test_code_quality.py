"""Maintainability invariants for the PiNAS standalone release."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "pinas"

class CodeQualityChecks(unittest.TestCase):
    def test_sources_parse(self):
        for path in sorted(SOURCE.glob("*.py")):
            with self.subTest(source=path.name):
                ast.parse(path.read_text(encoding="utf-8"))

    def test_generated_release_matches_sources(self):
        tree=ast.parse((ROOT / "pinas.py").read_text(encoding="utf-8"))
        parts=next(ast.literal_eval(n.value) for n in tree.body
                   if isinstance(n,ast.Assign)
                   and any(isinstance(t,ast.Name) and t.id=="PINAS_SOURCE_PARTS"
                           for t in n.targets))
        for name, content in parts.items():
            with self.subTest(module=name):
                self.assertEqual(content, (SOURCE / name).read_text(encoding="utf-8"))

    def test_single_shared_stylesheet_and_supported_themes(self):
        tree=ast.parse((SOURCE / "web_ui.py").read_text(encoding="utf-8"))
        page=next(ast.literal_eval(n.value) for n in tree.body
                  if isinstance(n,ast.Assign)
                  and any(isinstance(t,ast.Name) and t.id=="PAGE"
                          for t in n.targets))
        self.assertEqual(page.count("<style>"),1)
        self.assertEqual(page.count("</style>"),1)
        self.assertNotIn("light-cb",page)
        self.assertNotIn("dark-cb",page)
        self.assertIn('class="card section-spaced"',page)
        self.assertIn('class="btn outline button-with-icon"',page)
        self.assertNotIn('style="margin-top:16px"',page)

    def test_privileged_broker_and_registration_are_central(self):
        core=(SOURCE / "core.py").read_text(encoding="utf-8")
        installer=(SOURCE / "installer.py").read_text(encoding="utf-8")
        self.assertIn("def privileged_command(",core)
        self.assertIn("def install_privileged_helper(",installer)
        self.assertIn("privileged_command('pinas-nas-files'",core)
        self.assertIn("install_privileged_helper('pinas-nas-user'",installer)

if __name__ == "__main__":
    unittest.main()
