#!/usr/bin/env python3
"""PiNAS RC1 — lightweight NAS management interface (stdlib only)."""
import ssl, ipaddress, re, argparse, base64, hashlib, hmac, json, os, secrets, shutil, socket, subprocess, sys, time, threading
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

VERSION='0.6.0-rc16.3'
DATA=Path(os.environ.get('PINAS_DATA','/var/lib/pinas' if sys.platform=='linux' else str(Path.home()/'.local/share/pinas')))
CONFIG=DATA/'config.json'
SESSIONS={}
CPU_LOCK=threading.Lock()
CPU_SAMPLES=deque(maxlen=1800)
CPU_LAST=None
CPU_LATEST=0.0
DISCOVERY_LOCK=threading.Lock()
DISCOVERY_CACHE={}
DISCOVERY_AT=0
SETUP_LOCK=threading.Lock()
LOGIN_LOCK=threading.Lock()
LOGIN_ATTEMPTS={}
TLS_CERT=DATA/'tls-cert.pem'
TLS_KEY=DATA/'tls-key.pem'

def idle_seconds(cfg):
    minutes=cfg.get('session_timeout',5)
    return minutes*60 if type(minutes)==int and minutes in (5,10,15,30,60) else 300

def login_allowed(ip):
    now=time.monotonic()
    with LOGIN_LOCK:
        for key in list(LOGIN_ATTEMPTS):
            if now-LOGIN_ATTEMPTS[key][0]>900:LOGIN_ATTEMPTS.pop(key,None)
        last,count=LOGIN_ATTEMPTS.get(ip,(now,0))
        return count<8 or now-last>900

def login_failed(ip):
    now=time.monotonic()
    with LOGIN_LOCK:
        last,count=LOGIN_ATTEMPTS.get(ip,(now,0))
        LOGIN_ATTEMPTS[ip]=(now, count+1 if now-last<900 else 1)

def login_succeeded(ip):
    with LOGIN_LOCK:LOGIN_ATTEMPTS.pop(ip,None)


UPDATE_LOCK=threading.Lock()
UPDATE_STATUS={'running':False,'operation':'','last_check':None,'last_install':None,'error':'','output':''}

def package_updates():
    """Read APT's existing indexes; no privileged commands or network calls."""
    try:
        proc=subprocess.run(['/usr/bin/apt','list','--upgradable'],capture_output=True,text=True,timeout=25,check=False,env={**os.environ,'LC_ALL':'C'})
        if proc.returncode:return {'error':(proc.stderr or 'Unable to read APT indexes')[-400:],'packages':[]}
        packages=[]
        for line in proc.stdout.splitlines():
            if not line or line.startswith('Listing') or '/' not in line:continue
            match=re.match(r'^([^/\s]+)/([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+\[upgradable from: ([^]]+)\]',line)
            if match:
                name,repo,candidate,arch,installed=match.groups()
                packages.append({'name':name,'repository':repo,'candidate':candidate,'installed':installed,'architecture':arch})
            if len(packages)>=500:break
        return {'packages':packages,'truncated':len(packages)>=500}
    except (OSError,subprocess.TimeoutExpired) as exc:return {'error':str(exc),'packages':[]}

def update_worker(operation='refresh'):
    try:
        proc=subprocess.run(['/usr/bin/sudo','-n','/usr/local/libexec/pinas-apt-index',operation],capture_output=True,text=True,timeout=3600 if operation=='upgrade' else 240,check=False)
        with UPDATE_LOCK:
            UPDATE_STATUS.update(running=False,operation=operation,**({'last_install':int(time.time())} if operation=='upgrade' else {'last_check':int(time.time())}),error='' if proc.returncode==0 else (proc.stderr or 'APT operation failed')[-800:],output=((proc.stdout or '')+'\n'+(proc.stderr or ''))[-3500:])
    except (OSError,subprocess.TimeoutExpired) as exc:
        with UPDATE_LOCK:UPDATE_STATUS.update(running=False,operation=operation,error=str(exc))

def suggested_hostname(model):
    """Predictable, RFC-1123-compatible default from the Pi model."""
    m=re.search(r'Raspberry Pi\s+(\d+)(?:\s+Model\s+)?\s*([AB])?\+?',model,re.I)
    if not m:return 'pinas'
    number=m.group(1);letter=(m.group(2) or ('b' if number in ('3','4','5') else '')).lower()
    return 'pinas-'+number+letter

def valid_hostname(value):
    return isinstance(value,str) and 1<=len(value)<=63 and re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*',value) is not None

def cpu_counters():
    try:
        fields=Path('/proc/stat').read_text().splitlines()[0].split()
        values=[int(x) for x in fields[1:]]
        idle=values[3]+(values[4] if len(values)>4 else 0)
        return sum(values),idle
    except (OSError,ValueError,IndexError): return None

def cpu_sample_once():
    global CPU_LAST,CPU_LATEST
    now=time.time(); current=cpu_counters()
    if current is None:return
    with CPU_LOCK:
        if CPU_LAST:
            delta=current[0]-CPU_LAST[0]
            idle=current[1]-CPU_LAST[1]
            if delta>0:
                CPU_LATEST=round(max(0,min(100,100*(1-idle/delta))),1)
                CPU_SAMPLES.append([round(now),CPU_LATEST])
        CPU_LAST=current

def cpu_history(minutes=10):
    with CPU_LOCK:
        cutoff=time.time()-minutes*60
        return {'current':CPU_LATEST,'samples':[v for v in CPU_SAMPLES if v[0]>=cutoff]}

def cpu_sampler():
    cpu_sample_once()
    while True:
        interval=load().get('cpu_interval',5)
        if interval not in (2,5,10):interval=5
        time.sleep(interval)
        cpu_sample_once()


def command(*args, timeout=6):
    try:
        p=subprocess.run(args, capture_output=True,text=True,timeout=timeout,check=False)
        return p.stdout.strip() if p.returncode==0 else ''
    except (OSError,subprocess.TimeoutExpired): return ''

def read(path):
    try: return Path(path).read_text().strip()
    except OSError: return ''

def load():
    try: return json.loads(CONFIG.read_text())
    except (OSError,ValueError): return {'theme':'light','accent':'#c51a4a','font':12,'login_background':''}

def save(config):
    DATA.mkdir(parents=True,exist_ok=True)
    tmp=DATA/('config-'+secrets.token_hex(4)+'.tmp')
    tmp.write_text(json.dumps(config,indent=2))
    os.chmod(tmp,0o600); os.replace(tmp,CONFIG)

def hash_password(password,salt=None):
    salt=salt or secrets.token_bytes(16)
    return base64.b64encode(salt).decode()+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),salt,350000).hex()

def verify(password,stored):
    try:
        salt,digest=stored.split(':',1)
        result=hash_password(password,base64.b64decode(salt)).split(':',1)[1]
        return hmac.compare_digest(result,digest)
    except (ValueError,TypeError): return False

def admin_accounts(cfg):
    accounts=cfg.get('additional_admins',{})
    return accounts if isinstance(accounts,dict) else {}

def admin_record(cfg,username):
    if username==cfg.get('admin_user','admin'):
        return {'display_name':cfg.get('admin_display_name',username),'password':cfg.get('admin_password','')}
    return admin_accounts(cfg).get(username)

def valid_display_name(value):
    return isinstance(value,str) and 1<=len(value.strip())<=80 and not any(ord(c)<32 for c in value)

def valid_account_password(value):
    return isinstance(value,str) and 12<=len(value)<=256

def change_nas_password(username,password):
    proc=subprocess.run(['sudo','-n','/usr/local/libexec/pinas-nas-user','password',username],
        input=password+'\n',text=True,capture_output=True,timeout=35,check=False)
    if proc.returncode:raise RuntimeError('Unable to update Samba password: '+(proc.stderr.strip() or 'Privileged helper failed')[-400:])

def nas_user_list():
    """Query Samba passdb via the narrowly scoped root helper (passdb is root-only)."""
    try:
        p=subprocess.run(['sudo','-n','/usr/local/libexec/pinas-nas-user','list'],
            capture_output=True,text=True,timeout=8,check=False)
        if p.returncode == 0:
            users=json.loads(p.stdout)
            if isinstance(users,list):return users
    except (OSError,ValueError,subprocess.TimeoutExpired):pass
    # Legacy fallback for direct execution or a helper not yet installed.
    output=command('pdbedit','-L',timeout=4)
    return sorted([{'name':a[0],'uid':a[1]} for line in output.splitlines()
                   if len(a:=line.split(':',2))>=2 and re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',a[0])],key=lambda x:x['name'])

def storage_is_ready():
    """Require a persistent, mounted, supported data filesystem."""
    try:
        drives=discover().get('disks',[])
        return any(v.get('fs') in ('ext4','xfs','btrfs') and v.get('persistent') and v.get('mounts')
                   for d in drives for v in d.get('volumes',[]))
    except (KeyError,TypeError,ValueError):return False

def provision_nas_user(username,password):
    """Delegate narrowly scoped account provisioning; never run useradd in web process."""
    proc=subprocess.run(['sudo','-n','/usr/local/libexec/pinas-nas-user','create',username],
        input=password+'\n',text=True,capture_output=True,timeout=35,check=False)
    if proc.returncode:
        raise RuntimeError('NAS user provisioning failed: '+(proc.stderr.strip() or 'The privileged helper returned an error.')[-700:])
    return True

def nas_share_list():
    try:
        proc=subprocess.run(['sudo','-n','/usr/local/libexec/pinas-nas-share','list'],
            capture_output=True,text=True,timeout=8,check=False)
        if proc.returncode==0:
            result=json.loads(proc.stdout)
            if isinstance(result,list):return result
    except (OSError,ValueError,subprocess.TimeoutExpired):pass
    return []

def create_nas_share(name,volume,access):
    payload=json.dumps({'name':name,'volume':volume,'access':access})
    proc=subprocess.run(['sudo','-n','/usr/local/libexec/pinas-nas-share','create'],
        input=payload,text=True,capture_output=True,timeout=35,check=False)
    if proc.returncode:
        raise RuntimeError('Share creation failed: '+(proc.stderr.strip() or 'The privileged helper returned an error.')[-850:])

def edit_nas_share(name,new_name,access):
    proc=subprocess.run(['sudo','-n','/usr/local/libexec/pinas-nas-share','edit'],
        input=json.dumps({'name':name,'new_name':new_name,'access':access}),
        text=True,capture_output=True,timeout=35,check=False)
    if proc.returncode:
        raise RuntimeError('Share edit failed: '+(proc.stderr.strip() or 'The privileged helper returned an error.')[-850:])

def delete_nas_share(name):
    proc=subprocess.run(['sudo','-n','/usr/local/libexec/pinas-nas-share','delete'],
        input=json.dumps({'name':name}),text=True,capture_output=True,timeout=35,check=False)
    if proc.returncode:
        raise RuntimeError('Share removal failed: '+(proc.stderr.strip() or 'The privileged helper returned an error.')[-850:])

def configure_nas_mount(device):
    """Non-destructive UUID-based adoption via independently validated root broker."""
    proc=subprocess.run(['sudo','-n','/usr/local/libexec/pinas-nas-storage','adopt'],
        input=json.dumps({'device':device}),text=True,capture_output=True,timeout=40,check=False)
    if proc.returncode:
        raise RuntimeError((proc.stderr.strip() or 'Storage configuration failed')[-800:])
    return json.loads(proc.stdout)

def nas_file_action(action, username, share='', path='', **extra):
    payload={'action':action,'username':username,'share':share,'path':path,**extra}
    proc=subprocess.run(['sudo','-n','/usr/local/libexec/pinas-nas-files'],input=json.dumps(payload),
        capture_output=True,text=True,timeout=120,check=False)
    if proc.returncode:
        raise RuntimeError((proc.stderr.strip() or 'File operation failed')[-500:])
    return json.loads(proc.stdout)

def nas_authenticate(username,password):
    proc=subprocess.run(['sudo','-n','/usr/local/libexec/pinas-nas-files'],
        input=json.dumps({'action':'authenticate','username':username,'password':password}),
        capture_output=True,text=True,timeout=12,check=False)
    return proc.returncode==0 and proc.stdout.strip()=='true'

def nas_user_count():
    return len(nas_user_list())

def discover():
    global DISCOVERY_AT,DISCOVERY_CACHE
    with DISCOVERY_LOCK:
        if DISCOVERY_CACHE and time.monotonic()-DISCOVERY_AT<60:return DISCOVERY_CACHE
        result=hardware_discovery()
        DISCOVERY_CACHE=result
        DISCOVERY_AT=time.monotonic()
        return result

def system_storage():
    """OS filesystem only: never counted as user NAS capacity."""
    try:
        st=os.statvfs('/')
        total=st.f_blocks*st.f_frsize
        available=st.f_bavail*st.f_frsize
        return {'total':total,'used':max(0,total-available),'free':available,'percent':round(100*(total-available)/total) if total else 0}
    except OSError:return {'total':0,'used':0,'free':0,'percent':0}

def persistent_mounts():
    """Read fstab without resolving or changing devices."""
    entries=[]
    try:
        for line in Path('/etc/fstab').read_text().splitlines():
            line=line.strip()
            if not line or line.startswith('#'):continue
            cols=line.split()
            if len(cols)>=4:entries.append({'source':cols[0],'target':cols[1],'type':cols[2]})
    except OSError:pass
    return entries

def btrfs_probe(device):
    """Read-only fallback; blkid can miss Btrfs on some devices."""
    if not device or not device.startswith('/dev/') or not shutil.which('btrfs'):return ''
    # btrfs inspect-internal dump-super reads the superblock without mounting.
    result=command('btrfs','inspect-internal','dump-super',device,timeout=3)
    return 'btrfs' if 'magic' in result and '_BHRfS_M' in result else ''

def hardware_discovery():
    model=read('/proc/device-tree/model').replace('\x00','') or 'Non-Raspberry Pi / development host'
    disks=[]
    fstab=persistent_mounts()
    # Find the physical backing device(s) for the OS root and boot partitions.
    # Exclude the entire disk, not just its mounted partitions. This is also
    # important for future destructive operations (which remain disabled).
    raw=command('lsblk','-J','-b','-o','NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,TRAN,UUID,RO,PKNAME')
    system_mounts={'/','/boot','/boot/firmware','/boot/efi'}
    try:
        roots=json.loads(raw).get('blockdevices',[])
        def has_system_mount(node):
            return any(m in system_mounts for m in (node.get('mountpoints') or []) if m) or any(has_system_mount(c) for c in node.get('children') or [])
        # lsblk may report root as a device-mapper or md device. Follow its
        # parent block devices, not only the mountpoint on the physical disk.
        system_names=set()
        by_name={}
        def index(node):
            by_name[node.get('name')]=node
            for child in node.get('children') or []:index(child)
        for root in roots:index(root)
        def mark_parents(node):
            name=node.get('name')
            if not name or name in system_names:return
            system_names.add(name)
            parent=node.get('pkname')
            if parent and parent in by_name:mark_parents(by_name[parent])
        def mark_tree(node,ancestors=()):
            if has_system_mount(node):
                mark_parents(node)
                for ancestor in ancestors:mark_parents(ancestor)
            for child in node.get('children') or []:mark_tree(child,ancestors+(node,))
        for root in roots:mark_tree(root)
        # Resolve any root/boot mounts not represented by lsblk's tree.
        for mount in system_mounts:
            source=command('findmnt','-n','-o','SOURCE','--target',mount,timeout=2).splitlines()
            if source:
                dev=source[0].split('[',1)[0]
                for node in by_name.values():
                    if node.get('path')==dev:mark_parents(node)
        for root in roots:
            if (root.get('type')!='disk' or root.get('name') in system_names or has_system_mount(root)
                or (root.get('name') or '').startswith(('zram','ram','loop','nbd','sr','fd'))
                or (root.get('path') or '').startswith(('/dev/zram','/dev/ram','/dev/loop'))
                or (root.get('tran') or '').lower() in ('','unknown') and (root.get('name') or '').startswith(('zram','ram'))):continue
            # Capacity is based on mounted filesystems, not total disk size.
            # Unmounted / unformatted capacity is reported as unknown, not free.
            filesystems=[];seen=set()
            def walk(node):
                for mount in node.get('mountpoints') or []:
                    if not mount or mount in seen or not mount.startswith('/'):continue
                    seen.add(mount)
                    try:
                        stat=os.statvfs(mount)
                        total=stat.f_blocks*stat.f_frsize
                        free=stat.f_bavail*stat.f_frsize
                        if total>0:filesystems.append({'mount':mount,'total':total,'used':max(0,total-free),'free':free})
                    except OSError:pass
                for child in node.get('children') or []:walk(child)
            walk(root)
            volumes=[]
            def collect(node):
                if node is not root and node.get('type') in ('part','crypt','lvm','raid','md'):
                    path=node.get('path') or ''
                    fs=node.get('fstype') or ''
                    uuid=node.get('uuid') or ''
                    if not fs and path:fs=btrfs_probe(path)
                    mounts=[m for m in (node.get('mountpoints') or []) if m]
                    configured=any(e['source'] in (path,'UUID='+uuid) or (e['source'].startswith('/dev/disk/by-uuid/') and e['source'].rsplit('/',1)[-1]==uuid) for e in fstab)
                    volumes.append({'name':node.get('name'),'path':path,'size':node.get('size'),'fs':fs,'uuid':uuid,'mounts':mounts,'persistent':configured,'read_only':bool(node.get('ro'))})
                for child in node.get('children') or []:collect(child)
            collect(root)
            # Some disks have a filesystem directly on the whole disk.
            if root.get('fstype') and not volumes:
                uuid=root.get('uuid') or '';path=root.get('path') or ''
                volumes.append({'name':root.get('name'),'path':path,'size':root.get('size'),'fs':root.get('fstype'),'uuid':uuid,'mounts':[m for m in (root.get('mountpoints') or []) if m],'persistent':any(e['source'] in (path,'UUID='+uuid) for e in fstab),'read_only':bool(root.get('ro'))})
            walk(root)
            disks.append({'name':root.get('name'),'path':root.get('path'),'size':root.get('size'),'type':'disk','fs':root.get('fstype'),'mounts':root.get('mountpoints') or [],'model':root.get('model'),'transport':root.get('tran'),'uuid':root.get('uuid'),'read_only':bool(root.get('ro')),'filesystems':filesystems,'volumes':volumes,'has_partition_table':bool(root.get('children'))})
    except (ValueError,TypeError):pass
    raid=[]
    for name in os.listdir('/sys/block') if Path('/sys/block').exists() else []:
        if name.startswith('md') and (Path('/sys/block')/name/'md/level').exists():
            root=Path('/sys/block')/name/'md'
            # Read md sysfs directly: lightweight, no elevated permissions or mdadm subprocess.
            def number(field):
                try:return int(read(root/field))
                except (ValueError,OSError):return None
            members=[]
            for member in sorted(root.glob('dev-*')):
                try:
                    member_device=(member/'block').resolve().name
                    if not member_device or member_device=='block':
                        member_device=member.name[4:]
                except OSError:member_device=member.name[4:]
                members.append({'device':member_device,'state':read(member/'state') or 'unknown','slot':read(member/'slot')})
            action=read(root/'sync_action') or 'idle'
            completed=number('sync_completed')
            # sync_completed is a fraction such as '123 / 456', not a plain integer.
            progress=None
            sync_raw=read(root/'sync_completed')
            if '/' in sync_raw:
                try:
                    done,total=(int(x.strip()) for x in sync_raw.split('/',1))
                    if total>0:progress=round(min(100,max(0,100*done/total)),1)
                except ValueError:pass
            raid.append({'name':name,'level':read(root/'level'),'state':read(root/'array_state'),
                'sync':action,'degraded':read(root/'degraded'),'progress':progress,
                'raid_disks':number('raid_disks'),'members':members,
                'size':number('array_size'), 'metadata':read(root/'metadata_version')})
    shares=[]
    smb=command('testparm','-s',timeout=5)
    for line in smb.splitlines():
        line=line.strip()
        if line.startswith('[') and line.endswith(']') and line!='[global]': shares.append(line[1:-1])
    return {'model':model,'hostname':socket.gethostname(),'disks':disks,'raid':raid,'shares':shares,'packages':{x:bool(shutil.which(x)) for x in ('smbd','mkfs.xfs','mkfs.btrfs','mdadm')},'nas_users':nas_user_count(),'nas_user_list':nas_user_list(),'share_details':nas_share_list()}

def service_health():
    """Read-only, on-demand systemd snapshot; no background monitoring."""
    names=(('Samba file sharing','smbd.service'),('Samba name service','nmbd.service'),('SSH access','ssh.service'),('Network manager','NetworkManager.service'),('Scheduled updates','pinas-auto-updates.timer'))
    results=[]
    for label,unit in names:
        item={'name':label,'unit':unit,'state':'unknown','detail':'Status unavailable'}
        try:
            p=subprocess.run(['systemctl','show',unit,'--property=LoadState,ActiveState,SubState,UnitFileState','--no-pager'],
                             capture_output=True,text=True,timeout=4,check=False)
            if p.returncode:raise OSError('systemctl unavailable')
            fields=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
            loaded=fields.get('LoadState','')
            active=fields.get('ActiveState','unknown')
            if loaded=='not-found':
                item.update(state='not-installed',detail='Unit not installed')
            elif loaded in ('masked','error','bad-setting'):
                item.update(state='warning',detail='Unit '+loaded)
            elif active=='failed':
                item.update(state='warning',detail='Service failed')
            elif active=='active':
                item.update(state='healthy',detail='Active ('+fields.get('SubState','running')+')')
            elif active=='inactive':
                enabled=fields.get('UnitFileState','')
                item.update(state='warning' if enabled=='enabled' else 'inactive',
                            detail='Inactive'+(' (enabled)' if enabled=='enabled' else ''))
            elif active=='activating':
                item.update(state='pending',detail='Starting')
            else:
                item.update(state='unknown',detail='State: '+active[:32])
        except (OSError,subprocess.TimeoutExpired):
            pass
        results.append(item)
    warnings=[{'name':i['name'],'message':i['detail']} for i in results if i['state']=='warning']
    if Path('/run/reboot-required').exists():
        warnings.append({'name':'System reboot','message':'A reboot is required to finish updates'})
    return {'services':results,'warnings':warnings,'checked_at':int(time.time())}

def hardware():
    base=discover().copy()
    temp=read('/sys/class/thermal/thermal_zone0/temp')
    try: temp=round(int(temp)/1000,1)
    except ValueError: temp=None
    mem={}
    for line in read('/proc/meminfo').splitlines():
        if ':' in line:
            k,v=line.split(':',1)
            try:mem[k]=int(v.strip().split()[0])*1024
            except (ValueError,IndexError):pass
    base['system_storage']=system_storage()
    names=load().get('nas_display_names',{})
    if isinstance(names,dict):
        for user in base.get('nas_user_list',[]):
            if isinstance(user,dict):user['display_name']=names.get(user.get('name'),user.get('name'))
    cfg=load();base['admin_user_list']=[{'name':cfg.get('admin_user','admin'),'display_name':cfg.get('admin_display_name',cfg.get('admin_user','admin'))}]+[{'name':n,'display_name':v.get('display_name',n)} for n,v in admin_accounts(cfg).items() if isinstance(v,dict)]
    # Read-only, low-overhead system health snapshot. No new daemon or polling thread.
    try:uptime_seconds=max(0,int(float(read('/proc/uptime').split()[0])))
    except (ValueError,IndexError):uptime_seconds=None
    os_name='Linux'
    try:
        for os_line in Path('/etc/os-release').read_text().splitlines():
            if os_line.startswith('PRETTY_NAME='):
                os_name=os_line.split('=',1)[1].strip().strip('\"');break
    except OSError:pass
    try:kernel=os.uname().release
    except AttributeError:kernel='Unavailable'
    base.update(uptime_seconds=uptime_seconds,os_name=os_name,kernel=kernel)
    base.update(temperature=temp,throttle=command('vcgencmd','get_throttled',timeout=2),memory_total=mem.get('MemTotal',0),memory_used=max(0,mem.get('MemTotal',0)-mem.get('MemAvailable',0)),load=list(os.getloadavg()),version=VERSION)
    model=base['model'];ram=base['memory_total'];profile='performance' if 'Raspberry Pi 5' in model and ram>=3*1024**3 else 'enhanced' if 'Raspberry Pi 4' in model and ram>=2*1024**3 else 'essential'
    base['profile']=profile
    base['capabilities']={'samba':True,'raid':True,'minidlna':True,'curated_apps':profile!='essential','jellyfin':profile=='performance'}
    return base

PAGE=r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PiNAS · Raspberry Pi NAS</title><style>
:root{--accent:#c51a4a;--bg:#f6f6f7;--surface:#fff;--ink:#24242a;--muted:#71717c;--line:#e6e6ea;--soft:#f1f1f4;--radius:13px;font-family:Arial,Helvetica,sans-serif;font-size:14px;color:var(--ink);background:var(--bg)}
[data-theme=dark],[data-theme=dark-cb]{--bg:#17171c;--surface:#222229;--ink:#f5f5f7;--muted:#a7a7b3;--line:#3b3b46;--soft:#2c2c34}[data-theme=light-cb]{--bg:#fff;--surface:#fff;--ink:#101010;--muted:#333;--line:#555;--soft:#eee}[data-theme=dark-cb]{--bg:#080808;--surface:#161616;--ink:#fff;--muted:#ddd;--line:#aaa;--soft:#303030}*{box-sizing:border-box}body{margin:0}button,input,select{font:inherit}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}header{height:72px;background:var(--surface);border-bottom:1px solid var(--line);display:flex;align-items:center;padding:0 max(24px,calc((100vw - 1220px)/2));gap:18px}.brand{display:flex;align-items:center;gap:12px;font-weight:800;font-size:23px;white-space:nowrap}.mark{background:var(--accent);color:white;border-radius:12px;width:43px;height:43px;display:grid;place-items:center;font-size:27px}.brand small{font-size:11px;font-weight:500;color:var(--muted);display:block;letter-spacing:.6px}nav{display:flex;gap:4px;flex:1;overflow-x:auto;position:relative}nav button{background:transparent;border:0;color:var(--muted);padding:12px 14px;border-radius:8px;font-weight:600;white-space:nowrap}nav button.active{background:transparent;color:var(--ink)}main{max-width:1220px;margin:35px auto;padding:0 24px}h1{font-size:30px;letter-spacing:-1px;margin:0 0 7px}h2{font-size:17px;margin:0 0 16px}p{color:var(--muted);line-height:1.6}.subtitle{margin:0 0 27px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:23px;min-width:0}.wide{grid-column:1/-1}.span2{grid-column:span 2}.label{font-size:12px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.8px}.big{font-size:29px;font-weight:800;margin:11px 0}.small{font-size:12px;color:var(--muted)}.pill{display:inline-flex;padding:6px 10px;border-radius:30px;background:var(--soft);color:var(--muted);font-size:12px;font-weight:700}.good{color:#16864c}.bar{height:9px;background:var(--soft);border-radius:9px;overflow:hidden;margin:15px 0}.bar i{height:100%;display:block;background:var(--accent);border-radius:9px}.line{border-top:1px solid var(--line);padding:14px 0;display:flex;align-items:center;justify-content:space-between;gap:15px}.line:first-of-type{border-top:0}.line strong{display:block}.btn{background:var(--accent);border:1px solid var(--accent);color:white;padding:11px 17px;border-radius:8px;font-weight:700}.outline{background:transparent;border-color:var(--line);color:var(--ink)}.field{display:flex;flex-direction:column;gap:8px;margin:15px 0}.field input,.field select{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:12px;color:var(--ink);width:100%;max-width:440px}.hint{background:var(--soft);padding:15px;border-radius:9px;color:var(--muted);line-height:1.6}.danger{color:#c53540}.login{min-height:100vh;display:grid;place-items:center;padding:24px;background-position:center;background-size:cover}.login .card{width:min(100%,430px);box-shadow:0 14px 45px #00000017}.login h1{margin-top:22px}.login input{max-width:none}.login .btn{width:100%}.loginbg{background-image:var(--login-image)}.hidden{display:none!important}.footer{padding:26px 0;color:var(--muted);font-size:12px;display:flex;justify-content:space-between}input[type=color]{padding:3px;width:64px;height:42px}input[type=file]{max-width:440px}#message{margin-top:12px;color:var(--accent)}@media(max-width:900px){header{height:auto;flex-wrap:wrap;padding:12px 20px}nav{order:3;width:100%;flex-basis:100%}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.span2{grid-column:1/-1}}@media(max-width:560px){.grid{grid-template-columns:1fr}.span2{grid-column:auto}main{padding:0 15px;margin:22px auto}header{padding:10px 15px}.card{padding:18px}}
.icon-btn{display:grid;place-items:center;width:42px;height:42px;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--ink)}.icon-btn:hover{border-color:var(--accent)}.share-top-actions{display:flex;justify-content:flex-start;margin:12px 0}.share-icon-btn{display:inline-flex!important;align-items:center!important;justify-content:center!important;padding:0!important;width:42px!important;height:42px!important;min-width:42px!important;line-height:1!important;flex:none!important}.share-icon-btn svg{display:block!important;width:24px;height:24px;margin:0!important;flex:none}.share-entry{align-items:center}.share-meta{min-width:0;flex:1;overflow-wrap:anywhere}.share-meta>div{margin:4px 0}.share-meta strong{display:inline;font-weight:700}.share-actions{display:flex;gap:8px;align-items:center;flex:none}@media(max-width:550px){.share-entry{align-items:flex-start}.share-actions{flex-direction:column}}.modal-overlay{position:fixed;inset:0;z-index:1000;background:#0009;display:grid;place-items:center;padding:16px}.settings-modal{width:min(100%,570px);max-height:min(90vh,850px);display:flex;flex-direction:column;box-shadow:0 20px 80px #0005}.modal-heading,.modal-actions{display:flex;align-items:center;justify-content:space-between;gap:12px}.modal-heading h2{margin:0}.modal-actions{justify-content:flex-end;padding-top:16px;border-top:1px solid var(--line)}.settings-scroll{overflow-y:auto;padding:12px 2px}.settings-scroll h3{margin:24px 0 8px;font-size:1.1rem}.settings-scroll .field{max-width:100%}.stat .big{font-size:38px}.clickable{cursor:pointer}.clickable:hover{border-color:var(--accent)}.chart-title,.chart-footer{display:flex;align-items:center;justify-content:space-between;gap:12px}.chart-title h2{margin:0}.cpu-chart{margin:18px 0 8px;height:170px}.cpu-chart svg{height:100%;width:100%}.chart-footer .big{margin:5px 0}.metric{text-align:center}.metric h2{text-align:left}.ring{display:block;max-width:170px;width:100%;margin:8px auto}.metric p{margin:5px 0}.overview .wide{grid-column:1/-1}@media(max-width:560px){.overview .wide{grid-column:auto}}

 .storage-disk-entry{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:22px 0;border-top:1px solid var(--line)}.storage-disk-entry:first-of-type{border-top:0}.disk-properties{display:grid;gap:9px;min-width:0}.disk-properties>div{display:grid;grid-template-columns:135px minmax(0,1fr);gap:12px;align-items:baseline}.disk-properties span{color:var(--muted)}.disk-properties strong{font-weight:600;overflow-wrap:anywhere}.disk-management-action{display:flex;justify-content:space-between;align-items:center;gap:18px;border-top:1px solid var(--line);padding:18px 0}.disk-management-action>div{min-width:0}.disk-management-action p{margin:7px 0}.disk-management-action .btn{min-width:135px}.disk-management-action button:disabled{opacity:.45}@media(max-width:560px){.storage-disk-entry,.disk-management-action{align-items:stretch;flex-direction:column}.disk-properties>div{grid-template-columns:115px minmax(0,1fr)}}.storage-action{min-width:125px}.storage-volume{padding:10px 0;border-top:1px solid var(--line)}.wizard-option{display:block;padding:12px;border:1px solid var(--line);border-radius:var(--radius-sm);margin:8px 0}.wizard-option input{margin-right:8px}.wizard-option small{display:block;color:var(--muted);margin:5px 0 0 25px}.storage-wizard{width:min(100%,610px)}.disk-summary{padding:18px 0;border-top:1px solid var(--line)}.disk-summary:first-of-type{border-top:0}.disk-heading,.disk-foot{display:flex;justify-content:space-between;gap:12px;align-items:center}.disk-heading strong,.disk-heading .small{display:block}.disk-heading .small{margin-top:5px}.disk-usage{height:12px;margin:12px 0 8px}.disk-foot{color:var(--muted);font-size:12px}@media(max-width:560px){.disk-heading{align-items:flex-start;flex-direction:column}}
.raid-wizard{width:min(100%,660px)}.raid-disk{display:flex;gap:12px;align-items:center;border:1px solid var(--line);padding:12px;border-radius:var(--radius-sm);margin:8px 0;cursor:pointer}.raid-disk span{display:flex;flex-direction:column;gap:4px}.raid-disk small{color:var(--muted)}.raid-disk input{accent-color:var(--accent)}
.health-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.health-grid>div{display:flex;flex-direction:column;gap:7px;min-width:0}.health-grid strong{overflow-wrap:anywhere;font-size:1.1rem}@media(max-width:560px){.health-grid{grid-template-columns:1fr}}
/* PiNAS unified design system — no per-page hard-coded appearance rules */
:root{--success:#218457;--warning:#a76a12;--danger:#bb3444;--radius:16px;--radius-sm:11px;--space:8px;--ease:cubic-bezier(.2,.75,.25,1);--duration:190ms;--shadow:0 6px 24px rgba(20,24,34,.035);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;font-size:12px}
[data-theme=light]{--bg:#f7f8fa;--surface:#fff;--ink:#20232a;--muted:#646b76;--line:#e4e7eb;--soft:#f1f3f6}
[data-theme=dark]{--bg:#12151a;--surface:#1b2028;--ink:#f4f5f7;--muted:#abb3bf;--line:#343b47;--soft:#272e38}
[data-theme=light-cb]{--success:#12628a;--warning:#805600;--danger:#9d3359;--bg:#fff;--surface:#fff;--ink:#111;--muted:#333;--line:#777;--soft:#eee}
[data-theme=dark-cb]{--success:#7bd3ff;--warning:#ffd47d;--danger:#ff9ab3;--bg:#08090b;--surface:#17191e;--ink:#fff;--muted:#ddd;--line:#999;--soft:#30333a}
nav button{border-radius:0;position:relative;font-size:calc(1rem + 1.5px)}nav button:hover{background:transparent;color:var(--ink)}nav .nav-indicator{position:absolute;bottom:0;height:3px;background:var(--accent);border-radius:3px;pointer-events:none;left:0;width:0;transition:transform 260ms cubic-bezier(.22,1,.36,1),width 260ms cubic-bezier(.22,1,.36,1);will-change:transform,width}body{min-width:320px}header{gap:14px}main{margin-top:32px}.card{box-shadow:var(--shadow);transition:border-color var(--duration) var(--ease),box-shadow var(--duration) var(--ease)}.card:hover{box-shadow:0 9px 28px rgba(20,24,34,.06)}.btn,.icon-btn,nav button{transition:background var(--duration) var(--ease),color var(--duration) var(--ease),border-color var(--duration) var(--ease),transform var(--duration) var(--ease)}.btn:not(:disabled):active,.icon-btn:active{transform:scale(.98)}.btn:hover:not(:disabled){filter:brightness(.96)}.btn:focus-visible,.icon-btn:focus-visible,nav button:focus-visible,input:focus-visible,select:focus-visible,.clickable:focus-visible{outline:3px solid var(--accent);outline-offset:3px}.good{color:var(--success)}.danger{color:var(--danger)}.hint{border:1px solid var(--line)}.pill{font-weight:600}.settings-modal{animation:modal-in var(--duration) var(--ease)}.modal-overlay{animation:fade-in var(--duration) ease}.settings-scroll{overscroll-behavior:contain}.settings-modal .icon-btn{flex-shrink:0}.field input,.field select{min-height:44px}.clickable{transition:transform var(--duration) var(--ease),border-color var(--duration) var(--ease)}.clickable:hover{transform:translateY(-1px)}.line>div{min-width:0;overflow-wrap:anywhere}.footer{gap:12px;flex-wrap:wrap}.login .brand{justify-content:center}.login .card{border-radius:20px}.login h1{letter-spacing:-.7px}@keyframes modal-in{from{opacity:0;transform:translateY(8px) scale(.99)}to{opacity:1;transform:translateY(0) scale(1)}}@keyframes fade-in{from{opacity:0}to{opacity:1}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}@media(max-width:900px){header{gap:8px}nav{scrollbar-width:none}nav::-webkit-scrollbar{display:none}}@media(max-width:560px){.modal-overlay{padding:8px}.settings-modal{max-height:94dvh}.chart-footer{flex-wrap:wrap}}
.file-toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}

.file-action-btn{width:38px;height:38px;min-width:38px;display:inline-flex;align-items:center;justify-content:center;padding:6px;border-radius:10px;flex-shrink:0}.file-action-btn svg{display:block;flex-shrink:0}.file-action-btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff}.file-action-btn:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.file-toolbar .icon-btn{flex:0 0 48px;width:48px;height:48px;border-radius:11px;padding:8px;box-shadow:none;appearance:none;overflow:hidden}.file-toolbar .icon-btn svg{display:block;flex-shrink:0}.file-toolbar .icon-btn:hover:not(:disabled),.file-toolbar .file-upload-control:hover:not(:has(input:disabled)){background:var(--accent);border-color:var(--accent);color:#fff}.file-toolbar .icon-btn:focus-visible{outline:3px solid var(--accent);outline-offset:2px}.file-upload-control{position:relative;cursor:pointer}.file-upload-control input{position:absolute;width:1px;height:1px;opacity:0;overflow:hidden}.file-upload-control:focus-within{outline:3px solid var(--accent);outline-offset:3px}.file-upload-control:has(input:disabled){opacity:.5;cursor:default}.file-entry{display:flex;align-items:center;gap:11px;min-width:0}.file-entry svg{flex-shrink:0;color:var(--accent)}.file-entry .file-name{overflow-wrap:anywhere}.user-avatar{width:38px;height:38px;border-radius:50%;object-fit:cover;background:var(--soft);border:1px solid var(--line)}.user-header{display:flex;align-items:center;gap:10px;margin-left:auto}.profile-preview{width:74px;height:74px;border-radius:50%;object-fit:cover;border:1px solid var(--line);background:var(--soft)}
.file-entry{border:0;background:transparent;color:var(--ink);font:inherit;text-align:left;cursor:pointer;flex:1;padding:8px 0}.file-entry:hover{text-decoration:underline}
/* Shared icon behaviour across administrator and NAS-user views. */
.icon-btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff}
.icon-btn svg{display:block;flex-shrink:0}
.icon-btn:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
/* Keep input focus rings entirely within the control, including scrollable dialogs. */
.field input:focus,.field select:focus,.field textarea:focus{outline:none;border-color:var(--accent);box-shadow:inset 0 0 0 2px var(--accent)}
.field input:focus-visible,.field select:focus-visible,.field textarea:focus-visible{outline:none;outline-offset:0}
.settings-scroll{padding-left:8px;padding-right:8px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.modal-actions .btn svg,#transfer-cancel svg{width:19px;height:19px;vertical-align:middle;margin-right:6px}.user-header #file-logout{width:42px;height:42px;flex-shrink:0}.user-header #file-logout svg{display:block;width:24px;height:24px}.user-header #file-logout:hover{background:var(--accent);border-color:var(--accent);color:#fff}.user-top-actions{display:flex;justify-content:flex-start;gap:12px;flex-wrap:wrap;margin:0 0 18px}.add-user-button{display:inline-flex;align-items:center;justify-content:center;gap:8px;transition:background .18s ease,border-color .18s ease,color .18s ease}.add-user-button svg{display:block;width:22px;height:22px;flex:none}.add-user-button:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff;filter:none}.add-user-button:focus-visible{outline:2px solid var(--accent);outline-offset:3px}.user-management-cards{display:grid;grid-template-columns:1fr;gap:18px}.edit-user-button{display:inline-flex;align-items:center;gap:8px;flex-shrink:0}.edit-user-button svg{width:22px;height:22px;display:block;flex:none}.edit-user-button:hover{background:var(--accent);border-color:var(--accent);color:#fff}.edit-user-button:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.raid-array-entry{border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}.raid-array-entry .line{gap:12px}.progress-track{height:8px;background:var(--line);border-radius:8px;overflow:hidden;margin:8px 0}.progress-fill{height:100%;background:var(--accent);border-radius:8px;transition:width .3s ease}

.updates-schedule-options{border:0;padding:0;margin:14px 0 12px;min-width:0}.updates-schedule-options legend{font-weight:600;margin-bottom:10px}.updates-schedule-options label{display:flex;align-items:center;gap:12px;padding:10px 12px;margin:5px 0;border:1px solid var(--line);border-radius:11px;cursor:pointer;transition:border-color .18s,background .18s}.updates-schedule-options label:hover{border-color:var(--accent);background:var(--accent-soft,rgba(160,40,55,.06))}.updates-schedule-options input[type=radio]{accent-color:var(--accent);width:18px;height:18px;flex:none;margin:0}.updates-schedule-options label:has(input:checked){border-color:var(--accent)}.updates-schedule-options label:focus-within{outline:2px solid var(--accent);outline-offset:2px}

.save-schedule-button{display:inline-flex;align-items:center;gap:9px;margin:12px 0 8px}.save-schedule-button svg{flex:none;display:block}.save-schedule-button:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff}
.updates-actions{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 12px}.updates-actions .btn{display:inline-flex;align-items:center;justify-content:center;gap:9px;transition:background var(--duration) var(--ease),border-color var(--duration) var(--ease),color var(--duration) var(--ease),transform var(--duration) var(--ease)}.updates-actions .btn svg{display:block;width:22px;height:22px;flex:none}.updates-actions .btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff;filter:none}.updates-actions .btn:focus-visible{outline:2px solid var(--accent);outline-offset:3px}.updates-actions .btn:disabled{opacity:.45;cursor:not-allowed;transform:none;filter:none}.updates-status-row{display:flex;align-items:center;gap:12px;min-height:32px;margin:0 0 16px}.updates-spinner{width:18px;height:18px;flex:none;border:2px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:updates-spin .8s linear infinite}.updates-spinner[hidden]{display:none!important}@keyframes updates-spin{to{transform:rotate(360deg)}}.updates-log{margin-top:16px;border:1px solid var(--line);border-radius:11px;overflow:hidden}.updates-log summary{cursor:pointer;padding:12px 14px;font-weight:600;user-select:none}.updates-log summary:hover{color:var(--accent)}.updates-log pre{white-space:pre-wrap;overflow:auto;max-height:250px;margin:0;padding:12px 14px;border-top:1px solid var(--line)}.updates-actions .btn:disabled{opacity:.45;cursor:not-allowed;filter:grayscale(1)}
</style></head><body><div id="app"></div><script>
const app=document.getElementById('app');let info={},cfg={},cpu={},page='Overview',csrf='',role='admin',username='',displayName='',refreshTimer=null,lastNavRect=null;const nav=['Overview','Storage','Users','Shares','Applications'];
// Navigation is derived from actual mounted NAS volumes, not a setup flag.
// Once provisioned, existing accounts/shares remain accessible for recovery.
const storageReady=()=>disks().some(d=>(d.volumes||[]).some(v=>v.fs&&v.persistent&&(v.mounts||[]).some(m=>m&&m!=='/'&&!m.startsWith('/boot'))));
const navItems=()=>{const ready=storageReady(),existingUsers=Number(info.nas_users||0)>0,existingShares=(info.shares||[]).length>0;let items=['Overview','Storage'];items.push('RAID');items.push('Updates');if(ready||existingUsers||existingShares)items.push('Users');if((ready&&existingUsers)||existingShares)items.push('Shares');if(ready||existingShares)items.push('Applications');return items};
const setupNotice=()=>{if(!storageReady())return `<div class="card wide setup-next"><h2>Get your NAS ready</h2><p>Start by configuring a data disk. Once a supported filesystem is mounted and configured to reconnect at startup, PiNAS will unlock user management.</p><button class="btn" data-next="Storage">Set up storage</button></div>`;if(!(Number(info.nas_users||0)>0))return `<div class="card wide setup-next"><h2>Next step: Create a NAS user</h2><p>Your storage is ready. Create a Samba account before setting up shared folders. Create a NAS user to unlock shared folders.</p><button class="btn outline" data-next="Users">View users</button></div>`;if(!(info.shares||[]).length)return `<div class="card wide setup-next"><h2>Next step: Create a share</h2><p>Storage and Samba users are detected. The Shares page is now available; share creation is planned for the next functional milestone.</p><button class="btn outline" data-next="Shares">View shares</button></div>`;return ''};const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const size=n=>n?Number(n/1073741824).toFixed(1)+' GB':'—';const post=async(path,data)=>{let r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-PiNAS-CSRF':csrf},body:JSON.stringify(data)});let j=await r.json();if(!r.ok)throw Error(j.error||'Request failed');return j};async function init(){let r=await fetch('/api/state');let j=await r.json();cfg=j.settings||{};csrf=j.csrf||'';info=j.hardware||{};cpu=j.cpu||{};role=j.role||'admin';username=j.username||'';displayName=j.display_name||username;apply();if(!j.setup||!j.authenticated)login(!j.setup);else if(role==='user')renderFiles();else render()};function apply(){let theme=cfg.theme||'light';document.documentElement.dataset.theme=theme;document.documentElement.style.setProperty('--accent',cfg.accent||'#c51a4a');document.documentElement.style.fontSize=(cfg.font||12)+'px';document.documentElement.style.setProperty('--login-image',cfg.has_background?"url('/api/background-image')":'none')};function login(setup){const proposed=info.suggested_hostname||'pinas';app.innerHTML=`<section class="login ${cfg.has_background?'loginbg':''}"><div class="card"><div class="brand"><span class="mark">${PINAS_BRAND_ICON}</span><div>PiNAS<small>RASPBERRY PI NAS</small></div></div><h1>${setup?'Welcome to PiNAS':'Sign in'}</h1><p>${setup?'Name your NAS and create its administrator account.':'Manage your Raspberry Pi storage or access your files.'}</p><form id="auth">${setup?`<label class="field">NAS name / hostname<input name="hostname" required minlength="1" maxlength="63" pattern="[a-z][a-z0-9-]*[a-z0-9]|[a-z]" value="${esc(proposed)}" autocomplete="off"><span class="small">Your NAS will be reachable as <strong id="hostname-preview">${esc(proposed)}.local</strong> when local network discovery is available.</span></label>`:''}<label class="field">Administrator<input name="user" required value="${setup?'admin':''}" autocomplete="username"></label><label class="field">Password<input name="password" type="password" required minlength="${setup?12:1}" autocomplete="${setup?'new-password':'current-password'}"></label>${setup?'<label class="field">Confirm password<input name="confirm" type="password" required minlength="12" autocomplete="new-password"></label><p class="small">Use at least 12 characters. The administrator account is separate from Samba users.</p>':''}<button class="btn">${setup?'Create administrator':'Sign in'}</button><div id="message"></div></form></div></section>`;document.getElementById('auth').onsubmit=async e=>{e.preventDefault();let f=new FormData(e.target);if(setup&&f.get('password')!==f.get('confirm')){document.getElementById('message').textContent='Passwords do not match';return}try{await post(setup?'/api/setup':'/api/login',{user:f.get('user'),password:f.get('password'),...(setup?{hostname:String(f.get('hostname')||'').toLowerCase()}: {})});await init()}catch(err){document.getElementById('message').textContent=err.message}}};function shell(body){const oldActive=document.querySelector('nav button.active');if(oldActive)lastNavRect=oldActive.getBoundingClientRect();app.innerHTML=`<header><div class="brand"><span class="mark">${PINAS_BRAND_ICON}</span><div>PiNAS<small>RASPBERRY PI NAS</small></div></div><nav>${navItems().map(n=>`<button data-page="${n}" class="${n===page?'active':''}">${n}</button>`).join('')}<span class="nav-indicator" aria-hidden="true"></span></nav><button class="icon-btn" id="settings-trigger" aria-label="Settings" title="Settings">${SETTINGS_ICON}</button><button class="icon-btn" id="logout" aria-label="Sign out" title="Sign out">${LOGOFF_ICON}<span class="sr-only">Sign out</span></button></header><main>${body}<div class="footer"><span>PiNAS ${esc(info.version)} · Prototype</span><span>${esc(info.hostname)} · ${esc(info.profile||'essential')} profile</span></div></main>`;const navEl=document.querySelector('nav'),activeNav=navEl.querySelector('button.active'),indicator=navEl.querySelector('.nav-indicator');if(activeNav){const navRect=navEl.getBoundingClientRect(),target=activeNav.getBoundingClientRect();let startX=target.left-navRect.left+navEl.scrollLeft,startW=target.width;if(lastNavRect){startX=lastNavRect.left-navRect.left+navEl.scrollLeft;startW=lastNavRect.width}indicator.style.transition='none';indicator.style.transform=`translateX(${startX}px)`;indicator.style.width=startW+'px';requestAnimationFrame(()=>{requestAnimationFrame(()=>{indicator.style.transition='';indicator.style.transform=`translateX(${target.left-navRect.left+navEl.scrollLeft}px)`;indicator.style.width=target.width+'px'})});lastNavRect=null}navEl.addEventListener('scroll',()=>{if(!activeNav)return;indicator.style.transition='none';indicator.style.transform=`translateX(${activeNav.offsetLeft}px)`;requestAnimationFrame(()=>indicator.style.transition='')},{passive:true});document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{page=b.dataset.page;render()});document.getElementById('settings-trigger').onclick=()=>openSettings();document.getElementById('logout').onclick=async()=>{await post('/api/logout',{});await init()}};function ring(percent,center,label,color){let r=52,c=2*Math.PI*r,p=Math.max(0,Math.min(100,percent));return `<svg class="ring" viewBox="0 0 150 150" role="img" aria-label="${esc(label)}: ${esc(center)}"><circle cx="75" cy="75" r="${r}" stroke="var(--soft)" stroke-width="13" fill="none"/><circle cx="75" cy="75" r="${r}" stroke="${color}" stroke-width="13" fill="none" stroke-linecap="round" stroke-dasharray="${(p*c/100).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 75 75)"/><text x="75" y="73" fill="var(--ink)" font-size="25" font-weight="700" text-anchor="middle">${esc(center)}</text><text x="75" y="92" fill="var(--muted)" font-size="11" text-anchor="middle">${esc(label)}</text></svg>`}
function drawCPU(){let target=document.getElementById('cpu-chart');if(!target)return;let samples=cpu.samples||[],minutes=cfg.cpu_history||10,now=Date.now()/1000,points=samples.filter(p=>p[0]>=now-minutes*60),max=Math.max(0,...points.map(p=>p[1]));let coords=points.map(p=>[8+((p[0]-(now-minutes*60))/(minutes*60))*624,108-p[1]]);let path=coords.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');target.innerHTML=`<svg viewBox="0 0 640 136" preserveAspectRatio="none" aria-hidden="true"><path d="M8 8H632 M8 58H632 M8 108H632" stroke="var(--line)" stroke-dasharray="4 5" fill="none"/>${coords.length>1?`<path d="${path}" stroke="var(--accent)" stroke-width="2.5" fill="none" stroke-linejoin="round" stroke-linecap="round"/>`:''}<text x="8" y="132" fill="var(--muted)" font-size="11">${minutes}m ago</text><text x="632" y="132" fill="var(--muted)" font-size="11" text-anchor="end">Now</text></svg>`;document.getElementById('cpu-current').textContent=(cpu.current??0).toFixed(1)+'%';document.getElementById('cpu-peak').textContent=max.toFixed(1)+'%';target.title=points.length?`${points.length} CPU samples; peak ${max.toFixed(1)}%`:'Waiting for CPU samples'}
async function refreshOverview(){if(page!=='Overview'||!csrf)return;try{let r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)return;let j=await r.json();if(!j.authenticated)return;const before=navItems().join('|')+'|'+storageReady()+'|'+(info.shares||[]).length;info=j.hardware||info;cpu=j.cpu||cpu;const after=navItems().join('|')+'|'+storageReady()+'|'+(info.shares||[]).length;if(before!==after){render();return}updateOverview()}catch(e){/* transient connectivity */}}
setInterval(refreshOverview,10000);
function uptimeText(seconds){if(seconds==null)return 'Unavailable';let days=Math.floor(seconds/86400),hours=Math.floor(seconds%86400/3600),mins=Math.floor(seconds%3600/60);return days?`${days}d ${hours}h`:hours?`${hours}h ${mins}m`:`${mins}m`}
async function checkSmartHealth(){
    const target=document.getElementById('smart-health-results'),button=document.getElementById('check-smart-health');
    if(!target||!button)return;
    button.disabled=true;target.textContent='Checking attached drives…';
    try{
        const r=await fetch('/api/smart-health',{cache:'no-store'}),j=await r.json();
        if(!r.ok)throw Error(j.error||'SMART check failed');
        if(!j.installed){target.innerHTML='<p>SMART Tools are not installed. Install the optional <code>smartmontools</code> package to enable disk health checks.</p><p class="small">Run: <code>sudo apt install smartmontools</code></p>';return}
        target.innerHTML=(j.drives||[]).map(d=>'<div class="line"><div><strong>'+esc(d.model||d.device)+'</strong><span class="small">'+esc(d.device)+'</span></div><div><span class="pill '+(d.status==='Healthy'?'good':'')+'">'+esc(d.status)+'</span> '+(d.temperature==null?'':esc(d.temperature)+'°C')+'</div></div>').join('')||'<p>No supported physical drives detected.</p>';
    }catch(e){target.textContent=e.message}finally{button.disabled=false}
}
async function refreshServiceHealth(){
    const target=document.getElementById('service-health-results');
    const notices=document.getElementById('service-health-warnings');
    const button=document.getElementById('refresh-service-health');
    if(!target||!notices)return;
    if(button)button.disabled=true;
    target.textContent='Checking services…';
    try{
        const response=await fetch('/api/service-health',{cache:'no-store'});
        const data=await response.json();
        if(!response.ok)throw Error(data.error||'Service health unavailable');
        const stateText={healthy:'Running',warning:'Attention',inactive:'Stopped','not-installed':'Not installed',pending:'Starting',unknown:'Unavailable'};
        target.innerHTML=(data.services||[]).map(s=>'<div class="line"><div><strong>'+esc(s.name)+'</strong><span class="small">'+esc(s.unit)+'</span></div><div><span class="pill '+(s.state==='healthy'?'good':'')+'">'+esc(stateText[s.state]||'Unavailable')+'</span><span class="small">'+esc(s.detail)+'</span></div></div>').join('');
        notices.innerHTML=(data.warnings||[]).length?'<h3>System messages</h3>'+(data.warnings||[]).map(w=>'<p class="small"><strong>'+esc(w.name)+':</strong> '+esc(w.message)+'</p>').join(''):'<p class="small">No service failures or reboot requirements detected in the checked items.</p>';
    }catch(error){target.textContent='Unable to check services: '+error.message;notices.textContent=''}finally{if(button)button.disabled=false}
}
function updateHealth(){const uptime=document.getElementById('health-uptime'),os=document.getElementById('health-os'),kernel=document.getElementById('health-kernel'),load=document.getElementById('health-load');if(uptime)uptime.textContent=uptimeText(info.uptime_seconds);if(os)os.textContent=info.os_name||'Unavailable';if(kernel)kernel.textContent=info.kernel||'Unavailable';if(load)load.textContent=(info.load||[]).map(n=>Number(n).toFixed(2)).join(' / ')||'Unavailable'}
function updateOverview(){if(page!=='Overview')return;let disksCount=(info.disks||[]).filter(d=>d.type==='disk').length;for(let [id,value] of [['count-disks',disksCount],['count-shares',info.shares?.length||0],['count-users',info.nas_users??'—']]){let el=document.getElementById(id);if(el)el.textContent=value}let mem=info.memory_total||1,used=info.memory_used||0,temp=info.temperature;let a=document.getElementById('memory-ring'),b=document.getElementById('temp-ring');if(a)a.innerHTML=ring(Math.round(100*used/mem),Math.round(100*used/mem)+'%','Used','var(--accent)')+`<p class="small">${size(used)} / ${size(mem)}</p>`;if(b)b.innerHTML=ring(temp??0,temp==null?'—':temp+'°C','Temperature',temp>=75?'var(--danger)':temp>=65?'var(--warning)':'var(--success)')+`<p class="small">${temp==null?'Unavailable':temp>=75?'High temperature':temp>=65?'Elevated temperature':'Normal temperature'}</p>`;drawCPU();updateHealth()} 
const head=(name,desc)=>`<h1>${name}</h1><p class="subtitle">${desc}</p>`;const disks=()=>(info.disks||[]).filter(d=>d.type==='disk'&&!/^(zram|ram|loop|nbd|sr|fd)\d*/i.test(d.name||'')&&!/^\/dev\/(zram|ram|loop)/i.test(d.path||''));
function diskSummary(){return disks().map(d=>{let fs=d.filesystems||[],total=fs.reduce((a,f)=>a+(f.total||0),0),used=fs.reduce((a,f)=>a+(f.used||0),0),pct=total?Math.min(100,Math.round(used/total*100)):0;return `<div class="disk-summary"><div class="disk-heading"><div><strong>${esc(d.model||d.name||'Attached disk')}</strong><span class="small">${esc(d.path)} · ${size(d.size)} capacity</span></div><span class="small">${total?`${size(used)} used · ${size(Math.max(0,total-used))} available`:'Not mounted / usage unavailable'}</span></div><div class="bar disk-usage" role="progressbar" aria-label="${esc(d.model||d.name)} storage used" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></div><div class="disk-foot"><span>${total?pct+'% used':'No mounted filesystem'}</span><span>${total?size(total)+' filesystem capacity':'Connect or mount a data volume'}</span></div></div>`}).join('')||'<p class="small">No attached data disks detected. The PiNAS system disk is intentionally hidden.</p>'}
function render(){if(!navItems().includes(page))page='Overview';let body='';if(page==='Overview'){let used=info.memory_used||0,total=info.memory_total||1,pct=Math.min(100,Math.round(100*used/total)),temp=info.temperature,disksCount=disks().filter(d=>d.type==='disk').length;body=head('Overview','Your Raspberry Pi NAS at a glance.')+`<div class="grid overview">`+setupNotice()+`<div class="card stat clickable" role="button" tabindex="0" data-jump="Storage"><div class="label">Attached disks</div><div class="big" id="count-disks">${disksCount}</div><span class="small">Physical drives</span></div><div class="card stat clickable" role="button" tabindex="0" data-jump="Shares"><div class="label">Network shares</div><div class="big" id="count-shares">${info.shares?.length||0}</div><span class="small">Samba shares</span></div><div class="card stat clickable" role="button" tabindex="0" data-jump="Users"><div class="label">NAS users</div><div class="big" id="count-users">${info.nas_users??'—'}</div><span class="small">Samba accounts</span></div><div class="card wide"><div class="chart-title"><h2>CPU Activity</h2><span class="pill">Last ${cfg.cpu_history||10} minutes</span></div><div id="cpu-chart" class="cpu-chart" role="img" aria-label="CPU activity history"></div><div class="chart-footer"><div><div class="label">Current CPU</div><div class="big" id="cpu-current">—</div></div><div><div class="label">Peak in view</div><strong id="cpu-peak">—</strong></div></div></div><div class="card metric"><h2>Memory</h2><div id="memory-ring">${ring(pct,pct+'%','Used','var(--accent)')}<p class="small">${size(used)} / ${size(total)}</p></div></div><div class="card metric"><h2>CPU Temperature</h2><div id="temp-ring">${ring(temp==null?0:Math.min(100,temp),temp==null?'—':temp+'°C','Temperature',temp!=null&&temp>=75?'#c53540':temp!=null&&temp>=65?'#c28a22':'#299768')}<p class="small">${temp==null?'Unavailable':temp>=75?'High temperature':temp>=65?'Elevated temperature':'Normal temperature'}</p></div></div><div class="card metric"><h2>Raspberry Pi</h2><strong>${esc(info.model)}</strong><p class="small">${esc(info.hostname)}</p><span class="pill ${info.throttle==='throttled=0x0'?'good':''}">${esc(info.throttle||'Throttle status unavailable')}</span></div><div class="card wide"><h2>System health</h2><div class="health-grid"><div><span class="label">Uptime</span><strong id="health-uptime">${uptimeText(info.uptime_seconds)}</strong></div><div><span class="label">Operating system</span><strong id="health-os">${esc(info.os_name||'Unavailable')}</strong></div><div><span class="label">Kernel</span><strong id="health-kernel">${esc(info.kernel||'Unavailable')}</strong></div><div><span class="label">Load average (1 / 5 / 15 min)</span><strong id="health-load">${esc((info.load||[]).map(n=>Number(n).toFixed(2)).join(' / ')||'Unavailable')}</strong></div></div><p class="small">System information is read directly from Linux and refreshed with the Overview page. No additional monitoring service is required.</p></div><div class="card wide"><div class="chart-title"><h2>NAS service health</h2><button class="btn outline" id="refresh-service-health">Refresh</button></div><p class="small">Read-only service checks when Overview is opened or Refresh is pressed.</p><div id="service-health-warnings" role="status"></div><div id="service-health-results" role="status">Checking services…</div></div><div class="card wide"><h2>Storage at a glance</h2>${diskSummary()}</div></div>`}else if(page==='Storage'){body=head('Storage','Your attached data drives. System storage and swap devices are excluded.')+`<div class="card"><h2>Detected drives</h2>${disks().map((d,i)=>{const vs=d.volumes||[],v=vs.find(x=>x.mounts?.length)||vs[0],fs=[...new Set(vs.map(x=>x.fs).filter(Boolean))],mounts=vs.flatMap(x=>x.mounts||[]),persistent=vs.some(x=>x.persistent);return `<div class="storage-disk-entry"><div class="disk-properties"><div><span>Name:</span><strong>${esc(d.model||d.name||'Attached drive')}</strong></div><div><span>Capacity:</span><strong>${size(d.size)}</strong></div><div><span>File System:</span><strong>${esc(fs.join(', ')||'None detected')}</strong></div><div><span>Mount Status:</span><strong>${mounts.length?'Mounted':'Not mounted'}</strong></div><div><span>Mount Point:</span><strong>${esc(mounts.join(', ')||'—')}</strong></div><div><span>Persistent Mount:</span><strong>${persistent?'Yes':'No'}</strong></div></div><button class="btn outline storage-action" data-disk="${i}">Manage</button></div>`}).join('')||'<p>No attached data drives detected. System disks and zram swap are intentionally hidden.</p>'}</div><div class="card" style="margin-top:16px"><h2>Disk health</h2><p class="small">Read-only SMART health and temperature checks, on demand. Some USB adapters do not expose SMART data.</p><button class="btn outline" id="check-smart-health">Check disk health</button><div id="smart-health-results" style="margin-top:12px" role="status"></div></div><p class="hint">Existing filesystems can be adopted without formatting. Wiping and formatting remain unavailable until the privileged destructive-operation safeguards are implemented and tested.</p>`}else if(page==='RAID'){const arrays=info.raid||[];body=head('Software RAID','Discover and monitor Linux mdadm arrays. RAID creation remains protected.')+`<div class="card"><h2>Existing RAID arrays</h2>${arrays.map(r=>{const degraded=Number(r.degraded||0),healthy=r.state==='clean'||r.state==='active',status=degraded?'Degraded':healthy?'Healthy':'Check status';return `<div class="raid-array-entry"><div class="line"><div><strong>${esc(r.name)} · ${esc(r.level)}</strong><span class="small">${esc(r.state||'Unknown')} · ${r.raid_disks??'—'} expected members · ${r.members?.length??0} detected</span></div><span class="pill ${!degraded&&healthy?'good':''}">${status}</span></div><div class="disk-properties"><div><span>Sync activity:</span><strong>${esc(r.sync||'Unknown')}</strong></div><div><span>Degraded members:</span><strong>${degraded}</strong></div><div><span>Metadata:</span><strong>${esc(r.metadata||'—')}</strong></div></div>${r.progress!=null&&r.sync!=='idle'?`<div class="small">${esc(r.sync)}: ${r.progress}%</div><div class="progress-track"><div class="progress-fill" style="width:${Math.min(100,Math.max(0,r.progress))}%"></div></div>`:''}${(r.members||[]).map(m=>`<div class="line"><span>${esc(m.device)} · Slot ${esc(m.slot||'—')}</span><span class="small">${esc(m.state)}</span></div>`).join('')||'<p class="hint">No members reported by the kernel.</p>'}</div>`}).join('')||'<p>No mdadm arrays detected. You can review the RAID planner without changing any disks.</p>'}<button class="btn outline" id="raid-create">Plan a RAID array</button></div><p class="hint">This release is monitoring-only. RAID creation, deletion and member replacement remain disabled until device safeguards and recovery workflows have been tested. RAID is not a backup.</p>`}else if(page==='Shares'){body=head('Network shares','Manage shared folders and their access permissions.')+`<div class="card"><h2>Configured network shares</h2><div class="share-top-actions"><button class="btn outline icon-btn share-icon-btn" id="create-nas-share" title="Create share" aria-label="Create share">${CREATE_SHARE_ICON}</button></div>${(info.shares||[]).map(s=>{const d=(info.share_details||[]).find(x=>x.name===s);const perms=d?Object.entries(d.access||{}).map(([u,p])=>esc(u)+' | '+(p==='rw'?'Read & Write':'Read Only')).join(', '):'Unavailable';return `<div class="line share-entry"><div class="share-meta"><div><strong>Name:</strong> <span>${esc(s)}</span></div><div><strong>Location:</strong> <span>${esc(d?.folder||'Unavailable')}</span></div><div><strong>Permissions:</strong> <span>${perms}</span></div><div><strong>Type:</strong> <span>SMB</span></div></div><div class="share-actions"><button class="btn outline icon-btn share-icon-btn" data-delete-share="${esc(s)}" title="${d?'Remove share':'External share — not managed by PiNAS'}" aria-label="Remove share ${esc(s)}" ${d?'':'disabled'}>${DELETE_SHARE_ICON}</button><button class="btn outline icon-btn share-icon-btn" data-edit-share="${esc(s)}" title="${d?'Edit share':'External share — not managed by PiNAS'}" aria-label="Edit share ${esc(s)}" ${d?'':'disabled'}>${EDIT_SHARE_ICON}</button></div></div>`}).join('')||'<p>No network shares detected.</p>'}</div><p class="hint">Removing a share stops network access but preserves the folder and its contents. Editing a share changes its network name or access permissions without moving its folder.</p>`} else if(page==='Users'){body=head('User Management','Manage PiNAS administrators and NAS users.')+`<div class="user-top-actions"><button class="btn outline add-user-button" id="add-nas-user">${ADD_USER_ICON}<span>Add New User</span></button><button class="btn outline add-user-button" id="add-admin-user">${ADD_USER_ICON}<span>Add Admin User</span></button></div><div class="user-management-cards"><div class="card"><h2>Administrators</h2><p>Accounts authorised to manage PiNAS settings and storage.</p>${(info.admin_user_list||[]).map(u=>`<div class="line"><div><strong>${esc(u.display_name||u.name)}</strong><span class="small">@${esc(u.name)}</span></div><button class="btn outline edit-user-button" data-edit-admin="${esc(u.name)}">${EDIT_USER_ICON}<span>Edit User</span></button></div>`).join('')||'<p>No administrator accounts listed.</p>'}</div><div class="card"><h2>Users</h2><p>NAS accounts for accessing shared folders. Share permissions are managed from the Shares page.</p>${(info.nas_user_list||[]).map(u=>`<div class="line"><div><strong>${esc(u.display_name||u.name)}</strong><span class="small">@${esc(u.name)}</span></div><button class="btn outline edit-user-button" data-edit-nas="${esc(u.name)}">${EDIT_USER_ICON}<span>Edit User</span></button></div>`).join('')||'<p>No NAS users configured yet.</p>'}</div></div>`}else if(page==='Applications'){body=head('Applications','Start simple, then expand your NAS as needed.')+`<div class="grid">${['Scheduled backups','NFS sharing','MiniDLNA',...(info.capabilities?.curated_apps?['Curated apps (future release)']:[])].map(x=>`<div class="card"><h2>${x}</h2><p>Optional capability</p><button class="btn outline" disabled>Coming soon</button></div>`).join('')}</div>`}if(page==='Updates'){body=head('System Updates','Raspberry Pi OS and Debian package updates. PiNAS application updates are managed separately.')+`<div class="card"><h2>OS Updates</h2><div class="updates-actions"><button class="btn outline" id="check-os-updates" style="display:inline-flex;align-items:center;gap:9px"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><g fill="none"><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12.46 6H2.65m9.81 6H2.65m9.81 6H2.65M16.23 7.21l.88 1.08c.36.44.54.66.78.66s.41-.22.77-.67l2.72-3.35"/><rect width="5.15" height="5.15" fill="currentColor" opacity=".2" rx="1.5" transform="matrix(0 -1 -1 0 21.38 18.04)"/><rect width="5.15" height="5.15" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" rx="1.5" transform="matrix(0 -1 -1 0 21.38 18.04)"/></g></svg><span>Check for updates</span></button><button class="btn outline" id="install-os-updates" style="display:inline-flex;align-items:center;gap:9px"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13.65 6H2.61m11.04 6H2.61m11.04 6H2.61M17.13 6.1l.62.77c.36.44.54.66.78.66s.42-.22.77-.66l2.18-2.7m-4.35 7.93l.62.77c.36.44.54.66.78.66s.42-.22.77-.66l2.18-2.7m-4.35 7.93l.62.77c.36.44.54.66.78.66s.42-.22.77-.66l2.18-2.7"/></svg><span>Install updates</span></button></div><div class="updates-status-row"><div id="updates-message" role="status">Loading available updates…</div><span id="updates-spinner" class="updates-spinner" role="img" aria-label="Update operation in progress" hidden></span></div><div id="updates-list"></div><details class="updates-log"><summary>CLI output</summary><pre id="updates-output" class="small"></pre></details><p class="hint">Checking refreshes APT metadata without installing packages. Installation uses a standard APT upgrade without removing packages. Some updates may require a reboot.</p></div><div class="card" style="margin-top:16px"><h2>Automatic updates</h2><button class="btn outline save-schedule-button" id="save-updates-schedule"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><g fill="none"><path fill="currentColor" d="M4.71 20.95c-.93 0-1.4 0-1.69-.28l-.01-.02c-.29-.29-.29-.75-.29-1.69V4.9c0-.94 0-1.4.3-1.7c.29-.3.77-.3 1.72-.3c.77 0 1.15 0 1.42.22c.28.22.36.59.54 1.33l.23.98c.17.74.26 1.11.53 1.33s.65.21 1.41.21h2.45c.84 0 1.26 0 1.54-.25c.28-.24.34-.66.44-1.5l.3-2.4l4.05 2.82l2.95 2.6c.33.29.5.44.59.63c.09.2.09.42.09.87V19c0 .89 0 1.33-.26 1.62l-.07.06c-.29.26-.73.26-1.61.26c-.78 0-1.17 0-1.44-.22l-.07-.05c-.25-.24-.3-.63-.42-1.4l-.5-3.55c-.11-.77-.16-1.15-.42-1.4c-.26-.23-.65-.26-1.43-.31l-3.06-.2l-3.06.2c-.79.05-1.18.08-1.45.33c-.26.25-.3.64-.4 1.43l-.4 3.42c-.1.83-.15 1.24-.43 1.5h-.01c-.28.25-.7.25-1.54.25" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8.77 21.38c-2.83 0-4.24 0-5.12-.88s-.88-2.3-.88-5.12V8.6c0-2.83 0-4.24.88-5.12s2.3-.88 5.12-.88h3.58c1.05 0 1.58 0 2.07.18s.9.5 1.72 1.17l1.72 1.4l1.1.88c1.11.89 1.67 1.33 1.97 1.95s.3 1.33.3 2.75v4.45c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88z"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6.64 2.82v.65c0 1.55 0 2.32.4 2.86a2 2 0 0 0 .4.39c.53.4 1.3.4 2.84.4c1.55 0 2.32 0 2.86-.4a2 2 0 0 0 .39-.4c.4-.53.4-1.3.4-2.85v-.65m3.43 18.44v-3.29c0-1.89 0-2.83-.58-3.41c-.59-.59-1.53-.59-3.42-.59h-2.72c-1.89 0-2.83 0-3.42.59c-.58.58-.58 1.52-.58 3.41v3.29"/></g></svg><span>Save schedule</span></button><p id="updates-schedule-message" class="small" role="status"></p><p class="small">Choose how often PiNAS checks for and installs all available OS package updates.</p><fieldset class="updates-schedule-options"><legend>Pick your schedule</legend><label><input type="radio" name="updates-schedule" value="off" checked><span>Off — Manual updates only</span></label><label><input type="radio" name="updates-schedule" value="daily"><span>Daily</span></label><label><input type="radio" name="updates-schedule" value="weekly"><span>Weekly</span></label><label><input type="radio" name="updates-schedule" value="monthly"><span>Monthly</span></label></fieldset><p id="updates-schedule-description" class="small" aria-live="polite"></p><p class="hint">Times use the Raspberry Pi's local timezone. Automatic updates do not reboot the NAS. A scheduled update may temporarily restart services.</p></div>`}shell(body);if(page==='Updates'){const scheduleRadios=[...document.querySelectorAll('input[name="updates-schedule"]')],desc=document.getElementById('updates-schedule-description');const selectedSchedule=()=>scheduleRadios.find(r=>r.checked)?.value||'off';const descriptions={off:'Automatic updates are disabled.',daily:'Updates will be checked and installed at 01:00 every day.',weekly:'Updates will be checked and installed every Friday at 01:00.',monthly:'Updates will be checked and installed on the 28th of every month at 01:00.'};const updateScheduleDescription=()=>{desc.textContent=descriptions[selectedSchedule()]};scheduleRadios.forEach(r=>r.addEventListener('change',updateScheduleDescription));updateScheduleDescription();document.getElementById('save-updates-schedule').onclick=async()=>{const b=document.getElementById('save-updates-schedule'),m=document.getElementById('updates-schedule-message');b.disabled=true;m.textContent='Saving schedule…';try{await post('/api/updates',{action:'schedule',schedule:selectedSchedule()});m.textContent='Schedule saved.';await loadUpdates()}catch(e){m.textContent=e.message}finally{b.disabled=false}};document.getElementById('install-os-updates').onclick=async()=>{const pw=await updatePasswordDialog();if(pw===null)return;document.getElementById('updates-spinner').hidden=false;document.getElementById('updates-message').textContent='Starting update installation…';try{await post('/api/updates',{action:'upgrade',admin_password:pw});await loadUpdates()}catch(e){document.getElementById('updates-message').textContent=e.message}};document.getElementById('check-os-updates').onclick=async()=>{const b=document.getElementById('check-os-updates');b.disabled=true;document.getElementById('updates-spinner').hidden=false;document.getElementById('updates-message').textContent='Checking for updates…';try{await post('/api/updates',{action:'refresh'});await loadUpdates()}catch(e){document.getElementById('updates-message').textContent=e.message}finally{await loadUpdates()}};loadUpdates()}if(page==='Overview'){document.querySelectorAll('[data-jump]').forEach(el=>{if(!navItems().includes(el.dataset.jump)){el.classList.remove('clickable');el.removeAttribute('role');el.removeAttribute('tabindex');el.removeAttribute('data-jump')}})}if(page==='Users'){document.getElementById('add-nas-user')?.addEventListener('click',openNasUserWizard);document.getElementById('add-admin-user')?.addEventListener('click',()=>openAccountWizard('admin'));document.querySelectorAll('[data-edit-nas]').forEach(b=>b.onclick=()=>openAccountWizard('nas',(info.nas_user_list||[]).find(u=>u.name===b.dataset.editNas)));document.querySelectorAll('[data-edit-admin]').forEach(b=>b.onclick=()=>openAccountWizard('admin',(info.admin_user_list||[]).find(u=>u.name===b.dataset.editAdmin)))}if(page==='Shares'){document.getElementById('create-nas-share')?.addEventListener('click',openNasShareWizard);document.querySelectorAll('[data-delete-share]').forEach(b=>b.addEventListener('click',()=>removeNasShare(b.dataset.deleteShare)));document.querySelectorAll('[data-edit-share]').forEach(b=>b.addEventListener('click',()=>editNasShare(b.dataset.editShare)))}if(page==='RAID'){document.getElementById('raid-create')?.addEventListener('click',openRaidWizard)}if(page==='Storage'){document.getElementById('check-smart-health')?.addEventListener('click',checkSmartHealth);document.querySelectorAll('[data-disk]').forEach(b=>b.onclick=()=>openDiskWizard(Number(b.dataset.disk)))}if(page==='Overview'){document.getElementById('refresh-service-health')?.addEventListener('click',refreshServiceHealth);refreshServiceHealth();document.querySelectorAll('[data-jump]').forEach(el=>{el.onclick=()=>{page=navItems().includes(el.dataset.jump)?el.dataset.jump:'Storage';render()};el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();el.click()}}});drawCPU()}document.querySelectorAll('[data-next]').forEach(b=>b.onclick=()=>{page=b.dataset.next;render()})};

function updatePasswordDialog(){return new Promise(resolve=>{const overlay=document.createElement('div');overlay.className='modal-overlay';overlay.innerHTML='<div class="settings-modal card" role="dialog" aria-modal="true" aria-label="Install updates"><h2>Install system updates</h2><p>APT will upgrade available packages without removing packages. Back up important data first. A reboot may be required.</p><label class="field">Current administrator password<input type="password" autocomplete="current-password" id="apt-password"></label><div class="modal-actions"><button class="btn outline" id="apt-cancel">Cancel</button><button class="btn" id="apt-confirm">Install updates</button></div></div>';document.body.appendChild(overlay);const close=v=>{overlay.remove();resolve(v)};overlay.querySelector('#apt-cancel').onclick=()=>close(null);overlay.querySelector('#apt-confirm').onclick=()=>close(overlay.querySelector('#apt-password').value);overlay.onkeydown=e=>{if(e.key==='Escape')close(null);if(e.key==='Enter')close(overlay.querySelector('#apt-password').value)};overlay.querySelector('#apt-password').focus()})}
async function loadUpdates(){
 const message=document.getElementById('updates-message'),list=document.getElementById('updates-list');if(!message)return;
 try{const r=await fetch('/api/updates',{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error(j.error||'Could not read updates');
 const status=j.status||{};const radios=[...document.querySelectorAll('input[name="updates-schedule"]')];if(radios.length&&!radios.some(r=>r===document.activeElement)){const selected=j.schedule||'off';radios.forEach(r=>{r.checked=r.value===selected});radios.find(r=>r.checked)?.dispatchEvent(new Event('change'))}const output=document.getElementById('updates-output');if(output)output.textContent=status.output||'';const install=document.getElementById('install-os-updates');if(install)install.disabled=!!status.running||!j.packages?.length;const check=document.getElementById('check-os-updates');if(check)check.disabled=!!status.running;const spinner=document.getElementById('updates-spinner');if(spinner)spinner.hidden=!status.running;message.textContent=status.running?(status.operation==='upgrade'?'Installing available updates…':'Refreshing package indexes…'):j.error?'APT: '+j.error:status.error?'Last check failed: '+status.error:`${j.packages.length} available package update${j.packages.length===1?'':'s'}${j.reboot_required?' · Reboot required':''}`;
 list.innerHTML=(j.packages||[]).length?`<div style="overflow-x:auto"><table style="width:100%;text-align:left;border-spacing:0 9px"><thead><tr><th>Package</th><th>Installed</th><th>Available</th></tr></thead><tbody>${j.packages.map(p=>`<tr><td>${esc(p.name)}<div class="small">${esc(p.repository)} · ${esc(p.architecture)}</div></td><td>${esc(p.installed)}</td><td>${esc(p.candidate)}</td></tr>`).join('')}</tbody></table></div>`:!j.error?'<p class="small">No upgradable packages are currently listed in the local APT indexes.</p>':'';
 if(status.running&&page==='Updates')setTimeout(()=>{if(page==='Updates')loadUpdates()},3000);
 }catch(e){message.textContent=e.message}
}
function openRaidWizard(){
 const available=disks().filter(d=>!d.read_only&&Number(d.size)>0);
 const overlay=document.createElement('div');overlay.className='modal-overlay';overlay.id='raid-overlay';
 const close=()=>{document.removeEventListener('keydown',onKey);overlay.remove()};
 const onKey=e=>{if(e.key==='Escape')close()};document.addEventListener('keydown',onKey);
 const options=available.map((d,i)=>`<label class="raid-disk"><input type="checkbox" data-raid-disk="${i}"><span><strong>${esc(d.model||d.name)}</strong><small>${esc(d.path)} · ${size(d.size)}${d.volumes?.length?' · Existing partitions/data will be erased':''}</small></span></label>`).join('');
 overlay.innerHTML=`<section class="card settings-modal raid-wizard" role="dialog" aria-modal="true" aria-labelledby="raid-title" tabindex="-1"><div class="modal-heading"><h2 id="raid-title">Set up software RAID</h2><button class="icon-btn" id="raid-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><p>Select the disks to combine. <strong class="danger">Creating an array destroys all existing data on every selected disk.</strong> Back up anything you want to keep before continuing.</p><h3>1. Select disks</h3>${options||'<p>No eligible writable data disks detected.</p>'}<p id="raid-selection" class="small" aria-live="polite">Select at least two disks.</p><h3>2. RAID layout</h3><label class="field">RAID type<select id="raid-level"><option value="1">RAID 1 — Mirror (recommended for two disks)</option><option value="0">RAID 0 — Stripe (no redundancy)</option><option value="5">RAID 5 — Distributed parity (three or more disks)</option></select></label><div id="raid-layout-description" class="hint"></div><h3>3. Filesystem</h3>${Object.entries(FS_GUIDE).map(([key,v])=>`<label class="wizard-option"><input type="radio" name="raid-filesystem" value="${key}" ${key==='ext4'?'checked':''}><strong>${key.toUpperCase()}</strong>${key==='ext4'?' · Recommended':''} — ${v[0]}<small>${v[1]}</small></label>`).join('')}<h3>4. Review</h3><div class="hint" id="raid-review" aria-live="polite"></div><p class="danger"><strong>Destructive operation:</strong> the selected disks would be wiped, partitioned, assembled into an mdadm array, formatted and mounted automatically. The administrator password and final explicit confirmation will be required when RAID creation is implemented.</p></div><div class="modal-actions"><button class="btn outline" id="raid-cancel">Close</button><button class="btn" disabled title="Protected RAID creation not implemented">Create RAID (coming soon)</button></div></section>`;
 document.body.appendChild(overlay);overlay.querySelector('#raid-close').onclick=close;overlay.querySelector('#raid-cancel').onclick=close;overlay.onclick=e=>{if(e.target===overlay)close()};
 const level=overlay.querySelector('#raid-level');const boxes=[...overlay.querySelectorAll('[data-raid-disk]')];
 const refresh=()=>{const selected=boxes.filter(b=>b.checked).map(b=>available[Number(b.dataset.raidDisk)]),n=selected.length,min=selected.length?Math.min(...selected.map(d=>Number(d.size))):0;const validLevels=n>=3?['0','1','5']:['0','1'];level.querySelector('option[value="5"]').disabled=n<3;if(!validLevels.includes(level.value))level.value='1';const l=level.value;const estimated=n>=2?(l==='0'?n*min:l==='1'?min:(n-1)*min):0;const lost=n>=2?selected.reduce((a,d)=>a+Number(d.size),0)-n*min:0;overlay.querySelector('#raid-selection').textContent=n?`${n} disk${n===1?'':'s'} selected · Smallest disk: ${size(min)}`:'Select at least two disks.';
 overlay.querySelector('#raid-layout-description').textContent=l==='0'?'RAID 0 combines disk capacity and performance, but offers NO redundancy. Failure of one disk loses the entire array.':l==='1'?'RAID 1 mirrors data. With two disks, one disk can fail without immediate data loss; capacity is limited to the smallest disk. For three or more disks, mdadm mirrors across all selected disks.':'RAID 5 distributes parity across three or more disks. It tolerates one disk failure, but rebuilding a degraded array can be slow and risky.';
 overlay.querySelector('#raid-review').innerHTML=n<2?'Select at least two data disks to calculate capacity.':`<strong>Estimated usable array capacity: ${size(estimated)}</strong><p class="small">${n} × ${size(min)} equal-sized member partitions · ${l==='0'?'Striping':l==='1'?'Mirroring':'Single distributed parity'} · Before filesystem overhead</p>${lost?`<p class="small">${size(lost)} of larger-disk capacity would be unused because each member is limited by the smallest selected disk.</p>`:''}<p class="small">All selected disks would be erased. RAID is not a backup.</p>`;};
 boxes.forEach(b=>b.onchange=refresh);level.onchange=refresh;refresh();overlay.querySelector('.raid-wizard').focus();
}
function openNasUserWizard(){
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 overlay.innerHTML=`<div class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="Create NAS user"><div class="modal-heading"><h2>Create NAS user</h2><button class="icon-btn" id="nu-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><p>Create a Samba account for shared folders and web file access. This account cannot log in through SSH or the Linux console.</p><form id="nu-form"><label class="field">Display Name<input name="display_name" required maxlength="80" autocomplete="off" placeholder="e.g. Alice Smith"></label><label class="field">Username<input name="username" required minlength="3" maxlength="32" pattern="[a-z_][a-z0-9_-]{2,31}" autocomplete="off" placeholder="e.g. alice"></label><label class="field">Password<input name="password" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></label><label class="field">Confirm Password<input name="confirm" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></label><p class="hint">The display name is only used in the PiNAS web interface. The username is used for Samba and file access. Share permissions are configured separately.</p><div id="nu-message" role="status"></div><div class="modal-actions"><button class="btn outline" type="button" id="nu-cancel">Cancel</button><button class="btn" type="submit" id="nu-submit">Create user</button></div></form></div></div>`;
 document.body.appendChild(overlay);const close=()=>overlay.remove();overlay.querySelector('#nu-close').onclick=close;overlay.querySelector('#nu-cancel').onclick=close;
 overlay.querySelector('#nu-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),msg=overlay.querySelector('#nu-message'),btn=overlay.querySelector('#nu-submit');if(f.get('password')!==f.get('confirm')){msg.textContent='Passwords do not match.';return}btn.disabled=true;msg.textContent='Creating account…';try{await post('/api/nas-users',{display_name:f.get('display_name'),username:f.get('username'),password:f.get('password')});let j=await (await fetch('/api/state',{cache:'no-store'})).json();info=j.hardware||info;close();render()}catch(err){msg.textContent=err.message;btn.disabled=false}};
 overlay.querySelector('[name=username]').focus();
}
function openAccountWizard(kind,existing=null){
 const editing=!!existing,admin=kind==='admin',overlay=document.createElement('div');overlay.className='modal-overlay';
 const title=editing?'Edit User':admin?'Add Admin User':'Add New User';
 overlay.innerHTML=`<section class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="${title}"><div class="modal-heading"><h2>${title}</h2><button class="icon-btn" id="account-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><form id="account-form"><label class="field">Display Name<input name="display_name" required maxlength="80" value="${esc(existing?.display_name||'')}"></label><label class="field">Username<input name="username" required minlength="3" maxlength="32" pattern="[a-z_][a-z0-9_-]{2,31}" value="${esc(existing?.name||'')}" ${editing?'disabled':''}></label><label class="field">${editing?'New Password (leave blank to keep current)':'Password'}<input name="password" type="password" minlength="12" maxlength="256" ${editing?'':'required'} autocomplete="new-password"></label><label class="field">Confirm Password<input name="confirm" type="password" minlength="12" maxlength="256" ${editing?'':'required'} autocomplete="new-password"></label>${admin&&!editing?'<label class="field">Current Administrator Password<input name="admin_password" type="password" required autocomplete="current-password"></label>':''}<p class="hint">${editing?'The username cannot be changed. Leave password fields blank to keep the existing password.':admin?'Administrators can manage PiNAS. Confirm your own password to authorise creation.':'NAS users access shared folders and cannot administer PiNAS.'}</p><div id="account-message" role="status"></div><div class="modal-actions"><button class="btn outline" type="button" id="account-cancel">Cancel</button><button class="btn" id="account-submit" type="submit">${editing?'Save Changes':'Create User'}</button></div></form></div></section>`;
 document.body.append(overlay);const close=()=>overlay.remove();overlay.querySelector('#account-close').onclick=close;overlay.querySelector('#account-cancel').onclick=close;
 overlay.querySelector('#account-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),msg=overlay.querySelector('#account-message'),btn=overlay.querySelector('#account-submit');if(f.get('password')!==f.get('confirm')){msg.textContent='Passwords do not match.';return}btn.disabled=true;try{const payload={kind,username:editing?existing.name:f.get('username'),display_name:f.get('display_name'),password:f.get('password')};if(admin&&!editing)payload.admin_password=f.get('admin_password');await post(editing?'/api/edit-user':admin?'/api/admin-users':'/api/nas-users',payload);const j=await(await fetch('/api/state',{cache:'no-store'})).json();info=j.hardware||info;close();render()}catch(err){msg.textContent=err.message;btn.disabled=false}};
 overlay.querySelector('[name=display_name]').focus();
}
async function editNasShare(name){
 const d=(info.share_details||[]).find(x=>x.name===name);if(!d)return;
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 const users=info.nas_user_list||[];
 overlay.innerHTML=`<section class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="Edit share" tabindex="-1"><div class="modal-heading"><h2>Edit network share</h2><button class="icon-btn" id="es-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><p class="small">Location: ${esc(d.folder||'Unavailable')}. The folder and files will not be moved or renamed.</p><form id="es-form"><label class="field">Share name<input name="new_name" maxlength="32" required pattern="[A-Za-z][A-Za-z0-9 _-]{0,31}" value="${esc(name)}"></label><h3>User permissions</h3>${users.map(u=>`<label class="field">${esc(u.name)}<select data-share-user="${esc(u.name)}"><option value="none" ${!d.access?.[u.name]?'selected':''}>No Access</option><option value="ro" ${d.access?.[u.name]==='ro'?'selected':''}>Read Only</option><option value="rw" ${d.access?.[u.name]==='rw'?'selected':''}>Read & Write</option></select></label>`).join('')}<label class="field">Administrator password<input name="admin_password" type="password" required autocomplete="current-password"></label><p class="hint">Changes to permissions on existing files are not recursive. Existing file permissions may still restrict access.</p><p id="es-message" role="status"></p><div class="modal-actions"><button class="btn outline" type="button" id="es-cancel">Cancel</button><button class="btn" type="submit" id="es-save">Save changes</button></div></form></div></section>`;
 document.body.appendChild(overlay);const close=()=>overlay.remove();overlay.querySelector('#es-close').onclick=close;overlay.querySelector('#es-cancel').onclick=close;
 overlay.querySelector('#es-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget,access={};overlay.querySelectorAll('[data-share-user]').forEach(el=>{if(el.value!=='none')access[el.dataset.shareUser]=el.value});const msg=overlay.querySelector('#es-message'),btn=overlay.querySelector('#es-save');if(!Object.keys(access).length){msg.textContent='Assign access to at least one user.';return}btn.disabled=true;msg.textContent='Saving changes…';try{await post('/api/edit-share',{name,new_name:new FormData(form).get('new_name'),access,admin_password:new FormData(form).get('admin_password')});const r=await fetch('/api/state',{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error('Unable to refresh shares');info=j.hardware||info;close();render()}catch(error){msg.textContent=error.message;btn.disabled=false}};
 overlay.querySelector('[name=new_name]').focus();
}
function removeNasShare(name){
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 overlay.innerHTML=`<section class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="Remove share" tabindex="-1"><div class="modal-heading"><h2>Remove network share</h2><button class="icon-btn" id="ds-close" aria-label="Close">${CANCEL_ICON}</button></div><p>Remove the Samba share <strong>${esc(name)}</strong>?</p><p class="hint">The network share will be removed, but its folder and files will be preserved on disk.</p><form id="ds-form"><label class="field">Administrator password<input type="password" name="admin_password" required autocomplete="current-password"></label><p id="ds-message" role="status"></p><div class="modal-actions"><button type="button" class="btn outline" id="ds-cancel">Cancel</button><button type="submit" class="btn danger" id="ds-submit">Remove share</button></div></form></section>`;
 document.body.appendChild(overlay);const close=()=>overlay.remove();
 overlay.querySelector('#ds-close').onclick=close;overlay.querySelector('#ds-cancel').onclick=close;
 overlay.querySelector('#ds-form').onsubmit=async e=>{e.preventDefault();const btn=overlay.querySelector('#ds-submit'),msg=overlay.querySelector('#ds-message');btn.disabled=true;msg.textContent='Removing share…';try{await post('/api/delete-share',{name,admin_password:new FormData(e.currentTarget).get('admin_password')});const r=await fetch('/api/state',{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error('Unable to refresh shares');info=j.hardware||info;close();render()}catch(error){msg.textContent=error.message;btn.disabled=false}};
 overlay.querySelector('[name=admin_password]').focus();
}
function openNasShareWizard(){
 const users=info.nas_user_list||[],volumes=disks().flatMap(d=>(d.volumes||[]).filter(v=>['ext4','xfs','btrfs'].includes(v.fs)&&v.persistent&&v.mounts?.length).map(v=>({path:v.path,label:(d.model||d.name)+' · '+v.name+' · '+v.mounts[0]})));
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 overlay.innerHTML=`<section class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="Create NAS share" tabindex="-1"><div class="modal-heading"><h2>Create network share</h2><button class="icon-btn" id="ns-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><p>Choose a name, a configured data disk and the users who may access this share. PiNAS creates a new folder without changing existing files.</p><form id="ns-form"><label class="field">Share name<input name="name" maxlength="32" required pattern="[A-Za-z][A-Za-z0-9 _-]{0,31}" placeholder="e.g. Family Photos"></label><label class="field">Storage location<select name="volume" required>${volumes.map(v=>`<option value="${esc(v.path)}">${esc(v.label)}</option>`).join('')}</select></label><h3>User access</h3><p class="small">No Access is the default. Choose Read Only or Read & Write for each user.</p>${users.map(u=>`<label class="field">${esc(u.name)}<select data-share-user="${esc(u.name)}"><option value="none">No Access</option><option value="ro">Read Only</option><option value="rw">Read & Write</option></select></label>`).join('')}<label class="field">Administrator password<input name="admin_password" type="password" required autocomplete="current-password"></label><p class="hint">Permissions are applied to both SMB access and the underlying folder using POSIX ACLs. Share creation is not destructive.</p><div id="ns-message" role="status"></div><div class="modal-actions"><button class="btn outline" type="button" id="ns-cancel">Cancel</button><button class="btn" type="submit" id="ns-submit" ${!users.length||!volumes.length?'disabled':''}>Create share</button></div></form></div></section>`;
 document.body.appendChild(overlay);const close=()=>overlay.remove();overlay.querySelector('#ns-close').onclick=close;overlay.querySelector('#ns-cancel').onclick=close;
 overlay.querySelector('#ns-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),msg=overlay.querySelector('#ns-message'),btn=overlay.querySelector('#ns-submit'),access={};overlay.querySelectorAll('[data-share-user]').forEach(sel=>{if(sel.value!=='none')access[sel.dataset.shareUser]=sel.value});if(!Object.keys(access).length){msg.textContent='Assign access to at least one user.';return}btn.disabled=true;msg.textContent='Creating share…';try{await post('/api/nas-shares',{name:f.get('name'),volume:f.get('volume'),access,admin_password:f.get('admin_password')});const j=await (await fetch('/api/state',{cache:'no-store'})).json();info=j.hardware||info;close();render()}catch(err){msg.textContent=err.message;btn.disabled=false}};
 overlay.querySelector('[name=name]').focus();
}
const FS_GUIDE={ext4:['Recommended for most users','Simple, reliable Linux filesystem. A good default for general NAS storage.'],xfs:['Large files and media','Well suited to large files and sustained throughput; shrinking is not supported.'],btrfs:['Snapshots and data integrity','Checksums and snapshots; more advanced maintenance and memory requirements.']};
function openDiskWizard(index){
 const d=disks()[index];if(!d)return;
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 const vs=d.volumes||[],supported=vs.filter(v=>['ext4','xfs','btrfs'].includes(v.fs)&&v.uuid&&!v.read_only);
 const hasFilesystem=vs.some(v=>!!v.fs)||!!d.fs;
 const options=[
  {title:'Wipe Disk',description:'Erase all data and partition information from a disk. Any existing data on the disk will be lost.',disabled:true,reason:'Unavailable until destructive-operation protection is implemented.'},
  {title:hasFilesystem?'Reformat Disk':'Format Disk',description:hasFilesystem?'Prepare the drive with a new filesystem ready to be mounted. Warning: all existing data will be lost.':'Prepare the drive with a filesystem ready to be mounted. Formatting erases any data on the selected device.',disabled:true,reason:'Unavailable until formatting safety checks are implemented.'},
  {title:'Mount Disk',description:'Make the disk ready for NAS storage. Existing supported filesystems can be adopted without erasing data.',disabled:false}
 ];
 overlay.innerHTML=`<section class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="Manage disk" tabindex="-1"><div class="modal-heading"><h2>Manage Disk</h2><button class="icon-btn" id="disk-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><p><strong>${esc(d.model||d.name)}</strong> · ${size(d.size)} · ${esc(d.path)}</p>${options.map((o,i)=>`<div class="disk-management-action"><div><strong>${esc(o.title)}</strong><p class="small">${esc(o.description)}</p>${o.disabled?`<p class="small">${esc(o.reason)}</p>`:''}</div><button class="btn ${i===0?'outline':''}" ${o.disabled?'disabled title="Not yet available"':`id="disk-mount"`} type="button">${esc(o.title)}</button></div>`).join('')}<div id="disk-mount-options" class="hidden"><h3>Existing filesystems</h3>${supported.length?supported.map(v=>`<div class="storage-volume"><strong>${esc(v.fs.toUpperCase())}</strong> · ${esc(v.name)}<p class="small">${v.mounts.length?'Mounted at '+esc(v.mounts.join(', ')):'Not mounted'} · ${v.persistent?'Persistent':'Not configured for startup'}</p>${!v.persistent||!v.mounts.length?`<button class="btn outline" data-adopt="${esc(v.path)}">Adopt without formatting</button>`:'<p class="hint">Ready for NAS shares.</p>'}</div>`).join(''):'<p class="hint">No supported existing filesystem with a UUID was found. Formatting is not yet available.</p>'}</div><div id="disk-message" role="status"></div></div><div class="modal-actions"><button class="btn outline" id="disk-cancel">Close</button></div></section>`;
 document.body.appendChild(overlay);const close=()=>{document.removeEventListener('keydown',onKey);overlay.remove()};const onKey=e=>{if(e.key==='Escape')close()};document.addEventListener('keydown',onKey);overlay.querySelector('#disk-close').onclick=close;overlay.querySelector('#disk-cancel').onclick=close;overlay.onclick=e=>{if(e.target===overlay)close()};
 overlay.querySelector('#disk-mount').onclick=()=>overlay.querySelector('#disk-mount-options').classList.toggle('hidden');
 overlay.querySelectorAll('[data-adopt]').forEach(btn=>btn.onclick=async()=>{const device=btn.dataset.adopt;const password=await fileTextDialog({title:'Authorise storage adoption',label:'Administrator password',description:'PiNAS will preserve existing files and configure a UUID-based mount. The device will not be formatted.',confirmLabel:'Configure storage',password:true});if(password===null)return;btn.disabled=true;const msg=overlay.querySelector('#disk-message');msg.textContent='Configuring storage…';try{const result=await post('/api/storage',{device,admin_password:password});msg.textContent='Storage mounted at '+result.mount;const j=await (await fetch('/api/state',{cache:'no-store'})).json();info=j.hardware||info;close();render()}catch(e){msg.textContent=e.message;btn.disabled=false}});
 overlay.querySelector('.storage-wizard').focus();
}

function openSettings(){
 const existing=document.getElementById('settings-overlay');if(existing)existing.remove();
 const overlay=document.createElement('div');overlay.className='modal-overlay';overlay.id='settings-overlay';
 overlay.innerHTML=`<section class="card settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title" tabindex="-1">
 <div class="modal-heading"><h2 id="settings-title">PiNAS Settings</h2><button class="icon-btn" id="settings-close" aria-label="Close settings">${CANCEL_ICON}</button></div>
 <div class="settings-scroll">
 <h3>Device</h3><p class="small">Network name: <strong>${esc(info.hostname||'—')}</strong> · Local address: ${esc(info.hostname||'pinas')}.local (when mDNS is available)</p><h3>Appearance</h3>
 <label class="field">Font Size<select id="font"><option value="10">S — 10px</option><option value="12">M — 12px</option><option value="14">L — 14px</option><option value="16">XL — 16px</option></select></label>
 <label class="field">Theme<select id="theme"><option value="dark">Dark</option><option value="light">Light</option><option value="dark-cb">Dark (Colour blind)</option><option value="light-cb">Light (Colour blind)</option></select></label>
 <label class="field">Accent colour<input type="color" id="accent"></label>
 <h3>Device storage</h3><div class="card" id="device-storage" style="padding:14px"><div class="disk-heading"><strong>PiNAS system storage</strong><span class="small" id="system-usage">—</span></div><div class="bar"><i id="system-storage-bar" style="width:0%"></i></div><p class="small">Reserved for the operating system, updates, settings and optional applications. Not available for NAS shares.</p></div>
 <h3>CPU monitoring</h3>
 <label class="field">Sampling interval<select id="cpu_interval"><option value="2">2 seconds</option><option value="5">5 seconds</option><option value="10">10 seconds</option></select></label>
 <label class="field">CPU history<select id="cpu_history"><option value="10">10 minutes</option><option value="15">15 minutes</option><option value="30">30 minutes</option><option value="60">60 minutes</option></select></label>
 <h3>Security</h3><p class="small">HTTPS is enabled by default. The browser may require you to trust the locally generated certificate.</p><label class="field">Session idle timeout<select id="session_timeout"><option value="5">5 minutes</option><option value="10">10 minutes</option><option value="15">15 minutes</option><option value="30">30 minutes</option><option value="60">60 minutes</option></select></label>
 <h3>Login screen</h3><label class="field">Background image (JPEG, PNG or WebP, max 2 MB)<input id="background" type="file" accept="image/jpeg,image/png,image/webp"></label>
 <button class="btn outline" id="clear">Remove background</button>
 <h3>Update PiNAS</h3><label class="field">Select update file<input type="file" id="update-file" accept=".pinas,.zip"></label>
 <p class="small">Firmware updates will require signed packages and compatibility verification. Update installation is not yet enabled. For safety, selected files are not executed or installed in this prototype.</p>
 <div id="settings-message" role="status"></div></div>
 <div class="modal-actions"><button class="btn outline" id="settings-cancel">Cancel</button><button class="btn" id="save">Save settings</button></div></section>`;
 document.body.appendChild(overlay);
 const close=()=>{document.removeEventListener('keydown',onEscape);overlay.remove()},field=id=>overlay.querySelector('#'+id),msg=field('settings-message');
 field('settings-close').onclick=close;field('settings-cancel').onclick=close;
 overlay.onclick=e=>{if(e.target===overlay)close()};
 const onEscape=e=>{if(e.key==='Escape')close()};
 document.addEventListener('keydown',onEscape);
 const system=info.system_storage||{};field('system-usage').textContent=system.total?`${size(system.used)} used · ${size(system.free)} available of ${size(system.total)}`:'Unavailable';field('system-storage-bar').style.width=(system.percent||0)+'%';
 field('theme').value=['dark','light','dark-cb','light-cb'].includes(cfg.theme)?cfg.theme:'light';
 field('font').value=[10,12,14,16].includes(cfg.font)?cfg.font:12;
 field('accent').value=cfg.accent||'#c51a4a';
 field('cpu_interval').value=cfg.cpu_interval||5;field('cpu_history').value=cfg.cpu_history||10;field('session_timeout').value=cfg.session_timeout||5;
 field('save').onclick=async()=>{try{let j=await post('/api/settings',{theme:field('theme').value,accent:field('accent').value,font:Number(field('font').value),cpu_interval:Number(field('cpu_interval').value),cpu_history:Number(field('cpu_history').value),session_timeout:Number(field('session_timeout').value)});cfg=j.settings;apply();render();close()}catch(e){msg.textContent=e.message}};
 field('clear').onclick=async()=>{try{let j=await post('/api/background',{image:''});cfg=j.settings;apply();msg.textContent='Background removed'}catch(e){msg.textContent=e.message}};
 field('background').onchange=e=>{let f=e.target.files[0];if(!f)return;if(f.size>2*1024*1024){msg.textContent='Maximum image size is 2 MB';return}let reader=new FileReader();reader.onload=async()=>{try{let j=await post('/api/background',{image:reader.result});cfg=j.settings;apply();msg.textContent='Background updated'}catch(err){msg.textContent=err.message}};reader.readAsDataURL(f)};
 field('update-file').onchange=e=>{let f=e.target.files[0];msg.textContent=f?`Selected ${f.name}. Automatic update installation is not available in this prototype.`:''};
 overlay.querySelector('.settings-modal').focus();
}
const FILE_ICONS={folder:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',file:'<path d="M6 2h8l6 6v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z"/><path d="M14 2v6h6"/>',up:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="m9 14 3-3 3 3m-3-3v7"/>',plus:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M12 11v7m-3.5-3.5h7"/>',upload:'<path d="M6 2h8l6 6v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z"/><path d="M14 2v6h6m-8 11v-8m-3 3 3-3 3 3"/>',refresh:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M8 15a4 4 0 0 1 7-2m0-3v3h-3m4 3a4 4 0 0 1-7 2m0 3v-3h3"/>',gear:'<circle cx="12" cy="12" r="3"/><path d="M19 13.5a2 2 0 0 0 0-3l1-2-3-3-2 1a2 2 0 0 0-3-1l-1-2H9l-1 2a2 2 0 0 0-3 1l-2-1-2 3 1 2a2 2 0 0 0 0 3l-1 2 3 3 2-1a2 2 0 0 0 3 1l1 2h3l1-2a2 2 0 0 0 3-1l2 1 2-3Z"/>'};
const TOOLBAR_SVGS={"up":"<path d=\"M0 0h24v24H0z\" fill=\"none\"/><g fill=\"none\"><path fill=\"currentColor\" d=\"M22.23 15.94c0 1.18 0 1.77-.16 2.25a3 3 0 0 1-1.86 1.86c-.48.16-1.08.16-2.28.16H7.7c-2.83 0-4.25 0-5.13-.88s-.87-2.3-.87-5.12V7.47c0-.66 0-.98.05-1.26a3 3 0 0 1 2.4-2.4c.27-.05.6-.05 1.25-.05h1.07c1.09 0 1.63 0 2.14.19c.5.18.91.54 1.75 1.25l.4.34c.83.7 1.24 1.06 1.74 1.24c.5.19 1.05.19 2.14.19h1.6c2.82 0 4.24 0 5.11.88c.88.87.88 2.29.88 5.12z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M22.23 11.44c0-1.4 0-2.1-.23-2.66a3 3 0 0 0-1.62-1.62c-.55-.23-1.25-.23-2.65-.23H14.2c-1.04 0-1.56 0-2.04-.16l-.22-.09c-.47-.2-.85-.56-1.61-1.27c-.76-.7-1.15-1.06-1.61-1.26l-.22-.09c-.48-.17-1-.17-2.04-.17h-2.2A2.57 2.57 0 0 0 1.7 6.46v7.75c0 2.83 0 4.24.87 5.12c.88.88 2.3.88 5.13.88h5.95m5.84-5.31v6.2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"m22.55 17.04l-.94-.95c-1-1-1.5-1.5-2.12-1.5s-1.12.5-2.12 1.5l-.95.95\"/></g>","refresh":"<path d=\"M0 0h24v24H0z\" fill=\"none\"/><g fill=\"none\"><path fill=\"currentColor\" d=\"M14.47 20.18h.35a3 3 0 0 1 1.3.38l.29.18l.4.24a3 3 0 0 0 1.7.34l.45-.07l.4-.07l.27-.05a3 3 0 0 0 1.28-.64l.21-.19c.16-.14.23-.2.3-.28a3 3 0 0 0 .81-1.86V12.9c0-2.82 0-4.24-.87-5.12c-.88-.88-2.3-.88-5.12-.88h-1.6c-1.1 0-1.64 0-2.14-.18c-.5-.19-.92-.54-1.75-1.25l-.4-.34c-.84-.71-1.26-1.06-1.76-1.25S7.54 3.7 6.45 3.7H5.4c-.67 0-1 0-1.28.05a3 3 0 0 0-2.39 2.39c-.05.27-.05.6-.05 1.27v6.76c0 2.83 0 4.24.88 5.12s2.3.88 5.12.88z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M22.24 9.89a3 3 0 0 0-3-3h-5.05c-1.04 0-1.56 0-2.05-.17l-.2-.08c-.48-.2-.86-.56-1.62-1.27S9.17 4.29 8.7 4.09L8.5 4c-.48-.16-1-.16-2.05-.16h-2.2A2.57 2.57 0 0 0 1.67 6.4v7.77c0 2.83 0 4.24.88 5.12s2.3.88 5.12.88h2.79\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M21.77 15.87c-.93-1.32-2.05-2.22-3.64-2.22q-2.38 0-3.48 2.06m.2 3.49c.93 1.3 2.04 2.22 3.63 2.22q2.38 0 3.48-2.07\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"m22.28 13.48l-.04.82c-.06.94-.08 1.42-.4 1.7c-.3.27-.77.24-1.72.18l-.82-.04m-4.99 5.3l.05-.68c.06-.94.09-1.41.4-1.69c.31-.27.78-.24 1.72-.18l.68.05\"/></g>","plus":"<path d=\"M0 0h24v24H0z\" fill=\"none\"/><g fill=\"none\"><path fill=\"currentColor\" d=\"M22.24 14.2c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88H7.76c-2.83 0-4.24 0-5.12-.88s-.88-2.3-.88-5.12V7.5c0-.65 0-.98.05-1.25a3 3 0 0 1 2.4-2.4c.27-.05.6-.05 1.25-.05H6.5c1.1 0 1.64 0 2.14.18c.5.19.92.54 1.75 1.25l.39.33c.83.71 1.25 1.06 1.75 1.25s1.05.18 2.14.18h1.56c2.83 0 4.24 0 5.12.88s.88 2.3.88 5.12z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M22.24 14.2c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88H7.76c-2.83 0-4.24 0-5.12-.88s-.88-2.3-.88-5.12V6.5a2.56 2.56 0 0 1 2.56-2.56H6.5c1.04 0 1.55 0 2.03.16l.23.1c.46.2.84.55 1.6 1.25s1.14 1.06 1.6 1.26l.23.1c.47.16 1 .16 2.03.16h2.01c2.83 0 4.24 0 5.12.88s.88 2.3.88 5.12zM8.7 13.58h6.6M12 16.89v-6.6\"/></g>","upload":"<path d=\"M0 0h24v24H0z\" fill=\"none\" /><g fill=\"none\"><path fill=\"currentColor\" d=\"M7.72 22.24c-1.89 0-2.83 0-3.42-.59c-.58-.58-.58-1.52-.58-3.41V5.78c0-1.87 0-2.8.57-3.38c.58-.59 1.52-.6 3.38-.62l2.24-.02c1.3-.02 1.96-.02 2.44.27a2 2 0 0 1 .69.67c.29.48.29 1.14.29 2.44s0 1.95.29 2.42q.25.42.67.68c.48.29 1.13.29 2.42.29c1.3 0 1.95 0 2.43.29q.41.26.67.67c.3.48.3 1.13.3 2.43v6.32c0 1.89 0 2.83-.6 3.41c-.58.59-1.52.59-3.4.59z\" opacity=\".2\" /><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M20.1 12.82v-2.56c0-1.25 0-1.87-.24-2.43s-.68-1-1.57-1.87L17.1 4.81l-1.24-1.23c-.87-.87-1.3-1.3-1.85-1.53s-1.17-.23-2.39-.23h-1.9c-2.83 0-4.25 0-5.13.88S3.72 5 3.72 7.82v8.42c0 2.83 0 4.24.87 5.12c.88.88 2.3.88 5.13.88h2.94\" /><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M13.13 2.34v2.45c0 1.9 0 2.84.58 3.42s1.53.59 3.42.59h2.46m-1.29 7.94v6.2m3.07-4.07l-.94-.94c-1-1-1.5-1.5-2.13-1.5s-1.12.5-2.12 1.5l-.95.94\" /></g>"};
const ACTION_SVGS={"rename":"<path d=\"M7.67 22.24c-1.89 0-2.83 0-3.42-.59s-.58-1.53-.58-3.41V5.74c0-1.87 0-2.8.58-3.38c.57-.59 1.5-.6 3.38-.62l2.24-.02c1.31-.01 1.97-.02 2.45.27q.42.25.68.67c.3.48.3 1.14.3 2.45c0 1.3 0 1.95.29 2.43q.25.41.67.67c.48.3 1.13.3 2.43.3s1.95 0 2.43.28q.41.26.67.67c.3.48.3 1.13.3 2.43v2.96l-4.85 4.46l-1.14 2.93z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M20.08 11.28v-1.05c0-1.25 0-1.87-.23-2.43s-.69-1-1.58-1.87l-1.19-1.15l-1.24-1.24c-.87-.87-1.3-1.3-1.85-1.53s-1.17-.23-2.39-.23H9.67c-2.83 0-4.24 0-5.12.88s-.88 2.3-.88 5.12v8.46c0 2.82 0 4.24.88 5.12s2.29.88 5.12.88h.48\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M13.1 2.3v2.47c0 1.88 0 2.83.58 3.41s1.53.59 3.41.59h2.48\"/><rect width=\"2.36\" height=\"2.64\" fill=\"currentColor\" opacity=\".2\" rx=\"1\" transform=\"rotate(135 6.603 13.18)scale(-1 1)\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"m20.59 17.84l-1.78-1.77m-3.66 6.53c.55-.12.83-.18 1.07-.3l.03-.02c.24-.14.44-.33.84-.72l4.54-4.46c.31-.3.47-.46.54-.63a1 1 0 0 0 0-.81c-.07-.18-.22-.33-.53-.64s-.47-.47-.64-.54a1 1 0 0 0-.8 0c-.18.07-.33.23-.64.54l-4.51 4.5c-.4.38-.6.58-.73.82l-.02.05c-.13.24-.19.5-.3 1.05c-.15.65-.22.97-.05 1.16l.04.04c.19.17.51.1 1.16-.04\"/>","copy":"<path fill=\"currentColor\" d=\"M13.09 11.27c-.1-.48-.16-.72-.26-.94a2 2 0 0 0-.25-.38a4 4 0 0 0-.74-.64l-.08-.06c-.62-.47-.94-.71-1.13-1.03l-.16-.32c-.13-.35-.13-.74-.13-1.53V5.5c0-1.1 0-1.66.2-2.09a2 2 0 0 1 .88-.87c.42-.22.98-.23 2.08-.24h1.3a2 2 0 0 1 1.93 2.1v.18a2 2 0 0 0 1.92 1.92h.78a2 2 0 0 1 1.8 1.8v1.92c0 1.64 0 2.46-.45 3.01a2 2 0 0 1-.31.31c-.56.44-1.38.43-3.02.4l-1.13-.02c-1.03-.01-1.54-.02-1.96-.23a2 2 0 0 1-.66-.54c-.29-.37-.4-.87-.61-1.88\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M19 17.68v.29c0 1.63 0 2.44-.45 2.99a2 2 0 0 1-.3.3c-.54.44-1.36.44-2.98.44\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M21 18.35c-.88-.88-1.32-1.33-1.86-1.38h-.28c-.54.05-.98.5-1.86 1.38M8.6 7.37v.25c-.01 1.89-.01 2.83.57 3.42c.59.58 1.53.58 3.42.58h.26m3.52-9.08v.25c0 1.89 0 2.83.58 3.42c.59.59 1.53.59 3.42.59h.26\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M6.77 18.76c-1.89 0-2.83 0-3.42-.59c-.58-.58-.58-1.53-.58-3.41v-3.4c0-1.88 0-2.82.58-3.4c.59-.6 1.53-.6 3.42-.6h1.46c.72 0 1.08 0 1.4.13c.34.12.61.35 1.17.8l.88.74l.52.43c.72.59 1.08.89 1.27 1.3c.2.4.2.87.2 1.8v2.2c0 1.88 0 2.83-.6 3.41c-.58.59-1.52.59-3.4.59z\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M13.86 14h3.37c1.89 0 2.83 0 3.42-.58c.58-.59.58-1.53.58-3.42V7.57c0-.91 0-1.37-.19-1.78c-.18-.4-.54-.7-1.24-1.28l-.56-.47l-.87-.75a4 4 0 0 0-1.17-.84c-.33-.12-.7-.12-1.43-.12h-1.43c-1.89 0-2.83 0-3.42.59c-.58.58-.58 1.52-.58 3.41v1.42\"/>","move":"<path fill=\"currentColor\" d=\"M7.8 22.23c-1.9 0-2.83 0-3.42-.59c-.59-.58-.59-1.53-.59-3.41V5.73c0-1.86 0-2.8.58-3.38s1.51-.6 3.38-.61L10 1.7c1.3-.01 1.97-.02 2.45.27q.42.26.68.67c.3.48.3 1.14.3 2.45c0 1.3 0 1.95.28 2.43q.26.42.67.67c.48.3 1.13.3 2.43.3s1.96 0 2.44.29q.41.26.66.66c.3.48.3 1.13.3 2.44v6.34c0 1.88 0 2.83-.59 3.41s-1.53.59-3.41.59z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M3.8 7.78v8.45c0 2.83 0 4.24.87 5.12c.88.88 2.3.88 5.12.88h4.42c2.82 0 4.24 0 5.12-.88s.88-2.3.88-5.12v-6c0-1.25 0-1.88-.24-2.44s-.68-1-1.58-1.86l-1.18-1.16l-1.25-1.24c-.86-.87-1.3-1.3-1.85-1.53s-1.16-.22-2.38-.22H9.79c-2.82 0-4.24 0-5.12.87c-.88.88-.88 2.3-.88 5.13\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M13.22 2.3v2.46c0 1.89 0 2.83.58 3.42c.59.58 1.53.58 3.42.58h2.47m-6.23 9.73l.32-.32c1.33-1.34 2-2 2-2.83s-.66-1.5-2-2.83l-.32-.33m-5.61 3.15h7.8\"/>","delete":"<path fill=\"currentColor\" d=\"M7.85 22.2c-1.89 0-2.83 0-3.42-.58c-.58-.59-.58-1.53-.58-3.41V5.84c0-1.87 0-2.8.57-3.39c.58-.58 1.52-.59 3.38-.6l2.2-.03c1.3-.01 1.95-.02 2.43.26a2 2 0 0 1 .7.7c.28.47.28 1.12.28 2.4c0 1.29 0 1.93.29 2.4a2 2 0 0 0 .69.7c.47.28 1.11.28 2.4.28s1.92 0 2.39.28a2 2 0 0 1 .7.7c.27.47.27 1.1.27 2.39v6.28c0 1.88 0 2.82-.58 3.41c-.59.59-1.53.59-3.42.59z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M3.85 7.88v8.33c0 2.82 0 4.24.87 5.12c.88.88 2.3.88 5.13.88h4.3c2.83 0 4.25 0 5.13-.88s.87-2.3.87-5.12v-5.92c0-1.25 0-1.87-.23-2.43s-.68-1-1.58-1.87l-1.16-1.13l-1.23-1.22c-.87-.87-1.3-1.3-1.85-1.53s-1.16-.23-2.39-.23H9.85c-2.83 0-4.25 0-5.13.88s-.87 2.3-.87 5.12\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M13.21 2.4v2.42c0 1.89 0 2.83.58 3.42c.6.59 1.53.59 3.42.59h2.43M8.5 15.3h7\"/>"};
ACTION_SVGS.download="<path fill=\"currentColor\" d=\"M7.72 22.24c-1.89 0-2.83 0-3.42-.59c-.58-.58-.58-1.52-.58-3.41V5.78c0-1.87 0-2.8.57-3.38c.58-.59 1.52-.6 3.38-.62l2.24-.02c1.3-.02 1.96-.02 2.44.27a2 2 0 0 1 .69.67c.29.48.29 1.14.29 2.44s0 1.95.29 2.42q.25.42.67.68c.48.29 1.13.29 2.42.29c1.3 0 1.95 0 2.43.29q.41.26.67.67c.3.48.3 1.13.3 2.43v6.32c0 1.89 0 2.83-.6 3.41c-.58.59-1.52.59-3.4.59z\" opacity=\".2\" /><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M20.1 12.66v-2.4c0-1.25 0-1.87-.24-2.43s-.68-1-1.57-1.87L17.1 4.81l-1.24-1.23c-.87-.87-1.3-1.3-1.85-1.53s-1.17-.23-2.39-.23h-1.9c-2.83 0-4.25 0-5.13.88S3.72 5 3.72 7.82v8.42c0 2.83 0 4.24.87 5.12c.88.88 2.3.88 5.13.88h2.2\" /><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M13.13 2.34v2.45c0 1.9 0 2.84.58 3.42s1.53.59 3.42.59h2.46M18.3 22.4v-6.2m3.07 4.07l-.94.94c-1 1-1.5 1.5-2.13 1.5s-1.12-.5-2.12-1.5l-.95-.94\" />";
const actionIcon=(name)=>`<svg viewBox="0 0 24 24" width="24" height="24" fill="none" aria-hidden="true">${ACTION_SVGS[name]}</svg>`;
const PINAS_BRAND_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="27" height="27" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><g fill="none"><rect width="6.11" height="20.43" x="1.78" y="9" fill="currentColor" opacity=".2" rx="2" transform="rotate(-90 1.78 9)"/><rect width="6.11" height="20.43" x="1.78" y="21.23" fill="currentColor" opacity=".2" rx="2" transform="rotate(-90 1.78 21.23)"/><rect width="6.11" height="20.43" x="1.78" y="9" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" rx="2" transform="rotate(-90 1.78 9)"/><rect width="6.11" height="20.43" x="1.78" y="15.11" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" rx="2" transform="rotate(-90 1.78 15.11)"/><rect width="6.11" height="20.43" x="1.78" y="21.23" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" rx="2" transform="rotate(-90 1.78 21.23)"/><path fill="currentColor" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5.83 5.94a.41.41 0 1 1-.83 0a.41.41 0 0 1 .83 0m0 6.12a.41.41 0 1 1-.83 0a.41.41 0 0 1 .83 0m0 6.11a.41.41 0 1 1-.83 0a.41.41 0 0 1 .83 0m4.1-12.23a.41.41 0 1 1-.82 0a.41.41 0 0 1 .82 0m0 6.12a.41.41 0 1 1-.82 0a.41.41 0 0 1 .82 0m0 6.11a.41.41 0 1 1-.82 0a.41.41 0 0 1 .82 0"/></g></svg>`;
const LOGOFF_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none" /><g fill="none"><path fill="currentColor" d="M15.47 7.99a5.4 5.4 0 1 1-10.79 0a5.4 5.4 0 0 1 10.8 0" opacity=".2" /><path fill="currentColor" d="M18.38 21.84H1.78a8.4 8.4 0 0 1 8.3-8.46c4.58 0 8.3 3.79 8.3 8.46" opacity=".2" /><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.47 7.99a5.4 5.4 0 0 1-5.4 5.4a5.4 5.4 0 1 1 5.4-5.4" /><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M1.78 21.68a8.3 8.3 0 0 1 11.11-7.8m3.49 1.58h5.33m-.15 5.14h-5.33m4.62-7.1l.55.55c.67.66 1 1 1 1.41c0 .42-.33.75-1 1.42l-.55.55m-3.75 1.19l-.55.55c-.67.67-1 1-1 1.42s.33.75 1 1.41l.55.56" /></g></svg>`;
const CANCEL_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><path fill="currentColor" fill-rule="evenodd" d="M7.345 4.017a42.3 42.3 0 0 1 9.31 0c1.713.192 3.095 1.541 3.296 3.26a40.7 40.7 0 0 1 0 9.446c-.201 1.719-1.583 3.068-3.296 3.26a42.3 42.3 0 0 1-9.31 0c-1.713-.192-3.095-1.541-3.296-3.26a40.7 40.7 0 0 1 0-9.445a3.734 3.734 0 0 1 3.295-3.26M8.47 8.47a.75.75 0 0 1 1.06 0L12 10.94l2.47-2.47a.75.75 0 1 1 1.06 1.06L13.06 12l2.47 2.47a.75.75 0 0 1-1.06 1.06L12 13.06l-2.47 2.47a.75.75 0 1 1-1.06-1.06L10.94 12L8.47 9.53a.75.75 0 0 1 0-1.06" clip-rule="evenodd"/></svg>`;
const DELETE_SHARE_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><g fill="none"><path fill="currentColor" d="M22.2 14.17c0 2.83 0 4.25-.87 5.12c-.88.88-2.3.88-5.12.88H7.79c-2.82 0-4.24 0-5.12-.88c-.88-.87-.88-2.29-.88-5.12V7.51c0-.63 0-.95.05-1.22a3 3 0 0 1 2.42-2.41c.26-.05.58-.05 1.22-.05h1.04c1.1 0 1.64 0 2.14.18c.5.19.92.54 1.75 1.25l.38.32c.83.7 1.25 1.06 1.75 1.25s1.04.18 2.14.18h1.53c2.82 0 4.24 0 5.12.88s.88 2.3.88 5.12z" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M22.2 14.17c0 2.83 0 4.25-.87 5.12c-.88.88-2.3.88-5.12.88H7.79c-2.82 0-4.24 0-5.12-.88c-.88-.87-.88-2.29-.88-5.12V6.51a2.56 2.56 0 0 1 2.56-2.55h2.18c1.03 0 1.54 0 2.01.16l.25.1c.46.2.83.55 1.58 1.25s1.13 1.05 1.59 1.25l.24.1c.48.16 1 .16 2.02.16h1.99c2.82 0 4.24 0 5.12.88c.88.87.88 2.29.88 5.12zm-13.5-.68h6.6"/></g></svg>`;
const CREATE_SHARE_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><g fill="none"><path fill="currentColor" d="M22.24 14.2c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88H7.76c-2.83 0-4.24 0-5.12-.88s-.88-2.3-.88-5.12V7.5c0-.65 0-.98.05-1.25a3 3 0 0 1 2.4-2.4c.27-.05.6-.05 1.25-.05H6.5c1.1 0 1.64 0 2.14.18c.5.19.92.54 1.75 1.25l.39.33c.83.71 1.25 1.06 1.75 1.25s1.05.18 2.14.18h1.56c2.83 0 4.24 0 5.12.88s.88 2.3.88 5.12z" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M22.24 14.2c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88H7.76c-2.83 0-4.24 0-5.12-.88s-.88-2.3-.88-5.12V6.5a2.56 2.56 0 0 1 2.56-2.56H6.5c1.04 0 1.55 0 2.03.16l.23.1c.46.2.84.55 1.6 1.25s1.14 1.06 1.6 1.26l.23.1c.47.16 1 .16 2.03.16h2.01c2.83 0 4.24 0 5.12.88s.88 2.3.88 5.12zM8.7 13.58h6.6M12 16.89v-6.6"/></g></svg>`;
const EDIT_SHARE_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 20h16M6 16.5l.4-3.3L16.7 2.9a2.2 2.2 0 0 1 3.1 3.1L9.5 16.3 6 16.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const ADD_USER_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><g fill="none"><path fill="currentColor" d="M15.47 7.99a5.4 5.4 0 1 1-10.79 0a5.4 5.4 0 0 1 10.8 0" opacity=".2"/><path fill="currentColor" d="M18.38 21.84H1.78a8.4 8.4 0 0 1 8.3-8.46c4.58 0 8.3 3.79 8.3 8.46" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.47 7.99a5.4 5.4 0 0 1-5.4 5.4a5.4 5.4 0 1 1 5.4-5.4m-.45 10.71h7.16m-3.58 3.58v-7.16"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M1.78 21.68a8.3 8.3 0 0 1 12.32-7.26"/></g></svg>`;
const EDIT_USER_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><g fill="none"><path fill="currentColor" d="M15.47 7.99a5.4 5.4 0 1 1-10.79 0a5.4 5.4 0 0 1 10.8 0" opacity=".2"/><path fill="currentColor" d="M14.09 21.84H1.77a8.4 8.4 0 0 1 8.3-8.46c2.9 0 5.44 1.5 6.93 3.8c-1.59 1.38-3.2 2.89-2.91 4.66" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.47 7.99a5.4 5.4 0 0 1-5.4 5.4a5.4 5.4 0 1 1 5.4-5.4"/><rect width="2.4" height="2.69" fill="currentColor" opacity=".2" rx="1" transform="rotate(-45 31.28 -16)scale(1 -1)"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="m20.47 17.45l-1.81-1.81m-3.72 6.65a4 4 0 0 0 1.1-.32c.25-.13.46-.34.87-.74l4.62-4.53c.33-.33.5-.5.57-.68a1 1 0 0 0 0-.77c-.07-.19-.23-.35-.56-.68a3 3 0 0 0-.67-.56a1 1 0 0 0-.77 0c-.19.07-.35.23-.67.56l-4.6 4.58a4 4 0 0 0-.76.87c-.13.25-.2.53-.31 1.09c-.15.67-.23 1-.04 1.2l.01.01c.2.19.53.11 1.2-.03M1.78 21.8a8.3 8.3 0 0 1 12.32-7.25"/></g></svg>`;
const SETTINGS_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none" /><g fill="none"><path fill="currentColor" fill-rule="evenodd" d="M1.48 12.67c0 .94 0 1.41.3 1.7c.29.3.76.3 1.7.3h1.45c.27 0 .4 0 .52.03a1 1 0 0 1 .47.27c.09.09.16.2.29.43s.2.35.23.47a1 1 0 0 1 0 .54c-.03.12-.1.24-.23.47l-.67 1.15c-.47.82-.7 1.23-.6 1.63c.11.4.52.63 1.34 1.1l.95.55c.81.47 1.22.7 1.62.6s.64-.51 1.1-1.33l.41-.7c.24-.4.35-.6.53-.73l.16-.1c.2-.09.43-.09.9-.09c.45 0 .69 0 .88.1l.17.09c.17.12.29.32.52.72l.4.7c.48.83.71 1.23 1.11 1.34c.4.1.81-.13 1.63-.6l.95-.55c.82-.47 1.22-.7 1.33-1.1c.1-.4-.13-.81-.6-1.63l-.41-.71c-.28-.5-.42-.74-.43-1q0-.15.04-.3c.07-.24.27-.44.67-.84c.22-.22.33-.33.46-.4l.17-.07c.15-.04.3-.04.62-.04h.82c.95 0 1.42 0 1.71-.3c.3-.29.3-.76.3-1.7v-1.1c0-.94 0-1.41-.3-1.7s-.76-.3-1.7-.3h-.83c-.32 0-.47 0-.62-.04l-.17-.08a2 2 0 0 1-.46-.4c-.4-.4-.6-.6-.67-.84a1 1 0 0 1-.04-.3c0-.26.15-.5.43-.99l.41-.71c.47-.82.7-1.23.6-1.63s-.51-.64-1.33-1.1l-.95-.55c-.82-.48-1.23-.71-1.63-.6s-.63.51-1.1 1.33l-.41.7c-.23.4-.35.6-.52.73l-.17.1c-.2.08-.43.08-.89.08s-.7 0-.89-.09l-.16-.1c-.18-.12-.3-.32-.53-.72l-.4-.7c-.47-.82-.71-1.23-1.11-1.33s-.8.12-1.62.6l-.95.54c-.82.47-1.23.71-1.34 1.11c-.1.4.13.8.6 1.63l.67 1.15c.13.23.2.34.23.46a1 1 0 0 1 0 .55c-.03.12-.1.23-.23.46s-.2.35-.29.44a1 1 0 0 1-.47.27c-.12.03-.25.03-.52.03H3.48c-.94 0-1.41 0-1.7.3c-.3.29-.3.76-.3 1.7zm7.8-.55a2.87 2.87 0 1 0 5.75 0a2.87 2.87 0 0 0-5.75 0" clip-rule="evenodd" opacity=".2" /><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12.15 9.24a2.87 2.87 0 0 0-2.87 2.88a2.87 2.87 0 1 0 2.87-2.88" /><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4.03 14.67h.9a1.47 1.47 0 0 1 1.28 2.2l-.4.69a6 6 0 0 0-.44.86a2 2 0 0 0 .56 2.09c.16.14.38.27.82.53l.08.05c.37.2.55.31.72.37a2 2 0 0 0 2.2-.6c.12-.13.22-.3.43-.67l.18-.32a1.82 1.82 0 0 1 3.16 0l.18.32c.21.36.32.54.43.68a2 2 0 0 0 2.2.59c.18-.06.36-.16.72-.37l.24-.14c.3-.17.44-.26.56-.35a2 2 0 0 0 .62-2.31a5 5 0 0 0-.31-.58l-.23-.4a1.77 1.77 0 0 1 1.53-2.64h.3c.49 0 .73 0 .93-.04a2 2 0 0 0 1.55-1.56c.04-.2.04-.44.04-.92v-.06c0-.48 0-.72-.04-.92A2 2 0 0 0 20.7 9.6c-.2-.04-.44-.04-.92-.04h-.31a1.77 1.77 0 0 1-1.53-2.65l.23-.4c.17-.3.25-.44.3-.57a2 2 0 0 0-.61-2.32a5 5 0 0 0-.56-.34l-.24-.14c-.36-.2-.54-.31-.71-.37a2 2 0 0 0-2.2.59a5 5 0 0 0-.44.68l-.18.31a1.82 1.82 0 0 1-3.16 0l-.18-.31a5 5 0 0 0-.43-.68a2 2 0 0 0-2.2-.6a7 7 0 0 0-.72.38l-.08.05c-.44.25-.66.38-.82.53a2 2 0 0 0-.56 2.08c.07.2.2.43.45.87l.39.68a1.48 1.48 0 0 1-1.28 2.21h-.9c-.51 0-.77 0-.98.05a2 2 0 0 0-1.52 1.52c-.05.21-.05.47-.05.98c0 .5 0 .76.05.97a2 2 0 0 0 1.52 1.53c.21.05.47.05.98.05" /></g></svg>`;

const fileIcon=(name,size=22)=>`<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" ${TOOLBAR_SVGS[name]?'':'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'} aria-hidden="true">${TOOLBAR_SVGS[name]||FILE_ICONS[name]}</svg>`;
function userAvatar(){return cfg.profile_avatar||''}
function openUserSettings(){const overlay=document.createElement('div');overlay.className='modal-overlay';overlay.innerHTML=`<section class="card settings-modal" role="dialog" aria-modal="true" aria-labelledby="user-settings-title" tabindex="-1"><div class="modal-heading"><h2 id="user-settings-title">My Settings</h2><button class="icon-btn" id="user-settings-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><p>These preferences belong to your NAS account.</p><label class="field">Profile picture<img id="user-avatar-preview" class="profile-preview" alt="Profile picture" ${userAvatar()?`src="${userAvatar()}"`:''}><input type="file" id="user-avatar-input" accept="image/png,image/jpeg,image/webp"><span class="small">PNG, JPEG or WebP, maximum 256 KB.</span></label><button class="btn outline" id="user-avatar-remove" type="button">Remove picture</button><label class="field">Theme<select id="user-theme"><option value="light">Light</option><option value="dark">Dark</option><option value="light-cb">Light (Colour blind)</option><option value="dark-cb">Dark (Colour blind)</option></select></label><label class="field">Font size<select id="user-font"><option value="10">Small (10px)</option><option value="12">Medium (12px)</option><option value="14">Large (14px)</option><option value="16">Extra large (16px)</option></select></label><div id="user-settings-message" role="status"></div></div><div class="modal-actions"><button class="btn outline" id="user-settings-cancel">Cancel</button><button class="btn" id="user-settings-save">Save preferences</button></div></section>`;document.body.append(overlay);const get=id=>overlay.querySelector('#'+id),close=()=>overlay.remove();let avatar=userAvatar();get('user-theme').value=cfg.theme||'light';get('user-font').value=String(cfg.font||12);get('user-settings-close').onclick=close;get('user-settings-cancel').onclick=close;overlay.addEventListener('click',e=>{if(e.target===overlay)close()});get('user-avatar-remove').onclick=()=>{avatar='';get('user-avatar-preview').removeAttribute('src')};get('user-avatar-input').onchange=e=>{const file=e.target.files[0];if(!file)return;if(file.size>256*1024||!['image/png','image/jpeg','image/webp'].includes(file.type)){get('user-settings-message').textContent='Choose a PNG, JPEG or WebP under 256 KB.';return}const reader=new FileReader();reader.onload=()=>{avatar=reader.result;get('user-avatar-preview').src=avatar};reader.readAsDataURL(file)};get('user-settings-save').onclick=async()=>{try{const result=await post('/api/user-preferences',{theme:get('user-theme').value,font:Number(get('user-font').value),avatar});cfg={...cfg,...result.preferences};apply();close();renderFiles()}catch(e){get('user-settings-message').textContent=e.message}};get('user-theme').focus()}
function fileTextDialog({title,label,initial='',description='',confirmLabel='Save',password=false}){return new Promise(resolve=>{const overlay=document.createElement('div');overlay.className='modal-overlay';overlay.innerHTML=`<section class="card settings-modal file-dialog" role="dialog" aria-modal="true" aria-labelledby="file-dialog-title" tabindex="-1"><div class="modal-heading"><h2 id="file-dialog-title">${esc(title)}</h2><button type="button" class="icon-btn" id="file-dialog-close" aria-label="Close">${CANCEL_ICON}</button></div><form id="file-dialog-form"><div class="settings-scroll">${description?`<p>${esc(description)}</p>`:''}<label class="field">${esc(label)}<input id="file-dialog-value" type="${password?'password':'text'}" required maxlength="255" autocomplete="off" value="${esc(initial)}"></label><p id="file-dialog-error" role="status" class="small"></p></div><div class="modal-actions"><button type="button" class="btn outline" id="file-dialog-cancel">Cancel</button><button type="submit" class="btn">${esc(confirmLabel)}</button></div></form></section>`;document.body.append(overlay);const input=overlay.querySelector('#file-dialog-value');let finished=false;const done=v=>{if(finished)return;finished=true;document.removeEventListener('keydown',key);overlay.remove();resolve(v)};const key=e=>{if(e.key==='Escape'){e.preventDefault();done(null)}};document.addEventListener('keydown',key);overlay.querySelector('#file-dialog-close').onclick=()=>done(null);overlay.querySelector('#file-dialog-cancel').onclick=()=>done(null);overlay.addEventListener('click',e=>{if(e.target===overlay)done(null)});overlay.querySelector('#file-dialog-form').onsubmit=e=>{e.preventDefault();const value=input.value.trim();if(!value){overlay.querySelector('#file-dialog-error').textContent='Please enter a name.';return}done(value)};input.focus();input.select()})}
async function renderFiles(){
 app.innerHTML=`<header><div class="brand"><span class="mark">${PINAS_BRAND_ICON}</span><div>PiNAS<small>MY FILES</small></div></div><div class="user-header">${userAvatar()?`<img class="user-avatar" src="${userAvatar()}" alt="">`:''}<span class="small">${esc(displayName)}</span><button class="icon-btn" id="file-settings" aria-label="My Settings" title="My Settings">${SETTINGS_ICON}</button><button class="icon-btn" id="file-logout" aria-label="Sign out" title="Sign out">${LOGOFF_ICON}<span class="sr-only">Sign out</span></button></div></header><main><div class="page-heading"><h1>My Files</h1><p>Browse and manage your permitted SMB shares.</p></div><div class="card"><div id="file-breadcrumb" class="small"></div><div class="file-toolbar"><button class="icon-btn" id="file-back" aria-label="Folder up" title="Folder up">${fileIcon('up',32)}</button><button class="icon-btn" id="file-new" aria-label="New folder" title="New folder">${fileIcon('plus',32)}</button><label class="icon-btn file-upload-control" aria-label="Upload files" title="Upload files">${fileIcon('upload',32)}<input id="file-upload" type="file" multiple aria-label="Upload files"></label><button class="icon-btn" id="file-refresh" aria-label="Refresh folder" title="Refresh folder">${fileIcon('refresh',32)}</button></div><div id="file-items"><p>Loading files…</p></div><p class="small" id="file-message" role="status"></p><div id="transfer-panel" hidden><div class="small" id="transfer-label"></div><div class="bar"><i id="transfer-bar" style="width:0"></i></div><button class="btn outline" id="transfer-cancel">Cancel transfer</button></div></div></main>`;
 document.getElementById('file-settings').onclick=openUserSettings;
 document.getElementById('file-logout').onclick=async()=>{await post('/api/logout',{});await init()};
 let currentShare='',currentPath='',shares=[],activeTransfer=null;
 const msg=document.getElementById('file-message'),items=document.getElementById('file-items');
 const panel=document.getElementById('transfer-panel'),bar=document.getElementById('transfer-bar'),label=document.getElementById('transfer-label');
 const call=(action,extra={})=>post('/api/files',{action,share:currentShare,path:currentPath,...extra});
 const joined=(a,b)=>[a,b].filter(Boolean).join('/');
 const readonly=()=>!currentShare||shares.find(x=>x.name===currentShare)?.read_only;
 const fmt=n=>{let i=0;while(n>=1024&&i<4){n/=1024;i++}return n.toFixed(i?1:0)+' '+['B','KB','MB','GB','TB'][i]};
 const progress=(done,total,filename,start)=>{panel.hidden=false;bar.style.width=(total?Math.min(100,100*done/total):0)+'%';const speed=done/Math.max(.2,(Date.now()-start)/1000);label.textContent=`${filename} · ${fmt(done)} / ${fmt(total)} · ${fmt(speed)}/s`+(speed&&done<total?` · ${Math.ceil((total-done)/speed)}s remaining`:'')};
 document.getElementById('transfer-cancel').onclick=()=>{if(activeTransfer)activeTransfer.cancelled=true};
 async function downloadFile(path,name,size){
   const transfer={cancelled:false};activeTransfer=transfer;const started=Date.now(),chunk=384*1024;
   try{const parts=[];let offset=0;do{if(transfer.cancelled)throw Error('Download cancelled');const r=await call('download_chunk',{path,offset,size:chunk});const binary=atob(r.content);const bytes=new Uint8Array(binary.length);for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);parts.push(bytes);offset+=bytes.length;progress(offset,r.total,name,started);if(!bytes.length||offset>=r.total)break}while(true);
     const blob=new Blob(parts,{type:'application/octet-stream'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
   }catch(e){msg.textContent=e.message}finally{panel.hidden=true;activeTransfer=null}
 }
 async function uploadFile(file,index,total){
   const transfer={cancelled:false};activeTransfer=transfer;let token=null,offset=0;const started=Date.now(),chunk=384*1024;
   try{const result=await call('upload_start',{name:file.name,size:file.size});token=result.token;
     while(offset<file.size){if(transfer.cancelled)throw Error('Upload cancelled');const bytes=new Uint8Array(await file.slice(offset,offset+chunk).arrayBuffer());let binary='';for(let j=0;j<bytes.length;j+=8192)binary+=String.fromCharCode(...bytes.subarray(j,j+8192));const r=await call('upload_chunk',{token,offset,content:btoa(binary)});offset=r.offset;progress(offset,file.size,`File ${index}/${total}: ${file.name}`,started)}
     if(transfer.cancelled)throw Error('Upload cancelled');await call('upload_finish',{token});token=null;msg.textContent=`Uploaded ${file.name}`;
   }catch(e){msg.textContent=e.message;if(token){try{await call('upload_cancel',{token})}catch(_){}}return false}
   finally{panel.hidden=true;activeTransfer=null}return true;
 }
 async function show(){try{
   msg.textContent='';let rows;
   if(!currentShare){const result=await call('shares');shares=result.shares||[];rows=shares.map(x=>({name:x.name,dir:true,share:true,read_only:x.read_only}));}
   else rows=(await call('list')).entries||[];
   document.getElementById('file-breadcrumb').textContent=currentShare?currentShare+(currentPath?' / '+currentPath:''):'My Shares';
   document.getElementById('file-back').disabled=!currentShare;
   document.getElementById('file-new').disabled=readonly();document.getElementById('file-upload').disabled=readonly();
   items.replaceChildren();if(!rows.length){let p=document.createElement('p');p.textContent='Nothing here yet.';items.append(p)}
   for(const x of rows){const line=document.createElement('div');line.className='line';const title=document.createElement('button');title.className='file-entry';title.innerHTML=fileIcon(x.dir?'folder':'file')+`<span class="file-name">${esc(x.name)}</span>`;line.append(title);
     title.onclick=async()=>{if(x.share){currentShare=x.name;currentPath='';await show()}else if(x.dir){currentPath=joined(currentPath,x.name);await show()}else await downloadFile(joined(currentPath,x.name),x.name,x.size)};
     // Downloads are available for files regardless of whether the share is read-only.
     if(!x.share&&!x.dir){const download=document.createElement('button');download.className='icon-btn file-action-btn';download.innerHTML=actionIcon('download');download.title='Download';download.setAttribute('aria-label','Download '+x.name);download.onclick=()=>downloadFile(joined(currentPath,x.name),x.name,x.size);line.append(download)}
     if(!x.share&&!readonly()){
       const action=async(kind,extra)=>{try{await call(kind,{path:joined(currentPath,x.name),...extra});await show()}catch(e){msg.textContent=e.message}};
       const rename=document.createElement('button');rename.className='icon-btn file-action-btn';rename.innerHTML=actionIcon('rename');rename.title='Rename';rename.setAttribute('aria-label','Rename '+x.name);rename.onclick=async()=>{const name=await fileTextDialog({title:'Rename item',label:'New name',initial:x.name,confirmLabel:'Rename'});if(name&&name!==x.name)action('rename',{name})};line.append(rename);
       const copy=document.createElement('button');copy.className='icon-btn file-action-btn';copy.innerHTML=actionIcon('copy');copy.title='Copy';copy.setAttribute('aria-label','Copy '+x.name);copy.onclick=async()=>{const dest=await fileTextDialog({title:'Copy item',label:'Destination within this share',initial:joined(currentPath,x.name+'-copy'),description:'Enter a path relative to the current share.',confirmLabel:'Copy'});if(dest)action('copy',{dest})};line.append(copy);
       const move=document.createElement('button');move.className='icon-btn file-action-btn';move.innerHTML=actionIcon('move');move.title='Move';move.setAttribute('aria-label','Move '+x.name);move.onclick=async()=>{const dest=await fileTextDialog({title:'Move item',label:'Destination within this share',initial:joined(currentPath,x.name),description:'Enter a path relative to the current share.',confirmLabel:'Move'});if(dest&&dest!==joined(currentPath,x.name))action('move',{dest})};line.append(move);
       const del=document.createElement('button');del.className='icon-btn file-action-btn file-action-delete';del.innerHTML=actionIcon('delete');del.title='Delete';del.setAttribute('aria-label','Delete '+x.name);del.onclick=async()=>{if(!confirm('Delete '+x.name+'?'+(x.dir?' Folder must be empty.':'')))return;await action('delete',{})};line.append(del);
     }items.append(line)}
   }catch(e){msg.textContent=e.message}}
 document.getElementById('file-refresh').onclick=()=>show();
 document.getElementById('file-back').onclick=()=>{if(currentPath)currentPath=currentPath.split('/').slice(0,-1).join('/');else currentShare='';show()};
 document.getElementById('file-new').onclick=async()=>{const name=await fileTextDialog({title:'New folder',label:'Folder name',confirmLabel:'Create folder'});if(!name)return;try{await call('mkdir',{name});await show()}catch(e){msg.textContent=e.message}};
 document.getElementById('file-upload').onchange=async e=>{const files=Array.from(e.target.files);e.target.value='';for(let i=0;i<files.length;i++){if(!await uploadFile(files[i],i+1,files.length))break}await show()};
 await show();
}

init();
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    server_version='PiNAS/'+VERSION
    def log_message(self,fmt,*args): print('%s - %s'%(self.address_string(),fmt%args),file=sys.stderr)
    def send_headers(self,code=200,kind='application/json',cookie=None):
        self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if isinstance(self.connection,ssl.SSLSocket):self.send_header('Strict-Transport-Security','max-age=86400')
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers()
    def json(self,data,status=200,cookie=None): self.send_headers(status,cookie=cookie);self.wfile.write(json.dumps(data).encode())
    def session(self):
        cookies=dict(x.strip().split('=',1) for x in self.headers.get('Cookie','').split(';') if '=' in x)
        token=cookies.get('pinas_session','');s=SESSIONS.get(token)
        if s and s['expires']>time.time(): s['expires']=time.time()+idle_seconds(load());return token,s
        SESSIONS.pop(token,None);return '',None
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/':self.send_headers(kind='text/html; charset=utf-8');self.wfile.write(PAGE.encode());return
        if path=='/api/background-image':
            cfg=load();image=cfg.get('login_background','')
            if not image:self.json({'error':'Not found'},404);return
            try:
                meta,b64=image.split(',',1);mime=meta[5:].split(';',1)[0];payload=base64.b64decode(b64,validate=True)
                if mime not in ('image/jpeg','image/png','image/webp'):raise ValueError()
            except (ValueError,IndexError):self.json({'error':'Invalid image'},500);return
            self.send_headers(kind=mime);self.wfile.write(payload);return
        if path=='/api/service-health':
            _,sess=self.session()
            if not sess or sess.get('role')!='admin':self.json({'error':'Administrator access required'},403);return
            self.json(service_health());return
        if path=='/api/smart-health':
            _,sess=self.session()
            if not sess or sess.get('role')!='admin':self.json({'error':'Administrator access required'},403);return
            try:
                p=subprocess.run(['/usr/bin/sudo','-n','/usr/local/libexec/pinas-smart-health'],capture_output=True,text=True,timeout=80)
                if p.returncode:raise RuntimeError((p.stderr or 'SMART check failed')[-250:])
                self.json(json.loads(p.stdout));return
            except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
                self.json({'error':str(exc)},503);return
        if path=='/api/updates':
            _,sess=self.session()
            if not sess or sess.get('role')!='admin':self.json({'error':'Administrator access required'},403);return
            result=package_updates()
            with UPDATE_LOCK:result['status']=UPDATE_STATUS.copy()
            result['reboot_required']=Path('/var/run/reboot-required').exists()
            try:result['schedule']=(DATA/'update-schedule').read_text().strip()
            except OSError:result['schedule']='off'
            self.json(result);return
        if path!='/api/state':self.json({'error':'Not found'},404);return
        cfg=load();token,s=self.session();setup='admin_password' in cfg
        safe={k:cfg.get(k) for k in ('theme','accent','font','cpu_interval','cpu_history','session_timeout')};safe['has_background']=bool(cfg.get('login_background'))
        if s and s.get('role')=='user':safe.update(cfg.get('user_preferences',{}).get(s['username'],{}))
        self.json({'setup':setup,'authenticated':bool(s),'csrf':s['csrf'] if s else '', 'role':s.get('role','admin') if s else '', 'username':s.get('username','') if s else '', 'display_name':((cfg.get('nas_display_names',{}).get(s.get('username',''),s.get('username','')) if isinstance(cfg.get('nas_display_names',{}),dict) else s.get('username','')) if s and s.get('role')=='user' else (admin_record(cfg,s.get('username','')) or {}).get('display_name','') if s else ''), 'settings':safe,'hardware':hardware() if s and s.get('role')=='admin' else {'model':read('/proc/device-tree/model').replace('\x00','') or 'Raspberry Pi','suggested_hostname':suggested_hostname(read('/proc/device-tree/model').replace('\x00',''))},'cpu':cpu_history(cfg.get('cpu_history',10)) if s and s.get('role')=='admin' else {}})
    def do_POST(self):
        path=urlparse(self.path).path
        if path not in ('/api/edit-share','/api/delete-share','/api/setup','/api/login','/api/logout','/api/settings','/api/background','/api/nas-users','/api/admin-users','/api/edit-user','/api/nas-shares','/api/storage','/api/files','/api/user-preferences','/api/updates'):self.json({'error':'Not found'},404);return
        if int(self.headers.get('Content-Length','0'))>6*1024*1024:self.json({'error':'Request too large'},413);return
        try: data=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
        except (ValueError,TypeError):self.json({'error':'Invalid JSON'},400);return
        cfg=load();token,s=self.session()
        if path in ('/api/setup','/api/login'):
            user=data.get('user','');password=data.get('password','')
            if path=='/api/login' and not login_allowed(self.client_address[0]):self.json({'error':'Too many login attempts. Try again in 15 minutes.'},429);return
            if not isinstance(password,str):self.json({'error':'Invalid password'},400);return
            if path=='/api/setup':
                if 'admin_password' in cfg:self.json({'error':'Already configured'},403);return
                hostname=data.get('hostname','')
                if not valid_hostname(hostname):self.json({'error':'NAS name must use lowercase letters, digits and internal hyphens; start with a letter'},400);return
                if not isinstance(user,str) or not (3<=len(user)<=32) or not user.isascii() or not user[0].isalpha() or not all(c.isalnum() or c in '_-' for c in user) or len(password)<12 or len(password)>256:self.json({'error':'Use a 3–32 character username and a 12–256 character password'},400);return
                with SETUP_LOCK:
                    cfg=load()
                    if 'admin_password' in cfg:self.json({'error':'Already configured'},403);return
                    cfg['admin_user']=user;cfg['admin_password']=hash_password(password);cfg['hostname']=hostname;save(cfg)
            else:
                if isinstance(user,str) and isinstance(admin_record(cfg,user),dict) and verify(password,admin_record(cfg,user).get('password','')):
                    role='admin'
                elif isinstance(user,str) and re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',user) and nas_authenticate(user,password):
                    role='user'
                else:
                    login_failed(self.client_address[0]);time.sleep(.35);self.json({'error':'Incorrect credentials'},401);return
            if path=='/api/setup':role='admin'
            login_succeeded(self.client_address[0])
            token=secrets.token_urlsafe(32);SESSIONS[token]={'csrf':secrets.token_urlsafe(32),'expires':time.time()+idle_seconds(cfg),'role':role,'username':user}
            self.json({'ok':True},cookie=f'pinas_session={token}; HttpOnly; SameSite=Strict; Path=/'+('; Secure' if isinstance(self.connection,ssl.SSLSocket) else ''));return
        if not s or not hmac.compare_digest(self.headers.get('X-PiNAS-CSRF',''),s['csrf']):self.json({'error':'Authentication required'},403);return
        if path=='/api/user-preferences':
            if s.get('role')!='user':self.json({'error':'NAS user access required'},403);return
            theme,font,avatar=data.get('theme'),data.get('font'),data.get('avatar','')
            if theme not in ('light','dark','light-cb','dark-cb') or type(font)!=int or font not in (10,12,14,16) or not isinstance(avatar,str) or len(avatar)>360000:
                self.json({'error':'Invalid profile settings'},400);return
            if avatar:
                try:
                    header,encoded=avatar.split(',',1)
                    if header not in ('data:image/png;base64','data:image/jpeg;base64','data:image/webp;base64'):raise ValueError()
                    raw=base64.b64decode(encoded,validate=True)
                    if len(raw)>256*1024 or len(raw)<12:raise ValueError()
                    if not (raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff') or raw.startswith(b'RIFF') and raw[8:12]==b'WEBP'):raise ValueError()
                except (ValueError,IndexError):self.json({'error':'Invalid profile image'},400);return
            with SETUP_LOCK:
                latest=load();prefs=latest.setdefault('user_preferences',{});prefs[s['username']]={'theme':theme,'font':font,'profile_avatar':avatar};save(latest)
            self.json({'preferences':prefs[s['username']]});return
        if path=='/api/files':
            if s.get('role')!='user':self.json({'error':'NAS user login required'},403);return
            action=data.get('action');share=data.get('share','');relative=data.get('path','')
            if action not in ('shares','list','mkdir','delete','rename','move','copy','upload','download','upload_start','upload_chunk','upload_finish','upload_cancel','download_chunk'):
                self.json({'error':'Unsupported file action'},400);return
            try:
                result=nas_file_action(action,s['username'],share,relative,
                    name=data.get('name',''),content=data.get('content',''),dest=data.get('dest',''),token=data.get('token',''),offset=data.get('offset',0),size=data.get('size',0))
                self.json(result)
            except (RuntimeError,OSError,ValueError,subprocess.TimeoutExpired) as exc:
                self.json({'error':str(exc)},400)
            return
        if s.get('role')!='admin':self.json({'error':'Administrator access required'},403);return
        if path=='/api/updates':
            action=data.get('action')
            if action not in ('refresh','upgrade','schedule'):self.json({'error':'Unsupported update action'},400);return
            if action=='schedule':
                schedule=data.get('schedule')
                if schedule not in ('off','daily','weekly','monthly'):self.json({'error':'Invalid update schedule'},400);return
                try:
                    proc=subprocess.run(['/usr/bin/sudo','-n','/usr/local/libexec/pinas-apt-index','schedule',schedule],capture_output=True,text=True,timeout=35)
                    if proc.returncode:self.json({'error':(proc.stderr or 'Could not save update schedule')[-400:]},500);return
                except (OSError,subprocess.TimeoutExpired) as exc:self.json({'error':str(exc)},500);return
                self.json({'ok':True,'schedule':schedule});return
            if action=='upgrade':
                confirmation=data.get('admin_password')
                if not isinstance(confirmation,str) or not verify(confirmation,(admin_record(cfg,s['username']) or {}).get('password','')):
                    self.json({'error':'Incorrect administrator password'},403);return
                if not package_updates().get('packages'):
                    self.json({'error':'No available package upgrades in current APT indexes. Check for updates first.'},409);return
            with UPDATE_LOCK:
                if UPDATE_STATUS['running']:self.json({'error':'Another APT operation is already running'},409);return
                UPDATE_STATUS.update(running=True,operation=action,error='',output='')
            threading.Thread(target=update_worker,args=(action,),daemon=True).start()
            self.json({'ok':True,'message':'APT operation started'});return
        if path=='/api/admin-users':
            username=data.get('username');password=data.get('password');display_name=data.get('display_name');confirmation=data.get('admin_password')
            if not isinstance(username,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',username) or username in ('pinas','root','nobody'):
                self.json({'error':'Enter a valid lowercase username (3–32 characters).'},400);return
            if not valid_display_name(display_name) or not valid_account_password(password):
                self.json({'error':'Display name and a password of 12–256 characters are required.'},400);return
            if not isinstance(confirmation,str) or not verify(confirmation,(admin_record(cfg,s['username']) or {}).get('password','')):
                self.json({'error':'Incorrect administrator password.'},403);return
            if admin_record(cfg,username) or any(u['name']==username for u in nas_user_list()):
                self.json({'error':'Username already exists.'},409);return
            with SETUP_LOCK:
                latest=load();admins=admin_accounts(latest).copy()
                if admin_record(latest,username):self.json({'error':'Username already exists.'},409);return
                admins[username]={'display_name':display_name.strip(),'password':hash_password(password)}
                latest['additional_admins']=admins;save(latest)
            self.json({'ok':True});return
        if path=='/api/edit-user':
            kind=data.get('kind');username=data.get('username');display_name=data.get('display_name');password=data.get('password','')
            if kind not in ('admin','nas') or not isinstance(username,str) or not valid_display_name(display_name):
                self.json({'error':'Invalid account or display name.'},400);return
            if password and not valid_account_password(password):
                self.json({'error':'New password must be 12–256 characters.'},400);return
            if kind=='admin':
                if not admin_record(cfg,username):self.json({'error':'Administrator not found.'},404);return
                with SETUP_LOCK:
                    latest=load()
                    if username==latest.get('admin_user','admin'):
                        latest['admin_display_name']=display_name.strip()
                        if password:latest['admin_password']=hash_password(password)
                    else:
                        admins=admin_accounts(latest).copy()
                        if username not in admins:self.json({'error':'Administrator not found.'},404);return
                        admins[username]={**admins[username],'display_name':display_name.strip()}
                        if password:admins[username]['password']=hash_password(password)
                        latest['additional_admins']=admins
                    save(latest)
            else:
                if not any(u['name']==username for u in nas_user_list()):self.json({'error':'NAS user not found.'},404);return
                if password:
                    try:change_nas_password(username,password)
                    except (RuntimeError,OSError,subprocess.TimeoutExpired) as exc:self.json({'error':str(exc)},503);return
                with SETUP_LOCK:
                    latest=load();names=latest.get('nas_display_names',{}).copy();names[username]=display_name.strip();latest['nas_display_names']=names;save(latest)
            globals()['DISCOVERY_AT']=0
            self.json({'ok':True});return
        if path=='/api/nas-users':
            username=data.get('username');password=data.get('password');display_name=data.get('display_name')
            if not isinstance(username,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',username) or username in ('pinas','root','admin','nobody'):
                self.json({'error':'Use a unique lowercase username (3–32 characters).'},400);return
            if not isinstance(password,str) or not 12<=len(password)<=256:
                self.json({'error':'Password must be between 12 and 256 characters.'},400);return
            if not isinstance(display_name,str) or not 1<=len(display_name.strip())<=80 or any(ord(c)<32 for c in display_name):
                self.json({'error':'Enter a display name (1–80 characters).'},400);return
            display_name=display_name.strip()
            if not shutil.which('smbpasswd') or not shutil.which('pdbedit'):self.json({'error':'Samba utilities are missing. Install Samba and retry.'},503);return
            if not storage_is_ready():self.json({'error':'Configure and persistently mount a data disk before adding users.'},409);return
            if admin_record(cfg,username):
                self.json({'error':'Username reserved for the PiNAS administrator.'},409);return
            if any(u['name']==username for u in nas_user_list()):self.json({'error':'Samba user already exists.'},409);return
            try:provision_nas_user(username,password)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:
                self.json({'error':str(exc)},503);return
            with SETUP_LOCK:
                latest=load();names=latest.get('nas_display_names',{})
                if not isinstance(names,dict):names={}
                names[username]=display_name;latest['nas_display_names']=names;save(latest)
            global DISCOVERY_AT
            DISCOVERY_AT=0
            self.json({'ok':True,'username':username,'display_name':display_name});return
        if path=='/api/storage':
            if s.get('role')!='admin':self.json({'error':'Administrator access required'},403);return
            device=data.get('device');password=data.get('admin_password')
            if not isinstance(device,str) or not re.fullmatch(r'/dev/[A-Za-z0-9_./-]{1,90}',device) or '..' in device:
                self.json({'error':'Invalid device'},400);return
            if not isinstance(password,str) or not verify(password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect'},403);return
            try:result=configure_nas_mount(device)
            except (OSError,subprocess.TimeoutExpired,RuntimeError,ValueError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json(result);return
        if path=='/api/edit-share':
            name=data.get('name');new_name=data.get('new_name');access=data.get('access');password=data.get('admin_password')
            if not all(isinstance(x,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',x) and x.lower() not in ('global','homes','printers','print
            name=data.get('name');password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):
                self.json({'error':'Invalid share name.'},400);return
            if not isinstance(password,str) or not verify(password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not any(isinstance(item,dict) and item.get('name')==name for item in nas_share_list()):
                self.json({'error':'Only PiNAS-managed shares can be removed.'},404);return
            try:delete_nas_share(name)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name,'files_preserved':True});return
        if path=='/api/nas-shares':
            name=data.get('name');volume=data.get('volume');access=data.get('access');admin_password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):
                self.json({'error':'Choose a share name of 1–32 letters, digits, spaces, underscores or hyphens.'},400);return
            if not isinstance(volume,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',volume) or '..' in volume:
                self.json({'error':'Invalid storage selection.'},400);return
            if not isinstance(access,dict) or not access or len(access)>64 or any(not isinstance(k,str) or v not in ('ro','rw') for k,v in access.items()):
                self.json({'error':'Assign at least one user Read Only or Read & Write access.'},400);return
            if not isinstance(admin_password,str) or not verify(admin_password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not storage_is_ready():self.json({'error':'A mounted, persistent data filesystem is required.'},409);return
            valid_users={u['name'] for u in nas_user_list()}
            if not set(access).issubset(valid_users):self.json({'error':'One or more users are not valid Samba accounts.'},409);return
            if any(name.casefold()==s.casefold() for s in discover().get('shares',[])):
                self.json({'error':'A share with this name already exists.'},409);return
            try:create_nas_share(name,volume,access)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name});return
        if path=='/api/logout':SESSIONS.pop(token,None);self.json({'ok':True},cookie='pinas_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'+('; Secure' if isinstance(self.connection,ssl.SSLSocket) else ''));return
        if path=='/api/settings':
            theme,accent,font=data.get('theme'),data.get('accent'),data.get('font')
            interval,history=data.get('cpu_interval',cfg.get('cpu_interval',5)),data.get('cpu_history',cfg.get('cpu_history',10))
            session_timeout=data.get('session_timeout',cfg.get('session_timeout',5))
            if theme not in ('light','dark','dark-cb','light-cb') or not isinstance(accent,str) or len(accent)!=7 or accent[0]!='#' or any(c not in '0123456789abcdefABCDEF' for c in accent[1:]) or type(font)!=int or font not in (10,12,14,16) or type(interval)!=int or interval not in (2,5,10) or type(history)!=int or history not in (10,15,30,60) or type(session_timeout)!=int or session_timeout not in (5,10,15,30,60):self.json({'error':'Invalid appearance settings'},400);return
            cfg.update(theme=theme,accent=accent,font=font,cpu_interval=interval,cpu_history=history,session_timeout=session_timeout)
        elif path=='/api/background':
            image=data.get('image')
            if not isinstance(image,str) or len(image)>2_900_000:self.json({'error':'Image too large'},400);return
            if image:
                try:
                    meta,b64=image.split(',',1);mime=meta[5:].split(';',1)[0]
                    if mime not in ('image/jpeg','image/png','image/webp'):raise ValueError()
                    decoded=base64.b64decode(b64,validate=True)
                    if len(decoded)>2*1024*1024:raise ValueError()
                    if not ((mime=='image/jpeg' and decoded.startswith(b'\xff\xd8\xff')) or (mime=='image/png' and decoded.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/webp' and decoded.startswith(b'RIFF') and decoded[8:12]==b'WEBP')):raise ValueError()
                except (ValueError,IndexError):self.json({'error':'Invalid image'},400);return
            cfg['login_background']=image
        save(cfg);self.json({'settings':dict({k:cfg.get(k) for k in ('theme','accent','font','cpu_interval','cpu_history','session_timeout')},has_background=bool(cfg.get('login_background')))} )

HOSTNAME_HELPER = r"""#!/usr/bin/env python3
import json, re, subprocess
from pathlib import Path
try:
    path=Path('/var/lib/pinas/config.json')
    if not path.exists():raise SystemExit(0)
    cfg=json.loads(path.read_text())
    hostname=cfg.get('hostname','')
    if not hostname:raise SystemExit(0)
    if not isinstance(hostname,str) or not 1<=len(hostname)<=63 or not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*',hostname):
        raise ValueError('Invalid hostname')
    current=subprocess.run(['hostname','-s'],capture_output=True,text=True,check=True).stdout.strip()
    if current!=hostname:
        subprocess.run(['/usr/bin/hostnamectl','set-hostname',hostname],check=True,timeout=15)
except (OSError,ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
    raise SystemExit('PiNAS hostname not applied: '+str(exc))
"""

NAS_USER_HELPER = r"""#!/usr/bin/env python3
# Privileged helper. No arbitrary command execution; narrowly scoped account actions.
import grp, json, os, pwd, re, subprocess, sys

def run(argv, **kwargs):
    return subprocess.run(argv, check=True, timeout=20, **kwargs)

def samba_users():
    p=run(['/usr/bin/pdbedit','-L'],capture_output=True,text=True)
    result=[]
    for line in p.stdout.splitlines():
        fields=line.split(':',2)
        if len(fields)>=2 and re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',fields[0]):
            result.append({'name':fields[0],'uid':fields[1]})
    return sorted(result,key=lambda x:x['name'])

if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit(2)
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(samba_users()))
        raise SystemExit(0)
    if len(sys.argv)!=3 or sys.argv[1] not in ('create','password'):raise SystemExit(2)
    name=sys.argv[2]
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',name) or name in ('pinas','root','admin','nobody'):raise SystemExit(2)
    password=sys.stdin.readline(258).rstrip('\n')
    if not 12<=len(password)<=256:raise SystemExit(2)
    if sys.argv[1]=='password':
        group=grp.getgrnam('pinas-nas')
        existing=pwd.getpwnam(name)
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin') or not any(u['name']==name for u in samba_users()):
            raise SystemExit('Not a managed PiNAS Samba user')
        run(['/usr/bin/smbpasswd','-s',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        raise SystemExit(0)
    try:
        group=grp.getgrnam('pinas-nas')
    except KeyError:
        run(['/usr/sbin/groupadd','pinas-nas'])
        group=grp.getgrnam('pinas-nas')
    created=False
    try:
        existing=pwd.getpwnam(name)
    except KeyError:
        existing=None
    if existing:
        # Repair only a partial PiNAS account from a previous failed attempt.
        # Never repurpose unrelated Linux accounts.
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):
            raise SystemExit('Linux account already exists and is not a PiNAS NAS account; choose another username')
        if any(u['name']==name for u in samba_users()):
            raise SystemExit('Samba account already exists; refresh the Users page')
    else:
        run(['/usr/sbin/useradd','--no-create-home','--shell','/usr/sbin/nologin','--gid','pinas-nas',name])
        created=True
    try:
        run(['/usr/bin/smbpasswd','-s','-a',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        run(['/usr/bin/smbpasswd','-e',name],capture_output=True)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        if created:subprocess.run(['/usr/sbin/userdel',name],check=False,timeout=10)
        raise SystemExit('Samba account creation failed: '+str(exc))
"""

NAS_SHARE_HELPER = r"""#!/usr/bin/env python3
# Root-only share broker. Strict input validation and independent mount checks.
import json, os, pathlib, pwd, re, subprocess, sys, tempfile

DB=pathlib.Path('/var/lib/pinas/shares.json')
CONF=pathlib.Path('/etc/samba/pinas-shares.conf')
SMB=pathlib.Path('/etc/samba/smb.conf')

def run(cmd, **kw):
    return subprocess.run(cmd,check=True,timeout=15,capture_output=True,text=True,**kw)

def read_db():
    try:
        value=json.loads(DB.read_text())
        return value if isinstance(value,list) else []
    except (OSError,ValueError):return []

def atomic(path,content,mode=0o600):
    fd,name=tempfile.mkstemp(prefix='.pinas-',dir=str(path.parent))
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'w') as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def check_volume(device):
    if not isinstance(device,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',device) or '..' in device:raise ValueError('Invalid device')
    # Device must be a block device with an approved filesystem.
    p=pathlib.Path(device)
    if not p.is_block_device():raise ValueError('Selected storage is not a block device')
    fs=run(['/usr/bin/lsblk','-n','-o','FSTYPE',device]).stdout.strip().splitlines()
    if not fs or fs[0].strip().lower() not in ('ext4','xfs','btrfs'):raise ValueError('Unsupported filesystem')
    target=run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device]).stdout.strip().splitlines()
    if len(target)!=1:raise ValueError('Disk must have one unambiguous active mount')
    mount=pathlib.Path(target[0]).resolve(strict=True)
    if str(mount) in ('/','/boot','/boot/firmware') or any(str(mount).startswith(prefix) for prefix in ('/etc/','/var/','/usr/','/home/','/opt/','/root/','/proc/','/sys/','/run/')):
        raise ValueError('System storage cannot host NAS shares')
    if not mount.is_dir() or mount.is_symlink():raise ValueError('Invalid mount directory')
    # Confirm mounted persistently via UUID, path or LABEL; do not trust browser data.
    uuid=run(['/usr/sbin/blkid','-s','UUID','-o','value',device]).stdout.strip()
    entries=[line.split() for line in pathlib.Path('/etc/fstab').read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not any(len(e)>=2 and e[1]==str(mount) and e[0] in (device,'UUID='+uuid,'/dev/disk/by-uuid/'+uuid) for e in entries):
        raise ValueError('Disk is not persistently configured in fstab')
    # Reject root device even when mounted at a second location.
    rootdev=run(['/usr/bin/findmnt','-n','-o','SOURCE','/']).stdout.strip()
    if rootdev.startswith('/dev/'):
        rootparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',rootdev]).stdout.split())
        selectedparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',device]).stdout.split())
        if rootparents & selectedparents:raise ValueError('Operating system disk is protected')
    return mount

def main():
    if os.geteuid()!=0:raise ValueError('Root helper required')
    if len(sys.argv)==2 and sys.argv[1]=='list':
        items=read_db()
        for item in items:
            if not isinstance(item,dict):continue
            if isinstance(item.get('folder'),str) and item['folder'].startswith('/'):continue
            device=item.get('volume','')
            if not isinstance(device,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',device) or '..' in device:continue
            try:
                mount=run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device]).stdout.strip().splitlines()
                if len(mount)==1:item['folder']=str(pathlib.Path(mount[0])/'PiNAS Shares'/item.get('name',''))
            except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired):pass
        print(json.dumps(items));return
    if len(sys.argv)==2 and sys.argv[1]=='edit':
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('Request too large')
        request=json.loads(raw)
        name=request.get('name');new_name=request.get('new_name');access=request.get('access')
        valid=lambda n:isinstance(n,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',n) and n.lower() not in ('global','homes','printers','print
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('Request too large')
        request=json.loads(raw);name=request.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):raise ValueError('Invalid share name')
        current=read_db()
        matches=[item for item in current if isinstance(item,dict) and item.get('name')==name]
        if len(matches)!=1:raise ValueError('Share is not managed by PiNAS')
        oldconf=CONF.read_text()
        # Match only a complete, exact managed Samba section; never touch unrelated shares.
        section=re.compile(r'(?m)^\['+re.escape(name)+r'\][ \t]*\n(?:(?!\[).*(?:\n|$))*')
        found=list(section.finditer(oldconf))
        if len(found)!=1:raise ValueError('Managed Samba share section missing or ambiguous')
        updated=oldconf[:found[0].start()]+oldconf[found[0].end():]
        olddb=DB.read_text()
        try:
            atomic(CONF,updated,0o644)
            run(['/usr/bin/testparm','-s'])
            run(['/usr/bin/systemctl','reload','smbd'])
            atomic(DB,json.dumps([item for item in current if not (isinstance(item,dict) and item.get('name')==name)],indent=2),0o600)
        except Exception:
            atomic(CONF,oldconf,0o644)
            atomic(DB,olddb,0o600)
            try:run(['/usr/bin/systemctl','reload','smbd'])
            except Exception:pass
            raise
        # Deliberately leave the share directory, ACLs and files untouched.
        print(json.dumps({'ok':True,'files_preserved':True}));return
    if len(sys.argv)!=2 or sys.argv[1]!='create':raise ValueError('Unsupported action')
    raw=sys.stdin.read(8193)
    if len(raw)>8192:raise ValueError('Request too large')
    request=json.loads(raw)
    name=request.get('name');access=request.get('access');device=request.get('volume')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):raise ValueError('Invalid share name')
    if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):raise ValueError('Invalid access policy')
    # Verify users exist in Samba and Linux before creating any directory.
    samba={line.split(':',1)[0] for line in run(['/usr/bin/pdbedit','-L']).stdout.splitlines()}
    for user in access:
        if user not in samba:raise ValueError('Samba account not found: '+user)
        pwd.getpwnam(user)
    mount=check_volume(device)
    current=read_db()
    if any(item.get('name','').casefold()==name.casefold() for item in current):raise ValueError('Share already exists')
    # Samba's own configuration may include external shares; reject collisions.
    existing=run(['/usr/bin/testparm','-s']).stdout
    if any(line.strip().casefold()=='['+name.casefold()+']' for line in existing.splitlines()):raise ValueError('Share name already used by Samba')
    # No preexisting folder is ever adopted or modified by this operation.
    root=mount/'PiNAS Shares'
    if root.is_symlink():raise ValueError('Unsafe share root')
    root.mkdir(mode=0o711,exist_ok=True)
    if root.stat().st_uid!=0 or (root.stat().st_mode & 0o022):raise ValueError('Share root must be root-owned and not group/world writable')
    folder=root/name
    if folder.exists() or folder.is_symlink():raise ValueError('Folder already exists; choose a different name')
    if not pathlib.Path('/usr/bin/setfacl').exists():raise ValueError('POSIX ACL tools are required (install acl)')
    # Validate smb.conf can be managed before changing filesystem.
    original=SMB.read_text()
    include='   include = /etc/samba/pinas-shares.conf'
    if include not in original:
        if not re.search(r'(?im)^\s*\[global\]\s*$',original):raise ValueError('Samba [global] section missing')
        amended=re.sub(r'(?im)^(\s*\[global\]\s*)$',r'\1\n'+include,original,count=1)
    else:amended=original
    # Explicit per-user access; default deny for other NAS accounts.
    ro=[u for u,p in access.items() if p=='ro'];rw=[u for u,p in access.items() if p=='rw']
    stanza='\n['+name+']\n   path = '+str(folder)+'\n   browseable = yes\n   guest ok = no\n   read only = yes\n   valid users = '+', '.join(access)+'\n'
    if rw:stanza+='   write list = '+', '.join(rw)+'\n'
    stanza+='   create mask = 0660\n   directory mask = 0770\n   follow symlinks = no\n   wide links = no\n'
    oldconf=CONF.read_text() if CONF.exists() else ''
    if '['+name+']' in oldconf:raise ValueError('Duplicate managed share')
    folder.mkdir(mode=0o700)
    try:
        # Root-owned folder; Samba creates files as authenticated Unix users.
        os.chown(folder,0,0)
        os.chmod(folder,0o700)
        acl=['u::rwx','g::---','o::---','m::rwx']+[f'u:{u}:'+('rwx' if p=='rw' else 'r-x') for u,p in access.items()]
        default=['d:'+entry for entry in acl]
        run(['/usr/bin/setfacl','-m',','.join(acl+default),str(folder)])
        if amended!=original:atomic(SMB,amended,0o644)
        atomic(CONF,oldconf+stanza,0o644)
        run(['/usr/bin/testparm','-s'])
        run(['/usr/bin/systemctl','reload','smbd'])
        current.append({'name':name,'volume_label':mount.name,'volume':device,'folder':str(folder),'access':access})
        atomic(DB,json.dumps(current,indent=2),0o600)
    except Exception:
        atomic(CONF,oldconf,0o644)
        if amended!=original:atomic(SMB,original,0o644)
        try:run(['/usr/bin/systemctl','reload','smbd'])
        except Exception:pass
        try:folder.rmdir()
        except OSError:pass
        raise
    print(json.dumps({'ok':True,'name':name}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

NAS_FILES_HELPER = r"""#!/usr/bin/env python3
# Privileged, narrow file broker. Authentication against Samba passdb; filesystem
# operations executed as the NAS user's actual UID/GID and supplementary groups.
import base64, hashlib, hmac, json, os, pathlib, pwd, re, stat, subprocess, sys
DB=pathlib.Path('/var/lib/pinas/shares.json')
def md4(message):
    # NT hash is MD4(UTF-16LE password). Samba uses NT hashes for SMB auth.
    import struct
    original=len(message);message+=b'\x80';message+=b'\0'*((56-len(message)%64)%64)+struct.pack('<Q',original*8)
    a,b,c,d=0x67452301,0xefcdab89,0x98badcfe,0x10325476
    def rol(v,n):return ((v<<n)|(v>>(32-n)))&0xffffffff
    for offset in range(0,len(message),64):
        x=struct.unpack('<16I',message[offset:offset+64]);aa,bb,cc,dd=a,b,c,d
        for j in range(48):
            if j<16:f=(b&c)|(~b&d);k=j;shift=[3,7,11,19][j%4];constant=0
            elif j<32:f=(b&c)|(b&d)|(c&d);k=(j%4)*4+j//4-4;shift=[3,5,9,13][j%4];constant=0x5a827999
            else:f=b^c^d;k=[0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15][j-32];shift=[3,9,11,15][j%4];constant=0x6ed9eba1
            value=rol((a+f+x[k]+constant)&0xffffffff,shift);a,b,c,d=d,value,b,c
        a=(a+aa)&0xffffffff;b=(b+bb)&0xffffffff;c=(c+cc)&0xffffffff;d=(d+dd)&0xffffffff
    return struct.pack('<4I',a,b,c,d).hex().upper()
def samba_hash(user):
    p=subprocess.run(['/usr/bin/pdbedit','-Lw',user],capture_output=True,text=True,timeout=8)
    if p.returncode:raise ValueError('Unknown NAS account')
    for line in p.stdout.splitlines():
        fields=line.split(':')
        if len(fields)>4 and fields[0]==user and re.fullmatch('[A-Fa-f0-9]{32}',fields[3]):return fields[3].upper()
    raise ValueError('NAS account has no valid Samba password')
def valid_user(user):
    if not isinstance(user,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',user):raise ValueError('Invalid user')
    person=pwd.getpwnam(user)
    if person.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):raise ValueError('Not a PiNAS NAS user')
    if samba_hash(user)=='':raise ValueError('Not a Samba user')
    return person
def shares_for(user):
    entries=json.loads(DB.read_text())
    return [s for s in entries if isinstance(s,dict) and s.get('access',{}).get(user) in ('ro','rw')]
def drop(person):
    os.initgroups(person.pw_name,person.pw_gid);os.setgid(person.pw_gid);os.setuid(person.pw_uid)
def safe_path(root,relative):
    if not isinstance(relative,str) or len(relative)>1000 or relative.startswith('/') or '\\' in relative or '\x00' in relative:raise ValueError('Invalid path')
    parts=relative.split('/') if relative else []
    if any(x in ('','.','..') or x.startswith('.pinas-upload-') for x in parts):raise ValueError('Invalid path')
    # Reject symlinks at every level, including the leaf. Never follow them.
    cur=root
    for part in parts:
        cur=cur/part
        if cur.is_symlink():raise ValueError('Symbolic links are not accessible')
    if not cur.resolve(strict=False).is_relative_to(root.resolve(strict=True)):raise ValueError('Path outside share')
    return cur
def main():
    if os.geteuid()!=0:raise ValueError('Root required')
    raw=sys.stdin.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise ValueError('Request too large')
    q=json.loads(raw);action=q.get('action');user=q.get('username');person=valid_user(user)
    if action=='authenticate':
        password=q.get('password')
        if not isinstance(password,str) or len(password)>256:raise ValueError('Invalid password')
        print('true' if hmac.compare_digest(md4(password.encode('utf-16le')),samba_hash(user)) else 'false');return
    allowed=shares_for(user)
    if action=='shares':
        print(json.dumps({'shares':[{'name':s['name'],'read_only':s['access'][user]=='ro'} for s in allowed]}));return
    share=q.get('share');s=next((x for x in allowed if x['name']==share),None)
    if s is None:raise ValueError('Share not accessible')
    # Root path derived exclusively from privileged share metadata, not browser paths.
    root=pathlib.Path(s['volume_label']) if False else None
    # Resolve mount from device, and confirm it is still the same mounted filesystem.
    device=s['volume'];p=subprocess.run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device],capture_output=True,text=True,timeout=5)
    targets=p.stdout.strip().splitlines()
    if p.returncode or len(targets)!=1:raise ValueError('Share storage is offline')
    mount=pathlib.Path(targets[0]).resolve(strict=True)
    if str(mount)=='/' or str(mount).startswith(('/etc/','/var/','/usr/','/home/','/boot/')):raise ValueError('Protected mount')
    root=mount/'PiNAS Shares'/s['name']
    if root.is_symlink() or not root.is_dir():raise ValueError('Share folder unavailable')
    relative=q.get('path','');target=safe_path(root,relative)
    writable=s['access'][user]=='rw'
    if action in ('mkdir','delete','rename','move','copy','upload','upload_start','upload_chunk','upload_finish','upload_cancel') and not writable:raise ValueError('Read-only share')
    drop(person)
    # All operations below run with the NAS user's UID/GID. Uploads are staged
    # in the destination directory, then published by an atomic rename.
    def valid_name(name):
        if not isinstance(name,str) or not name or len(name)>255 or name in ('.','..') or '/' in name or '\\' in name or '\x00' in name or name.startswith('.pinas-upload-'):raise ValueError('Invalid file name')
        return name
    def destination(relative):
        dest=safe_path(root,relative)
        if dest==root or dest.exists() or dest.is_symlink():raise ValueError('Destination already exists')
        if not dest.parent.is_dir():raise ValueError('Destination folder does not exist')
        return dest
    if action in ('rename','move','copy'):
        if target==root or not target.exists():raise ValueError('Invalid source')
        if action=='rename':
            dest=destination('/'.join(filter(None,[relative.rsplit('/',1)[0] if '/' in relative else '',valid_name(q.get('name'))])))
        else:
            dest=destination(q.get('dest',''))
        if target.is_dir() and (dest==target or target in dest.parents):raise ValueError('Cannot place folder inside itself')
        if action=='copy':
            import shutil
            if target.is_dir():
                # Reject links anywhere in the tree and cap total copy size.
                total=0
                for directory,dirs,files in os.walk(target,followlinks=False):
                    for name in dirs+files:
                        node=pathlib.Path(directory)/name
                        if node.is_symlink():raise ValueError('Symbolic links cannot be copied')
                        if node.is_file():total+=node.stat().st_size
                        if total>8*1024**3:raise ValueError('Folder copy exceeds 8 GiB safety limit')
                shutil.copytree(target,dest,symlinks=False)
            elif target.is_file():
                with target.open('rb') as src, dest.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            else:raise ValueError('Unsupported file type')
        else:
            # Same-share only; atomic rename prevents partial moves.
            if target.is_file():
                os.link(target,dest,follow_symlinks=False);target.unlink()
            else:target.rename(dest)
        print('{"ok":true}');return
    if action=='upload_start':
        name=valid_name(q.get('name'))
        if not target.is_dir():raise ValueError('Not a folder')
        destination('/'.join(filter(None,[relative,name])))
        size=q.get('size')
        if not isinstance(size,int) or size<0 or size>100*1024**3:raise ValueError('Invalid upload size')
        import secrets
        token=secrets.token_hex(20)
        staging=target/('.pinas-upload-'+token)
        fd=os.open(staging,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        meta=target/('.pinas-upload-'+token+'.json')
        fd=os.open(meta,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'name':name,'size':size,'path':relative},f)
        print(json.dumps({'token':token}));return
    if action in ('upload_chunk','upload_finish','upload_cancel'):
        token=q.get('token','')
        if not isinstance(token,str) or not re.fullmatch('[0-9a-f]{40}',token):raise ValueError('Invalid transfer token')
        stage=target/('.pinas-upload-'+token)
        meta=target/('.pinas-upload-'+token+'.json')
        if stage.is_symlink() or meta.is_symlink() or not stage.is_file() or not meta.is_file():raise ValueError('Unknown transfer')
        details=json.loads(meta.read_text());name=valid_name(details['name']);size=details['size']
        if details.get('path')!=relative:raise ValueError('Transfer location mismatch')
        if action=='upload_cancel':stage.unlink();meta.unlink();print('{"ok":true}');return
        if action=='upload_chunk':
            content=q.get('content','');offset=q.get('offset')
            if not isinstance(content,str) or len(content)>700000 or not isinstance(offset,int):raise ValueError('Invalid chunk')
            payload=base64.b64decode(content,validate=True)
            if len(payload)>512*1024 or offset!=stage.stat().st_size or offset+len(payload)>size:raise ValueError('Chunk offset or size mismatch')
            with stage.open('ab') as f:f.write(payload)
            print(json.dumps({'offset':offset+len(payload)}));return
        if stage.stat().st_size!=size:raise ValueError('Upload incomplete')
        dest=destination('/'.join(filter(None,[relative,name])))
        # Hard-link is no-clobber and atomic on the same filesystem.
        os.link(stage,dest,follow_symlinks=False);stage.unlink();meta.unlink()
        print('{"ok":true}');return
    if action=='download_chunk':
        offset=q.get('offset');size=q.get('size')
        if not isinstance(offset,int) or offset<0 or not isinstance(size,int) or size<1 or size>512*1024:raise ValueError('Invalid download range')
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode):raise ValueError('Not a regular file')
        total=target.stat().st_size
        with target.open('rb') as f:f.seek(offset);chunk=f.read(size)
        print(json.dumps({'content':base64.b64encode(chunk).decode(),'total':total}));return
    if action=='list':
        if not target.is_dir():raise ValueError('Not a folder')
        entries=[]
        for child in sorted(target.iterdir(),key=lambda x:x.name.casefold()):
            if child.is_symlink() or child.name.startswith('.pinas-upload-'):continue
            try:st=child.stat()
            except OSError:continue
            if stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode):entries.append({'name':child.name,'dir':stat.S_ISDIR(st.st_mode),'size':st.st_size})
            if len(entries)>=1000:break
        print(json.dumps({'entries':entries}));return
    if action=='mkdir':
        name=q.get('name','');dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..'):raise ValueError('Invalid folder name')
        dest.mkdir(mode=0o770);print('{"ok":true}');return
    if action=='delete':
        if target==root:raise ValueError('Cannot delete share root')
        if target.is_dir():target.rmdir()
        elif target.is_file():target.unlink()
        else:raise ValueError('Not a regular file or empty folder')
        print('{"ok":true}');return
    if action=='download':
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode) or target.stat().st_size>3*1024*1024:raise ValueError('Only files up to 3 MB supported in this test build')
        with target.open('rb') as f:content=base64.b64encode(f.read()).decode()
        print(json.dumps({'content':content}));return
    if action=='upload':
        name=q.get('name','');content=q.get('content','')
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..') or not isinstance(content,str) or len(content)>4*1024*1024+16:raise ValueError('Invalid upload')
        dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not target.is_dir():raise ValueError('Not a directory')
        payload=base64.b64decode(content,validate=True)
        if len(payload)>3*1024*1024:raise ValueError('Upload exceeds 3 MB')
        fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o660)
        with os.fdopen(fd,'wb') as f:f.write(payload)
        print('{"ok":true}');return
    raise ValueError('Unsupported action')
if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
"""

APT_INDEX_HELPER = r"""#!/usr/bin/env python3
import os,subprocess,sys
from pathlib import Path
ALLOWED={'off':None,'daily':'*-*-* 01:00:00','weekly':'Fri *-*-* 01:00:00','monthly':'*-*-28 01:00:00'}
def run(cmd,timeout=30):
    p=subprocess.run(cmd,timeout=timeout,check=False)
    if p.returncode:sys.exit(p.returncode)
def main():
    if os.geteuid()!=0:sys.exit('Root access required')
    args=sys.argv[1:]
    if len(args)==2 and args[0]=='schedule' and args[1] in ALLOWED:
        schedule=args[1];calendar=ALLOWED[schedule]
        timer=Path('/etc/systemd/system/pinas-auto-updates.timer')
        if calendar:
            timer.write_text('[Unit]\nDescription=PiNAS automatic OS updates\n[Timer]\nOnCalendar='+calendar+'\nPersistent=true\nUnit=pinas-auto-updates.service\n[Install]\nWantedBy=timers.target\n')
        run(['systemctl','daemon-reload'])
        if calendar:
            run(['systemctl','enable','--now','pinas-auto-updates.timer'])
            run(['systemctl','restart','pinas-auto-updates.timer'])
        else:
            run(['systemctl','disable','--now','pinas-auto-updates.timer']) if timer.exists() else None
            timer.unlink(missing_ok=True)
            run(['systemctl','daemon-reload'])
        marker=Path('/var/lib/pinas/update-schedule');marker.write_text(schedule+'\n');os.chmod(marker,0o644)
        return
    if args==['automatic']:
        # Only the systemd oneshot invokes this command, not the web service account.
        run(['/usr/bin/apt-get','update'],210)
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
        return
    if args==['upgrade']:
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
    elif args==['refresh']:
        run(['/usr/bin/apt-get','update'],210)
    else:sys.exit('Unsupported operation')
if __name__=='__main__':main()
"""

NAS_STORAGE_HELPER='#!/usr/bin/env python3\n"""PiNAS RC13 restricted, non-destructive storage adoption helper."""\nimport json,os,pathlib,re,subprocess,sys,uuid\nfrom pathlib import Path\n\ndef run(*args,timeout=15):\n    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)\n    if p.returncode:raise ValueError((p.stderr or \'Storage command failed\').strip()[-500:])\n    return p.stdout.strip()\n\ndef main():\n    if os.geteuid()!=0 or sys.argv[1:]!=[\'adopt\']:raise ValueError(\'Unsupported storage operation\')\n    data=json.loads(sys.stdin.read(4096));device=data.get(\'device\')\n    if not isinstance(device,str) or not re.fullmatch(r\'/dev/[A-Za-z0-9_./-]{1,90}\',device) or \'..\' in device:raise ValueError(\'Invalid device\')\n    path=Path(device)\n    if not path.is_block_device():raise ValueError(\'Device is not a block device\')\n    # The privileged helper independently identifies eligible physical disks.\n    roots=json.loads(run(\'lsblk\',\'-J\',\'-b\',\'-o\',\'NAME,PATH,TYPE,FSTYPE,UUID,MOUNTPOINTS,RO,PKNAME\')).get(\'blockdevices\',[])\n    bypath={};byname={};parents={}\n    def walk(node,parent=None):\n        name=node.get(\'name\');bypath[node.get(\'path\')]=node;byname[name]=node\n        if parent:parents[name]=parent\n        for child in node.get(\'children\') or []:walk(child,name)\n    for root in roots:walk(root)\n    node=bypath.get(str(path.resolve())) or bypath.get(device)\n    if not node or node.get(\'type\') not in (\'part\',\'disk\') or node.get(\'ro\'):raise ValueError(\'Not an eligible writable disk or partition\')\n    def root_for(n):\n        seen=set()\n        while n.get(\'name\') in parents:\n            if n[\'name\'] in seen:raise ValueError(\'Invalid device topology\')\n            seen.add(n[\'name\']);n=byname[parents[n[\'name\']]]\n        return n\n    disk=root_for(node)\n    if disk.get(\'type\')!=\'disk\' or disk.get(\'ro\') or str(disk.get(\'name\',\'\')).startswith((\'loop\',\'zram\',\'ram\',\'nbd\',\'sr\',\'fd\')):raise ValueError(\'Unsupported backing device\')\n    # Reject any physical disk carrying the root or boot filesystems.\n    protected={\'/\',\'/boot\',\'/boot/firmware\',\'/boot/efi\'}\n    def contains_system(n):\n        if any(m in protected for m in (n.get(\'mountpoints\') or []) if m):return True\n        return any(contains_system(c) for c in n.get(\'children\') or [])\n    if contains_system(disk):raise ValueError(\'Operating system storage is protected\')\n    for mount in protected:\n        src=run(\'findmnt\',\'-n\',\'-o\',\'SOURCE\',\'--target\',mount).split(\'[\',1)[0]\n        if src and src in bypath and root_for(bypath[src]).get(\'name\')==disk.get(\'name\'):\n            raise ValueError(\'Operating system storage is protected\')\n    fs=run(\'blkid\',\'-s\',\'TYPE\',\'-o\',\'value\',device)\n    uid=run(\'blkid\',\'-s\',\'UUID\',\'-o\',\'value\',device)\n    if fs not in (\'ext4\',\'xfs\',\'btrfs\') or not re.fullmatch(r\'[A-Za-z0-9-]{8,64}\',uid):raise ValueError(\'Supported filesystem and UUID required\')\n    # Reject RAID/LVM/crypto members and nested volume layouts.\n    if node.get(\'type\')==\'disk\' and node.get(\'children\'):raise ValueError(\'Choose a filesystem partition, not its parent disk\')\n    if node.get(\'children\'):raise ValueError(\'Complex volume layout not supported\')\n    mountpoints=[m for m in node.get(\'mountpoints\') or [] if m]\n    if len(mountpoints)>1:raise ValueError(\'Multiple mountpoints require manual review\')\n    if mountpoints and not str(mountpoints[0]).startswith(\'/mnt/pinas/\'):\n        raise ValueError(\'Filesystem is already mounted elsewhere; manage it manually to avoid disrupting applications\')\n    target=Path(\'/mnt/pinas\')/uid\n    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir())) and str(target) not in mountpoints):raise ValueError(\'Mount destination is not empty\')\n    fstab=Path(\'/etc/fstab\');original=fstab.read_text();entries=[line.split() for line in original.splitlines() if line.strip() and not line.lstrip().startswith(\'#\')]\n    for e in entries:\n        if len(e)>=2 and (e[0] in (device,\'UUID=\'+uid,\'/dev/disk/by-uuid/\'+uid) or e[1]==str(target)):\n            if e[0]==\'UUID=\'+uid and e[1]==str(target):\n                if str(target) not in mountpoints:run(\'mount\',str(target),timeout=25)\n                print(json.dumps({\'ok\':True,\'mount\':str(target),\'existing\':True}));return\n            raise ValueError(\'Existing fstab configuration requires manual review\')\n    target.parent.mkdir(parents=True,exist_ok=True)\n    target.mkdir(mode=0o755,exist_ok=True)\n    options=\'defaults,nofail,noatime,x-systemd.device-timeout=10s\'\n    entry=f\'UUID={uid} {target} {fs} {options} 0 {2 if fs=="ext4" else 0} # PiNAS managed\\\\n\'\n    entry=entry.replace(\'\\\\n\',\'\\n\')\n    backup=fstab.with_name(\'fstab.pinas-\'+uuid.uuid4().hex[:12]+\'.bak\')\n    backup.write_text(original);os.chmod(backup,0o600)\n    temp=fstab.with_name(\'.fstab.pinas-\'+uuid.uuid4().hex)\n    try:\n        temp.write_text(original.rstrip(\'\\n\')+\'\\n\'+entry);os.chmod(temp,0o644)\n        os.replace(temp,fstab)\n        run(\'systemctl\',\'daemon-reload\',timeout=15)\n        run(\'mount\',str(target),timeout=25)\n        actual=run(\'findmnt\',\'-n\',\'-o\',\'UUID\',\'--target\',str(target))\n        if actual!=uid:raise ValueError(\'Mounted filesystem UUID verification failed\')\n    except Exception:\n        fstab.write_text(original)\n        try:run(\'systemctl\',\'daemon-reload\')\n        except Exception:pass\n        raise\n    print(json.dumps({\'ok\':True,\'mount\':str(target)}))\nif __name__==\'__main__\':\n    try:main()\n    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)\n'

SMART_HEALTH_HELPER = """#!/usr/bin/env python3
import json,os,shutil,subprocess,sys
from pathlib import Path
def main():
    if os.geteuid()!=0 or len(sys.argv)!=1:
        raise ValueError('Unsupported operation')
    smartctl=shutil.which('smartctl')
    if not smartctl:
        print(json.dumps({'installed':False,'drives':[]}));return
    p=subprocess.run(['lsblk','-J','-b','-o','NAME,PATH,TYPE,MODEL,TRAN'],capture_output=True,text=True,timeout=8,check=True)
    drives=[]
    for disk in json.loads(p.stdout).get('blockdevices',[]):
        if disk.get('type')!='disk':continue
        device=disk.get('path','')
        if not isinstance(device,str) or not device.startswith('/dev/') or not Path(device).is_block_device():continue
        if disk.get('name','').startswith(('loop','zram','ram','nbd','sr','fd')):continue
        entry={'device':device,'model':disk.get('model') or disk.get('name'),'status':'Unavailable','temperature':None}
        try:
            result=subprocess.run([smartctl,'-j','-H','-A',device],capture_output=True,text=True,timeout=12)
            data=json.loads(result.stdout)
            health=data.get('smart_status',{}).get('passed')
            if health is True:entry['status']='Healthy'
            elif health is False:entry['status']='Warning'
            temp=data.get('temperature',{}).get('current')
            if isinstance(temp,(int,float)) and -20<=temp<=120:entry['temperature']=temp
            if data.get('smart_support',{}).get('available') is False:entry['status']='Unsupported'
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        drives.append(entry)
    print(json.dumps({'installed':True,'drives':drives}))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

def install(args):
    if sys.platform!='linux' or os.geteuid()!=0:sys.exit('Install requires Linux and sudo/root.')
    if not Path('/etc/os-release').exists():sys.exit('Unsupported OS')
    osinfo=read('/etc/os-release')
    if 'debian' not in osinfo.lower() and 'raspbian' not in osinfo.lower():sys.exit('Requires Raspberry Pi OS / Debian family')
    if not args.skip_packages:
        print('Installing NAS dependencies (requires network and may take time)...',flush=True)
        subprocess.run(['apt-get','update'],check=True)
        subprocess.run(['apt-get','install','-y','samba','xfsprogs','btrfs-progs','mdadm','parted','util-linux','e2fsprogs','avahi-daemon','acl','openssl'],check=True)
    target=Path('/opt/pinas');target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(__file__).resolve(),target/'pinas.py');os.chmod(target/'pinas.py',0o755)
    if subprocess.run(['id','-u','pinas'],capture_output=True).returncode!=0:
        subprocess.run(['useradd','--system','--home-dir','/var/lib/pinas','--shell','/usr/sbin/nologin','pinas'],check=True)
    DATA.mkdir(parents=True,exist_ok=True);os.chmod(DATA,0o700)
    subprocess.run(['chown','pinas:pinas',str(DATA)],check=True)
    helper=Path('/usr/local/libexec/pinas-apply-hostname')
    helper.parent.mkdir(parents=True,exist_ok=True)
    helper.write_text(HOSTNAME_HELPER)
    os.chmod(helper,0o755)
    unit='''[Unit]\nDescription=Apply validated PiNAS device hostname\nAfter=systemd-hostnamed.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /usr/local/libexec/pinas-apply-hostname\nNoNewPrivileges=true\nProtectHome=true\nPrivateTmp=true\n'''
    Path('/etc/systemd/system/pinas-hostname.service').write_text(unit)
    path_unit='''[Unit]\nDescription=Apply PiNAS hostname when configuration changes\n[Path]\nPathChanged=/var/lib/pinas/config.json\nUnit=pinas-hostname.service\n[Install]\nWantedBy=multi-user.target\n'''
    Path('/etc/systemd/system/pinas-hostname.path').write_text(path_unit)
    user_helper=Path('/usr/local/libexec/pinas-nas-user')
    user_helper.write_text(NAS_USER_HELPER)
    os.chown(user_helper,0,0);os.chmod(user_helper,0o700)
    sudoers=Path('/etc/sudoers.d/pinas-nas-user')
    sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-user create *, /usr/local/libexec/pinas-nas-user password *, /usr/local/libexec/pinas-nas-user list\n')
    os.chown(sudoers,0,0);os.chmod(sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(sudoers)],capture_output=True).returncode:
        sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS sudoers configuration')
    share_helper=Path('/usr/local/libexec/pinas-nas-share')
    share_helper.write_text(NAS_SHARE_HELPER)
    os.chown(share_helper,0,0);os.chmod(share_helper,0o700)
    share_sudoers=Path('/etc/sudoers.d/pinas-nas-share')
    share_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-share list, /usr/local/libexec/pinas-nas-share create\n')
    os.chown(share_sudoers,0,0);os.chmod(share_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(share_sudoers)],capture_output=True).returncode:
        share_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS share sudoers configuration')
    files_helper=Path('/usr/local/libexec/pinas-nas-files')
    files_helper.write_text(NAS_FILES_HELPER)
    os.chown(files_helper,0,0);os.chmod(files_helper,0o700)
    files_sudoers=Path('/etc/sudoers.d/pinas-nas-files')
    files_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-files\n')
    os.chown(files_sudoers,0,0);os.chmod(files_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(files_sudoers)],capture_output=True).returncode:
        files_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS file helper sudoers configuration')
    storage_helper=Path('/usr/local/libexec/pinas-nas-storage')
    storage_helper.write_text(NAS_STORAGE_HELPER)
    os.chown(storage_helper,0,0);os.chmod(storage_helper,0o700)
    storage_sudoers=Path('/etc/sudoers.d/pinas-nas-storage')
    storage_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-storage adopt\n')
    os.chown(storage_sudoers,0,0);os.chmod(storage_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(storage_sudoers)],capture_output=True).returncode:
        storage_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS storage sudoers configuration')
    smart_helper=Path('/usr/local/libexec/pinas-smart-health')
    smart_helper.write_text(SMART_HEALTH_HELPER)
    os.chown(smart_helper,0,0);os.chmod(smart_helper,0o700)
    smart_sudoers=Path('/etc/sudoers.d/pinas-smart-health')
    smart_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-smart-health\n')
    os.chown(smart_sudoers,0,0);os.chmod(smart_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(smart_sudoers)],capture_output=True).returncode:
        smart_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS SMART sudoers configuration')
    apt_helper=Path('/usr/local/libexec/pinas-apt-index')
    apt_helper.write_text(APT_INDEX_HELPER)
    os.chown(apt_helper,0,0);os.chmod(apt_helper,0o700)
    apt_sudoers=Path('/etc/sudoers.d/pinas-apt-index')
    apt_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-apt-index refresh, /usr/local/libexec/pinas-apt-index upgrade, /usr/local/libexec/pinas-apt-index schedule off, /usr/local/libexec/pinas-apt-index schedule daily, /usr/local/libexec/pinas-apt-index schedule weekly, /usr/local/libexec/pinas-apt-index schedule monthly\n')
    os.chown(apt_sudoers,0,0);os.chmod(apt_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(apt_sudoers)],capture_output=True).returncode:
        apt_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS APT sudoers configuration')
    auto_service=Path('/etc/systemd/system/pinas-auto-updates.service')
    auto_service.write_text('[Unit]\nDescription=PiNAS scheduled OS updates\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=oneshot\nExecStart=/usr/local/libexec/pinas-apt-index automatic\nEnvironment=DEBIAN_FRONTEND=noninteractive\n')
    os.chown(auto_service,0,0);os.chmod(auto_service,0o644)
    # Existing schedule is preserved when upgrading PiNAS.
    # Generate a persistent per-install certificate; never replace it on upgrades.
    if not TLS_CERT.exists() or not TLS_KEY.exists():
        if TLS_CERT.exists() or TLS_KEY.exists():sys.exit('Incomplete TLS certificate pair; resolve manually before installing')
        if not shutil.which('openssl'):sys.exit('OpenSSL required for initial TLS certificate generation')
        hostname=load().get('hostname','pinas')
        if not valid_hostname(hostname):hostname='pinas'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','825',
            '-keyout',str(TLS_KEY),'-out',str(TLS_CERT),'-subj',f'/CN={hostname}.local',
            '-addext',f'subjectAltName=DNS:{hostname}.local,DNS:localhost,IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL)
    for f,mode in ((TLS_CERT,0o644),(TLS_KEY,0o600)):
        os.chown(f,0 if f==TLS_CERT else __import__('pwd').getpwnam('pinas').pw_uid,0 if f==TLS_CERT else __import__('grp').getgrnam('pinas').gr_gid)
        os.chmod(f,mode)
    bind_host='0.0.0.0' if args.lan else '127.0.0.1' 
    # TEMPORARY RC9.2: sudo inherits the service mount namespace. A root helper
    # cannot write /etc/passwd, /etc/group or Samba state with ProtectSystem=strict.
    # Replace sudo delegation with an independently sandboxed privileged service.
    service='''[Unit]\nDescription=PiNAS prototype web dashboard\nAfter=network.target\n[Service]\nType=simple\nUser=pinas\nGroup=pinas\nExecStart=/usr/bin/python3 /opt/pinas/pinas.py --serve --tls --host %s --port %d\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=false\nProtectSystem=false\nReadWritePaths=/var/lib/pinas\nPrivateTmp=true\n[Install]\nWantedBy=multi-user.target\n'''%(bind_host,args.port)
    Path('/etc/systemd/system/pinas.service').write_text(service)
    subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','enable','--now','pinas-hostname.path'],check=True);subprocess.run(['systemctl','start','pinas-hostname.service'],check=True);subprocess.run(['systemctl','enable','pinas.service'],check=True);subprocess.run(['systemctl','restart','pinas.service'],check=True)
    print(f'PiNAS installed. For localhost access: https://127.0.0.1:{args.port} (self-signed certificate)')
    if args.lan:print(f'LAN TLS MODE: open https://<PI-IP>:{args.port}. Certificate is self-signed; use the .local hostname for name matching. Do not expose this port to the internet.')
    else:print('Localhost-only mode; re-run installer with --lan to enable direct LAN access for testing.')

def main():
    ap=argparse.ArgumentParser(description='PiNAS Raspberry Pi NAS prototype')
    ap.add_argument('--lan',action='store_true',help='Bind HTTPS server to LAN interfaces');ap.add_argument('--install',action='store_true');ap.add_argument('--serve',action='store_true');ap.add_argument('--tls',action='store_true');ap.add_argument('--skip-packages',action='store_true');ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=8765)
    a=ap.parse_args()
    if a.install:install(a);return
    if a.serve:
        if a.host not in ('127.0.0.1','::1','0.0.0.0'):sys.exit('Unsupported bind address.')
        if a.host=='0.0.0.0' and not a.tls:sys.exit('LAN listening requires HTTPS (--tls)')
        server=ThreadingHTTPServer((a.host,a.port),Handler)
        if a.tls:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(TLS_CERT),str(TLS_KEY))
            server.socket=context.wrap_socket(server.socket,server_side=True)
        print('PiNAS running on %s://%s:%s'%('https' if a.tls else 'http',a.host,a.port))
        threading.Thread(target=cpu_sampler,daemon=True).start();server.serve_forever();return
    ap.print_help()
if __name__=='__main__':main(),'ipc
            name=data.get('name');password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):
                self.json({'error':'Invalid share name.'},400);return
            if not isinstance(password,str) or not verify(password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not any(isinstance(item,dict) and item.get('name')==name for item in nas_share_list()):
                self.json({'error':'Only PiNAS-managed shares can be removed.'},404);return
            try:delete_nas_share(name)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name,'files_preserved':True});return
        if path=='/api/nas-shares':
            name=data.get('name');volume=data.get('volume');access=data.get('access');admin_password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):
                self.json({'error':'Choose a share name of 1–32 letters, digits, spaces, underscores or hyphens.'},400);return
            if not isinstance(volume,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',volume) or '..' in volume:
                self.json({'error':'Invalid storage selection.'},400);return
            if not isinstance(access,dict) or not access or len(access)>64 or any(not isinstance(k,str) or v not in ('ro','rw') for k,v in access.items()):
                self.json({'error':'Assign at least one user Read Only or Read & Write access.'},400);return
            if not isinstance(admin_password,str) or not verify(admin_password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not storage_is_ready():self.json({'error':'A mounted, persistent data filesystem is required.'},409);return
            valid_users={u['name'] for u in nas_user_list()}
            if not set(access).issubset(valid_users):self.json({'error':'One or more users are not valid Samba accounts.'},409);return
            if any(name.casefold()==s.casefold() for s in discover().get('shares',[])):
                self.json({'error':'A share with this name already exists.'},409);return
            try:create_nas_share(name,volume,access)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name});return
        if path=='/api/logout':SESSIONS.pop(token,None);self.json({'ok':True},cookie='pinas_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'+('; Secure' if isinstance(self.connection,ssl.SSLSocket) else ''));return
        if path=='/api/settings':
            theme,accent,font=data.get('theme'),data.get('accent'),data.get('font')
            interval,history=data.get('cpu_interval',cfg.get('cpu_interval',5)),data.get('cpu_history',cfg.get('cpu_history',10))
            session_timeout=data.get('session_timeout',cfg.get('session_timeout',5))
            if theme not in ('light','dark','dark-cb','light-cb') or not isinstance(accent,str) or len(accent)!=7 or accent[0]!='#' or any(c not in '0123456789abcdefABCDEF' for c in accent[1:]) or type(font)!=int or font not in (10,12,14,16) or type(interval)!=int or interval not in (2,5,10) or type(history)!=int or history not in (10,15,30,60) or type(session_timeout)!=int or session_timeout not in (5,10,15,30,60):self.json({'error':'Invalid appearance settings'},400);return
            cfg.update(theme=theme,accent=accent,font=font,cpu_interval=interval,cpu_history=history,session_timeout=session_timeout)
        elif path=='/api/background':
            image=data.get('image')
            if not isinstance(image,str) or len(image)>2_900_000:self.json({'error':'Image too large'},400);return
            if image:
                try:
                    meta,b64=image.split(',',1);mime=meta[5:].split(';',1)[0]
                    if mime not in ('image/jpeg','image/png','image/webp'):raise ValueError()
                    decoded=base64.b64decode(b64,validate=True)
                    if len(decoded)>2*1024*1024:raise ValueError()
                    if not ((mime=='image/jpeg' and decoded.startswith(b'\xff\xd8\xff')) or (mime=='image/png' and decoded.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/webp' and decoded.startswith(b'RIFF') and decoded[8:12]==b'WEBP')):raise ValueError()
                except (ValueError,IndexError):self.json({'error':'Invalid image'},400);return
            cfg['login_background']=image
        save(cfg);self.json({'settings':dict({k:cfg.get(k) for k in ('theme','accent','font','cpu_interval','cpu_history','session_timeout')},has_background=bool(cfg.get('login_background')))} )

HOSTNAME_HELPER = r"""#!/usr/bin/env python3
import json, re, subprocess
from pathlib import Path
try:
    path=Path('/var/lib/pinas/config.json')
    if not path.exists():raise SystemExit(0)
    cfg=json.loads(path.read_text())
    hostname=cfg.get('hostname','')
    if not hostname:raise SystemExit(0)
    if not isinstance(hostname,str) or not 1<=len(hostname)<=63 or not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*',hostname):
        raise ValueError('Invalid hostname')
    current=subprocess.run(['hostname','-s'],capture_output=True,text=True,check=True).stdout.strip()
    if current!=hostname:
        subprocess.run(['/usr/bin/hostnamectl','set-hostname',hostname],check=True,timeout=15)
except (OSError,ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
    raise SystemExit('PiNAS hostname not applied: '+str(exc))
"""

NAS_USER_HELPER = r"""#!/usr/bin/env python3
# Privileged helper. No arbitrary command execution; narrowly scoped account actions.
import grp, json, os, pwd, re, subprocess, sys

def run(argv, **kwargs):
    return subprocess.run(argv, check=True, timeout=20, **kwargs)

def samba_users():
    p=run(['/usr/bin/pdbedit','-L'],capture_output=True,text=True)
    result=[]
    for line in p.stdout.splitlines():
        fields=line.split(':',2)
        if len(fields)>=2 and re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',fields[0]):
            result.append({'name':fields[0],'uid':fields[1]})
    return sorted(result,key=lambda x:x['name'])

if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit(2)
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(samba_users()))
        raise SystemExit(0)
    if len(sys.argv)!=3 or sys.argv[1] not in ('create','password'):raise SystemExit(2)
    name=sys.argv[2]
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',name) or name in ('pinas','root','admin','nobody'):raise SystemExit(2)
    password=sys.stdin.readline(258).rstrip('\n')
    if not 12<=len(password)<=256:raise SystemExit(2)
    if sys.argv[1]=='password':
        group=grp.getgrnam('pinas-nas')
        existing=pwd.getpwnam(name)
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin') or not any(u['name']==name for u in samba_users()):
            raise SystemExit('Not a managed PiNAS Samba user')
        run(['/usr/bin/smbpasswd','-s',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        raise SystemExit(0)
    try:
        group=grp.getgrnam('pinas-nas')
    except KeyError:
        run(['/usr/sbin/groupadd','pinas-nas'])
        group=grp.getgrnam('pinas-nas')
    created=False
    try:
        existing=pwd.getpwnam(name)
    except KeyError:
        existing=None
    if existing:
        # Repair only a partial PiNAS account from a previous failed attempt.
        # Never repurpose unrelated Linux accounts.
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):
            raise SystemExit('Linux account already exists and is not a PiNAS NAS account; choose another username')
        if any(u['name']==name for u in samba_users()):
            raise SystemExit('Samba account already exists; refresh the Users page')
    else:
        run(['/usr/sbin/useradd','--no-create-home','--shell','/usr/sbin/nologin','--gid','pinas-nas',name])
        created=True
    try:
        run(['/usr/bin/smbpasswd','-s','-a',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        run(['/usr/bin/smbpasswd','-e',name],capture_output=True)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        if created:subprocess.run(['/usr/sbin/userdel',name],check=False,timeout=10)
        raise SystemExit('Samba account creation failed: '+str(exc))
"""

NAS_SHARE_HELPER = r"""#!/usr/bin/env python3
# Root-only share broker. Strict input validation and independent mount checks.
import json, os, pathlib, pwd, re, subprocess, sys, tempfile

DB=pathlib.Path('/var/lib/pinas/shares.json')
CONF=pathlib.Path('/etc/samba/pinas-shares.conf')
SMB=pathlib.Path('/etc/samba/smb.conf')

def run(cmd, **kw):
    return subprocess.run(cmd,check=True,timeout=15,capture_output=True,text=True,**kw)

def read_db():
    try:
        value=json.loads(DB.read_text())
        return value if isinstance(value,list) else []
    except (OSError,ValueError):return []

def atomic(path,content,mode=0o600):
    fd,name=tempfile.mkstemp(prefix='.pinas-',dir=str(path.parent))
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'w') as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def check_volume(device):
    if not isinstance(device,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',device) or '..' in device:raise ValueError('Invalid device')
    # Device must be a block device with an approved filesystem.
    p=pathlib.Path(device)
    if not p.is_block_device():raise ValueError('Selected storage is not a block device')
    fs=run(['/usr/bin/lsblk','-n','-o','FSTYPE',device]).stdout.strip().splitlines()
    if not fs or fs[0].strip().lower() not in ('ext4','xfs','btrfs'):raise ValueError('Unsupported filesystem')
    target=run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device]).stdout.strip().splitlines()
    if len(target)!=1:raise ValueError('Disk must have one unambiguous active mount')
    mount=pathlib.Path(target[0]).resolve(strict=True)
    if str(mount) in ('/','/boot','/boot/firmware') or any(str(mount).startswith(prefix) for prefix in ('/etc/','/var/','/usr/','/home/','/opt/','/root/','/proc/','/sys/','/run/')):
        raise ValueError('System storage cannot host NAS shares')
    if not mount.is_dir() or mount.is_symlink():raise ValueError('Invalid mount directory')
    # Confirm mounted persistently via UUID, path or LABEL; do not trust browser data.
    uuid=run(['/usr/sbin/blkid','-s','UUID','-o','value',device]).stdout.strip()
    entries=[line.split() for line in pathlib.Path('/etc/fstab').read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not any(len(e)>=2 and e[1]==str(mount) and e[0] in (device,'UUID='+uuid,'/dev/disk/by-uuid/'+uuid) for e in entries):
        raise ValueError('Disk is not persistently configured in fstab')
    # Reject root device even when mounted at a second location.
    rootdev=run(['/usr/bin/findmnt','-n','-o','SOURCE','/']).stdout.strip()
    if rootdev.startswith('/dev/'):
        rootparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',rootdev]).stdout.split())
        selectedparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',device]).stdout.split())
        if rootparents & selectedparents:raise ValueError('Operating system disk is protected')
    return mount

def main():
    if os.geteuid()!=0:raise ValueError('Root helper required')
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(read_db()));return
    if len(sys.argv)==2 and sys.argv[1]=='delete':
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('Request too large')
        request=json.loads(raw);name=request.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):raise ValueError('Invalid share name')
        current=read_db()
        matches=[item for item in current if isinstance(item,dict) and item.get('name')==name]
        if len(matches)!=1:raise ValueError('Share is not managed by PiNAS')
        oldconf=CONF.read_text()
        # Match only a complete, exact managed Samba section; never touch unrelated shares.
        section=re.compile(r'(?m)^\['+re.escape(name)+r'\][ \t]*\n(?:(?!\[).*(?:\n|$))*')
        found=list(section.finditer(oldconf))
        if len(found)!=1:raise ValueError('Managed Samba share section missing or ambiguous')
        updated=oldconf[:found[0].start()]+oldconf[found[0].end():]
        olddb=DB.read_text()
        try:
            atomic(CONF,updated,0o644)
            run(['/usr/bin/testparm','-s'])
            run(['/usr/bin/systemctl','reload','smbd'])
            atomic(DB,json.dumps([item for item in current if not (isinstance(item,dict) and item.get('name')==name)],indent=2),0o600)
        except Exception:
            atomic(CONF,oldconf,0o644)
            atomic(DB,olddb,0o600)
            try:run(['/usr/bin/systemctl','reload','smbd'])
            except Exception:pass
            raise
        # Deliberately leave the share directory, ACLs and files untouched.
        print(json.dumps({'ok':True,'files_preserved':True}));return
    if len(sys.argv)!=2 or sys.argv[1]!='create':raise ValueError('Unsupported action')
    raw=sys.stdin.read(8193)
    if len(raw)>8192:raise ValueError('Request too large')
    request=json.loads(raw)
    name=request.get('name');access=request.get('access');device=request.get('volume')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):raise ValueError('Invalid share name')
    if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):raise ValueError('Invalid access policy')
    # Verify users exist in Samba and Linux before creating any directory.
    samba={line.split(':',1)[0] for line in run(['/usr/bin/pdbedit','-L']).stdout.splitlines()}
    for user in access:
        if user not in samba:raise ValueError('Samba account not found: '+user)
        pwd.getpwnam(user)
    mount=check_volume(device)
    current=read_db()
    if any(item.get('name','').casefold()==name.casefold() for item in current):raise ValueError('Share already exists')
    # Samba's own configuration may include external shares; reject collisions.
    existing=run(['/usr/bin/testparm','-s']).stdout
    if any(line.strip().casefold()=='['+name.casefold()+']' for line in existing.splitlines()):raise ValueError('Share name already used by Samba')
    # No preexisting folder is ever adopted or modified by this operation.
    root=mount/'PiNAS Shares'
    if root.is_symlink():raise ValueError('Unsafe share root')
    root.mkdir(mode=0o711,exist_ok=True)
    if root.stat().st_uid!=0 or (root.stat().st_mode & 0o022):raise ValueError('Share root must be root-owned and not group/world writable')
    folder=root/name
    if folder.exists() or folder.is_symlink():raise ValueError('Folder already exists; choose a different name')
    if not pathlib.Path('/usr/bin/setfacl').exists():raise ValueError('POSIX ACL tools are required (install acl)')
    # Validate smb.conf can be managed before changing filesystem.
    original=SMB.read_text()
    include='   include = /etc/samba/pinas-shares.conf'
    if include not in original:
        if not re.search(r'(?im)^\s*\[global\]\s*$',original):raise ValueError('Samba [global] section missing')
        amended=re.sub(r'(?im)^(\s*\[global\]\s*)$',r'\1\n'+include,original,count=1)
    else:amended=original
    # Explicit per-user access; default deny for other NAS accounts.
    ro=[u for u,p in access.items() if p=='ro'];rw=[u for u,p in access.items() if p=='rw']
    stanza='\n['+name+']\n   path = '+str(folder)+'\n   browseable = yes\n   guest ok = no\n   read only = yes\n   valid users = '+', '.join(access)+'\n'
    if rw:stanza+='   write list = '+', '.join(rw)+'\n'
    stanza+='   create mask = 0660\n   directory mask = 0770\n   follow symlinks = no\n   wide links = no\n'
    oldconf=CONF.read_text() if CONF.exists() else ''
    if '['+name+']' in oldconf:raise ValueError('Duplicate managed share')
    folder.mkdir(mode=0o700)
    try:
        # Root-owned folder; Samba creates files as authenticated Unix users.
        os.chown(folder,0,0)
        os.chmod(folder,0o700)
        acl=['u::rwx','g::---','o::---','m::rwx']+[f'u:{u}:'+('rwx' if p=='rw' else 'r-x') for u,p in access.items()]
        default=['d:'+entry for entry in acl]
        run(['/usr/bin/setfacl','-m',','.join(acl+default),str(folder)])
        if amended!=original:atomic(SMB,amended,0o644)
        atomic(CONF,oldconf+stanza,0o644)
        run(['/usr/bin/testparm','-s'])
        run(['/usr/bin/systemctl','reload','smbd'])
        current.append({'name':name,'volume_label':mount.name,'volume':device,'access':access})
        atomic(DB,json.dumps(current,indent=2),0o600)
    except Exception:
        atomic(CONF,oldconf,0o644)
        if amended!=original:atomic(SMB,original,0o644)
        try:run(['/usr/bin/systemctl','reload','smbd'])
        except Exception:pass
        try:folder.rmdir()
        except OSError:pass
        raise
    print(json.dumps({'ok':True,'name':name}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

NAS_FILES_HELPER = r"""#!/usr/bin/env python3
# Privileged, narrow file broker. Authentication against Samba passdb; filesystem
# operations executed as the NAS user's actual UID/GID and supplementary groups.
import base64, hashlib, hmac, json, os, pathlib, pwd, re, stat, subprocess, sys
DB=pathlib.Path('/var/lib/pinas/shares.json')
def md4(message):
    # NT hash is MD4(UTF-16LE password). Samba uses NT hashes for SMB auth.
    import struct
    original=len(message);message+=b'\x80';message+=b'\0'*((56-len(message)%64)%64)+struct.pack('<Q',original*8)
    a,b,c,d=0x67452301,0xefcdab89,0x98badcfe,0x10325476
    def rol(v,n):return ((v<<n)|(v>>(32-n)))&0xffffffff
    for offset in range(0,len(message),64):
        x=struct.unpack('<16I',message[offset:offset+64]);aa,bb,cc,dd=a,b,c,d
        for j in range(48):
            if j<16:f=(b&c)|(~b&d);k=j;shift=[3,7,11,19][j%4];constant=0
            elif j<32:f=(b&c)|(b&d)|(c&d);k=(j%4)*4+j//4-4;shift=[3,5,9,13][j%4];constant=0x5a827999
            else:f=b^c^d;k=[0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15][j-32];shift=[3,9,11,15][j%4];constant=0x6ed9eba1
            value=rol((a+f+x[k]+constant)&0xffffffff,shift);a,b,c,d=d,value,b,c
        a=(a+aa)&0xffffffff;b=(b+bb)&0xffffffff;c=(c+cc)&0xffffffff;d=(d+dd)&0xffffffff
    return struct.pack('<4I',a,b,c,d).hex().upper()
def samba_hash(user):
    p=subprocess.run(['/usr/bin/pdbedit','-Lw',user],capture_output=True,text=True,timeout=8)
    if p.returncode:raise ValueError('Unknown NAS account')
    for line in p.stdout.splitlines():
        fields=line.split(':')
        if len(fields)>4 and fields[0]==user and re.fullmatch('[A-Fa-f0-9]{32}',fields[3]):return fields[3].upper()
    raise ValueError('NAS account has no valid Samba password')
def valid_user(user):
    if not isinstance(user,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',user):raise ValueError('Invalid user')
    person=pwd.getpwnam(user)
    if person.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):raise ValueError('Not a PiNAS NAS user')
    if samba_hash(user)=='':raise ValueError('Not a Samba user')
    return person
def shares_for(user):
    entries=json.loads(DB.read_text())
    return [s for s in entries if isinstance(s,dict) and s.get('access',{}).get(user) in ('ro','rw')]
def drop(person):
    os.initgroups(person.pw_name,person.pw_gid);os.setgid(person.pw_gid);os.setuid(person.pw_uid)
def safe_path(root,relative):
    if not isinstance(relative,str) or len(relative)>1000 or relative.startswith('/') or '\\' in relative or '\x00' in relative:raise ValueError('Invalid path')
    parts=relative.split('/') if relative else []
    if any(x in ('','.','..') or x.startswith('.pinas-upload-') for x in parts):raise ValueError('Invalid path')
    # Reject symlinks at every level, including the leaf. Never follow them.
    cur=root
    for part in parts:
        cur=cur/part
        if cur.is_symlink():raise ValueError('Symbolic links are not accessible')
    if not cur.resolve(strict=False).is_relative_to(root.resolve(strict=True)):raise ValueError('Path outside share')
    return cur
def main():
    if os.geteuid()!=0:raise ValueError('Root required')
    raw=sys.stdin.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise ValueError('Request too large')
    q=json.loads(raw);action=q.get('action');user=q.get('username');person=valid_user(user)
    if action=='authenticate':
        password=q.get('password')
        if not isinstance(password,str) or len(password)>256:raise ValueError('Invalid password')
        print('true' if hmac.compare_digest(md4(password.encode('utf-16le')),samba_hash(user)) else 'false');return
    allowed=shares_for(user)
    if action=='shares':
        print(json.dumps({'shares':[{'name':s['name'],'read_only':s['access'][user]=='ro'} for s in allowed]}));return
    share=q.get('share');s=next((x for x in allowed if x['name']==share),None)
    if s is None:raise ValueError('Share not accessible')
    # Root path derived exclusively from privileged share metadata, not browser paths.
    root=pathlib.Path(s['volume_label']) if False else None
    # Resolve mount from device, and confirm it is still the same mounted filesystem.
    device=s['volume'];p=subprocess.run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device],capture_output=True,text=True,timeout=5)
    targets=p.stdout.strip().splitlines()
    if p.returncode or len(targets)!=1:raise ValueError('Share storage is offline')
    mount=pathlib.Path(targets[0]).resolve(strict=True)
    if str(mount)=='/' or str(mount).startswith(('/etc/','/var/','/usr/','/home/','/boot/')):raise ValueError('Protected mount')
    root=mount/'PiNAS Shares'/s['name']
    if root.is_symlink() or not root.is_dir():raise ValueError('Share folder unavailable')
    relative=q.get('path','');target=safe_path(root,relative)
    writable=s['access'][user]=='rw'
    if action in ('mkdir','delete','rename','move','copy','upload','upload_start','upload_chunk','upload_finish','upload_cancel') and not writable:raise ValueError('Read-only share')
    drop(person)
    # All operations below run with the NAS user's UID/GID. Uploads are staged
    # in the destination directory, then published by an atomic rename.
    def valid_name(name):
        if not isinstance(name,str) or not name or len(name)>255 or name in ('.','..') or '/' in name or '\\' in name or '\x00' in name or name.startswith('.pinas-upload-'):raise ValueError('Invalid file name')
        return name
    def destination(relative):
        dest=safe_path(root,relative)
        if dest==root or dest.exists() or dest.is_symlink():raise ValueError('Destination already exists')
        if not dest.parent.is_dir():raise ValueError('Destination folder does not exist')
        return dest
    if action in ('rename','move','copy'):
        if target==root or not target.exists():raise ValueError('Invalid source')
        if action=='rename':
            dest=destination('/'.join(filter(None,[relative.rsplit('/',1)[0] if '/' in relative else '',valid_name(q.get('name'))])))
        else:
            dest=destination(q.get('dest',''))
        if target.is_dir() and (dest==target or target in dest.parents):raise ValueError('Cannot place folder inside itself')
        if action=='copy':
            import shutil
            if target.is_dir():
                # Reject links anywhere in the tree and cap total copy size.
                total=0
                for directory,dirs,files in os.walk(target,followlinks=False):
                    for name in dirs+files:
                        node=pathlib.Path(directory)/name
                        if node.is_symlink():raise ValueError('Symbolic links cannot be copied')
                        if node.is_file():total+=node.stat().st_size
                        if total>8*1024**3:raise ValueError('Folder copy exceeds 8 GiB safety limit')
                shutil.copytree(target,dest,symlinks=False)
            elif target.is_file():
                with target.open('rb') as src, dest.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            else:raise ValueError('Unsupported file type')
        else:
            # Same-share only; atomic rename prevents partial moves.
            if target.is_file():
                os.link(target,dest,follow_symlinks=False);target.unlink()
            else:target.rename(dest)
        print('{"ok":true}');return
    if action=='upload_start':
        name=valid_name(q.get('name'))
        if not target.is_dir():raise ValueError('Not a folder')
        destination('/'.join(filter(None,[relative,name])))
        size=q.get('size')
        if not isinstance(size,int) or size<0 or size>100*1024**3:raise ValueError('Invalid upload size')
        import secrets
        token=secrets.token_hex(20)
        staging=target/('.pinas-upload-'+token)
        fd=os.open(staging,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        meta=target/('.pinas-upload-'+token+'.json')
        fd=os.open(meta,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'name':name,'size':size,'path':relative},f)
        print(json.dumps({'token':token}));return
    if action in ('upload_chunk','upload_finish','upload_cancel'):
        token=q.get('token','')
        if not isinstance(token,str) or not re.fullmatch('[0-9a-f]{40}',token):raise ValueError('Invalid transfer token')
        stage=target/('.pinas-upload-'+token)
        meta=target/('.pinas-upload-'+token+'.json')
        if stage.is_symlink() or meta.is_symlink() or not stage.is_file() or not meta.is_file():raise ValueError('Unknown transfer')
        details=json.loads(meta.read_text());name=valid_name(details['name']);size=details['size']
        if details.get('path')!=relative:raise ValueError('Transfer location mismatch')
        if action=='upload_cancel':stage.unlink();meta.unlink();print('{"ok":true}');return
        if action=='upload_chunk':
            content=q.get('content','');offset=q.get('offset')
            if not isinstance(content,str) or len(content)>700000 or not isinstance(offset,int):raise ValueError('Invalid chunk')
            payload=base64.b64decode(content,validate=True)
            if len(payload)>512*1024 or offset!=stage.stat().st_size or offset+len(payload)>size:raise ValueError('Chunk offset or size mismatch')
            with stage.open('ab') as f:f.write(payload)
            print(json.dumps({'offset':offset+len(payload)}));return
        if stage.stat().st_size!=size:raise ValueError('Upload incomplete')
        dest=destination('/'.join(filter(None,[relative,name])))
        # Hard-link is no-clobber and atomic on the same filesystem.
        os.link(stage,dest,follow_symlinks=False);stage.unlink();meta.unlink()
        print('{"ok":true}');return
    if action=='download_chunk':
        offset=q.get('offset');size=q.get('size')
        if not isinstance(offset,int) or offset<0 or not isinstance(size,int) or size<1 or size>512*1024:raise ValueError('Invalid download range')
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode):raise ValueError('Not a regular file')
        total=target.stat().st_size
        with target.open('rb') as f:f.seek(offset);chunk=f.read(size)
        print(json.dumps({'content':base64.b64encode(chunk).decode(),'total':total}));return
    if action=='list':
        if not target.is_dir():raise ValueError('Not a folder')
        entries=[]
        for child in sorted(target.iterdir(),key=lambda x:x.name.casefold()):
            if child.is_symlink() or child.name.startswith('.pinas-upload-'):continue
            try:st=child.stat()
            except OSError:continue
            if stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode):entries.append({'name':child.name,'dir':stat.S_ISDIR(st.st_mode),'size':st.st_size})
            if len(entries)>=1000:break
        print(json.dumps({'entries':entries}));return
    if action=='mkdir':
        name=q.get('name','');dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..'):raise ValueError('Invalid folder name')
        dest.mkdir(mode=0o770);print('{"ok":true}');return
    if action=='delete':
        if target==root:raise ValueError('Cannot delete share root')
        if target.is_dir():target.rmdir()
        elif target.is_file():target.unlink()
        else:raise ValueError('Not a regular file or empty folder')
        print('{"ok":true}');return
    if action=='download':
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode) or target.stat().st_size>3*1024*1024:raise ValueError('Only files up to 3 MB supported in this test build')
        with target.open('rb') as f:content=base64.b64encode(f.read()).decode()
        print(json.dumps({'content':content}));return
    if action=='upload':
        name=q.get('name','');content=q.get('content','')
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..') or not isinstance(content,str) or len(content)>4*1024*1024+16:raise ValueError('Invalid upload')
        dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not target.is_dir():raise ValueError('Not a directory')
        payload=base64.b64decode(content,validate=True)
        if len(payload)>3*1024*1024:raise ValueError('Upload exceeds 3 MB')
        fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o660)
        with os.fdopen(fd,'wb') as f:f.write(payload)
        print('{"ok":true}');return
    raise ValueError('Unsupported action')
if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
"""

APT_INDEX_HELPER = r"""#!/usr/bin/env python3
import os,subprocess,sys
from pathlib import Path
ALLOWED={'off':None,'daily':'*-*-* 01:00:00','weekly':'Fri *-*-* 01:00:00','monthly':'*-*-28 01:00:00'}
def run(cmd,timeout=30):
    p=subprocess.run(cmd,timeout=timeout,check=False)
    if p.returncode:sys.exit(p.returncode)
def main():
    if os.geteuid()!=0:sys.exit('Root access required')
    args=sys.argv[1:]
    if len(args)==2 and args[0]=='schedule' and args[1] in ALLOWED:
        schedule=args[1];calendar=ALLOWED[schedule]
        timer=Path('/etc/systemd/system/pinas-auto-updates.timer')
        if calendar:
            timer.write_text('[Unit]\nDescription=PiNAS automatic OS updates\n[Timer]\nOnCalendar='+calendar+'\nPersistent=true\nUnit=pinas-auto-updates.service\n[Install]\nWantedBy=timers.target\n')
        run(['systemctl','daemon-reload'])
        if calendar:
            run(['systemctl','enable','--now','pinas-auto-updates.timer'])
            run(['systemctl','restart','pinas-auto-updates.timer'])
        else:
            run(['systemctl','disable','--now','pinas-auto-updates.timer']) if timer.exists() else None
            timer.unlink(missing_ok=True)
            run(['systemctl','daemon-reload'])
        marker=Path('/var/lib/pinas/update-schedule');marker.write_text(schedule+'\n');os.chmod(marker,0o644)
        return
    if args==['automatic']:
        # Only the systemd oneshot invokes this command, not the web service account.
        run(['/usr/bin/apt-get','update'],210)
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
        return
    if args==['upgrade']:
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
    elif args==['refresh']:
        run(['/usr/bin/apt-get','update'],210)
    else:sys.exit('Unsupported operation')
if __name__=='__main__':main()
"""

NAS_STORAGE_HELPER='#!/usr/bin/env python3\n"""PiNAS RC13 restricted, non-destructive storage adoption helper."""\nimport json,os,pathlib,re,subprocess,sys,uuid\nfrom pathlib import Path\n\ndef run(*args,timeout=15):\n    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)\n    if p.returncode:raise ValueError((p.stderr or \'Storage command failed\').strip()[-500:])\n    return p.stdout.strip()\n\ndef main():\n    if os.geteuid()!=0 or sys.argv[1:]!=[\'adopt\']:raise ValueError(\'Unsupported storage operation\')\n    data=json.loads(sys.stdin.read(4096));device=data.get(\'device\')\n    if not isinstance(device,str) or not re.fullmatch(r\'/dev/[A-Za-z0-9_./-]{1,90}\',device) or \'..\' in device:raise ValueError(\'Invalid device\')\n    path=Path(device)\n    if not path.is_block_device():raise ValueError(\'Device is not a block device\')\n    # The privileged helper independently identifies eligible physical disks.\n    roots=json.loads(run(\'lsblk\',\'-J\',\'-b\',\'-o\',\'NAME,PATH,TYPE,FSTYPE,UUID,MOUNTPOINTS,RO,PKNAME\')).get(\'blockdevices\',[])\n    bypath={};byname={};parents={}\n    def walk(node,parent=None):\n        name=node.get(\'name\');bypath[node.get(\'path\')]=node;byname[name]=node\n        if parent:parents[name]=parent\n        for child in node.get(\'children\') or []:walk(child,name)\n    for root in roots:walk(root)\n    node=bypath.get(str(path.resolve())) or bypath.get(device)\n    if not node or node.get(\'type\') not in (\'part\',\'disk\') or node.get(\'ro\'):raise ValueError(\'Not an eligible writable disk or partition\')\n    def root_for(n):\n        seen=set()\n        while n.get(\'name\') in parents:\n            if n[\'name\'] in seen:raise ValueError(\'Invalid device topology\')\n            seen.add(n[\'name\']);n=byname[parents[n[\'name\']]]\n        return n\n    disk=root_for(node)\n    if disk.get(\'type\')!=\'disk\' or disk.get(\'ro\') or str(disk.get(\'name\',\'\')).startswith((\'loop\',\'zram\',\'ram\',\'nbd\',\'sr\',\'fd\')):raise ValueError(\'Unsupported backing device\')\n    # Reject any physical disk carrying the root or boot filesystems.\n    protected={\'/\',\'/boot\',\'/boot/firmware\',\'/boot/efi\'}\n    def contains_system(n):\n        if any(m in protected for m in (n.get(\'mountpoints\') or []) if m):return True\n        return any(contains_system(c) for c in n.get(\'children\') or [])\n    if contains_system(disk):raise ValueError(\'Operating system storage is protected\')\n    for mount in protected:\n        src=run(\'findmnt\',\'-n\',\'-o\',\'SOURCE\',\'--target\',mount).split(\'[\',1)[0]\n        if src and src in bypath and root_for(bypath[src]).get(\'name\')==disk.get(\'name\'):\n            raise ValueError(\'Operating system storage is protected\')\n    fs=run(\'blkid\',\'-s\',\'TYPE\',\'-o\',\'value\',device)\n    uid=run(\'blkid\',\'-s\',\'UUID\',\'-o\',\'value\',device)\n    if fs not in (\'ext4\',\'xfs\',\'btrfs\') or not re.fullmatch(r\'[A-Za-z0-9-]{8,64}\',uid):raise ValueError(\'Supported filesystem and UUID required\')\n    # Reject RAID/LVM/crypto members and nested volume layouts.\n    if node.get(\'type\')==\'disk\' and node.get(\'children\'):raise ValueError(\'Choose a filesystem partition, not its parent disk\')\n    if node.get(\'children\'):raise ValueError(\'Complex volume layout not supported\')\n    mountpoints=[m for m in node.get(\'mountpoints\') or [] if m]\n    if len(mountpoints)>1:raise ValueError(\'Multiple mountpoints require manual review\')\n    if mountpoints and not str(mountpoints[0]).startswith(\'/mnt/pinas/\'):\n        raise ValueError(\'Filesystem is already mounted elsewhere; manage it manually to avoid disrupting applications\')\n    target=Path(\'/mnt/pinas\')/uid\n    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir())) and str(target) not in mountpoints):raise ValueError(\'Mount destination is not empty\')\n    fstab=Path(\'/etc/fstab\');original=fstab.read_text();entries=[line.split() for line in original.splitlines() if line.strip() and not line.lstrip().startswith(\'#\')]\n    for e in entries:\n        if len(e)>=2 and (e[0] in (device,\'UUID=\'+uid,\'/dev/disk/by-uuid/\'+uid) or e[1]==str(target)):\n            if e[0]==\'UUID=\'+uid and e[1]==str(target):\n                if str(target) not in mountpoints:run(\'mount\',str(target),timeout=25)\n                print(json.dumps({\'ok\':True,\'mount\':str(target),\'existing\':True}));return\n            raise ValueError(\'Existing fstab configuration requires manual review\')\n    target.parent.mkdir(parents=True,exist_ok=True)\n    target.mkdir(mode=0o755,exist_ok=True)\n    options=\'defaults,nofail,noatime,x-systemd.device-timeout=10s\'\n    entry=f\'UUID={uid} {target} {fs} {options} 0 {2 if fs=="ext4" else 0} # PiNAS managed\\\\n\'\n    entry=entry.replace(\'\\\\n\',\'\\n\')\n    backup=fstab.with_name(\'fstab.pinas-\'+uuid.uuid4().hex[:12]+\'.bak\')\n    backup.write_text(original);os.chmod(backup,0o600)\n    temp=fstab.with_name(\'.fstab.pinas-\'+uuid.uuid4().hex)\n    try:\n        temp.write_text(original.rstrip(\'\\n\')+\'\\n\'+entry);os.chmod(temp,0o644)\n        os.replace(temp,fstab)\n        run(\'systemctl\',\'daemon-reload\',timeout=15)\n        run(\'mount\',str(target),timeout=25)\n        actual=run(\'findmnt\',\'-n\',\'-o\',\'UUID\',\'--target\',str(target))\n        if actual!=uid:raise ValueError(\'Mounted filesystem UUID verification failed\')\n    except Exception:\n        fstab.write_text(original)\n        try:run(\'systemctl\',\'daemon-reload\')\n        except Exception:pass\n        raise\n    print(json.dumps({\'ok\':True,\'mount\':str(target)}))\nif __name__==\'__main__\':\n    try:main()\n    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)\n'

SMART_HEALTH_HELPER = """#!/usr/bin/env python3
import json,os,shutil,subprocess,sys
from pathlib import Path
def main():
    if os.geteuid()!=0 or len(sys.argv)!=1:
        raise ValueError('Unsupported operation')
    smartctl=shutil.which('smartctl')
    if not smartctl:
        print(json.dumps({'installed':False,'drives':[]}));return
    p=subprocess.run(['lsblk','-J','-b','-o','NAME,PATH,TYPE,MODEL,TRAN'],capture_output=True,text=True,timeout=8,check=True)
    drives=[]
    for disk in json.loads(p.stdout).get('blockdevices',[]):
        if disk.get('type')!='disk':continue
        device=disk.get('path','')
        if not isinstance(device,str) or not device.startswith('/dev/') or not Path(device).is_block_device():continue
        if disk.get('name','').startswith(('loop','zram','ram','nbd','sr','fd')):continue
        entry={'device':device,'model':disk.get('model') or disk.get('name'),'status':'Unavailable','temperature':None}
        try:
            result=subprocess.run([smartctl,'-j','-H','-A',device],capture_output=True,text=True,timeout=12)
            data=json.loads(result.stdout)
            health=data.get('smart_status',{}).get('passed')
            if health is True:entry['status']='Healthy'
            elif health is False:entry['status']='Warning'
            temp=data.get('temperature',{}).get('current')
            if isinstance(temp,(int,float)) and -20<=temp<=120:entry['temperature']=temp
            if data.get('smart_support',{}).get('available') is False:entry['status']='Unsupported'
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        drives.append(entry)
    print(json.dumps({'installed':True,'drives':drives}))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

def install(args):
    if sys.platform!='linux' or os.geteuid()!=0:sys.exit('Install requires Linux and sudo/root.')
    if not Path('/etc/os-release').exists():sys.exit('Unsupported OS')
    osinfo=read('/etc/os-release')
    if 'debian' not in osinfo.lower() and 'raspbian' not in osinfo.lower():sys.exit('Requires Raspberry Pi OS / Debian family')
    if not args.skip_packages:
        print('Installing NAS dependencies (requires network and may take time)...',flush=True)
        subprocess.run(['apt-get','update'],check=True)
        subprocess.run(['apt-get','install','-y','samba','xfsprogs','btrfs-progs','mdadm','parted','util-linux','e2fsprogs','avahi-daemon','acl','openssl'],check=True)
    target=Path('/opt/pinas');target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(__file__).resolve(),target/'pinas.py');os.chmod(target/'pinas.py',0o755)
    if subprocess.run(['id','-u','pinas'],capture_output=True).returncode!=0:
        subprocess.run(['useradd','--system','--home-dir','/var/lib/pinas','--shell','/usr/sbin/nologin','pinas'],check=True)
    DATA.mkdir(parents=True,exist_ok=True);os.chmod(DATA,0o700)
    subprocess.run(['chown','pinas:pinas',str(DATA)],check=True)
    helper=Path('/usr/local/libexec/pinas-apply-hostname')
    helper.parent.mkdir(parents=True,exist_ok=True)
    helper.write_text(HOSTNAME_HELPER)
    os.chmod(helper,0o755)
    unit='''[Unit]\nDescription=Apply validated PiNAS device hostname\nAfter=systemd-hostnamed.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /usr/local/libexec/pinas-apply-hostname\nNoNewPrivileges=true\nProtectHome=true\nPrivateTmp=true\n'''
    Path('/etc/systemd/system/pinas-hostname.service').write_text(unit)
    path_unit='''[Unit]\nDescription=Apply PiNAS hostname when configuration changes\n[Path]\nPathChanged=/var/lib/pinas/config.json\nUnit=pinas-hostname.service\n[Install]\nWantedBy=multi-user.target\n'''
    Path('/etc/systemd/system/pinas-hostname.path').write_text(path_unit)
    user_helper=Path('/usr/local/libexec/pinas-nas-user')
    user_helper.write_text(NAS_USER_HELPER)
    os.chown(user_helper,0,0);os.chmod(user_helper,0o700)
    sudoers=Path('/etc/sudoers.d/pinas-nas-user')
    sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-user create *, /usr/local/libexec/pinas-nas-user password *, /usr/local/libexec/pinas-nas-user list\n')
    os.chown(sudoers,0,0);os.chmod(sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(sudoers)],capture_output=True).returncode:
        sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS sudoers configuration')
    share_helper=Path('/usr/local/libexec/pinas-nas-share')
    share_helper.write_text(NAS_SHARE_HELPER)
    os.chown(share_helper,0,0);os.chmod(share_helper,0o700)
    share_sudoers=Path('/etc/sudoers.d/pinas-nas-share')
    share_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-share list, /usr/local/libexec/pinas-nas-share create\n')
    os.chown(share_sudoers,0,0);os.chmod(share_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(share_sudoers)],capture_output=True).returncode:
        share_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS share sudoers configuration')
    files_helper=Path('/usr/local/libexec/pinas-nas-files')
    files_helper.write_text(NAS_FILES_HELPER)
    os.chown(files_helper,0,0);os.chmod(files_helper,0o700)
    files_sudoers=Path('/etc/sudoers.d/pinas-nas-files')
    files_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-files\n')
    os.chown(files_sudoers,0,0);os.chmod(files_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(files_sudoers)],capture_output=True).returncode:
        files_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS file helper sudoers configuration')
    storage_helper=Path('/usr/local/libexec/pinas-nas-storage')
    storage_helper.write_text(NAS_STORAGE_HELPER)
    os.chown(storage_helper,0,0);os.chmod(storage_helper,0o700)
    storage_sudoers=Path('/etc/sudoers.d/pinas-nas-storage')
    storage_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-storage adopt\n')
    os.chown(storage_sudoers,0,0);os.chmod(storage_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(storage_sudoers)],capture_output=True).returncode:
        storage_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS storage sudoers configuration')
    smart_helper=Path('/usr/local/libexec/pinas-smart-health')
    smart_helper.write_text(SMART_HEALTH_HELPER)
    os.chown(smart_helper,0,0);os.chmod(smart_helper,0o700)
    smart_sudoers=Path('/etc/sudoers.d/pinas-smart-health')
    smart_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-smart-health\n')
    os.chown(smart_sudoers,0,0);os.chmod(smart_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(smart_sudoers)],capture_output=True).returncode:
        smart_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS SMART sudoers configuration')
    apt_helper=Path('/usr/local/libexec/pinas-apt-index')
    apt_helper.write_text(APT_INDEX_HELPER)
    os.chown(apt_helper,0,0);os.chmod(apt_helper,0o700)
    apt_sudoers=Path('/etc/sudoers.d/pinas-apt-index')
    apt_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-apt-index refresh, /usr/local/libexec/pinas-apt-index upgrade, /usr/local/libexec/pinas-apt-index schedule off, /usr/local/libexec/pinas-apt-index schedule daily, /usr/local/libexec/pinas-apt-index schedule weekly, /usr/local/libexec/pinas-apt-index schedule monthly\n')
    os.chown(apt_sudoers,0,0);os.chmod(apt_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(apt_sudoers)],capture_output=True).returncode:
        apt_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS APT sudoers configuration')
    auto_service=Path('/etc/systemd/system/pinas-auto-updates.service')
    auto_service.write_text('[Unit]\nDescription=PiNAS scheduled OS updates\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=oneshot\nExecStart=/usr/local/libexec/pinas-apt-index automatic\nEnvironment=DEBIAN_FRONTEND=noninteractive\n')
    os.chown(auto_service,0,0);os.chmod(auto_service,0o644)
    # Existing schedule is preserved when upgrading PiNAS.
    # Generate a persistent per-install certificate; never replace it on upgrades.
    if not TLS_CERT.exists() or not TLS_KEY.exists():
        if TLS_CERT.exists() or TLS_KEY.exists():sys.exit('Incomplete TLS certificate pair; resolve manually before installing')
        if not shutil.which('openssl'):sys.exit('OpenSSL required for initial TLS certificate generation')
        hostname=load().get('hostname','pinas')
        if not valid_hostname(hostname):hostname='pinas'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','825',
            '-keyout',str(TLS_KEY),'-out',str(TLS_CERT),'-subj',f'/CN={hostname}.local',
            '-addext',f'subjectAltName=DNS:{hostname}.local,DNS:localhost,IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL)
    for f,mode in ((TLS_CERT,0o644),(TLS_KEY,0o600)):
        os.chown(f,0 if f==TLS_CERT else __import__('pwd').getpwnam('pinas').pw_uid,0 if f==TLS_CERT else __import__('grp').getgrnam('pinas').gr_gid)
        os.chmod(f,mode)
    bind_host='0.0.0.0' if args.lan else '127.0.0.1' 
    # TEMPORARY RC9.2: sudo inherits the service mount namespace. A root helper
    # cannot write /etc/passwd, /etc/group or Samba state with ProtectSystem=strict.
    # Replace sudo delegation with an independently sandboxed privileged service.
    service='''[Unit]\nDescription=PiNAS prototype web dashboard\nAfter=network.target\n[Service]\nType=simple\nUser=pinas\nGroup=pinas\nExecStart=/usr/bin/python3 /opt/pinas/pinas.py --serve --tls --host %s --port %d\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=false\nProtectSystem=false\nReadWritePaths=/var/lib/pinas\nPrivateTmp=true\n[Install]\nWantedBy=multi-user.target\n'''%(bind_host,args.port)
    Path('/etc/systemd/system/pinas.service').write_text(service)
    subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','enable','--now','pinas-hostname.path'],check=True);subprocess.run(['systemctl','start','pinas-hostname.service'],check=True);subprocess.run(['systemctl','enable','pinas.service'],check=True);subprocess.run(['systemctl','restart','pinas.service'],check=True)
    print(f'PiNAS installed. For localhost access: https://127.0.0.1:{args.port} (self-signed certificate)')
    if args.lan:print(f'LAN TLS MODE: open https://<PI-IP>:{args.port}. Certificate is self-signed; use the .local hostname for name matching. Do not expose this port to the internet.')
    else:print('Localhost-only mode; re-run installer with --lan to enable direct LAN access for testing.')

def main():
    ap=argparse.ArgumentParser(description='PiNAS Raspberry Pi NAS prototype')
    ap.add_argument('--lan',action='store_true',help='Bind HTTPS server to LAN interfaces');ap.add_argument('--install',action='store_true');ap.add_argument('--serve',action='store_true');ap.add_argument('--tls',action='store_true');ap.add_argument('--skip-packages',action='store_true');ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=8765)
    a=ap.parse_args()
    if a.install:install(a);return
    if a.serve:
        if a.host not in ('127.0.0.1','::1','0.0.0.0'):sys.exit('Unsupported bind address.')
        if a.host=='0.0.0.0' and not a.tls:sys.exit('LAN listening requires HTTPS (--tls)')
        server=ThreadingHTTPServer((a.host,a.port),Handler)
        if a.tls:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(TLS_CERT),str(TLS_KEY))
            server.socket=context.wrap_socket(server.socket,server_side=True)
        print('PiNAS running on %s://%s:%s'%('https' if a.tls else 'http',a.host,a.port))
        threading.Thread(target=cpu_sampler,daemon=True).start();server.serve_forever();return
    ap.print_help()
if __name__=='__main__':main()) for x in (name,new_name)):
                self.json({'error':'Invalid share name.'},400);return
            if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not isinstance(u,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):
                self.json({'error':'Assign at least one valid user access.'},400);return
            if not isinstance(password,str) or not verify(password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not set(access).issubset({u['name'] for u in nas_user_list()}):
                self.json({'error':'Unknown NAS user.'},409);return
            if not any(isinstance(item,dict) and item.get('name')==name for item in nas_share_list()):
                self.json({'error':'Only PiNAS-managed shares can be edited.'},404);return
            try:edit_nas_share(name,new_name,access)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':new_name});return
        if path=='/api/delete-share':
            name=data.get('name');password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):
                self.json({'error':'Invalid share name.'},400);return
            if not isinstance(password,str) or not verify(password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not any(isinstance(item,dict) and item.get('name')==name for item in nas_share_list()):
                self.json({'error':'Only PiNAS-managed shares can be removed.'},404);return
            try:delete_nas_share(name)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name,'files_preserved':True});return
        if path=='/api/nas-shares':
            name=data.get('name');volume=data.get('volume');access=data.get('access');admin_password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):
                self.json({'error':'Choose a share name of 1–32 letters, digits, spaces, underscores or hyphens.'},400);return
            if not isinstance(volume,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',volume) or '..' in volume:
                self.json({'error':'Invalid storage selection.'},400);return
            if not isinstance(access,dict) or not access or len(access)>64 or any(not isinstance(k,str) or v not in ('ro','rw') for k,v in access.items()):
                self.json({'error':'Assign at least one user Read Only or Read & Write access.'},400);return
            if not isinstance(admin_password,str) or not verify(admin_password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not storage_is_ready():self.json({'error':'A mounted, persistent data filesystem is required.'},409);return
            valid_users={u['name'] for u in nas_user_list()}
            if not set(access).issubset(valid_users):self.json({'error':'One or more users are not valid Samba accounts.'},409);return
            if any(name.casefold()==s.casefold() for s in discover().get('shares',[])):
                self.json({'error':'A share with this name already exists.'},409);return
            try:create_nas_share(name,volume,access)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name});return
        if path=='/api/logout':SESSIONS.pop(token,None);self.json({'ok':True},cookie='pinas_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'+('; Secure' if isinstance(self.connection,ssl.SSLSocket) else ''));return
        if path=='/api/settings':
            theme,accent,font=data.get('theme'),data.get('accent'),data.get('font')
            interval,history=data.get('cpu_interval',cfg.get('cpu_interval',5)),data.get('cpu_history',cfg.get('cpu_history',10))
            session_timeout=data.get('session_timeout',cfg.get('session_timeout',5))
            if theme not in ('light','dark','dark-cb','light-cb') or not isinstance(accent,str) or len(accent)!=7 or accent[0]!='#' or any(c not in '0123456789abcdefABCDEF' for c in accent[1:]) or type(font)!=int or font not in (10,12,14,16) or type(interval)!=int or interval not in (2,5,10) or type(history)!=int or history not in (10,15,30,60) or type(session_timeout)!=int or session_timeout not in (5,10,15,30,60):self.json({'error':'Invalid appearance settings'},400);return
            cfg.update(theme=theme,accent=accent,font=font,cpu_interval=interval,cpu_history=history,session_timeout=session_timeout)
        elif path=='/api/background':
            image=data.get('image')
            if not isinstance(image,str) or len(image)>2_900_000:self.json({'error':'Image too large'},400);return
            if image:
                try:
                    meta,b64=image.split(',',1);mime=meta[5:].split(';',1)[0]
                    if mime not in ('image/jpeg','image/png','image/webp'):raise ValueError()
                    decoded=base64.b64decode(b64,validate=True)
                    if len(decoded)>2*1024*1024:raise ValueError()
                    if not ((mime=='image/jpeg' and decoded.startswith(b'\xff\xd8\xff')) or (mime=='image/png' and decoded.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/webp' and decoded.startswith(b'RIFF') and decoded[8:12]==b'WEBP')):raise ValueError()
                except (ValueError,IndexError):self.json({'error':'Invalid image'},400);return
            cfg['login_background']=image
        save(cfg);self.json({'settings':dict({k:cfg.get(k) for k in ('theme','accent','font','cpu_interval','cpu_history','session_timeout')},has_background=bool(cfg.get('login_background')))} )

HOSTNAME_HELPER = r"""#!/usr/bin/env python3
import json, re, subprocess
from pathlib import Path
try:
    path=Path('/var/lib/pinas/config.json')
    if not path.exists():raise SystemExit(0)
    cfg=json.loads(path.read_text())
    hostname=cfg.get('hostname','')
    if not hostname:raise SystemExit(0)
    if not isinstance(hostname,str) or not 1<=len(hostname)<=63 or not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*',hostname):
        raise ValueError('Invalid hostname')
    current=subprocess.run(['hostname','-s'],capture_output=True,text=True,check=True).stdout.strip()
    if current!=hostname:
        subprocess.run(['/usr/bin/hostnamectl','set-hostname',hostname],check=True,timeout=15)
except (OSError,ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
    raise SystemExit('PiNAS hostname not applied: '+str(exc))
"""

NAS_USER_HELPER = r"""#!/usr/bin/env python3
# Privileged helper. No arbitrary command execution; narrowly scoped account actions.
import grp, json, os, pwd, re, subprocess, sys

def run(argv, **kwargs):
    return subprocess.run(argv, check=True, timeout=20, **kwargs)

def samba_users():
    p=run(['/usr/bin/pdbedit','-L'],capture_output=True,text=True)
    result=[]
    for line in p.stdout.splitlines():
        fields=line.split(':',2)
        if len(fields)>=2 and re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',fields[0]):
            result.append({'name':fields[0],'uid':fields[1]})
    return sorted(result,key=lambda x:x['name'])

if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit(2)
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(samba_users()))
        raise SystemExit(0)
    if len(sys.argv)!=3 or sys.argv[1] not in ('create','password'):raise SystemExit(2)
    name=sys.argv[2]
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',name) or name in ('pinas','root','admin','nobody'):raise SystemExit(2)
    password=sys.stdin.readline(258).rstrip('\n')
    if not 12<=len(password)<=256:raise SystemExit(2)
    if sys.argv[1]=='password':
        group=grp.getgrnam('pinas-nas')
        existing=pwd.getpwnam(name)
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin') or not any(u['name']==name for u in samba_users()):
            raise SystemExit('Not a managed PiNAS Samba user')
        run(['/usr/bin/smbpasswd','-s',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        raise SystemExit(0)
    try:
        group=grp.getgrnam('pinas-nas')
    except KeyError:
        run(['/usr/sbin/groupadd','pinas-nas'])
        group=grp.getgrnam('pinas-nas')
    created=False
    try:
        existing=pwd.getpwnam(name)
    except KeyError:
        existing=None
    if existing:
        # Repair only a partial PiNAS account from a previous failed attempt.
        # Never repurpose unrelated Linux accounts.
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):
            raise SystemExit('Linux account already exists and is not a PiNAS NAS account; choose another username')
        if any(u['name']==name for u in samba_users()):
            raise SystemExit('Samba account already exists; refresh the Users page')
    else:
        run(['/usr/sbin/useradd','--no-create-home','--shell','/usr/sbin/nologin','--gid','pinas-nas',name])
        created=True
    try:
        run(['/usr/bin/smbpasswd','-s','-a',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        run(['/usr/bin/smbpasswd','-e',name],capture_output=True)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        if created:subprocess.run(['/usr/sbin/userdel',name],check=False,timeout=10)
        raise SystemExit('Samba account creation failed: '+str(exc))
"""

NAS_SHARE_HELPER = r"""#!/usr/bin/env python3
# Root-only share broker. Strict input validation and independent mount checks.
import json, os, pathlib, pwd, re, subprocess, sys, tempfile

DB=pathlib.Path('/var/lib/pinas/shares.json')
CONF=pathlib.Path('/etc/samba/pinas-shares.conf')
SMB=pathlib.Path('/etc/samba/smb.conf')

def run(cmd, **kw):
    return subprocess.run(cmd,check=True,timeout=15,capture_output=True,text=True,**kw)

def read_db():
    try:
        value=json.loads(DB.read_text())
        return value if isinstance(value,list) else []
    except (OSError,ValueError):return []

def atomic(path,content,mode=0o600):
    fd,name=tempfile.mkstemp(prefix='.pinas-',dir=str(path.parent))
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'w') as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def check_volume(device):
    if not isinstance(device,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',device) or '..' in device:raise ValueError('Invalid device')
    # Device must be a block device with an approved filesystem.
    p=pathlib.Path(device)
    if not p.is_block_device():raise ValueError('Selected storage is not a block device')
    fs=run(['/usr/bin/lsblk','-n','-o','FSTYPE',device]).stdout.strip().splitlines()
    if not fs or fs[0].strip().lower() not in ('ext4','xfs','btrfs'):raise ValueError('Unsupported filesystem')
    target=run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device]).stdout.strip().splitlines()
    if len(target)!=1:raise ValueError('Disk must have one unambiguous active mount')
    mount=pathlib.Path(target[0]).resolve(strict=True)
    if str(mount) in ('/','/boot','/boot/firmware') or any(str(mount).startswith(prefix) for prefix in ('/etc/','/var/','/usr/','/home/','/opt/','/root/','/proc/','/sys/','/run/')):
        raise ValueError('System storage cannot host NAS shares')
    if not mount.is_dir() or mount.is_symlink():raise ValueError('Invalid mount directory')
    # Confirm mounted persistently via UUID, path or LABEL; do not trust browser data.
    uuid=run(['/usr/sbin/blkid','-s','UUID','-o','value',device]).stdout.strip()
    entries=[line.split() for line in pathlib.Path('/etc/fstab').read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not any(len(e)>=2 and e[1]==str(mount) and e[0] in (device,'UUID='+uuid,'/dev/disk/by-uuid/'+uuid) for e in entries):
        raise ValueError('Disk is not persistently configured in fstab')
    # Reject root device even when mounted at a second location.
    rootdev=run(['/usr/bin/findmnt','-n','-o','SOURCE','/']).stdout.strip()
    if rootdev.startswith('/dev/'):
        rootparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',rootdev]).stdout.split())
        selectedparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',device]).stdout.split())
        if rootparents & selectedparents:raise ValueError('Operating system disk is protected')
    return mount

def main():
    if os.geteuid()!=0:raise ValueError('Root helper required')
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(read_db()));return
    if len(sys.argv)==2 and sys.argv[1]=='delete':
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('Request too large')
        request=json.loads(raw);name=request.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):raise ValueError('Invalid share name')
        current=read_db()
        matches=[item for item in current if isinstance(item,dict) and item.get('name')==name]
        if len(matches)!=1:raise ValueError('Share is not managed by PiNAS')
        oldconf=CONF.read_text()
        # Match only a complete, exact managed Samba section; never touch unrelated shares.
        section=re.compile(r'(?m)^\['+re.escape(name)+r'\][ \t]*\n(?:(?!\[).*(?:\n|$))*')
        found=list(section.finditer(oldconf))
        if len(found)!=1:raise ValueError('Managed Samba share section missing or ambiguous')
        updated=oldconf[:found[0].start()]+oldconf[found[0].end():]
        olddb=DB.read_text()
        try:
            atomic(CONF,updated,0o644)
            run(['/usr/bin/testparm','-s'])
            run(['/usr/bin/systemctl','reload','smbd'])
            atomic(DB,json.dumps([item for item in current if not (isinstance(item,dict) and item.get('name')==name)],indent=2),0o600)
        except Exception:
            atomic(CONF,oldconf,0o644)
            atomic(DB,olddb,0o600)
            try:run(['/usr/bin/systemctl','reload','smbd'])
            except Exception:pass
            raise
        # Deliberately leave the share directory, ACLs and files untouched.
        print(json.dumps({'ok':True,'files_preserved':True}));return
    if len(sys.argv)!=2 or sys.argv[1]!='create':raise ValueError('Unsupported action')
    raw=sys.stdin.read(8193)
    if len(raw)>8192:raise ValueError('Request too large')
    request=json.loads(raw)
    name=request.get('name');access=request.get('access');device=request.get('volume')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):raise ValueError('Invalid share name')
    if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):raise ValueError('Invalid access policy')
    # Verify users exist in Samba and Linux before creating any directory.
    samba={line.split(':',1)[0] for line in run(['/usr/bin/pdbedit','-L']).stdout.splitlines()}
    for user in access:
        if user not in samba:raise ValueError('Samba account not found: '+user)
        pwd.getpwnam(user)
    mount=check_volume(device)
    current=read_db()
    if any(item.get('name','').casefold()==name.casefold() for item in current):raise ValueError('Share already exists')
    # Samba's own configuration may include external shares; reject collisions.
    existing=run(['/usr/bin/testparm','-s']).stdout
    if any(line.strip().casefold()=='['+name.casefold()+']' for line in existing.splitlines()):raise ValueError('Share name already used by Samba')
    # No preexisting folder is ever adopted or modified by this operation.
    root=mount/'PiNAS Shares'
    if root.is_symlink():raise ValueError('Unsafe share root')
    root.mkdir(mode=0o711,exist_ok=True)
    if root.stat().st_uid!=0 or (root.stat().st_mode & 0o022):raise ValueError('Share root must be root-owned and not group/world writable')
    folder=root/name
    if folder.exists() or folder.is_symlink():raise ValueError('Folder already exists; choose a different name')
    if not pathlib.Path('/usr/bin/setfacl').exists():raise ValueError('POSIX ACL tools are required (install acl)')
    # Validate smb.conf can be managed before changing filesystem.
    original=SMB.read_text()
    include='   include = /etc/samba/pinas-shares.conf'
    if include not in original:
        if not re.search(r'(?im)^\s*\[global\]\s*$',original):raise ValueError('Samba [global] section missing')
        amended=re.sub(r'(?im)^(\s*\[global\]\s*)$',r'\1\n'+include,original,count=1)
    else:amended=original
    # Explicit per-user access; default deny for other NAS accounts.
    ro=[u for u,p in access.items() if p=='ro'];rw=[u for u,p in access.items() if p=='rw']
    stanza='\n['+name+']\n   path = '+str(folder)+'\n   browseable = yes\n   guest ok = no\n   read only = yes\n   valid users = '+', '.join(access)+'\n'
    if rw:stanza+='   write list = '+', '.join(rw)+'\n'
    stanza+='   create mask = 0660\n   directory mask = 0770\n   follow symlinks = no\n   wide links = no\n'
    oldconf=CONF.read_text() if CONF.exists() else ''
    if '['+name+']' in oldconf:raise ValueError('Duplicate managed share')
    folder.mkdir(mode=0o700)
    try:
        # Root-owned folder; Samba creates files as authenticated Unix users.
        os.chown(folder,0,0)
        os.chmod(folder,0o700)
        acl=['u::rwx','g::---','o::---','m::rwx']+[f'u:{u}:'+('rwx' if p=='rw' else 'r-x') for u,p in access.items()]
        default=['d:'+entry for entry in acl]
        run(['/usr/bin/setfacl','-m',','.join(acl+default),str(folder)])
        if amended!=original:atomic(SMB,amended,0o644)
        atomic(CONF,oldconf+stanza,0o644)
        run(['/usr/bin/testparm','-s'])
        run(['/usr/bin/systemctl','reload','smbd'])
        current.append({'name':name,'volume_label':mount.name,'volume':device,'access':access})
        atomic(DB,json.dumps(current,indent=2),0o600)
    except Exception:
        atomic(CONF,oldconf,0o644)
        if amended!=original:atomic(SMB,original,0o644)
        try:run(['/usr/bin/systemctl','reload','smbd'])
        except Exception:pass
        try:folder.rmdir()
        except OSError:pass
        raise
    print(json.dumps({'ok':True,'name':name}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

NAS_FILES_HELPER = r"""#!/usr/bin/env python3
# Privileged, narrow file broker. Authentication against Samba passdb; filesystem
# operations executed as the NAS user's actual UID/GID and supplementary groups.
import base64, hashlib, hmac, json, os, pathlib, pwd, re, stat, subprocess, sys
DB=pathlib.Path('/var/lib/pinas/shares.json')
def md4(message):
    # NT hash is MD4(UTF-16LE password). Samba uses NT hashes for SMB auth.
    import struct
    original=len(message);message+=b'\x80';message+=b'\0'*((56-len(message)%64)%64)+struct.pack('<Q',original*8)
    a,b,c,d=0x67452301,0xefcdab89,0x98badcfe,0x10325476
    def rol(v,n):return ((v<<n)|(v>>(32-n)))&0xffffffff
    for offset in range(0,len(message),64):
        x=struct.unpack('<16I',message[offset:offset+64]);aa,bb,cc,dd=a,b,c,d
        for j in range(48):
            if j<16:f=(b&c)|(~b&d);k=j;shift=[3,7,11,19][j%4];constant=0
            elif j<32:f=(b&c)|(b&d)|(c&d);k=(j%4)*4+j//4-4;shift=[3,5,9,13][j%4];constant=0x5a827999
            else:f=b^c^d;k=[0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15][j-32];shift=[3,9,11,15][j%4];constant=0x6ed9eba1
            value=rol((a+f+x[k]+constant)&0xffffffff,shift);a,b,c,d=d,value,b,c
        a=(a+aa)&0xffffffff;b=(b+bb)&0xffffffff;c=(c+cc)&0xffffffff;d=(d+dd)&0xffffffff
    return struct.pack('<4I',a,b,c,d).hex().upper()
def samba_hash(user):
    p=subprocess.run(['/usr/bin/pdbedit','-Lw',user],capture_output=True,text=True,timeout=8)
    if p.returncode:raise ValueError('Unknown NAS account')
    for line in p.stdout.splitlines():
        fields=line.split(':')
        if len(fields)>4 and fields[0]==user and re.fullmatch('[A-Fa-f0-9]{32}',fields[3]):return fields[3].upper()
    raise ValueError('NAS account has no valid Samba password')
def valid_user(user):
    if not isinstance(user,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',user):raise ValueError('Invalid user')
    person=pwd.getpwnam(user)
    if person.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):raise ValueError('Not a PiNAS NAS user')
    if samba_hash(user)=='':raise ValueError('Not a Samba user')
    return person
def shares_for(user):
    entries=json.loads(DB.read_text())
    return [s for s in entries if isinstance(s,dict) and s.get('access',{}).get(user) in ('ro','rw')]
def drop(person):
    os.initgroups(person.pw_name,person.pw_gid);os.setgid(person.pw_gid);os.setuid(person.pw_uid)
def safe_path(root,relative):
    if not isinstance(relative,str) or len(relative)>1000 or relative.startswith('/') or '\\' in relative or '\x00' in relative:raise ValueError('Invalid path')
    parts=relative.split('/') if relative else []
    if any(x in ('','.','..') or x.startswith('.pinas-upload-') for x in parts):raise ValueError('Invalid path')
    # Reject symlinks at every level, including the leaf. Never follow them.
    cur=root
    for part in parts:
        cur=cur/part
        if cur.is_symlink():raise ValueError('Symbolic links are not accessible')
    if not cur.resolve(strict=False).is_relative_to(root.resolve(strict=True)):raise ValueError('Path outside share')
    return cur
def main():
    if os.geteuid()!=0:raise ValueError('Root required')
    raw=sys.stdin.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise ValueError('Request too large')
    q=json.loads(raw);action=q.get('action');user=q.get('username');person=valid_user(user)
    if action=='authenticate':
        password=q.get('password')
        if not isinstance(password,str) or len(password)>256:raise ValueError('Invalid password')
        print('true' if hmac.compare_digest(md4(password.encode('utf-16le')),samba_hash(user)) else 'false');return
    allowed=shares_for(user)
    if action=='shares':
        print(json.dumps({'shares':[{'name':s['name'],'read_only':s['access'][user]=='ro'} for s in allowed]}));return
    share=q.get('share');s=next((x for x in allowed if x['name']==share),None)
    if s is None:raise ValueError('Share not accessible')
    # Root path derived exclusively from privileged share metadata, not browser paths.
    root=pathlib.Path(s['volume_label']) if False else None
    # Resolve mount from device, and confirm it is still the same mounted filesystem.
    device=s['volume'];p=subprocess.run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device],capture_output=True,text=True,timeout=5)
    targets=p.stdout.strip().splitlines()
    if p.returncode or len(targets)!=1:raise ValueError('Share storage is offline')
    mount=pathlib.Path(targets[0]).resolve(strict=True)
    if str(mount)=='/' or str(mount).startswith(('/etc/','/var/','/usr/','/home/','/boot/')):raise ValueError('Protected mount')
    root=mount/'PiNAS Shares'/s['name']
    if root.is_symlink() or not root.is_dir():raise ValueError('Share folder unavailable')
    relative=q.get('path','');target=safe_path(root,relative)
    writable=s['access'][user]=='rw'
    if action in ('mkdir','delete','rename','move','copy','upload','upload_start','upload_chunk','upload_finish','upload_cancel') and not writable:raise ValueError('Read-only share')
    drop(person)
    # All operations below run with the NAS user's UID/GID. Uploads are staged
    # in the destination directory, then published by an atomic rename.
    def valid_name(name):
        if not isinstance(name,str) or not name or len(name)>255 or name in ('.','..') or '/' in name or '\\' in name or '\x00' in name or name.startswith('.pinas-upload-'):raise ValueError('Invalid file name')
        return name
    def destination(relative):
        dest=safe_path(root,relative)
        if dest==root or dest.exists() or dest.is_symlink():raise ValueError('Destination already exists')
        if not dest.parent.is_dir():raise ValueError('Destination folder does not exist')
        return dest
    if action in ('rename','move','copy'):
        if target==root or not target.exists():raise ValueError('Invalid source')
        if action=='rename':
            dest=destination('/'.join(filter(None,[relative.rsplit('/',1)[0] if '/' in relative else '',valid_name(q.get('name'))])))
        else:
            dest=destination(q.get('dest',''))
        if target.is_dir() and (dest==target or target in dest.parents):raise ValueError('Cannot place folder inside itself')
        if action=='copy':
            import shutil
            if target.is_dir():
                # Reject links anywhere in the tree and cap total copy size.
                total=0
                for directory,dirs,files in os.walk(target,followlinks=False):
                    for name in dirs+files:
                        node=pathlib.Path(directory)/name
                        if node.is_symlink():raise ValueError('Symbolic links cannot be copied')
                        if node.is_file():total+=node.stat().st_size
                        if total>8*1024**3:raise ValueError('Folder copy exceeds 8 GiB safety limit')
                shutil.copytree(target,dest,symlinks=False)
            elif target.is_file():
                with target.open('rb') as src, dest.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            else:raise ValueError('Unsupported file type')
        else:
            # Same-share only; atomic rename prevents partial moves.
            if target.is_file():
                os.link(target,dest,follow_symlinks=False);target.unlink()
            else:target.rename(dest)
        print('{"ok":true}');return
    if action=='upload_start':
        name=valid_name(q.get('name'))
        if not target.is_dir():raise ValueError('Not a folder')
        destination('/'.join(filter(None,[relative,name])))
        size=q.get('size')
        if not isinstance(size,int) or size<0 or size>100*1024**3:raise ValueError('Invalid upload size')
        import secrets
        token=secrets.token_hex(20)
        staging=target/('.pinas-upload-'+token)
        fd=os.open(staging,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        meta=target/('.pinas-upload-'+token+'.json')
        fd=os.open(meta,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'name':name,'size':size,'path':relative},f)
        print(json.dumps({'token':token}));return
    if action in ('upload_chunk','upload_finish','upload_cancel'):
        token=q.get('token','')
        if not isinstance(token,str) or not re.fullmatch('[0-9a-f]{40}',token):raise ValueError('Invalid transfer token')
        stage=target/('.pinas-upload-'+token)
        meta=target/('.pinas-upload-'+token+'.json')
        if stage.is_symlink() or meta.is_symlink() or not stage.is_file() or not meta.is_file():raise ValueError('Unknown transfer')
        details=json.loads(meta.read_text());name=valid_name(details['name']);size=details['size']
        if details.get('path')!=relative:raise ValueError('Transfer location mismatch')
        if action=='upload_cancel':stage.unlink();meta.unlink();print('{"ok":true}');return
        if action=='upload_chunk':
            content=q.get('content','');offset=q.get('offset')
            if not isinstance(content,str) or len(content)>700000 or not isinstance(offset,int):raise ValueError('Invalid chunk')
            payload=base64.b64decode(content,validate=True)
            if len(payload)>512*1024 or offset!=stage.stat().st_size or offset+len(payload)>size:raise ValueError('Chunk offset or size mismatch')
            with stage.open('ab') as f:f.write(payload)
            print(json.dumps({'offset':offset+len(payload)}));return
        if stage.stat().st_size!=size:raise ValueError('Upload incomplete')
        dest=destination('/'.join(filter(None,[relative,name])))
        # Hard-link is no-clobber and atomic on the same filesystem.
        os.link(stage,dest,follow_symlinks=False);stage.unlink();meta.unlink()
        print('{"ok":true}');return
    if action=='download_chunk':
        offset=q.get('offset');size=q.get('size')
        if not isinstance(offset,int) or offset<0 or not isinstance(size,int) or size<1 or size>512*1024:raise ValueError('Invalid download range')
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode):raise ValueError('Not a regular file')
        total=target.stat().st_size
        with target.open('rb') as f:f.seek(offset);chunk=f.read(size)
        print(json.dumps({'content':base64.b64encode(chunk).decode(),'total':total}));return
    if action=='list':
        if not target.is_dir():raise ValueError('Not a folder')
        entries=[]
        for child in sorted(target.iterdir(),key=lambda x:x.name.casefold()):
            if child.is_symlink() or child.name.startswith('.pinas-upload-'):continue
            try:st=child.stat()
            except OSError:continue
            if stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode):entries.append({'name':child.name,'dir':stat.S_ISDIR(st.st_mode),'size':st.st_size})
            if len(entries)>=1000:break
        print(json.dumps({'entries':entries}));return
    if action=='mkdir':
        name=q.get('name','');dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..'):raise ValueError('Invalid folder name')
        dest.mkdir(mode=0o770);print('{"ok":true}');return
    if action=='delete':
        if target==root:raise ValueError('Cannot delete share root')
        if target.is_dir():target.rmdir()
        elif target.is_file():target.unlink()
        else:raise ValueError('Not a regular file or empty folder')
        print('{"ok":true}');return
    if action=='download':
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode) or target.stat().st_size>3*1024*1024:raise ValueError('Only files up to 3 MB supported in this test build')
        with target.open('rb') as f:content=base64.b64encode(f.read()).decode()
        print(json.dumps({'content':content}));return
    if action=='upload':
        name=q.get('name','');content=q.get('content','')
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..') or not isinstance(content,str) or len(content)>4*1024*1024+16:raise ValueError('Invalid upload')
        dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not target.is_dir():raise ValueError('Not a directory')
        payload=base64.b64decode(content,validate=True)
        if len(payload)>3*1024*1024:raise ValueError('Upload exceeds 3 MB')
        fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o660)
        with os.fdopen(fd,'wb') as f:f.write(payload)
        print('{"ok":true}');return
    raise ValueError('Unsupported action')
if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
"""

APT_INDEX_HELPER = r"""#!/usr/bin/env python3
import os,subprocess,sys
from pathlib import Path
ALLOWED={'off':None,'daily':'*-*-* 01:00:00','weekly':'Fri *-*-* 01:00:00','monthly':'*-*-28 01:00:00'}
def run(cmd,timeout=30):
    p=subprocess.run(cmd,timeout=timeout,check=False)
    if p.returncode:sys.exit(p.returncode)
def main():
    if os.geteuid()!=0:sys.exit('Root access required')
    args=sys.argv[1:]
    if len(args)==2 and args[0]=='schedule' and args[1] in ALLOWED:
        schedule=args[1];calendar=ALLOWED[schedule]
        timer=Path('/etc/systemd/system/pinas-auto-updates.timer')
        if calendar:
            timer.write_text('[Unit]\nDescription=PiNAS automatic OS updates\n[Timer]\nOnCalendar='+calendar+'\nPersistent=true\nUnit=pinas-auto-updates.service\n[Install]\nWantedBy=timers.target\n')
        run(['systemctl','daemon-reload'])
        if calendar:
            run(['systemctl','enable','--now','pinas-auto-updates.timer'])
            run(['systemctl','restart','pinas-auto-updates.timer'])
        else:
            run(['systemctl','disable','--now','pinas-auto-updates.timer']) if timer.exists() else None
            timer.unlink(missing_ok=True)
            run(['systemctl','daemon-reload'])
        marker=Path('/var/lib/pinas/update-schedule');marker.write_text(schedule+'\n');os.chmod(marker,0o644)
        return
    if args==['automatic']:
        # Only the systemd oneshot invokes this command, not the web service account.
        run(['/usr/bin/apt-get','update'],210)
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
        return
    if args==['upgrade']:
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
    elif args==['refresh']:
        run(['/usr/bin/apt-get','update'],210)
    else:sys.exit('Unsupported operation')
if __name__=='__main__':main()
"""

NAS_STORAGE_HELPER='#!/usr/bin/env python3\n"""PiNAS RC13 restricted, non-destructive storage adoption helper."""\nimport json,os,pathlib,re,subprocess,sys,uuid\nfrom pathlib import Path\n\ndef run(*args,timeout=15):\n    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)\n    if p.returncode:raise ValueError((p.stderr or \'Storage command failed\').strip()[-500:])\n    return p.stdout.strip()\n\ndef main():\n    if os.geteuid()!=0 or sys.argv[1:]!=[\'adopt\']:raise ValueError(\'Unsupported storage operation\')\n    data=json.loads(sys.stdin.read(4096));device=data.get(\'device\')\n    if not isinstance(device,str) or not re.fullmatch(r\'/dev/[A-Za-z0-9_./-]{1,90}\',device) or \'..\' in device:raise ValueError(\'Invalid device\')\n    path=Path(device)\n    if not path.is_block_device():raise ValueError(\'Device is not a block device\')\n    # The privileged helper independently identifies eligible physical disks.\n    roots=json.loads(run(\'lsblk\',\'-J\',\'-b\',\'-o\',\'NAME,PATH,TYPE,FSTYPE,UUID,MOUNTPOINTS,RO,PKNAME\')).get(\'blockdevices\',[])\n    bypath={};byname={};parents={}\n    def walk(node,parent=None):\n        name=node.get(\'name\');bypath[node.get(\'path\')]=node;byname[name]=node\n        if parent:parents[name]=parent\n        for child in node.get(\'children\') or []:walk(child,name)\n    for root in roots:walk(root)\n    node=bypath.get(str(path.resolve())) or bypath.get(device)\n    if not node or node.get(\'type\') not in (\'part\',\'disk\') or node.get(\'ro\'):raise ValueError(\'Not an eligible writable disk or partition\')\n    def root_for(n):\n        seen=set()\n        while n.get(\'name\') in parents:\n            if n[\'name\'] in seen:raise ValueError(\'Invalid device topology\')\n            seen.add(n[\'name\']);n=byname[parents[n[\'name\']]]\n        return n\n    disk=root_for(node)\n    if disk.get(\'type\')!=\'disk\' or disk.get(\'ro\') or str(disk.get(\'name\',\'\')).startswith((\'loop\',\'zram\',\'ram\',\'nbd\',\'sr\',\'fd\')):raise ValueError(\'Unsupported backing device\')\n    # Reject any physical disk carrying the root or boot filesystems.\n    protected={\'/\',\'/boot\',\'/boot/firmware\',\'/boot/efi\'}\n    def contains_system(n):\n        if any(m in protected for m in (n.get(\'mountpoints\') or []) if m):return True\n        return any(contains_system(c) for c in n.get(\'children\') or [])\n    if contains_system(disk):raise ValueError(\'Operating system storage is protected\')\n    for mount in protected:\n        src=run(\'findmnt\',\'-n\',\'-o\',\'SOURCE\',\'--target\',mount).split(\'[\',1)[0]\n        if src and src in bypath and root_for(bypath[src]).get(\'name\')==disk.get(\'name\'):\n            raise ValueError(\'Operating system storage is protected\')\n    fs=run(\'blkid\',\'-s\',\'TYPE\',\'-o\',\'value\',device)\n    uid=run(\'blkid\',\'-s\',\'UUID\',\'-o\',\'value\',device)\n    if fs not in (\'ext4\',\'xfs\',\'btrfs\') or not re.fullmatch(r\'[A-Za-z0-9-]{8,64}\',uid):raise ValueError(\'Supported filesystem and UUID required\')\n    # Reject RAID/LVM/crypto members and nested volume layouts.\n    if node.get(\'type\')==\'disk\' and node.get(\'children\'):raise ValueError(\'Choose a filesystem partition, not its parent disk\')\n    if node.get(\'children\'):raise ValueError(\'Complex volume layout not supported\')\n    mountpoints=[m for m in node.get(\'mountpoints\') or [] if m]\n    if len(mountpoints)>1:raise ValueError(\'Multiple mountpoints require manual review\')\n    if mountpoints and not str(mountpoints[0]).startswith(\'/mnt/pinas/\'):\n        raise ValueError(\'Filesystem is already mounted elsewhere; manage it manually to avoid disrupting applications\')\n    target=Path(\'/mnt/pinas\')/uid\n    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir())) and str(target) not in mountpoints):raise ValueError(\'Mount destination is not empty\')\n    fstab=Path(\'/etc/fstab\');original=fstab.read_text();entries=[line.split() for line in original.splitlines() if line.strip() and not line.lstrip().startswith(\'#\')]\n    for e in entries:\n        if len(e)>=2 and (e[0] in (device,\'UUID=\'+uid,\'/dev/disk/by-uuid/\'+uid) or e[1]==str(target)):\n            if e[0]==\'UUID=\'+uid and e[1]==str(target):\n                if str(target) not in mountpoints:run(\'mount\',str(target),timeout=25)\n                print(json.dumps({\'ok\':True,\'mount\':str(target),\'existing\':True}));return\n            raise ValueError(\'Existing fstab configuration requires manual review\')\n    target.parent.mkdir(parents=True,exist_ok=True)\n    target.mkdir(mode=0o755,exist_ok=True)\n    options=\'defaults,nofail,noatime,x-systemd.device-timeout=10s\'\n    entry=f\'UUID={uid} {target} {fs} {options} 0 {2 if fs=="ext4" else 0} # PiNAS managed\\\\n\'\n    entry=entry.replace(\'\\\\n\',\'\\n\')\n    backup=fstab.with_name(\'fstab.pinas-\'+uuid.uuid4().hex[:12]+\'.bak\')\n    backup.write_text(original);os.chmod(backup,0o600)\n    temp=fstab.with_name(\'.fstab.pinas-\'+uuid.uuid4().hex)\n    try:\n        temp.write_text(original.rstrip(\'\\n\')+\'\\n\'+entry);os.chmod(temp,0o644)\n        os.replace(temp,fstab)\n        run(\'systemctl\',\'daemon-reload\',timeout=15)\n        run(\'mount\',str(target),timeout=25)\n        actual=run(\'findmnt\',\'-n\',\'-o\',\'UUID\',\'--target\',str(target))\n        if actual!=uid:raise ValueError(\'Mounted filesystem UUID verification failed\')\n    except Exception:\n        fstab.write_text(original)\n        try:run(\'systemctl\',\'daemon-reload\')\n        except Exception:pass\n        raise\n    print(json.dumps({\'ok\':True,\'mount\':str(target)}))\nif __name__==\'__main__\':\n    try:main()\n    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)\n'

SMART_HEALTH_HELPER = """#!/usr/bin/env python3
import json,os,shutil,subprocess,sys
from pathlib import Path
def main():
    if os.geteuid()!=0 or len(sys.argv)!=1:
        raise ValueError('Unsupported operation')
    smartctl=shutil.which('smartctl')
    if not smartctl:
        print(json.dumps({'installed':False,'drives':[]}));return
    p=subprocess.run(['lsblk','-J','-b','-o','NAME,PATH,TYPE,MODEL,TRAN'],capture_output=True,text=True,timeout=8,check=True)
    drives=[]
    for disk in json.loads(p.stdout).get('blockdevices',[]):
        if disk.get('type')!='disk':continue
        device=disk.get('path','')
        if not isinstance(device,str) or not device.startswith('/dev/') or not Path(device).is_block_device():continue
        if disk.get('name','').startswith(('loop','zram','ram','nbd','sr','fd')):continue
        entry={'device':device,'model':disk.get('model') or disk.get('name'),'status':'Unavailable','temperature':None}
        try:
            result=subprocess.run([smartctl,'-j','-H','-A',device],capture_output=True,text=True,timeout=12)
            data=json.loads(result.stdout)
            health=data.get('smart_status',{}).get('passed')
            if health is True:entry['status']='Healthy'
            elif health is False:entry['status']='Warning'
            temp=data.get('temperature',{}).get('current')
            if isinstance(temp,(int,float)) and -20<=temp<=120:entry['temperature']=temp
            if data.get('smart_support',{}).get('available') is False:entry['status']='Unsupported'
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        drives.append(entry)
    print(json.dumps({'installed':True,'drives':drives}))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

def install(args):
    if sys.platform!='linux' or os.geteuid()!=0:sys.exit('Install requires Linux and sudo/root.')
    if not Path('/etc/os-release').exists():sys.exit('Unsupported OS')
    osinfo=read('/etc/os-release')
    if 'debian' not in osinfo.lower() and 'raspbian' not in osinfo.lower():sys.exit('Requires Raspberry Pi OS / Debian family')
    if not args.skip_packages:
        print('Installing NAS dependencies (requires network and may take time)...',flush=True)
        subprocess.run(['apt-get','update'],check=True)
        subprocess.run(['apt-get','install','-y','samba','xfsprogs','btrfs-progs','mdadm','parted','util-linux','e2fsprogs','avahi-daemon','acl','openssl'],check=True)
    target=Path('/opt/pinas');target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(__file__).resolve(),target/'pinas.py');os.chmod(target/'pinas.py',0o755)
    if subprocess.run(['id','-u','pinas'],capture_output=True).returncode!=0:
        subprocess.run(['useradd','--system','--home-dir','/var/lib/pinas','--shell','/usr/sbin/nologin','pinas'],check=True)
    DATA.mkdir(parents=True,exist_ok=True);os.chmod(DATA,0o700)
    subprocess.run(['chown','pinas:pinas',str(DATA)],check=True)
    helper=Path('/usr/local/libexec/pinas-apply-hostname')
    helper.parent.mkdir(parents=True,exist_ok=True)
    helper.write_text(HOSTNAME_HELPER)
    os.chmod(helper,0o755)
    unit='''[Unit]\nDescription=Apply validated PiNAS device hostname\nAfter=systemd-hostnamed.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /usr/local/libexec/pinas-apply-hostname\nNoNewPrivileges=true\nProtectHome=true\nPrivateTmp=true\n'''
    Path('/etc/systemd/system/pinas-hostname.service').write_text(unit)
    path_unit='''[Unit]\nDescription=Apply PiNAS hostname when configuration changes\n[Path]\nPathChanged=/var/lib/pinas/config.json\nUnit=pinas-hostname.service\n[Install]\nWantedBy=multi-user.target\n'''
    Path('/etc/systemd/system/pinas-hostname.path').write_text(path_unit)
    user_helper=Path('/usr/local/libexec/pinas-nas-user')
    user_helper.write_text(NAS_USER_HELPER)
    os.chown(user_helper,0,0);os.chmod(user_helper,0o700)
    sudoers=Path('/etc/sudoers.d/pinas-nas-user')
    sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-user create *, /usr/local/libexec/pinas-nas-user password *, /usr/local/libexec/pinas-nas-user list\n')
    os.chown(sudoers,0,0);os.chmod(sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(sudoers)],capture_output=True).returncode:
        sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS sudoers configuration')
    share_helper=Path('/usr/local/libexec/pinas-nas-share')
    share_helper.write_text(NAS_SHARE_HELPER)
    os.chown(share_helper,0,0);os.chmod(share_helper,0o700)
    share_sudoers=Path('/etc/sudoers.d/pinas-nas-share')
    share_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-share list, /usr/local/libexec/pinas-nas-share create\n')
    os.chown(share_sudoers,0,0);os.chmod(share_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(share_sudoers)],capture_output=True).returncode:
        share_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS share sudoers configuration')
    files_helper=Path('/usr/local/libexec/pinas-nas-files')
    files_helper.write_text(NAS_FILES_HELPER)
    os.chown(files_helper,0,0);os.chmod(files_helper,0o700)
    files_sudoers=Path('/etc/sudoers.d/pinas-nas-files')
    files_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-files\n')
    os.chown(files_sudoers,0,0);os.chmod(files_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(files_sudoers)],capture_output=True).returncode:
        files_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS file helper sudoers configuration')
    storage_helper=Path('/usr/local/libexec/pinas-nas-storage')
    storage_helper.write_text(NAS_STORAGE_HELPER)
    os.chown(storage_helper,0,0);os.chmod(storage_helper,0o700)
    storage_sudoers=Path('/etc/sudoers.d/pinas-nas-storage')
    storage_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-storage adopt\n')
    os.chown(storage_sudoers,0,0);os.chmod(storage_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(storage_sudoers)],capture_output=True).returncode:
        storage_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS storage sudoers configuration')
    smart_helper=Path('/usr/local/libexec/pinas-smart-health')
    smart_helper.write_text(SMART_HEALTH_HELPER)
    os.chown(smart_helper,0,0);os.chmod(smart_helper,0o700)
    smart_sudoers=Path('/etc/sudoers.d/pinas-smart-health')
    smart_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-smart-health\n')
    os.chown(smart_sudoers,0,0);os.chmod(smart_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(smart_sudoers)],capture_output=True).returncode:
        smart_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS SMART sudoers configuration')
    apt_helper=Path('/usr/local/libexec/pinas-apt-index')
    apt_helper.write_text(APT_INDEX_HELPER)
    os.chown(apt_helper,0,0);os.chmod(apt_helper,0o700)
    apt_sudoers=Path('/etc/sudoers.d/pinas-apt-index')
    apt_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-apt-index refresh, /usr/local/libexec/pinas-apt-index upgrade, /usr/local/libexec/pinas-apt-index schedule off, /usr/local/libexec/pinas-apt-index schedule daily, /usr/local/libexec/pinas-apt-index schedule weekly, /usr/local/libexec/pinas-apt-index schedule monthly\n')
    os.chown(apt_sudoers,0,0);os.chmod(apt_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(apt_sudoers)],capture_output=True).returncode:
        apt_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS APT sudoers configuration')
    auto_service=Path('/etc/systemd/system/pinas-auto-updates.service')
    auto_service.write_text('[Unit]\nDescription=PiNAS scheduled OS updates\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=oneshot\nExecStart=/usr/local/libexec/pinas-apt-index automatic\nEnvironment=DEBIAN_FRONTEND=noninteractive\n')
    os.chown(auto_service,0,0);os.chmod(auto_service,0o644)
    # Existing schedule is preserved when upgrading PiNAS.
    # Generate a persistent per-install certificate; never replace it on upgrades.
    if not TLS_CERT.exists() or not TLS_KEY.exists():
        if TLS_CERT.exists() or TLS_KEY.exists():sys.exit('Incomplete TLS certificate pair; resolve manually before installing')
        if not shutil.which('openssl'):sys.exit('OpenSSL required for initial TLS certificate generation')
        hostname=load().get('hostname','pinas')
        if not valid_hostname(hostname):hostname='pinas'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','825',
            '-keyout',str(TLS_KEY),'-out',str(TLS_CERT),'-subj',f'/CN={hostname}.local',
            '-addext',f'subjectAltName=DNS:{hostname}.local,DNS:localhost,IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL)
    for f,mode in ((TLS_CERT,0o644),(TLS_KEY,0o600)):
        os.chown(f,0 if f==TLS_CERT else __import__('pwd').getpwnam('pinas').pw_uid,0 if f==TLS_CERT else __import__('grp').getgrnam('pinas').gr_gid)
        os.chmod(f,mode)
    bind_host='0.0.0.0' if args.lan else '127.0.0.1' 
    # TEMPORARY RC9.2: sudo inherits the service mount namespace. A root helper
    # cannot write /etc/passwd, /etc/group or Samba state with ProtectSystem=strict.
    # Replace sudo delegation with an independently sandboxed privileged service.
    service='''[Unit]\nDescription=PiNAS prototype web dashboard\nAfter=network.target\n[Service]\nType=simple\nUser=pinas\nGroup=pinas\nExecStart=/usr/bin/python3 /opt/pinas/pinas.py --serve --tls --host %s --port %d\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=false\nProtectSystem=false\nReadWritePaths=/var/lib/pinas\nPrivateTmp=true\n[Install]\nWantedBy=multi-user.target\n'''%(bind_host,args.port)
    Path('/etc/systemd/system/pinas.service').write_text(service)
    subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','enable','--now','pinas-hostname.path'],check=True);subprocess.run(['systemctl','start','pinas-hostname.service'],check=True);subprocess.run(['systemctl','enable','pinas.service'],check=True);subprocess.run(['systemctl','restart','pinas.service'],check=True)
    print(f'PiNAS installed. For localhost access: https://127.0.0.1:{args.port} (self-signed certificate)')
    if args.lan:print(f'LAN TLS MODE: open https://<PI-IP>:{args.port}. Certificate is self-signed; use the .local hostname for name matching. Do not expose this port to the internet.')
    else:print('Localhost-only mode; re-run installer with --lan to enable direct LAN access for testing.')

def main():
    ap=argparse.ArgumentParser(description='PiNAS Raspberry Pi NAS prototype')
    ap.add_argument('--lan',action='store_true',help='Bind HTTPS server to LAN interfaces');ap.add_argument('--install',action='store_true');ap.add_argument('--serve',action='store_true');ap.add_argument('--tls',action='store_true');ap.add_argument('--skip-packages',action='store_true');ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=8765)
    a=ap.parse_args()
    if a.install:install(a);return
    if a.serve:
        if a.host not in ('127.0.0.1','::1','0.0.0.0'):sys.exit('Unsupported bind address.')
        if a.host=='0.0.0.0' and not a.tls:sys.exit('LAN listening requires HTTPS (--tls)')
        server=ThreadingHTTPServer((a.host,a.port),Handler)
        if a.tls:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(TLS_CERT),str(TLS_KEY))
            server.socket=context.wrap_socket(server.socket,server_side=True)
        print('PiNAS running on %s://%s:%s'%('https' if a.tls else 'http',a.host,a.port))
        threading.Thread(target=cpu_sampler,daemon=True).start();server.serve_forever();return
    ap.print_help()
if __name__=='__main__':main(),'ipc
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('Request too large')
        request=json.loads(raw);name=request.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):raise ValueError('Invalid share name')
        current=read_db()
        matches=[item for item in current if isinstance(item,dict) and item.get('name')==name]
        if len(matches)!=1:raise ValueError('Share is not managed by PiNAS')
        oldconf=CONF.read_text()
        # Match only a complete, exact managed Samba section; never touch unrelated shares.
        section=re.compile(r'(?m)^\['+re.escape(name)+r'\][ \t]*\n(?:(?!\[).*(?:\n|$))*')
        found=list(section.finditer(oldconf))
        if len(found)!=1:raise ValueError('Managed Samba share section missing or ambiguous')
        updated=oldconf[:found[0].start()]+oldconf[found[0].end():]
        olddb=DB.read_text()
        try:
            atomic(CONF,updated,0o644)
            run(['/usr/bin/testparm','-s'])
            run(['/usr/bin/systemctl','reload','smbd'])
            atomic(DB,json.dumps([item for item in current if not (isinstance(item,dict) and item.get('name')==name)],indent=2),0o600)
        except Exception:
            atomic(CONF,oldconf,0o644)
            atomic(DB,olddb,0o600)
            try:run(['/usr/bin/systemctl','reload','smbd'])
            except Exception:pass
            raise
        # Deliberately leave the share directory, ACLs and files untouched.
        print(json.dumps({'ok':True,'files_preserved':True}));return
    if len(sys.argv)!=2 or sys.argv[1]!='create':raise ValueError('Unsupported action')
    raw=sys.stdin.read(8193)
    if len(raw)>8192:raise ValueError('Request too large')
    request=json.loads(raw)
    name=request.get('name');access=request.get('access');device=request.get('volume')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):raise ValueError('Invalid share name')
    if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):raise ValueError('Invalid access policy')
    # Verify users exist in Samba and Linux before creating any directory.
    samba={line.split(':',1)[0] for line in run(['/usr/bin/pdbedit','-L']).stdout.splitlines()}
    for user in access:
        if user not in samba:raise ValueError('Samba account not found: '+user)
        pwd.getpwnam(user)
    mount=check_volume(device)
    current=read_db()
    if any(item.get('name','').casefold()==name.casefold() for item in current):raise ValueError('Share already exists')
    # Samba's own configuration may include external shares; reject collisions.
    existing=run(['/usr/bin/testparm','-s']).stdout
    if any(line.strip().casefold()=='['+name.casefold()+']' for line in existing.splitlines()):raise ValueError('Share name already used by Samba')
    # No preexisting folder is ever adopted or modified by this operation.
    root=mount/'PiNAS Shares'
    if root.is_symlink():raise ValueError('Unsafe share root')
    root.mkdir(mode=0o711,exist_ok=True)
    if root.stat().st_uid!=0 or (root.stat().st_mode & 0o022):raise ValueError('Share root must be root-owned and not group/world writable')
    folder=root/name
    if folder.exists() or folder.is_symlink():raise ValueError('Folder already exists; choose a different name')
    if not pathlib.Path('/usr/bin/setfacl').exists():raise ValueError('POSIX ACL tools are required (install acl)')
    # Validate smb.conf can be managed before changing filesystem.
    original=SMB.read_text()
    include='   include = /etc/samba/pinas-shares.conf'
    if include not in original:
        if not re.search(r'(?im)^\s*\[global\]\s*$',original):raise ValueError('Samba [global] section missing')
        amended=re.sub(r'(?im)^(\s*\[global\]\s*)$',r'\1\n'+include,original,count=1)
    else:amended=original
    # Explicit per-user access; default deny for other NAS accounts.
    ro=[u for u,p in access.items() if p=='ro'];rw=[u for u,p in access.items() if p=='rw']
    stanza='\n['+name+']\n   path = '+str(folder)+'\n   browseable = yes\n   guest ok = no\n   read only = yes\n   valid users = '+', '.join(access)+'\n'
    if rw:stanza+='   write list = '+', '.join(rw)+'\n'
    stanza+='   create mask = 0660\n   directory mask = 0770\n   follow symlinks = no\n   wide links = no\n'
    oldconf=CONF.read_text() if CONF.exists() else ''
    if '['+name+']' in oldconf:raise ValueError('Duplicate managed share')
    folder.mkdir(mode=0o700)
    try:
        # Root-owned folder; Samba creates files as authenticated Unix users.
        os.chown(folder,0,0)
        os.chmod(folder,0o700)
        acl=['u::rwx','g::---','o::---','m::rwx']+[f'u:{u}:'+('rwx' if p=='rw' else 'r-x') for u,p in access.items()]
        default=['d:'+entry for entry in acl]
        run(['/usr/bin/setfacl','-m',','.join(acl+default),str(folder)])
        if amended!=original:atomic(SMB,amended,0o644)
        atomic(CONF,oldconf+stanza,0o644)
        run(['/usr/bin/testparm','-s'])
        run(['/usr/bin/systemctl','reload','smbd'])
        current.append({'name':name,'volume_label':mount.name,'volume':device,'access':access})
        atomic(DB,json.dumps(current,indent=2),0o600)
    except Exception:
        atomic(CONF,oldconf,0o644)
        if amended!=original:atomic(SMB,original,0o644)
        try:run(['/usr/bin/systemctl','reload','smbd'])
        except Exception:pass
        try:folder.rmdir()
        except OSError:pass
        raise
    print(json.dumps({'ok':True,'name':name}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

NAS_FILES_HELPER = r"""#!/usr/bin/env python3
# Privileged, narrow file broker. Authentication against Samba passdb; filesystem
# operations executed as the NAS user's actual UID/GID and supplementary groups.
import base64, hashlib, hmac, json, os, pathlib, pwd, re, stat, subprocess, sys
DB=pathlib.Path('/var/lib/pinas/shares.json')
def md4(message):
    # NT hash is MD4(UTF-16LE password). Samba uses NT hashes for SMB auth.
    import struct
    original=len(message);message+=b'\x80';message+=b'\0'*((56-len(message)%64)%64)+struct.pack('<Q',original*8)
    a,b,c,d=0x67452301,0xefcdab89,0x98badcfe,0x10325476
    def rol(v,n):return ((v<<n)|(v>>(32-n)))&0xffffffff
    for offset in range(0,len(message),64):
        x=struct.unpack('<16I',message[offset:offset+64]);aa,bb,cc,dd=a,b,c,d
        for j in range(48):
            if j<16:f=(b&c)|(~b&d);k=j;shift=[3,7,11,19][j%4];constant=0
            elif j<32:f=(b&c)|(b&d)|(c&d);k=(j%4)*4+j//4-4;shift=[3,5,9,13][j%4];constant=0x5a827999
            else:f=b^c^d;k=[0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15][j-32];shift=[3,9,11,15][j%4];constant=0x6ed9eba1
            value=rol((a+f+x[k]+constant)&0xffffffff,shift);a,b,c,d=d,value,b,c
        a=(a+aa)&0xffffffff;b=(b+bb)&0xffffffff;c=(c+cc)&0xffffffff;d=(d+dd)&0xffffffff
    return struct.pack('<4I',a,b,c,d).hex().upper()
def samba_hash(user):
    p=subprocess.run(['/usr/bin/pdbedit','-Lw',user],capture_output=True,text=True,timeout=8)
    if p.returncode:raise ValueError('Unknown NAS account')
    for line in p.stdout.splitlines():
        fields=line.split(':')
        if len(fields)>4 and fields[0]==user and re.fullmatch('[A-Fa-f0-9]{32}',fields[3]):return fields[3].upper()
    raise ValueError('NAS account has no valid Samba password')
def valid_user(user):
    if not isinstance(user,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',user):raise ValueError('Invalid user')
    person=pwd.getpwnam(user)
    if person.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):raise ValueError('Not a PiNAS NAS user')
    if samba_hash(user)=='':raise ValueError('Not a Samba user')
    return person
def shares_for(user):
    entries=json.loads(DB.read_text())
    return [s for s in entries if isinstance(s,dict) and s.get('access',{}).get(user) in ('ro','rw')]
def drop(person):
    os.initgroups(person.pw_name,person.pw_gid);os.setgid(person.pw_gid);os.setuid(person.pw_uid)
def safe_path(root,relative):
    if not isinstance(relative,str) or len(relative)>1000 or relative.startswith('/') or '\\' in relative or '\x00' in relative:raise ValueError('Invalid path')
    parts=relative.split('/') if relative else []
    if any(x in ('','.','..') or x.startswith('.pinas-upload-') for x in parts):raise ValueError('Invalid path')
    # Reject symlinks at every level, including the leaf. Never follow them.
    cur=root
    for part in parts:
        cur=cur/part
        if cur.is_symlink():raise ValueError('Symbolic links are not accessible')
    if not cur.resolve(strict=False).is_relative_to(root.resolve(strict=True)):raise ValueError('Path outside share')
    return cur
def main():
    if os.geteuid()!=0:raise ValueError('Root required')
    raw=sys.stdin.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise ValueError('Request too large')
    q=json.loads(raw);action=q.get('action');user=q.get('username');person=valid_user(user)
    if action=='authenticate':
        password=q.get('password')
        if not isinstance(password,str) or len(password)>256:raise ValueError('Invalid password')
        print('true' if hmac.compare_digest(md4(password.encode('utf-16le')),samba_hash(user)) else 'false');return
    allowed=shares_for(user)
    if action=='shares':
        print(json.dumps({'shares':[{'name':s['name'],'read_only':s['access'][user]=='ro'} for s in allowed]}));return
    share=q.get('share');s=next((x for x in allowed if x['name']==share),None)
    if s is None:raise ValueError('Share not accessible')
    # Root path derived exclusively from privileged share metadata, not browser paths.
    root=pathlib.Path(s['volume_label']) if False else None
    # Resolve mount from device, and confirm it is still the same mounted filesystem.
    device=s['volume'];p=subprocess.run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device],capture_output=True,text=True,timeout=5)
    targets=p.stdout.strip().splitlines()
    if p.returncode or len(targets)!=1:raise ValueError('Share storage is offline')
    mount=pathlib.Path(targets[0]).resolve(strict=True)
    if str(mount)=='/' or str(mount).startswith(('/etc/','/var/','/usr/','/home/','/boot/')):raise ValueError('Protected mount')
    root=mount/'PiNAS Shares'/s['name']
    if root.is_symlink() or not root.is_dir():raise ValueError('Share folder unavailable')
    relative=q.get('path','');target=safe_path(root,relative)
    writable=s['access'][user]=='rw'
    if action in ('mkdir','delete','rename','move','copy','upload','upload_start','upload_chunk','upload_finish','upload_cancel') and not writable:raise ValueError('Read-only share')
    drop(person)
    # All operations below run with the NAS user's UID/GID. Uploads are staged
    # in the destination directory, then published by an atomic rename.
    def valid_name(name):
        if not isinstance(name,str) or not name or len(name)>255 or name in ('.','..') or '/' in name or '\\' in name or '\x00' in name or name.startswith('.pinas-upload-'):raise ValueError('Invalid file name')
        return name
    def destination(relative):
        dest=safe_path(root,relative)
        if dest==root or dest.exists() or dest.is_symlink():raise ValueError('Destination already exists')
        if not dest.parent.is_dir():raise ValueError('Destination folder does not exist')
        return dest
    if action in ('rename','move','copy'):
        if target==root or not target.exists():raise ValueError('Invalid source')
        if action=='rename':
            dest=destination('/'.join(filter(None,[relative.rsplit('/',1)[0] if '/' in relative else '',valid_name(q.get('name'))])))
        else:
            dest=destination(q.get('dest',''))
        if target.is_dir() and (dest==target or target in dest.parents):raise ValueError('Cannot place folder inside itself')
        if action=='copy':
            import shutil
            if target.is_dir():
                # Reject links anywhere in the tree and cap total copy size.
                total=0
                for directory,dirs,files in os.walk(target,followlinks=False):
                    for name in dirs+files:
                        node=pathlib.Path(directory)/name
                        if node.is_symlink():raise ValueError('Symbolic links cannot be copied')
                        if node.is_file():total+=node.stat().st_size
                        if total>8*1024**3:raise ValueError('Folder copy exceeds 8 GiB safety limit')
                shutil.copytree(target,dest,symlinks=False)
            elif target.is_file():
                with target.open('rb') as src, dest.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            else:raise ValueError('Unsupported file type')
        else:
            # Same-share only; atomic rename prevents partial moves.
            if target.is_file():
                os.link(target,dest,follow_symlinks=False);target.unlink()
            else:target.rename(dest)
        print('{"ok":true}');return
    if action=='upload_start':
        name=valid_name(q.get('name'))
        if not target.is_dir():raise ValueError('Not a folder')
        destination('/'.join(filter(None,[relative,name])))
        size=q.get('size')
        if not isinstance(size,int) or size<0 or size>100*1024**3:raise ValueError('Invalid upload size')
        import secrets
        token=secrets.token_hex(20)
        staging=target/('.pinas-upload-'+token)
        fd=os.open(staging,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        meta=target/('.pinas-upload-'+token+'.json')
        fd=os.open(meta,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'name':name,'size':size,'path':relative},f)
        print(json.dumps({'token':token}));return
    if action in ('upload_chunk','upload_finish','upload_cancel'):
        token=q.get('token','')
        if not isinstance(token,str) or not re.fullmatch('[0-9a-f]{40}',token):raise ValueError('Invalid transfer token')
        stage=target/('.pinas-upload-'+token)
        meta=target/('.pinas-upload-'+token+'.json')
        if stage.is_symlink() or meta.is_symlink() or not stage.is_file() or not meta.is_file():raise ValueError('Unknown transfer')
        details=json.loads(meta.read_text());name=valid_name(details['name']);size=details['size']
        if details.get('path')!=relative:raise ValueError('Transfer location mismatch')
        if action=='upload_cancel':stage.unlink();meta.unlink();print('{"ok":true}');return
        if action=='upload_chunk':
            content=q.get('content','');offset=q.get('offset')
            if not isinstance(content,str) or len(content)>700000 or not isinstance(offset,int):raise ValueError('Invalid chunk')
            payload=base64.b64decode(content,validate=True)
            if len(payload)>512*1024 or offset!=stage.stat().st_size or offset+len(payload)>size:raise ValueError('Chunk offset or size mismatch')
            with stage.open('ab') as f:f.write(payload)
            print(json.dumps({'offset':offset+len(payload)}));return
        if stage.stat().st_size!=size:raise ValueError('Upload incomplete')
        dest=destination('/'.join(filter(None,[relative,name])))
        # Hard-link is no-clobber and atomic on the same filesystem.
        os.link(stage,dest,follow_symlinks=False);stage.unlink();meta.unlink()
        print('{"ok":true}');return
    if action=='download_chunk':
        offset=q.get('offset');size=q.get('size')
        if not isinstance(offset,int) or offset<0 or not isinstance(size,int) or size<1 or size>512*1024:raise ValueError('Invalid download range')
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode):raise ValueError('Not a regular file')
        total=target.stat().st_size
        with target.open('rb') as f:f.seek(offset);chunk=f.read(size)
        print(json.dumps({'content':base64.b64encode(chunk).decode(),'total':total}));return
    if action=='list':
        if not target.is_dir():raise ValueError('Not a folder')
        entries=[]
        for child in sorted(target.iterdir(),key=lambda x:x.name.casefold()):
            if child.is_symlink() or child.name.startswith('.pinas-upload-'):continue
            try:st=child.stat()
            except OSError:continue
            if stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode):entries.append({'name':child.name,'dir':stat.S_ISDIR(st.st_mode),'size':st.st_size})
            if len(entries)>=1000:break
        print(json.dumps({'entries':entries}));return
    if action=='mkdir':
        name=q.get('name','');dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..'):raise ValueError('Invalid folder name')
        dest.mkdir(mode=0o770);print('{"ok":true}');return
    if action=='delete':
        if target==root:raise ValueError('Cannot delete share root')
        if target.is_dir():target.rmdir()
        elif target.is_file():target.unlink()
        else:raise ValueError('Not a regular file or empty folder')
        print('{"ok":true}');return
    if action=='download':
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode) or target.stat().st_size>3*1024*1024:raise ValueError('Only files up to 3 MB supported in this test build')
        with target.open('rb') as f:content=base64.b64encode(f.read()).decode()
        print(json.dumps({'content':content}));return
    if action=='upload':
        name=q.get('name','');content=q.get('content','')
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..') or not isinstance(content,str) or len(content)>4*1024*1024+16:raise ValueError('Invalid upload')
        dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not target.is_dir():raise ValueError('Not a directory')
        payload=base64.b64decode(content,validate=True)
        if len(payload)>3*1024*1024:raise ValueError('Upload exceeds 3 MB')
        fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o660)
        with os.fdopen(fd,'wb') as f:f.write(payload)
        print('{"ok":true}');return
    raise ValueError('Unsupported action')
if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
"""

APT_INDEX_HELPER = r"""#!/usr/bin/env python3
import os,subprocess,sys
from pathlib import Path
ALLOWED={'off':None,'daily':'*-*-* 01:00:00','weekly':'Fri *-*-* 01:00:00','monthly':'*-*-28 01:00:00'}
def run(cmd,timeout=30):
    p=subprocess.run(cmd,timeout=timeout,check=False)
    if p.returncode:sys.exit(p.returncode)
def main():
    if os.geteuid()!=0:sys.exit('Root access required')
    args=sys.argv[1:]
    if len(args)==2 and args[0]=='schedule' and args[1] in ALLOWED:
        schedule=args[1];calendar=ALLOWED[schedule]
        timer=Path('/etc/systemd/system/pinas-auto-updates.timer')
        if calendar:
            timer.write_text('[Unit]\nDescription=PiNAS automatic OS updates\n[Timer]\nOnCalendar='+calendar+'\nPersistent=true\nUnit=pinas-auto-updates.service\n[Install]\nWantedBy=timers.target\n')
        run(['systemctl','daemon-reload'])
        if calendar:
            run(['systemctl','enable','--now','pinas-auto-updates.timer'])
            run(['systemctl','restart','pinas-auto-updates.timer'])
        else:
            run(['systemctl','disable','--now','pinas-auto-updates.timer']) if timer.exists() else None
            timer.unlink(missing_ok=True)
            run(['systemctl','daemon-reload'])
        marker=Path('/var/lib/pinas/update-schedule');marker.write_text(schedule+'\n');os.chmod(marker,0o644)
        return
    if args==['automatic']:
        # Only the systemd oneshot invokes this command, not the web service account.
        run(['/usr/bin/apt-get','update'],210)
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
        return
    if args==['upgrade']:
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
    elif args==['refresh']:
        run(['/usr/bin/apt-get','update'],210)
    else:sys.exit('Unsupported operation')
if __name__=='__main__':main()
"""

NAS_STORAGE_HELPER='#!/usr/bin/env python3\n"""PiNAS RC13 restricted, non-destructive storage adoption helper."""\nimport json,os,pathlib,re,subprocess,sys,uuid\nfrom pathlib import Path\n\ndef run(*args,timeout=15):\n    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)\n    if p.returncode:raise ValueError((p.stderr or \'Storage command failed\').strip()[-500:])\n    return p.stdout.strip()\n\ndef main():\n    if os.geteuid()!=0 or sys.argv[1:]!=[\'adopt\']:raise ValueError(\'Unsupported storage operation\')\n    data=json.loads(sys.stdin.read(4096));device=data.get(\'device\')\n    if not isinstance(device,str) or not re.fullmatch(r\'/dev/[A-Za-z0-9_./-]{1,90}\',device) or \'..\' in device:raise ValueError(\'Invalid device\')\n    path=Path(device)\n    if not path.is_block_device():raise ValueError(\'Device is not a block device\')\n    # The privileged helper independently identifies eligible physical disks.\n    roots=json.loads(run(\'lsblk\',\'-J\',\'-b\',\'-o\',\'NAME,PATH,TYPE,FSTYPE,UUID,MOUNTPOINTS,RO,PKNAME\')).get(\'blockdevices\',[])\n    bypath={};byname={};parents={}\n    def walk(node,parent=None):\n        name=node.get(\'name\');bypath[node.get(\'path\')]=node;byname[name]=node\n        if parent:parents[name]=parent\n        for child in node.get(\'children\') or []:walk(child,name)\n    for root in roots:walk(root)\n    node=bypath.get(str(path.resolve())) or bypath.get(device)\n    if not node or node.get(\'type\') not in (\'part\',\'disk\') or node.get(\'ro\'):raise ValueError(\'Not an eligible writable disk or partition\')\n    def root_for(n):\n        seen=set()\n        while n.get(\'name\') in parents:\n            if n[\'name\'] in seen:raise ValueError(\'Invalid device topology\')\n            seen.add(n[\'name\']);n=byname[parents[n[\'name\']]]\n        return n\n    disk=root_for(node)\n    if disk.get(\'type\')!=\'disk\' or disk.get(\'ro\') or str(disk.get(\'name\',\'\')).startswith((\'loop\',\'zram\',\'ram\',\'nbd\',\'sr\',\'fd\')):raise ValueError(\'Unsupported backing device\')\n    # Reject any physical disk carrying the root or boot filesystems.\n    protected={\'/\',\'/boot\',\'/boot/firmware\',\'/boot/efi\'}\n    def contains_system(n):\n        if any(m in protected for m in (n.get(\'mountpoints\') or []) if m):return True\n        return any(contains_system(c) for c in n.get(\'children\') or [])\n    if contains_system(disk):raise ValueError(\'Operating system storage is protected\')\n    for mount in protected:\n        src=run(\'findmnt\',\'-n\',\'-o\',\'SOURCE\',\'--target\',mount).split(\'[\',1)[0]\n        if src and src in bypath and root_for(bypath[src]).get(\'name\')==disk.get(\'name\'):\n            raise ValueError(\'Operating system storage is protected\')\n    fs=run(\'blkid\',\'-s\',\'TYPE\',\'-o\',\'value\',device)\n    uid=run(\'blkid\',\'-s\',\'UUID\',\'-o\',\'value\',device)\n    if fs not in (\'ext4\',\'xfs\',\'btrfs\') or not re.fullmatch(r\'[A-Za-z0-9-]{8,64}\',uid):raise ValueError(\'Supported filesystem and UUID required\')\n    # Reject RAID/LVM/crypto members and nested volume layouts.\n    if node.get(\'type\')==\'disk\' and node.get(\'children\'):raise ValueError(\'Choose a filesystem partition, not its parent disk\')\n    if node.get(\'children\'):raise ValueError(\'Complex volume layout not supported\')\n    mountpoints=[m for m in node.get(\'mountpoints\') or [] if m]\n    if len(mountpoints)>1:raise ValueError(\'Multiple mountpoints require manual review\')\n    if mountpoints and not str(mountpoints[0]).startswith(\'/mnt/pinas/\'):\n        raise ValueError(\'Filesystem is already mounted elsewhere; manage it manually to avoid disrupting applications\')\n    target=Path(\'/mnt/pinas\')/uid\n    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir())) and str(target) not in mountpoints):raise ValueError(\'Mount destination is not empty\')\n    fstab=Path(\'/etc/fstab\');original=fstab.read_text();entries=[line.split() for line in original.splitlines() if line.strip() and not line.lstrip().startswith(\'#\')]\n    for e in entries:\n        if len(e)>=2 and (e[0] in (device,\'UUID=\'+uid,\'/dev/disk/by-uuid/\'+uid) or e[1]==str(target)):\n            if e[0]==\'UUID=\'+uid and e[1]==str(target):\n                if str(target) not in mountpoints:run(\'mount\',str(target),timeout=25)\n                print(json.dumps({\'ok\':True,\'mount\':str(target),\'existing\':True}));return\n            raise ValueError(\'Existing fstab configuration requires manual review\')\n    target.parent.mkdir(parents=True,exist_ok=True)\n    target.mkdir(mode=0o755,exist_ok=True)\n    options=\'defaults,nofail,noatime,x-systemd.device-timeout=10s\'\n    entry=f\'UUID={uid} {target} {fs} {options} 0 {2 if fs=="ext4" else 0} # PiNAS managed\\\\n\'\n    entry=entry.replace(\'\\\\n\',\'\\n\')\n    backup=fstab.with_name(\'fstab.pinas-\'+uuid.uuid4().hex[:12]+\'.bak\')\n    backup.write_text(original);os.chmod(backup,0o600)\n    temp=fstab.with_name(\'.fstab.pinas-\'+uuid.uuid4().hex)\n    try:\n        temp.write_text(original.rstrip(\'\\n\')+\'\\n\'+entry);os.chmod(temp,0o644)\n        os.replace(temp,fstab)\n        run(\'systemctl\',\'daemon-reload\',timeout=15)\n        run(\'mount\',str(target),timeout=25)\n        actual=run(\'findmnt\',\'-n\',\'-o\',\'UUID\',\'--target\',str(target))\n        if actual!=uid:raise ValueError(\'Mounted filesystem UUID verification failed\')\n    except Exception:\n        fstab.write_text(original)\n        try:run(\'systemctl\',\'daemon-reload\')\n        except Exception:pass\n        raise\n    print(json.dumps({\'ok\':True,\'mount\':str(target)}))\nif __name__==\'__main__\':\n    try:main()\n    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)\n'

SMART_HEALTH_HELPER = """#!/usr/bin/env python3
import json,os,shutil,subprocess,sys
from pathlib import Path
def main():
    if os.geteuid()!=0 or len(sys.argv)!=1:
        raise ValueError('Unsupported operation')
    smartctl=shutil.which('smartctl')
    if not smartctl:
        print(json.dumps({'installed':False,'drives':[]}));return
    p=subprocess.run(['lsblk','-J','-b','-o','NAME,PATH,TYPE,MODEL,TRAN'],capture_output=True,text=True,timeout=8,check=True)
    drives=[]
    for disk in json.loads(p.stdout).get('blockdevices',[]):
        if disk.get('type')!='disk':continue
        device=disk.get('path','')
        if not isinstance(device,str) or not device.startswith('/dev/') or not Path(device).is_block_device():continue
        if disk.get('name','').startswith(('loop','zram','ram','nbd','sr','fd')):continue
        entry={'device':device,'model':disk.get('model') or disk.get('name'),'status':'Unavailable','temperature':None}
        try:
            result=subprocess.run([smartctl,'-j','-H','-A',device],capture_output=True,text=True,timeout=12)
            data=json.loads(result.stdout)
            health=data.get('smart_status',{}).get('passed')
            if health is True:entry['status']='Healthy'
            elif health is False:entry['status']='Warning'
            temp=data.get('temperature',{}).get('current')
            if isinstance(temp,(int,float)) and -20<=temp<=120:entry['temperature']=temp
            if data.get('smart_support',{}).get('available') is False:entry['status']='Unsupported'
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        drives.append(entry)
    print(json.dumps({'installed':True,'drives':drives}))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

def install(args):
    if sys.platform!='linux' or os.geteuid()!=0:sys.exit('Install requires Linux and sudo/root.')
    if not Path('/etc/os-release').exists():sys.exit('Unsupported OS')
    osinfo=read('/etc/os-release')
    if 'debian' not in osinfo.lower() and 'raspbian' not in osinfo.lower():sys.exit('Requires Raspberry Pi OS / Debian family')
    if not args.skip_packages:
        print('Installing NAS dependencies (requires network and may take time)...',flush=True)
        subprocess.run(['apt-get','update'],check=True)
        subprocess.run(['apt-get','install','-y','samba','xfsprogs','btrfs-progs','mdadm','parted','util-linux','e2fsprogs','avahi-daemon','acl','openssl'],check=True)
    target=Path('/opt/pinas');target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(__file__).resolve(),target/'pinas.py');os.chmod(target/'pinas.py',0o755)
    if subprocess.run(['id','-u','pinas'],capture_output=True).returncode!=0:
        subprocess.run(['useradd','--system','--home-dir','/var/lib/pinas','--shell','/usr/sbin/nologin','pinas'],check=True)
    DATA.mkdir(parents=True,exist_ok=True);os.chmod(DATA,0o700)
    subprocess.run(['chown','pinas:pinas',str(DATA)],check=True)
    helper=Path('/usr/local/libexec/pinas-apply-hostname')
    helper.parent.mkdir(parents=True,exist_ok=True)
    helper.write_text(HOSTNAME_HELPER)
    os.chmod(helper,0o755)
    unit='''[Unit]\nDescription=Apply validated PiNAS device hostname\nAfter=systemd-hostnamed.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /usr/local/libexec/pinas-apply-hostname\nNoNewPrivileges=true\nProtectHome=true\nPrivateTmp=true\n'''
    Path('/etc/systemd/system/pinas-hostname.service').write_text(unit)
    path_unit='''[Unit]\nDescription=Apply PiNAS hostname when configuration changes\n[Path]\nPathChanged=/var/lib/pinas/config.json\nUnit=pinas-hostname.service\n[Install]\nWantedBy=multi-user.target\n'''
    Path('/etc/systemd/system/pinas-hostname.path').write_text(path_unit)
    user_helper=Path('/usr/local/libexec/pinas-nas-user')
    user_helper.write_text(NAS_USER_HELPER)
    os.chown(user_helper,0,0);os.chmod(user_helper,0o700)
    sudoers=Path('/etc/sudoers.d/pinas-nas-user')
    sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-user create *, /usr/local/libexec/pinas-nas-user password *, /usr/local/libexec/pinas-nas-user list\n')
    os.chown(sudoers,0,0);os.chmod(sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(sudoers)],capture_output=True).returncode:
        sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS sudoers configuration')
    share_helper=Path('/usr/local/libexec/pinas-nas-share')
    share_helper.write_text(NAS_SHARE_HELPER)
    os.chown(share_helper,0,0);os.chmod(share_helper,0o700)
    share_sudoers=Path('/etc/sudoers.d/pinas-nas-share')
    share_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-share list, /usr/local/libexec/pinas-nas-share create\n')
    os.chown(share_sudoers,0,0);os.chmod(share_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(share_sudoers)],capture_output=True).returncode:
        share_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS share sudoers configuration')
    files_helper=Path('/usr/local/libexec/pinas-nas-files')
    files_helper.write_text(NAS_FILES_HELPER)
    os.chown(files_helper,0,0);os.chmod(files_helper,0o700)
    files_sudoers=Path('/etc/sudoers.d/pinas-nas-files')
    files_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-files\n')
    os.chown(files_sudoers,0,0);os.chmod(files_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(files_sudoers)],capture_output=True).returncode:
        files_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS file helper sudoers configuration')
    storage_helper=Path('/usr/local/libexec/pinas-nas-storage')
    storage_helper.write_text(NAS_STORAGE_HELPER)
    os.chown(storage_helper,0,0);os.chmod(storage_helper,0o700)
    storage_sudoers=Path('/etc/sudoers.d/pinas-nas-storage')
    storage_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-storage adopt\n')
    os.chown(storage_sudoers,0,0);os.chmod(storage_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(storage_sudoers)],capture_output=True).returncode:
        storage_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS storage sudoers configuration')
    smart_helper=Path('/usr/local/libexec/pinas-smart-health')
    smart_helper.write_text(SMART_HEALTH_HELPER)
    os.chown(smart_helper,0,0);os.chmod(smart_helper,0o700)
    smart_sudoers=Path('/etc/sudoers.d/pinas-smart-health')
    smart_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-smart-health\n')
    os.chown(smart_sudoers,0,0);os.chmod(smart_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(smart_sudoers)],capture_output=True).returncode:
        smart_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS SMART sudoers configuration')
    apt_helper=Path('/usr/local/libexec/pinas-apt-index')
    apt_helper.write_text(APT_INDEX_HELPER)
    os.chown(apt_helper,0,0);os.chmod(apt_helper,0o700)
    apt_sudoers=Path('/etc/sudoers.d/pinas-apt-index')
    apt_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-apt-index refresh, /usr/local/libexec/pinas-apt-index upgrade, /usr/local/libexec/pinas-apt-index schedule off, /usr/local/libexec/pinas-apt-index schedule daily, /usr/local/libexec/pinas-apt-index schedule weekly, /usr/local/libexec/pinas-apt-index schedule monthly\n')
    os.chown(apt_sudoers,0,0);os.chmod(apt_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(apt_sudoers)],capture_output=True).returncode:
        apt_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS APT sudoers configuration')
    auto_service=Path('/etc/systemd/system/pinas-auto-updates.service')
    auto_service.write_text('[Unit]\nDescription=PiNAS scheduled OS updates\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=oneshot\nExecStart=/usr/local/libexec/pinas-apt-index automatic\nEnvironment=DEBIAN_FRONTEND=noninteractive\n')
    os.chown(auto_service,0,0);os.chmod(auto_service,0o644)
    # Existing schedule is preserved when upgrading PiNAS.
    # Generate a persistent per-install certificate; never replace it on upgrades.
    if not TLS_CERT.exists() or not TLS_KEY.exists():
        if TLS_CERT.exists() or TLS_KEY.exists():sys.exit('Incomplete TLS certificate pair; resolve manually before installing')
        if not shutil.which('openssl'):sys.exit('OpenSSL required for initial TLS certificate generation')
        hostname=load().get('hostname','pinas')
        if not valid_hostname(hostname):hostname='pinas'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','825',
            '-keyout',str(TLS_KEY),'-out',str(TLS_CERT),'-subj',f'/CN={hostname}.local',
            '-addext',f'subjectAltName=DNS:{hostname}.local,DNS:localhost,IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL)
    for f,mode in ((TLS_CERT,0o644),(TLS_KEY,0o600)):
        os.chown(f,0 if f==TLS_CERT else __import__('pwd').getpwnam('pinas').pw_uid,0 if f==TLS_CERT else __import__('grp').getgrnam('pinas').gr_gid)
        os.chmod(f,mode)
    bind_host='0.0.0.0' if args.lan else '127.0.0.1' 
    # TEMPORARY RC9.2: sudo inherits the service mount namespace. A root helper
    # cannot write /etc/passwd, /etc/group or Samba state with ProtectSystem=strict.
    # Replace sudo delegation with an independently sandboxed privileged service.
    service='''[Unit]\nDescription=PiNAS prototype web dashboard\nAfter=network.target\n[Service]\nType=simple\nUser=pinas\nGroup=pinas\nExecStart=/usr/bin/python3 /opt/pinas/pinas.py --serve --tls --host %s --port %d\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=false\nProtectSystem=false\nReadWritePaths=/var/lib/pinas\nPrivateTmp=true\n[Install]\nWantedBy=multi-user.target\n'''%(bind_host,args.port)
    Path('/etc/systemd/system/pinas.service').write_text(service)
    subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','enable','--now','pinas-hostname.path'],check=True);subprocess.run(['systemctl','start','pinas-hostname.service'],check=True);subprocess.run(['systemctl','enable','pinas.service'],check=True);subprocess.run(['systemctl','restart','pinas.service'],check=True)
    print(f'PiNAS installed. For localhost access: https://127.0.0.1:{args.port} (self-signed certificate)')
    if args.lan:print(f'LAN TLS MODE: open https://<PI-IP>:{args.port}. Certificate is self-signed; use the .local hostname for name matching. Do not expose this port to the internet.')
    else:print('Localhost-only mode; re-run installer with --lan to enable direct LAN access for testing.')

def main():
    ap=argparse.ArgumentParser(description='PiNAS Raspberry Pi NAS prototype')
    ap.add_argument('--lan',action='store_true',help='Bind HTTPS server to LAN interfaces');ap.add_argument('--install',action='store_true');ap.add_argument('--serve',action='store_true');ap.add_argument('--tls',action='store_true');ap.add_argument('--skip-packages',action='store_true');ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=8765)
    a=ap.parse_args()
    if a.install:install(a);return
    if a.serve:
        if a.host not in ('127.0.0.1','::1','0.0.0.0'):sys.exit('Unsupported bind address.')
        if a.host=='0.0.0.0' and not a.tls:sys.exit('LAN listening requires HTTPS (--tls)')
        server=ThreadingHTTPServer((a.host,a.port),Handler)
        if a.tls:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(TLS_CERT),str(TLS_KEY))
            server.socket=context.wrap_socket(server.socket,server_side=True)
        print('PiNAS running on %s://%s:%s'%('https' if a.tls else 'http',a.host,a.port))
        threading.Thread(target=cpu_sampler,daemon=True).start();server.serve_forever();return
    ap.print_help()
if __name__=='__main__':main(),'ipc
            name=data.get('name');password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):
                self.json({'error':'Invalid share name.'},400);return
            if not isinstance(password,str) or not verify(password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not any(isinstance(item,dict) and item.get('name')==name for item in nas_share_list()):
                self.json({'error':'Only PiNAS-managed shares can be removed.'},404);return
            try:delete_nas_share(name)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name,'files_preserved':True});return
        if path=='/api/nas-shares':
            name=data.get('name');volume=data.get('volume');access=data.get('access');admin_password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):
                self.json({'error':'Choose a share name of 1–32 letters, digits, spaces, underscores or hyphens.'},400);return
            if not isinstance(volume,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',volume) or '..' in volume:
                self.json({'error':'Invalid storage selection.'},400);return
            if not isinstance(access,dict) or not access or len(access)>64 or any(not isinstance(k,str) or v not in ('ro','rw') for k,v in access.items()):
                self.json({'error':'Assign at least one user Read Only or Read & Write access.'},400);return
            if not isinstance(admin_password,str) or not verify(admin_password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not storage_is_ready():self.json({'error':'A mounted, persistent data filesystem is required.'},409);return
            valid_users={u['name'] for u in nas_user_list()}
            if not set(access).issubset(valid_users):self.json({'error':'One or more users are not valid Samba accounts.'},409);return
            if any(name.casefold()==s.casefold() for s in discover().get('shares',[])):
                self.json({'error':'A share with this name already exists.'},409);return
            try:create_nas_share(name,volume,access)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name});return
        if path=='/api/logout':SESSIONS.pop(token,None);self.json({'ok':True},cookie='pinas_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'+('; Secure' if isinstance(self.connection,ssl.SSLSocket) else ''));return
        if path=='/api/settings':
            theme,accent,font=data.get('theme'),data.get('accent'),data.get('font')
            interval,history=data.get('cpu_interval',cfg.get('cpu_interval',5)),data.get('cpu_history',cfg.get('cpu_history',10))
            session_timeout=data.get('session_timeout',cfg.get('session_timeout',5))
            if theme not in ('light','dark','dark-cb','light-cb') or not isinstance(accent,str) or len(accent)!=7 or accent[0]!='#' or any(c not in '0123456789abcdefABCDEF' for c in accent[1:]) or type(font)!=int or font not in (10,12,14,16) or type(interval)!=int or interval not in (2,5,10) or type(history)!=int or history not in (10,15,30,60) or type(session_timeout)!=int or session_timeout not in (5,10,15,30,60):self.json({'error':'Invalid appearance settings'},400);return
            cfg.update(theme=theme,accent=accent,font=font,cpu_interval=interval,cpu_history=history,session_timeout=session_timeout)
        elif path=='/api/background':
            image=data.get('image')
            if not isinstance(image,str) or len(image)>2_900_000:self.json({'error':'Image too large'},400);return
            if image:
                try:
                    meta,b64=image.split(',',1);mime=meta[5:].split(';',1)[0]
                    if mime not in ('image/jpeg','image/png','image/webp'):raise ValueError()
                    decoded=base64.b64decode(b64,validate=True)
                    if len(decoded)>2*1024*1024:raise ValueError()
                    if not ((mime=='image/jpeg' and decoded.startswith(b'\xff\xd8\xff')) or (mime=='image/png' and decoded.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/webp' and decoded.startswith(b'RIFF') and decoded[8:12]==b'WEBP')):raise ValueError()
                except (ValueError,IndexError):self.json({'error':'Invalid image'},400);return
            cfg['login_background']=image
        save(cfg);self.json({'settings':dict({k:cfg.get(k) for k in ('theme','accent','font','cpu_interval','cpu_history','session_timeout')},has_background=bool(cfg.get('login_background')))} )

HOSTNAME_HELPER = r"""#!/usr/bin/env python3
import json, re, subprocess
from pathlib import Path
try:
    path=Path('/var/lib/pinas/config.json')
    if not path.exists():raise SystemExit(0)
    cfg=json.loads(path.read_text())
    hostname=cfg.get('hostname','')
    if not hostname:raise SystemExit(0)
    if not isinstance(hostname,str) or not 1<=len(hostname)<=63 or not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*',hostname):
        raise ValueError('Invalid hostname')
    current=subprocess.run(['hostname','-s'],capture_output=True,text=True,check=True).stdout.strip()
    if current!=hostname:
        subprocess.run(['/usr/bin/hostnamectl','set-hostname',hostname],check=True,timeout=15)
except (OSError,ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
    raise SystemExit('PiNAS hostname not applied: '+str(exc))
"""

NAS_USER_HELPER = r"""#!/usr/bin/env python3
# Privileged helper. No arbitrary command execution; narrowly scoped account actions.
import grp, json, os, pwd, re, subprocess, sys

def run(argv, **kwargs):
    return subprocess.run(argv, check=True, timeout=20, **kwargs)

def samba_users():
    p=run(['/usr/bin/pdbedit','-L'],capture_output=True,text=True)
    result=[]
    for line in p.stdout.splitlines():
        fields=line.split(':',2)
        if len(fields)>=2 and re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',fields[0]):
            result.append({'name':fields[0],'uid':fields[1]})
    return sorted(result,key=lambda x:x['name'])

if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit(2)
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(samba_users()))
        raise SystemExit(0)
    if len(sys.argv)!=3 or sys.argv[1] not in ('create','password'):raise SystemExit(2)
    name=sys.argv[2]
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',name) or name in ('pinas','root','admin','nobody'):raise SystemExit(2)
    password=sys.stdin.readline(258).rstrip('\n')
    if not 12<=len(password)<=256:raise SystemExit(2)
    if sys.argv[1]=='password':
        group=grp.getgrnam('pinas-nas')
        existing=pwd.getpwnam(name)
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin') or not any(u['name']==name for u in samba_users()):
            raise SystemExit('Not a managed PiNAS Samba user')
        run(['/usr/bin/smbpasswd','-s',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        raise SystemExit(0)
    try:
        group=grp.getgrnam('pinas-nas')
    except KeyError:
        run(['/usr/sbin/groupadd','pinas-nas'])
        group=grp.getgrnam('pinas-nas')
    created=False
    try:
        existing=pwd.getpwnam(name)
    except KeyError:
        existing=None
    if existing:
        # Repair only a partial PiNAS account from a previous failed attempt.
        # Never repurpose unrelated Linux accounts.
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):
            raise SystemExit('Linux account already exists and is not a PiNAS NAS account; choose another username')
        if any(u['name']==name for u in samba_users()):
            raise SystemExit('Samba account already exists; refresh the Users page')
    else:
        run(['/usr/sbin/useradd','--no-create-home','--shell','/usr/sbin/nologin','--gid','pinas-nas',name])
        created=True
    try:
        run(['/usr/bin/smbpasswd','-s','-a',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        run(['/usr/bin/smbpasswd','-e',name],capture_output=True)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        if created:subprocess.run(['/usr/sbin/userdel',name],check=False,timeout=10)
        raise SystemExit('Samba account creation failed: '+str(exc))
"""

NAS_SHARE_HELPER = r"""#!/usr/bin/env python3
# Root-only share broker. Strict input validation and independent mount checks.
import json, os, pathlib, pwd, re, subprocess, sys, tempfile

DB=pathlib.Path('/var/lib/pinas/shares.json')
CONF=pathlib.Path('/etc/samba/pinas-shares.conf')
SMB=pathlib.Path('/etc/samba/smb.conf')

def run(cmd, **kw):
    return subprocess.run(cmd,check=True,timeout=15,capture_output=True,text=True,**kw)

def read_db():
    try:
        value=json.loads(DB.read_text())
        return value if isinstance(value,list) else []
    except (OSError,ValueError):return []

def atomic(path,content,mode=0o600):
    fd,name=tempfile.mkstemp(prefix='.pinas-',dir=str(path.parent))
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'w') as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def check_volume(device):
    if not isinstance(device,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',device) or '..' in device:raise ValueError('Invalid device')
    # Device must be a block device with an approved filesystem.
    p=pathlib.Path(device)
    if not p.is_block_device():raise ValueError('Selected storage is not a block device')
    fs=run(['/usr/bin/lsblk','-n','-o','FSTYPE',device]).stdout.strip().splitlines()
    if not fs or fs[0].strip().lower() not in ('ext4','xfs','btrfs'):raise ValueError('Unsupported filesystem')
    target=run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device]).stdout.strip().splitlines()
    if len(target)!=1:raise ValueError('Disk must have one unambiguous active mount')
    mount=pathlib.Path(target[0]).resolve(strict=True)
    if str(mount) in ('/','/boot','/boot/firmware') or any(str(mount).startswith(prefix) for prefix in ('/etc/','/var/','/usr/','/home/','/opt/','/root/','/proc/','/sys/','/run/')):
        raise ValueError('System storage cannot host NAS shares')
    if not mount.is_dir() or mount.is_symlink():raise ValueError('Invalid mount directory')
    # Confirm mounted persistently via UUID, path or LABEL; do not trust browser data.
    uuid=run(['/usr/sbin/blkid','-s','UUID','-o','value',device]).stdout.strip()
    entries=[line.split() for line in pathlib.Path('/etc/fstab').read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not any(len(e)>=2 and e[1]==str(mount) and e[0] in (device,'UUID='+uuid,'/dev/disk/by-uuid/'+uuid) for e in entries):
        raise ValueError('Disk is not persistently configured in fstab')
    # Reject root device even when mounted at a second location.
    rootdev=run(['/usr/bin/findmnt','-n','-o','SOURCE','/']).stdout.strip()
    if rootdev.startswith('/dev/'):
        rootparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',rootdev]).stdout.split())
        selectedparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',device]).stdout.split())
        if rootparents & selectedparents:raise ValueError('Operating system disk is protected')
    return mount

def main():
    if os.geteuid()!=0:raise ValueError('Root helper required')
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(read_db()));return
    if len(sys.argv)==2 and sys.argv[1]=='delete':
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('Request too large')
        request=json.loads(raw);name=request.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):raise ValueError('Invalid share name')
        current=read_db()
        matches=[item for item in current if isinstance(item,dict) and item.get('name')==name]
        if len(matches)!=1:raise ValueError('Share is not managed by PiNAS')
        oldconf=CONF.read_text()
        # Match only a complete, exact managed Samba section; never touch unrelated shares.
        section=re.compile(r'(?m)^\['+re.escape(name)+r'\][ \t]*\n(?:(?!\[).*(?:\n|$))*')
        found=list(section.finditer(oldconf))
        if len(found)!=1:raise ValueError('Managed Samba share section missing or ambiguous')
        updated=oldconf[:found[0].start()]+oldconf[found[0].end():]
        olddb=DB.read_text()
        try:
            atomic(CONF,updated,0o644)
            run(['/usr/bin/testparm','-s'])
            run(['/usr/bin/systemctl','reload','smbd'])
            atomic(DB,json.dumps([item for item in current if not (isinstance(item,dict) and item.get('name')==name)],indent=2),0o600)
        except Exception:
            atomic(CONF,oldconf,0o644)
            atomic(DB,olddb,0o600)
            try:run(['/usr/bin/systemctl','reload','smbd'])
            except Exception:pass
            raise
        # Deliberately leave the share directory, ACLs and files untouched.
        print(json.dumps({'ok':True,'files_preserved':True}));return
    if len(sys.argv)!=2 or sys.argv[1]!='create':raise ValueError('Unsupported action')
    raw=sys.stdin.read(8193)
    if len(raw)>8192:raise ValueError('Request too large')
    request=json.loads(raw)
    name=request.get('name');access=request.get('access');device=request.get('volume')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):raise ValueError('Invalid share name')
    if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):raise ValueError('Invalid access policy')
    # Verify users exist in Samba and Linux before creating any directory.
    samba={line.split(':',1)[0] for line in run(['/usr/bin/pdbedit','-L']).stdout.splitlines()}
    for user in access:
        if user not in samba:raise ValueError('Samba account not found: '+user)
        pwd.getpwnam(user)
    mount=check_volume(device)
    current=read_db()
    if any(item.get('name','').casefold()==name.casefold() for item in current):raise ValueError('Share already exists')
    # Samba's own configuration may include external shares; reject collisions.
    existing=run(['/usr/bin/testparm','-s']).stdout
    if any(line.strip().casefold()=='['+name.casefold()+']' for line in existing.splitlines()):raise ValueError('Share name already used by Samba')
    # No preexisting folder is ever adopted or modified by this operation.
    root=mount/'PiNAS Shares'
    if root.is_symlink():raise ValueError('Unsafe share root')
    root.mkdir(mode=0o711,exist_ok=True)
    if root.stat().st_uid!=0 or (root.stat().st_mode & 0o022):raise ValueError('Share root must be root-owned and not group/world writable')
    folder=root/name
    if folder.exists() or folder.is_symlink():raise ValueError('Folder already exists; choose a different name')
    if not pathlib.Path('/usr/bin/setfacl').exists():raise ValueError('POSIX ACL tools are required (install acl)')
    # Validate smb.conf can be managed before changing filesystem.
    original=SMB.read_text()
    include='   include = /etc/samba/pinas-shares.conf'
    if include not in original:
        if not re.search(r'(?im)^\s*\[global\]\s*$',original):raise ValueError('Samba [global] section missing')
        amended=re.sub(r'(?im)^(\s*\[global\]\s*)$',r'\1\n'+include,original,count=1)
    else:amended=original
    # Explicit per-user access; default deny for other NAS accounts.
    ro=[u for u,p in access.items() if p=='ro'];rw=[u for u,p in access.items() if p=='rw']
    stanza='\n['+name+']\n   path = '+str(folder)+'\n   browseable = yes\n   guest ok = no\n   read only = yes\n   valid users = '+', '.join(access)+'\n'
    if rw:stanza+='   write list = '+', '.join(rw)+'\n'
    stanza+='   create mask = 0660\n   directory mask = 0770\n   follow symlinks = no\n   wide links = no\n'
    oldconf=CONF.read_text() if CONF.exists() else ''
    if '['+name+']' in oldconf:raise ValueError('Duplicate managed share')
    folder.mkdir(mode=0o700)
    try:
        # Root-owned folder; Samba creates files as authenticated Unix users.
        os.chown(folder,0,0)
        os.chmod(folder,0o700)
        acl=['u::rwx','g::---','o::---','m::rwx']+[f'u:{u}:'+('rwx' if p=='rw' else 'r-x') for u,p in access.items()]
        default=['d:'+entry for entry in acl]
        run(['/usr/bin/setfacl','-m',','.join(acl+default),str(folder)])
        if amended!=original:atomic(SMB,amended,0o644)
        atomic(CONF,oldconf+stanza,0o644)
        run(['/usr/bin/testparm','-s'])
        run(['/usr/bin/systemctl','reload','smbd'])
        current.append({'name':name,'volume_label':mount.name,'volume':device,'access':access})
        atomic(DB,json.dumps(current,indent=2),0o600)
    except Exception:
        atomic(CONF,oldconf,0o644)
        if amended!=original:atomic(SMB,original,0o644)
        try:run(['/usr/bin/systemctl','reload','smbd'])
        except Exception:pass
        try:folder.rmdir()
        except OSError:pass
        raise
    print(json.dumps({'ok':True,'name':name}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

NAS_FILES_HELPER = r"""#!/usr/bin/env python3
# Privileged, narrow file broker. Authentication against Samba passdb; filesystem
# operations executed as the NAS user's actual UID/GID and supplementary groups.
import base64, hashlib, hmac, json, os, pathlib, pwd, re, stat, subprocess, sys
DB=pathlib.Path('/var/lib/pinas/shares.json')
def md4(message):
    # NT hash is MD4(UTF-16LE password). Samba uses NT hashes for SMB auth.
    import struct
    original=len(message);message+=b'\x80';message+=b'\0'*((56-len(message)%64)%64)+struct.pack('<Q',original*8)
    a,b,c,d=0x67452301,0xefcdab89,0x98badcfe,0x10325476
    def rol(v,n):return ((v<<n)|(v>>(32-n)))&0xffffffff
    for offset in range(0,len(message),64):
        x=struct.unpack('<16I',message[offset:offset+64]);aa,bb,cc,dd=a,b,c,d
        for j in range(48):
            if j<16:f=(b&c)|(~b&d);k=j;shift=[3,7,11,19][j%4];constant=0
            elif j<32:f=(b&c)|(b&d)|(c&d);k=(j%4)*4+j//4-4;shift=[3,5,9,13][j%4];constant=0x5a827999
            else:f=b^c^d;k=[0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15][j-32];shift=[3,9,11,15][j%4];constant=0x6ed9eba1
            value=rol((a+f+x[k]+constant)&0xffffffff,shift);a,b,c,d=d,value,b,c
        a=(a+aa)&0xffffffff;b=(b+bb)&0xffffffff;c=(c+cc)&0xffffffff;d=(d+dd)&0xffffffff
    return struct.pack('<4I',a,b,c,d).hex().upper()
def samba_hash(user):
    p=subprocess.run(['/usr/bin/pdbedit','-Lw',user],capture_output=True,text=True,timeout=8)
    if p.returncode:raise ValueError('Unknown NAS account')
    for line in p.stdout.splitlines():
        fields=line.split(':')
        if len(fields)>4 and fields[0]==user and re.fullmatch('[A-Fa-f0-9]{32}',fields[3]):return fields[3].upper()
    raise ValueError('NAS account has no valid Samba password')
def valid_user(user):
    if not isinstance(user,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',user):raise ValueError('Invalid user')
    person=pwd.getpwnam(user)
    if person.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):raise ValueError('Not a PiNAS NAS user')
    if samba_hash(user)=='':raise ValueError('Not a Samba user')
    return person
def shares_for(user):
    entries=json.loads(DB.read_text())
    return [s for s in entries if isinstance(s,dict) and s.get('access',{}).get(user) in ('ro','rw')]
def drop(person):
    os.initgroups(person.pw_name,person.pw_gid);os.setgid(person.pw_gid);os.setuid(person.pw_uid)
def safe_path(root,relative):
    if not isinstance(relative,str) or len(relative)>1000 or relative.startswith('/') or '\\' in relative or '\x00' in relative:raise ValueError('Invalid path')
    parts=relative.split('/') if relative else []
    if any(x in ('','.','..') or x.startswith('.pinas-upload-') for x in parts):raise ValueError('Invalid path')
    # Reject symlinks at every level, including the leaf. Never follow them.
    cur=root
    for part in parts:
        cur=cur/part
        if cur.is_symlink():raise ValueError('Symbolic links are not accessible')
    if not cur.resolve(strict=False).is_relative_to(root.resolve(strict=True)):raise ValueError('Path outside share')
    return cur
def main():
    if os.geteuid()!=0:raise ValueError('Root required')
    raw=sys.stdin.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise ValueError('Request too large')
    q=json.loads(raw);action=q.get('action');user=q.get('username');person=valid_user(user)
    if action=='authenticate':
        password=q.get('password')
        if not isinstance(password,str) or len(password)>256:raise ValueError('Invalid password')
        print('true' if hmac.compare_digest(md4(password.encode('utf-16le')),samba_hash(user)) else 'false');return
    allowed=shares_for(user)
    if action=='shares':
        print(json.dumps({'shares':[{'name':s['name'],'read_only':s['access'][user]=='ro'} for s in allowed]}));return
    share=q.get('share');s=next((x for x in allowed if x['name']==share),None)
    if s is None:raise ValueError('Share not accessible')
    # Root path derived exclusively from privileged share metadata, not browser paths.
    root=pathlib.Path(s['volume_label']) if False else None
    # Resolve mount from device, and confirm it is still the same mounted filesystem.
    device=s['volume'];p=subprocess.run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device],capture_output=True,text=True,timeout=5)
    targets=p.stdout.strip().splitlines()
    if p.returncode or len(targets)!=1:raise ValueError('Share storage is offline')
    mount=pathlib.Path(targets[0]).resolve(strict=True)
    if str(mount)=='/' or str(mount).startswith(('/etc/','/var/','/usr/','/home/','/boot/')):raise ValueError('Protected mount')
    root=mount/'PiNAS Shares'/s['name']
    if root.is_symlink() or not root.is_dir():raise ValueError('Share folder unavailable')
    relative=q.get('path','');target=safe_path(root,relative)
    writable=s['access'][user]=='rw'
    if action in ('mkdir','delete','rename','move','copy','upload','upload_start','upload_chunk','upload_finish','upload_cancel') and not writable:raise ValueError('Read-only share')
    drop(person)
    # All operations below run with the NAS user's UID/GID. Uploads are staged
    # in the destination directory, then published by an atomic rename.
    def valid_name(name):
        if not isinstance(name,str) or not name or len(name)>255 or name in ('.','..') or '/' in name or '\\' in name or '\x00' in name or name.startswith('.pinas-upload-'):raise ValueError('Invalid file name')
        return name
    def destination(relative):
        dest=safe_path(root,relative)
        if dest==root or dest.exists() or dest.is_symlink():raise ValueError('Destination already exists')
        if not dest.parent.is_dir():raise ValueError('Destination folder does not exist')
        return dest
    if action in ('rename','move','copy'):
        if target==root or not target.exists():raise ValueError('Invalid source')
        if action=='rename':
            dest=destination('/'.join(filter(None,[relative.rsplit('/',1)[0] if '/' in relative else '',valid_name(q.get('name'))])))
        else:
            dest=destination(q.get('dest',''))
        if target.is_dir() and (dest==target or target in dest.parents):raise ValueError('Cannot place folder inside itself')
        if action=='copy':
            import shutil
            if target.is_dir():
                # Reject links anywhere in the tree and cap total copy size.
                total=0
                for directory,dirs,files in os.walk(target,followlinks=False):
                    for name in dirs+files:
                        node=pathlib.Path(directory)/name
                        if node.is_symlink():raise ValueError('Symbolic links cannot be copied')
                        if node.is_file():total+=node.stat().st_size
                        if total>8*1024**3:raise ValueError('Folder copy exceeds 8 GiB safety limit')
                shutil.copytree(target,dest,symlinks=False)
            elif target.is_file():
                with target.open('rb') as src, dest.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            else:raise ValueError('Unsupported file type')
        else:
            # Same-share only; atomic rename prevents partial moves.
            if target.is_file():
                os.link(target,dest,follow_symlinks=False);target.unlink()
            else:target.rename(dest)
        print('{"ok":true}');return
    if action=='upload_start':
        name=valid_name(q.get('name'))
        if not target.is_dir():raise ValueError('Not a folder')
        destination('/'.join(filter(None,[relative,name])))
        size=q.get('size')
        if not isinstance(size,int) or size<0 or size>100*1024**3:raise ValueError('Invalid upload size')
        import secrets
        token=secrets.token_hex(20)
        staging=target/('.pinas-upload-'+token)
        fd=os.open(staging,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        meta=target/('.pinas-upload-'+token+'.json')
        fd=os.open(meta,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'name':name,'size':size,'path':relative},f)
        print(json.dumps({'token':token}));return
    if action in ('upload_chunk','upload_finish','upload_cancel'):
        token=q.get('token','')
        if not isinstance(token,str) or not re.fullmatch('[0-9a-f]{40}',token):raise ValueError('Invalid transfer token')
        stage=target/('.pinas-upload-'+token)
        meta=target/('.pinas-upload-'+token+'.json')
        if stage.is_symlink() or meta.is_symlink() or not stage.is_file() or not meta.is_file():raise ValueError('Unknown transfer')
        details=json.loads(meta.read_text());name=valid_name(details['name']);size=details['size']
        if details.get('path')!=relative:raise ValueError('Transfer location mismatch')
        if action=='upload_cancel':stage.unlink();meta.unlink();print('{"ok":true}');return
        if action=='upload_chunk':
            content=q.get('content','');offset=q.get('offset')
            if not isinstance(content,str) or len(content)>700000 or not isinstance(offset,int):raise ValueError('Invalid chunk')
            payload=base64.b64decode(content,validate=True)
            if len(payload)>512*1024 or offset!=stage.stat().st_size or offset+len(payload)>size:raise ValueError('Chunk offset or size mismatch')
            with stage.open('ab') as f:f.write(payload)
            print(json.dumps({'offset':offset+len(payload)}));return
        if stage.stat().st_size!=size:raise ValueError('Upload incomplete')
        dest=destination('/'.join(filter(None,[relative,name])))
        # Hard-link is no-clobber and atomic on the same filesystem.
        os.link(stage,dest,follow_symlinks=False);stage.unlink();meta.unlink()
        print('{"ok":true}');return
    if action=='download_chunk':
        offset=q.get('offset');size=q.get('size')
        if not isinstance(offset,int) or offset<0 or not isinstance(size,int) or size<1 or size>512*1024:raise ValueError('Invalid download range')
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode):raise ValueError('Not a regular file')
        total=target.stat().st_size
        with target.open('rb') as f:f.seek(offset);chunk=f.read(size)
        print(json.dumps({'content':base64.b64encode(chunk).decode(),'total':total}));return
    if action=='list':
        if not target.is_dir():raise ValueError('Not a folder')
        entries=[]
        for child in sorted(target.iterdir(),key=lambda x:x.name.casefold()):
            if child.is_symlink() or child.name.startswith('.pinas-upload-'):continue
            try:st=child.stat()
            except OSError:continue
            if stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode):entries.append({'name':child.name,'dir':stat.S_ISDIR(st.st_mode),'size':st.st_size})
            if len(entries)>=1000:break
        print(json.dumps({'entries':entries}));return
    if action=='mkdir':
        name=q.get('name','');dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..'):raise ValueError('Invalid folder name')
        dest.mkdir(mode=0o770);print('{"ok":true}');return
    if action=='delete':
        if target==root:raise ValueError('Cannot delete share root')
        if target.is_dir():target.rmdir()
        elif target.is_file():target.unlink()
        else:raise ValueError('Not a regular file or empty folder')
        print('{"ok":true}');return
    if action=='download':
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode) or target.stat().st_size>3*1024*1024:raise ValueError('Only files up to 3 MB supported in this test build')
        with target.open('rb') as f:content=base64.b64encode(f.read()).decode()
        print(json.dumps({'content':content}));return
    if action=='upload':
        name=q.get('name','');content=q.get('content','')
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..') or not isinstance(content,str) or len(content)>4*1024*1024+16:raise ValueError('Invalid upload')
        dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not target.is_dir():raise ValueError('Not a directory')
        payload=base64.b64decode(content,validate=True)
        if len(payload)>3*1024*1024:raise ValueError('Upload exceeds 3 MB')
        fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o660)
        with os.fdopen(fd,'wb') as f:f.write(payload)
        print('{"ok":true}');return
    raise ValueError('Unsupported action')
if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
"""

APT_INDEX_HELPER = r"""#!/usr/bin/env python3
import os,subprocess,sys
from pathlib import Path
ALLOWED={'off':None,'daily':'*-*-* 01:00:00','weekly':'Fri *-*-* 01:00:00','monthly':'*-*-28 01:00:00'}
def run(cmd,timeout=30):
    p=subprocess.run(cmd,timeout=timeout,check=False)
    if p.returncode:sys.exit(p.returncode)
def main():
    if os.geteuid()!=0:sys.exit('Root access required')
    args=sys.argv[1:]
    if len(args)==2 and args[0]=='schedule' and args[1] in ALLOWED:
        schedule=args[1];calendar=ALLOWED[schedule]
        timer=Path('/etc/systemd/system/pinas-auto-updates.timer')
        if calendar:
            timer.write_text('[Unit]\nDescription=PiNAS automatic OS updates\n[Timer]\nOnCalendar='+calendar+'\nPersistent=true\nUnit=pinas-auto-updates.service\n[Install]\nWantedBy=timers.target\n')
        run(['systemctl','daemon-reload'])
        if calendar:
            run(['systemctl','enable','--now','pinas-auto-updates.timer'])
            run(['systemctl','restart','pinas-auto-updates.timer'])
        else:
            run(['systemctl','disable','--now','pinas-auto-updates.timer']) if timer.exists() else None
            timer.unlink(missing_ok=True)
            run(['systemctl','daemon-reload'])
        marker=Path('/var/lib/pinas/update-schedule');marker.write_text(schedule+'\n');os.chmod(marker,0o644)
        return
    if args==['automatic']:
        # Only the systemd oneshot invokes this command, not the web service account.
        run(['/usr/bin/apt-get','update'],210)
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
        return
    if args==['upgrade']:
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
    elif args==['refresh']:
        run(['/usr/bin/apt-get','update'],210)
    else:sys.exit('Unsupported operation')
if __name__=='__main__':main()
"""

NAS_STORAGE_HELPER='#!/usr/bin/env python3\n"""PiNAS RC13 restricted, non-destructive storage adoption helper."""\nimport json,os,pathlib,re,subprocess,sys,uuid\nfrom pathlib import Path\n\ndef run(*args,timeout=15):\n    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)\n    if p.returncode:raise ValueError((p.stderr or \'Storage command failed\').strip()[-500:])\n    return p.stdout.strip()\n\ndef main():\n    if os.geteuid()!=0 or sys.argv[1:]!=[\'adopt\']:raise ValueError(\'Unsupported storage operation\')\n    data=json.loads(sys.stdin.read(4096));device=data.get(\'device\')\n    if not isinstance(device,str) or not re.fullmatch(r\'/dev/[A-Za-z0-9_./-]{1,90}\',device) or \'..\' in device:raise ValueError(\'Invalid device\')\n    path=Path(device)\n    if not path.is_block_device():raise ValueError(\'Device is not a block device\')\n    # The privileged helper independently identifies eligible physical disks.\n    roots=json.loads(run(\'lsblk\',\'-J\',\'-b\',\'-o\',\'NAME,PATH,TYPE,FSTYPE,UUID,MOUNTPOINTS,RO,PKNAME\')).get(\'blockdevices\',[])\n    bypath={};byname={};parents={}\n    def walk(node,parent=None):\n        name=node.get(\'name\');bypath[node.get(\'path\')]=node;byname[name]=node\n        if parent:parents[name]=parent\n        for child in node.get(\'children\') or []:walk(child,name)\n    for root in roots:walk(root)\n    node=bypath.get(str(path.resolve())) or bypath.get(device)\n    if not node or node.get(\'type\') not in (\'part\',\'disk\') or node.get(\'ro\'):raise ValueError(\'Not an eligible writable disk or partition\')\n    def root_for(n):\n        seen=set()\n        while n.get(\'name\') in parents:\n            if n[\'name\'] in seen:raise ValueError(\'Invalid device topology\')\n            seen.add(n[\'name\']);n=byname[parents[n[\'name\']]]\n        return n\n    disk=root_for(node)\n    if disk.get(\'type\')!=\'disk\' or disk.get(\'ro\') or str(disk.get(\'name\',\'\')).startswith((\'loop\',\'zram\',\'ram\',\'nbd\',\'sr\',\'fd\')):raise ValueError(\'Unsupported backing device\')\n    # Reject any physical disk carrying the root or boot filesystems.\n    protected={\'/\',\'/boot\',\'/boot/firmware\',\'/boot/efi\'}\n    def contains_system(n):\n        if any(m in protected for m in (n.get(\'mountpoints\') or []) if m):return True\n        return any(contains_system(c) for c in n.get(\'children\') or [])\n    if contains_system(disk):raise ValueError(\'Operating system storage is protected\')\n    for mount in protected:\n        src=run(\'findmnt\',\'-n\',\'-o\',\'SOURCE\',\'--target\',mount).split(\'[\',1)[0]\n        if src and src in bypath and root_for(bypath[src]).get(\'name\')==disk.get(\'name\'):\n            raise ValueError(\'Operating system storage is protected\')\n    fs=run(\'blkid\',\'-s\',\'TYPE\',\'-o\',\'value\',device)\n    uid=run(\'blkid\',\'-s\',\'UUID\',\'-o\',\'value\',device)\n    if fs not in (\'ext4\',\'xfs\',\'btrfs\') or not re.fullmatch(r\'[A-Za-z0-9-]{8,64}\',uid):raise ValueError(\'Supported filesystem and UUID required\')\n    # Reject RAID/LVM/crypto members and nested volume layouts.\n    if node.get(\'type\')==\'disk\' and node.get(\'children\'):raise ValueError(\'Choose a filesystem partition, not its parent disk\')\n    if node.get(\'children\'):raise ValueError(\'Complex volume layout not supported\')\n    mountpoints=[m for m in node.get(\'mountpoints\') or [] if m]\n    if len(mountpoints)>1:raise ValueError(\'Multiple mountpoints require manual review\')\n    if mountpoints and not str(mountpoints[0]).startswith(\'/mnt/pinas/\'):\n        raise ValueError(\'Filesystem is already mounted elsewhere; manage it manually to avoid disrupting applications\')\n    target=Path(\'/mnt/pinas\')/uid\n    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir())) and str(target) not in mountpoints):raise ValueError(\'Mount destination is not empty\')\n    fstab=Path(\'/etc/fstab\');original=fstab.read_text();entries=[line.split() for line in original.splitlines() if line.strip() and not line.lstrip().startswith(\'#\')]\n    for e in entries:\n        if len(e)>=2 and (e[0] in (device,\'UUID=\'+uid,\'/dev/disk/by-uuid/\'+uid) or e[1]==str(target)):\n            if e[0]==\'UUID=\'+uid and e[1]==str(target):\n                if str(target) not in mountpoints:run(\'mount\',str(target),timeout=25)\n                print(json.dumps({\'ok\':True,\'mount\':str(target),\'existing\':True}));return\n            raise ValueError(\'Existing fstab configuration requires manual review\')\n    target.parent.mkdir(parents=True,exist_ok=True)\n    target.mkdir(mode=0o755,exist_ok=True)\n    options=\'defaults,nofail,noatime,x-systemd.device-timeout=10s\'\n    entry=f\'UUID={uid} {target} {fs} {options} 0 {2 if fs=="ext4" else 0} # PiNAS managed\\\\n\'\n    entry=entry.replace(\'\\\\n\',\'\\n\')\n    backup=fstab.with_name(\'fstab.pinas-\'+uuid.uuid4().hex[:12]+\'.bak\')\n    backup.write_text(original);os.chmod(backup,0o600)\n    temp=fstab.with_name(\'.fstab.pinas-\'+uuid.uuid4().hex)\n    try:\n        temp.write_text(original.rstrip(\'\\n\')+\'\\n\'+entry);os.chmod(temp,0o644)\n        os.replace(temp,fstab)\n        run(\'systemctl\',\'daemon-reload\',timeout=15)\n        run(\'mount\',str(target),timeout=25)\n        actual=run(\'findmnt\',\'-n\',\'-o\',\'UUID\',\'--target\',str(target))\n        if actual!=uid:raise ValueError(\'Mounted filesystem UUID verification failed\')\n    except Exception:\n        fstab.write_text(original)\n        try:run(\'systemctl\',\'daemon-reload\')\n        except Exception:pass\n        raise\n    print(json.dumps({\'ok\':True,\'mount\':str(target)}))\nif __name__==\'__main__\':\n    try:main()\n    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)\n'

SMART_HEALTH_HELPER = """#!/usr/bin/env python3
import json,os,shutil,subprocess,sys
from pathlib import Path
def main():
    if os.geteuid()!=0 or len(sys.argv)!=1:
        raise ValueError('Unsupported operation')
    smartctl=shutil.which('smartctl')
    if not smartctl:
        print(json.dumps({'installed':False,'drives':[]}));return
    p=subprocess.run(['lsblk','-J','-b','-o','NAME,PATH,TYPE,MODEL,TRAN'],capture_output=True,text=True,timeout=8,check=True)
    drives=[]
    for disk in json.loads(p.stdout).get('blockdevices',[]):
        if disk.get('type')!='disk':continue
        device=disk.get('path','')
        if not isinstance(device,str) or not device.startswith('/dev/') or not Path(device).is_block_device():continue
        if disk.get('name','').startswith(('loop','zram','ram','nbd','sr','fd')):continue
        entry={'device':device,'model':disk.get('model') or disk.get('name'),'status':'Unavailable','temperature':None}
        try:
            result=subprocess.run([smartctl,'-j','-H','-A',device],capture_output=True,text=True,timeout=12)
            data=json.loads(result.stdout)
            health=data.get('smart_status',{}).get('passed')
            if health is True:entry['status']='Healthy'
            elif health is False:entry['status']='Warning'
            temp=data.get('temperature',{}).get('current')
            if isinstance(temp,(int,float)) and -20<=temp<=120:entry['temperature']=temp
            if data.get('smart_support',{}).get('available') is False:entry['status']='Unsupported'
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        drives.append(entry)
    print(json.dumps({'installed':True,'drives':drives}))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

def install(args):
    if sys.platform!='linux' or os.geteuid()!=0:sys.exit('Install requires Linux and sudo/root.')
    if not Path('/etc/os-release').exists():sys.exit('Unsupported OS')
    osinfo=read('/etc/os-release')
    if 'debian' not in osinfo.lower() and 'raspbian' not in osinfo.lower():sys.exit('Requires Raspberry Pi OS / Debian family')
    if not args.skip_packages:
        print('Installing NAS dependencies (requires network and may take time)...',flush=True)
        subprocess.run(['apt-get','update'],check=True)
        subprocess.run(['apt-get','install','-y','samba','xfsprogs','btrfs-progs','mdadm','parted','util-linux','e2fsprogs','avahi-daemon','acl','openssl'],check=True)
    target=Path('/opt/pinas');target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(__file__).resolve(),target/'pinas.py');os.chmod(target/'pinas.py',0o755)
    if subprocess.run(['id','-u','pinas'],capture_output=True).returncode!=0:
        subprocess.run(['useradd','--system','--home-dir','/var/lib/pinas','--shell','/usr/sbin/nologin','pinas'],check=True)
    DATA.mkdir(parents=True,exist_ok=True);os.chmod(DATA,0o700)
    subprocess.run(['chown','pinas:pinas',str(DATA)],check=True)
    helper=Path('/usr/local/libexec/pinas-apply-hostname')
    helper.parent.mkdir(parents=True,exist_ok=True)
    helper.write_text(HOSTNAME_HELPER)
    os.chmod(helper,0o755)
    unit='''[Unit]\nDescription=Apply validated PiNAS device hostname\nAfter=systemd-hostnamed.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /usr/local/libexec/pinas-apply-hostname\nNoNewPrivileges=true\nProtectHome=true\nPrivateTmp=true\n'''
    Path('/etc/systemd/system/pinas-hostname.service').write_text(unit)
    path_unit='''[Unit]\nDescription=Apply PiNAS hostname when configuration changes\n[Path]\nPathChanged=/var/lib/pinas/config.json\nUnit=pinas-hostname.service\n[Install]\nWantedBy=multi-user.target\n'''
    Path('/etc/systemd/system/pinas-hostname.path').write_text(path_unit)
    user_helper=Path('/usr/local/libexec/pinas-nas-user')
    user_helper.write_text(NAS_USER_HELPER)
    os.chown(user_helper,0,0);os.chmod(user_helper,0o700)
    sudoers=Path('/etc/sudoers.d/pinas-nas-user')
    sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-user create *, /usr/local/libexec/pinas-nas-user password *, /usr/local/libexec/pinas-nas-user list\n')
    os.chown(sudoers,0,0);os.chmod(sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(sudoers)],capture_output=True).returncode:
        sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS sudoers configuration')
    share_helper=Path('/usr/local/libexec/pinas-nas-share')
    share_helper.write_text(NAS_SHARE_HELPER)
    os.chown(share_helper,0,0);os.chmod(share_helper,0o700)
    share_sudoers=Path('/etc/sudoers.d/pinas-nas-share')
    share_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-share list, /usr/local/libexec/pinas-nas-share create\n')
    os.chown(share_sudoers,0,0);os.chmod(share_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(share_sudoers)],capture_output=True).returncode:
        share_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS share sudoers configuration')
    files_helper=Path('/usr/local/libexec/pinas-nas-files')
    files_helper.write_text(NAS_FILES_HELPER)
    os.chown(files_helper,0,0);os.chmod(files_helper,0o700)
    files_sudoers=Path('/etc/sudoers.d/pinas-nas-files')
    files_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-files\n')
    os.chown(files_sudoers,0,0);os.chmod(files_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(files_sudoers)],capture_output=True).returncode:
        files_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS file helper sudoers configuration')
    storage_helper=Path('/usr/local/libexec/pinas-nas-storage')
    storage_helper.write_text(NAS_STORAGE_HELPER)
    os.chown(storage_helper,0,0);os.chmod(storage_helper,0o700)
    storage_sudoers=Path('/etc/sudoers.d/pinas-nas-storage')
    storage_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-storage adopt\n')
    os.chown(storage_sudoers,0,0);os.chmod(storage_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(storage_sudoers)],capture_output=True).returncode:
        storage_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS storage sudoers configuration')
    smart_helper=Path('/usr/local/libexec/pinas-smart-health')
    smart_helper.write_text(SMART_HEALTH_HELPER)
    os.chown(smart_helper,0,0);os.chmod(smart_helper,0o700)
    smart_sudoers=Path('/etc/sudoers.d/pinas-smart-health')
    smart_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-smart-health\n')
    os.chown(smart_sudoers,0,0);os.chmod(smart_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(smart_sudoers)],capture_output=True).returncode:
        smart_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS SMART sudoers configuration')
    apt_helper=Path('/usr/local/libexec/pinas-apt-index')
    apt_helper.write_text(APT_INDEX_HELPER)
    os.chown(apt_helper,0,0);os.chmod(apt_helper,0o700)
    apt_sudoers=Path('/etc/sudoers.d/pinas-apt-index')
    apt_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-apt-index refresh, /usr/local/libexec/pinas-apt-index upgrade, /usr/local/libexec/pinas-apt-index schedule off, /usr/local/libexec/pinas-apt-index schedule daily, /usr/local/libexec/pinas-apt-index schedule weekly, /usr/local/libexec/pinas-apt-index schedule monthly\n')
    os.chown(apt_sudoers,0,0);os.chmod(apt_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(apt_sudoers)],capture_output=True).returncode:
        apt_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS APT sudoers configuration')
    auto_service=Path('/etc/systemd/system/pinas-auto-updates.service')
    auto_service.write_text('[Unit]\nDescription=PiNAS scheduled OS updates\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=oneshot\nExecStart=/usr/local/libexec/pinas-apt-index automatic\nEnvironment=DEBIAN_FRONTEND=noninteractive\n')
    os.chown(auto_service,0,0);os.chmod(auto_service,0o644)
    # Existing schedule is preserved when upgrading PiNAS.
    # Generate a persistent per-install certificate; never replace it on upgrades.
    if not TLS_CERT.exists() or not TLS_KEY.exists():
        if TLS_CERT.exists() or TLS_KEY.exists():sys.exit('Incomplete TLS certificate pair; resolve manually before installing')
        if not shutil.which('openssl'):sys.exit('OpenSSL required for initial TLS certificate generation')
        hostname=load().get('hostname','pinas')
        if not valid_hostname(hostname):hostname='pinas'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','825',
            '-keyout',str(TLS_KEY),'-out',str(TLS_CERT),'-subj',f'/CN={hostname}.local',
            '-addext',f'subjectAltName=DNS:{hostname}.local,DNS:localhost,IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL)
    for f,mode in ((TLS_CERT,0o644),(TLS_KEY,0o600)):
        os.chown(f,0 if f==TLS_CERT else __import__('pwd').getpwnam('pinas').pw_uid,0 if f==TLS_CERT else __import__('grp').getgrnam('pinas').gr_gid)
        os.chmod(f,mode)
    bind_host='0.0.0.0' if args.lan else '127.0.0.1' 
    # TEMPORARY RC9.2: sudo inherits the service mount namespace. A root helper
    # cannot write /etc/passwd, /etc/group or Samba state with ProtectSystem=strict.
    # Replace sudo delegation with an independently sandboxed privileged service.
    service='''[Unit]\nDescription=PiNAS prototype web dashboard\nAfter=network.target\n[Service]\nType=simple\nUser=pinas\nGroup=pinas\nExecStart=/usr/bin/python3 /opt/pinas/pinas.py --serve --tls --host %s --port %d\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=false\nProtectSystem=false\nReadWritePaths=/var/lib/pinas\nPrivateTmp=true\n[Install]\nWantedBy=multi-user.target\n'''%(bind_host,args.port)
    Path('/etc/systemd/system/pinas.service').write_text(service)
    subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','enable','--now','pinas-hostname.path'],check=True);subprocess.run(['systemctl','start','pinas-hostname.service'],check=True);subprocess.run(['systemctl','enable','pinas.service'],check=True);subprocess.run(['systemctl','restart','pinas.service'],check=True)
    print(f'PiNAS installed. For localhost access: https://127.0.0.1:{args.port} (self-signed certificate)')
    if args.lan:print(f'LAN TLS MODE: open https://<PI-IP>:{args.port}. Certificate is self-signed; use the .local hostname for name matching. Do not expose this port to the internet.')
    else:print('Localhost-only mode; re-run installer with --lan to enable direct LAN access for testing.')

def main():
    ap=argparse.ArgumentParser(description='PiNAS Raspberry Pi NAS prototype')
    ap.add_argument('--lan',action='store_true',help='Bind HTTPS server to LAN interfaces');ap.add_argument('--install',action='store_true');ap.add_argument('--serve',action='store_true');ap.add_argument('--tls',action='store_true');ap.add_argument('--skip-packages',action='store_true');ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=8765)
    a=ap.parse_args()
    if a.install:install(a);return
    if a.serve:
        if a.host not in ('127.0.0.1','::1','0.0.0.0'):sys.exit('Unsupported bind address.')
        if a.host=='0.0.0.0' and not a.tls:sys.exit('LAN listening requires HTTPS (--tls)')
        server=ThreadingHTTPServer((a.host,a.port),Handler)
        if a.tls:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(TLS_CERT),str(TLS_KEY))
            server.socket=context.wrap_socket(server.socket,server_side=True)
        print('PiNAS running on %s://%s:%s'%('https' if a.tls else 'http',a.host,a.port))
        threading.Thread(target=cpu_sampler,daemon=True).start();server.serve_forever();return
    ap.print_help()
if __name__=='__main__':main()) for x in (name,new_name)):
                self.json({'error':'Invalid share name.'},400);return
            if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not isinstance(u,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):
                self.json({'error':'Assign at least one valid user access.'},400);return
            if not isinstance(password,str) or not verify(password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not set(access).issubset({u['name'] for u in nas_user_list()}):
                self.json({'error':'Unknown NAS user.'},409);return
            if not any(isinstance(item,dict) and item.get('name')==name for item in nas_share_list()):
                self.json({'error':'Only PiNAS-managed shares can be edited.'},404);return
            try:edit_nas_share(name,new_name,access)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':new_name});return
        if path=='/api/delete-share':
            name=data.get('name');password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):
                self.json({'error':'Invalid share name.'},400);return
            if not isinstance(password,str) or not verify(password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not any(isinstance(item,dict) and item.get('name')==name for item in nas_share_list()):
                self.json({'error':'Only PiNAS-managed shares can be removed.'},404);return
            try:delete_nas_share(name)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name,'files_preserved':True});return
        if path=='/api/nas-shares':
            name=data.get('name');volume=data.get('volume');access=data.get('access');admin_password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):
                self.json({'error':'Choose a share name of 1–32 letters, digits, spaces, underscores or hyphens.'},400);return
            if not isinstance(volume,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',volume) or '..' in volume:
                self.json({'error':'Invalid storage selection.'},400);return
            if not isinstance(access,dict) or not access or len(access)>64 or any(not isinstance(k,str) or v not in ('ro','rw') for k,v in access.items()):
                self.json({'error':'Assign at least one user Read Only or Read & Write access.'},400);return
            if not isinstance(admin_password,str) or not verify(admin_password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not storage_is_ready():self.json({'error':'A mounted, persistent data filesystem is required.'},409);return
            valid_users={u['name'] for u in nas_user_list()}
            if not set(access).issubset(valid_users):self.json({'error':'One or more users are not valid Samba accounts.'},409);return
            if any(name.casefold()==s.casefold() for s in discover().get('shares',[])):
                self.json({'error':'A share with this name already exists.'},409);return
            try:create_nas_share(name,volume,access)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name});return
        if path=='/api/logout':SESSIONS.pop(token,None);self.json({'ok':True},cookie='pinas_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'+('; Secure' if isinstance(self.connection,ssl.SSLSocket) else ''));return
        if path=='/api/settings':
            theme,accent,font=data.get('theme'),data.get('accent'),data.get('font')
            interval,history=data.get('cpu_interval',cfg.get('cpu_interval',5)),data.get('cpu_history',cfg.get('cpu_history',10))
            session_timeout=data.get('session_timeout',cfg.get('session_timeout',5))
            if theme not in ('light','dark','dark-cb','light-cb') or not isinstance(accent,str) or len(accent)!=7 or accent[0]!='#' or any(c not in '0123456789abcdefABCDEF' for c in accent[1:]) or type(font)!=int or font not in (10,12,14,16) or type(interval)!=int or interval not in (2,5,10) or type(history)!=int or history not in (10,15,30,60) or type(session_timeout)!=int or session_timeout not in (5,10,15,30,60):self.json({'error':'Invalid appearance settings'},400);return
            cfg.update(theme=theme,accent=accent,font=font,cpu_interval=interval,cpu_history=history,session_timeout=session_timeout)
        elif path=='/api/background':
            image=data.get('image')
            if not isinstance(image,str) or len(image)>2_900_000:self.json({'error':'Image too large'},400);return
            if image:
                try:
                    meta,b64=image.split(',',1);mime=meta[5:].split(';',1)[0]
                    if mime not in ('image/jpeg','image/png','image/webp'):raise ValueError()
                    decoded=base64.b64decode(b64,validate=True)
                    if len(decoded)>2*1024*1024:raise ValueError()
                    if not ((mime=='image/jpeg' and decoded.startswith(b'\xff\xd8\xff')) or (mime=='image/png' and decoded.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/webp' and decoded.startswith(b'RIFF') and decoded[8:12]==b'WEBP')):raise ValueError()
                except (ValueError,IndexError):self.json({'error':'Invalid image'},400);return
            cfg['login_background']=image
        save(cfg);self.json({'settings':dict({k:cfg.get(k) for k in ('theme','accent','font','cpu_interval','cpu_history','session_timeout')},has_background=bool(cfg.get('login_background')))} )

HOSTNAME_HELPER = r"""#!/usr/bin/env python3
import json, re, subprocess
from pathlib import Path
try:
    path=Path('/var/lib/pinas/config.json')
    if not path.exists():raise SystemExit(0)
    cfg=json.loads(path.read_text())
    hostname=cfg.get('hostname','')
    if not hostname:raise SystemExit(0)
    if not isinstance(hostname,str) or not 1<=len(hostname)<=63 or not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*',hostname):
        raise ValueError('Invalid hostname')
    current=subprocess.run(['hostname','-s'],capture_output=True,text=True,check=True).stdout.strip()
    if current!=hostname:
        subprocess.run(['/usr/bin/hostnamectl','set-hostname',hostname],check=True,timeout=15)
except (OSError,ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
    raise SystemExit('PiNAS hostname not applied: '+str(exc))
"""

NAS_USER_HELPER = r"""#!/usr/bin/env python3
# Privileged helper. No arbitrary command execution; narrowly scoped account actions.
import grp, json, os, pwd, re, subprocess, sys

def run(argv, **kwargs):
    return subprocess.run(argv, check=True, timeout=20, **kwargs)

def samba_users():
    p=run(['/usr/bin/pdbedit','-L'],capture_output=True,text=True)
    result=[]
    for line in p.stdout.splitlines():
        fields=line.split(':',2)
        if len(fields)>=2 and re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',fields[0]):
            result.append({'name':fields[0],'uid':fields[1]})
    return sorted(result,key=lambda x:x['name'])

if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit(2)
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(samba_users()))
        raise SystemExit(0)
    if len(sys.argv)!=3 or sys.argv[1] not in ('create','password'):raise SystemExit(2)
    name=sys.argv[2]
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',name) or name in ('pinas','root','admin','nobody'):raise SystemExit(2)
    password=sys.stdin.readline(258).rstrip('\n')
    if not 12<=len(password)<=256:raise SystemExit(2)
    if sys.argv[1]=='password':
        group=grp.getgrnam('pinas-nas')
        existing=pwd.getpwnam(name)
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin') or not any(u['name']==name for u in samba_users()):
            raise SystemExit('Not a managed PiNAS Samba user')
        run(['/usr/bin/smbpasswd','-s',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        raise SystemExit(0)
    try:
        group=grp.getgrnam('pinas-nas')
    except KeyError:
        run(['/usr/sbin/groupadd','pinas-nas'])
        group=grp.getgrnam('pinas-nas')
    created=False
    try:
        existing=pwd.getpwnam(name)
    except KeyError:
        existing=None
    if existing:
        # Repair only a partial PiNAS account from a previous failed attempt.
        # Never repurpose unrelated Linux accounts.
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):
            raise SystemExit('Linux account already exists and is not a PiNAS NAS account; choose another username')
        if any(u['name']==name for u in samba_users()):
            raise SystemExit('Samba account already exists; refresh the Users page')
    else:
        run(['/usr/sbin/useradd','--no-create-home','--shell','/usr/sbin/nologin','--gid','pinas-nas',name])
        created=True
    try:
        run(['/usr/bin/smbpasswd','-s','-a',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        run(['/usr/bin/smbpasswd','-e',name],capture_output=True)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        if created:subprocess.run(['/usr/sbin/userdel',name],check=False,timeout=10)
        raise SystemExit('Samba account creation failed: '+str(exc))
"""

NAS_SHARE_HELPER = r"""#!/usr/bin/env python3
# Root-only share broker. Strict input validation and independent mount checks.
import json, os, pathlib, pwd, re, subprocess, sys, tempfile

DB=pathlib.Path('/var/lib/pinas/shares.json')
CONF=pathlib.Path('/etc/samba/pinas-shares.conf')
SMB=pathlib.Path('/etc/samba/smb.conf')

def run(cmd, **kw):
    return subprocess.run(cmd,check=True,timeout=15,capture_output=True,text=True,**kw)

def read_db():
    try:
        value=json.loads(DB.read_text())
        return value if isinstance(value,list) else []
    except (OSError,ValueError):return []

def atomic(path,content,mode=0o600):
    fd,name=tempfile.mkstemp(prefix='.pinas-',dir=str(path.parent))
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'w') as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def check_volume(device):
    if not isinstance(device,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',device) or '..' in device:raise ValueError('Invalid device')
    # Device must be a block device with an approved filesystem.
    p=pathlib.Path(device)
    if not p.is_block_device():raise ValueError('Selected storage is not a block device')
    fs=run(['/usr/bin/lsblk','-n','-o','FSTYPE',device]).stdout.strip().splitlines()
    if not fs or fs[0].strip().lower() not in ('ext4','xfs','btrfs'):raise ValueError('Unsupported filesystem')
    target=run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device]).stdout.strip().splitlines()
    if len(target)!=1:raise ValueError('Disk must have one unambiguous active mount')
    mount=pathlib.Path(target[0]).resolve(strict=True)
    if str(mount) in ('/','/boot','/boot/firmware') or any(str(mount).startswith(prefix) for prefix in ('/etc/','/var/','/usr/','/home/','/opt/','/root/','/proc/','/sys/','/run/')):
        raise ValueError('System storage cannot host NAS shares')
    if not mount.is_dir() or mount.is_symlink():raise ValueError('Invalid mount directory')
    # Confirm mounted persistently via UUID, path or LABEL; do not trust browser data.
    uuid=run(['/usr/sbin/blkid','-s','UUID','-o','value',device]).stdout.strip()
    entries=[line.split() for line in pathlib.Path('/etc/fstab').read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not any(len(e)>=2 and e[1]==str(mount) and e[0] in (device,'UUID='+uuid,'/dev/disk/by-uuid/'+uuid) for e in entries):
        raise ValueError('Disk is not persistently configured in fstab')
    # Reject root device even when mounted at a second location.
    rootdev=run(['/usr/bin/findmnt','-n','-o','SOURCE','/']).stdout.strip()
    if rootdev.startswith('/dev/'):
        rootparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',rootdev]).stdout.split())
        selectedparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',device]).stdout.split())
        if rootparents & selectedparents:raise ValueError('Operating system disk is protected')
    return mount

def main():
    if os.geteuid()!=0:raise ValueError('Root helper required')
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(read_db()));return
    if len(sys.argv)==2 and sys.argv[1]=='delete':
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('Request too large')
        request=json.loads(raw);name=request.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):raise ValueError('Invalid share name')
        current=read_db()
        matches=[item for item in current if isinstance(item,dict) and item.get('name')==name]
        if len(matches)!=1:raise ValueError('Share is not managed by PiNAS')
        oldconf=CONF.read_text()
        # Match only a complete, exact managed Samba section; never touch unrelated shares.
        section=re.compile(r'(?m)^\['+re.escape(name)+r'\][ \t]*\n(?:(?!\[).*(?:\n|$))*')
        found=list(section.finditer(oldconf))
        if len(found)!=1:raise ValueError('Managed Samba share section missing or ambiguous')
        updated=oldconf[:found[0].start()]+oldconf[found[0].end():]
        olddb=DB.read_text()
        try:
            atomic(CONF,updated,0o644)
            run(['/usr/bin/testparm','-s'])
            run(['/usr/bin/systemctl','reload','smbd'])
            atomic(DB,json.dumps([item for item in current if not (isinstance(item,dict) and item.get('name')==name)],indent=2),0o600)
        except Exception:
            atomic(CONF,oldconf,0o644)
            atomic(DB,olddb,0o600)
            try:run(['/usr/bin/systemctl','reload','smbd'])
            except Exception:pass
            raise
        # Deliberately leave the share directory, ACLs and files untouched.
        print(json.dumps({'ok':True,'files_preserved':True}));return
    if len(sys.argv)!=2 or sys.argv[1]!='create':raise ValueError('Unsupported action')
    raw=sys.stdin.read(8193)
    if len(raw)>8192:raise ValueError('Request too large')
    request=json.loads(raw)
    name=request.get('name');access=request.get('access');device=request.get('volume')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):raise ValueError('Invalid share name')
    if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):raise ValueError('Invalid access policy')
    # Verify users exist in Samba and Linux before creating any directory.
    samba={line.split(':',1)[0] for line in run(['/usr/bin/pdbedit','-L']).stdout.splitlines()}
    for user in access:
        if user not in samba:raise ValueError('Samba account not found: '+user)
        pwd.getpwnam(user)
    mount=check_volume(device)
    current=read_db()
    if any(item.get('name','').casefold()==name.casefold() for item in current):raise ValueError('Share already exists')
    # Samba's own configuration may include external shares; reject collisions.
    existing=run(['/usr/bin/testparm','-s']).stdout
    if any(line.strip().casefold()=='['+name.casefold()+']' for line in existing.splitlines()):raise ValueError('Share name already used by Samba')
    # No preexisting folder is ever adopted or modified by this operation.
    root=mount/'PiNAS Shares'
    if root.is_symlink():raise ValueError('Unsafe share root')
    root.mkdir(mode=0o711,exist_ok=True)
    if root.stat().st_uid!=0 or (root.stat().st_mode & 0o022):raise ValueError('Share root must be root-owned and not group/world writable')
    folder=root/name
    if folder.exists() or folder.is_symlink():raise ValueError('Folder already exists; choose a different name')
    if not pathlib.Path('/usr/bin/setfacl').exists():raise ValueError('POSIX ACL tools are required (install acl)')
    # Validate smb.conf can be managed before changing filesystem.
    original=SMB.read_text()
    include='   include = /etc/samba/pinas-shares.conf'
    if include not in original:
        if not re.search(r'(?im)^\s*\[global\]\s*$',original):raise ValueError('Samba [global] section missing')
        amended=re.sub(r'(?im)^(\s*\[global\]\s*)$',r'\1\n'+include,original,count=1)
    else:amended=original
    # Explicit per-user access; default deny for other NAS accounts.
    ro=[u for u,p in access.items() if p=='ro'];rw=[u for u,p in access.items() if p=='rw']
    stanza='\n['+name+']\n   path = '+str(folder)+'\n   browseable = yes\n   guest ok = no\n   read only = yes\n   valid users = '+', '.join(access)+'\n'
    if rw:stanza+='   write list = '+', '.join(rw)+'\n'
    stanza+='   create mask = 0660\n   directory mask = 0770\n   follow symlinks = no\n   wide links = no\n'
    oldconf=CONF.read_text() if CONF.exists() else ''
    if '['+name+']' in oldconf:raise ValueError('Duplicate managed share')
    folder.mkdir(mode=0o700)
    try:
        # Root-owned folder; Samba creates files as authenticated Unix users.
        os.chown(folder,0,0)
        os.chmod(folder,0o700)
        acl=['u::rwx','g::---','o::---','m::rwx']+[f'u:{u}:'+('rwx' if p=='rw' else 'r-x') for u,p in access.items()]
        default=['d:'+entry for entry in acl]
        run(['/usr/bin/setfacl','-m',','.join(acl+default),str(folder)])
        if amended!=original:atomic(SMB,amended,0o644)
        atomic(CONF,oldconf+stanza,0o644)
        run(['/usr/bin/testparm','-s'])
        run(['/usr/bin/systemctl','reload','smbd'])
        current.append({'name':name,'volume_label':mount.name,'volume':device,'access':access})
        atomic(DB,json.dumps(current,indent=2),0o600)
    except Exception:
        atomic(CONF,oldconf,0o644)
        if amended!=original:atomic(SMB,original,0o644)
        try:run(['/usr/bin/systemctl','reload','smbd'])
        except Exception:pass
        try:folder.rmdir()
        except OSError:pass
        raise
    print(json.dumps({'ok':True,'name':name}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

NAS_FILES_HELPER = r"""#!/usr/bin/env python3
# Privileged, narrow file broker. Authentication against Samba passdb; filesystem
# operations executed as the NAS user's actual UID/GID and supplementary groups.
import base64, hashlib, hmac, json, os, pathlib, pwd, re, stat, subprocess, sys
DB=pathlib.Path('/var/lib/pinas/shares.json')
def md4(message):
    # NT hash is MD4(UTF-16LE password). Samba uses NT hashes for SMB auth.
    import struct
    original=len(message);message+=b'\x80';message+=b'\0'*((56-len(message)%64)%64)+struct.pack('<Q',original*8)
    a,b,c,d=0x67452301,0xefcdab89,0x98badcfe,0x10325476
    def rol(v,n):return ((v<<n)|(v>>(32-n)))&0xffffffff
    for offset in range(0,len(message),64):
        x=struct.unpack('<16I',message[offset:offset+64]);aa,bb,cc,dd=a,b,c,d
        for j in range(48):
            if j<16:f=(b&c)|(~b&d);k=j;shift=[3,7,11,19][j%4];constant=0
            elif j<32:f=(b&c)|(b&d)|(c&d);k=(j%4)*4+j//4-4;shift=[3,5,9,13][j%4];constant=0x5a827999
            else:f=b^c^d;k=[0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15][j-32];shift=[3,9,11,15][j%4];constant=0x6ed9eba1
            value=rol((a+f+x[k]+constant)&0xffffffff,shift);a,b,c,d=d,value,b,c
        a=(a+aa)&0xffffffff;b=(b+bb)&0xffffffff;c=(c+cc)&0xffffffff;d=(d+dd)&0xffffffff
    return struct.pack('<4I',a,b,c,d).hex().upper()
def samba_hash(user):
    p=subprocess.run(['/usr/bin/pdbedit','-Lw',user],capture_output=True,text=True,timeout=8)
    if p.returncode:raise ValueError('Unknown NAS account')
    for line in p.stdout.splitlines():
        fields=line.split(':')
        if len(fields)>4 and fields[0]==user and re.fullmatch('[A-Fa-f0-9]{32}',fields[3]):return fields[3].upper()
    raise ValueError('NAS account has no valid Samba password')
def valid_user(user):
    if not isinstance(user,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',user):raise ValueError('Invalid user')
    person=pwd.getpwnam(user)
    if person.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):raise ValueError('Not a PiNAS NAS user')
    if samba_hash(user)=='':raise ValueError('Not a Samba user')
    return person
def shares_for(user):
    entries=json.loads(DB.read_text())
    return [s for s in entries if isinstance(s,dict) and s.get('access',{}).get(user) in ('ro','rw')]
def drop(person):
    os.initgroups(person.pw_name,person.pw_gid);os.setgid(person.pw_gid);os.setuid(person.pw_uid)
def safe_path(root,relative):
    if not isinstance(relative,str) or len(relative)>1000 or relative.startswith('/') or '\\' in relative or '\x00' in relative:raise ValueError('Invalid path')
    parts=relative.split('/') if relative else []
    if any(x in ('','.','..') or x.startswith('.pinas-upload-') for x in parts):raise ValueError('Invalid path')
    # Reject symlinks at every level, including the leaf. Never follow them.
    cur=root
    for part in parts:
        cur=cur/part
        if cur.is_symlink():raise ValueError('Symbolic links are not accessible')
    if not cur.resolve(strict=False).is_relative_to(root.resolve(strict=True)):raise ValueError('Path outside share')
    return cur
def main():
    if os.geteuid()!=0:raise ValueError('Root required')
    raw=sys.stdin.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise ValueError('Request too large')
    q=json.loads(raw);action=q.get('action');user=q.get('username');person=valid_user(user)
    if action=='authenticate':
        password=q.get('password')
        if not isinstance(password,str) or len(password)>256:raise ValueError('Invalid password')
        print('true' if hmac.compare_digest(md4(password.encode('utf-16le')),samba_hash(user)) else 'false');return
    allowed=shares_for(user)
    if action=='shares':
        print(json.dumps({'shares':[{'name':s['name'],'read_only':s['access'][user]=='ro'} for s in allowed]}));return
    share=q.get('share');s=next((x for x in allowed if x['name']==share),None)
    if s is None:raise ValueError('Share not accessible')
    # Root path derived exclusively from privileged share metadata, not browser paths.
    root=pathlib.Path(s['volume_label']) if False else None
    # Resolve mount from device, and confirm it is still the same mounted filesystem.
    device=s['volume'];p=subprocess.run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device],capture_output=True,text=True,timeout=5)
    targets=p.stdout.strip().splitlines()
    if p.returncode or len(targets)!=1:raise ValueError('Share storage is offline')
    mount=pathlib.Path(targets[0]).resolve(strict=True)
    if str(mount)=='/' or str(mount).startswith(('/etc/','/var/','/usr/','/home/','/boot/')):raise ValueError('Protected mount')
    root=mount/'PiNAS Shares'/s['name']
    if root.is_symlink() or not root.is_dir():raise ValueError('Share folder unavailable')
    relative=q.get('path','');target=safe_path(root,relative)
    writable=s['access'][user]=='rw'
    if action in ('mkdir','delete','rename','move','copy','upload','upload_start','upload_chunk','upload_finish','upload_cancel') and not writable:raise ValueError('Read-only share')
    drop(person)
    # All operations below run with the NAS user's UID/GID. Uploads are staged
    # in the destination directory, then published by an atomic rename.
    def valid_name(name):
        if not isinstance(name,str) or not name or len(name)>255 or name in ('.','..') or '/' in name or '\\' in name or '\x00' in name or name.startswith('.pinas-upload-'):raise ValueError('Invalid file name')
        return name
    def destination(relative):
        dest=safe_path(root,relative)
        if dest==root or dest.exists() or dest.is_symlink():raise ValueError('Destination already exists')
        if not dest.parent.is_dir():raise ValueError('Destination folder does not exist')
        return dest
    if action in ('rename','move','copy'):
        if target==root or not target.exists():raise ValueError('Invalid source')
        if action=='rename':
            dest=destination('/'.join(filter(None,[relative.rsplit('/',1)[0] if '/' in relative else '',valid_name(q.get('name'))])))
        else:
            dest=destination(q.get('dest',''))
        if target.is_dir() and (dest==target or target in dest.parents):raise ValueError('Cannot place folder inside itself')
        if action=='copy':
            import shutil
            if target.is_dir():
                # Reject links anywhere in the tree and cap total copy size.
                total=0
                for directory,dirs,files in os.walk(target,followlinks=False):
                    for name in dirs+files:
                        node=pathlib.Path(directory)/name
                        if node.is_symlink():raise ValueError('Symbolic links cannot be copied')
                        if node.is_file():total+=node.stat().st_size
                        if total>8*1024**3:raise ValueError('Folder copy exceeds 8 GiB safety limit')
                shutil.copytree(target,dest,symlinks=False)
            elif target.is_file():
                with target.open('rb') as src, dest.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            else:raise ValueError('Unsupported file type')
        else:
            # Same-share only; atomic rename prevents partial moves.
            if target.is_file():
                os.link(target,dest,follow_symlinks=False);target.unlink()
            else:target.rename(dest)
        print('{"ok":true}');return
    if action=='upload_start':
        name=valid_name(q.get('name'))
        if not target.is_dir():raise ValueError('Not a folder')
        destination('/'.join(filter(None,[relative,name])))
        size=q.get('size')
        if not isinstance(size,int) or size<0 or size>100*1024**3:raise ValueError('Invalid upload size')
        import secrets
        token=secrets.token_hex(20)
        staging=target/('.pinas-upload-'+token)
        fd=os.open(staging,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        meta=target/('.pinas-upload-'+token+'.json')
        fd=os.open(meta,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'name':name,'size':size,'path':relative},f)
        print(json.dumps({'token':token}));return
    if action in ('upload_chunk','upload_finish','upload_cancel'):
        token=q.get('token','')
        if not isinstance(token,str) or not re.fullmatch('[0-9a-f]{40}',token):raise ValueError('Invalid transfer token')
        stage=target/('.pinas-upload-'+token)
        meta=target/('.pinas-upload-'+token+'.json')
        if stage.is_symlink() or meta.is_symlink() or not stage.is_file() or not meta.is_file():raise ValueError('Unknown transfer')
        details=json.loads(meta.read_text());name=valid_name(details['name']);size=details['size']
        if details.get('path')!=relative:raise ValueError('Transfer location mismatch')
        if action=='upload_cancel':stage.unlink();meta.unlink();print('{"ok":true}');return
        if action=='upload_chunk':
            content=q.get('content','');offset=q.get('offset')
            if not isinstance(content,str) or len(content)>700000 or not isinstance(offset,int):raise ValueError('Invalid chunk')
            payload=base64.b64decode(content,validate=True)
            if len(payload)>512*1024 or offset!=stage.stat().st_size or offset+len(payload)>size:raise ValueError('Chunk offset or size mismatch')
            with stage.open('ab') as f:f.write(payload)
            print(json.dumps({'offset':offset+len(payload)}));return
        if stage.stat().st_size!=size:raise ValueError('Upload incomplete')
        dest=destination('/'.join(filter(None,[relative,name])))
        # Hard-link is no-clobber and atomic on the same filesystem.
        os.link(stage,dest,follow_symlinks=False);stage.unlink();meta.unlink()
        print('{"ok":true}');return
    if action=='download_chunk':
        offset=q.get('offset');size=q.get('size')
        if not isinstance(offset,int) or offset<0 or not isinstance(size,int) or size<1 or size>512*1024:raise ValueError('Invalid download range')
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode):raise ValueError('Not a regular file')
        total=target.stat().st_size
        with target.open('rb') as f:f.seek(offset);chunk=f.read(size)
        print(json.dumps({'content':base64.b64encode(chunk).decode(),'total':total}));return
    if action=='list':
        if not target.is_dir():raise ValueError('Not a folder')
        entries=[]
        for child in sorted(target.iterdir(),key=lambda x:x.name.casefold()):
            if child.is_symlink() or child.name.startswith('.pinas-upload-'):continue
            try:st=child.stat()
            except OSError:continue
            if stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode):entries.append({'name':child.name,'dir':stat.S_ISDIR(st.st_mode),'size':st.st_size})
            if len(entries)>=1000:break
        print(json.dumps({'entries':entries}));return
    if action=='mkdir':
        name=q.get('name','');dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..'):raise ValueError('Invalid folder name')
        dest.mkdir(mode=0o770);print('{"ok":true}');return
    if action=='delete':
        if target==root:raise ValueError('Cannot delete share root')
        if target.is_dir():target.rmdir()
        elif target.is_file():target.unlink()
        else:raise ValueError('Not a regular file or empty folder')
        print('{"ok":true}');return
    if action=='download':
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode) or target.stat().st_size>3*1024*1024:raise ValueError('Only files up to 3 MB supported in this test build')
        with target.open('rb') as f:content=base64.b64encode(f.read()).decode()
        print(json.dumps({'content':content}));return
    if action=='upload':
        name=q.get('name','');content=q.get('content','')
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..') or not isinstance(content,str) or len(content)>4*1024*1024+16:raise ValueError('Invalid upload')
        dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not target.is_dir():raise ValueError('Not a directory')
        payload=base64.b64decode(content,validate=True)
        if len(payload)>3*1024*1024:raise ValueError('Upload exceeds 3 MB')
        fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o660)
        with os.fdopen(fd,'wb') as f:f.write(payload)
        print('{"ok":true}');return
    raise ValueError('Unsupported action')
if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
"""

APT_INDEX_HELPER = r"""#!/usr/bin/env python3
import os,subprocess,sys
from pathlib import Path
ALLOWED={'off':None,'daily':'*-*-* 01:00:00','weekly':'Fri *-*-* 01:00:00','monthly':'*-*-28 01:00:00'}
def run(cmd,timeout=30):
    p=subprocess.run(cmd,timeout=timeout,check=False)
    if p.returncode:sys.exit(p.returncode)
def main():
    if os.geteuid()!=0:sys.exit('Root access required')
    args=sys.argv[1:]
    if len(args)==2 and args[0]=='schedule' and args[1] in ALLOWED:
        schedule=args[1];calendar=ALLOWED[schedule]
        timer=Path('/etc/systemd/system/pinas-auto-updates.timer')
        if calendar:
            timer.write_text('[Unit]\nDescription=PiNAS automatic OS updates\n[Timer]\nOnCalendar='+calendar+'\nPersistent=true\nUnit=pinas-auto-updates.service\n[Install]\nWantedBy=timers.target\n')
        run(['systemctl','daemon-reload'])
        if calendar:
            run(['systemctl','enable','--now','pinas-auto-updates.timer'])
            run(['systemctl','restart','pinas-auto-updates.timer'])
        else:
            run(['systemctl','disable','--now','pinas-auto-updates.timer']) if timer.exists() else None
            timer.unlink(missing_ok=True)
            run(['systemctl','daemon-reload'])
        marker=Path('/var/lib/pinas/update-schedule');marker.write_text(schedule+'\n');os.chmod(marker,0o644)
        return
    if args==['automatic']:
        # Only the systemd oneshot invokes this command, not the web service account.
        run(['/usr/bin/apt-get','update'],210)
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
        return
    if args==['upgrade']:
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
    elif args==['refresh']:
        run(['/usr/bin/apt-get','update'],210)
    else:sys.exit('Unsupported operation')
if __name__=='__main__':main()
"""

NAS_STORAGE_HELPER='#!/usr/bin/env python3\n"""PiNAS RC13 restricted, non-destructive storage adoption helper."""\nimport json,os,pathlib,re,subprocess,sys,uuid\nfrom pathlib import Path\n\ndef run(*args,timeout=15):\n    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)\n    if p.returncode:raise ValueError((p.stderr or \'Storage command failed\').strip()[-500:])\n    return p.stdout.strip()\n\ndef main():\n    if os.geteuid()!=0 or sys.argv[1:]!=[\'adopt\']:raise ValueError(\'Unsupported storage operation\')\n    data=json.loads(sys.stdin.read(4096));device=data.get(\'device\')\n    if not isinstance(device,str) or not re.fullmatch(r\'/dev/[A-Za-z0-9_./-]{1,90}\',device) or \'..\' in device:raise ValueError(\'Invalid device\')\n    path=Path(device)\n    if not path.is_block_device():raise ValueError(\'Device is not a block device\')\n    # The privileged helper independently identifies eligible physical disks.\n    roots=json.loads(run(\'lsblk\',\'-J\',\'-b\',\'-o\',\'NAME,PATH,TYPE,FSTYPE,UUID,MOUNTPOINTS,RO,PKNAME\')).get(\'blockdevices\',[])\n    bypath={};byname={};parents={}\n    def walk(node,parent=None):\n        name=node.get(\'name\');bypath[node.get(\'path\')]=node;byname[name]=node\n        if parent:parents[name]=parent\n        for child in node.get(\'children\') or []:walk(child,name)\n    for root in roots:walk(root)\n    node=bypath.get(str(path.resolve())) or bypath.get(device)\n    if not node or node.get(\'type\') not in (\'part\',\'disk\') or node.get(\'ro\'):raise ValueError(\'Not an eligible writable disk or partition\')\n    def root_for(n):\n        seen=set()\n        while n.get(\'name\') in parents:\n            if n[\'name\'] in seen:raise ValueError(\'Invalid device topology\')\n            seen.add(n[\'name\']);n=byname[parents[n[\'name\']]]\n        return n\n    disk=root_for(node)\n    if disk.get(\'type\')!=\'disk\' or disk.get(\'ro\') or str(disk.get(\'name\',\'\')).startswith((\'loop\',\'zram\',\'ram\',\'nbd\',\'sr\',\'fd\')):raise ValueError(\'Unsupported backing device\')\n    # Reject any physical disk carrying the root or boot filesystems.\n    protected={\'/\',\'/boot\',\'/boot/firmware\',\'/boot/efi\'}\n    def contains_system(n):\n        if any(m in protected for m in (n.get(\'mountpoints\') or []) if m):return True\n        return any(contains_system(c) for c in n.get(\'children\') or [])\n    if contains_system(disk):raise ValueError(\'Operating system storage is protected\')\n    for mount in protected:\n        src=run(\'findmnt\',\'-n\',\'-o\',\'SOURCE\',\'--target\',mount).split(\'[\',1)[0]\n        if src and src in bypath and root_for(bypath[src]).get(\'name\')==disk.get(\'name\'):\n            raise ValueError(\'Operating system storage is protected\')\n    fs=run(\'blkid\',\'-s\',\'TYPE\',\'-o\',\'value\',device)\n    uid=run(\'blkid\',\'-s\',\'UUID\',\'-o\',\'value\',device)\n    if fs not in (\'ext4\',\'xfs\',\'btrfs\') or not re.fullmatch(r\'[A-Za-z0-9-]{8,64}\',uid):raise ValueError(\'Supported filesystem and UUID required\')\n    # Reject RAID/LVM/crypto members and nested volume layouts.\n    if node.get(\'type\')==\'disk\' and node.get(\'children\'):raise ValueError(\'Choose a filesystem partition, not its parent disk\')\n    if node.get(\'children\'):raise ValueError(\'Complex volume layout not supported\')\n    mountpoints=[m for m in node.get(\'mountpoints\') or [] if m]\n    if len(mountpoints)>1:raise ValueError(\'Multiple mountpoints require manual review\')\n    if mountpoints and not str(mountpoints[0]).startswith(\'/mnt/pinas/\'):\n        raise ValueError(\'Filesystem is already mounted elsewhere; manage it manually to avoid disrupting applications\')\n    target=Path(\'/mnt/pinas\')/uid\n    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir())) and str(target) not in mountpoints):raise ValueError(\'Mount destination is not empty\')\n    fstab=Path(\'/etc/fstab\');original=fstab.read_text();entries=[line.split() for line in original.splitlines() if line.strip() and not line.lstrip().startswith(\'#\')]\n    for e in entries:\n        if len(e)>=2 and (e[0] in (device,\'UUID=\'+uid,\'/dev/disk/by-uuid/\'+uid) or e[1]==str(target)):\n            if e[0]==\'UUID=\'+uid and e[1]==str(target):\n                if str(target) not in mountpoints:run(\'mount\',str(target),timeout=25)\n                print(json.dumps({\'ok\':True,\'mount\':str(target),\'existing\':True}));return\n            raise ValueError(\'Existing fstab configuration requires manual review\')\n    target.parent.mkdir(parents=True,exist_ok=True)\n    target.mkdir(mode=0o755,exist_ok=True)\n    options=\'defaults,nofail,noatime,x-systemd.device-timeout=10s\'\n    entry=f\'UUID={uid} {target} {fs} {options} 0 {2 if fs=="ext4" else 0} # PiNAS managed\\\\n\'\n    entry=entry.replace(\'\\\\n\',\'\\n\')\n    backup=fstab.with_name(\'fstab.pinas-\'+uuid.uuid4().hex[:12]+\'.bak\')\n    backup.write_text(original);os.chmod(backup,0o600)\n    temp=fstab.with_name(\'.fstab.pinas-\'+uuid.uuid4().hex)\n    try:\n        temp.write_text(original.rstrip(\'\\n\')+\'\\n\'+entry);os.chmod(temp,0o644)\n        os.replace(temp,fstab)\n        run(\'systemctl\',\'daemon-reload\',timeout=15)\n        run(\'mount\',str(target),timeout=25)\n        actual=run(\'findmnt\',\'-n\',\'-o\',\'UUID\',\'--target\',str(target))\n        if actual!=uid:raise ValueError(\'Mounted filesystem UUID verification failed\')\n    except Exception:\n        fstab.write_text(original)\n        try:run(\'systemctl\',\'daemon-reload\')\n        except Exception:pass\n        raise\n    print(json.dumps({\'ok\':True,\'mount\':str(target)}))\nif __name__==\'__main__\':\n    try:main()\n    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)\n'

SMART_HEALTH_HELPER = """#!/usr/bin/env python3
import json,os,shutil,subprocess,sys
from pathlib import Path
def main():
    if os.geteuid()!=0 or len(sys.argv)!=1:
        raise ValueError('Unsupported operation')
    smartctl=shutil.which('smartctl')
    if not smartctl:
        print(json.dumps({'installed':False,'drives':[]}));return
    p=subprocess.run(['lsblk','-J','-b','-o','NAME,PATH,TYPE,MODEL,TRAN'],capture_output=True,text=True,timeout=8,check=True)
    drives=[]
    for disk in json.loads(p.stdout).get('blockdevices',[]):
        if disk.get('type')!='disk':continue
        device=disk.get('path','')
        if not isinstance(device,str) or not device.startswith('/dev/') or not Path(device).is_block_device():continue
        if disk.get('name','').startswith(('loop','zram','ram','nbd','sr','fd')):continue
        entry={'device':device,'model':disk.get('model') or disk.get('name'),'status':'Unavailable','temperature':None}
        try:
            result=subprocess.run([smartctl,'-j','-H','-A',device],capture_output=True,text=True,timeout=12)
            data=json.loads(result.stdout)
            health=data.get('smart_status',{}).get('passed')
            if health is True:entry['status']='Healthy'
            elif health is False:entry['status']='Warning'
            temp=data.get('temperature',{}).get('current')
            if isinstance(temp,(int,float)) and -20<=temp<=120:entry['temperature']=temp
            if data.get('smart_support',{}).get('available') is False:entry['status']='Unsupported'
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        drives.append(entry)
    print(json.dumps({'installed':True,'drives':drives}))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

def install(args):
    if sys.platform!='linux' or os.geteuid()!=0:sys.exit('Install requires Linux and sudo/root.')
    if not Path('/etc/os-release').exists():sys.exit('Unsupported OS')
    osinfo=read('/etc/os-release')
    if 'debian' not in osinfo.lower() and 'raspbian' not in osinfo.lower():sys.exit('Requires Raspberry Pi OS / Debian family')
    if not args.skip_packages:
        print('Installing NAS dependencies (requires network and may take time)...',flush=True)
        subprocess.run(['apt-get','update'],check=True)
        subprocess.run(['apt-get','install','-y','samba','xfsprogs','btrfs-progs','mdadm','parted','util-linux','e2fsprogs','avahi-daemon','acl','openssl'],check=True)
    target=Path('/opt/pinas');target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(__file__).resolve(),target/'pinas.py');os.chmod(target/'pinas.py',0o755)
    if subprocess.run(['id','-u','pinas'],capture_output=True).returncode!=0:
        subprocess.run(['useradd','--system','--home-dir','/var/lib/pinas','--shell','/usr/sbin/nologin','pinas'],check=True)
    DATA.mkdir(parents=True,exist_ok=True);os.chmod(DATA,0o700)
    subprocess.run(['chown','pinas:pinas',str(DATA)],check=True)
    helper=Path('/usr/local/libexec/pinas-apply-hostname')
    helper.parent.mkdir(parents=True,exist_ok=True)
    helper.write_text(HOSTNAME_HELPER)
    os.chmod(helper,0o755)
    unit='''[Unit]\nDescription=Apply validated PiNAS device hostname\nAfter=systemd-hostnamed.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /usr/local/libexec/pinas-apply-hostname\nNoNewPrivileges=true\nProtectHome=true\nPrivateTmp=true\n'''
    Path('/etc/systemd/system/pinas-hostname.service').write_text(unit)
    path_unit='''[Unit]\nDescription=Apply PiNAS hostname when configuration changes\n[Path]\nPathChanged=/var/lib/pinas/config.json\nUnit=pinas-hostname.service\n[Install]\nWantedBy=multi-user.target\n'''
    Path('/etc/systemd/system/pinas-hostname.path').write_text(path_unit)
    user_helper=Path('/usr/local/libexec/pinas-nas-user')
    user_helper.write_text(NAS_USER_HELPER)
    os.chown(user_helper,0,0);os.chmod(user_helper,0o700)
    sudoers=Path('/etc/sudoers.d/pinas-nas-user')
    sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-user create *, /usr/local/libexec/pinas-nas-user password *, /usr/local/libexec/pinas-nas-user list\n')
    os.chown(sudoers,0,0);os.chmod(sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(sudoers)],capture_output=True).returncode:
        sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS sudoers configuration')
    share_helper=Path('/usr/local/libexec/pinas-nas-share')
    share_helper.write_text(NAS_SHARE_HELPER)
    os.chown(share_helper,0,0);os.chmod(share_helper,0o700)
    share_sudoers=Path('/etc/sudoers.d/pinas-nas-share')
    share_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-share list, /usr/local/libexec/pinas-nas-share create\n')
    os.chown(share_sudoers,0,0);os.chmod(share_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(share_sudoers)],capture_output=True).returncode:
        share_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS share sudoers configuration')
    files_helper=Path('/usr/local/libexec/pinas-nas-files')
    files_helper.write_text(NAS_FILES_HELPER)
    os.chown(files_helper,0,0);os.chmod(files_helper,0o700)
    files_sudoers=Path('/etc/sudoers.d/pinas-nas-files')
    files_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-files\n')
    os.chown(files_sudoers,0,0);os.chmod(files_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(files_sudoers)],capture_output=True).returncode:
        files_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS file helper sudoers configuration')
    storage_helper=Path('/usr/local/libexec/pinas-nas-storage')
    storage_helper.write_text(NAS_STORAGE_HELPER)
    os.chown(storage_helper,0,0);os.chmod(storage_helper,0o700)
    storage_sudoers=Path('/etc/sudoers.d/pinas-nas-storage')
    storage_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-storage adopt\n')
    os.chown(storage_sudoers,0,0);os.chmod(storage_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(storage_sudoers)],capture_output=True).returncode:
        storage_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS storage sudoers configuration')
    smart_helper=Path('/usr/local/libexec/pinas-smart-health')
    smart_helper.write_text(SMART_HEALTH_HELPER)
    os.chown(smart_helper,0,0);os.chmod(smart_helper,0o700)
    smart_sudoers=Path('/etc/sudoers.d/pinas-smart-health')
    smart_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-smart-health\n')
    os.chown(smart_sudoers,0,0);os.chmod(smart_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(smart_sudoers)],capture_output=True).returncode:
        smart_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS SMART sudoers configuration')
    apt_helper=Path('/usr/local/libexec/pinas-apt-index')
    apt_helper.write_text(APT_INDEX_HELPER)
    os.chown(apt_helper,0,0);os.chmod(apt_helper,0o700)
    apt_sudoers=Path('/etc/sudoers.d/pinas-apt-index')
    apt_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-apt-index refresh, /usr/local/libexec/pinas-apt-index upgrade, /usr/local/libexec/pinas-apt-index schedule off, /usr/local/libexec/pinas-apt-index schedule daily, /usr/local/libexec/pinas-apt-index schedule weekly, /usr/local/libexec/pinas-apt-index schedule monthly\n')
    os.chown(apt_sudoers,0,0);os.chmod(apt_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(apt_sudoers)],capture_output=True).returncode:
        apt_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS APT sudoers configuration')
    auto_service=Path('/etc/systemd/system/pinas-auto-updates.service')
    auto_service.write_text('[Unit]\nDescription=PiNAS scheduled OS updates\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=oneshot\nExecStart=/usr/local/libexec/pinas-apt-index automatic\nEnvironment=DEBIAN_FRONTEND=noninteractive\n')
    os.chown(auto_service,0,0);os.chmod(auto_service,0o644)
    # Existing schedule is preserved when upgrading PiNAS.
    # Generate a persistent per-install certificate; never replace it on upgrades.
    if not TLS_CERT.exists() or not TLS_KEY.exists():
        if TLS_CERT.exists() or TLS_KEY.exists():sys.exit('Incomplete TLS certificate pair; resolve manually before installing')
        if not shutil.which('openssl'):sys.exit('OpenSSL required for initial TLS certificate generation')
        hostname=load().get('hostname','pinas')
        if not valid_hostname(hostname):hostname='pinas'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','825',
            '-keyout',str(TLS_KEY),'-out',str(TLS_CERT),'-subj',f'/CN={hostname}.local',
            '-addext',f'subjectAltName=DNS:{hostname}.local,DNS:localhost,IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL)
    for f,mode in ((TLS_CERT,0o644),(TLS_KEY,0o600)):
        os.chown(f,0 if f==TLS_CERT else __import__('pwd').getpwnam('pinas').pw_uid,0 if f==TLS_CERT else __import__('grp').getgrnam('pinas').gr_gid)
        os.chmod(f,mode)
    bind_host='0.0.0.0' if args.lan else '127.0.0.1' 
    # TEMPORARY RC9.2: sudo inherits the service mount namespace. A root helper
    # cannot write /etc/passwd, /etc/group or Samba state with ProtectSystem=strict.
    # Replace sudo delegation with an independently sandboxed privileged service.
    service='''[Unit]\nDescription=PiNAS prototype web dashboard\nAfter=network.target\n[Service]\nType=simple\nUser=pinas\nGroup=pinas\nExecStart=/usr/bin/python3 /opt/pinas/pinas.py --serve --tls --host %s --port %d\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=false\nProtectSystem=false\nReadWritePaths=/var/lib/pinas\nPrivateTmp=true\n[Install]\nWantedBy=multi-user.target\n'''%(bind_host,args.port)
    Path('/etc/systemd/system/pinas.service').write_text(service)
    subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','enable','--now','pinas-hostname.path'],check=True);subprocess.run(['systemctl','start','pinas-hostname.service'],check=True);subprocess.run(['systemctl','enable','pinas.service'],check=True);subprocess.run(['systemctl','restart','pinas.service'],check=True)
    print(f'PiNAS installed. For localhost access: https://127.0.0.1:{args.port} (self-signed certificate)')
    if args.lan:print(f'LAN TLS MODE: open https://<PI-IP>:{args.port}. Certificate is self-signed; use the .local hostname for name matching. Do not expose this port to the internet.')
    else:print('Localhost-only mode; re-run installer with --lan to enable direct LAN access for testing.')

def main():
    ap=argparse.ArgumentParser(description='PiNAS Raspberry Pi NAS prototype')
    ap.add_argument('--lan',action='store_true',help='Bind HTTPS server to LAN interfaces');ap.add_argument('--install',action='store_true');ap.add_argument('--serve',action='store_true');ap.add_argument('--tls',action='store_true');ap.add_argument('--skip-packages',action='store_true');ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=8765)
    a=ap.parse_args()
    if a.install:install(a);return
    if a.serve:
        if a.host not in ('127.0.0.1','::1','0.0.0.0'):sys.exit('Unsupported bind address.')
        if a.host=='0.0.0.0' and not a.tls:sys.exit('LAN listening requires HTTPS (--tls)')
        server=ThreadingHTTPServer((a.host,a.port),Handler)
        if a.tls:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(TLS_CERT),str(TLS_KEY))
            server.socket=context.wrap_socket(server.socket,server_side=True)
        print('PiNAS running on %s://%s:%s'%('https' if a.tls else 'http',a.host,a.port))
        threading.Thread(target=cpu_sampler,daemon=True).start();server.serve_forever();return
    ap.print_help()
if __name__=='__main__':main())
        if not valid(name) or not valid(new_name):raise ValueError('Invalid share name')
        if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not isinstance(u,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):raise ValueError('Invalid permissions')
        current=read_db()
        matches=[i for i in current if isinstance(i,dict) and i.get('name')==name]
        if len(matches)!=1:raise ValueError('Share is not managed by PiNAS')
        if any(i.get('name','').casefold()==new_name.casefold() and i.get('name')!=name for i in current if isinstance(i,dict)):raise ValueError('Share name already exists')
        samba={line.split(':',1)[0] for line in run(['/usr/bin/pdbedit','-L']).stdout.splitlines()}
        for user in access:
            if user not in samba:raise ValueError('Samba account not found: '+user)
            pwd.getpwnam(user)
        item=matches[0]
        mount=check_volume(item.get('volume'))
        folder=pathlib.Path(item.get('folder') or str(mount/'PiNAS Shares'/name))
        if folder.parent!=mount/'PiNAS Shares' or folder.is_symlink() or not folder.is_dir() or folder.stat().st_uid!=0:raise ValueError('Unsafe managed share folder')
        oldconf=CONF.read_text()
        section=re.compile(r'(?m)^\\['+re.escape(name)+r'\\][ \\t]*\\n(?:(?!\\[).*(?:\\n|$))*')
        found=list(section.finditer(oldconf))
        if len(found)!=1:raise ValueError('Managed share section missing or ambiguous')
        if new_name!=name:
            existing=run(['/usr/bin/testparm','-s']).stdout
            if any(line.strip().casefold()=='['+new_name.casefold()+']' for line in existing.splitlines()):raise ValueError('Share name already used by Samba')
        ro=[u for u,p in access.items() if p=='ro'];rw=[u for u,p in access.items() if p=='rw']
        stanza='['+new_name+']\\n   path = '+str(folder)+'\\n   browseable = yes\\n   guest ok = no\\n   read only = yes\\n   valid users = '+', '.join(access)+'\\n'
        if rw:stanza+='   write list = '+', '.join(rw)+'\\n'
        stanza+='   create mask = 0660\\n   directory mask = 0770\\n   follow symlinks = no\\n   wide links = no\\n'
        newconf=oldconf[:found[0].start()]+stanza+oldconf[found[0].end():]
        olddb=DB.read_text()
        oldacl=run(['/usr/bin/getfacl','-p',str(folder)]).stdout
        acl=['u::rwx','g::---','o::---','m::rwx']+[f'u:{u}:'+('rwx' if p=='rw' else 'r-x') for u,p in access.items()]
        try:
            # Clear obsolete named user ACLs on the share root; leave contents untouched.
            run(['/usr/bin/setfacl','-b',str(folder)])
            run(['/usr/bin/setfacl','-k',str(folder)])
            run(['/usr/bin/setfacl','-m',','.join(acl+['d:'+entry for entry in acl]),str(folder)])
            atomic(CONF,newconf,0o644)
            run(['/usr/bin/testparm','-s'])
            run(['/usr/bin/systemctl','reload','smbd'])
            item['name']=new_name;item['access']=access;item['folder']=str(folder)
            atomic(DB,json.dumps(current,indent=2),0o600)
        except Exception:
            atomic(CONF,oldconf,0o644)
            atomic(DB,olddb,0o600)
            try:
                restore=subprocess.run(['/usr/bin/setfacl','--restore=-'],input=oldacl,text=True,capture_output=True,timeout=15)
                if restore.returncode:raise ValueError(restore.stderr)
            except Exception:pass
            try:run(['/usr/bin/systemctl','reload','smbd'])
            except Exception:pass
            raise
        print(json.dumps({'ok':True,'name':new_name}));return
    if len(sys.argv)==2 and sys.argv[1]=='delete':
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('Request too large')
        request=json.loads(raw);name=request.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):raise ValueError('Invalid share name')
        current=read_db()
        matches=[item for item in current if isinstance(item,dict) and item.get('name')==name]
        if len(matches)!=1:raise ValueError('Share is not managed by PiNAS')
        oldconf=CONF.read_text()
        # Match only a complete, exact managed Samba section; never touch unrelated shares.
        section=re.compile(r'(?m)^\['+re.escape(name)+r'\][ \t]*\n(?:(?!\[).*(?:\n|$))*')
        found=list(section.finditer(oldconf))
        if len(found)!=1:raise ValueError('Managed Samba share section missing or ambiguous')
        updated=oldconf[:found[0].start()]+oldconf[found[0].end():]
        olddb=DB.read_text()
        try:
            atomic(CONF,updated,0o644)
            run(['/usr/bin/testparm','-s'])
            run(['/usr/bin/systemctl','reload','smbd'])
            atomic(DB,json.dumps([item for item in current if not (isinstance(item,dict) and item.get('name')==name)],indent=2),0o600)
        except Exception:
            atomic(CONF,oldconf,0o644)
            atomic(DB,olddb,0o600)
            try:run(['/usr/bin/systemctl','reload','smbd'])
            except Exception:pass
            raise
        # Deliberately leave the share directory, ACLs and files untouched.
        print(json.dumps({'ok':True,'files_preserved':True}));return
    if len(sys.argv)!=2 or sys.argv[1]!='create':raise ValueError('Unsupported action')
    raw=sys.stdin.read(8193)
    if len(raw)>8192:raise ValueError('Request too large')
    request=json.loads(raw)
    name=request.get('name');access=request.get('access');device=request.get('volume')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):raise ValueError('Invalid share name')
    if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):raise ValueError('Invalid access policy')
    # Verify users exist in Samba and Linux before creating any directory.
    samba={line.split(':',1)[0] for line in run(['/usr/bin/pdbedit','-L']).stdout.splitlines()}
    for user in access:
        if user not in samba:raise ValueError('Samba account not found: '+user)
        pwd.getpwnam(user)
    mount=check_volume(device)
    current=read_db()
    if any(item.get('name','').casefold()==name.casefold() for item in current):raise ValueError('Share already exists')
    # Samba's own configuration may include external shares; reject collisions.
    existing=run(['/usr/bin/testparm','-s']).stdout
    if any(line.strip().casefold()=='['+name.casefold()+']' for line in existing.splitlines()):raise ValueError('Share name already used by Samba')
    # No preexisting folder is ever adopted or modified by this operation.
    root=mount/'PiNAS Shares'
    if root.is_symlink():raise ValueError('Unsafe share root')
    root.mkdir(mode=0o711,exist_ok=True)
    if root.stat().st_uid!=0 or (root.stat().st_mode & 0o022):raise ValueError('Share root must be root-owned and not group/world writable')
    folder=root/name
    if folder.exists() or folder.is_symlink():raise ValueError('Folder already exists; choose a different name')
    if not pathlib.Path('/usr/bin/setfacl').exists():raise ValueError('POSIX ACL tools are required (install acl)')
    # Validate smb.conf can be managed before changing filesystem.
    original=SMB.read_text()
    include='   include = /etc/samba/pinas-shares.conf'
    if include not in original:
        if not re.search(r'(?im)^\s*\[global\]\s*$',original):raise ValueError('Samba [global] section missing')
        amended=re.sub(r'(?im)^(\s*\[global\]\s*)$',r'\1\n'+include,original,count=1)
    else:amended=original
    # Explicit per-user access; default deny for other NAS accounts.
    ro=[u for u,p in access.items() if p=='ro'];rw=[u for u,p in access.items() if p=='rw']
    stanza='\n['+name+']\n   path = '+str(folder)+'\n   browseable = yes\n   guest ok = no\n   read only = yes\n   valid users = '+', '.join(access)+'\n'
    if rw:stanza+='   write list = '+', '.join(rw)+'\n'
    stanza+='   create mask = 0660\n   directory mask = 0770\n   follow symlinks = no\n   wide links = no\n'
    oldconf=CONF.read_text() if CONF.exists() else ''
    if '['+name+']' in oldconf:raise ValueError('Duplicate managed share')
    folder.mkdir(mode=0o700)
    try:
        # Root-owned folder; Samba creates files as authenticated Unix users.
        os.chown(folder,0,0)
        os.chmod(folder,0o700)
        acl=['u::rwx','g::---','o::---','m::rwx']+[f'u:{u}:'+('rwx' if p=='rw' else 'r-x') for u,p in access.items()]
        default=['d:'+entry for entry in acl]
        run(['/usr/bin/setfacl','-m',','.join(acl+default),str(folder)])
        if amended!=original:atomic(SMB,amended,0o644)
        atomic(CONF,oldconf+stanza,0o644)
        run(['/usr/bin/testparm','-s'])
        run(['/usr/bin/systemctl','reload','smbd'])
        current.append({'name':name,'volume_label':mount.name,'volume':device,'access':access})
        atomic(DB,json.dumps(current,indent=2),0o600)
    except Exception:
        atomic(CONF,oldconf,0o644)
        if amended!=original:atomic(SMB,original,0o644)
        try:run(['/usr/bin/systemctl','reload','smbd'])
        except Exception:pass
        try:folder.rmdir()
        except OSError:pass
        raise
    print(json.dumps({'ok':True,'name':name}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

NAS_FILES_HELPER = r"""#!/usr/bin/env python3
# Privileged, narrow file broker. Authentication against Samba passdb; filesystem
# operations executed as the NAS user's actual UID/GID and supplementary groups.
import base64, hashlib, hmac, json, os, pathlib, pwd, re, stat, subprocess, sys
DB=pathlib.Path('/var/lib/pinas/shares.json')
def md4(message):
    # NT hash is MD4(UTF-16LE password). Samba uses NT hashes for SMB auth.
    import struct
    original=len(message);message+=b'\x80';message+=b'\0'*((56-len(message)%64)%64)+struct.pack('<Q',original*8)
    a,b,c,d=0x67452301,0xefcdab89,0x98badcfe,0x10325476
    def rol(v,n):return ((v<<n)|(v>>(32-n)))&0xffffffff
    for offset in range(0,len(message),64):
        x=struct.unpack('<16I',message[offset:offset+64]);aa,bb,cc,dd=a,b,c,d
        for j in range(48):
            if j<16:f=(b&c)|(~b&d);k=j;shift=[3,7,11,19][j%4];constant=0
            elif j<32:f=(b&c)|(b&d)|(c&d);k=(j%4)*4+j//4-4;shift=[3,5,9,13][j%4];constant=0x5a827999
            else:f=b^c^d;k=[0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15][j-32];shift=[3,9,11,15][j%4];constant=0x6ed9eba1
            value=rol((a+f+x[k]+constant)&0xffffffff,shift);a,b,c,d=d,value,b,c
        a=(a+aa)&0xffffffff;b=(b+bb)&0xffffffff;c=(c+cc)&0xffffffff;d=(d+dd)&0xffffffff
    return struct.pack('<4I',a,b,c,d).hex().upper()
def samba_hash(user):
    p=subprocess.run(['/usr/bin/pdbedit','-Lw',user],capture_output=True,text=True,timeout=8)
    if p.returncode:raise ValueError('Unknown NAS account')
    for line in p.stdout.splitlines():
        fields=line.split(':')
        if len(fields)>4 and fields[0]==user and re.fullmatch('[A-Fa-f0-9]{32}',fields[3]):return fields[3].upper()
    raise ValueError('NAS account has no valid Samba password')
def valid_user(user):
    if not isinstance(user,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',user):raise ValueError('Invalid user')
    person=pwd.getpwnam(user)
    if person.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):raise ValueError('Not a PiNAS NAS user')
    if samba_hash(user)=='':raise ValueError('Not a Samba user')
    return person
def shares_for(user):
    entries=json.loads(DB.read_text())
    return [s for s in entries if isinstance(s,dict) and s.get('access',{}).get(user) in ('ro','rw')]
def drop(person):
    os.initgroups(person.pw_name,person.pw_gid);os.setgid(person.pw_gid);os.setuid(person.pw_uid)
def safe_path(root,relative):
    if not isinstance(relative,str) or len(relative)>1000 or relative.startswith('/') or '\\' in relative or '\x00' in relative:raise ValueError('Invalid path')
    parts=relative.split('/') if relative else []
    if any(x in ('','.','..') or x.startswith('.pinas-upload-') for x in parts):raise ValueError('Invalid path')
    # Reject symlinks at every level, including the leaf. Never follow them.
    cur=root
    for part in parts:
        cur=cur/part
        if cur.is_symlink():raise ValueError('Symbolic links are not accessible')
    if not cur.resolve(strict=False).is_relative_to(root.resolve(strict=True)):raise ValueError('Path outside share')
    return cur
def main():
    if os.geteuid()!=0:raise ValueError('Root required')
    raw=sys.stdin.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise ValueError('Request too large')
    q=json.loads(raw);action=q.get('action');user=q.get('username');person=valid_user(user)
    if action=='authenticate':
        password=q.get('password')
        if not isinstance(password,str) or len(password)>256:raise ValueError('Invalid password')
        print('true' if hmac.compare_digest(md4(password.encode('utf-16le')),samba_hash(user)) else 'false');return
    allowed=shares_for(user)
    if action=='shares':
        print(json.dumps({'shares':[{'name':s['name'],'read_only':s['access'][user]=='ro'} for s in allowed]}));return
    share=q.get('share');s=next((x for x in allowed if x['name']==share),None)
    if s is None:raise ValueError('Share not accessible')
    # Root path derived exclusively from privileged share metadata, not browser paths.
    root=pathlib.Path(s['volume_label']) if False else None
    # Resolve mount from device, and confirm it is still the same mounted filesystem.
    device=s['volume'];p=subprocess.run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device],capture_output=True,text=True,timeout=5)
    targets=p.stdout.strip().splitlines()
    if p.returncode or len(targets)!=1:raise ValueError('Share storage is offline')
    mount=pathlib.Path(targets[0]).resolve(strict=True)
    if str(mount)=='/' or str(mount).startswith(('/etc/','/var/','/usr/','/home/','/boot/')):raise ValueError('Protected mount')
    root=mount/'PiNAS Shares'/s['name']
    if root.is_symlink() or not root.is_dir():raise ValueError('Share folder unavailable')
    relative=q.get('path','');target=safe_path(root,relative)
    writable=s['access'][user]=='rw'
    if action in ('mkdir','delete','rename','move','copy','upload','upload_start','upload_chunk','upload_finish','upload_cancel') and not writable:raise ValueError('Read-only share')
    drop(person)
    # All operations below run with the NAS user's UID/GID. Uploads are staged
    # in the destination directory, then published by an atomic rename.
    def valid_name(name):
        if not isinstance(name,str) or not name or len(name)>255 or name in ('.','..') or '/' in name or '\\' in name or '\x00' in name or name.startswith('.pinas-upload-'):raise ValueError('Invalid file name')
        return name
    def destination(relative):
        dest=safe_path(root,relative)
        if dest==root or dest.exists() or dest.is_symlink():raise ValueError('Destination already exists')
        if not dest.parent.is_dir():raise ValueError('Destination folder does not exist')
        return dest
    if action in ('rename','move','copy'):
        if target==root or not target.exists():raise ValueError('Invalid source')
        if action=='rename':
            dest=destination('/'.join(filter(None,[relative.rsplit('/',1)[0] if '/' in relative else '',valid_name(q.get('name'))])))
        else:
            dest=destination(q.get('dest',''))
        if target.is_dir() and (dest==target or target in dest.parents):raise ValueError('Cannot place folder inside itself')
        if action=='copy':
            import shutil
            if target.is_dir():
                # Reject links anywhere in the tree and cap total copy size.
                total=0
                for directory,dirs,files in os.walk(target,followlinks=False):
                    for name in dirs+files:
                        node=pathlib.Path(directory)/name
                        if node.is_symlink():raise ValueError('Symbolic links cannot be copied')
                        if node.is_file():total+=node.stat().st_size
                        if total>8*1024**3:raise ValueError('Folder copy exceeds 8 GiB safety limit')
                shutil.copytree(target,dest,symlinks=False)
            elif target.is_file():
                with target.open('rb') as src, dest.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            else:raise ValueError('Unsupported file type')
        else:
            # Same-share only; atomic rename prevents partial moves.
            if target.is_file():
                os.link(target,dest,follow_symlinks=False);target.unlink()
            else:target.rename(dest)
        print('{"ok":true}');return
    if action=='upload_start':
        name=valid_name(q.get('name'))
        if not target.is_dir():raise ValueError('Not a folder')
        destination('/'.join(filter(None,[relative,name])))
        size=q.get('size')
        if not isinstance(size,int) or size<0 or size>100*1024**3:raise ValueError('Invalid upload size')
        import secrets
        token=secrets.token_hex(20)
        staging=target/('.pinas-upload-'+token)
        fd=os.open(staging,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        meta=target/('.pinas-upload-'+token+'.json')
        fd=os.open(meta,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'name':name,'size':size,'path':relative},f)
        print(json.dumps({'token':token}));return
    if action in ('upload_chunk','upload_finish','upload_cancel'):
        token=q.get('token','')
        if not isinstance(token,str) or not re.fullmatch('[0-9a-f]{40}',token):raise ValueError('Invalid transfer token')
        stage=target/('.pinas-upload-'+token)
        meta=target/('.pinas-upload-'+token+'.json')
        if stage.is_symlink() or meta.is_symlink() or not stage.is_file() or not meta.is_file():raise ValueError('Unknown transfer')
        details=json.loads(meta.read_text());name=valid_name(details['name']);size=details['size']
        if details.get('path')!=relative:raise ValueError('Transfer location mismatch')
        if action=='upload_cancel':stage.unlink();meta.unlink();print('{"ok":true}');return
        if action=='upload_chunk':
            content=q.get('content','');offset=q.get('offset')
            if not isinstance(content,str) or len(content)>700000 or not isinstance(offset,int):raise ValueError('Invalid chunk')
            payload=base64.b64decode(content,validate=True)
            if len(payload)>512*1024 or offset!=stage.stat().st_size or offset+len(payload)>size:raise ValueError('Chunk offset or size mismatch')
            with stage.open('ab') as f:f.write(payload)
            print(json.dumps({'offset':offset+len(payload)}));return
        if stage.stat().st_size!=size:raise ValueError('Upload incomplete')
        dest=destination('/'.join(filter(None,[relative,name])))
        # Hard-link is no-clobber and atomic on the same filesystem.
        os.link(stage,dest,follow_symlinks=False);stage.unlink();meta.unlink()
        print('{"ok":true}');return
    if action=='download_chunk':
        offset=q.get('offset');size=q.get('size')
        if not isinstance(offset,int) or offset<0 or not isinstance(size,int) or size<1 or size>512*1024:raise ValueError('Invalid download range')
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode):raise ValueError('Not a regular file')
        total=target.stat().st_size
        with target.open('rb') as f:f.seek(offset);chunk=f.read(size)
        print(json.dumps({'content':base64.b64encode(chunk).decode(),'total':total}));return
    if action=='list':
        if not target.is_dir():raise ValueError('Not a folder')
        entries=[]
        for child in sorted(target.iterdir(),key=lambda x:x.name.casefold()):
            if child.is_symlink() or child.name.startswith('.pinas-upload-'):continue
            try:st=child.stat()
            except OSError:continue
            if stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode):entries.append({'name':child.name,'dir':stat.S_ISDIR(st.st_mode),'size':st.st_size})
            if len(entries)>=1000:break
        print(json.dumps({'entries':entries}));return
    if action=='mkdir':
        name=q.get('name','');dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..'):raise ValueError('Invalid folder name')
        dest.mkdir(mode=0o770);print('{"ok":true}');return
    if action=='delete':
        if target==root:raise ValueError('Cannot delete share root')
        if target.is_dir():target.rmdir()
        elif target.is_file():target.unlink()
        else:raise ValueError('Not a regular file or empty folder')
        print('{"ok":true}');return
    if action=='download':
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode) or target.stat().st_size>3*1024*1024:raise ValueError('Only files up to 3 MB supported in this test build')
        with target.open('rb') as f:content=base64.b64encode(f.read()).decode()
        print(json.dumps({'content':content}));return
    if action=='upload':
        name=q.get('name','');content=q.get('content','')
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..') or not isinstance(content,str) or len(content)>4*1024*1024+16:raise ValueError('Invalid upload')
        dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not target.is_dir():raise ValueError('Not a directory')
        payload=base64.b64decode(content,validate=True)
        if len(payload)>3*1024*1024:raise ValueError('Upload exceeds 3 MB')
        fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o660)
        with os.fdopen(fd,'wb') as f:f.write(payload)
        print('{"ok":true}');return
    raise ValueError('Unsupported action')
if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
"""

APT_INDEX_HELPER = r"""#!/usr/bin/env python3
import os,subprocess,sys
from pathlib import Path
ALLOWED={'off':None,'daily':'*-*-* 01:00:00','weekly':'Fri *-*-* 01:00:00','monthly':'*-*-28 01:00:00'}
def run(cmd,timeout=30):
    p=subprocess.run(cmd,timeout=timeout,check=False)
    if p.returncode:sys.exit(p.returncode)
def main():
    if os.geteuid()!=0:sys.exit('Root access required')
    args=sys.argv[1:]
    if len(args)==2 and args[0]=='schedule' and args[1] in ALLOWED:
        schedule=args[1];calendar=ALLOWED[schedule]
        timer=Path('/etc/systemd/system/pinas-auto-updates.timer')
        if calendar:
            timer.write_text('[Unit]\nDescription=PiNAS automatic OS updates\n[Timer]\nOnCalendar='+calendar+'\nPersistent=true\nUnit=pinas-auto-updates.service\n[Install]\nWantedBy=timers.target\n')
        run(['systemctl','daemon-reload'])
        if calendar:
            run(['systemctl','enable','--now','pinas-auto-updates.timer'])
            run(['systemctl','restart','pinas-auto-updates.timer'])
        else:
            run(['systemctl','disable','--now','pinas-auto-updates.timer']) if timer.exists() else None
            timer.unlink(missing_ok=True)
            run(['systemctl','daemon-reload'])
        marker=Path('/var/lib/pinas/update-schedule');marker.write_text(schedule+'\n');os.chmod(marker,0o644)
        return
    if args==['automatic']:
        # Only the systemd oneshot invokes this command, not the web service account.
        run(['/usr/bin/apt-get','update'],210)
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
        return
    if args==['upgrade']:
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
    elif args==['refresh']:
        run(['/usr/bin/apt-get','update'],210)
    else:sys.exit('Unsupported operation')
if __name__=='__main__':main()
"""

NAS_STORAGE_HELPER='#!/usr/bin/env python3\n"""PiNAS RC13 restricted, non-destructive storage adoption helper."""\nimport json,os,pathlib,re,subprocess,sys,uuid\nfrom pathlib import Path\n\ndef run(*args,timeout=15):\n    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)\n    if p.returncode:raise ValueError((p.stderr or \'Storage command failed\').strip()[-500:])\n    return p.stdout.strip()\n\ndef main():\n    if os.geteuid()!=0 or sys.argv[1:]!=[\'adopt\']:raise ValueError(\'Unsupported storage operation\')\n    data=json.loads(sys.stdin.read(4096));device=data.get(\'device\')\n    if not isinstance(device,str) or not re.fullmatch(r\'/dev/[A-Za-z0-9_./-]{1,90}\',device) or \'..\' in device:raise ValueError(\'Invalid device\')\n    path=Path(device)\n    if not path.is_block_device():raise ValueError(\'Device is not a block device\')\n    # The privileged helper independently identifies eligible physical disks.\n    roots=json.loads(run(\'lsblk\',\'-J\',\'-b\',\'-o\',\'NAME,PATH,TYPE,FSTYPE,UUID,MOUNTPOINTS,RO,PKNAME\')).get(\'blockdevices\',[])\n    bypath={};byname={};parents={}\n    def walk(node,parent=None):\n        name=node.get(\'name\');bypath[node.get(\'path\')]=node;byname[name]=node\n        if parent:parents[name]=parent\n        for child in node.get(\'children\') or []:walk(child,name)\n    for root in roots:walk(root)\n    node=bypath.get(str(path.resolve())) or bypath.get(device)\n    if not node or node.get(\'type\') not in (\'part\',\'disk\') or node.get(\'ro\'):raise ValueError(\'Not an eligible writable disk or partition\')\n    def root_for(n):\n        seen=set()\n        while n.get(\'name\') in parents:\n            if n[\'name\'] in seen:raise ValueError(\'Invalid device topology\')\n            seen.add(n[\'name\']);n=byname[parents[n[\'name\']]]\n        return n\n    disk=root_for(node)\n    if disk.get(\'type\')!=\'disk\' or disk.get(\'ro\') or str(disk.get(\'name\',\'\')).startswith((\'loop\',\'zram\',\'ram\',\'nbd\',\'sr\',\'fd\')):raise ValueError(\'Unsupported backing device\')\n    # Reject any physical disk carrying the root or boot filesystems.\n    protected={\'/\',\'/boot\',\'/boot/firmware\',\'/boot/efi\'}\n    def contains_system(n):\n        if any(m in protected for m in (n.get(\'mountpoints\') or []) if m):return True\n        return any(contains_system(c) for c in n.get(\'children\') or [])\n    if contains_system(disk):raise ValueError(\'Operating system storage is protected\')\n    for mount in protected:\n        src=run(\'findmnt\',\'-n\',\'-o\',\'SOURCE\',\'--target\',mount).split(\'[\',1)[0]\n        if src and src in bypath and root_for(bypath[src]).get(\'name\')==disk.get(\'name\'):\n            raise ValueError(\'Operating system storage is protected\')\n    fs=run(\'blkid\',\'-s\',\'TYPE\',\'-o\',\'value\',device)\n    uid=run(\'blkid\',\'-s\',\'UUID\',\'-o\',\'value\',device)\n    if fs not in (\'ext4\',\'xfs\',\'btrfs\') or not re.fullmatch(r\'[A-Za-z0-9-]{8,64}\',uid):raise ValueError(\'Supported filesystem and UUID required\')\n    # Reject RAID/LVM/crypto members and nested volume layouts.\n    if node.get(\'type\')==\'disk\' and node.get(\'children\'):raise ValueError(\'Choose a filesystem partition, not its parent disk\')\n    if node.get(\'children\'):raise ValueError(\'Complex volume layout not supported\')\n    mountpoints=[m for m in node.get(\'mountpoints\') or [] if m]\n    if len(mountpoints)>1:raise ValueError(\'Multiple mountpoints require manual review\')\n    if mountpoints and not str(mountpoints[0]).startswith(\'/mnt/pinas/\'):\n        raise ValueError(\'Filesystem is already mounted elsewhere; manage it manually to avoid disrupting applications\')\n    target=Path(\'/mnt/pinas\')/uid\n    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir())) and str(target) not in mountpoints):raise ValueError(\'Mount destination is not empty\')\n    fstab=Path(\'/etc/fstab\');original=fstab.read_text();entries=[line.split() for line in original.splitlines() if line.strip() and not line.lstrip().startswith(\'#\')]\n    for e in entries:\n        if len(e)>=2 and (e[0] in (device,\'UUID=\'+uid,\'/dev/disk/by-uuid/\'+uid) or e[1]==str(target)):\n            if e[0]==\'UUID=\'+uid and e[1]==str(target):\n                if str(target) not in mountpoints:run(\'mount\',str(target),timeout=25)\n                print(json.dumps({\'ok\':True,\'mount\':str(target),\'existing\':True}));return\n            raise ValueError(\'Existing fstab configuration requires manual review\')\n    target.parent.mkdir(parents=True,exist_ok=True)\n    target.mkdir(mode=0o755,exist_ok=True)\n    options=\'defaults,nofail,noatime,x-systemd.device-timeout=10s\'\n    entry=f\'UUID={uid} {target} {fs} {options} 0 {2 if fs=="ext4" else 0} # PiNAS managed\\\\n\'\n    entry=entry.replace(\'\\\\n\',\'\\n\')\n    backup=fstab.with_name(\'fstab.pinas-\'+uuid.uuid4().hex[:12]+\'.bak\')\n    backup.write_text(original);os.chmod(backup,0o600)\n    temp=fstab.with_name(\'.fstab.pinas-\'+uuid.uuid4().hex)\n    try:\n        temp.write_text(original.rstrip(\'\\n\')+\'\\n\'+entry);os.chmod(temp,0o644)\n        os.replace(temp,fstab)\n        run(\'systemctl\',\'daemon-reload\',timeout=15)\n        run(\'mount\',str(target),timeout=25)\n        actual=run(\'findmnt\',\'-n\',\'-o\',\'UUID\',\'--target\',str(target))\n        if actual!=uid:raise ValueError(\'Mounted filesystem UUID verification failed\')\n    except Exception:\n        fstab.write_text(original)\n        try:run(\'systemctl\',\'daemon-reload\')\n        except Exception:pass\n        raise\n    print(json.dumps({\'ok\':True,\'mount\':str(target)}))\nif __name__==\'__main__\':\n    try:main()\n    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)\n'

SMART_HEALTH_HELPER = """#!/usr/bin/env python3
import json,os,shutil,subprocess,sys
from pathlib import Path
def main():
    if os.geteuid()!=0 or len(sys.argv)!=1:
        raise ValueError('Unsupported operation')
    smartctl=shutil.which('smartctl')
    if not smartctl:
        print(json.dumps({'installed':False,'drives':[]}));return
    p=subprocess.run(['lsblk','-J','-b','-o','NAME,PATH,TYPE,MODEL,TRAN'],capture_output=True,text=True,timeout=8,check=True)
    drives=[]
    for disk in json.loads(p.stdout).get('blockdevices',[]):
        if disk.get('type')!='disk':continue
        device=disk.get('path','')
        if not isinstance(device,str) or not device.startswith('/dev/') or not Path(device).is_block_device():continue
        if disk.get('name','').startswith(('loop','zram','ram','nbd','sr','fd')):continue
        entry={'device':device,'model':disk.get('model') or disk.get('name'),'status':'Unavailable','temperature':None}
        try:
            result=subprocess.run([smartctl,'-j','-H','-A',device],capture_output=True,text=True,timeout=12)
            data=json.loads(result.stdout)
            health=data.get('smart_status',{}).get('passed')
            if health is True:entry['status']='Healthy'
            elif health is False:entry['status']='Warning'
            temp=data.get('temperature',{}).get('current')
            if isinstance(temp,(int,float)) and -20<=temp<=120:entry['temperature']=temp
            if data.get('smart_support',{}).get('available') is False:entry['status']='Unsupported'
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        drives.append(entry)
    print(json.dumps({'installed':True,'drives':drives}))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

def install(args):
    if sys.platform!='linux' or os.geteuid()!=0:sys.exit('Install requires Linux and sudo/root.')
    if not Path('/etc/os-release').exists():sys.exit('Unsupported OS')
    osinfo=read('/etc/os-release')
    if 'debian' not in osinfo.lower() and 'raspbian' not in osinfo.lower():sys.exit('Requires Raspberry Pi OS / Debian family')
    if not args.skip_packages:
        print('Installing NAS dependencies (requires network and may take time)...',flush=True)
        subprocess.run(['apt-get','update'],check=True)
        subprocess.run(['apt-get','install','-y','samba','xfsprogs','btrfs-progs','mdadm','parted','util-linux','e2fsprogs','avahi-daemon','acl','openssl'],check=True)
    target=Path('/opt/pinas');target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(__file__).resolve(),target/'pinas.py');os.chmod(target/'pinas.py',0o755)
    if subprocess.run(['id','-u','pinas'],capture_output=True).returncode!=0:
        subprocess.run(['useradd','--system','--home-dir','/var/lib/pinas','--shell','/usr/sbin/nologin','pinas'],check=True)
    DATA.mkdir(parents=True,exist_ok=True);os.chmod(DATA,0o700)
    subprocess.run(['chown','pinas:pinas',str(DATA)],check=True)
    helper=Path('/usr/local/libexec/pinas-apply-hostname')
    helper.parent.mkdir(parents=True,exist_ok=True)
    helper.write_text(HOSTNAME_HELPER)
    os.chmod(helper,0o755)
    unit='''[Unit]\nDescription=Apply validated PiNAS device hostname\nAfter=systemd-hostnamed.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /usr/local/libexec/pinas-apply-hostname\nNoNewPrivileges=true\nProtectHome=true\nPrivateTmp=true\n'''
    Path('/etc/systemd/system/pinas-hostname.service').write_text(unit)
    path_unit='''[Unit]\nDescription=Apply PiNAS hostname when configuration changes\n[Path]\nPathChanged=/var/lib/pinas/config.json\nUnit=pinas-hostname.service\n[Install]\nWantedBy=multi-user.target\n'''
    Path('/etc/systemd/system/pinas-hostname.path').write_text(path_unit)
    user_helper=Path('/usr/local/libexec/pinas-nas-user')
    user_helper.write_text(NAS_USER_HELPER)
    os.chown(user_helper,0,0);os.chmod(user_helper,0o700)
    sudoers=Path('/etc/sudoers.d/pinas-nas-user')
    sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-user create *, /usr/local/libexec/pinas-nas-user password *, /usr/local/libexec/pinas-nas-user list\n')
    os.chown(sudoers,0,0);os.chmod(sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(sudoers)],capture_output=True).returncode:
        sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS sudoers configuration')
    share_helper=Path('/usr/local/libexec/pinas-nas-share')
    share_helper.write_text(NAS_SHARE_HELPER)
    os.chown(share_helper,0,0);os.chmod(share_helper,0o700)
    share_sudoers=Path('/etc/sudoers.d/pinas-nas-share')
    share_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-share list, /usr/local/libexec/pinas-nas-share create\n')
    os.chown(share_sudoers,0,0);os.chmod(share_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(share_sudoers)],capture_output=True).returncode:
        share_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS share sudoers configuration')
    files_helper=Path('/usr/local/libexec/pinas-nas-files')
    files_helper.write_text(NAS_FILES_HELPER)
    os.chown(files_helper,0,0);os.chmod(files_helper,0o700)
    files_sudoers=Path('/etc/sudoers.d/pinas-nas-files')
    files_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-files\n')
    os.chown(files_sudoers,0,0);os.chmod(files_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(files_sudoers)],capture_output=True).returncode:
        files_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS file helper sudoers configuration')
    storage_helper=Path('/usr/local/libexec/pinas-nas-storage')
    storage_helper.write_text(NAS_STORAGE_HELPER)
    os.chown(storage_helper,0,0);os.chmod(storage_helper,0o700)
    storage_sudoers=Path('/etc/sudoers.d/pinas-nas-storage')
    storage_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-storage adopt\n')
    os.chown(storage_sudoers,0,0);os.chmod(storage_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(storage_sudoers)],capture_output=True).returncode:
        storage_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS storage sudoers configuration')
    smart_helper=Path('/usr/local/libexec/pinas-smart-health')
    smart_helper.write_text(SMART_HEALTH_HELPER)
    os.chown(smart_helper,0,0);os.chmod(smart_helper,0o700)
    smart_sudoers=Path('/etc/sudoers.d/pinas-smart-health')
    smart_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-smart-health\n')
    os.chown(smart_sudoers,0,0);os.chmod(smart_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(smart_sudoers)],capture_output=True).returncode:
        smart_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS SMART sudoers configuration')
    apt_helper=Path('/usr/local/libexec/pinas-apt-index')
    apt_helper.write_text(APT_INDEX_HELPER)
    os.chown(apt_helper,0,0);os.chmod(apt_helper,0o700)
    apt_sudoers=Path('/etc/sudoers.d/pinas-apt-index')
    apt_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-apt-index refresh, /usr/local/libexec/pinas-apt-index upgrade, /usr/local/libexec/pinas-apt-index schedule off, /usr/local/libexec/pinas-apt-index schedule daily, /usr/local/libexec/pinas-apt-index schedule weekly, /usr/local/libexec/pinas-apt-index schedule monthly\n')
    os.chown(apt_sudoers,0,0);os.chmod(apt_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(apt_sudoers)],capture_output=True).returncode:
        apt_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS APT sudoers configuration')
    auto_service=Path('/etc/systemd/system/pinas-auto-updates.service')
    auto_service.write_text('[Unit]\nDescription=PiNAS scheduled OS updates\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=oneshot\nExecStart=/usr/local/libexec/pinas-apt-index automatic\nEnvironment=DEBIAN_FRONTEND=noninteractive\n')
    os.chown(auto_service,0,0);os.chmod(auto_service,0o644)
    # Existing schedule is preserved when upgrading PiNAS.
    # Generate a persistent per-install certificate; never replace it on upgrades.
    if not TLS_CERT.exists() or not TLS_KEY.exists():
        if TLS_CERT.exists() or TLS_KEY.exists():sys.exit('Incomplete TLS certificate pair; resolve manually before installing')
        if not shutil.which('openssl'):sys.exit('OpenSSL required for initial TLS certificate generation')
        hostname=load().get('hostname','pinas')
        if not valid_hostname(hostname):hostname='pinas'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','825',
            '-keyout',str(TLS_KEY),'-out',str(TLS_CERT),'-subj',f'/CN={hostname}.local',
            '-addext',f'subjectAltName=DNS:{hostname}.local,DNS:localhost,IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL)
    for f,mode in ((TLS_CERT,0o644),(TLS_KEY,0o600)):
        os.chown(f,0 if f==TLS_CERT else __import__('pwd').getpwnam('pinas').pw_uid,0 if f==TLS_CERT else __import__('grp').getgrnam('pinas').gr_gid)
        os.chmod(f,mode)
    bind_host='0.0.0.0' if args.lan else '127.0.0.1' 
    # TEMPORARY RC9.2: sudo inherits the service mount namespace. A root helper
    # cannot write /etc/passwd, /etc/group or Samba state with ProtectSystem=strict.
    # Replace sudo delegation with an independently sandboxed privileged service.
    service='''[Unit]\nDescription=PiNAS prototype web dashboard\nAfter=network.target\n[Service]\nType=simple\nUser=pinas\nGroup=pinas\nExecStart=/usr/bin/python3 /opt/pinas/pinas.py --serve --tls --host %s --port %d\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=false\nProtectSystem=false\nReadWritePaths=/var/lib/pinas\nPrivateTmp=true\n[Install]\nWantedBy=multi-user.target\n'''%(bind_host,args.port)
    Path('/etc/systemd/system/pinas.service').write_text(service)
    subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','enable','--now','pinas-hostname.path'],check=True);subprocess.run(['systemctl','start','pinas-hostname.service'],check=True);subprocess.run(['systemctl','enable','pinas.service'],check=True);subprocess.run(['systemctl','restart','pinas.service'],check=True)
    print(f'PiNAS installed. For localhost access: https://127.0.0.1:{args.port} (self-signed certificate)')
    if args.lan:print(f'LAN TLS MODE: open https://<PI-IP>:{args.port}. Certificate is self-signed; use the .local hostname for name matching. Do not expose this port to the internet.')
    else:print('Localhost-only mode; re-run installer with --lan to enable direct LAN access for testing.')

def main():
    ap=argparse.ArgumentParser(description='PiNAS Raspberry Pi NAS prototype')
    ap.add_argument('--lan',action='store_true',help='Bind HTTPS server to LAN interfaces');ap.add_argument('--install',action='store_true');ap.add_argument('--serve',action='store_true');ap.add_argument('--tls',action='store_true');ap.add_argument('--skip-packages',action='store_true');ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=8765)
    a=ap.parse_args()
    if a.install:install(a);return
    if a.serve:
        if a.host not in ('127.0.0.1','::1','0.0.0.0'):sys.exit('Unsupported bind address.')
        if a.host=='0.0.0.0' and not a.tls:sys.exit('LAN listening requires HTTPS (--tls)')
        server=ThreadingHTTPServer((a.host,a.port),Handler)
        if a.tls:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(TLS_CERT),str(TLS_KEY))
            server.socket=context.wrap_socket(server.socket,server_side=True)
        print('PiNAS running on %s://%s:%s'%('https' if a.tls else 'http',a.host,a.port))
        threading.Thread(target=cpu_sampler,daemon=True).start();server.serve_forever();return
    ap.print_help()
if __name__=='__main__':main(),'ipc
            name=data.get('name');password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):
                self.json({'error':'Invalid share name.'},400);return
            if not isinstance(password,str) or not verify(password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not any(isinstance(item,dict) and item.get('name')==name for item in nas_share_list()):
                self.json({'error':'Only PiNAS-managed shares can be removed.'},404);return
            try:delete_nas_share(name)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name,'files_preserved':True});return
        if path=='/api/nas-shares':
            name=data.get('name');volume=data.get('volume');access=data.get('access');admin_password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):
                self.json({'error':'Choose a share name of 1–32 letters, digits, spaces, underscores or hyphens.'},400);return
            if not isinstance(volume,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',volume) or '..' in volume:
                self.json({'error':'Invalid storage selection.'},400);return
            if not isinstance(access,dict) or not access or len(access)>64 or any(not isinstance(k,str) or v not in ('ro','rw') for k,v in access.items()):
                self.json({'error':'Assign at least one user Read Only or Read & Write access.'},400);return
            if not isinstance(admin_password,str) or not verify(admin_password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not storage_is_ready():self.json({'error':'A mounted, persistent data filesystem is required.'},409);return
            valid_users={u['name'] for u in nas_user_list()}
            if not set(access).issubset(valid_users):self.json({'error':'One or more users are not valid Samba accounts.'},409);return
            if any(name.casefold()==s.casefold() for s in discover().get('shares',[])):
                self.json({'error':'A share with this name already exists.'},409);return
            try:create_nas_share(name,volume,access)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name});return
        if path=='/api/logout':SESSIONS.pop(token,None);self.json({'ok':True},cookie='pinas_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'+('; Secure' if isinstance(self.connection,ssl.SSLSocket) else ''));return
        if path=='/api/settings':
            theme,accent,font=data.get('theme'),data.get('accent'),data.get('font')
            interval,history=data.get('cpu_interval',cfg.get('cpu_interval',5)),data.get('cpu_history',cfg.get('cpu_history',10))
            session_timeout=data.get('session_timeout',cfg.get('session_timeout',5))
            if theme not in ('light','dark','dark-cb','light-cb') or not isinstance(accent,str) or len(accent)!=7 or accent[0]!='#' or any(c not in '0123456789abcdefABCDEF' for c in accent[1:]) or type(font)!=int or font not in (10,12,14,16) or type(interval)!=int or interval not in (2,5,10) or type(history)!=int or history not in (10,15,30,60) or type(session_timeout)!=int or session_timeout not in (5,10,15,30,60):self.json({'error':'Invalid appearance settings'},400);return
            cfg.update(theme=theme,accent=accent,font=font,cpu_interval=interval,cpu_history=history,session_timeout=session_timeout)
        elif path=='/api/background':
            image=data.get('image')
            if not isinstance(image,str) or len(image)>2_900_000:self.json({'error':'Image too large'},400);return
            if image:
                try:
                    meta,b64=image.split(',',1);mime=meta[5:].split(';',1)[0]
                    if mime not in ('image/jpeg','image/png','image/webp'):raise ValueError()
                    decoded=base64.b64decode(b64,validate=True)
                    if len(decoded)>2*1024*1024:raise ValueError()
                    if not ((mime=='image/jpeg' and decoded.startswith(b'\xff\xd8\xff')) or (mime=='image/png' and decoded.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/webp' and decoded.startswith(b'RIFF') and decoded[8:12]==b'WEBP')):raise ValueError()
                except (ValueError,IndexError):self.json({'error':'Invalid image'},400);return
            cfg['login_background']=image
        save(cfg);self.json({'settings':dict({k:cfg.get(k) for k in ('theme','accent','font','cpu_interval','cpu_history','session_timeout')},has_background=bool(cfg.get('login_background')))} )

HOSTNAME_HELPER = r"""#!/usr/bin/env python3
import json, re, subprocess
from pathlib import Path
try:
    path=Path('/var/lib/pinas/config.json')
    if not path.exists():raise SystemExit(0)
    cfg=json.loads(path.read_text())
    hostname=cfg.get('hostname','')
    if not hostname:raise SystemExit(0)
    if not isinstance(hostname,str) or not 1<=len(hostname)<=63 or not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*',hostname):
        raise ValueError('Invalid hostname')
    current=subprocess.run(['hostname','-s'],capture_output=True,text=True,check=True).stdout.strip()
    if current!=hostname:
        subprocess.run(['/usr/bin/hostnamectl','set-hostname',hostname],check=True,timeout=15)
except (OSError,ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
    raise SystemExit('PiNAS hostname not applied: '+str(exc))
"""

NAS_USER_HELPER = r"""#!/usr/bin/env python3
# Privileged helper. No arbitrary command execution; narrowly scoped account actions.
import grp, json, os, pwd, re, subprocess, sys

def run(argv, **kwargs):
    return subprocess.run(argv, check=True, timeout=20, **kwargs)

def samba_users():
    p=run(['/usr/bin/pdbedit','-L'],capture_output=True,text=True)
    result=[]
    for line in p.stdout.splitlines():
        fields=line.split(':',2)
        if len(fields)>=2 and re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',fields[0]):
            result.append({'name':fields[0],'uid':fields[1]})
    return sorted(result,key=lambda x:x['name'])

if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit(2)
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(samba_users()))
        raise SystemExit(0)
    if len(sys.argv)!=3 or sys.argv[1] not in ('create','password'):raise SystemExit(2)
    name=sys.argv[2]
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',name) or name in ('pinas','root','admin','nobody'):raise SystemExit(2)
    password=sys.stdin.readline(258).rstrip('\n')
    if not 12<=len(password)<=256:raise SystemExit(2)
    if sys.argv[1]=='password':
        group=grp.getgrnam('pinas-nas')
        existing=pwd.getpwnam(name)
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin') or not any(u['name']==name for u in samba_users()):
            raise SystemExit('Not a managed PiNAS Samba user')
        run(['/usr/bin/smbpasswd','-s',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        raise SystemExit(0)
    try:
        group=grp.getgrnam('pinas-nas')
    except KeyError:
        run(['/usr/sbin/groupadd','pinas-nas'])
        group=grp.getgrnam('pinas-nas')
    created=False
    try:
        existing=pwd.getpwnam(name)
    except KeyError:
        existing=None
    if existing:
        # Repair only a partial PiNAS account from a previous failed attempt.
        # Never repurpose unrelated Linux accounts.
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):
            raise SystemExit('Linux account already exists and is not a PiNAS NAS account; choose another username')
        if any(u['name']==name for u in samba_users()):
            raise SystemExit('Samba account already exists; refresh the Users page')
    else:
        run(['/usr/sbin/useradd','--no-create-home','--shell','/usr/sbin/nologin','--gid','pinas-nas',name])
        created=True
    try:
        run(['/usr/bin/smbpasswd','-s','-a',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        run(['/usr/bin/smbpasswd','-e',name],capture_output=True)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        if created:subprocess.run(['/usr/sbin/userdel',name],check=False,timeout=10)
        raise SystemExit('Samba account creation failed: '+str(exc))
"""

NAS_SHARE_HELPER = r"""#!/usr/bin/env python3
# Root-only share broker. Strict input validation and independent mount checks.
import json, os, pathlib, pwd, re, subprocess, sys, tempfile

DB=pathlib.Path('/var/lib/pinas/shares.json')
CONF=pathlib.Path('/etc/samba/pinas-shares.conf')
SMB=pathlib.Path('/etc/samba/smb.conf')

def run(cmd, **kw):
    return subprocess.run(cmd,check=True,timeout=15,capture_output=True,text=True,**kw)

def read_db():
    try:
        value=json.loads(DB.read_text())
        return value if isinstance(value,list) else []
    except (OSError,ValueError):return []

def atomic(path,content,mode=0o600):
    fd,name=tempfile.mkstemp(prefix='.pinas-',dir=str(path.parent))
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'w') as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def check_volume(device):
    if not isinstance(device,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',device) or '..' in device:raise ValueError('Invalid device')
    # Device must be a block device with an approved filesystem.
    p=pathlib.Path(device)
    if not p.is_block_device():raise ValueError('Selected storage is not a block device')
    fs=run(['/usr/bin/lsblk','-n','-o','FSTYPE',device]).stdout.strip().splitlines()
    if not fs or fs[0].strip().lower() not in ('ext4','xfs','btrfs'):raise ValueError('Unsupported filesystem')
    target=run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device]).stdout.strip().splitlines()
    if len(target)!=1:raise ValueError('Disk must have one unambiguous active mount')
    mount=pathlib.Path(target[0]).resolve(strict=True)
    if str(mount) in ('/','/boot','/boot/firmware') or any(str(mount).startswith(prefix) for prefix in ('/etc/','/var/','/usr/','/home/','/opt/','/root/','/proc/','/sys/','/run/')):
        raise ValueError('System storage cannot host NAS shares')
    if not mount.is_dir() or mount.is_symlink():raise ValueError('Invalid mount directory')
    # Confirm mounted persistently via UUID, path or LABEL; do not trust browser data.
    uuid=run(['/usr/sbin/blkid','-s','UUID','-o','value',device]).stdout.strip()
    entries=[line.split() for line in pathlib.Path('/etc/fstab').read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not any(len(e)>=2 and e[1]==str(mount) and e[0] in (device,'UUID='+uuid,'/dev/disk/by-uuid/'+uuid) for e in entries):
        raise ValueError('Disk is not persistently configured in fstab')
    # Reject root device even when mounted at a second location.
    rootdev=run(['/usr/bin/findmnt','-n','-o','SOURCE','/']).stdout.strip()
    if rootdev.startswith('/dev/'):
        rootparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',rootdev]).stdout.split())
        selectedparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',device]).stdout.split())
        if rootparents & selectedparents:raise ValueError('Operating system disk is protected')
    return mount

def main():
    if os.geteuid()!=0:raise ValueError('Root helper required')
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(read_db()));return
    if len(sys.argv)==2 and sys.argv[1]=='delete':
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('Request too large')
        request=json.loads(raw);name=request.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):raise ValueError('Invalid share name')
        current=read_db()
        matches=[item for item in current if isinstance(item,dict) and item.get('name')==name]
        if len(matches)!=1:raise ValueError('Share is not managed by PiNAS')
        oldconf=CONF.read_text()
        # Match only a complete, exact managed Samba section; never touch unrelated shares.
        section=re.compile(r'(?m)^\['+re.escape(name)+r'\][ \t]*\n(?:(?!\[).*(?:\n|$))*')
        found=list(section.finditer(oldconf))
        if len(found)!=1:raise ValueError('Managed Samba share section missing or ambiguous')
        updated=oldconf[:found[0].start()]+oldconf[found[0].end():]
        olddb=DB.read_text()
        try:
            atomic(CONF,updated,0o644)
            run(['/usr/bin/testparm','-s'])
            run(['/usr/bin/systemctl','reload','smbd'])
            atomic(DB,json.dumps([item for item in current if not (isinstance(item,dict) and item.get('name')==name)],indent=2),0o600)
        except Exception:
            atomic(CONF,oldconf,0o644)
            atomic(DB,olddb,0o600)
            try:run(['/usr/bin/systemctl','reload','smbd'])
            except Exception:pass
            raise
        # Deliberately leave the share directory, ACLs and files untouched.
        print(json.dumps({'ok':True,'files_preserved':True}));return
    if len(sys.argv)!=2 or sys.argv[1]!='create':raise ValueError('Unsupported action')
    raw=sys.stdin.read(8193)
    if len(raw)>8192:raise ValueError('Request too large')
    request=json.loads(raw)
    name=request.get('name');access=request.get('access');device=request.get('volume')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):raise ValueError('Invalid share name')
    if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):raise ValueError('Invalid access policy')
    # Verify users exist in Samba and Linux before creating any directory.
    samba={line.split(':',1)[0] for line in run(['/usr/bin/pdbedit','-L']).stdout.splitlines()}
    for user in access:
        if user not in samba:raise ValueError('Samba account not found: '+user)
        pwd.getpwnam(user)
    mount=check_volume(device)
    current=read_db()
    if any(item.get('name','').casefold()==name.casefold() for item in current):raise ValueError('Share already exists')
    # Samba's own configuration may include external shares; reject collisions.
    existing=run(['/usr/bin/testparm','-s']).stdout
    if any(line.strip().casefold()=='['+name.casefold()+']' for line in existing.splitlines()):raise ValueError('Share name already used by Samba')
    # No preexisting folder is ever adopted or modified by this operation.
    root=mount/'PiNAS Shares'
    if root.is_symlink():raise ValueError('Unsafe share root')
    root.mkdir(mode=0o711,exist_ok=True)
    if root.stat().st_uid!=0 or (root.stat().st_mode & 0o022):raise ValueError('Share root must be root-owned and not group/world writable')
    folder=root/name
    if folder.exists() or folder.is_symlink():raise ValueError('Folder already exists; choose a different name')
    if not pathlib.Path('/usr/bin/setfacl').exists():raise ValueError('POSIX ACL tools are required (install acl)')
    # Validate smb.conf can be managed before changing filesystem.
    original=SMB.read_text()
    include='   include = /etc/samba/pinas-shares.conf'
    if include not in original:
        if not re.search(r'(?im)^\s*\[global\]\s*$',original):raise ValueError('Samba [global] section missing')
        amended=re.sub(r'(?im)^(\s*\[global\]\s*)$',r'\1\n'+include,original,count=1)
    else:amended=original
    # Explicit per-user access; default deny for other NAS accounts.
    ro=[u for u,p in access.items() if p=='ro'];rw=[u for u,p in access.items() if p=='rw']
    stanza='\n['+name+']\n   path = '+str(folder)+'\n   browseable = yes\n   guest ok = no\n   read only = yes\n   valid users = '+', '.join(access)+'\n'
    if rw:stanza+='   write list = '+', '.join(rw)+'\n'
    stanza+='   create mask = 0660\n   directory mask = 0770\n   follow symlinks = no\n   wide links = no\n'
    oldconf=CONF.read_text() if CONF.exists() else ''
    if '['+name+']' in oldconf:raise ValueError('Duplicate managed share')
    folder.mkdir(mode=0o700)
    try:
        # Root-owned folder; Samba creates files as authenticated Unix users.
        os.chown(folder,0,0)
        os.chmod(folder,0o700)
        acl=['u::rwx','g::---','o::---','m::rwx']+[f'u:{u}:'+('rwx' if p=='rw' else 'r-x') for u,p in access.items()]
        default=['d:'+entry for entry in acl]
        run(['/usr/bin/setfacl','-m',','.join(acl+default),str(folder)])
        if amended!=original:atomic(SMB,amended,0o644)
        atomic(CONF,oldconf+stanza,0o644)
        run(['/usr/bin/testparm','-s'])
        run(['/usr/bin/systemctl','reload','smbd'])
        current.append({'name':name,'volume_label':mount.name,'volume':device,'access':access})
        atomic(DB,json.dumps(current,indent=2),0o600)
    except Exception:
        atomic(CONF,oldconf,0o644)
        if amended!=original:atomic(SMB,original,0o644)
        try:run(['/usr/bin/systemctl','reload','smbd'])
        except Exception:pass
        try:folder.rmdir()
        except OSError:pass
        raise
    print(json.dumps({'ok':True,'name':name}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

NAS_FILES_HELPER = r"""#!/usr/bin/env python3
# Privileged, narrow file broker. Authentication against Samba passdb; filesystem
# operations executed as the NAS user's actual UID/GID and supplementary groups.
import base64, hashlib, hmac, json, os, pathlib, pwd, re, stat, subprocess, sys
DB=pathlib.Path('/var/lib/pinas/shares.json')
def md4(message):
    # NT hash is MD4(UTF-16LE password). Samba uses NT hashes for SMB auth.
    import struct
    original=len(message);message+=b'\x80';message+=b'\0'*((56-len(message)%64)%64)+struct.pack('<Q',original*8)
    a,b,c,d=0x67452301,0xefcdab89,0x98badcfe,0x10325476
    def rol(v,n):return ((v<<n)|(v>>(32-n)))&0xffffffff
    for offset in range(0,len(message),64):
        x=struct.unpack('<16I',message[offset:offset+64]);aa,bb,cc,dd=a,b,c,d
        for j in range(48):
            if j<16:f=(b&c)|(~b&d);k=j;shift=[3,7,11,19][j%4];constant=0
            elif j<32:f=(b&c)|(b&d)|(c&d);k=(j%4)*4+j//4-4;shift=[3,5,9,13][j%4];constant=0x5a827999
            else:f=b^c^d;k=[0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15][j-32];shift=[3,9,11,15][j%4];constant=0x6ed9eba1
            value=rol((a+f+x[k]+constant)&0xffffffff,shift);a,b,c,d=d,value,b,c
        a=(a+aa)&0xffffffff;b=(b+bb)&0xffffffff;c=(c+cc)&0xffffffff;d=(d+dd)&0xffffffff
    return struct.pack('<4I',a,b,c,d).hex().upper()
def samba_hash(user):
    p=subprocess.run(['/usr/bin/pdbedit','-Lw',user],capture_output=True,text=True,timeout=8)
    if p.returncode:raise ValueError('Unknown NAS account')
    for line in p.stdout.splitlines():
        fields=line.split(':')
        if len(fields)>4 and fields[0]==user and re.fullmatch('[A-Fa-f0-9]{32}',fields[3]):return fields[3].upper()
    raise ValueError('NAS account has no valid Samba password')
def valid_user(user):
    if not isinstance(user,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',user):raise ValueError('Invalid user')
    person=pwd.getpwnam(user)
    if person.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):raise ValueError('Not a PiNAS NAS user')
    if samba_hash(user)=='':raise ValueError('Not a Samba user')
    return person
def shares_for(user):
    entries=json.loads(DB.read_text())
    return [s for s in entries if isinstance(s,dict) and s.get('access',{}).get(user) in ('ro','rw')]
def drop(person):
    os.initgroups(person.pw_name,person.pw_gid);os.setgid(person.pw_gid);os.setuid(person.pw_uid)
def safe_path(root,relative):
    if not isinstance(relative,str) or len(relative)>1000 or relative.startswith('/') or '\\' in relative or '\x00' in relative:raise ValueError('Invalid path')
    parts=relative.split('/') if relative else []
    if any(x in ('','.','..') or x.startswith('.pinas-upload-') for x in parts):raise ValueError('Invalid path')
    # Reject symlinks at every level, including the leaf. Never follow them.
    cur=root
    for part in parts:
        cur=cur/part
        if cur.is_symlink():raise ValueError('Symbolic links are not accessible')
    if not cur.resolve(strict=False).is_relative_to(root.resolve(strict=True)):raise ValueError('Path outside share')
    return cur
def main():
    if os.geteuid()!=0:raise ValueError('Root required')
    raw=sys.stdin.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise ValueError('Request too large')
    q=json.loads(raw);action=q.get('action');user=q.get('username');person=valid_user(user)
    if action=='authenticate':
        password=q.get('password')
        if not isinstance(password,str) or len(password)>256:raise ValueError('Invalid password')
        print('true' if hmac.compare_digest(md4(password.encode('utf-16le')),samba_hash(user)) else 'false');return
    allowed=shares_for(user)
    if action=='shares':
        print(json.dumps({'shares':[{'name':s['name'],'read_only':s['access'][user]=='ro'} for s in allowed]}));return
    share=q.get('share');s=next((x for x in allowed if x['name']==share),None)
    if s is None:raise ValueError('Share not accessible')
    # Root path derived exclusively from privileged share metadata, not browser paths.
    root=pathlib.Path(s['volume_label']) if False else None
    # Resolve mount from device, and confirm it is still the same mounted filesystem.
    device=s['volume'];p=subprocess.run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device],capture_output=True,text=True,timeout=5)
    targets=p.stdout.strip().splitlines()
    if p.returncode or len(targets)!=1:raise ValueError('Share storage is offline')
    mount=pathlib.Path(targets[0]).resolve(strict=True)
    if str(mount)=='/' or str(mount).startswith(('/etc/','/var/','/usr/','/home/','/boot/')):raise ValueError('Protected mount')
    root=mount/'PiNAS Shares'/s['name']
    if root.is_symlink() or not root.is_dir():raise ValueError('Share folder unavailable')
    relative=q.get('path','');target=safe_path(root,relative)
    writable=s['access'][user]=='rw'
    if action in ('mkdir','delete','rename','move','copy','upload','upload_start','upload_chunk','upload_finish','upload_cancel') and not writable:raise ValueError('Read-only share')
    drop(person)
    # All operations below run with the NAS user's UID/GID. Uploads are staged
    # in the destination directory, then published by an atomic rename.
    def valid_name(name):
        if not isinstance(name,str) or not name or len(name)>255 or name in ('.','..') or '/' in name or '\\' in name or '\x00' in name or name.startswith('.pinas-upload-'):raise ValueError('Invalid file name')
        return name
    def destination(relative):
        dest=safe_path(root,relative)
        if dest==root or dest.exists() or dest.is_symlink():raise ValueError('Destination already exists')
        if not dest.parent.is_dir():raise ValueError('Destination folder does not exist')
        return dest
    if action in ('rename','move','copy'):
        if target==root or not target.exists():raise ValueError('Invalid source')
        if action=='rename':
            dest=destination('/'.join(filter(None,[relative.rsplit('/',1)[0] if '/' in relative else '',valid_name(q.get('name'))])))
        else:
            dest=destination(q.get('dest',''))
        if target.is_dir() and (dest==target or target in dest.parents):raise ValueError('Cannot place folder inside itself')
        if action=='copy':
            import shutil
            if target.is_dir():
                # Reject links anywhere in the tree and cap total copy size.
                total=0
                for directory,dirs,files in os.walk(target,followlinks=False):
                    for name in dirs+files:
                        node=pathlib.Path(directory)/name
                        if node.is_symlink():raise ValueError('Symbolic links cannot be copied')
                        if node.is_file():total+=node.stat().st_size
                        if total>8*1024**3:raise ValueError('Folder copy exceeds 8 GiB safety limit')
                shutil.copytree(target,dest,symlinks=False)
            elif target.is_file():
                with target.open('rb') as src, dest.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            else:raise ValueError('Unsupported file type')
        else:
            # Same-share only; atomic rename prevents partial moves.
            if target.is_file():
                os.link(target,dest,follow_symlinks=False);target.unlink()
            else:target.rename(dest)
        print('{"ok":true}');return
    if action=='upload_start':
        name=valid_name(q.get('name'))
        if not target.is_dir():raise ValueError('Not a folder')
        destination('/'.join(filter(None,[relative,name])))
        size=q.get('size')
        if not isinstance(size,int) or size<0 or size>100*1024**3:raise ValueError('Invalid upload size')
        import secrets
        token=secrets.token_hex(20)
        staging=target/('.pinas-upload-'+token)
        fd=os.open(staging,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        meta=target/('.pinas-upload-'+token+'.json')
        fd=os.open(meta,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'name':name,'size':size,'path':relative},f)
        print(json.dumps({'token':token}));return
    if action in ('upload_chunk','upload_finish','upload_cancel'):
        token=q.get('token','')
        if not isinstance(token,str) or not re.fullmatch('[0-9a-f]{40}',token):raise ValueError('Invalid transfer token')
        stage=target/('.pinas-upload-'+token)
        meta=target/('.pinas-upload-'+token+'.json')
        if stage.is_symlink() or meta.is_symlink() or not stage.is_file() or not meta.is_file():raise ValueError('Unknown transfer')
        details=json.loads(meta.read_text());name=valid_name(details['name']);size=details['size']
        if details.get('path')!=relative:raise ValueError('Transfer location mismatch')
        if action=='upload_cancel':stage.unlink();meta.unlink();print('{"ok":true}');return
        if action=='upload_chunk':
            content=q.get('content','');offset=q.get('offset')
            if not isinstance(content,str) or len(content)>700000 or not isinstance(offset,int):raise ValueError('Invalid chunk')
            payload=base64.b64decode(content,validate=True)
            if len(payload)>512*1024 or offset!=stage.stat().st_size or offset+len(payload)>size:raise ValueError('Chunk offset or size mismatch')
            with stage.open('ab') as f:f.write(payload)
            print(json.dumps({'offset':offset+len(payload)}));return
        if stage.stat().st_size!=size:raise ValueError('Upload incomplete')
        dest=destination('/'.join(filter(None,[relative,name])))
        # Hard-link is no-clobber and atomic on the same filesystem.
        os.link(stage,dest,follow_symlinks=False);stage.unlink();meta.unlink()
        print('{"ok":true}');return
    if action=='download_chunk':
        offset=q.get('offset');size=q.get('size')
        if not isinstance(offset,int) or offset<0 or not isinstance(size,int) or size<1 or size>512*1024:raise ValueError('Invalid download range')
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode):raise ValueError('Not a regular file')
        total=target.stat().st_size
        with target.open('rb') as f:f.seek(offset);chunk=f.read(size)
        print(json.dumps({'content':base64.b64encode(chunk).decode(),'total':total}));return
    if action=='list':
        if not target.is_dir():raise ValueError('Not a folder')
        entries=[]
        for child in sorted(target.iterdir(),key=lambda x:x.name.casefold()):
            if child.is_symlink() or child.name.startswith('.pinas-upload-'):continue
            try:st=child.stat()
            except OSError:continue
            if stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode):entries.append({'name':child.name,'dir':stat.S_ISDIR(st.st_mode),'size':st.st_size})
            if len(entries)>=1000:break
        print(json.dumps({'entries':entries}));return
    if action=='mkdir':
        name=q.get('name','');dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..'):raise ValueError('Invalid folder name')
        dest.mkdir(mode=0o770);print('{"ok":true}');return
    if action=='delete':
        if target==root:raise ValueError('Cannot delete share root')
        if target.is_dir():target.rmdir()
        elif target.is_file():target.unlink()
        else:raise ValueError('Not a regular file or empty folder')
        print('{"ok":true}');return
    if action=='download':
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode) or target.stat().st_size>3*1024*1024:raise ValueError('Only files up to 3 MB supported in this test build')
        with target.open('rb') as f:content=base64.b64encode(f.read()).decode()
        print(json.dumps({'content':content}));return
    if action=='upload':
        name=q.get('name','');content=q.get('content','')
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..') or not isinstance(content,str) or len(content)>4*1024*1024+16:raise ValueError('Invalid upload')
        dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not target.is_dir():raise ValueError('Not a directory')
        payload=base64.b64decode(content,validate=True)
        if len(payload)>3*1024*1024:raise ValueError('Upload exceeds 3 MB')
        fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o660)
        with os.fdopen(fd,'wb') as f:f.write(payload)
        print('{"ok":true}');return
    raise ValueError('Unsupported action')
if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
"""

APT_INDEX_HELPER = r"""#!/usr/bin/env python3
import os,subprocess,sys
from pathlib import Path
ALLOWED={'off':None,'daily':'*-*-* 01:00:00','weekly':'Fri *-*-* 01:00:00','monthly':'*-*-28 01:00:00'}
def run(cmd,timeout=30):
    p=subprocess.run(cmd,timeout=timeout,check=False)
    if p.returncode:sys.exit(p.returncode)
def main():
    if os.geteuid()!=0:sys.exit('Root access required')
    args=sys.argv[1:]
    if len(args)==2 and args[0]=='schedule' and args[1] in ALLOWED:
        schedule=args[1];calendar=ALLOWED[schedule]
        timer=Path('/etc/systemd/system/pinas-auto-updates.timer')
        if calendar:
            timer.write_text('[Unit]\nDescription=PiNAS automatic OS updates\n[Timer]\nOnCalendar='+calendar+'\nPersistent=true\nUnit=pinas-auto-updates.service\n[Install]\nWantedBy=timers.target\n')
        run(['systemctl','daemon-reload'])
        if calendar:
            run(['systemctl','enable','--now','pinas-auto-updates.timer'])
            run(['systemctl','restart','pinas-auto-updates.timer'])
        else:
            run(['systemctl','disable','--now','pinas-auto-updates.timer']) if timer.exists() else None
            timer.unlink(missing_ok=True)
            run(['systemctl','daemon-reload'])
        marker=Path('/var/lib/pinas/update-schedule');marker.write_text(schedule+'\n');os.chmod(marker,0o644)
        return
    if args==['automatic']:
        # Only the systemd oneshot invokes this command, not the web service account.
        run(['/usr/bin/apt-get','update'],210)
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
        return
    if args==['upgrade']:
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
    elif args==['refresh']:
        run(['/usr/bin/apt-get','update'],210)
    else:sys.exit('Unsupported operation')
if __name__=='__main__':main()
"""

NAS_STORAGE_HELPER='#!/usr/bin/env python3\n"""PiNAS RC13 restricted, non-destructive storage adoption helper."""\nimport json,os,pathlib,re,subprocess,sys,uuid\nfrom pathlib import Path\n\ndef run(*args,timeout=15):\n    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)\n    if p.returncode:raise ValueError((p.stderr or \'Storage command failed\').strip()[-500:])\n    return p.stdout.strip()\n\ndef main():\n    if os.geteuid()!=0 or sys.argv[1:]!=[\'adopt\']:raise ValueError(\'Unsupported storage operation\')\n    data=json.loads(sys.stdin.read(4096));device=data.get(\'device\')\n    if not isinstance(device,str) or not re.fullmatch(r\'/dev/[A-Za-z0-9_./-]{1,90}\',device) or \'..\' in device:raise ValueError(\'Invalid device\')\n    path=Path(device)\n    if not path.is_block_device():raise ValueError(\'Device is not a block device\')\n    # The privileged helper independently identifies eligible physical disks.\n    roots=json.loads(run(\'lsblk\',\'-J\',\'-b\',\'-o\',\'NAME,PATH,TYPE,FSTYPE,UUID,MOUNTPOINTS,RO,PKNAME\')).get(\'blockdevices\',[])\n    bypath={};byname={};parents={}\n    def walk(node,parent=None):\n        name=node.get(\'name\');bypath[node.get(\'path\')]=node;byname[name]=node\n        if parent:parents[name]=parent\n        for child in node.get(\'children\') or []:walk(child,name)\n    for root in roots:walk(root)\n    node=bypath.get(str(path.resolve())) or bypath.get(device)\n    if not node or node.get(\'type\') not in (\'part\',\'disk\') or node.get(\'ro\'):raise ValueError(\'Not an eligible writable disk or partition\')\n    def root_for(n):\n        seen=set()\n        while n.get(\'name\') in parents:\n            if n[\'name\'] in seen:raise ValueError(\'Invalid device topology\')\n            seen.add(n[\'name\']);n=byname[parents[n[\'name\']]]\n        return n\n    disk=root_for(node)\n    if disk.get(\'type\')!=\'disk\' or disk.get(\'ro\') or str(disk.get(\'name\',\'\')).startswith((\'loop\',\'zram\',\'ram\',\'nbd\',\'sr\',\'fd\')):raise ValueError(\'Unsupported backing device\')\n    # Reject any physical disk carrying the root or boot filesystems.\n    protected={\'/\',\'/boot\',\'/boot/firmware\',\'/boot/efi\'}\n    def contains_system(n):\n        if any(m in protected for m in (n.get(\'mountpoints\') or []) if m):return True\n        return any(contains_system(c) for c in n.get(\'children\') or [])\n    if contains_system(disk):raise ValueError(\'Operating system storage is protected\')\n    for mount in protected:\n        src=run(\'findmnt\',\'-n\',\'-o\',\'SOURCE\',\'--target\',mount).split(\'[\',1)[0]\n        if src and src in bypath and root_for(bypath[src]).get(\'name\')==disk.get(\'name\'):\n            raise ValueError(\'Operating system storage is protected\')\n    fs=run(\'blkid\',\'-s\',\'TYPE\',\'-o\',\'value\',device)\n    uid=run(\'blkid\',\'-s\',\'UUID\',\'-o\',\'value\',device)\n    if fs not in (\'ext4\',\'xfs\',\'btrfs\') or not re.fullmatch(r\'[A-Za-z0-9-]{8,64}\',uid):raise ValueError(\'Supported filesystem and UUID required\')\n    # Reject RAID/LVM/crypto members and nested volume layouts.\n    if node.get(\'type\')==\'disk\' and node.get(\'children\'):raise ValueError(\'Choose a filesystem partition, not its parent disk\')\n    if node.get(\'children\'):raise ValueError(\'Complex volume layout not supported\')\n    mountpoints=[m for m in node.get(\'mountpoints\') or [] if m]\n    if len(mountpoints)>1:raise ValueError(\'Multiple mountpoints require manual review\')\n    if mountpoints and not str(mountpoints[0]).startswith(\'/mnt/pinas/\'):\n        raise ValueError(\'Filesystem is already mounted elsewhere; manage it manually to avoid disrupting applications\')\n    target=Path(\'/mnt/pinas\')/uid\n    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir())) and str(target) not in mountpoints):raise ValueError(\'Mount destination is not empty\')\n    fstab=Path(\'/etc/fstab\');original=fstab.read_text();entries=[line.split() for line in original.splitlines() if line.strip() and not line.lstrip().startswith(\'#\')]\n    for e in entries:\n        if len(e)>=2 and (e[0] in (device,\'UUID=\'+uid,\'/dev/disk/by-uuid/\'+uid) or e[1]==str(target)):\n            if e[0]==\'UUID=\'+uid and e[1]==str(target):\n                if str(target) not in mountpoints:run(\'mount\',str(target),timeout=25)\n                print(json.dumps({\'ok\':True,\'mount\':str(target),\'existing\':True}));return\n            raise ValueError(\'Existing fstab configuration requires manual review\')\n    target.parent.mkdir(parents=True,exist_ok=True)\n    target.mkdir(mode=0o755,exist_ok=True)\n    options=\'defaults,nofail,noatime,x-systemd.device-timeout=10s\'\n    entry=f\'UUID={uid} {target} {fs} {options} 0 {2 if fs=="ext4" else 0} # PiNAS managed\\\\n\'\n    entry=entry.replace(\'\\\\n\',\'\\n\')\n    backup=fstab.with_name(\'fstab.pinas-\'+uuid.uuid4().hex[:12]+\'.bak\')\n    backup.write_text(original);os.chmod(backup,0o600)\n    temp=fstab.with_name(\'.fstab.pinas-\'+uuid.uuid4().hex)\n    try:\n        temp.write_text(original.rstrip(\'\\n\')+\'\\n\'+entry);os.chmod(temp,0o644)\n        os.replace(temp,fstab)\n        run(\'systemctl\',\'daemon-reload\',timeout=15)\n        run(\'mount\',str(target),timeout=25)\n        actual=run(\'findmnt\',\'-n\',\'-o\',\'UUID\',\'--target\',str(target))\n        if actual!=uid:raise ValueError(\'Mounted filesystem UUID verification failed\')\n    except Exception:\n        fstab.write_text(original)\n        try:run(\'systemctl\',\'daemon-reload\')\n        except Exception:pass\n        raise\n    print(json.dumps({\'ok\':True,\'mount\':str(target)}))\nif __name__==\'__main__\':\n    try:main()\n    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)\n'

SMART_HEALTH_HELPER = """#!/usr/bin/env python3
import json,os,shutil,subprocess,sys
from pathlib import Path
def main():
    if os.geteuid()!=0 or len(sys.argv)!=1:
        raise ValueError('Unsupported operation')
    smartctl=shutil.which('smartctl')
    if not smartctl:
        print(json.dumps({'installed':False,'drives':[]}));return
    p=subprocess.run(['lsblk','-J','-b','-o','NAME,PATH,TYPE,MODEL,TRAN'],capture_output=True,text=True,timeout=8,check=True)
    drives=[]
    for disk in json.loads(p.stdout).get('blockdevices',[]):
        if disk.get('type')!='disk':continue
        device=disk.get('path','')
        if not isinstance(device,str) or not device.startswith('/dev/') or not Path(device).is_block_device():continue
        if disk.get('name','').startswith(('loop','zram','ram','nbd','sr','fd')):continue
        entry={'device':device,'model':disk.get('model') or disk.get('name'),'status':'Unavailable','temperature':None}
        try:
            result=subprocess.run([smartctl,'-j','-H','-A',device],capture_output=True,text=True,timeout=12)
            data=json.loads(result.stdout)
            health=data.get('smart_status',{}).get('passed')
            if health is True:entry['status']='Healthy'
            elif health is False:entry['status']='Warning'
            temp=data.get('temperature',{}).get('current')
            if isinstance(temp,(int,float)) and -20<=temp<=120:entry['temperature']=temp
            if data.get('smart_support',{}).get('available') is False:entry['status']='Unsupported'
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        drives.append(entry)
    print(json.dumps({'installed':True,'drives':drives}))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

def install(args):
    if sys.platform!='linux' or os.geteuid()!=0:sys.exit('Install requires Linux and sudo/root.')
    if not Path('/etc/os-release').exists():sys.exit('Unsupported OS')
    osinfo=read('/etc/os-release')
    if 'debian' not in osinfo.lower() and 'raspbian' not in osinfo.lower():sys.exit('Requires Raspberry Pi OS / Debian family')
    if not args.skip_packages:
        print('Installing NAS dependencies (requires network and may take time)...',flush=True)
        subprocess.run(['apt-get','update'],check=True)
        subprocess.run(['apt-get','install','-y','samba','xfsprogs','btrfs-progs','mdadm','parted','util-linux','e2fsprogs','avahi-daemon','acl','openssl'],check=True)
    target=Path('/opt/pinas');target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(__file__).resolve(),target/'pinas.py');os.chmod(target/'pinas.py',0o755)
    if subprocess.run(['id','-u','pinas'],capture_output=True).returncode!=0:
        subprocess.run(['useradd','--system','--home-dir','/var/lib/pinas','--shell','/usr/sbin/nologin','pinas'],check=True)
    DATA.mkdir(parents=True,exist_ok=True);os.chmod(DATA,0o700)
    subprocess.run(['chown','pinas:pinas',str(DATA)],check=True)
    helper=Path('/usr/local/libexec/pinas-apply-hostname')
    helper.parent.mkdir(parents=True,exist_ok=True)
    helper.write_text(HOSTNAME_HELPER)
    os.chmod(helper,0o755)
    unit='''[Unit]\nDescription=Apply validated PiNAS device hostname\nAfter=systemd-hostnamed.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /usr/local/libexec/pinas-apply-hostname\nNoNewPrivileges=true\nProtectHome=true\nPrivateTmp=true\n'''
    Path('/etc/systemd/system/pinas-hostname.service').write_text(unit)
    path_unit='''[Unit]\nDescription=Apply PiNAS hostname when configuration changes\n[Path]\nPathChanged=/var/lib/pinas/config.json\nUnit=pinas-hostname.service\n[Install]\nWantedBy=multi-user.target\n'''
    Path('/etc/systemd/system/pinas-hostname.path').write_text(path_unit)
    user_helper=Path('/usr/local/libexec/pinas-nas-user')
    user_helper.write_text(NAS_USER_HELPER)
    os.chown(user_helper,0,0);os.chmod(user_helper,0o700)
    sudoers=Path('/etc/sudoers.d/pinas-nas-user')
    sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-user create *, /usr/local/libexec/pinas-nas-user password *, /usr/local/libexec/pinas-nas-user list\n')
    os.chown(sudoers,0,0);os.chmod(sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(sudoers)],capture_output=True).returncode:
        sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS sudoers configuration')
    share_helper=Path('/usr/local/libexec/pinas-nas-share')
    share_helper.write_text(NAS_SHARE_HELPER)
    os.chown(share_helper,0,0);os.chmod(share_helper,0o700)
    share_sudoers=Path('/etc/sudoers.d/pinas-nas-share')
    share_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-share list, /usr/local/libexec/pinas-nas-share create\n')
    os.chown(share_sudoers,0,0);os.chmod(share_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(share_sudoers)],capture_output=True).returncode:
        share_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS share sudoers configuration')
    files_helper=Path('/usr/local/libexec/pinas-nas-files')
    files_helper.write_text(NAS_FILES_HELPER)
    os.chown(files_helper,0,0);os.chmod(files_helper,0o700)
    files_sudoers=Path('/etc/sudoers.d/pinas-nas-files')
    files_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-files\n')
    os.chown(files_sudoers,0,0);os.chmod(files_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(files_sudoers)],capture_output=True).returncode:
        files_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS file helper sudoers configuration')
    storage_helper=Path('/usr/local/libexec/pinas-nas-storage')
    storage_helper.write_text(NAS_STORAGE_HELPER)
    os.chown(storage_helper,0,0);os.chmod(storage_helper,0o700)
    storage_sudoers=Path('/etc/sudoers.d/pinas-nas-storage')
    storage_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-storage adopt\n')
    os.chown(storage_sudoers,0,0);os.chmod(storage_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(storage_sudoers)],capture_output=True).returncode:
        storage_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS storage sudoers configuration')
    smart_helper=Path('/usr/local/libexec/pinas-smart-health')
    smart_helper.write_text(SMART_HEALTH_HELPER)
    os.chown(smart_helper,0,0);os.chmod(smart_helper,0o700)
    smart_sudoers=Path('/etc/sudoers.d/pinas-smart-health')
    smart_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-smart-health\n')
    os.chown(smart_sudoers,0,0);os.chmod(smart_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(smart_sudoers)],capture_output=True).returncode:
        smart_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS SMART sudoers configuration')
    apt_helper=Path('/usr/local/libexec/pinas-apt-index')
    apt_helper.write_text(APT_INDEX_HELPER)
    os.chown(apt_helper,0,0);os.chmod(apt_helper,0o700)
    apt_sudoers=Path('/etc/sudoers.d/pinas-apt-index')
    apt_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-apt-index refresh, /usr/local/libexec/pinas-apt-index upgrade, /usr/local/libexec/pinas-apt-index schedule off, /usr/local/libexec/pinas-apt-index schedule daily, /usr/local/libexec/pinas-apt-index schedule weekly, /usr/local/libexec/pinas-apt-index schedule monthly\n')
    os.chown(apt_sudoers,0,0);os.chmod(apt_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(apt_sudoers)],capture_output=True).returncode:
        apt_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS APT sudoers configuration')
    auto_service=Path('/etc/systemd/system/pinas-auto-updates.service')
    auto_service.write_text('[Unit]\nDescription=PiNAS scheduled OS updates\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=oneshot\nExecStart=/usr/local/libexec/pinas-apt-index automatic\nEnvironment=DEBIAN_FRONTEND=noninteractive\n')
    os.chown(auto_service,0,0);os.chmod(auto_service,0o644)
    # Existing schedule is preserved when upgrading PiNAS.
    # Generate a persistent per-install certificate; never replace it on upgrades.
    if not TLS_CERT.exists() or not TLS_KEY.exists():
        if TLS_CERT.exists() or TLS_KEY.exists():sys.exit('Incomplete TLS certificate pair; resolve manually before installing')
        if not shutil.which('openssl'):sys.exit('OpenSSL required for initial TLS certificate generation')
        hostname=load().get('hostname','pinas')
        if not valid_hostname(hostname):hostname='pinas'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','825',
            '-keyout',str(TLS_KEY),'-out',str(TLS_CERT),'-subj',f'/CN={hostname}.local',
            '-addext',f'subjectAltName=DNS:{hostname}.local,DNS:localhost,IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL)
    for f,mode in ((TLS_CERT,0o644),(TLS_KEY,0o600)):
        os.chown(f,0 if f==TLS_CERT else __import__('pwd').getpwnam('pinas').pw_uid,0 if f==TLS_CERT else __import__('grp').getgrnam('pinas').gr_gid)
        os.chmod(f,mode)
    bind_host='0.0.0.0' if args.lan else '127.0.0.1' 
    # TEMPORARY RC9.2: sudo inherits the service mount namespace. A root helper
    # cannot write /etc/passwd, /etc/group or Samba state with ProtectSystem=strict.
    # Replace sudo delegation with an independently sandboxed privileged service.
    service='''[Unit]\nDescription=PiNAS prototype web dashboard\nAfter=network.target\n[Service]\nType=simple\nUser=pinas\nGroup=pinas\nExecStart=/usr/bin/python3 /opt/pinas/pinas.py --serve --tls --host %s --port %d\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=false\nProtectSystem=false\nReadWritePaths=/var/lib/pinas\nPrivateTmp=true\n[Install]\nWantedBy=multi-user.target\n'''%(bind_host,args.port)
    Path('/etc/systemd/system/pinas.service').write_text(service)
    subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','enable','--now','pinas-hostname.path'],check=True);subprocess.run(['systemctl','start','pinas-hostname.service'],check=True);subprocess.run(['systemctl','enable','pinas.service'],check=True);subprocess.run(['systemctl','restart','pinas.service'],check=True)
    print(f'PiNAS installed. For localhost access: https://127.0.0.1:{args.port} (self-signed certificate)')
    if args.lan:print(f'LAN TLS MODE: open https://<PI-IP>:{args.port}. Certificate is self-signed; use the .local hostname for name matching. Do not expose this port to the internet.')
    else:print('Localhost-only mode; re-run installer with --lan to enable direct LAN access for testing.')

def main():
    ap=argparse.ArgumentParser(description='PiNAS Raspberry Pi NAS prototype')
    ap.add_argument('--lan',action='store_true',help='Bind HTTPS server to LAN interfaces');ap.add_argument('--install',action='store_true');ap.add_argument('--serve',action='store_true');ap.add_argument('--tls',action='store_true');ap.add_argument('--skip-packages',action='store_true');ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=8765)
    a=ap.parse_args()
    if a.install:install(a);return
    if a.serve:
        if a.host not in ('127.0.0.1','::1','0.0.0.0'):sys.exit('Unsupported bind address.')
        if a.host=='0.0.0.0' and not a.tls:sys.exit('LAN listening requires HTTPS (--tls)')
        server=ThreadingHTTPServer((a.host,a.port),Handler)
        if a.tls:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(TLS_CERT),str(TLS_KEY))
            server.socket=context.wrap_socket(server.socket,server_side=True)
        print('PiNAS running on %s://%s:%s'%('https' if a.tls else 'http',a.host,a.port))
        threading.Thread(target=cpu_sampler,daemon=True).start();server.serve_forever();return
    ap.print_help()
if __name__=='__main__':main()) for x in (name,new_name)):
                self.json({'error':'Invalid share name.'},400);return
            if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not isinstance(u,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):
                self.json({'error':'Assign at least one valid user access.'},400);return
            if not isinstance(password,str) or not verify(password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not set(access).issubset({u['name'] for u in nas_user_list()}):
                self.json({'error':'Unknown NAS user.'},409);return
            if not any(isinstance(item,dict) and item.get('name')==name for item in nas_share_list()):
                self.json({'error':'Only PiNAS-managed shares can be edited.'},404);return
            try:edit_nas_share(name,new_name,access)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':new_name});return
        if path=='/api/delete-share':
            name=data.get('name');password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):
                self.json({'error':'Invalid share name.'},400);return
            if not isinstance(password,str) or not verify(password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not any(isinstance(item,dict) and item.get('name')==name for item in nas_share_list()):
                self.json({'error':'Only PiNAS-managed shares can be removed.'},404);return
            try:delete_nas_share(name)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name,'files_preserved':True});return
        if path=='/api/nas-shares':
            name=data.get('name');volume=data.get('volume');access=data.get('access');admin_password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):
                self.json({'error':'Choose a share name of 1–32 letters, digits, spaces, underscores or hyphens.'},400);return
            if not isinstance(volume,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',volume) or '..' in volume:
                self.json({'error':'Invalid storage selection.'},400);return
            if not isinstance(access,dict) or not access or len(access)>64 or any(not isinstance(k,str) or v not in ('ro','rw') for k,v in access.items()):
                self.json({'error':'Assign at least one user Read Only or Read & Write access.'},400);return
            if not isinstance(admin_password,str) or not verify(admin_password,cfg.get('admin_password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not storage_is_ready():self.json({'error':'A mounted, persistent data filesystem is required.'},409);return
            valid_users={u['name'] for u in nas_user_list()}
            if not set(access).issubset(valid_users):self.json({'error':'One or more users are not valid Samba accounts.'},409);return
            if any(name.casefold()==s.casefold() for s in discover().get('shares',[])):
                self.json({'error':'A share with this name already exists.'},409);return
            try:create_nas_share(name,volume,access)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name});return
        if path=='/api/logout':SESSIONS.pop(token,None);self.json({'ok':True},cookie='pinas_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'+('; Secure' if isinstance(self.connection,ssl.SSLSocket) else ''));return
        if path=='/api/settings':
            theme,accent,font=data.get('theme'),data.get('accent'),data.get('font')
            interval,history=data.get('cpu_interval',cfg.get('cpu_interval',5)),data.get('cpu_history',cfg.get('cpu_history',10))
            session_timeout=data.get('session_timeout',cfg.get('session_timeout',5))
            if theme not in ('light','dark','dark-cb','light-cb') or not isinstance(accent,str) or len(accent)!=7 or accent[0]!='#' or any(c not in '0123456789abcdefABCDEF' for c in accent[1:]) or type(font)!=int or font not in (10,12,14,16) or type(interval)!=int or interval not in (2,5,10) or type(history)!=int or history not in (10,15,30,60) or type(session_timeout)!=int or session_timeout not in (5,10,15,30,60):self.json({'error':'Invalid appearance settings'},400);return
            cfg.update(theme=theme,accent=accent,font=font,cpu_interval=interval,cpu_history=history,session_timeout=session_timeout)
        elif path=='/api/background':
            image=data.get('image')
            if not isinstance(image,str) or len(image)>2_900_000:self.json({'error':'Image too large'},400);return
            if image:
                try:
                    meta,b64=image.split(',',1);mime=meta[5:].split(';',1)[0]
                    if mime not in ('image/jpeg','image/png','image/webp'):raise ValueError()
                    decoded=base64.b64decode(b64,validate=True)
                    if len(decoded)>2*1024*1024:raise ValueError()
                    if not ((mime=='image/jpeg' and decoded.startswith(b'\xff\xd8\xff')) or (mime=='image/png' and decoded.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/webp' and decoded.startswith(b'RIFF') and decoded[8:12]==b'WEBP')):raise ValueError()
                except (ValueError,IndexError):self.json({'error':'Invalid image'},400);return
            cfg['login_background']=image
        save(cfg);self.json({'settings':dict({k:cfg.get(k) for k in ('theme','accent','font','cpu_interval','cpu_history','session_timeout')},has_background=bool(cfg.get('login_background')))} )

HOSTNAME_HELPER = r"""#!/usr/bin/env python3
import json, re, subprocess
from pathlib import Path
try:
    path=Path('/var/lib/pinas/config.json')
    if not path.exists():raise SystemExit(0)
    cfg=json.loads(path.read_text())
    hostname=cfg.get('hostname','')
    if not hostname:raise SystemExit(0)
    if not isinstance(hostname,str) or not 1<=len(hostname)<=63 or not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*',hostname):
        raise ValueError('Invalid hostname')
    current=subprocess.run(['hostname','-s'],capture_output=True,text=True,check=True).stdout.strip()
    if current!=hostname:
        subprocess.run(['/usr/bin/hostnamectl','set-hostname',hostname],check=True,timeout=15)
except (OSError,ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
    raise SystemExit('PiNAS hostname not applied: '+str(exc))
"""

NAS_USER_HELPER = r"""#!/usr/bin/env python3
# Privileged helper. No arbitrary command execution; narrowly scoped account actions.
import grp, json, os, pwd, re, subprocess, sys

def run(argv, **kwargs):
    return subprocess.run(argv, check=True, timeout=20, **kwargs)

def samba_users():
    p=run(['/usr/bin/pdbedit','-L'],capture_output=True,text=True)
    result=[]
    for line in p.stdout.splitlines():
        fields=line.split(':',2)
        if len(fields)>=2 and re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',fields[0]):
            result.append({'name':fields[0],'uid':fields[1]})
    return sorted(result,key=lambda x:x['name'])

if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit(2)
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(samba_users()))
        raise SystemExit(0)
    if len(sys.argv)!=3 or sys.argv[1] not in ('create','password'):raise SystemExit(2)
    name=sys.argv[2]
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',name) or name in ('pinas','root','admin','nobody'):raise SystemExit(2)
    password=sys.stdin.readline(258).rstrip('\n')
    if not 12<=len(password)<=256:raise SystemExit(2)
    if sys.argv[1]=='password':
        group=grp.getgrnam('pinas-nas')
        existing=pwd.getpwnam(name)
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin') or not any(u['name']==name for u in samba_users()):
            raise SystemExit('Not a managed PiNAS Samba user')
        run(['/usr/bin/smbpasswd','-s',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        raise SystemExit(0)
    try:
        group=grp.getgrnam('pinas-nas')
    except KeyError:
        run(['/usr/sbin/groupadd','pinas-nas'])
        group=grp.getgrnam('pinas-nas')
    created=False
    try:
        existing=pwd.getpwnam(name)
    except KeyError:
        existing=None
    if existing:
        # Repair only a partial PiNAS account from a previous failed attempt.
        # Never repurpose unrelated Linux accounts.
        if existing.pw_gid!=group.gr_gid or existing.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):
            raise SystemExit('Linux account already exists and is not a PiNAS NAS account; choose another username')
        if any(u['name']==name for u in samba_users()):
            raise SystemExit('Samba account already exists; refresh the Users page')
    else:
        run(['/usr/sbin/useradd','--no-create-home','--shell','/usr/sbin/nologin','--gid','pinas-nas',name])
        created=True
    try:
        run(['/usr/bin/smbpasswd','-s','-a',name],input=password+'\n'+password+'\n',text=True,capture_output=True)
        run(['/usr/bin/smbpasswd','-e',name],capture_output=True)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        if created:subprocess.run(['/usr/sbin/userdel',name],check=False,timeout=10)
        raise SystemExit('Samba account creation failed: '+str(exc))
"""

NAS_SHARE_HELPER = r"""#!/usr/bin/env python3
# Root-only share broker. Strict input validation and independent mount checks.
import json, os, pathlib, pwd, re, subprocess, sys, tempfile

DB=pathlib.Path('/var/lib/pinas/shares.json')
CONF=pathlib.Path('/etc/samba/pinas-shares.conf')
SMB=pathlib.Path('/etc/samba/smb.conf')

def run(cmd, **kw):
    return subprocess.run(cmd,check=True,timeout=15,capture_output=True,text=True,**kw)

def read_db():
    try:
        value=json.loads(DB.read_text())
        return value if isinstance(value,list) else []
    except (OSError,ValueError):return []

def atomic(path,content,mode=0o600):
    fd,name=tempfile.mkstemp(prefix='.pinas-',dir=str(path.parent))
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'w') as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def check_volume(device):
    if not isinstance(device,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',device) or '..' in device:raise ValueError('Invalid device')
    # Device must be a block device with an approved filesystem.
    p=pathlib.Path(device)
    if not p.is_block_device():raise ValueError('Selected storage is not a block device')
    fs=run(['/usr/bin/lsblk','-n','-o','FSTYPE',device]).stdout.strip().splitlines()
    if not fs or fs[0].strip().lower() not in ('ext4','xfs','btrfs'):raise ValueError('Unsupported filesystem')
    target=run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device]).stdout.strip().splitlines()
    if len(target)!=1:raise ValueError('Disk must have one unambiguous active mount')
    mount=pathlib.Path(target[0]).resolve(strict=True)
    if str(mount) in ('/','/boot','/boot/firmware') or any(str(mount).startswith(prefix) for prefix in ('/etc/','/var/','/usr/','/home/','/opt/','/root/','/proc/','/sys/','/run/')):
        raise ValueError('System storage cannot host NAS shares')
    if not mount.is_dir() or mount.is_symlink():raise ValueError('Invalid mount directory')
    # Confirm mounted persistently via UUID, path or LABEL; do not trust browser data.
    uuid=run(['/usr/sbin/blkid','-s','UUID','-o','value',device]).stdout.strip()
    entries=[line.split() for line in pathlib.Path('/etc/fstab').read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not any(len(e)>=2 and e[1]==str(mount) and e[0] in (device,'UUID='+uuid,'/dev/disk/by-uuid/'+uuid) for e in entries):
        raise ValueError('Disk is not persistently configured in fstab')
    # Reject root device even when mounted at a second location.
    rootdev=run(['/usr/bin/findmnt','-n','-o','SOURCE','/']).stdout.strip()
    if rootdev.startswith('/dev/'):
        rootparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',rootdev]).stdout.split())
        selectedparents=set(run(['/usr/bin/lsblk','-s','-n','-o','MAJ:MIN',device]).stdout.split())
        if rootparents & selectedparents:raise ValueError('Operating system disk is protected')
    return mount

def main():
    if os.geteuid()!=0:raise ValueError('Root helper required')
    if len(sys.argv)==2 and sys.argv[1]=='list':
        print(json.dumps(read_db()));return
    if len(sys.argv)==2 and sys.argv[1]=='delete':
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('Request too large')
        request=json.loads(raw);name=request.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):raise ValueError('Invalid share name')
        current=read_db()
        matches=[item for item in current if isinstance(item,dict) and item.get('name')==name]
        if len(matches)!=1:raise ValueError('Share is not managed by PiNAS')
        oldconf=CONF.read_text()
        # Match only a complete, exact managed Samba section; never touch unrelated shares.
        section=re.compile(r'(?m)^\['+re.escape(name)+r'\][ \t]*\n(?:(?!\[).*(?:\n|$))*')
        found=list(section.finditer(oldconf))
        if len(found)!=1:raise ValueError('Managed Samba share section missing or ambiguous')
        updated=oldconf[:found[0].start()]+oldconf[found[0].end():]
        olddb=DB.read_text()
        try:
            atomic(CONF,updated,0o644)
            run(['/usr/bin/testparm','-s'])
            run(['/usr/bin/systemctl','reload','smbd'])
            atomic(DB,json.dumps([item for item in current if not (isinstance(item,dict) and item.get('name')==name)],indent=2),0o600)
        except Exception:
            atomic(CONF,oldconf,0o644)
            atomic(DB,olddb,0o600)
            try:run(['/usr/bin/systemctl','reload','smbd'])
            except Exception:pass
            raise
        # Deliberately leave the share directory, ACLs and files untouched.
        print(json.dumps({'ok':True,'files_preserved':True}));return
    if len(sys.argv)!=2 or sys.argv[1]!='create':raise ValueError('Unsupported action')
    raw=sys.stdin.read(8193)
    if len(raw)>8192:raise ValueError('Request too large')
    request=json.loads(raw)
    name=request.get('name');access=request.get('access');device=request.get('volume')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):raise ValueError('Invalid share name')
    if not isinstance(access,dict) or not 1<=len(access)<=64 or any(not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):raise ValueError('Invalid access policy')
    # Verify users exist in Samba and Linux before creating any directory.
    samba={line.split(':',1)[0] for line in run(['/usr/bin/pdbedit','-L']).stdout.splitlines()}
    for user in access:
        if user not in samba:raise ValueError('Samba account not found: '+user)
        pwd.getpwnam(user)
    mount=check_volume(device)
    current=read_db()
    if any(item.get('name','').casefold()==name.casefold() for item in current):raise ValueError('Share already exists')
    # Samba's own configuration may include external shares; reject collisions.
    existing=run(['/usr/bin/testparm','-s']).stdout
    if any(line.strip().casefold()=='['+name.casefold()+']' for line in existing.splitlines()):raise ValueError('Share name already used by Samba')
    # No preexisting folder is ever adopted or modified by this operation.
    root=mount/'PiNAS Shares'
    if root.is_symlink():raise ValueError('Unsafe share root')
    root.mkdir(mode=0o711,exist_ok=True)
    if root.stat().st_uid!=0 or (root.stat().st_mode & 0o022):raise ValueError('Share root must be root-owned and not group/world writable')
    folder=root/name
    if folder.exists() or folder.is_symlink():raise ValueError('Folder already exists; choose a different name')
    if not pathlib.Path('/usr/bin/setfacl').exists():raise ValueError('POSIX ACL tools are required (install acl)')
    # Validate smb.conf can be managed before changing filesystem.
    original=SMB.read_text()
    include='   include = /etc/samba/pinas-shares.conf'
    if include not in original:
        if not re.search(r'(?im)^\s*\[global\]\s*$',original):raise ValueError('Samba [global] section missing')
        amended=re.sub(r'(?im)^(\s*\[global\]\s*)$',r'\1\n'+include,original,count=1)
    else:amended=original
    # Explicit per-user access; default deny for other NAS accounts.
    ro=[u for u,p in access.items() if p=='ro'];rw=[u for u,p in access.items() if p=='rw']
    stanza='\n['+name+']\n   path = '+str(folder)+'\n   browseable = yes\n   guest ok = no\n   read only = yes\n   valid users = '+', '.join(access)+'\n'
    if rw:stanza+='   write list = '+', '.join(rw)+'\n'
    stanza+='   create mask = 0660\n   directory mask = 0770\n   follow symlinks = no\n   wide links = no\n'
    oldconf=CONF.read_text() if CONF.exists() else ''
    if '['+name+']' in oldconf:raise ValueError('Duplicate managed share')
    folder.mkdir(mode=0o700)
    try:
        # Root-owned folder; Samba creates files as authenticated Unix users.
        os.chown(folder,0,0)
        os.chmod(folder,0o700)
        acl=['u::rwx','g::---','o::---','m::rwx']+[f'u:{u}:'+('rwx' if p=='rw' else 'r-x') for u,p in access.items()]
        default=['d:'+entry for entry in acl]
        run(['/usr/bin/setfacl','-m',','.join(acl+default),str(folder)])
        if amended!=original:atomic(SMB,amended,0o644)
        atomic(CONF,oldconf+stanza,0o644)
        run(['/usr/bin/testparm','-s'])
        run(['/usr/bin/systemctl','reload','smbd'])
        current.append({'name':name,'volume_label':mount.name,'volume':device,'access':access})
        atomic(DB,json.dumps(current,indent=2),0o600)
    except Exception:
        atomic(CONF,oldconf,0o644)
        if amended!=original:atomic(SMB,original,0o644)
        try:run(['/usr/bin/systemctl','reload','smbd'])
        except Exception:pass
        try:folder.rmdir()
        except OSError:pass
        raise
    print(json.dumps({'ok':True,'name':name}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

NAS_FILES_HELPER = r"""#!/usr/bin/env python3
# Privileged, narrow file broker. Authentication against Samba passdb; filesystem
# operations executed as the NAS user's actual UID/GID and supplementary groups.
import base64, hashlib, hmac, json, os, pathlib, pwd, re, stat, subprocess, sys
DB=pathlib.Path('/var/lib/pinas/shares.json')
def md4(message):
    # NT hash is MD4(UTF-16LE password). Samba uses NT hashes for SMB auth.
    import struct
    original=len(message);message+=b'\x80';message+=b'\0'*((56-len(message)%64)%64)+struct.pack('<Q',original*8)
    a,b,c,d=0x67452301,0xefcdab89,0x98badcfe,0x10325476
    def rol(v,n):return ((v<<n)|(v>>(32-n)))&0xffffffff
    for offset in range(0,len(message),64):
        x=struct.unpack('<16I',message[offset:offset+64]);aa,bb,cc,dd=a,b,c,d
        for j in range(48):
            if j<16:f=(b&c)|(~b&d);k=j;shift=[3,7,11,19][j%4];constant=0
            elif j<32:f=(b&c)|(b&d)|(c&d);k=(j%4)*4+j//4-4;shift=[3,5,9,13][j%4];constant=0x5a827999
            else:f=b^c^d;k=[0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15][j-32];shift=[3,9,11,15][j%4];constant=0x6ed9eba1
            value=rol((a+f+x[k]+constant)&0xffffffff,shift);a,b,c,d=d,value,b,c
        a=(a+aa)&0xffffffff;b=(b+bb)&0xffffffff;c=(c+cc)&0xffffffff;d=(d+dd)&0xffffffff
    return struct.pack('<4I',a,b,c,d).hex().upper()
def samba_hash(user):
    p=subprocess.run(['/usr/bin/pdbedit','-Lw',user],capture_output=True,text=True,timeout=8)
    if p.returncode:raise ValueError('Unknown NAS account')
    for line in p.stdout.splitlines():
        fields=line.split(':')
        if len(fields)>4 and fields[0]==user and re.fullmatch('[A-Fa-f0-9]{32}',fields[3]):return fields[3].upper()
    raise ValueError('NAS account has no valid Samba password')
def valid_user(user):
    if not isinstance(user,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',user):raise ValueError('Invalid user')
    person=pwd.getpwnam(user)
    if person.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):raise ValueError('Not a PiNAS NAS user')
    if samba_hash(user)=='':raise ValueError('Not a Samba user')
    return person
def shares_for(user):
    entries=json.loads(DB.read_text())
    return [s for s in entries if isinstance(s,dict) and s.get('access',{}).get(user) in ('ro','rw')]
def drop(person):
    os.initgroups(person.pw_name,person.pw_gid);os.setgid(person.pw_gid);os.setuid(person.pw_uid)
def safe_path(root,relative):
    if not isinstance(relative,str) or len(relative)>1000 or relative.startswith('/') or '\\' in relative or '\x00' in relative:raise ValueError('Invalid path')
    parts=relative.split('/') if relative else []
    if any(x in ('','.','..') or x.startswith('.pinas-upload-') for x in parts):raise ValueError('Invalid path')
    # Reject symlinks at every level, including the leaf. Never follow them.
    cur=root
    for part in parts:
        cur=cur/part
        if cur.is_symlink():raise ValueError('Symbolic links are not accessible')
    if not cur.resolve(strict=False).is_relative_to(root.resolve(strict=True)):raise ValueError('Path outside share')
    return cur
def main():
    if os.geteuid()!=0:raise ValueError('Root required')
    raw=sys.stdin.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise ValueError('Request too large')
    q=json.loads(raw);action=q.get('action');user=q.get('username');person=valid_user(user)
    if action=='authenticate':
        password=q.get('password')
        if not isinstance(password,str) or len(password)>256:raise ValueError('Invalid password')
        print('true' if hmac.compare_digest(md4(password.encode('utf-16le')),samba_hash(user)) else 'false');return
    allowed=shares_for(user)
    if action=='shares':
        print(json.dumps({'shares':[{'name':s['name'],'read_only':s['access'][user]=='ro'} for s in allowed]}));return
    share=q.get('share');s=next((x for x in allowed if x['name']==share),None)
    if s is None:raise ValueError('Share not accessible')
    # Root path derived exclusively from privileged share metadata, not browser paths.
    root=pathlib.Path(s['volume_label']) if False else None
    # Resolve mount from device, and confirm it is still the same mounted filesystem.
    device=s['volume'];p=subprocess.run(['/usr/bin/findmnt','-n','-o','TARGET','--source',device],capture_output=True,text=True,timeout=5)
    targets=p.stdout.strip().splitlines()
    if p.returncode or len(targets)!=1:raise ValueError('Share storage is offline')
    mount=pathlib.Path(targets[0]).resolve(strict=True)
    if str(mount)=='/' or str(mount).startswith(('/etc/','/var/','/usr/','/home/','/boot/')):raise ValueError('Protected mount')
    root=mount/'PiNAS Shares'/s['name']
    if root.is_symlink() or not root.is_dir():raise ValueError('Share folder unavailable')
    relative=q.get('path','');target=safe_path(root,relative)
    writable=s['access'][user]=='rw'
    if action in ('mkdir','delete','rename','move','copy','upload','upload_start','upload_chunk','upload_finish','upload_cancel') and not writable:raise ValueError('Read-only share')
    drop(person)
    # All operations below run with the NAS user's UID/GID. Uploads are staged
    # in the destination directory, then published by an atomic rename.
    def valid_name(name):
        if not isinstance(name,str) or not name or len(name)>255 or name in ('.','..') or '/' in name or '\\' in name or '\x00' in name or name.startswith('.pinas-upload-'):raise ValueError('Invalid file name')
        return name
    def destination(relative):
        dest=safe_path(root,relative)
        if dest==root or dest.exists() or dest.is_symlink():raise ValueError('Destination already exists')
        if not dest.parent.is_dir():raise ValueError('Destination folder does not exist')
        return dest
    if action in ('rename','move','copy'):
        if target==root or not target.exists():raise ValueError('Invalid source')
        if action=='rename':
            dest=destination('/'.join(filter(None,[relative.rsplit('/',1)[0] if '/' in relative else '',valid_name(q.get('name'))])))
        else:
            dest=destination(q.get('dest',''))
        if target.is_dir() and (dest==target or target in dest.parents):raise ValueError('Cannot place folder inside itself')
        if action=='copy':
            import shutil
            if target.is_dir():
                # Reject links anywhere in the tree and cap total copy size.
                total=0
                for directory,dirs,files in os.walk(target,followlinks=False):
                    for name in dirs+files:
                        node=pathlib.Path(directory)/name
                        if node.is_symlink():raise ValueError('Symbolic links cannot be copied')
                        if node.is_file():total+=node.stat().st_size
                        if total>8*1024**3:raise ValueError('Folder copy exceeds 8 GiB safety limit')
                shutil.copytree(target,dest,symlinks=False)
            elif target.is_file():
                with target.open('rb') as src, dest.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            else:raise ValueError('Unsupported file type')
        else:
            # Same-share only; atomic rename prevents partial moves.
            if target.is_file():
                os.link(target,dest,follow_symlinks=False);target.unlink()
            else:target.rename(dest)
        print('{"ok":true}');return
    if action=='upload_start':
        name=valid_name(q.get('name'))
        if not target.is_dir():raise ValueError('Not a folder')
        destination('/'.join(filter(None,[relative,name])))
        size=q.get('size')
        if not isinstance(size,int) or size<0 or size>100*1024**3:raise ValueError('Invalid upload size')
        import secrets
        token=secrets.token_hex(20)
        staging=target/('.pinas-upload-'+token)
        fd=os.open(staging,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        meta=target/('.pinas-upload-'+token+'.json')
        fd=os.open(meta,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'name':name,'size':size,'path':relative},f)
        print(json.dumps({'token':token}));return
    if action in ('upload_chunk','upload_finish','upload_cancel'):
        token=q.get('token','')
        if not isinstance(token,str) or not re.fullmatch('[0-9a-f]{40}',token):raise ValueError('Invalid transfer token')
        stage=target/('.pinas-upload-'+token)
        meta=target/('.pinas-upload-'+token+'.json')
        if stage.is_symlink() or meta.is_symlink() or not stage.is_file() or not meta.is_file():raise ValueError('Unknown transfer')
        details=json.loads(meta.read_text());name=valid_name(details['name']);size=details['size']
        if details.get('path')!=relative:raise ValueError('Transfer location mismatch')
        if action=='upload_cancel':stage.unlink();meta.unlink();print('{"ok":true}');return
        if action=='upload_chunk':
            content=q.get('content','');offset=q.get('offset')
            if not isinstance(content,str) or len(content)>700000 or not isinstance(offset,int):raise ValueError('Invalid chunk')
            payload=base64.b64decode(content,validate=True)
            if len(payload)>512*1024 or offset!=stage.stat().st_size or offset+len(payload)>size:raise ValueError('Chunk offset or size mismatch')
            with stage.open('ab') as f:f.write(payload)
            print(json.dumps({'offset':offset+len(payload)}));return
        if stage.stat().st_size!=size:raise ValueError('Upload incomplete')
        dest=destination('/'.join(filter(None,[relative,name])))
        # Hard-link is no-clobber and atomic on the same filesystem.
        os.link(stage,dest,follow_symlinks=False);stage.unlink();meta.unlink()
        print('{"ok":true}');return
    if action=='download_chunk':
        offset=q.get('offset');size=q.get('size')
        if not isinstance(offset,int) or offset<0 or not isinstance(size,int) or size<1 or size>512*1024:raise ValueError('Invalid download range')
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode):raise ValueError('Not a regular file')
        total=target.stat().st_size
        with target.open('rb') as f:f.seek(offset);chunk=f.read(size)
        print(json.dumps({'content':base64.b64encode(chunk).decode(),'total':total}));return
    if action=='list':
        if not target.is_dir():raise ValueError('Not a folder')
        entries=[]
        for child in sorted(target.iterdir(),key=lambda x:x.name.casefold()):
            if child.is_symlink() or child.name.startswith('.pinas-upload-'):continue
            try:st=child.stat()
            except OSError:continue
            if stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode):entries.append({'name':child.name,'dir':stat.S_ISDIR(st.st_mode),'size':st.st_size})
            if len(entries)>=1000:break
        print(json.dumps({'entries':entries}));return
    if action=='mkdir':
        name=q.get('name','');dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..'):raise ValueError('Invalid folder name')
        dest.mkdir(mode=0o770);print('{"ok":true}');return
    if action=='delete':
        if target==root:raise ValueError('Cannot delete share root')
        if target.is_dir():target.rmdir()
        elif target.is_file():target.unlink()
        else:raise ValueError('Not a regular file or empty folder')
        print('{"ok":true}');return
    if action=='download':
        if not target.is_file() or not stat.S_ISREG(target.stat().st_mode) or target.stat().st_size>3*1024*1024:raise ValueError('Only files up to 3 MB supported in this test build')
        with target.open('rb') as f:content=base64.b64encode(f.read()).decode()
        print(json.dumps({'content':content}));return
    if action=='upload':
        name=q.get('name','');content=q.get('content','')
        if not isinstance(name,str) or not name or '/' in name or name in ('.','..') or not isinstance(content,str) or len(content)>4*1024*1024+16:raise ValueError('Invalid upload')
        dest=safe_path(root,'/'.join(filter(None,[relative,name])))
        if not target.is_dir():raise ValueError('Not a directory')
        payload=base64.b64decode(content,validate=True)
        if len(payload)>3*1024*1024:raise ValueError('Upload exceeds 3 MB')
        fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o660)
        with os.fdopen(fd,'wb') as f:f.write(payload)
        print('{"ok":true}');return
    raise ValueError('Unsupported action')
if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
"""

APT_INDEX_HELPER = r"""#!/usr/bin/env python3
import os,subprocess,sys
from pathlib import Path
ALLOWED={'off':None,'daily':'*-*-* 01:00:00','weekly':'Fri *-*-* 01:00:00','monthly':'*-*-28 01:00:00'}
def run(cmd,timeout=30):
    p=subprocess.run(cmd,timeout=timeout,check=False)
    if p.returncode:sys.exit(p.returncode)
def main():
    if os.geteuid()!=0:sys.exit('Root access required')
    args=sys.argv[1:]
    if len(args)==2 and args[0]=='schedule' and args[1] in ALLOWED:
        schedule=args[1];calendar=ALLOWED[schedule]
        timer=Path('/etc/systemd/system/pinas-auto-updates.timer')
        if calendar:
            timer.write_text('[Unit]\nDescription=PiNAS automatic OS updates\n[Timer]\nOnCalendar='+calendar+'\nPersistent=true\nUnit=pinas-auto-updates.service\n[Install]\nWantedBy=timers.target\n')
        run(['systemctl','daemon-reload'])
        if calendar:
            run(['systemctl','enable','--now','pinas-auto-updates.timer'])
            run(['systemctl','restart','pinas-auto-updates.timer'])
        else:
            run(['systemctl','disable','--now','pinas-auto-updates.timer']) if timer.exists() else None
            timer.unlink(missing_ok=True)
            run(['systemctl','daemon-reload'])
        marker=Path('/var/lib/pinas/update-schedule');marker.write_text(schedule+'\n');os.chmod(marker,0o644)
        return
    if args==['automatic']:
        # Only the systemd oneshot invokes this command, not the web service account.
        run(['/usr/bin/apt-get','update'],210)
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
        return
    if args==['upgrade']:
        run(['/usr/bin/apt-get','upgrade','-y','--no-remove','-o','Dpkg::Options::=--force-confold'],3300)
    elif args==['refresh']:
        run(['/usr/bin/apt-get','update'],210)
    else:sys.exit('Unsupported operation')
if __name__=='__main__':main()
"""

NAS_STORAGE_HELPER='#!/usr/bin/env python3\n"""PiNAS RC13 restricted, non-destructive storage adoption helper."""\nimport json,os,pathlib,re,subprocess,sys,uuid\nfrom pathlib import Path\n\ndef run(*args,timeout=15):\n    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)\n    if p.returncode:raise ValueError((p.stderr or \'Storage command failed\').strip()[-500:])\n    return p.stdout.strip()\n\ndef main():\n    if os.geteuid()!=0 or sys.argv[1:]!=[\'adopt\']:raise ValueError(\'Unsupported storage operation\')\n    data=json.loads(sys.stdin.read(4096));device=data.get(\'device\')\n    if not isinstance(device,str) or not re.fullmatch(r\'/dev/[A-Za-z0-9_./-]{1,90}\',device) or \'..\' in device:raise ValueError(\'Invalid device\')\n    path=Path(device)\n    if not path.is_block_device():raise ValueError(\'Device is not a block device\')\n    # The privileged helper independently identifies eligible physical disks.\n    roots=json.loads(run(\'lsblk\',\'-J\',\'-b\',\'-o\',\'NAME,PATH,TYPE,FSTYPE,UUID,MOUNTPOINTS,RO,PKNAME\')).get(\'blockdevices\',[])\n    bypath={};byname={};parents={}\n    def walk(node,parent=None):\n        name=node.get(\'name\');bypath[node.get(\'path\')]=node;byname[name]=node\n        if parent:parents[name]=parent\n        for child in node.get(\'children\') or []:walk(child,name)\n    for root in roots:walk(root)\n    node=bypath.get(str(path.resolve())) or bypath.get(device)\n    if not node or node.get(\'type\') not in (\'part\',\'disk\') or node.get(\'ro\'):raise ValueError(\'Not an eligible writable disk or partition\')\n    def root_for(n):\n        seen=set()\n        while n.get(\'name\') in parents:\n            if n[\'name\'] in seen:raise ValueError(\'Invalid device topology\')\n            seen.add(n[\'name\']);n=byname[parents[n[\'name\']]]\n        return n\n    disk=root_for(node)\n    if disk.get(\'type\')!=\'disk\' or disk.get(\'ro\') or str(disk.get(\'name\',\'\')).startswith((\'loop\',\'zram\',\'ram\',\'nbd\',\'sr\',\'fd\')):raise ValueError(\'Unsupported backing device\')\n    # Reject any physical disk carrying the root or boot filesystems.\n    protected={\'/\',\'/boot\',\'/boot/firmware\',\'/boot/efi\'}\n    def contains_system(n):\n        if any(m in protected for m in (n.get(\'mountpoints\') or []) if m):return True\n        return any(contains_system(c) for c in n.get(\'children\') or [])\n    if contains_system(disk):raise ValueError(\'Operating system storage is protected\')\n    for mount in protected:\n        src=run(\'findmnt\',\'-n\',\'-o\',\'SOURCE\',\'--target\',mount).split(\'[\',1)[0]\n        if src and src in bypath and root_for(bypath[src]).get(\'name\')==disk.get(\'name\'):\n            raise ValueError(\'Operating system storage is protected\')\n    fs=run(\'blkid\',\'-s\',\'TYPE\',\'-o\',\'value\',device)\n    uid=run(\'blkid\',\'-s\',\'UUID\',\'-o\',\'value\',device)\n    if fs not in (\'ext4\',\'xfs\',\'btrfs\') or not re.fullmatch(r\'[A-Za-z0-9-]{8,64}\',uid):raise ValueError(\'Supported filesystem and UUID required\')\n    # Reject RAID/LVM/crypto members and nested volume layouts.\n    if node.get(\'type\')==\'disk\' and node.get(\'children\'):raise ValueError(\'Choose a filesystem partition, not its parent disk\')\n    if node.get(\'children\'):raise ValueError(\'Complex volume layout not supported\')\n    mountpoints=[m for m in node.get(\'mountpoints\') or [] if m]\n    if len(mountpoints)>1:raise ValueError(\'Multiple mountpoints require manual review\')\n    if mountpoints and not str(mountpoints[0]).startswith(\'/mnt/pinas/\'):\n        raise ValueError(\'Filesystem is already mounted elsewhere; manage it manually to avoid disrupting applications\')\n    target=Path(\'/mnt/pinas\')/uid\n    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir())) and str(target) not in mountpoints):raise ValueError(\'Mount destination is not empty\')\n    fstab=Path(\'/etc/fstab\');original=fstab.read_text();entries=[line.split() for line in original.splitlines() if line.strip() and not line.lstrip().startswith(\'#\')]\n    for e in entries:\n        if len(e)>=2 and (e[0] in (device,\'UUID=\'+uid,\'/dev/disk/by-uuid/\'+uid) or e[1]==str(target)):\n            if e[0]==\'UUID=\'+uid and e[1]==str(target):\n                if str(target) not in mountpoints:run(\'mount\',str(target),timeout=25)\n                print(json.dumps({\'ok\':True,\'mount\':str(target),\'existing\':True}));return\n            raise ValueError(\'Existing fstab configuration requires manual review\')\n    target.parent.mkdir(parents=True,exist_ok=True)\n    target.mkdir(mode=0o755,exist_ok=True)\n    options=\'defaults,nofail,noatime,x-systemd.device-timeout=10s\'\n    entry=f\'UUID={uid} {target} {fs} {options} 0 {2 if fs=="ext4" else 0} # PiNAS managed\\\\n\'\n    entry=entry.replace(\'\\\\n\',\'\\n\')\n    backup=fstab.with_name(\'fstab.pinas-\'+uuid.uuid4().hex[:12]+\'.bak\')\n    backup.write_text(original);os.chmod(backup,0o600)\n    temp=fstab.with_name(\'.fstab.pinas-\'+uuid.uuid4().hex)\n    try:\n        temp.write_text(original.rstrip(\'\\n\')+\'\\n\'+entry);os.chmod(temp,0o644)\n        os.replace(temp,fstab)\n        run(\'systemctl\',\'daemon-reload\',timeout=15)\n        run(\'mount\',str(target),timeout=25)\n        actual=run(\'findmnt\',\'-n\',\'-o\',\'UUID\',\'--target\',str(target))\n        if actual!=uid:raise ValueError(\'Mounted filesystem UUID verification failed\')\n    except Exception:\n        fstab.write_text(original)\n        try:run(\'systemctl\',\'daemon-reload\')\n        except Exception:pass\n        raise\n    print(json.dumps({\'ok\':True,\'mount\':str(target)}))\nif __name__==\'__main__\':\n    try:main()\n    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)\n'

SMART_HEALTH_HELPER = """#!/usr/bin/env python3
import json,os,shutil,subprocess,sys
from pathlib import Path
def main():
    if os.geteuid()!=0 or len(sys.argv)!=1:
        raise ValueError('Unsupported operation')
    smartctl=shutil.which('smartctl')
    if not smartctl:
        print(json.dumps({'installed':False,'drives':[]}));return
    p=subprocess.run(['lsblk','-J','-b','-o','NAME,PATH,TYPE,MODEL,TRAN'],capture_output=True,text=True,timeout=8,check=True)
    drives=[]
    for disk in json.loads(p.stdout).get('blockdevices',[]):
        if disk.get('type')!='disk':continue
        device=disk.get('path','')
        if not isinstance(device,str) or not device.startswith('/dev/') or not Path(device).is_block_device():continue
        if disk.get('name','').startswith(('loop','zram','ram','nbd','sr','fd')):continue
        entry={'device':device,'model':disk.get('model') or disk.get('name'),'status':'Unavailable','temperature':None}
        try:
            result=subprocess.run([smartctl,'-j','-H','-A',device],capture_output=True,text=True,timeout=12)
            data=json.loads(result.stdout)
            health=data.get('smart_status',{}).get('passed')
            if health is True:entry['status']='Healthy'
            elif health is False:entry['status']='Warning'
            temp=data.get('temperature',{}).get('current')
            if isinstance(temp,(int,float)) and -20<=temp<=120:entry['temperature']=temp
            if data.get('smart_support',{}).get('available') is False:entry['status']='Unsupported'
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        drives.append(entry)
    print(json.dumps({'installed':True,'drives':drives}))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""

def install(args):
    if sys.platform!='linux' or os.geteuid()!=0:sys.exit('Install requires Linux and sudo/root.')
    if not Path('/etc/os-release').exists():sys.exit('Unsupported OS')
    osinfo=read('/etc/os-release')
    if 'debian' not in osinfo.lower() and 'raspbian' not in osinfo.lower():sys.exit('Requires Raspberry Pi OS / Debian family')
    if not args.skip_packages:
        print('Installing NAS dependencies (requires network and may take time)...',flush=True)
        subprocess.run(['apt-get','update'],check=True)
        subprocess.run(['apt-get','install','-y','samba','xfsprogs','btrfs-progs','mdadm','parted','util-linux','e2fsprogs','avahi-daemon','acl','openssl'],check=True)
    target=Path('/opt/pinas');target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(__file__).resolve(),target/'pinas.py');os.chmod(target/'pinas.py',0o755)
    if subprocess.run(['id','-u','pinas'],capture_output=True).returncode!=0:
        subprocess.run(['useradd','--system','--home-dir','/var/lib/pinas','--shell','/usr/sbin/nologin','pinas'],check=True)
    DATA.mkdir(parents=True,exist_ok=True);os.chmod(DATA,0o700)
    subprocess.run(['chown','pinas:pinas',str(DATA)],check=True)
    helper=Path('/usr/local/libexec/pinas-apply-hostname')
    helper.parent.mkdir(parents=True,exist_ok=True)
    helper.write_text(HOSTNAME_HELPER)
    os.chmod(helper,0o755)
    unit='''[Unit]\nDescription=Apply validated PiNAS device hostname\nAfter=systemd-hostnamed.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /usr/local/libexec/pinas-apply-hostname\nNoNewPrivileges=true\nProtectHome=true\nPrivateTmp=true\n'''
    Path('/etc/systemd/system/pinas-hostname.service').write_text(unit)
    path_unit='''[Unit]\nDescription=Apply PiNAS hostname when configuration changes\n[Path]\nPathChanged=/var/lib/pinas/config.json\nUnit=pinas-hostname.service\n[Install]\nWantedBy=multi-user.target\n'''
    Path('/etc/systemd/system/pinas-hostname.path').write_text(path_unit)
    user_helper=Path('/usr/local/libexec/pinas-nas-user')
    user_helper.write_text(NAS_USER_HELPER)
    os.chown(user_helper,0,0);os.chmod(user_helper,0o700)
    sudoers=Path('/etc/sudoers.d/pinas-nas-user')
    sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-user create *, /usr/local/libexec/pinas-nas-user password *, /usr/local/libexec/pinas-nas-user list\n')
    os.chown(sudoers,0,0);os.chmod(sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(sudoers)],capture_output=True).returncode:
        sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS sudoers configuration')
    share_helper=Path('/usr/local/libexec/pinas-nas-share')
    share_helper.write_text(NAS_SHARE_HELPER)
    os.chown(share_helper,0,0);os.chmod(share_helper,0o700)
    share_sudoers=Path('/etc/sudoers.d/pinas-nas-share')
    share_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-share list, /usr/local/libexec/pinas-nas-share create\n')
    os.chown(share_sudoers,0,0);os.chmod(share_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(share_sudoers)],capture_output=True).returncode:
        share_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS share sudoers configuration')
    files_helper=Path('/usr/local/libexec/pinas-nas-files')
    files_helper.write_text(NAS_FILES_HELPER)
    os.chown(files_helper,0,0);os.chmod(files_helper,0o700)
    files_sudoers=Path('/etc/sudoers.d/pinas-nas-files')
    files_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-files\n')
    os.chown(files_sudoers,0,0);os.chmod(files_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(files_sudoers)],capture_output=True).returncode:
        files_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS file helper sudoers configuration')
    storage_helper=Path('/usr/local/libexec/pinas-nas-storage')
    storage_helper.write_text(NAS_STORAGE_HELPER)
    os.chown(storage_helper,0,0);os.chmod(storage_helper,0o700)
    storage_sudoers=Path('/etc/sudoers.d/pinas-nas-storage')
    storage_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-storage adopt\n')
    os.chown(storage_sudoers,0,0);os.chmod(storage_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(storage_sudoers)],capture_output=True).returncode:
        storage_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS storage sudoers configuration')
    smart_helper=Path('/usr/local/libexec/pinas-smart-health')
    smart_helper.write_text(SMART_HEALTH_HELPER)
    os.chown(smart_helper,0,0);os.chmod(smart_helper,0o700)
    smart_sudoers=Path('/etc/sudoers.d/pinas-smart-health')
    smart_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-smart-health\n')
    os.chown(smart_sudoers,0,0);os.chmod(smart_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(smart_sudoers)],capture_output=True).returncode:
        smart_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS SMART sudoers configuration')
    apt_helper=Path('/usr/local/libexec/pinas-apt-index')
    apt_helper.write_text(APT_INDEX_HELPER)
    os.chown(apt_helper,0,0);os.chmod(apt_helper,0o700)
    apt_sudoers=Path('/etc/sudoers.d/pinas-apt-index')
    apt_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-apt-index refresh, /usr/local/libexec/pinas-apt-index upgrade, /usr/local/libexec/pinas-apt-index schedule off, /usr/local/libexec/pinas-apt-index schedule daily, /usr/local/libexec/pinas-apt-index schedule weekly, /usr/local/libexec/pinas-apt-index schedule monthly\n')
    os.chown(apt_sudoers,0,0);os.chmod(apt_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(apt_sudoers)],capture_output=True).returncode:
        apt_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS APT sudoers configuration')
    auto_service=Path('/etc/systemd/system/pinas-auto-updates.service')
    auto_service.write_text('[Unit]\nDescription=PiNAS scheduled OS updates\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=oneshot\nExecStart=/usr/local/libexec/pinas-apt-index automatic\nEnvironment=DEBIAN_FRONTEND=noninteractive\n')
    os.chown(auto_service,0,0);os.chmod(auto_service,0o644)
    # Existing schedule is preserved when upgrading PiNAS.
    # Generate a persistent per-install certificate; never replace it on upgrades.
    if not TLS_CERT.exists() or not TLS_KEY.exists():
        if TLS_CERT.exists() or TLS_KEY.exists():sys.exit('Incomplete TLS certificate pair; resolve manually before installing')
        if not shutil.which('openssl'):sys.exit('OpenSSL required for initial TLS certificate generation')
        hostname=load().get('hostname','pinas')
        if not valid_hostname(hostname):hostname='pinas'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','825',
            '-keyout',str(TLS_KEY),'-out',str(TLS_CERT),'-subj',f'/CN={hostname}.local',
            '-addext',f'subjectAltName=DNS:{hostname}.local,DNS:localhost,IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL)
    for f,mode in ((TLS_CERT,0o644),(TLS_KEY,0o600)):
        os.chown(f,0 if f==TLS_CERT else __import__('pwd').getpwnam('pinas').pw_uid,0 if f==TLS_CERT else __import__('grp').getgrnam('pinas').gr_gid)
        os.chmod(f,mode)
    bind_host='0.0.0.0' if args.lan else '127.0.0.1' 
    # TEMPORARY RC9.2: sudo inherits the service mount namespace. A root helper
    # cannot write /etc/passwd, /etc/group or Samba state with ProtectSystem=strict.
    # Replace sudo delegation with an independently sandboxed privileged service.
    service='''[Unit]\nDescription=PiNAS prototype web dashboard\nAfter=network.target\n[Service]\nType=simple\nUser=pinas\nGroup=pinas\nExecStart=/usr/bin/python3 /opt/pinas/pinas.py --serve --tls --host %s --port %d\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=false\nProtectSystem=false\nReadWritePaths=/var/lib/pinas\nPrivateTmp=true\n[Install]\nWantedBy=multi-user.target\n'''%(bind_host,args.port)
    Path('/etc/systemd/system/pinas.service').write_text(service)
    subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','enable','--now','pinas-hostname.path'],check=True);subprocess.run(['systemctl','start','pinas-hostname.service'],check=True);subprocess.run(['systemctl','enable','pinas.service'],check=True);subprocess.run(['systemctl','restart','pinas.service'],check=True)
    print(f'PiNAS installed. For localhost access: https://127.0.0.1:{args.port} (self-signed certificate)')
    if args.lan:print(f'LAN TLS MODE: open https://<PI-IP>:{args.port}. Certificate is self-signed; use the .local hostname for name matching. Do not expose this port to the internet.')
    else:print('Localhost-only mode; re-run installer with --lan to enable direct LAN access for testing.')

def main():
    ap=argparse.ArgumentParser(description='PiNAS Raspberry Pi NAS prototype')
    ap.add_argument('--lan',action='store_true',help='Bind HTTPS server to LAN interfaces');ap.add_argument('--install',action='store_true');ap.add_argument('--serve',action='store_true');ap.add_argument('--tls',action='store_true');ap.add_argument('--skip-packages',action='store_true');ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=8765)
    a=ap.parse_args()
    if a.install:install(a);return
    if a.serve:
        if a.host not in ('127.0.0.1','::1','0.0.0.0'):sys.exit('Unsupported bind address.')
        if a.host=='0.0.0.0' and not a.tls:sys.exit('LAN listening requires HTTPS (--tls)')
        server=ThreadingHTTPServer((a.host,a.port),Handler)
        if a.tls:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(TLS_CERT),str(TLS_KEY))
            server.socket=context.wrap_socket(server.socket,server_side=True)
        print('PiNAS running on %s://%s:%s'%('https' if a.tls else 'http',a.host,a.port))
        threading.Thread(target=cpu_sampler,daemon=True).start();server.serve_forever();return
    ap.print_help()
if __name__=='__main__':main()