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
        self.assertIn('id="refresh-disk-health"',PAGE)
        self.assertIn("if(page==='Storage')",PAGE)

    def test_smart_checked_only_on_overview_and_button(self):
        self.assertEqual(PAGE.count("fetch('/api/smart-health'"),1)
        self.assertIn("if(page==='Overview'){document.getElementById('refresh-service-health')",PAGE)
        self.assertIn("addEventListener('click',checkSmartHealth)",PAGE)
        self.assertIn("displayDiskHealth();checkSmartHealth()",PAGE)
        self.assertIn('const entries=new Map(',PAGE)
        self.assertIn('entries.get(panel.dataset.smartDevice)',PAGE)
        self.assertIn("!result.installed?",PAGE)
        self.assertIn("health==='Healthy'",PAGE)
        self.assertIn("health==='Warning'",PAGE)

if __name__=='__main__':
    unittest.main()
