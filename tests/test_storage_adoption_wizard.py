"""PiNAS v1.0.9 adoption flow regression checks (no actual disks modified)."""
import ast
import pathlib
import subprocess
import types
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
UI=(ROOT/'src/pinas/web_ui.py').read_text(encoding='utf-8')
HELPERS=(ROOT/'src/pinas/privileged_helpers.py').read_text(encoding='utf-8')
INSTALLER=(ROOT/'src/pinas/installer.py').read_text(encoding='utf-8')
PAGE=next(ast.literal_eval(n.value) for n in ast.parse(UI).body
          if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PAGE' for t in n.targets))
ADOPT=next(ast.literal_eval(n.value) for n in ast.parse(HELPERS).body
           if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='NAS_STORAGE_HELPER' for t in n.targets))

class StorageAdoptionRegression(unittest.TestCase):
    def test_helper_syntax(self):
        compile(ADOPT,'pinas-nas-storage','exec')

    def test_command_failure_reports_executed_command_and_code(self):
        ns={'__name__':'pinas_adoption_test'}
        exec(compile(ADOPT,'pinas-nas-storage','exec'),ns)
        fake=subprocess.CompletedProcess(args=['mount','/mnt/test'],returncode=32,stdout='',stderr='')
        with mock.patch.object(ns['subprocess'],'run',return_value=fake):
            with self.assertRaisesRegex(ValueError,r'mount failed .exit 32.:'):
                ns['run']('mount','/mnt/test')

    def test_optional_boot_mounts_are_not_fatal(self):
        self.assertIn("probe.returncode not in (0,1)",ADOPT)
        self.assertIn("if probe.returncode:continue",ADOPT)
        self.assertIn("'--mountpoint',mount",ADOPT)
        self.assertNotIn("'--target',mount",ADOPT)

    def test_new_filesystem_is_probed_without_stale_cache(self):
        self.assertIn("run('blkid','-p','-s','TYPE','-o','value',device)",ADOPT)
        self.assertIn("run('blkid','-p','-s','UUID','-o','value',device)",ADOPT)
        self.assertIn("'--mountpoint',str(target)",ADOPT)

    def test_ui_keeps_wizard_open_until_adoption_succeeds(self):
        start=PAGE.index('function openDiskWizard(index){')
        end=PAGE.index('async function readPinasServiceInstance()',start)
        wizard=PAGE[start:end]
        self.assertIn("renderMountOptions();",wizard)
        self.assertIn("if(action==='format'){",wizard)
        self.assertIn("mountOptions.classList.remove('hidden')",wizard)
        self.assertIn("Disk formatted. Choose Adopt without formatting below",wizard)
        self.assertIn("Disk wiped. Choose Format Disk",wizard)
        self.assertIn("const renderMountOptions=function renderMountOptions()",wizard)
        self.assertIn("const result=await post('/api/storage'",wizard)
        self.assertIn("diskMessage.textContent='Storage mounted at '+result.mount;",wizard)
        destructive=wizard[wizard.index("const result=await post('/api/disk-destructive'"):wizard.index("}catch(error){",wizard.index("const result=await post('/api/disk-destructive'"))]
        self.assertNotIn("close();",destructive)
        self.assertNotIn("render();",destructive)

    def test_web_update_refreshes_privileged_adoption_helper(self):
        expand=INSTALLER[:INSTALLER.index('def install_privileged_helper(')]
        self.assertIn("('pinas-nas-storage',NAS_STORAGE_HELPER,[\"adopt\"])",expand)
        self.assertIn("for name,source,allowed in specifications:",expand)

if __name__=='__main__':
    unittest.main()
