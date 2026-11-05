"""PiNAS on-demand, per-volume disk file-type accounting.

A dedicated root helper is needed because managed SMB shares can be mode 0700.
Do not poll, open file contents, follow symlinks or descend into other mounts.
"""
import os as _storage_os
import pathlib as _storage_pathlib
import stat as _storage_stat
import subprocess as _storage_subprocess
import threading as _storage_threading
import time as _storage_time
import json as _storage_json

VIDEO_EXT={'.avi','.mp4','.m4v','.mkv','.mov','.wmv','.flv','.webm','.mpeg','.mpg','.m2ts','.mts','.ts','.3gp','.vob','.ogv','.divx'}
PICTURE_EXT={'.bmp','.jpg','.jpeg','.jpe','.png','.svg','.gif','.webp','.tif','.tiff','.heic','.heif','.avif','.raw','.cr2','.nef','.dng','.ico'}
MUSIC_EXT={'.wav','.aac','.mp3','.flac','.m4a','.ogg','.oga','.opus','.wma','.aiff','.aif','.alac','.ape','.mid','.midi'}

_STORAGE_LOCK=_storage_threading.Lock()
_STORAGE_STATE={}
_STORAGE_INTERVAL=1800

def media_category(filename):
    ext=_storage_pathlib.Path(filename).suffix.casefold()
    if ext in VIDEO_EXT:return 'video'
    if ext in PICTURE_EXT:return 'pictures'
    if ext in MUSIC_EXT:return 'music'
    return 'other'

def scan_media_volume(folder):
    """Metadata-only classification, kept testable without root or NAS hardware."""
    base=_storage_pathlib.Path(folder)
    stat=base.lstat()
    if not _storage_stat.S_ISDIR(stat.st_mode) or base.is_symlink():
        raise ValueError('Not an ordinary data directory')
    counts={'video':0,'pictures':0,'music':0,'other':0}
    files=0
    stack=[str(base)]
    while stack:
        directory=stack.pop()
        try:
            with _storage_os.scandir(directory) as items:
                for entry in items:
                    try:info=entry.stat(follow_symlinks=False)
                    except OSError:continue
                    if info.st_dev!=stat.st_dev:continue
                    if _storage_stat.S_ISDIR(info.st_mode):
                        stack.append(entry.path)
                    elif _storage_stat.S_ISREG(info.st_mode):
                        counts[media_category(entry.name)]+=max(0,info.st_blocks*512)
                        files+=1
                        if files%2048==0:_storage_time.sleep(.012)
        except PermissionError as exc:
            raise PermissionError('Cannot access '+directory) from exc
    return counts,files

def _valid_media_mount(mount):
    """Require a currently configured, physically mounted PiNAS data volume."""
    if not isinstance(mount,str) or not mount.startswith('/mnt/pinas/') or mount.count('/')!=3:
        raise ValueError('Select a configured mounted PiNAS data volume')
    if mount not in {
        point
        for disk in hardware_discovery().get('disks',[])
        for volume in disk.get('volumes',[])
        if volume.get('persistent')
        for point in volume.get('mounts',[])
    }:
        raise ValueError('Disk must be configured and mounted in Storage')
    return mount

def _media_scan_worker(mount):
    try:
        result=_storage_subprocess.run(
            ['/usr/bin/sudo','-n','/usr/local/libexec/pinas-file-types','scan',mount],
            capture_output=True,text=True,timeout=1800,check=False)
        if result.returncode:
            raise RuntimeError((result.stderr or 'File type scan failed').strip()[-350:])
        data=_storage_json.loads(result.stdout)
        if not isinstance(data.get('categories'),dict):
            raise ValueError('Invalid file-type scan output')
        with _STORAGE_LOCK:
            _STORAGE_STATE[mount]={'running':False,'scanned_at':int(_storage_time.time()),
                'categories':data['categories'],'files':data.get('files',0),
                'skipped_dirs':data.get('skipped_dirs',0),'error':None}
    except (_storage_subprocess.TimeoutExpired,OSError,ValueError,RuntimeError) as exc:
        with _STORAGE_LOCK:
            previous=_STORAGE_STATE.get(mount,{}).copy()
            previous.update(running=False,error=str(exc)[:350])
            _STORAGE_STATE[mount]=previous

def media_breakdown_status(mount=None,refresh=False):
    if mount is not None:_valid_media_mount(mount)
    with _STORAGE_LOCK:
        if refresh:
            if mount is None:raise ValueError('Select a disk before scanning')
            if any(state.get('running') for state in _STORAGE_STATE.values()):
                raise ValueError('Another disk file-type scan is already running')
            previous=_STORAGE_STATE.get(mount,{}).copy()
            previous.update(running=True,error=None)
            _STORAGE_STATE[mount]=previous
            _storage_threading.Thread(target=_media_scan_worker,args=(mount,),daemon=True,
                                      name='pinas-file-types').start()
        if mount is None:
            return {'disks':{key:value.copy() for key,value in _STORAGE_STATE.items()}}
        return {'mount':mount,**_STORAGE_STATE.get(mount,{'running':False,'scanned_at':None})}

# Embedded as a separate, restricted root-only executable at installation.
# This does not import the unprivileged HTTP application or its credentials.
FILE_TYPE_SCAN_HELPER = r"""#!/usr/bin/env python3
import json,os,pathlib,re,stat,subprocess,sys,time

VIDEO={'.avi','.mp4','.m4v','.mkv','.mov','.wmv','.flv','.webm','.mpeg','.mpg','.m2ts','.mts','.ts','.3gp','.vob','.ogv','.divx'}
PICTURES={'.bmp','.jpg','.jpeg','.jpe','.png','.svg','.gif','.webp','.tif','.tiff','.heic','.heif','.avif','.raw','.cr2','.nef','.dng','.ico'}
MUSIC={'.wav','.aac','.mp3','.flac','.m4a','.ogg','.oga','.opus','.wma','.aiff','.alac','.ape','.mid','.midi'}

def validate_mount(value):
    if not isinstance(value,str) or not re.fullmatch(r'/mnt/pinas/[A-Za-z0-9][A-Za-z0-9._-]{0,127}',value):
        raise ValueError('Invalid PiNAS data-volume path')
    folder=pathlib.Path(value)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('Volume is unavailable or is a symlink')
    result=subprocess.run(['/usr/bin/findmnt','-rn','-o','TARGET','--mountpoint',value],
                          capture_output=True,text=True,timeout=10)
    if result.returncode or result.stdout.strip()!=value:
        raise ValueError('Volume is not an active mountpoint')
    # Additional safeguard against a manually-created directory under /mnt/pinas.
    # Only physical, mounted filesystem paths are accepted.
    return folder

def scan(volume):
    root=validate_mount(volume)
    top=root.lstat()
    if not stat.S_ISDIR(top.st_mode):raise ValueError('Not an ordinary data volume')
    counters={'video':0,'pictures':0,'music':0,'other':0}
    stack=[str(root)]
    files=0
    skipped=0
    while stack:
        directory=stack.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:meta=entry.stat(follow_symlinks=False)
                    except OSError:skipped+=1;continue
                    if meta.st_dev!=top.st_dev:continue
                    if stat.S_ISDIR(meta.st_mode):
                        stack.append(entry.path)
                    elif stat.S_ISREG(meta.st_mode):
                        suffix=pathlib.Path(entry.name).suffix.casefold()
                        kind='video' if suffix in VIDEO else 'pictures' if suffix in PICTURES else 'music' if suffix in MUSIC else 'other'
                        counters[kind]+=max(0,int(meta.st_blocks)*512)
                        files+=1
                        if files%1024==0:time.sleep(.01)
        except OSError:
            skipped+=1
    print(json.dumps({'categories':counters,'files':files,'skipped_dirs':skipped}))

if __name__=='__main__':
    try:
        if os.geteuid()!=0 or len(sys.argv)!=3 or sys.argv[1]!='scan':
            raise ValueError('Unsupported operation')
        scan(sys.argv[2])
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
"""
