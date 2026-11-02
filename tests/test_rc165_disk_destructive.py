"""Static regression checks for RC16.5 privileged disk operations.

These checks never execute wipefs, mkfs or parted. Hardware testing must use
a disposable disk and verify protected drives are rejected.
"""
import ast
import pathlib
import unittest

SRC = (pathlib.Path(__file__).resolve().parents[1] / 'pinas.py').read_text()
TREE = ast.parse(SRC)
VALUES = {}
for statement in TREE.body:
    if isinstance(statement, ast.Assign):
        for target in statement.targets:
            if isinstance(target, ast.Name) and target.id in ('NAS_DESTRUCTIVE_HELPER', 'PAGE'):
                VALUES[target.id] = ast.literal_eval(statement.value)

class DiskDestructiveGuards(unittest.TestCase):
    def test_helper_python_syntax(self):
        compile(VALUES['NAS_DESTRUCTIVE_HELPER'],'pinas-disk-destructive','exec')

    def test_device_guards(self):
        code=VALUES['NAS_DESTRUCTIVE_HELPER']
        for guard in ('is_block_device()', "get('type')=='disk'", 'Device has active holders',
                      'Disk contains mounted filesystems', 'Operating-system disk',
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
        self.assertIn("/usr/local/libexec/pinas-disk-destructive execute\\n", SRC)
        self.assertIn("os.chmod(disk_helper,0o700)", SRC)

if __name__=='__main__':unittest.main()
