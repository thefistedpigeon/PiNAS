"""Low-impact, on-demand classification of space on PiNAS data volumes.

Never reads file contents, follows symlinks, scans system mounts or runs a
continuous watcher. Cached results are shared by all Overview requests.
"""
import os as _storage_os
import pathlib as _storage_pathlib
import stat as _storage_stat
import threading as _storage_threading
import time as _storage_time

VIDEO_EXT={'.avi','.mp4','.m4v','.mkv','.mov','.wmv','.flv','.webm','.mpeg','.mpg','.m2ts','.mts','.ts','.3gp','.vob','.ogv','.divx'}
PICTURE_EXT={'.bmp','.jpg','.jpeg','.jpe','.png','.svg','.gif','.webp','.tif','.tiff','.heic','.heif','.avif','.raw','.cr2','.nef','.dng','.ico'}
MUSIC_EXT={'.wav','.aac','.mp3','.flac','.m4a','.ogg','.oga','.opus','.wma','.aiff','.aif','.alac','.ape','.mid','.midi'}
_STORAGE_LOCK=_storage_threading.Lock()
_STORAGE_STATE={'running':False,'scanned_at':None,'disks':{},'error':None,'scanned_files':0}
_STORAGE_INTERVAL=1800  # no automatic repeated full scan from 10-second Overview polling

def media_category(filename):
    extension=_storage_pathlib.Path(filename).suffix.casefold()
    if extension in VIDEO_EXT:return 'video'
    if extension in PICTURE_EXT:return 'pictures'
    if extension in MUSIC_EXT:return 'music'
    return 'other'

def scan_media_volume(folder):
    """Count allocated blocks only; no content opens or symlink traversal."""
    base=_storage_pathlib.Path(folder)
    rootstat=base.lstat()
    if not _storage_stat.S_ISDIR(rootstat.st_mode) or base.is_symlink():
        raise ValueError('Not a physical data directory')
    total={'video':0,'pictures':0,'music':0,'other':0}
    files=0
    stack=[str(base)]
    while stack:
        directory=stack.pop()
        with _storage_os.scandir(directory) as items:
            for entry in items:
                try:st=entry.stat(follow_symlinks=False)
                except (OSError,PermissionError):continue
                if st.st_dev!=rootstat.st_dev:continue
                if _storage_stat.S_ISDIR(st.st_mode):
                    stack.append(entry.path)
                elif _storage_stat.S_ISREG(st.st_mode):
                    total[media_category(entry.name)]+=max(0,int(st.st_blocks)*512)
                    files+=1
                    if files%2048==0:_storage_time.sleep(.012)
    return total,files

def _media_volumes():
    """Discover only PiNAS-owned persistent mountpoints, never an OS root."""
    items=[]
    known=set()
    for disk in hardware_discovery().get('disks',[]):
        for volume in disk.get('volumes',[]):
            if not volume.get('persistent') or volume.get('read_only'):continue
            for mount in volume.get('mounts',[]):
                if not isinstance(mount,str) or not mount.startswith('/mnt/pinas/') or mount.count('/')!=3:
                    continue
                if mount in known:continue
                known.add(mount)
                try:
                    p=_storage_pathlib.Path(mount)
                    if p.is_symlink() or not p.is_dir():continue
                    if not _storage_os.path.ismount(mount):continue
                except OSError:continue
                items.append(mount)
    return items

def _scan_media_background():
    try:
        result={}
        file_count=0
        for mount in _media_volumes():
            try:
                values,count=scan_media_volume(mount)
                result[mount]={'categories':values,'files':count,'scanned_at':int(_storage_time.time())}
                file_count+=count
            except (OSError,ValueError) as exc:
                result[mount]={'error':str(exc)[:180]}
        with _STORAGE_LOCK:
            _STORAGE_STATE.update(disks=result,scanned_at=int(_storage_time.time()),
                                  scanned_files=file_count,error=None,running=False)
    except Exception as exc:
        with _STORAGE_LOCK:
            _STORAGE_STATE.update(error=str(exc)[:180],running=False)

def media_breakdown_status(refresh=False):
    """Start an on-demand background scan, returning the last cached result."""
    with _STORAGE_LOCK:
        expired=not _STORAGE_STATE['scanned_at'] or _storage_time.time()-_STORAGE_STATE['scanned_at']>=_STORAGE_INTERVAL
        if not _STORAGE_STATE['running'] and (refresh or expired):
            _STORAGE_STATE['running']=True
            _storage_threading.Thread(target=_scan_media_background,daemon=True,name='pinas-storage-breakdown').start()
        return {
            'running':_STORAGE_STATE['running'],
            'scanned_at':_STORAGE_STATE['scanned_at'],
            'disks':dict(_STORAGE_STATE['disks']),
            'scanned_files':_STORAGE_STATE['scanned_files'],
            'error':_STORAGE_STATE['error'],
        }
