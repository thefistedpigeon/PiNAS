"""v1.0.5: read-only managed disk status and storage preflight regression tests."""
import pathlib
import types
import unittest

SOURCE=pathlib.Path(__file__).resolve().parents[1]/'src'/'pinas'

class StorageSafetyChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scope={'__name__':'pinas_storage_safety_test'}
        exec(compile((SOURCE/'core.py').read_text(encoding='utf-8'),str(SOURCE/'core.py'),'exec'),cls.scope)

    def check_mount(self,device_present=True,mounted=True,actual='12345678-abcd',fstab=None):
        scope=self.scope
        defaults=[
            'UUID=12345678-abcd /mnt/pinas/12345678-abcd ext4 defaults 0 2 # PiNAS managed',
            'UUID=87654321-abcd /mnt/other ext4 defaults 0 2 # PiNAS managed',
            'UUID=87654321-abcd /mnt/pinas/87654321-abcd ext4 defaults 0 2',
            '/dev/mmcblk0p2 / ext4 defaults 0 1',
        ]
        lines=defaults if fstab is None else fstab
        class FakePath:
            def __init__(self,part):self.part=part
            def read_text(self):return '\n'.join(lines)
            def __truediv__(self,part):return FakePath(self.part+'/'+part)
            def exists(self):return device_present
        old={key:scope[key] for key in ('Path','os','command')}
        try:
            scope['Path']=FakePath
            scope['os']=types.SimpleNamespace(path=types.SimpleNamespace(ismount=lambda path:mounted))
            scope['command']=lambda *args,**kwargs:actual
            return scope['managed_storage_health']()
        finally:
            scope.update(old)

    def test_mounted_managed_disk_is_healthy(self):
        self.assertEqual(self.check_mount()[0]['state'],'mounted')
        self.assertEqual(len(self.check_mount()),1)

    def test_missing_disk_is_reported(self):
        self.assertEqual(self.check_mount(device_present=False)[0]['state'],'missing')

    def test_present_but_not_mounted_is_reported(self):
        self.assertEqual(self.check_mount(mounted=False)[0]['state'],'unmounted')

    def test_mounted_wrong_disk_is_flagged(self):
        self.assertEqual(self.check_mount(actual='different-uuid')[0]['state'],'mismatch')

    def test_unrelated_fstab_entries_are_ignored(self):
        self.assertEqual(self.check_mount(fstab=[
            '/dev/sda1 /mnt/pinas/not-managed ext4 defaults 0 2',
            'UUID=12345678-abcd /mnt/pinas/elsewhere ext4 defaults 0 2 # PiNAS managed',
        ]),[])

    def test_api_checks_fresh_disk_before_adoption(self):
        src=(SOURCE/'http_api.py').read_text(encoding='utf-8')
        endpoint=src[src.index("if path=='/api/storage':"):src.index("if path=='/api/edit-share':")]
        self.assertIn("fresh=hardware_discovery()",endpoint)
        self.assertLess(endpoint.index("fresh=hardware_discovery()"),endpoint.index("result=configure_nas_mount(device)"))
        self.assertIn("Selected data filesystem is missing, read-only or ineligible",endpoint)

    def test_warning_is_visible_but_no_automatic_repair(self):
        src=(SOURCE/'web_ui.py').read_text(encoding='utf-8')
        self.assertIn("function storageSafetyWarnings()",src)
        self.assertIn("managed_storage_health||[]",src)
        self.assertIn("RAID degraded",src)
        self.assertIn("will not automatically format, repair, or mount",src)
        self.assertIn("storageSafetyWarnings()+",src)

if __name__=='__main__':
    unittest.main()
