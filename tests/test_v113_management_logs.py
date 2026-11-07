"""PiNAS v1.1.3 — update logs, account removal, and split share deletion."""
import ast
import pathlib
import tempfile
import time
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
CORE=(ROOT/'src/pinas/core.py').read_text(encoding='utf-8')
API=(ROOT/'src/pinas/http_api.py').read_text(encoding='utf-8')
UI=(ROOT/'src/pinas/web_ui.py').read_text(encoding='utf-8')
INSTALL=(ROOT/'src/pinas/installer.py').read_text(encoding='utf-8')
PAGE=next(ast.literal_eval(n.value) for n in ast.parse(UI).body
          if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PAGE' for t in n.targets))
HELPERS={node.targets[0].id:ast.literal_eval(node.value)
         for node in ast.parse(API).body if isinstance(node,ast.Assign)
         and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)
         and node.targets[0].id in ('NAS_USER_HELPER','NAS_SHARE_HELPER')}

class ManagementLogsTests(unittest.TestCase):
    def test_release_version(self):
        self.assertIn("VERSION='1.1.3'",CORE)

    def test_log_export_includes_all_retained_records(self):
        self.assertIn("if path=='/api/update-history-download':",API)
        self.assertIn("update_history(limit=2000)",API)
        self.assertIn("min(max(int(limit),1),2000)",CORE)
        self.assertIn("text/plain; charset=utf-8",API)
        self.assertIn("download_filename=filename",API)
        self.assertIn("sess.get('role')!='admin'",API)
        self.assertIn("Cache-Control",API)
        self.assertIn("download-update-logs",PAGE)
        self.assertIn("URL.createObjectURL(file)",PAGE)
        self.assertIn("URL.revokeObjectURL(url)",PAGE)

    def test_log_export_formatter(self):
        tree=ast.parse(CORE)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
                and n.name=='format_update_history')
        module=ast.Module(body=[fn],type_ignores=[])
        ns={'time':time}
        exec(compile(module,'core_formatter.py','exec'),ns)
        output=ns['format_update_history']([{
            'started_at':1700000000,'source':'manual','result':'success',
            'packages':['samba','curl'],'summary':'Setting up samba'
        },{
            'started_at':1700086400,'source':'automatic','result':'failed',
            'packages':[],'summary':'APT failed'
        }],12,1700172800)
        self.assertIn('Installed Update History',output)
        self.assertIn('Retention: 12 weeks',output)
        self.assertIn('Records: 2',output)
        for expected in ('Type: Manual','Type: Automatic','Result: Installed',
                         'Result: Failed','  - samba','  - curl','Setting up samba','APT failed'):
            self.assertIn(expected,output)
        self.assertIn('No update installations recorded',ns['format_update_history']([],1,1700172800))

    def test_user_removal_requires_password_and_share_detachment(self):
        helper=HELPERS['NAS_USER_HELPER']
        compile(helper,'pinas-nas-user','exec')
        for term in ("sys.argv[1]=='remove'", "account.pw_uid<1000",
                     "account.pw_gid!=group.gr_gid","pinas-nas", "name in item['access']",
                     "['/usr/bin/smbpasswd','-x',name]", "['/usr/sbin/userdel',name]"):
            self.assertIn(term,helper)
        self.assertIn("'remove *'",INSTALL.replace('"remove *"',"'remove *'"))
        for term in ("if path=='/api/remove-user':","data.get('confirm_name')!=username",
                     "data.get('confirm')!='REMOVE USER'",
                     "username==cfg.get('admin_user','admin')",
                     "username==s['username']", "remove_nas_user(username)",
                     "values.pop(username,None)","SESSIONS.pop(key,None)"):
            self.assertIn(term,API)
        self.assertIn("('user' if kind=='nas' else 'admin')",API)

    def test_user_controls_have_supplied_icon_and_confirmation(self):
        for term in ("const REMOVE_USER_ICON=", "data-remove-nas=", "data-remove-admin=",
                     "function removePinasUser(kind,name)", "m16.71 16.65",
                     "confirm:'REMOVE USER'", "if(form.get('confirm_name')!==name)"):
            self.assertIn(term,PAGE)
        self.assertIn("data-remove-nas",PAGE)
        self.assertIn("Remove the user from network share permissions first",PAGE)

    def test_stop_sharing_never_deletes_files(self):
        helper=HELPERS['NAS_SHARE_HELPER']
        compile(helper,'pinas-nas-share','exec')
        self.assertIn("('delete','delete-folder')",helper)
        self.assertIn("if removing_folder:",helper)
        self.assertIn("files_preserved':True",helper)
        self.assertIn("data-stop-share=",PAGE)
        self.assertIn("function stopNasSharing(name)",PAGE)
        self.assertNotIn("data-delete-share=",PAGE)
        self.assertIn("'/api/delete-share'",PAGE)

    def test_delete_folder_is_deliberate_and_confined(self):
        helper=HELPERS['NAS_SHARE_HELPER']
        for term in ("def safe_delete_folder(item,items):", "mount=check_volume(item.get('volume'))",
                     "if folder not in (modern,legacy):", "parent.is_symlink()",
                     "folder.is_symlink()","folder.stat().st_uid!=0",
                     "os.path.ismount(folder)", "os.walk(folder,followlinks=False",
                     "'--one-file-system','--',str(folder)", "timeout=600"):
            self.assertIn(term,helper)
        for term in ("if path=='/api/delete-folder':",
                     "data.get('confirm')!='DELETE FOLDER'",
                     "data.get('confirm_name')!=name",
                     "start_job(token,'delete-folder',delete_nas_share_folder,name)"):
            self.assertIn(term,API)
        for term in ("const DELETE_FOLDER_ICON=", "function deleteNasShareFolder(name)",
                     "data-delete-folder=", "confirm:'DELETE FOLDER'",
                     "Permanently delete", "share-remove-confirm"):
            self.assertIn(term,PAGE)
        self.assertIn('"delete-folder"',INSTALL)

    def test_rejects_arbitrary_delete_paths_before_touching_contents(self):
        scope={'__name__':'pinas_share_guard_test'}
        exec(compile(HELPERS['NAS_SHARE_HELPER'],'pinas-nas-share','exec'),scope)
        with tempfile.TemporaryDirectory() as temp:
            mount=pathlib.Path(temp)
            scope['check_volume']=lambda device:mount
            item={'name':'Media','volume':'/dev/sdb1','folder':'/etc'}
            with self.assertRaisesRegex(ValueError,'differs'):
                scope['safe_delete_folder'](item,[item])
            # A malicious symlink in the managed share root must be rejected.
            external=mount/'external';external.mkdir()
            (mount/'pinas-shares').symlink_to(external,target_is_directory=True)
            item['folder']=str(mount/'pinas-shares'/'Media')
            (external/'Media').mkdir()
            with self.assertRaisesRegex(ValueError,'protected root-owned'):
                scope['safe_delete_folder'](item,[item])

if __name__=='__main__':
    unittest.main()
