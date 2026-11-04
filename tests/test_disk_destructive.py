"""PiNAS v1.0.8 destructive-storage safety and confirmation regression tests.

No real block device is modified by these tests.
"""
import ast
import pathlib
import stat
import types
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/pinas'
CORE=(SOURCE/'core.py').read_text(encoding='utf-8')
UI=(SOURCE/'web_ui.py').read_text(encoding='utf-8')
HTTP=(SOURCE/'http_api.py').read_text(encoding='utf-8')
INSTALL=(SOURCE/'installer.py').read_text(encoding='utf-8')
HELPERS=(SOURCE/'privileged_helpers.py').read_text(encoding='utf-8')
CONSTANTS={}
for name,text in [('PAGE',UI),('NAS_DISK_ERASE_HELPER',HELPERS)]:
    for item in ast.parse(text).body:
        if (isinstance(item,ast.Assign)
            and any(isinstance(target,ast.Name) and target.id==name for target in item.targets)):
            CONSTANTS[name]=ast.literal_eval(item.value)
            break
PAGE=CONSTANTS['PAGE']
HELPER=CONSTANTS['NAS_DISK_ERASE_HELPER']


def load_helper():
    namespace={'__name__':'pinas_disk_erase_unit_test'}
    exec(compile(HELPER,'pinas-disk-erase','exec'),namespace)
    return namespace


class DiskDestructiveTests(unittest.TestCase):
    def test_helper_and_bundle_compile(self):
        compile(HELPER,'pinas-disk-erase','exec')
        self.assertIn("VERSION='1.0.8'",CORE)

    def test_web_requires_explicit_yes_and_current_password(self):
        self.assertIn('id="disk-danger-yes" type="checkbox" required',PAGE)
        self.assertIn('class="field disk-danger-consent"',PAGE)
        self.assertIn('.modal-overlay .disk-danger-consent input[type="checkbox"]{width:18px;height:18px;min-width:18px;max-width:18px;padding:0;margin:0;flex:none;accent-color:var(--accent)}',PAGE)
        self.assertIn('id="disk-danger-password" type="password"',PAGE)
        self.assertIn('class="btn danger" id="disk-danger-confirm" type="submit" disabled',PAGE)
        self.assertIn("submit.disabled=!(check.checked&&password.value.length)",PAGE)
        self.assertIn("if(!check.checked||!password.value)return",PAGE)
        self.assertIn("await post('/api/disk-destructive'",PAGE)
        self.assertIn("action,device:d.path,expected_size:Number(d.size),filesystem:approved.filesystem,confirm:true,admin_password:approved.admin_password",PAGE)
        self.assertIn("['wipe','format']",PAGE)
        self.assertIn("o.id==='disk-mount'?'':'danger'",PAGE)

    def test_http_revalidates_and_does_not_trust_browser(self):
        self.assertIn("if path=='/api/disk-destructive':",HTTP)
        self.assertIn("if s.get('role')!='admin':",HTTP)
        self.assertIn("confirmation is not True",HTTP)
        self.assertIn("verify(password,(admin_record(cfg,s['username']) or {}).get('password',''))",HTTP)
        self.assertIn("fresh=hardware_discovery()",HTTP)
        self.assertIn("d.get('size')==expected_size",HTTP)
        self.assertIn("expected_size!=int(disk.get('size') or 0)",HELPER)
        self.assertIn("'/usr/local/libexec/pinas-disk-erase',action",HTTP)
        self.assertIn("DISCOVERY_CACHE.clear()",HTTP)

    def test_privileged_helper_denies_unsafe_topologies(self):
        for phrase in ('Operating system disk is protected','Mounted disks or partitions cannot be wiped',
                       'RAID, encryption, LVM and nested devices are protected','Active swap is protected',
                       'A partition is configured in fstab','Unable to identify operating system disk safely',
                       'Only direct block-device paths are allowed','Disk topology changed; operation aborted'):
            self.assertIn(phrase,HELPER)
        self.assertIn("os.O_NOFOLLOW",HELPER)
        self.assertIn("fcntl.flock(lock,fcntl.LOCK_EX)",HELPER)

    def test_mounted_disk_refused_before_command(self):
        namespace=load_helper()
        roots=[{'name':'sda','path':'/dev/sda','type':'disk','size':2000000000,'ro':False,
                'mountpoints':['/data'],'children':[]},
               {'name':'mmcblk0','path':'/dev/mmcblk0','type':'disk','size':1000000000,'ro':False,
                'mountpoints':['/'],'children':[]}]
        with (mock.patch.object(namespace['Path'],'is_symlink',return_value=False),
              mock.patch.object(namespace['Path'],'is_block_device',return_value=True),
              mock.patch.object(namespace['os'],'open',return_value=3),
              mock.patch.object(namespace['os'],'close'),
              mock.patch.object(namespace['os'],'fstat',return_value=types.SimpleNamespace(st_mode=stat.S_IFBLK))):
            with self.assertRaisesRegex(ValueError,'Mounted disks'):
                namespace['checked_disk']('/dev/sda',roots,2000000000)

    def test_disk_with_raid_child_refused(self):
        namespace=load_helper()
        roots=[{'name':'sda','path':'/dev/sda','type':'disk','size':2000000000,'ro':False,
                'mountpoints':[],
                'children':[{'name':'md0','path':'/dev/md0','type':'raid1','ro':False,'mountpoints':[]}]},
               {'name':'mmcblk0','path':'/dev/mmcblk0','type':'disk','size':1000000000,'ro':False,
                'mountpoints':['/'],'children':[]}]
        with (mock.patch.object(namespace['Path'],'is_symlink',return_value=False),
              mock.patch.object(namespace['Path'],'is_block_device',return_value=True),
              mock.patch.object(namespace['os'],'open',return_value=3),
              mock.patch.object(namespace['os'],'close'),
              mock.patch.object(namespace['os'],'fstat',return_value=types.SimpleNamespace(st_mode=stat.S_IFBLK))):
            with self.assertRaisesRegex(ValueError,'RAID'):
                namespace['checked_disk']('/dev/sda',roots,2000000000)

    def test_signature_erasure_targets_parts_before_disk(self):
        namespace=load_helper()
        calls=[]
        namespace['run']=lambda *args,**kwargs:calls.append(args) or ''
        disk={'path':'/dev/sdb'}
        part={'path':'/dev/sdb1'}
        with mock.patch.object(namespace['Path'],'is_block_device',return_value=True):
            namespace['erase_signatures']([disk,part])
        self.assertEqual(calls[0],('wipefs','--all','--force','/dev/sdb1'))
        self.assertEqual(calls[1],('wipefs','--all','--force','/dev/sdb'))
        self.assertEqual(calls[2],('blockdev','--rereadpt','/dev/sdb'))

    def test_no_secure_erase_claim_and_only_allowlisted_formatters(self):
        self.assertIn('quick wipe, NOT a secure overwrite',PAGE)
        self.assertIn("'ext4':('mkfs.ext4','-F')",HELPER)
        self.assertIn("'xfs':('mkfs.xfs','-f')",HELPER)
        self.assertIn("'btrfs':('mkfs.btrfs','-f')",HELPER)
        self.assertIn("if detected!=filesystem:raise ValueError('Formatted filesystem verification failed')",HELPER)
        self.assertIn("if action=='format' and filesystem not in FILESYSTEMS",HELPER)

    def test_upgrade_installs_restricted_root_helper(self):
        self.assertIn("install_privileged_helper('pinas-disk-erase',NAS_DISK_ERASE_HELPER,[\"wipe\",\"format\"])",INSTALL)
        self.assertIn("if Path('/usr/local/libexec/pinas-apt-index').is_file()",INSTALL)

if __name__=='__main__':
    unittest.main()
