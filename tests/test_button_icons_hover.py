"""PiNAS v1.0.17 button icon and hover regression tests."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'src/pinas/web_ui.py').read_text()
PAGE=ast.literal_eval(next(node.value for node in ast.parse(SOURCE).body if isinstance(node,ast.Assign)
    and any(isinstance(t,ast.Name) and t.id=='PAGE' for t in node.targets)))

class ButtonIconsTests(unittest.TestCase):
    def test_all_media_and_storage_icons(self):
        for key in ('scan','start','stop','restart','rescan','rebuild','create','folder','grant','upload'):
            with self.subTest(key=key):
                self.assertIn("'+NAS_ACTION_ICONS."+key+"+'",PAGE)
        self.assertIn('const NAS_ACTION_ICONS=',PAGE)
        self.assertIn('data-scan-volume=',PAGE)
        self.assertIn('data-media-upload=',PAGE)
        self.assertIn('data-media-grant=',PAGE)

    def test_shared_outline_hover_and_22px_icons(self):
        self.assertIn('.btn.outline:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff;filter:none}',PAGE)
        self.assertIn('.btn.button-with-icon{display:inline-flex;align-items:center;justify-content:center;gap:8px}',PAGE)
        self.assertIn('.btn.button-with-icon>svg{display:block;width:22px;height:22px;min-width:22px;flex:none;color:inherit}',PAGE)
        self.assertIn('fill="currentColor"',PAGE)
        self.assertIn('stroke="currentColor"',PAGE)

    def test_text_only_save_and_refresh(self):
        self.assertIn('<button class="btn" type="submit">Save settings</button>',PAGE)
        self.assertIn('<button type="button" class="btn outline" id="ms-refresh">Refresh</button>',PAGE)

if __name__=='__main__':unittest.main()
