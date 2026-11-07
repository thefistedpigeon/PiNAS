"""PiNAS 1.1.4 — Shares page icon, label, hover and ordering regressions."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE = (ROOT / "src/pinas/core.py").read_text(encoding="utf-8")
UI = (ROOT / "src/pinas/web_ui.py").read_text(encoding="utf-8")
PAGE = next(ast.literal_eval(n.value) for n in ast.parse(UI).body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "PAGE" for t in n.targets))


class ShareButtonConsistencyTests(unittest.TestCase):
    def test_release_version(self):
        self.assertIn("VERSION='1.1.4'", CORE)

    def test_create_share_keeps_icon_and_adds_text(self):
        self.assertIn("const CREATE_SHARE_ICON=", PAGE)
        self.assertIn('id="create-nas-share"', PAGE)
        self.assertIn('id="create-nas-share" title="Create Share"', PAGE)
        self.assertIn('id="create-nas-share" title="Create Share" aria-label="Create Share" type="button">${CREATE_SHARE_ICON}<span>Create Share</span></button>', PAGE)
        self.assertIn("document.getElementById('create-nas-share')?.addEventListener('click',openNasShareWizard)", PAGE)

    def test_new_icons_match_supplied_svg_geometry(self):
        self.assertIn("const STOP_SHARING_ICON=", PAGE)
        self.assertIn("const REPAIR_ACCESS_ICON=", PAGE)
        self.assertIn("M18 14.16a2.87 2.87 0 0 0-1.62 4", PAGE)
        self.assertIn("m16.51 14.52", PAGE)
        self.assertIn("M14.82 4.13c1.42-1.42", PAGE)
        self.assertIn("m15.06 11.77", PAGE)
        self.assertIn("const EDIT_SHARE_ICON=", PAGE)
        self.assertIn("const DELETE_FOLDER_ICON=", PAGE)

    def test_buttons_are_text_and_icon_with_correct_order(self):
        share_region = PAGE.split("}else if(page==='Shares'){", 1)[1].split(
            "} else if(page==='Users'){", 1)[0]
        actions = share_region.split('<div class="share-actions">', 1)[1].split('</div></div>', 1)[0]
        names = ("data-edit-share=", "data-stop-share=",
                 "data-repair-share=", "data-delete-folder=")
        for term in names:
            self.assertEqual(actions.count(term), 1, term)
        self.assertEqual(sorted(actions.index(term) for term in names),
                         [actions.index(term) for term in names])
        for label in ("Edit Share", "Stop Sharing", "Repair Access", "Delete Folder"):
            self.assertIn("<span>"+label+"</span>", actions)
        for icon in ("${EDIT_SHARE_ICON}", "${STOP_SHARING_ICON}",
                     "${REPAIR_ACCESS_ICON}", "${DELETE_FOLDER_ICON}"):
            self.assertIn(icon, actions)
        self.assertEqual(actions.count('button-with-icon'), 4)
        self.assertEqual(actions.count('action-icon-btn'), 3)
        self.assertIn('delete-folder-action', actions)
        self.assertIn('type="button"', actions)

    def test_legacy_migration_kept_separate_from_four_actions(self):
        share_region = PAGE.split("}else if(page==='Shares'){", 1)[1].split(
            "} else if(page==='Users'){", 1)[0]
        self.assertIn('data-migrate-share=', share_region)
        self.assertIn('share-legacy-action', share_region)
        self.assertLess(share_region.index('share-legacy-action'),
                        share_region.index('<div class="share-actions">'))
        self.assertNotIn('data-migrate-share=', share_region.split('<div class="share-actions">', 1)[1].split('</div></div>', 1)[0])

    def test_shared_hover_and_click_handlers_are_unchanged(self):
        self.assertIn('.action-icon-btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff;filter:none}', PAGE)
        self.assertIn('.delete-folder-action:hover:not(:disabled){background:var(--danger);border-color:var(--danger);color:#fff}', PAGE)
        for selector, action in (
            ("data-edit-share", "editNasShare(b.dataset.editShare)"),
            ("data-stop-share", "stopNasSharing(b.dataset.stopShare)"),
            ("data-repair-share", "repairNasShare(b.dataset.repairShare)"),
            ("data-delete-folder", "deleteNasShareFolder(b.dataset.deleteFolder)"),
        ):
            self.assertIn(f"querySelectorAll('[{selector}]')", PAGE)
            self.assertIn(action, PAGE)


if __name__ == "__main__":
    unittest.main()
