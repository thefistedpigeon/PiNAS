"""Regression tests for update-triggered reboot and default NAS-user avatar."""
import ast
import io
import pathlib
import types
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src'/'pinas'

class RebootAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scope={'__name__':'pinas_reboot_test'}
        for name in ('core.py','http_api.py'):
            exec(compile((SOURCE/name).read_text(encoding='utf-8'),str(SOURCE/name),'exec'),cls.scope)

    def request(self,role='admin',marker=True,password_ok=True,running=False,csrf_ok=True):
        scope=self.scope
        original={key:scope[key] for key in ('load','verify','admin_record','Path','subprocess')}
        original_running=scope['UPDATE_STATUS']['running']
        calls=[]
        class Marker:
            def exists(self):
                return marker
        class FakeSubprocess:
            TimeoutExpired=original['subprocess'].TimeoutExpired
            def run(self,command,**kwargs):
                calls.append(command)
                return types.SimpleNamespace(returncode=0,stderr='',stdout='')
        try:
            scope['load']=lambda:{}
            scope['verify']=lambda given,stored:password_ok
            scope['admin_record']=lambda cfg,username:{'password':'mock-hash'}
            scope['Path']=lambda path:Marker()
            scope['subprocess']=FakeSubprocess()
            scope['UPDATE_STATUS']['running']=running
            session={'role':role,'csrf':'test-csrf','username':'admin','expires':9999999999}
            h=scope['Handler'].__new__(scope['Handler'])
            h.path='/api/updates'
            h.headers={'Content-Length':'35','X-PiNAS-CSRF':'test-csrf' if csrf_ok else 'wrong'}
            payload=b'{"action":"reboot","admin_password":"pw"}'
            h.headers['Content-Length']=str(len(payload))
            h.rfile=io.BytesIO(payload)
            h.connection=object()
            h.session=lambda:('test-token',session)
            responses=[]
            h.json=lambda obj,status=200,cookie=None:responses.append((obj,status))
            h.do_POST()
            return responses,calls
        finally:
            scope['UPDATE_STATUS']['running']=original_running
            scope.update(original)

    def test_admin_can_schedule_reboot_only_when_required(self):
        responses,calls=self.request()
        self.assertEqual(responses,[({'ok':True,'message':'System reboot scheduled'},200)])
        self.assertEqual(calls,[['/usr/bin/sudo','-n','/usr/local/libexec/pinas-apt-index','reboot']])

    def test_standard_users_cannot_reboot(self):
        result,calls=self.request(role='user')
        self.assertEqual(result[0][1],403)
        self.assertEqual(calls,[])

    def test_marker_is_required(self):
        result,calls=self.request(marker=False)
        self.assertEqual(result[0][1],409)
        self.assertEqual(calls,[])

    def test_in_progress_updates_block_reboot(self):
        result,calls=self.request(running=True)
        self.assertEqual(result[0][1],409)
        self.assertEqual(calls,[])

    def test_password_and_csrf_required(self):
        for kwargs in ({'password_ok':False},{'csrf_ok':False}):
            with self.subTest(kwargs=kwargs):
                result,calls=self.request(**kwargs)
                self.assertEqual(result[0][1],403)
                self.assertEqual(calls,[])

class RebootAndAvatarSourceTests(unittest.TestCase):
    def test_reboot_is_hidden_unless_needed(self):
        tree=ast.parse((SOURCE/'web_ui.py').read_text(encoding='utf-8'))
        page=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PAGE' for t in n.targets))
        self.assertIn('id="update-reboot-panel" hidden',page)
        self.assertIn('rebootPanel.hidden=!j.reboot_required||!!status.running',page)
        self.assertIn("updatePasswordDialog('reboot')",page)
        self.assertIn("action:'reboot',admin_password:password",page)
        self.assertNotIn("const DEFAULT_USER_AVATAR_ICON=\`\`",page)

    def test_default_avatar_svg_and_custom_picture(self):
        src=(SOURCE/'web_ui.py').read_text(encoding='utf-8')
        self.assertIn('const DEFAULT_USER_AVATAR_ICON=',src)
        self.assertIn('userAvatarMarkup("user-avatar")',src)
        self.assertIn('updateAvatarPreview(avatar)',src)
        self.assertIn('updateAvatarPreview(\'\')',src)
        self.assertIn('cfg.profile_avatar||\'\'',src)

    def test_helper_has_root_side_reboot_gate(self):
        src=(SOURCE/'http_api.py').read_text(encoding='utf-8')
        self.assertIn("if args==['reboot']:",src)
        self.assertIn("Path('/run/reboot-required').is_file()",src)
        self.assertIn("'--on-active=10s'",src)
        installer=(SOURCE/'installer.py').read_text(encoding='utf-8')
        self.assertIn('"schedule monthly","reboot"',installer)

if __name__=='__main__':
    unittest.main()
