"""Current MiniDLNA privileged helper regression tests."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
MEDIA=(ROOT/'src/pinas/media_server.py').read_text()
API=(ROOT/'src/pinas/http_api.py').read_text()
UI=(ROOT/'src/pinas/web_ui.py').read_text()
INSTALL=(ROOT/'src/pinas/installer.py').read_text()
def literal(name):
    for node in ast.parse(MEDIA).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError('Missing '+name)
class MiniDLNATests(unittest.TestCase):
    def test_real_helper_compiles(self):
        compile(literal('MEDIA_SERVER_HELPER'),'pinas-media-server','exec')
    def test_command_and_media_folder_validation(self):
        helper=literal('MEDIA_SERVER_HELPER')
        for token in ('def validate(data):','safe_path(', 'setup_library(', 'setfacl','media_dir'):
            with self.subTest(token=token):self.assertIn(token,helper)
        self.assertNotIn("shell=True",helper)
    def test_admin_api_and_optional_installation(self):
        self.assertIn("if path=='/api/media-server':",API)
        self.assertIn("verify(password,(admin_record(cfg,s['username'])",API)
        self.assertIn("install_privileged_helper('pinas-media-server'",INSTALL)
        self.assertIn("items.push('Media Server')",UI)
if __name__=='__main__':unittest.main()
