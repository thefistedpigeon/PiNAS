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

NAS_UPDATER_HELPER = r"""#!/usr/bin/env python3
# Restricted privileged PiNAS updater: accepts package bytes only through stdin.
import ast,hashlib,json,os,pathlib,re,shutil,subprocess,sys,time
BASE=pathlib.Path('/opt/pinas/pinas.py')
ROOT=pathlib.Path('/var/lib/pinas-upgrader')
STAGE=ROOT/'staged.py'
STATUS=ROOT/'status.json'
BACKUP=pathlib.Path('/opt/pinas/pinas.py.previous')
MAX=2*1024*1024
def status(state,message):
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    tmp=ROOT/'status.tmp'
    tmp.write_text(json.dumps({'state':state,'message':message,'at':time.time()}))
    os.chmod(tmp,0o644);os.replace(tmp,STATUS)
def validate(data):
    if len(data)<1000 or len(data)>MAX:raise ValueError('Invalid PiNAS release size')
    text=data.decode('utf-8')
    tree=ast.parse(text,filename='pinas.py')
    if not text.startswith('#!/usr/bin/env python3') or 'PiNAS' not in text[:512]:
        raise ValueError('File is not a recognised PiNAS standalone release')
    versions=[n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in n.targets) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str)]
    if len(versions)!=1 or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9.]+)?',versions[0]):raise ValueError('Missing valid PiNAS version')
    if not any(isinstance(n,ast.FunctionDef) and n.name=='install' for n in tree.body):raise ValueError('Missing PiNAS installer')
    compile(tree,'pinas.py','exec')
    return versions[0]
def main():
    if os.geteuid()!=0:raise ValueError('Root required')
    if sys.argv[1:]==['status']:
        print(STATUS.read_text() if STATUS.exists() else json.dumps({'state':'idle','message':'No PiNAS update scheduled'}));return
    if sys.argv[1:]==['apply']:
        ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
        data=sys.stdin.buffer.read(MAX+1)
        version=validate(data)
        if STAGE.exists():raise ValueError('Another update is already staged')
        fd=os.open(STAGE,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
            status('scheduled','PiNAS '+version+' installation scheduled')
            p=subprocess.run(['/usr/bin/systemd-run','--unit=pinas-application-upgrade','--collect','/usr/bin/python3','/usr/local/libexec/pinas-upgrader','worker'],capture_output=True,text=True,timeout=15)
            if p.returncode:raise ValueError('Could not start updater: '+p.stderr.strip()[-500:])
        except Exception:
            STAGE.unlink(missing_ok=True);status('failed','Unable to schedule update');raise
        print(json.dumps({'scheduled':True,'version':version}))
    elif sys.argv[1:]==['worker']:
        if not STAGE.is_file():raise ValueError('No staged update')
        data=STAGE.read_bytes();version=validate(data)
        status('installing','Installing PiNAS '+version)
        if not BASE.is_file():raise ValueError('Installed PiNAS file missing')
        target=BASE.with_name('pinas.py.new')
        try:
            shutil.copy2(BASE,BACKUP)
            target.write_bytes(data);os.chmod(target,0o755)
            os.replace(target,BASE)
            extracted=subprocess.run(['/usr/bin/python3',str(BASE),'--extract-modules'],capture_output=True,text=True,timeout=30)
            if extracted.returncode:raise ValueError('Module extraction failed: '+extracted.stderr[-500:])
            result=subprocess.run(['/usr/bin/systemctl','restart','pinas.service'],capture_output=True,text=True,timeout=35)
            if result.returncode:raise ValueError('PiNAS restart failed: '+result.stderr[-500:])
            time.sleep(2)
            active=subprocess.run(['/usr/bin/systemctl','is-active','--quiet','pinas.service'],timeout=10)
            if active.returncode:raise ValueError('Updated PiNAS service is not running')
            status('succeeded','PiNAS '+version+' installed. Previous release retained as pinas.py.previous')
        except Exception as exc:
            if BACKUP.exists():
                shutil.copy2(BACKUP,BASE)
                # Restore the expanded module tree along with the launcher.
                subprocess.run(['/usr/bin/python3',str(BASE),'--extract-modules'],timeout=30,check=False)
                subprocess.run(['/usr/bin/systemctl','restart','pinas.service'],timeout=35,check=False)
            status('rolled_back','Update failed and previous application restored: '+str(exc)[:600])
            raise
        finally:
            target.unlink(missing_ok=True);STAGE.unlink(missing_ok=True)
    else:raise ValueError('Invalid updater command')
if __name__=='__main__':
    try:main()
    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)
"""

