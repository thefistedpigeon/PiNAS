#!/usr/bin/env python3
"""PiNAS lightweight NAS management interface (stdlib only)."""
import ssl, re, argparse, base64, copy, hashlib, hmac, json, os, secrets, shutil, socket, sqlite3, subprocess, sys, time, threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs

VERSION='1.1.0'
# A fresh identifier per service process lets browsers detect an update restart,
# even when the application is updated without changing its version number.
SERVER_INSTANCE=secrets.token_hex(16)
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



# Long file and ACL operations run outside the HTTP request. Ownership is
# tied to the existing session ID, not a public result token.
JOB_LOCK=threading.Lock()
JOBS={}

def start_job(session_token,action,callback,*args):
    now=time.monotonic()
    with JOB_LOCK:
        for job_id,entry in list(JOBS.items()):
            if now-entry['created']>3600 and not entry['running']:
                JOBS.pop(job_id,None)
        if sum(entry['running'] for entry in JOBS.values())>=2:
            raise RuntimeError('Two long operations are already running')
        if any(entry['running'] and entry['owner']==session_token for entry in JOBS.values()):
            raise RuntimeError('An operation is already in progress for this session')
        job_id=secrets.token_urlsafe(18)
        JOBS[job_id]={'owner':session_token,'action':action,'created':now,
                      'running':True,'result':None,'error':None}
    def worker():
        try:
            result=callback(*args)
            with JOB_LOCK:JOBS[job_id].update(result=result,running=False)
        except Exception as exc:
            with JOB_LOCK:JOBS[job_id].update(error=str(exc)[:700],running=False)
    threading.Thread(target=worker,daemon=True,name='pinas-job-'+action).start()
    return {'job_id':job_id,'running':True}

def get_job(session_token,job_id):
    with JOB_LOCK:
        entry=JOBS.get(job_id)
        if not entry or entry['owner']!=session_token:
            raise ValueError('Job not found')
        return {'running':entry['running'],'result':entry['result'],'error':entry['error'],
                'action':entry['action']}

UPDATE_LOCK=threading.Lock()
UPDATE_STATUS={'running':False,'operation':'','last_check':None,'last_install':None,'error':'','output':''}

UPDATE_HISTORY_DB=Path('/var/lib/pinas-update-history/updates.sqlite3')

def update_history(limit=40):
    """Read a short recent history, with no write transactions or periodic polling."""
    if not UPDATE_HISTORY_DB.is_file():return []
    try:
        with sqlite3.connect(UPDATE_HISTORY_DB.as_uri()+'?mode=ro',uri=True,timeout=2) as db:
            db.row_factory=sqlite3.Row
            rows=db.execute('SELECT started_at,completed_at,source,result,packages,summary FROM update_events ORDER BY id DESC LIMIT ?', (min(max(int(limit),1),100),)).fetchall()
        history=[]
        for row in rows:
            try:packages=json.loads(row['packages'])
            except (ValueError,TypeError):packages=[]
            history.append({'started_at':row['started_at'],'completed_at':row['completed_at'],
                            'source':row['source'],'result':row['result'],
                            'packages':packages if isinstance(packages,list) else [],
                            'summary':row['summary']})
        return history
    except (sqlite3.Error,OSError,ValueError):
        return []

APT_CACHE_LOCK=threading.Lock()
APT_CACHE_AT=0.0
APT_CACHE_RESULT={'packages':[]}

def package_updates(force=False):
    """Read APT metadata at most once a minute; never invoke APT while upgrading."""
    global APT_CACHE_AT,APT_CACHE_RESULT
    with APT_CACHE_LOCK:
        with UPDATE_LOCK:
            running=UPDATE_STATUS['running']
        if running or (APT_CACHE_AT>0 and not force and time.monotonic()-APT_CACHE_AT<60):
            return copy.deepcopy(APT_CACHE_RESULT)
        result=_package_updates_uncached()
        APT_CACHE_RESULT=result
        APT_CACHE_AT=time.monotonic()
        return copy.deepcopy(result)

def _package_updates_uncached():
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

def firmware_check():
    """Read-only Raspberry Pi EEPROM status; no flashing or boot changes."""
    if not Path('/proc/device-tree/model').exists():
        return {'state':'unsupported','message':'Not Raspberry Pi hardware'}
    try:
        proc=subprocess.run(['/usr/bin/sudo','-n','/usr/local/libexec/pinas-apt-index','firmware-check'],capture_output=True,text=True,timeout=45,check=False)
        if proc.returncode:
            message=(proc.stderr or proc.stdout or '').strip()
            return {'state':'error','message':message[-500:]}
        output=proc.stdout
        if 'BOOTLOADER: update available' in output or '*** UPDATE AVAILABLE ***' in output:
            return {'state':'available','message':output[-800:]}
        if 'BOOTLOADER: up to date' in output or 'BOOTLOADER: up-to-date' in output:
            return {'state':'current','message':output[-800:]}
        return {'state':'unknown','message':output[-800:]}
    except (OSError,subprocess.TimeoutExpired) as exc:
        return {'state':'error','message':str(exc)}

def update_worker(operation='refresh'):
    try:
        proc=subprocess.run(['/usr/bin/sudo','-n','/usr/local/libexec/pinas-apt-index',operation],capture_output=True,text=True,timeout=3600 if operation=='upgrade' else 240,check=False)
        firmware=firmware_check() if operation=='refresh' else None
        with APT_CACHE_LOCK:
            global APT_CACHE_AT
            APT_CACHE_AT=0
        with UPDATE_LOCK:
            if firmware is not None:UPDATE_STATUS['firmware']=firmware
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

# A lightweight mtime/inode cache avoids reparsing multi-megabyte inline avatars
# and backgrounds on each /api/state poll and CPU sample.
CONFIG_LOCK=threading.RLock()
CONFIG_CACHE_KEY=None
CONFIG_CACHE_VALUE=None

def load():
    global CONFIG_CACHE_KEY,CONFIG_CACHE_VALUE
    with CONFIG_LOCK:
        try:
            st=CONFIG.stat()
            key=(st.st_dev,st.st_ino,st.st_mtime_ns,st.st_size)
            if key!=CONFIG_CACHE_KEY:
                CONFIG_CACHE_VALUE=json.loads(CONFIG.read_text())
                CONFIG_CACHE_KEY=key
            return copy.deepcopy(CONFIG_CACHE_VALUE)
        except (OSError,ValueError,TypeError):
            return {'theme':'light','font':12,'login_background':''}

def save(config):
    global CONFIG_CACHE_KEY,CONFIG_CACHE_VALUE
    with CONFIG_LOCK:
        DATA.mkdir(parents=True,exist_ok=True)
        tmp=DATA/('config-'+secrets.token_hex(4)+'.tmp')
        try:
            tmp.write_text(json.dumps(config,indent=2))
            os.chmod(tmp,0o600);os.replace(tmp,CONFIG)
        finally:
            tmp.unlink(missing_ok=True)
        st=CONFIG.stat()
        CONFIG_CACHE_KEY=(st.st_dev,st.st_ino,st.st_mtime_ns,st.st_size)
        CONFIG_CACHE_VALUE=copy.deepcopy(config)

# Only non-secret, device-local settings are portable. Linux/Samba users, credentials,
# mounts and data volumes must be recovered separately, never modified by this import.
BACKUP_SETTINGS={
    'theme':('light','dark'),
    'font':(10,12,14,16),
    'cpu_interval':(2,5,10),
    'cpu_history':(10,15,30,60),
    'session_timeout':(5,10,15,30,60),
}

def configuration_backup(cfg):
    """Create a non-secret recovery manifest without touching NAS storage."""
    settings={key:cfg[key] for key in BACKUP_SETTINGS
              if key in cfg and type(cfg[key]) is type(BACKUP_SETTINGS[key][0])
              and cfg[key] in BACKUP_SETTINGS[key]}
    names=cfg.get('nas_display_names',{})
    if not isinstance(names,dict):names={}
    names={key:value for key,value in names.items()
           if isinstance(key,str) and re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',key)
           and valid_display_name(value)}
    return {
        'format':'pinas-configuration-v1',
        'version':VERSION,
        'created_at':int(time.time()),
        'settings':settings,
        'display_names':names,
        'accounts':[u['name'] for u in nas_user_list() if isinstance(u,dict) and isinstance(u.get('name'),str)],
        'shares':nas_share_list(),
        'restore_scope':'settings-and-display-names-only',
        'warning':'User accounts, SMB credentials, shares, mounts, RAID, and files are inventory only; restore them separately.',
    }

def validate_configuration_restore(backup):
    """Strictly validate a settings-only backup before changing any configuration."""
    if not isinstance(backup,dict) or backup.get('format')!='pinas-configuration-v1' or backup.get('restore_scope')!='settings-and-display-names-only':
        raise ValueError('Unsupported PiNAS configuration backup format')
    if not isinstance(backup.get('settings'),dict) or not isinstance(backup.get('display_names'),dict):
        raise ValueError('Configuration settings or display names are missing')
    settings=backup['settings']
    if any(key not in BACKUP_SETTINGS or type(value) is not type(BACKUP_SETTINGS[key][0])
           or value not in BACKUP_SETTINGS[key] for key,value in settings.items()):
        raise ValueError('Backup contains invalid configuration settings')
    names=backup['display_names']
    if len(names)>128 or any(not isinstance(key,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',key)
                             or not valid_display_name(value) for key,value in names.items()):
        raise ValueError('Backup contains invalid account display names')
    # Do not trust file-supplied credentials, paths, passwords or shares.
    return settings.copy(),names.copy()

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

def privileged_command(helper, *args, payload=None, timeout=35):
    """Run an installed PiNAS root broker with explicit input and timeout."""
    if not re.fullmatch(r'pinas-[a-z-]+', helper):
        raise ValueError('Invalid privileged helper')
    return subprocess.run(
        ['sudo','-n','/usr/local/libexec/'+helper,*args],
        input=payload, capture_output=True, text=True, timeout=timeout, check=False,
    )

def change_nas_password(username,password):
    proc=privileged_command('pinas-nas-user','password',username,payload=password+'\n')
    if proc.returncode:raise RuntimeError('Unable to update Samba password: '+(proc.stderr.strip() or 'Privileged helper failed')[-400:])

def nas_user_list():
    """Query Samba passdb via the narrowly scoped root helper (passdb is root-only)."""
    try:
        p=privileged_command('pinas-nas-user','list',timeout=8)
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
    proc=privileged_command('pinas-nas-user','create',username,payload=password+'\n')
    if proc.returncode:
        raise RuntimeError('NAS user provisioning failed: '+(proc.stderr.strip() or 'The privileged helper returned an error.')[-700:])
    return True

def nas_share_list():
    try:
        proc=privileged_command('pinas-nas-share','list',timeout=8)
        if proc.returncode==0:
            result=json.loads(proc.stdout)
            if isinstance(result,list):return result
    except (OSError,ValueError,subprocess.TimeoutExpired):pass
    return []

def create_nas_share(name,volume,access,public=False,public_write=False):
    payload=json.dumps({'name':name,'volume':volume,'access':access,'public':public,'public_write':public_write})
    proc=privileged_command('pinas-nas-share','create',payload=payload)
    if proc.returncode:
        raise RuntimeError('Share creation failed: '+(proc.stderr.strip() or 'The privileged helper returned an error.')[-850:])

def edit_nas_share(name,new_name,access,public=False,public_write=False):
    proc=privileged_command('pinas-nas-share','edit',payload=json.dumps({'name':name,'new_name':new_name,'access':access,'public':public,'public_write':public_write}))
    if proc.returncode:
        raise RuntimeError('Share edit failed: '+(proc.stderr.strip() or 'The privileged helper returned an error.')[-850:])

def migrate_nas_share(name):
    """Explicitly migrate a PiNAS-managed legacy share without overwriting data."""
    proc=privileged_command('pinas-nas-share','migrate',payload=json.dumps({'name':name}),timeout=60)
    if proc.returncode:
        raise RuntimeError('Share migration failed: '+(proc.stderr.strip() or 'Privileged migration helper failed')[-850:])
    return json.loads(proc.stdout)

def delete_nas_share(name):
    proc=privileged_command('pinas-nas-share','delete',payload=json.dumps({'name':name}))
    if proc.returncode:
        raise RuntimeError('Share removal failed: '+(proc.stderr.strip() or 'The privileged helper returned an error.')[-850:])

def configure_nas_mount(device):
    """Non-destructive UUID-based adoption via independently validated root broker."""
    proc=privileged_command('pinas-nas-storage','adopt',payload=json.dumps({'device':device}),timeout=40)
    if proc.returncode:
        raise RuntimeError((proc.stderr.strip() or 'Storage configuration failed')[-800:])
    return json.loads(proc.stdout)

def nas_file_action(action, username, share='', path='', **extra):
    payload={'action':action,'username':username,'share':share,'path':path,**extra}
    proc=privileged_command('pinas-nas-files',payload=json.dumps(payload),timeout=720 if action in ('copy','delete') else 120)
    if proc.returncode:
        raise RuntimeError((proc.stderr.strip() or 'File operation failed')[-500:])
    return json.loads(proc.stdout)

def nas_authenticate(username,password):
    proc=privileged_command('pinas-nas-files',payload=json.dumps({'action':'authenticate','username':username,'password':password}),timeout=12)
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

def managed_storage_health():
    """Read-only health of PiNAS-created UUID mounts, without touching devices.

    Only entries explicitly tagged by PiNAS and under /mnt/pinas are reported.
    Do not interpret unrelated administrator-managed fstab records as PiNAS drives.
    """
    health=[]
    try:
        lines=Path('/etc/fstab').read_text().splitlines()
    except OSError:
        return health
    for line in lines:
        if '# PiNAS managed' not in line or line.lstrip().startswith('#'):
            continue
        cols=line.split('#',1)[0].split()
        if len(cols)<4:
            continue
        source,target,fs=cols[:3]
        if not re.fullmatch(r'UUID=[A-Za-z0-9-]{8,64}',source):
            continue
        if target!='/mnt/pinas/'+source[5:] or fs not in ('ext4','xfs','btrfs'):
            continue
        uuid=source[5:]
        device=Path('/dev/disk/by-uuid')/uuid
        try:
            if not device.exists():
                state='missing'
            elif not os.path.ismount(target):
                state='unmounted'
            else:
                # A directory mounted with the wrong filesystem is not healthy.
                actual=command('findmnt','-n','-o','UUID','--mountpoint',target,timeout=2).strip()
                state='mounted' if actual==uuid else 'mismatch'
        except OSError:
            state='unmounted'
        health.append({'uuid':uuid,'mount':target,'filesystem':fs,'state':state})
    return health

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
                if node is not root and (node.get('type') in ('part','crypt','lvm','raid','md') or str(node.get('type') or '').startswith('raid')):
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
    """On-demand systemd health; an inactive completed oneshot is normal."""
    schedule=read(DATA/'update-schedule')
    auto_enabled=schedule in ('daily','weekly','monthly')
    names=(('Samba file sharing','smbd.service'),('Samba name service','nmbd.service'),
           ('SSH access','ssh.service'),('Network manager','NetworkManager.service'),
           ('Automatic updates timer','pinas-auto-updates.timer'),
           ('Automatic updates service','pinas-auto-updates.service'))
    results=[]
    for label,unit in names:
        item={'name':label,'unit':unit,'state':'unknown','detail':'Status unavailable'}
        if unit.startswith('pinas-auto-updates.') and not auto_enabled:
            item.update(state='inactive',detail='Automatic updates disabled in schedule')
            results.append(item);continue
        try:
            p=subprocess.run(['systemctl','show',unit,
                '--property=LoadState,ActiveState,SubState,UnitFileState,Result',
                '--no-pager'],capture_output=True,text=True,timeout=4,check=False)
            if p.returncode:raise OSError('systemctl unavailable')
            fields=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
            loaded=fields.get('LoadState','')
            active=fields.get('ActiveState','unknown')
            result=fields.get('Result','')
            enabled=fields.get('UnitFileState','')
            if loaded=='not-found':
                item.update(state='warning' if auto_enabled and unit.startswith('pinas-auto-') else 'not-installed',
                            detail='Unit not installed')
            elif loaded in ('masked','error','bad-setting'):
                item.update(state='warning',detail='Unit '+loaded)
            elif active=='failed' or (unit.endswith('.service') and unit.startswith('pinas-auto-') and result not in ('','success') and active!='activating'):
                item.update(state='warning',detail='Last run failed ('+str(result or active)[:48]+')')
            elif unit=='pinas-auto-updates.service':
                if active=='activating':item.update(state='pending',detail='Scheduled update running')
                elif active in ('inactive','active'):item.update(state='healthy',detail='Last run succeeded or waiting for next schedule')
                else:item.update(state='unknown',detail='State: '+str(active)[:32])
            elif active=='active':
                item.update(state='healthy',detail='Active ('+fields.get('SubState','running')+')')
            elif active=='inactive':
                item.update(state='warning' if (enabled=='enabled' or unit=='pinas-auto-updates.timer') else 'inactive',
                            detail='Inactive'+(' (enabled)' if enabled=='enabled' else ''))
            elif active=='activating':
                item.update(state='pending',detail='Starting')
            else:
                item.update(state='unknown',detail='State: '+str(active)[:32])
            if (unit.startswith('pinas-auto-updates.') and auto_enabled and
                item['state']=='warning' and loaded not in ('not-found','masked')):
                item['restart_action']='timer' if unit.endswith('.timer') else 'service'
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
    base['managed_storage_health']=managed_storage_health()
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
    base.update(temperature=temp,throttle=command('vcgencmd','get_throttled',timeout=2),memory_total=mem.get('MemTotal',0),memory_used=max(0,mem.get('MemTotal',0)-mem.get('MemAvailable',0)),version=VERSION)
    model=base['model'];ram=base['memory_total'];profile='performance' if 'Raspberry Pi 5' in model and ram>=3*1024**3 else 'enhanced' if 'Raspberry Pi 4' in model and ram>=2*1024**3 else 'essential'
    base['profile']=profile
    base['capabilities']={'samba':True,'raid':True,'curated_apps':profile!='essential','jellyfin':profile=='performance'}
    return base

