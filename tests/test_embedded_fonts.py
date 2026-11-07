"""Self-hosted typography and offline font delivery regression checks."""
import ast
import base64
import http.server
import pathlib
import runpy
import threading
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
FONT_NAMES = ("ClearSans-Regular.woff", "ClearSans-Medium.woff",
              "ClearSans-Bold.woff", "SourceCodePro-Regular.woff2",
              "SourceCodePro-Bold.woff2")

class EmbeddedFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scope = runpy.run_path(str(ROOT / "pinas.py"),
                                   run_name="pinas_font_tests")

    def test_fonts_embedded_and_identical_to_vendored_files(self):
        fonts = self.scope["PINAS_FONT_ASSETS"]
        self.assertEqual(set(fonts), set(FONT_NAMES))
        for name in FONT_NAMES:
            with self.subTest(font=name):
                raw = base64.b64decode(fonts[name], validate=True)
                self.assertEqual(raw, (ROOT / "assets" / "fonts" / name).read_bytes())
                self.assertTrue(raw.startswith(b"wOF2" if name.endswith(".woff2")
                                                   else b"wOFF"))
        for name in ("LICENSE-ClearSans.txt", "LICENSE-SourceCodePro.md"):
            self.assertTrue((ROOT / "assets" / "fonts" / name).is_file())

    def test_ui_applies_fonts_with_self_hosted_urls(self):
        page = self.scope["PAGE"]
        self.assertIn("font-family:var(--font-ui)", page)
        self.assertIn("pre,code,kbd,samp,#ms-folders{font-family:var(--font-mono)}", page)
        for name in FONT_NAMES:
            self.assertIn("/assets/fonts/" + name, page)
        self.assertNotIn("fonts.googleapis.com", page)

    def test_font_api_no_auth_and_cached_binary(self):
        handler = self.scope["Handler"]
        # Requesting a font must work on the pre-login page as well.
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}/assets/fonts/"
                for name in (FONT_NAMES[0], FONT_NAMES[-1]):
                    with self.subTest(font=name), urllib.request.urlopen(base + name) as response:
                        expected = "font/woff2" if name.endswith(".woff2") else "font/woff"
                        self.assertEqual(response.headers["Content-Type"], expected)
                        self.assertIn("max-age=", response.headers["Cache-Control"])
                        self.assertEqual(response.read(), (ROOT / "assets" / "fonts" / name).read_bytes())
                with self.assertRaises(urllib.error.HTTPError) as missing:
                    urllib.request.urlopen(base + "../missing.woff")
                self.assertEqual(missing.exception.code, 404)
            finally:
                server.shutdown()
                thread.join(timeout=5)

if __name__ == "__main__":
    unittest.main()
