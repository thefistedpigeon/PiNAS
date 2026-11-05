"""PiNAS v1.0.14 resource and privilege hardening regressions."""
from pathlib import Path
import ast
import json
import os
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'src/pinas/core.py').read_text()
API=(ROOT/'src/pinas/http_api.py').read_text()
INSTALL=(ROOT/'src/pinas/installer.py').read_text()
UI=(ROOT/'src/pinas/web_ui.py').read_text()
HELPERS=(ROOT/'src/pinas/privileged_helpers.py').read_text()
MEDIA=(ROOT/'src/pinas/media_server.py').read_text()
def load_helper(name,source):
    return ast.literal_eval(next(node.value for node in ast.parse(source).body
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets)))
def scope():
    ns={'__name__':'pinas_core_test'}
    exec(compile(CORE,'core.py','exec'),ns)
    return ns

class HardeningTests(unittest.TestCase):
    def test_config_cache_is_mutation_safe_and_detects_replacements(self):
        ns=scope()
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'config.json'
            config.write_text(json.dumps({'theme':'dark','profiles':{'user':'Alice'}}))
            ns['CONFIG']=config
            ns['CONFIG_CACHE_KEY']=None
            ns['CONFIG_CACHE_VALUE']=None
            first=ns['load']()
            first['profiles']['user']='Modified'
            self.assertEqual(ns['load']()['profiles']['user'],'Alice')
            replacement=Path(tmp)/'new.json'
            replacement.write_text(json.dumps({'theme':'light','profiles':{'user':'Bob'}}))
            os.replace(replacement,config)
            self.assertEqual(ns['load']()['profiles']['user'],'Bob')
            saved=ns['load']();saved['theme']='dark'
            ns['save'](saved)
            self.assertEqual(ns['load']()['theme'],'dark')

    def test_apt_cache_does_not_poll_during_upgrade(self):
        ns=scope()
        count=[]
        def read_packages():
            count.append(1)
            return {'packages':[{'name':'test'}]}
        ns['_package_updates_uncached']=read_packages
        ns['UPDATE_STATUS']['running']=True
        self.assertEqual(ns['package_updates']()['packages'],[])
        self.assertEqual(count,[])
        ns['UPDATE_STATUS']['running']=False
        self.assertEqual(len(ns['package_updates']()['packages']),1)
        self.assertEqual(len(ns['package_updates']()['packages']),1)
        self.assertEqual(len(count),1)

    def test_jobs_are_session_scoped(self):
        ns=scope()
        job=ns['start_job']('admin-session','unit',lambda:{'ok':True})
        with self.assertRaises(ValueError):ns['get_job']('other-session',job['job_id'])
        for _ in range(100):
            result=ns['get_job']('admin-session',job['job_id'])
            if not result['running']:break
            time.sleep(.01)
        self.assertFalse(result['running'])
        self.assertEqual(result['result'],{'ok':True})

    def test_sudoers_requires_validation_and_atomic_install(self):
        self.assertIn("if not visudo:raise RuntimeError",INSTALL)
        self.assertIn("os.replace(staged_rule,rule)",INSTALL)
        self.assertIn("[visudo,'-cf',str(staged_rule)]",INSTALL)
        self.assertIn("persist-credentials: false",(ROOT/'.github/workflows/quality.yml').read_text())

    def test_smart_and_raid_safeguards(self):
        smart=load_helper('SMART_HEALTH_HELPER',HELPERS)
        self.assertIn("[smartctl,'-j','-n','standby','-H','-A',device]",smart)
        self.assertIn("startswith('raid')",CORE)
        self.assertIn('noatime,nosuid,nodev',HELPERS)

    def test_tls_renewal_is_limited_to_managed_certificates(self):
        tls=load_helper('HOSTNAME_HELPER',API)
        compile(tls,'pinas-apply-hostname','exec')
        self.assertIn("MANAGED=ROOT/'tls-managed'",tls)
        self.assertIn("'checkend','5184000'",tls)
        self.assertIn("if not MANAGED.exists():",tls)
        self.assertIn("OnCalendar=monthly",INSTALL)

    def test_browser_password_page_download_and_file_paging(self):
        page=load_helper('PAGE',UI)
        self.assertIn("password?input.value:input.value.trim()",page)
        self.assertIn("maxlength=",page)
        self.assertIn("hostname-preview",page)
        self.assertIn("Advanced MiniDLNA settings",page)
        self.assertIn("Load more files",page)
        self.assertIn("/api/file-download?",page)
        self.assertIn("PAGE_BYTES=PAGE.encode('utf-8')",UI)
        files=load_helper('NAS_FILES_HELPER',API)
        compile(files,'pinas-nas-files','exec')
        self.assertIn("if action=='download_stream':",files)
        self.assertIn("'next_offset':next_offset",files)
        self.assertIn("with target.open('rb') as source:",files)
        self.assertIn("if path=='/api/file-download':",API)
        self.assertIn("self.wfile.write(block)",API)
        self.assertIn("filename*=UTF-8",API)

    def test_share_lock_and_restore_merge(self):
        share=load_helper('NAS_SHARE_HELPER',API)
        self.assertIn("fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)",share)
        self.assertIn("'nas_display_names']={**existing_names,**names}",API)
        self.assertIn("repair_existing",UI)

if __name__=='__main__':unittest.main()
