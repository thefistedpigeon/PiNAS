"""v1.0.6 overview SMART and health layout regression checks."""
import ast
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
UI=(ROOT/'src/pinas/web_ui.py').read_text(encoding='utf-8')
CORE=(ROOT/'src/pinas/core.py').read_text(encoding='utf-8')
tree=ast.parse(UI)
PAGE=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
          and any(isinstance(t,ast.Name) and t.id=='PAGE' for t in n.targets))

class OverviewDiskHealthTests(unittest.TestCase):
    def test_system_health_load_average_removed(self):
        self.assertNotIn('Load average (1 / 5 / 15 min)',PAGE)
        self.assertNotIn('health-load',PAGE)
        self.assertNotIn('os.getloadavg()',CORE)

    def test_per_disk_health_is_inside_storage_summary(self):
        start=PAGE.index('function diskSummary(){')
        end=PAGE.index('function render(){',start)
        function=PAGE[start:end]
        self.assertIn('data-smart-device=',function)
        self.assertIn('data-smart-status',function)
        self.assertIn('data-smart-temp',function)
        self.assertIn('Temperature:',function)
        self.assertIn('Health:',function)

    def test_storage_page_no_longer_has_disk_health_section(self):
        self.assertNotIn('<h2>Disk health</h2>',PAGE)
        self.assertNotIn('id="smart-health-results"',PAGE)
        self.assertNotIn('id="check-smart-health"',PAGE)
        self.assertNotIn('id="refresh-disk-health"',PAGE)
        self.assertIn("if(page==='Storage')",PAGE)

    def test_disk_health_card_stays_in_overview_without_buttons(self):
        self.assertIn('class="chart-title storage-summary-heading"',PAGE)
        self.assertNotIn('<span>Check disk health</span>',PAGE)
        self.assertNotIn('id="refresh-disk-health-storage"',PAGE)
        self.assertIn('.storage-summary-heading{padding-bottom:16px;margin-bottom:14px;',PAGE)

    def test_hover_has_accent_colour_and_icon_inheritance(self):
        self.assertIn('.storage-summary-heading .btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff;filter:none}',PAGE)
        self.assertIn('fill="currentColor"',PAGE)
        self.assertIn('stroke="currentColor"',PAGE)

    def test_update_and_service_buttons_use_shared_hover_and_supplied_icons(self):
        self.assertIn('class="btn outline button-with-icon action-icon-btn" id="apply-pinas-update"',PAGE)
        self.assertIn('class="btn outline button-with-icon action-icon-btn" id="refresh-service-health"',PAGE)
        self.assertIn('<span>Install selected update</span>',PAGE)
        self.assertIn('<span>Refresh</span>',PAGE)
        self.assertIn('M17.7 8.57H13',PAGE)
        self.assertIn('M20.62 7.9c-3.12-4.09',PAGE)
        self.assertIn('.action-icon-btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff;filter:none}',PAGE)
        self.assertIn('.action-icon-btn svg{display:block;width:22px;height:22px;flex:none}',PAGE)
        self.assertIn("field('apply-pinas-update').onclick=async()=>",PAGE)
        self.assertIn("document.getElementById('refresh-service-health')?.addEventListener('click',refreshServiceHealth)",PAGE)

    def test_upgrade_reloads_when_new_instance_appears(self):
        self.assertIn("fetch('/api/pinas-build',{cache:'no-store',credentials:'same-origin'})",PAGE)
        self.assertIn("current!==previousInstance",PAGE)
        self.assertIn("window.location.reload()",PAGE)
        self.assertIn("watchPinasUpgradeRestart(previousInstance,field('pinas-update-status'),msg,button)",PAGE)
        self.assertIn("const previousInstance=await readPinasServiceInstance();",PAGE)
        self.assertLess(PAGE.index("const previousInstance=await readPinasServiceInstance();"),
                        PAGE.index("await post('/api/pinas-upgrade',{admin_password:pw"))
        self.assertNotIn("checks++>40",PAGE)

    def test_service_restart_probe_is_minimal_and_cache_bypassed(self):
        core=(ROOT/'src/pinas/core.py').read_text(encoding='utf-8')
        api=(ROOT/'src/pinas/http_api.py').read_text(encoding='utf-8')
        self.assertIn("SERVER_INSTANCE=secrets.token_hex(16)",core)
        self.assertIn("if path=='/api/pinas-build':self.json({'version':VERSION,'instance':SERVER_INSTANCE});return",api)
        self.assertIn("self.send_header('Cache-Control',cache_control)",api)

    def test_smart_automatically_checks_overview_storage_and_10_min_periodically(self):
        self.assertEqual(PAGE.count("fetch('/api/smart-health'"),1)
        self.assertIn("if(page==='Overview'){document.getElementById('refresh-service-health')",PAGE)
        self.assertIn('function autoDiskHealth()',PAGE)
        self.assertIn('refreshServiceHealth();autoDiskHealth()',PAGE)
        self.assertIn('bindStorageScans();autoDiskHealth()',PAGE)
        self.assertIn('Date.now()-diskSmartLastChecked>=600000',PAGE)
        self.assertIn("setInterval(()=>{if(['Overview','Storage'].includes(page)",PAGE)
        self.assertIn('const entries=new Map(',PAGE)
        self.assertIn('entries.get(panel.dataset.smartDevice)',PAGE)
        self.assertIn("!result.installed?",PAGE)
        self.assertIn("health==='Healthy'",PAGE)
        self.assertIn("health==='Warning'",PAGE)

if __name__=='__main__':
    unittest.main()
