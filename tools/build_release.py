#!/usr/bin/env python3
"""Build the standalone, self-extracting pinas.py from modular source parts."""
import ast
import base64
import json
import pathlib
import re
import sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
FONT_FILES=('ClearSans-Regular.woff','ClearSans-Medium.woff','ClearSans-Bold.woff',
            'SourceCodePro-Regular.woff2','SourceCodePro-Bold.woff2')
NAMES=('core.py','web_ui.py','storage_breakdown.py','http_api.py','privileged_helpers.py','media_server.py','installer.py')
def build():
    parts={name:(ROOT/'src'/'pinas'/name).read_text(encoding='utf-8') for name in NAMES}
    version=re.search(r"^VERSION='([^']+)'",parts['core.py'],re.M)
    if not version:raise SystemExit('Missing PiNAS VERSION')
    for name,source in parts.items():
        # web_ui.py intentionally starts with PAGE assignment and helper strings
        # are compiled after expansion into the common PiNAS execution namespace.
        ast.parse(source,filename=name)
    payload=json.dumps(parts,ensure_ascii=True)
    font_assets={name:base64.b64encode((ROOT/'assets'/'fonts'/name).read_bytes()).decode('ascii') for name in FONT_FILES}
    font_payload=json.dumps(font_assets,ensure_ascii=True)
    out=("#!/usr/bin/env python3\n"
         '"""PiNAS portable standalone bundle; generated from src/pinas by tools/build_release.py."""\n'
         "import json as _bundle_json\n"
         "VERSION="+repr(version.group(1))+"\n"
         "def install(args):\n"
         '    """Top-level installer entry recognised by existing PiNAS updater validation."""\n'
         "    raise RuntimeError('PiNAS embedded modules failed to load')\n"
         "PINAS_FONT_ASSETS = "+font_payload+"\n"
         "PINAS_SOURCE_PARTS = "+payload+"\n"
         "for _module_name, _module_source in PINAS_SOURCE_PARTS.items():\n"
         "    exec(compile(_module_source, 'pinas/'+_module_name, 'exec'), globals())\n"
         "if __name__=='__main__':\n"
         "    main()\n")
    ast.parse(out,filename='pinas.py')
    output=ROOT/'pinas.py'
    if '--check' in sys.argv:
        actual=output.read_text(encoding='utf-8')
        if actual!=out:raise SystemExit('pinas.py differs from generated release output; rebuild the release')
        print('Release bundle matches source modules')
    else:
        output.write_text(out,encoding='utf-8')
        output.chmod(0o755)
        print('Built',output,'('+str(len(out.encode()))+' bytes)')
if __name__=='__main__':build()
