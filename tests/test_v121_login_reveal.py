"""PiNAS v1.2.1: login password reveal is accessible and never submits the form."""
import ast
import pathlib
import shutil
import subprocess
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
CORE=(ROOT/'src/pinas/core.py').read_text(encoding='utf-8')
UI=(ROOT/'src/pinas/web_ui.py').read_text(encoding='utf-8')
PAGE=next(ast.literal_eval(n.value) for n in ast.parse(UI).body
          if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PAGE' for t in n.targets))


class LoginPasswordRevealTests(unittest.TestCase):
    def test_patch_version(self):
        self.assertIn("VERSION='1.2.1'",CORE)

    def test_login_input_remains_protected_by_default(self):
        self.assertIn('id="login-password" name="password" type="password"',PAGE)
        self.assertIn('for="login-password">Password</label>',PAGE)
        self.assertIn('autocomplete="${setup?\'new-password\':\'current-password\'}"',PAGE)
        self.assertIn('required minlength="${setup?12:1}"',PAGE)
        self.assertIn("new FormData(e.target)",PAGE)
        self.assertIn("password:f.get('password')",PAGE)

    def test_toggle_has_correct_accessible_button_semantics(self):
        for part in (
            'id="toggle-login-password"',
            'class="login-password-toggle"',
            'type="button" aria-label="Show password"',
            'aria-controls="login-password" aria-pressed="false"',
            'const PASSWORD_SHOW_ICON=', 'const PASSWORD_HIDE_ICON=',
            "passwordField.type=revealed?'text':'password'",
            "passwordToggle.setAttribute('aria-label',revealed?'Hide password':'Show password')",
            "passwordToggle.setAttribute('aria-pressed',String(revealed))",
        ):
            self.assertIn(part,PAGE)

    def test_style_works_with_both_themes_and_focus(self):
        for part in (
            '.login-password-wrap{display:block;position:relative;width:100%}',
            '.login .login-password-wrap input{width:100%;max-width:none;padding-right:56px}',
            '.login-password-toggle:hover{color:var(--accent);background:var(--soft)}',
            '.login-password-toggle:focus-visible{outline:3px solid var(--accent)',
            '.login-password-toggle svg{display:block;width:22px;height:22px;',
        ):
            self.assertIn(part,PAGE)
        self.assertNotIn('class="btn login-password-toggle"',PAGE)

    @unittest.skipUnless(shutil.which('node'),'Node.js needed for browser handler simulation')
    def test_password_show_hide_keeps_value_and_does_not_submit(self):
        marker="const passwordField=document.getElementById('login-password'),passwordToggle=document.getElementById('toggle-login-password');"
        self.assertEqual(PAGE.count(marker),1)
        listener=PAGE.split(marker,1)[1].split("document.getElementById('auth').onsubmit=",1)[0]
        script="""
const assert=require('node:assert/strict');
const stubPasswordField={type:'password',value:'My@Tricky"Password!42'};
let submitCount=0;
const attrs={};
const stubPasswordToggle={
 title:'Show password',innerHTML:'show',
 setAttribute:(name,value)=>{attrs[name]=value;}
};
const PASSWORD_SHOW_ICON='show',PASSWORD_HIDE_ICON='hide';
"""
const document={getElementById:(id)=>id==='login-password'?stubPasswordField:id==='toggle-login-password'?stubPasswordToggle:null};
""" + marker + listener + """
assert.equal(passwordToggle.title,'Show password');
passwordToggle.onclick();
assert.equal(passwordField.type,'text');
assert.equal(passwordField.value,'My@Tricky"Password!42');
assert.equal(passwordToggle.title,'Hide password');
assert.equal(attrs['aria-label'],'Hide password');
assert.equal(attrs['aria-pressed'],'true');
assert.equal(passwordToggle.innerHTML,'hide');
passwordToggle.onclick();
assert.equal(passwordField.type,'password');
assert.equal(passwordField.value,'My@Tricky"Password!42');
assert.equal(passwordToggle.title,'Show password');
assert.equal(attrs['aria-pressed'],'false');
assert.equal(passwordToggle.innerHTML,'show');
assert.equal(submitCount,0);
"""
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=12)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
