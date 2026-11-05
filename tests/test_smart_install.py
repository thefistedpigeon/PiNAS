"""Ensure PiNAS installs its SMART monitoring dependency on a fresh system."""
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
INSTALLER=(ROOT/'src/pinas/installer.py').read_text(encoding='utf-8')
HELPERS=(ROOT/'src/pinas/privileged_helpers.py').read_text(encoding='utf-8')

class SmartInstallationTests(unittest.TestCase):
    def test_fresh_install_includes_smartmontools(self):
        start=INSTALLER.index("subprocess.run(['apt-get','install','-y'")
        stop=INSTALLER.index("],check=True,env=apt_env)",start)
        install=INSTALLER[start:stop]
        self.assertIn("'smartmontools'",install)

    def test_smart_health_checks_for_smartctl(self):
        self.assertIn("shutil.which('smartctl')",HELPERS)

if __name__=='__main__':
    unittest.main()
