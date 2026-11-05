"""PiNAS admin MiniDLNA upload regression tests.

Uses temporary directories only. No actual sudo, MiniDLNA service, Samba,
disk mount, privileged helper installation or NAS file modification.
"""
import ast
import base64
import json
import pathlib
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
MEDIA=(ROOT/'src/pinas/media_server.py').read_text()
API=(ROOT/'src/pinas/http_api.py').read_text()
INSTALL=(ROOT/'src/pinas/installer.py').read_text()
UI=(ROOT/'src/pinas/web_ui.py').read_text()

def helper_source(name):
    return ast.literal_eval(next(node.value for node in ast.parse(MEDIA).body
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets)))

def helper_namespace():
    values={'__name__':'pinas_media_upload_tests'}
    exec(compile(helper_source('MEDIA_UPLOAD_HELPER'),'media-upload-helper','exec'),values)
    return values

class MediaUploadTests(unittest.TestCase):
    def test_helper_compiles_and_whitelists_actions(self):
        helper=helper_source('MEDIA_UPLOAD_HELPER')
        compile(helper,'media-upload-helper','exec')
        for expected in ('os.O_NOFOLLOW', 'os.O_EXCL', 'os.link(stage,final,follow_symlinks=False)',
                         "file_name(data['name'])","path not in configured()",
                         "'--target',path", "stage.stat().st_size!=data['size']",
                         "'u:minidlna:r--'","'start','chunk','finish','cancel'"):
            with self.subTest(expected=expected):self.assertIn(expected,helper)
        self.assertNotIn('shell=True',helper)
        self.assertIn("timeout=65",MEDIA)

    def test_media_file_extensions_and_paths(self):
        ns=helper_namespace()
        for name in ('Movie.MKV','track.FLAC','picture.JPG','subtitles.srt','clip.webm'):
            self.assertEqual(ns['file_name'](name),name)
        for invalid in ('../../secret.mp4','test.exe','.hidden.mp4','a/b.mp4',
                        'folder\\file.mp4','', 'bad\nname.mp4'):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                ns['file_name'](invalid)
        self.assertEqual(ns['MAX_FILE'],100*1024**3)

    def test_upload_start_chunk_finish_atomic_no_clobber(self):
        ns=helper_namespace()
        with tempfile.TemporaryDirectory() as root:
            folder=pathlib.Path(root)
            payload=b'example movie bytes'
            started=ns['start'](folder,{'name':'Movie.mkv','size':len(payload)})
            token=started['token']
            stage,meta=ns['staging_paths'](folder,token)
            self.assertTrue(stage.exists())
            self.assertFalse((folder/'Movie.mkv').exists())
            self.assertEqual(stat.S_IMODE(stage.stat().st_mode),0o600)
            # Tests run unprivileged; simulate root ownership for staged file
            # without altering ownership of any real file.
            actual_lstat=pathlib.Path.lstat
            def pretend_root(path,*args,**kwargs):
                info=actual_lstat(path,*args,**kwargs)
                if path in (stage,meta):
                    entries=list(info)
                    entries[4]=0
                    return os.stat_result(entries)
                return info
            import os
            with mock.patch.object(pathlib.Path,'lstat',autospec=True,side_effect=pretend_root):
                next_offset=ns['chunk'](folder,{
                    'token':token,'offset':0,'content':base64.b64encode(payload).decode()})
                self.assertEqual(next_offset['offset'],len(payload))
                with self.assertRaises(ValueError):
                    ns['chunk'](folder,{
                        'token':token,'offset':0,'content':base64.b64encode(payload).decode()})
                with mock.patch.object(ns['subprocess'],'run',return_value=subprocess.CompletedProcess([],0,'','')):
                    result=ns['finish'](folder,{'token':token})
            self.assertTrue(result['ok'])
            self.assertEqual((folder/'Movie.mkv').read_bytes(),payload)
            self.assertFalse(stage.exists())
            self.assertFalse(meta.exists())

    def test_existing_files_are_not_overwritten(self):
        ns=helper_namespace()
        with tempfile.TemporaryDirectory() as root:
            folder=pathlib.Path(root)
            (folder/'movie.mp4').write_bytes(b'keep existing')
            with self.assertRaises(ValueError):
                ns['start'](folder,{'name':'movie.mp4','size':123})
            self.assertEqual((folder/'movie.mp4').read_bytes(),b'keep existing')

    def test_user_interface_and_authenticated_api(self):
        self.assertIn('data-media-upload',UI)
        self.assertIn('openMediaUpload(button.dataset.mediaUpload)',UI)
        self.assertIn("file.slice(offset,offset+384*1024)",UI)
        for action in ("action:'start'","action:'chunk'","action:'finish'","action:'cancel'"):
            self.assertIn(action,UI)
        self.assertIn("if path=='/api/media-upload':",API)
        self.assertIn("if s.get('role')!='admin':",API)
        self.assertIn("admin_password",API)
        self.assertIn("media_upload_action(action,details)",API)
        self.assertIn("('pinas-media-upload',MEDIA_UPLOAD_HELPER,[\"start\",\"chunk\",\"finish\",\"cancel\"])",INSTALL)
        self.assertIn("install_privileged_helper('pinas-media-upload',MEDIA_UPLOAD_HELPER",INSTALL)

if __name__=='__main__':unittest.main()
