"""PiNAS 1.1.2: activity-only session renewal and weekly update retention."""
import ast
import json
import pathlib
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
CORE=(ROOT/'src/pinas/core.py').read_text(encoding='utf-8')
API=(ROOT/'src/pinas/http_api.py').read_text(encoding='utf-8')
PAGE=next(ast.literal_eval(n.value) for n in ast.parse((ROOT/'src/pinas/web_ui.py').read_text()).body
          if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PAGE' for t in n.targets))

class QualityOfLifeTests(unittest.TestCase):
    def core_scope(self):
        scope={'__name__':'pinas_qol_test'}
        exec(compile(CORE,'core.py','exec'),scope)
        return scope

    def test_default_history_is_twelve_weeks_and_values_are_bounded(self):
        ns=self.core_scope()
        valid=ns['valid_history_weeks']
        for value in (1,12,52):
            self.assertEqual(valid(value),value)
        for value in (0,53,-1,True,'12',None):
            self.assertEqual(valid(value),12)
        self.assertIn("type(weeks) is not int or not 1<=weeks<=52",API)
        self.assertIn("args[1].isdigit() and 1<=int(args[1])<=52",API)
        self.assertIn("latest.pop('update_history_months',None)",API)

    def test_history_reader_enforces_retention_immediately(self):
        ns=self.core_scope()
        now=int(time.time())
        with tempfile.TemporaryDirectory() as folder:
            dbpath=pathlib.Path(folder)/'updates.sqlite3'
            with sqlite3.connect(dbpath) as db:
                db.execute("""CREATE TABLE update_events (
                    id INTEGER PRIMARY KEY, started_at INTEGER, completed_at INTEGER,
                    source TEXT, result TEXT, packages TEXT, summary TEXT)""")
                for age in (3,30,100):
                    db.execute("INSERT INTO update_events(started_at,completed_at,source,result,packages,summary) VALUES (?,?,?,?,?,?)",
                               (now-age*86400,now-age*86400,'manual','success','[]','ok'))
            ns['UPDATE_HISTORY_DB']=dbpath
            ns['load']=lambda:{'update_history_weeks':12}
            rows=ns['update_history']()
            self.assertEqual(len(rows),2)
            ns['load']=lambda:{'update_history_weeks':1}
            self.assertEqual(len(ns['update_history']()),1)

    def test_background_get_does_not_renew_server_session(self):
        ns=self.core_scope()
        exec(compile(API,'http_api.py','exec'),ns)
        handler=ns['Handler'].__new__(ns['Handler'])
        handler.headers={'Cookie':'pinas_session=valid'}
        ns['SESSIONS']={'valid':{'expires':1100.0,'role':'admin','csrf':'token'}}
        ns['load']=lambda:{'session_timeout':5}
        with mock.patch.object(ns['time'],'time',return_value=1000.0):
            handler.command='GET'
            self.assertEqual(handler.session()[0],'valid')
            self.assertEqual(ns['SESSIONS']['valid']['expires'],1100.0)
            handler.command='POST'
            self.assertEqual(handler.session()[0],'valid')
            self.assertEqual(ns['SESSIONS']['valid']['expires'],1300.0)
        with mock.patch.object(ns['time'],'time',return_value=1301.0):
            self.assertEqual(handler.session(),('' ,None))
            self.assertNotIn('valid',ns['SESSIONS'])

    def test_browser_redirects_on_idle_and_unauthenticated_results(self):
        for needle in (
            "setInterval(checkSessionIdle,1000)",
            "Date.now()-lastUserAction>=sessionIdleMs()",
            "window.location.replace('/')",
            "fetch('/api/session-touch'",
            "lastActivitySync<30000",
            "if(!j.authenticated){returnToLogin();return}",
            "if(r.status===403&&/authentication required|access required/i.test(j.error||''))returnToLogin()",
        ):
            self.assertIn(needle,PAGE)
        self.assertIn("if self.command=='POST':s['expires']",API)

    def test_smart_is_automatic_and_history_cards_are_collapsed(self):
        for needle in ("autoDiskHealth()", "diskSmartLastChecked>=600000",
                       "function diskSmartMessage(message)",
                       'id="update-history-weeks"',
                       'Array.from({length:52}',"date.toLocaleDateString()",
                       '<details class="update-history-row">',
                       "packages.map(name=>", "esc(item.summary||'No summary available')"):
            self.assertIn(needle,PAGE)
        self.assertNotIn('id="refresh-disk-health"',PAGE)
        self.assertNotIn('id="refresh-disk-health-storage"',PAGE)

if __name__=='__main__':
    unittest.main()
