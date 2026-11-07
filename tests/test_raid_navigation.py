"""RAID navigation visibility follows safe physical-disk discovery."""
import ast
import json
import pathlib
import re
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "pinas" / "web_ui.py"


def ui_script():
    tree = ast.parse(WEB.read_text(encoding="utf-8"))
    return next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "PAGE"
                        for target in node.targets))


class RaidNavigationTests(unittest.TestCase):
    def test_navigation_uses_same_disks_as_raid_planner(self):
        script = ui_script()
        self.assertIn("if(raidPageAvailable())items.push('RAID')", script)
        self.assertIn("const available=raidEligibleDisks();", script)
        self.assertIn("raidEligibleDisks().length>=2||(info.raid||[]).length>0", script)
        self.assertIn("['Overview','Storage','RAID'].includes(page)", script)

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for browser-script checks")
    def test_raid_tab_only_for_two_usable_disks_or_an_existing_array(self):
        script = ui_script()
        declarations = []
        for name in ("disks", "raidEligibleDisks", "raidPageAvailable", "navItems"):
            found = re.search(r"const " + name + r"=\(\)=>[^\n]+", script)
            self.assertIsNotNone(found, name)
            declarations.append(found.group(0))
        disk = lambda name, **extra: dict({"name":name, "path":"/dev/" + name,
                                              "type":"disk", "size":500_000_000_000,
                                              "read_only":False}, **extra)
        cases = [
            ({"disks": []}, False),
            ({"disks": [disk("sda")]}, False),
            ({"disks": [disk("sda"), disk("sdb")]}, True),
            ({"disks": [disk("sda"), disk("zram0")]}, False),
            ({"disks": [disk("sda"), disk("loop1")]}, False),
            ({"disks": [disk("sda"), disk("sdb", read_only=True)]}, False),
            ({"disks": [disk("sda"), disk("sdb", size=0)]}, False),
            ({"disks": [disk("sda"), {"name":"sda1", "path":"/dev/sda1",
                                      "type":"part", "size":1000}]}, False),
            ({"disks": [disk("sda")], "raid": [{"name":"md0", "degraded":1}]}, True),
        ]
        # Hardware discovery removes root/boot backing disks before this inventory.
        core = (ROOT / "src" / "pinas" / "core.py").read_text(encoding="utf-8")
        self.assertIn("system_mounts={'/','/boot','/boot/firmware','/boot/efi'}", core)
        self.assertIn("root.get('name') in system_names", core)
        js = ("let info={};const storageReady=()=>false;\n"
              + "\n".join(declarations) + "\n"
              + "const inputs=" + json.dumps([entry for entry, _ in cases]) + ";\n"
              + "process.stdout.write(JSON.stringify(inputs.map(item=>"
                "{info=item;return navItems().includes('RAID')})));")
        result = subprocess.run(["node", "-e", js], text=True,
                                capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout), [expected for _, expected in cases])


if __name__ == "__main__":
    unittest.main()
