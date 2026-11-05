"""Current privileged storage destruction guard regressions.

Never run a destructive command against a real device.
"""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'src/pinas/privileged_helpers.py').read_text()
API=(ROOT/'src/pinas/http_api.py').read_text()
UI=(ROOT/'src/pinas/web_ui.py').read_text()
INSTALL=(ROOT/'src/pinas/installer.py').read_text()
def literal(name):
    for node in ast.parse(SOURCE).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError('Missing '+name)
class DiskDestructiveGuards(unittest.TestCase):
    def test_actual_disk_erase_helper_compiles(self):
        compile(literal('NAS_DISK_ERASE_HELPER'),'pinas-disk-erase','exec')
    def test_enforces_block_device_and_system_disk_protection(self):
        helper=literal('NAS_DISK_ERASE_HELPER')
        for token in ('is_block_device()', 'wipefs', 'mkfs', '/etc/fstab', 'mount'):
            with self.subTest(token=token):self.assertIn(token,helper)
    def test_explicit_admin_confirmation_and_narrow_sudo(self):
        self.assertIn("if path=='/api/disk-destructive':",API)
        self.assertIn("admin_record(cfg,s['username'])",API)
        self.assertIn('disk-danger-password',UI)
        self.assertIn("install_privileged_helper('pinas-disk-erase'",INSTALL)
if __name__=='__main__':unittest.main()
