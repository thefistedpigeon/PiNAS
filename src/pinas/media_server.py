"""Optional on-demand MiniDLNA integration."""
import json as _media_json

def media_server_action(action,settings=None):
    if action not in ('status','install','save','start','stop','restart','rescan','grant','rebuild','setup-library'):
        raise ValueError('Unsupported media action')
    result=privileged_command('pinas-media-server',action,
        payload=_media_json.dumps(settings) if settings is not None else None,
        timeout=240 if action=='install' else 420 if action=='grant' else 60)
    if result.returncode:raise RuntimeError((result.stderr.strip() or 'Media server helper failed')[-700:])
    return _media_json.loads(result.stdout)

MEDIA_SERVER_HELPER = "#!/usr/bin/env python3\nimport json,os,pathlib,re,subprocess,sys,tempfile\nCONF=pathlib.Path('/etc/minidlna.conf')\nMEDIA_ROOT=pathlib.Path('/mnt/pinas')\nBOOL={'inotify','strict_dlna','enable_tivo','merge_media_dirs','enable_subtitles','enable_thumbnail','enable_thumbnail_filmstrip'}\nTEXT={'friendly_name','model_name','model_number','serial','uuid','presentation_url','album_art_names','force_sort_criteria','log_level','network_interface','tivo_discovery','root_container'}\nINT={'port':(1024,65535),'notify_interval':(30,86400),'max_connections':(1,100),'thumbnail_width':(64,1024),'thumbnail_quality':(1,10)}\nALLOWED=BOOL|TEXT|set(INT)|{'media_dir'}\ndef run(args,timeout=35,env=None):\n    return subprocess.run(args,capture_output=True,text=True,check=True,timeout=timeout,env=env)\ndef installed():\n    p=subprocess.run(['/usr/bin/dpkg-query','-W','-f=$'+'{Status}','minidlna'],capture_output=True,text=True,timeout=8)\n    return p.returncode==0 and p.stdout.strip()=='install ok installed'\ndef active():\n    p=subprocess.run(['/usr/bin/systemctl','is-active','minidlna.service'],capture_output=True,text=True,timeout=8)\n    return p.stdout.strip() if p.returncode==0 else 'inactive'\ndef settings():\n    result={}\n    if CONF.is_file():\n        for line in CONF.read_text().splitlines():\n            line=line.strip()\n            if not line or line.startswith('#') or '=' not in line:continue\n            key,val=line.split('=',1);key=key.strip()\n            if key=='media_dir':result.setdefault(key,[]).append(val.strip())\n            elif key in ALLOWED:result[key]=val.strip()\n    return result\ndef status():\n    present=installed()\n    print(json.dumps({'ok':True,'installed':present,'state':active() if present else 'not-installed','settings':settings() if present else {},'service':'minidlna.service'}))\ndef safe_path(value):\n    if not isinstance(value,str) or len(value)>320 or not value.startswith('/mnt/pinas/'):raise ValueError('Select a PiNAS media folder')\n    p=pathlib.Path(value)\n    if '..' in p.parts or any(x.is_symlink() for x in (p,*p.parents)) or not p.is_dir():raise ValueError('Invalid media folder')\n    mount=run(['/usr/bin/findmnt','-n','-o','TARGET','--target',value]).stdout.strip()\n    if pathlib.Path(mount).parent!=pathlib.Path('/mnt/pinas') or not p.resolve().is_relative_to(pathlib.Path(mount).resolve()):\n        raise ValueError('Media folder is not on a mounted PiNAS volume')\n    return value\ndef validate(data):\n    if not isinstance(data,dict) or set(data)-ALLOWED:raise ValueError('Unknown setting')\n    out={}\n    for key,val in data.items():\n        if key=='media_dir':\n            if not isinstance(val,list) or len(val)>16:raise ValueError('Maximum 16 media folders')\n            folders=[]\n            for entry in val:\n                if not isinstance(entry,dict) or set(entry)-{'path','type'} or entry.get('type') not in ('','A','V','P'):\n                    raise ValueError('Invalid media folder entry')\n                folders.append((entry['type']+',' if entry['type'] else '')+safe_path(entry.get('path')))\n            out[key]=list(dict.fromkeys(folders))\n        elif key in BOOL:\n            if type(val) is not bool:raise ValueError('Invalid '+key)\n            out[key]='yes' if val else 'no'\n        elif key in INT:\n            low,high=INT[key]\n            if type(val) is not int or not low<=val<=high:raise ValueError('Invalid '+key)\n            out[key]=str(val)\n        else:\n            if not isinstance(val,str) or len(val)>180 or any(c in val for c in '\\n\\r#'):raise ValueError('Invalid '+key)\n            if key=='friendly_name' and not val.strip():raise ValueError('Server name required')\n            if key=='network_interface' and val and not re.fullmatch(r'[a-zA-Z0-9_.-]{1,20}(,[a-zA-Z0-9_.-]{1,20}){0,5}',val):raise ValueError('Invalid network interface')\n            if key=='root_container' and val not in ('','.', 'B','M','V','P'):raise ValueError('Invalid root container')\n            if key=='tivo_discovery' and val not in ('','bonjour','beacon'):raise ValueError('Invalid TiVo discovery')\n            out[key]=val\n    return out\ndef atomic(content):\n    fd,tmp=tempfile.mkstemp(prefix='.pinas-minidlna-',dir=str(CONF.parent))\n    try:\n        os.fchmod(fd,0o644)\n        with os.fdopen(fd,'w') as f:f.write(content);f.flush();os.fsync(f.fileno())\n        os.replace(tmp,CONF)\n    finally:\n        if os.path.exists(tmp):os.unlink(tmp)\ndef save(data,emit_status=True):\n    if not installed() or not CONF.is_file():raise ValueError('MiniDLNA unavailable')\n    changes=validate(data);before=CONF.read_text()\n    lines=[]\n    for line in before.splitlines(keepends=True):\n        match=re.match(r'^\\s*([a-z_]+)\\s*=',line)\n        if not match or match.group(1) not in changes:lines.append(line)\n    if lines and not lines[-1].endswith('\\n'):lines.append('\\n')\n    lines.append('\\n# Settings managed by PiNAS\\n')\n    for key,val in sorted(changes.items()):\n        if key=='media_dir':\n            for folder in val:lines.append('media_dir='+folder+'\\n')\n        elif val!='':lines.append(key+'='+val+'\\n')\n    try:\n        atomic(''.join(lines))\n        run(['/usr/bin/systemctl','restart','minidlna.service'])\n        if active()!='active':raise RuntimeError('MiniDLNA failed to start')\n    except Exception:\n        atomic(before)\n        try:run(['/usr/bin/systemctl','restart','minidlna.service'])\n        except Exception:pass\n        raise\n    if emit_status:status()\n\ndef configured_media_folders():\n    folders=set()\n    for entry in settings().get('media_dir',[]):\n        path=entry.split(',',1)[1] if re.match(r'^[AVP],/',entry) else entry\n        folders.add(path)\n    return folders\ndef grant(data):\n    if not isinstance(data,dict) or set(data)!={'path'}:raise ValueError('Invalid permission request')\n    path=safe_path(data.get('path'))\n    if path not in configured_media_folders():raise ValueError('Save the media folder before granting read access')\n    mounts=run(['/usr/bin/findmnt','-rn','-o','TARGET']).stdout.splitlines()\n    if any(p==path or p.startswith(path.rstrip('/')+'/') for p in mounts):\n        raise ValueError('Media folder contains a separate mounted filesystem')\n    run(['/usr/bin/setfacl','-R','-m','u:minidlna:rX',path],timeout=180)\n    run(['/usr/bin/find',path,'-xdev','-type','d','-exec','/usr/bin/setfacl',\n         '-m','d:u:minidlna:rX','{}','+'],timeout=180)\n    print(json.dumps({'ok':True,'folder':path}))\ndef rebuild():\n    cache='/var/cache/minidlna'\n    if CONF.is_file():\n        for line in CONF.read_text().splitlines():\n            line=line.strip()\n            if not line or line.startswith('#') or '=' not in line:continue\n            key,val=line.split('=',1)\n            if key.strip()=='db_dir':cache=val.strip()\n    if cache not in ('/var/cache/minidlna','/var/lib/minidlna'):\n        raise ValueError('Custom cache directory; rebuild outside PiNAS')\n    directory=pathlib.Path(cache)\n    if directory.is_symlink() or not directory.is_dir():raise ValueError('Unsafe MiniDLNA cache directory')\n    index=directory/'files.db'\n    if index.is_symlink():raise ValueError('Unsafe MiniDLNA index file')\n    run(['/usr/bin/systemctl','stop','minidlna.service'])\n    try:\n        if index.exists():\n            if not index.is_file():raise ValueError('Unexpected MiniDLNA index type')\n            index.unlink()\n    finally:\n        run(['/usr/bin/systemctl','start','minidlna.service'],timeout=45)\n    status()\n\n\ndef configured_volume(value):\n    \"\"\"Return only an exact, mounted, writable PiNAS data volume.\"\"\"\n    if not isinstance(value,str) or len(value)>160:raise ValueError('Select an available data volume')\n    volume=pathlib.Path(value)\n    if volume.parent!=MEDIA_ROOT or volume.name in ('.','..') or not volume.name:\n        raise ValueError('Select a configured PiNAS data volume')\n    if volume.is_symlink() or not volume.is_dir():raise ValueError('Volume is not available')\n    actual=run(['/usr/bin/findmnt','-n','-o','TARGET','--target',value]).stdout.strip()\n    if actual!=str(volume):raise ValueError('Volume must be mounted before media setup')\n    if os.statvfs(volume).f_flag & os.ST_RDONLY:raise ValueError('Volume is read-only')\n    return volume\n\ndef setup_library(data):\n    \"\"\"Create standard media subfolders; never delete existing user files.\"\"\"\n    if not installed():raise ValueError('Install MiniDLNA before setting up a library')\n    if not isinstance(data,dict) or set(data)!={'volume'}:\n        raise ValueError('Select a target storage volume')\n    volume=configured_volume(data['volume'])\n    library=volume/'pinas-media'\n    folders=[('Movies','V'),('Television','V'),('Music','A'),('Pictures','P')]\n    created=[]\n    try:\n        for path in [library]+[library/name for name,_ in folders]:\n            if path.is_symlink() or (path.exists() and not path.is_dir()):\n                raise ValueError('Media path is not an ordinary directory: '+str(path))\n            if not path.exists():\n                path.mkdir(mode=0o755)\n                os.chmod(path,0o755)\n                created.append(path)\n        entries=[{'path':str(library/name),'type':kind} for name,kind in folders]\n        save({'media_dir':entries,'inotify':True},emit_status=False)\n    except Exception:\n        for path in reversed(created):\n            try:path.rmdir()\n            except OSError:pass\n        raise\n    print(json.dumps({'ok':True,'installed':True,'state':active(),\n      'settings':settings(),'service':'minidlna.service',\n      'library_path':str(library),'created_folders':[str(p) for p in created]}))\n\ndef main():\n    if os.geteuid()!=0:raise ValueError('Root required')\n    if len(sys.argv)!=2 or sys.argv[1] not in ('status','install','save','start','stop','restart','rescan','grant','rebuild','setup-library'):raise ValueError('Unsupported command')\n    action=sys.argv[1]\n    if action=='status':status();return\n    if action=='install':\n        if not installed():\n            env=os.environ.copy();env.update({'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','DEBIAN_FRONTEND':'noninteractive'})\n            run(['/usr/bin/apt-get','install','-y','--no-install-recommends','minidlna'],timeout=210,env=env)\n            run(['/usr/bin/systemctl','enable','--now','minidlna.service'])\n        status();return\n    if not installed():raise ValueError('MiniDLNA is not installed')\n    if action in ('save','grant','setup-library'):\n        raw=sys.stdin.read(16385)\n        if len(raw)>16384:raise ValueError('Request too large')\n        if action=='save':save(json.loads(raw))\n        elif action=='grant':grant(json.loads(raw))\n        else:setup_library(json.loads(raw))\n        return\n    if action=='rebuild':rebuild();return\n    # Normal restart triggers scanning with the configured inotify watcher.\n    run(['/usr/bin/systemctl','restart' if action=='rescan' else action,'minidlna.service'])\n    status()\nif __name__=='__main__':\n    try:main()\n    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)\n"


# Media uploads are isolated from the MiniDLNA configuration helper.
# Browser requests are chunked, and the privileged side never accepts
# arbitrary filesystem paths, destination names containing separators,
# or commands supplied by the browser.
def media_upload_action(action,details):
    if action not in ('start','chunk','finish','cancel'):
        raise ValueError('Unsupported media upload action')
    if not isinstance(details,dict):
        raise ValueError('Invalid media upload details')
    response=privileged_command('pinas-media-upload',action,
        payload=_media_json.dumps(details),timeout=65)
    if response.returncode:
        raise RuntimeError((response.stderr.strip() or 'Media upload failed')[-500:])
    return _media_json.loads(response.stdout)

MEDIA_UPLOAD_HELPER = r"""#!/usr/bin/env python3
# Privileged upload broker: one configured MiniDLNA folder and one file at a time.
import base64,json,os,pathlib,re,secrets,stat,subprocess,sys,time
CONF=pathlib.Path('/etc/minidlna.conf')
ROOT=pathlib.Path('/mnt/pinas')
MAX_FILE=100*1024**3
MAX_CHUNK=384*1024
EXT={'.avi','.mp4','.m4v','.mkv','.mov','.wmv','.flv','.webm',
     '.mpeg','.mpg','.m2ts','.mts','.ts','.3gp','.vob','.ogv',
     '.mp3','.wav','.aac','.flac','.m4a','.ogg','.oga','.opus',
     '.wma','.aiff','.aif','.alac','.ape',
     '.jpg','.jpeg','.jpe','.png','.bmp','.svg','.gif','.webp',
     '.tif','.tiff','.heic','.heif','.avif','.ico',
     '.srt','.vtt','.ass','.ssa','.sub','.idx'}

def configured():
    if not CONF.is_file() or CONF.is_symlink():
        raise ValueError('MiniDLNA configuration is unavailable')
    allowed=set()
    for line in CONF.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#') or not line.startswith('media_dir='):
            continue
        value=line.split('=',1)[1].strip()
        if re.match(r'^[AVP],/',value):value=value[2:]
        allowed.add(value)
    return allowed

def media_folder(path):
    if not isinstance(path,str) or not 1<=len(path)<=320:
        raise ValueError('Select a media folder')
    folder=pathlib.Path(path)
    if not folder.is_absolute() or '..' in folder.parts or str(folder)!=path:
        raise ValueError('Invalid media folder')
    if path not in configured():
        raise ValueError('Save this folder in MiniDLNA before uploading')
    if not folder.is_dir() or any(part.is_symlink() for part in (folder,*folder.parents)):
        raise ValueError('Media folder is unavailable or contains symlinks')
    lookup=subprocess.run(['/usr/bin/findmnt','-rn','-o','TARGET','--target',path],
                          capture_output=True,text=True,timeout=10)
    mount=lookup.stdout.strip()
    if lookup.returncode or pathlib.Path(mount).parent!=ROOT or not folder.is_relative_to(mount):
        raise ValueError('Folder is not on an active PiNAS data volume')
    if os.statvfs(folder).f_flag & os.ST_RDONLY:
        raise ValueError('Media folder is read-only')
    return folder

def file_name(value):
    if not isinstance(value,str) or not value or len(os.fsencode(value))>240:
        raise ValueError('Invalid media filename')
    if value in ('.','..') or '/' in value or '\\' in value or any(ord(c)<32 for c in value):
        raise ValueError('Invalid media filename')
    if value.startswith('.pinas-media-upload-') or value.startswith('.'):
        raise ValueError('Hidden or reserved media filename')
    if pathlib.Path(value).suffix.casefold() not in EXT:
        raise ValueError('Select a video, audio, image or subtitle file')
    return value

def staging_paths(folder,token):
    if not isinstance(token,str) or not re.fullmatch(r'[0-9a-f]{40}',token):
        raise ValueError('Invalid transfer identifier')
    path=folder/('.pinas-media-upload-'+token)
    return path,folder/(path.name+'.json')

def read_staged(folder,token):
    stage,meta=staging_paths(folder,token)
    for path in (stage,meta):
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_dev!=folder.stat().st_dev:
            raise ValueError('Unsafe upload state')
        if stat.S_IMODE(info.st_mode)&0o077:
            raise ValueError('Insecure upload staging permissions')
    with meta.open('r') as handle:
        data=json.load(handle)
    if not isinstance(data,dict) or set(data)!={'folder','name','size','inode','created'}:
        raise ValueError('Invalid upload state')
    if data['folder']!=str(folder) or stage.stat().st_ino!=data['inode']:
        raise ValueError('Upload state changed')
    file_name(data['name'])
    if type(data['size']) is not int or not 1<=data['size']<=MAX_FILE:
        raise ValueError('Invalid upload size')
    return stage,meta,data

def start(folder,request):
    name=file_name(request.get('name'))
    size=request.get('size')
    if type(size) is not int or not 1<=size<=MAX_FILE:
        raise ValueError('Select a nonempty media file below 100 GiB')
    final=folder/name
    if final.exists() or final.is_symlink():
        raise ValueError('A file with this name already exists')
    token=secrets.token_hex(20)
    stage,meta=staging_paths(folder,token)
    fd=os.open(stage,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    info=os.fstat(fd)
    os.close(fd)
    try:
        metadata={'folder':str(folder),'name':name,'size':size,'inode':info.st_ino,'created':int(time.time())}
        md=os.open(meta,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(md,'w') as output:json.dump(metadata,output)
    except Exception:
        stage.unlink(missing_ok=True)
        raise
    return {'token':token,'size':size,'offset':0}

def chunk(folder,request):
    stage,meta,data=read_staged(folder,request.get('token'))
    offset=request.get('offset')
    encoded=request.get('content')
    if type(offset) is not int or not isinstance(encoded,str) or len(encoded)>MAX_CHUNK*2:
        raise ValueError('Invalid chunk')
    try:payload=base64.b64decode(encoded,validate=True)
    except (ValueError,base64.binascii.Error):raise ValueError('Invalid chunk encoding')
    if not payload or len(payload)>MAX_CHUNK:
        raise ValueError('Invalid chunk size')
    descriptor=os.open(stage,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW)
    try:
        current=os.fstat(descriptor)
        if current.st_ino!=data['inode'] or current.st_size!=offset or offset+len(payload)>data['size']:
            raise ValueError('Unexpected upload offset or file state')
        os.write(descriptor,payload)
    finally:os.close(descriptor)
    return {'offset':offset+len(payload)}

def finish(folder,request):
    stage,meta,data=read_staged(folder,request.get('token'))
    if stage.stat().st_size!=data['size']:
        raise ValueError('Media upload is incomplete')
    final=folder/data['name']
    if final.exists() or final.is_symlink():
        raise ValueError('A media file with this name already exists')
    # Mode is set before named ACLs, so chmod cannot reset the ACL mask.
    os.chmod(stage,0o644)
    acl=subprocess.run(['/usr/bin/setfacl','-m','u:minidlna:r--',str(stage)],
                       capture_output=True,text=True,timeout=12)
    if acl.returncode:
        os.chmod(stage,0o600)
        raise RuntimeError('Unable to grant MiniDLNA read access: '+acl.stderr[-150:])
    # Atomic no-clobber publication on the same filesystem.
    os.link(stage,final,follow_symlinks=False)
    stage.unlink()
    meta.unlink()
    return {'ok':True,'name':data['name'],'size':data['size'],'path':str(final)}

def cancel(folder,request):
    stage,meta,data=read_staged(folder,request.get('token'))
    stage.unlink()
    meta.unlink()
    return {'ok':True}

def main():
    if os.geteuid()!=0 or len(sys.argv)!=2 or sys.argv[1] not in ('start','chunk','finish','cancel'):
        raise ValueError('Unsupported media upload operation')
    raw=sys.stdin.read(700001)
    if len(raw)>700000:raise ValueError('Media upload request exceeds limit')
    request=json.loads(raw)
    if not isinstance(request,dict) or set(request)-{'path','name','size','token','offset','content'}:
        raise ValueError('Invalid media upload request')
    folder=media_folder(request.get('path'))
    action=sys.argv[1]
    if action=='start':result=start(folder,request)
    elif action=='chunk':result=chunk(folder,request)
    elif action=='finish':result=finish(folder,request)
    else:result=cancel(folder,request)
    print(json.dumps(result))

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""
