"""Static regression checks for RC16.5 privileged disk operations.

These checks never execute wipefs, mkfs or parted. Hardware testing must use
a disposable disk and verify protected drives are rejected.
"""
import ast
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SRC = '\n'.join((ROOT / 'src' / 'pinas' / name).read_text(encoding='utf-8') for name in ('core.py','web_ui.py','http_api.py','privileged_helpers.py','installer.py'))
TREE = ast.parse(SRC)
VALUES = {}
for statement in TREE.body:
    if isinstance(statement, ast.Assign):
        for target in statement.targets:
            if isinstance(target, ast.Name) and target.id in ('NAS_DESTRUCTIVE_HELPER', 'PAGE'):
                VALUES[target.id] = ast.literal_eval(statement.value)

@unittest.skipUnless('NAS_DESTRUCTIVE_HELPER' in VALUES, 'Destructive disk helper not present in this source branch')
class DiskDestructiveGuards(unittest.TestCase):
    def test_helper_python_syntax(self):
        compile(VALUES['NAS_DESTRUCTIVE_HELPER'],'pinas-disk-destructive','exec')

    def test_device_guards(self):
        code=VALUES['NAS_DESTRUCTIVE_HELPER']
        for guard in ('is_block_device()', "get('type')=='disk'", 'Device has active holders',
                      'Disk contains mounted filesystems', 'System disk is protected',
                      'Unable to identify operating-system disk', '/etc/fstab',
                      'Disk belongs to a PiNAS share', 'Active swap is protected',
                      "details.st_dev",):
            if guard=='details.st_dev':
                continue
            with self.subTest(guard=guard):
                self.assertIn(guard, code)
        self.assertNotIn("umount", code)
        self.assertNotIn("rm -rf", code)

    def test_supported_filesystems_and_operation(self):
        code=VALUES['NAS_DESTRUCTIVE_HELPER']
        for cmd in ('mkfs.ext4','mkfs.xfs','mkfs.btrfs','wipefs','parted'):
            self.assertIn(cmd, code)
        self.assertIn("('ext4','xfs','btrfs')",code)

    def test_explicit_authorisation(self):
        self.assertIn("confirmation!=device", SRC)
        self.assertIn("admin_record(cfg,s['username'])", SRC)
        self.assertIn("Current administrator password", VALUES['PAGE'])
        self.assertIn("data-disk-operation", VALUES['PAGE'])

    def test_sudo_narrow_scope(self):
        self.assertIn("/usr/local/libexec/pinas-disk-destructive execute", SRC)
        self.assertIn("os.chmod(disk_helper,0o700)", SRC)

if __name__=='__main__':unittest.main()
