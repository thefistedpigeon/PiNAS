"""PiNAS v1.0.7 update history, automatic update service health and recovery."""
import ast
import json
import pathlib
import sqlite3
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
CORE=(ROOT/'src/pinas/core.py').read_text()
API=(ROOT/'src/pinas/http_api.py').read_text()
INSTALLER=(ROOT/'src/pinas/installer.py').read_text()
WEB=(ROOT/'src/pinas/web_ui.py').read_text()
PAGE=next(ast.literal_eval(n.value) for n in ast.parse(WEB).body
          if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PAGE' for t in n.targets))
HELPER=next(ast.literal_eval(n.value) for n in ast.parse(API).body
          if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APT_INDEX_HELPER' for t in n.targets))

class UpdateHistoryTests(unittest.TestCase):
    def test_helper_syntax_and_restricted_commands(self):
        compile(HELPER,'pinas-apt-index','exec')
        self.assertIn("args[0]=='restart-auto' and args[1] in UNITS",HELPER)
        self.assertIn("args[0]=='prune' and args[1] in ('6','12')",HELPER)
        self.assertIn("record('automatic','failed'",HELPER)
        self.assertIn("upgrade('manual')",HELPER)
        self.assertIn("upgrade('automatic')",HELPER)

    def test_log_is_separate_and_bounded(self):
        self.assertIn("DB_DIR=Path('/var/lib/pinas-update-history')",HELPER)
        self.assertIn("DB=DB_DIR/'updates.sqlite3'",HELPER)
        self.assertIn("LIMIT 2000",HELPER)
        self.assertIn("PRAGMA auto_vacuum=INCREMENTAL",HELPER)
        self.assertIn("os.chmod(DB,0o640)",HELPER)
        self.assertIn("os.chmod(DB_DIR,0o750)",HELPER)
        self.assertIn("summary[-800:]",HELPER)
        self.assertIn("sorted(packages)[:120]",HELPER)

    def test_sqlite_record_and_retention(self):
        scope={'__name__':'update_helper_test'}
        exec(compile(HELPER,'pinas-apt-index','exec'),scope)
        with tempfile.TemporaryDirectory() as tmp:
            db_dir=pathlib.Path(tmp)/'history'
            scope['DB_DIR']=db_dir
            scope['DB']=db_dir/'updates.sqlite3'
            scope['CFG']=pathlib.Path(tmp)/'config.json'
            scope['CFG'].write_text(json.dumps({'update_history_months':6}))
            # CI runs as a regular user; no ownership changes are required here.
            with mock.patch.object(scope['os'],'chown'),mock.patch.object(scope['grp'],'getgrnam',return_value=types.SimpleNamespace(gr_gid=0)):
                scope['record']('manual','success',int(time.time()),{'samba','curl'},'Installed updates')
                with sqlite3.connect(scope['DB']) as connection:
                    rows=connection.execute('SELECT source,result,packages,summary FROM update_events').fetchall()
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0][0:2],('manual','success'))
                self.assertEqual(json.loads(rows[0][2]),['curl','samba'])
                with scope['database']() as db:
                    db.execute('INSERT INTO update_events(started_at,completed_at,source,result,packages,summary) VALUES(?,?,?,?,?,?)',
                               (int(time.time())-400*86400,int(time.time())-400*86400,'automatic','failed','[]','Old event'))
                    scope['prune'](db,6)
                with sqlite3.connect(scope['DB']) as connection:
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM update_events').fetchone()[0],1)

    def test_service_health_distinguishes_oneshot_idle_from_failure(self):
        self.assertIn("'pinas-auto-updates.timer'",CORE)
        self.assertIn("'pinas-auto-updates.service'",CORE)
        self.assertIn("item.update(state='healthy',detail='Last run succeeded or waiting for next schedule')",CORE)
        self.assertIn("item['restart_action']='timer' if unit.endswith('.timer') else 'service'",CORE)
        self.assertIn("Automatic updates disabled in schedule",CORE)

    def test_api_requires_admin_and_password_to_restart(self):
        self.assertIn("if action=='restart-auto':",API)
        self.assertIn("if unit not in ('timer','service')",API)
        self.assertIn("verify(pw,(admin_record(cfg,s['username']) or {}).get('password',''))",API)
        self.assertIn("item.get('restart_action')!=unit",API)
        self.assertIn("if action=='history-retention':",API)
        self.assertIn("type(months) is not int or months not in (6,12)",API)
        self.assertIn("result['history']=update_history()",API)
        self.assertIn("result['history_months']=load().get('update_history_months',6)",API)

    def test_gui_installer_updates_privileged_helper(self):
        self.assertIn("('pinas-apt-index',APT_INDEX_HELPER",INSTALLER)
        self.assertIn('"restart-auto timer","restart-auto service"',INSTALLER)
        self.assertIn('"prune 6","prune 12"',INSTALLER)

    def test_ui_displays_history_and_guarded_restart(self):
        for expected in ('Installed update history','update-history-months','update-history-list',
                         'data-restart-auto','Automatic update service health','loadUpdateUnitHealth()'):
            self.assertIn(expected,PAGE)
        self.assertIn("fileTextDialog({title:'Restart automatic updates'",PAGE)
        self.assertIn("action:'restart-auto',unit,admin_password:password",PAGE)
        self.assertIn("action:'history-retention',months",PAGE)
        self.assertIn("esc(item.summary||'No summary available')",PAGE)

if __name__=='__main__':
    unittest.main()
