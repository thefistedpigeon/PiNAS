"""Visual consistency and unchanged interaction guards for the seven action buttons."""
import ast
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
UI=(ROOT/'src/pinas/web_ui.py').read_text(encoding='utf-8')
PAGE=next(ast.literal_eval(node.value) for node in ast.parse(UI).body
          if isinstance(node,ast.Assign) and
          any(isinstance(target,ast.Name) and target.id=='PAGE' for target in node.targets))

class ButtonVisualConsistency(unittest.TestCase):
    def test_shared_button_css_controls_hover(self):
        self.assertIn('.button-with-icon{display:inline-flex;align-items:center;justify-content:center;gap:9px}',PAGE)
        self.assertIn('.action-icon-btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff;filter:none}',PAGE)
        self.assertIn('.action-icon-btn svg{display:block;width:22px;height:22px;flex:none}',PAGE)

    def test_storage_manage_button_retains_disk_index_and_click_handler(self):
        self.assertIn('class="btn outline button-with-icon action-icon-btn storage-action" data-disk="${i}"',PAGE)
        self.assertIn('<span>Manage Disk</span>',PAGE)
        self.assertIn("document.querySelectorAll('[data-disk]').forEach(b=>b.onclick=()=>openDiskWizard(Number(b.dataset.disk)))",PAGE)
        self.assertIn('M20.88 5.23v13.73',PAGE)

    def test_destructive_buttons_require_confirmed_authorisation(self):
        self.assertIn("{title:'Wipe Disk',icon:'wipe',id:'disk-wipe'",PAGE)
        self.assertIn("{title:'Format Disk',icon:'format',id:'disk-format'",PAGE)
        self.assertIn("disabled:false",PAGE)
        self.assertIn("function confirmDestructiveDisk(d,action)",PAGE)
        self.assertIn('id="disk-danger-yes" type="checkbox" required',PAGE)
        self.assertIn('id="disk-danger-password" type="password"',PAGE)
        self.assertIn("submit.disabled=!(check.checked&&password.value.length)",PAGE)
        self.assertIn("action,device:d.path,expected_size:Number(d.size),filesystem:approved.filesystem,confirm:true,admin_password:approved.admin_password",PAGE)
        self.assertIn("overlay.querySelector('#disk-mount').onclick=",PAGE)
        self.assertIn("DISK_ACTION_ICONS[o.icon]",PAGE)
        self.assertIn('M14.62 3.74L9.4 8.98',PAGE)
        self.assertIn('M15.84 6.27c-1.36-1.78',PAGE)
        self.assertIn('M12 3.19v6.33',PAGE)

    def test_raid_button_preserves_existing_planner(self):
        self.assertIn('id="raid-create" type="button"',PAGE)
        self.assertIn('<span>Configure RAID</span>',PAGE)
        self.assertIn("document.getElementById('raid-create')?.addEventListener('click',openRaidWizard)",PAGE)
        self.assertIn('m6.68-16.23v6.15',PAGE)

    def test_updates_buttons_preserve_ids_and_callbacks(self):
        self.assertIn('id="refresh-update-service-health" type="button"',PAGE)
        self.assertIn('<span>Refresh</span>',PAGE)
        self.assertIn("document.getElementById('refresh-update-service-health')?.addEventListener('click',loadUpdateUnitHealth)",PAGE)
        self.assertIn('id="save-update-history" type="button"',PAGE)
        self.assertIn('<span>Save</span>',PAGE)
        self.assertIn("saveHistory.onclick=async()=>",PAGE)
        self.assertIn("action:'history-retention',months",PAGE)
        self.assertIn('M20.38 8.6c-2.24-3.19',PAGE)
        self.assertIn('M4.71 20.95c-.93',PAGE)

if __name__=='__main__':
    unittest.main()
