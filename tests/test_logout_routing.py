"""Exercise authenticated logout through the actual HTTP handler for both roles."""
import io
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src'/'pinas'

class LogoutRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.globals={'__name__':'pinas_logout_test'}
        for name in ('core.py','http_api.py'):
            exec(compile((SOURCE/name).read_text(encoding='utf-8'),str(SOURCE/name),'exec'),cls.globals)

    def request(self,role,csrf_header='test-csrf'):
        scope=self.globals
        token='test-logout-'+role
        session={'role':role,'csrf':'test-csrf','expires':9999999999,'username':'tester'}
        scope['SESSIONS'][token]=session
        scope['load']=lambda:{'session_timeout':5}
        handler=scope['Handler'].__new__(scope['Handler'])
        handler.path='/api/logout'
        handler.headers={'Content-Length':'2','X-PiNAS-CSRF':csrf_header}
        handler.rfile=io.BytesIO(b'{}')
        handler.connection=object()
        handler.session=lambda:(token,session)
        responses=[]
        handler.json=lambda data,status=200,cookie=None: responses.append((data,status,cookie))
        handler.do_POST()
        return token,responses

    def test_admin_and_standard_user_can_logout(self):
        for role in ('admin','user'):
            with self.subTest(role=role):
                token,responses=self.request(role)
                self.assertEqual(len(responses),1)
                payload,status,cookie=responses[0]
                self.assertEqual(status,200)
                self.assertEqual(payload,{'ok':True})
                self.assertIn('Max-Age=0',cookie)
                self.assertNotIn(token,self.globals['SESSIONS'])

    def test_csrf_must_still_match(self):
        token,responses=self.request('user',csrf_header='bad-csrf')
        self.assertEqual(responses[0][1],403)
        self.assertIn(token,self.globals['SESSIONS'])
        self.globals['SESSIONS'].pop(token,None)

if __name__=='__main__':
    unittest.main()
