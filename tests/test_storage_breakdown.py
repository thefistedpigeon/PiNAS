"""Media storage classification: no continuous watchers, no content reads."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'src/pinas/storage_breakdown.py').read_text()
UI=(ROOT/'src/pinas/web_ui.py').read_text()
API=(ROOT/'src/pinas/http_api.py').read_text()
INSTALL=(ROOT/'src/pinas/installer.py').read_text()

def scope():
    values={'__name__':'pinas_storage_breakdown_test'}
    exec(compile(SOURCE,'storage_breakdown.py','exec'),values)
    return values

class StorageBreakdownTests(unittest.TestCase):
    def test_extensions(self):
        ns=scope()
        cases={'film.MKV':'video','clip.avi':'video','sample.MP4':'video',
               'PHOTO.JPEG':'pictures','icon.svg':'pictures','photo.png':'pictures',
               'track.FLAC':'music','song.mp3':'music','audio.aac':'music',
               'archive.zip':'other','README':'other'}
        for filename,kind in cases.items():self.assertEqual(ns['media_category'](filename),kind)

    def test_scanner_does_not_follow_symlinks_or_open_file_content(self):
        ns=scope()
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)/'library';base.mkdir()
            (base/'Movies').mkdir()
            (base/'Movies'/'video.mkv').write_bytes(b'x'*8192)
            (base/'Pictures').mkdir()
            (base/'Pictures'/'image.png').write_bytes(b'x'*4096)
            (base/'README').write_text('other')
            (base/'escape').symlink_to(Path(root))
            totals,files=ns['scan_media_volume'](base)
            self.assertEqual(files,3)
            self.assertGreater(totals['video'],0)
            self.assertGreater(totals['pictures'],0)
            self.assertGreaterEqual(totals['other'],0)

    def test_folder_symlink_is_rejected(self):
        ns=scope()
        with tempfile.TemporaryDirectory() as root:
            link=Path(root)/'alias';link.symlink_to(Path(root))
            with self.assertRaises(ValueError):ns['scan_media_volume'](link)

    def test_ui_is_nonblocking_and_on_demand(self):
        self.assertIn("mediaBreakdownCache",UI)
        self.assertIn("loadMediaBreakdown()",UI)
        self.assertIn("Rescan media types",UI)
        self.assertIn("MEDIA_STORAGE_TYPES",UI)
        self.assertIn("if path=='/api/media-breakdown':",API)
        self.assertIn("media_breakdown_status(refresh=True)",API)
        self.assertIn("_STORAGE_INTERVAL=1800",SOURCE)
        self.assertIn("st.st_blocks",SOURCE)
        self.assertIn("if st.st_dev!=rootstat.st_dev:continue",SOURCE)
        self.assertIn("if not volume.get('persistent') or volume.get('read_only')",SOURCE)

    def test_existing_share_permissions_are_inherited(self):
        share=API.split('NAS_SHARE_HELPER = r',1)[1].split('NAS_FILES_HELPER = r',1)[0]
        self.assertGreaterEqual(share.count('inherit acls = yes'),2)
        self.assertIn("if len(sys.argv)==2 and sys.argv[1]=='repair':",share)
        self.assertIn("run(['/usr/bin/setfacl','-R','-P','-m'",share)
        self.assertIn("point.startswith(str(folder)+'/')",share)
        self.assertIn("os.chmod(folder,0o777 if public else 0o700)\n            # chmod after setfacl",share)
        self.assertIn("['list','create','delete','edit','migrate','repair']",INSTALL.replace('"',"'"))
        self.assertIn("data-repair-share",UI)
        self.assertIn("if path=='/api/repair-share':",API)

if __name__=='__main__':unittest.main()
