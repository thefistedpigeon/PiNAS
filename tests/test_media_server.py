"""Media Server regression and validation tests."""
import ast
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
MEDIA=(ROOT/'src/pinas/media_server.py').read_text()
API=(ROOT/'src/pinas/http_api.py').read_text()
INSTALL=(ROOT/'src/pinas/installer.py').read_text()
UI=ast.literal_eval(next(node.value for node in ast.parse((ROOT/'src/pinas/web_ui.py').read_text()).body
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PAGE' for t in node.targets)))
HELPER=ast.literal_eval(next(node.value for node in ast.parse(MEDIA).body
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MEDIA_SERVER_HELPER' for t in node.targets)))
def scope():
    result={'__name__':'pinas_media_test'}
    exec(compile(HELPER,'pinas-media-server','exec'),result)
    return result
class MediaServerTests(unittest.TestCase):
    def test_library_setup_provisions_four_typed_folders(self):
        ns=scope()
        saved=[]
        with tempfile.TemporaryDirectory() as root:
            volume=Path(root)/'uuid';volume.mkdir()
            folder=volume/'pinas-media';folder.mkdir()
            (folder/'Movies').mkdir()
            (folder/'Movies'/'existing.mkv').write_text('untouched')
            ns['installed']=lambda:True
            ns['configured_volume']=lambda v:volume
            ns['save']=lambda data,emit_status=True:saved.append(data)
            ns['active']=lambda:'active'
            ns['settings']=lambda:{}
            ns['setup_library']({'volume':str(volume)})
            self.assertEqual((folder/'Movies'/'existing.mkv').read_text(),'untouched')
            self.assertTrue(all((folder/name).is_dir() for name in ('Movies','Television','Music','Pictures')))
            self.assertEqual([x['type'] for x in saved[0]['media_dir']],['V','V','A','P'])
            self.assertTrue(saved[0]['inotify'])

    def test_library_setup_preserves_existing_media_on_failure(self):
        ns=scope()
        with tempfile.TemporaryDirectory() as root:
            volume=Path(root)/'uuid';volume.mkdir()
            folder=volume/'pinas-media';folder.mkdir()
            (folder/'Movies').mkdir()
            (folder/'Movies'/'existing.mkv').write_text('keep')
            ns['installed']=lambda:True
            ns['configured_volume']=lambda v:volume
            def fail(data,emit_status=True):raise RuntimeError('Restart failed')
            ns['save']=fail
            with self.assertRaises(RuntimeError):ns['setup_library']({'volume':str(volume)})
            self.assertEqual((folder/'Movies'/'existing.mkv').read_text(),'keep')
            self.assertFalse((folder/'Television').exists())

    def test_library_setup_rejects_invalid_payloads(self):
        ns=scope();ns['installed']=lambda:True
        for data in (None,{}, {'volume':'/etc'}, {'volume':42}):
            with self.assertRaises((ValueError,TypeError)):
                ns['setup_library'](data)

    def test_library_api_and_ui_are_admin_gated(self):
        self.assertIn("if action in ('install','save','grant','rebuild','setup-library'):",API)
        self.assertIn("if action in ('save','grant','setup-library') and not isinstance",API)
        self.assertIn("id=\"ms-library-volume\"",UI)
        self.assertIn("mediaAction('setup-library',true,{volume:target})",UI)

    def test_media_configuration_docs_and_valid_choices(self):
        for name in ('MEDIA_DOC','MEDIA_SELECTS','MEDIA_NUMERIC','root_container','tivo_discovery'):
            self.assertIn(name,UI)
        for literal in ('895','8200','bonjour','64','1024'):
            self.assertIn(literal,UI)
        self.assertIn("el.value.trim()===''?null:Number(el.value)",UI)
        self.assertIn("if(settings[key]===null)delete settings[key]",UI)

    def test_syntax_and_optional_install(self):
        compile(MEDIA,'media_server.py','exec')
        compile(HELPER,'pinas-media-server','exec')
        self.assertGreaterEqual(INSTALL.count("install_privileged_helper('pinas-media-server',MEDIA_SERVER_HELPER"),2)
        self.assertIn("'--no-install-recommends','minidlna'",HELPER)
        self.assertIn("'PATH':'/usr/sbin:/usr/bin:/sbin:/bin'",HELPER)
    def test_api_is_admin_only_and_password_protected(self):
        self.assertIn("if path=='/api/media-server':",API)
        self.assertIn("media_server_action(action,payload)",API)
        self.assertIn("verify(password,(admin_record(cfg,s['username'])",API)
    def test_ui_has_menu_install_and_settings(self):
        self.assertIn("items.push('Media Server')",UI)
        self.assertIn("id=\"ms-folders\"",UI)
        self.assertIn("Install MiniDLNA",UI)
        self.assertIn("mediaAction('save',true,settings)",UI)
    def test_validation_denies_invalid_input(self):
        ns=scope()
        for data in ({'arbitrary':'x'},{'port':1},{'friendly_name':'hello\nuser=root'},{'inotify':'yes'}):
            with self.assertRaises(ValueError):ns['validate'](data)
        for path in ('/etc','/mnt/pinas/../../etc'):
            with self.assertRaises(ValueError):ns['safe_path'](path)
    def test_permission_grant_is_explicit_and_restricted(self):
        self.assertIn("'grant'",HELPER)
        self.assertIn("safe_path(data.get('path'))",HELPER)
        self.assertIn("configured_media_folders()",HELPER)
        self.assertIn("u:minidlna:rX",HELPER)
        self.assertIn("d:u:minidlna:rX",HELPER)
        self.assertIn("data-media-grant",UI)
        self.assertIn("if action in ('install','save','grant','rebuild','setup-library'):",API)
    def test_rebuild_is_admin_confirmed_and_limited_to_database(self):
        self.assertIn("'rebuild'",HELPER)
        self.assertIn("files.db",HELPER)
        self.assertIn("'/var/cache/minidlna'",HELPER)
        self.assertIn("'/var/lib/minidlna'",HELPER)
        self.assertIn("Rebuild library",UI)
    def test_configuration_preserves_other_directives_and_rolls_back(self):
        ns=scope()
        with tempfile.TemporaryDirectory() as root:
            config=Path(root)/'minidlna.conf'
            config.write_text('# old\nuser=minidlna\nfriendly_name=Old\nmedia_dir=/mnt/legacy\n')
            ns['CONF']=config
            ns['installed']=lambda:True
            ns['run']=lambda args,timeout=35,env=None:SimpleNamespace(stdout='')
            ns['active']=lambda:'active'
            ns['status']=lambda:None
            ns['save']({'friendly_name':'New','inotify':True})
            text=config.read_text()
            self.assertIn('user=minidlna',text)
            self.assertIn('media_dir=/mnt/legacy',text)
            self.assertIn('friendly_name=New',text)
            self.assertNotIn('friendly_name=Old',text)
            ns['active']=lambda:'failed'
            with self.assertRaises(RuntimeError):ns['save']({'friendly_name':'Broken'})
            self.assertEqual(config.read_text(),text)
if __name__=='__main__':unittest.main()
