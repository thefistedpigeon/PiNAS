"""v1.0.15: administrator power controls and per-disk diagnostics.

No root command, disk scan or actual power action is invoked here.
"""
import ast
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'src/pinas/storage_breakdown.py').read_text()
API=(ROOT/'src/pinas/http_api.py').read_text()
INSTALL=(ROOT/'src/pinas/installer.py').read_text()
PRIV=(ROOT/'src/pinas/privileged_helpers.py').read_text()
UI=(ROOT/'src/pinas/web_ui.py').read_text()

def helper(name,source):
    for item in ast.parse(source).body:
        if isinstance(item,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in item.targets):
            return ast.literal_eval(item.value)
    raise ValueError('Helper missing: '+name)

def storage():
    ns={'__name__':'pinas_file_type_test'}
    exec(compile(SOURCE,'storage_breakdown.py','exec'),ns)
    return ns

class DiskDiagnosticsTests(unittest.TestCase):
    def test_root_scanner_compiles_and_stays_on_mount(self):
        source=helper('FILE_TYPE_SCAN_HELPER',SOURCE)
        compile(source,'pinas-file-types','exec')
        for match in ('os.geteuid()!=0','findmnt',"'--mountpoint'","meta.st_dev!=top.st_dev",
                      "entry.stat(follow_symlinks=False)",'st_blocks','time.sleep(.01)'):
            self.assertIn(match,source)
        self.assertNotIn('shell=True',source)
        self.assertIn("('pinas-file-types',FILE_TYPE_SCAN_HELPER,[\"scan *\"])",INSTALL)
        self.assertIn("install_privileged_helper('pinas-file-types',FILE_TYPE_SCAN_HELPER,[\"scan *\"])",INSTALL)

    def test_media_scan_is_manual_per_volume_and_restricted(self):
        ns=storage()
        with self.assertRaises(ValueError):ns['media_breakdown_status']('/etc')
        with mock.patch.dict(ns,{'hardware_discovery':lambda:{
            'disks':[{'volumes':[{'persistent':True,'mounts':['/mnt/pinas/drive-id']}]}]
        }}):
            self.assertEqual(ns['_valid_media_mount']('/mnt/pinas/drive-id'),'/mnt/pinas/drive-id')
            with self.assertRaises(ValueError):ns['_valid_media_mount']('/mnt/pinas/not-owned')
        self.assertIn("media_breakdown_status(data.get('mount'),refresh=True)",API)
        self.assertIn("readFileTypeStatus(mount)",UI)
        self.assertIn("data-scan-volume",UI)
        self.assertNotIn("loadMediaBreakdown()",UI)
        overview=UI.split("else if(page==='Overview'){",1)[1].split("else if(page==='Storage'){",1)[0]
        self.assertNotIn("storageScanPanels(d)",overview)

    def test_file_type_worker_uses_privileged_broker(self):
        ns=storage();mount='/mnt/pinas/drive-id'
        response=subprocess.CompletedProcess([],0,json.dumps({
            'categories':{'video':4096,'pictures':0,'music':0,'other':0},'files':1}),"")
        with mock.patch.object(ns['_storage_subprocess'],'run',return_value=response) as run:
            ns['_media_scan_worker'](mount)
            self.assertEqual(run.call_args.args[0][-2:],['scan',mount])
        self.assertEqual(ns['_STORAGE_STATE'][mount]['categories']['video'],4096)
        self.assertFalse(ns['_STORAGE_STATE'][mount]['running'])

    def test_smart_reports_sleeping_and_bridge_limitations(self):
        smart=helper('SMART_HEALTH_HELPER',PRIV)
        compile(smart,'pinas-smart-health','exec')
        self.assertIn("'-n','standby'",smart)
        self.assertIn("'Standby'",smart)
        self.assertIn("'Unsupported'",smart)
        self.assertIn("'sat'",smart)
        self.assertIn("entry['message']",smart)
        self.assertIn("data-smart-detail",UI)
        self.assertIn("disk-health-storage-message",UI)
        self.assertIn('autoDiskHealth()',UI)

    def test_power_helper_is_narrow_and_delayed(self):
        power=helper('POWER_HELPER',PRIV)
        compile(power,'pinas-power','exec')
        self.assertIn("('reboot','shutdown')",power)
        self.assertIn("'--on-active=8s'",power)
        self.assertIn("command='reboot' if action=='reboot' else 'poweroff'",power)
        self.assertNotIn('shell=True',power)
        self.assertIn("('pinas-power',POWER_HELPER,[\"reboot\",\"shutdown\"])",INSTALL)
        self.assertIn("install_privileged_helper('pinas-power',POWER_HELPER,[\"reboot\",\"shutdown\"])",INSTALL)
        self.assertIn("if path=='/api/power':",API)
        self.assertIn("confirmed is not True",API)
        self.assertIn("verify(password,(admin_record(cfg,s['username'])",API)
        self.assertIn("if s.get('role')!='admin':",API)
        self.assertIn("await post('/api/power',{action,admin_password:password,confirm:true})",UI)
        self.assertIn("id=\"power-menu\"",UI)

if __name__=='__main__':
    unittest.main()
