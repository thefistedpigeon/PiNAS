"""Check same-port HTTP-to-HTTPS redirect and unchanged TLS routing."""
import pathlib
import socket
import ssl
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

ROOT=pathlib.Path(__file__).resolve().parents[1]
INSTALLER=(ROOT/'src/pinas/installer.py').read_text()

class FakeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'plain')
    def log_message(self,*args):
        return

class ProtocolTests(unittest.TestCase):
    def test_http_redirect_on_https_port(self):
        namespace={'__name__':'pinas_protocol_test','ThreadingHTTPServer':ThreadingHTTPServer,
                   'socket':socket,'ssl':ssl}
        exec(compile(INSTALLER,'installer.py','exec'),namespace)
        server=namespace['PiNASProtocolServer'](('127.0.0.1',0),FakeHandler)
        server.tls_context=object()
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with socket.create_connection(('127.0.0.1',server.server_port),timeout=3) as client:
                client.sendall(b'GET / HTTP/1.1\r\nHost: attacker.invalid\r\nConnection: close\r\n\r\n')
                data=b''
                while True:
                    chunk=client.recv(4096)
                    if not chunk:break
                    data+=chunk
            self.assertIn(b'HTTP/1.1 307 Temporary Redirect\r\n',data)
            self.assertIn(('Location: https://127.0.0.1:'+str(server.server_port)+'/\r\n').encode(),data)
            self.assertNotIn(b'attacker.invalid',data)
            self.assertIn(b'Cache-Control: no-store\r\n',data)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_tls_is_detected_and_webapp_tls_only_is_unchanged(self):
        self.assertIn("initial==b'\\x16'",INSTALLER)
        self.assertIn('self.tls_context.wrap_socket(request,server_side=True)',INSTALLER)
        self.assertIn("if a.host=='0.0.0.0' and not a.tls",INSTALLER)
        self.assertIn('context.minimum_version=ssl.TLSVersion.TLSv1_2',INSTALLER)
        self.assertIn('server.tls_context=context',INSTALLER)
        self.assertNotIn('server.socket=context.wrap_socket(server.socket,server_side=True)',INSTALLER)

if __name__=='__main__':
    unittest.main()
