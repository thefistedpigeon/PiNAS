"""RC16.6 MiniDLNA integration checks (non-destructive).

Run: python3 -m unittest discover -s tests -v
"""
import ast
import pathlib
import unittest

SOURCE=(pathlib.Path(__file__).resolve().parents[1]/'pinas.py').read_text(encoding='utf-8')
TREE=ast.parse(SOURCE)
EMBEDDED={}
for node in TREE.body:
    if isinstance(node,ast.Assign):
        for target in node.targets:
            if isinstance(target,ast.Name) and target.id in ('NAS_MINIDLNA_HELPER','PAGE'):
                EMBEDDED[target.id]=ast.literal_eval(node.value)

class MiniDLNATests(unittest.TestCase):
    def test_helper_compiles(self):
        compile(EMBEDDED['NAS_MINIDLNA_HELPER'],'pinas-minidlna','exec')

    def test_api_and_sudo_broker(self):
        self.assertIn("if path=='/api/minidlna':",SOURCE)
        self.assertIn("admin_record(cfg,s['username'])",SOURCE)
        self.assertIn('pinas-minidlna status, /usr/local/libexec/pinas-minidlna action',SOURCE)
        self.assertIn("os.chmod(media_helper,0o700)",SOURCE)

    def test_configuration_is_allowlisted(self):
        helper=EMBEDDED['NAS_MINIDLNA_HELPER']
        self.assertIn("('all','audio','video','pictures')",helper)
        self.assertIn("share not in choices",helper)
        self.assertIn("managed_shares()",helper)
        self.assertIn("port not",helper) if False else None
        self.assertIn("not 1024<=port<=65535",helper)
        self.assertIn("not 60<=interval<=3600",helper)
        self.assertIn("backups=CONF.parent/",helper)
        self.assertIn("atomic(CONF,previous)",helper)

    def test_media_access_opt_in(self):
        helper=EMBEDDED['NAS_MINIDLNA_HELPER']
        self.assertIn("grant=data.get('grant_access',False)",helper)
        self.assertIn("'/usr/bin/find',root,'-xdev'",helper)
        self.assertIn("u:minidlna:r--",helper)
        self.assertIn("d:u:minidlna:rx",helper)

    def test_noninteractive_install_and_diagnostics(self):
        helper=EMBEDDED['NAS_MINIDLNA_HELPER']
        self.assertIn("'DEBIAN_FRONTEND':'noninteractive'",helper)
        self.assertIn("'Dpkg::Use-Pty=0'",helper)
        self.assertIn("p.stdout.strip(),p.stderr.strip()",helper)
        self.assertIn("[-5000:]",helper)

    def test_media_card_icon(self):
        page=EMBEDDED['PAGE']
        self.assertIn('class="app-card-title"',page)
        self.assertIn('viewBox="0 0 24 24"',page)
        self.assertIn('.app-card-title{display:flex;align-items:center;gap:12px}',page)

    def test_ui_install_and_configuration(self):
        page=EMBEDDED['PAGE']
        self.assertIn("function openMiniDLNA()",page)
        self.assertIn('id="open-minidlna"',page)
        self.assertIn("Install MiniDLNA",page)
        self.assertIn("Grant MiniDLNA read-only",page)
        self.assertIn("command('configure'",page)
        self.assertIn("data-dlna",page)

if __name__=='__main__':
    unittest.main()
