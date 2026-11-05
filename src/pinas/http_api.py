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
        if path=='/api/pinas-build':self.json({'version':VERSION,'instance':SERVER_INSTANCE});return
        if path=='/api/pinas-upgrade':
            _,session=self.session()
            if not session or session.get('role')!='admin':self.json({'error':'Administrator access required'},403);return
            try:
                p=subprocess.run(['/usr/bin/sudo','-n','/usr/local/libexec/pinas-upgrader','status'],capture_output=True,text=True,timeout=8)
                if p.returncode:raise OSError('Unable to read update status')
                state=json.loads(p.stdout)
                self.json({'state':state.get('state','unknown'),'message':state.get('message','')});return
            except (OSError,ValueError):
                self.json({'state':'idle','message':'No PiNAS upgrade has been scheduled.'});return
        if path=='/api/background-image':
            cfg=load();image=cfg.get('login_background','')
            if not image:self.json({'error':'Not found'},404);return
            try:
                meta,b64=image.split(',',1);mime=meta[5:].split(';',1)[0];payload=base64.b64decode(b64,validate=True)
                if mime not in ('image/jpeg','image/png','image/webp'):raise ValueError()
            except (ValueError,IndexError):self.json({'error':'Invalid image'},500);return
            self.send_headers(kind=mime);self.wfile.write(payload);return
        if path=='/api/media-server':
            _,session=self.session()
            if not session or session.get('role')!='admin':
                self.json({'error':'Administrator access required'},403);return
            try:self.json(media_server_action('status'))
            except (RuntimeError,OSError,ValueError,subprocess.TimeoutExpired) as exc:
                self.json({'error':str(exc)},503)
            return
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
            with UPDATE_LOCK:result['status']=UPDATE_STATUS.copy();result['firmware']=UPDATE_STATUS.get('firmware',{'state':'unknown'})
            result['reboot_required']=Path('/var/run/reboot-required').exists()
            result['history']=update_history()
            result['history_months']=load().get('update_history_months',6)
            try:result['schedule']=(DATA/'update-schedule').read_text().strip()
            except OSError:result['schedule']='off'
            self.json(result);return
        if path!='/api/state':self.json({'error':'Not found'},404);return
        cfg=load();token,s=self.session();setup='admin_password' in cfg
        safe={k:cfg.get(k) for k in ('theme','font','cpu_interval','cpu_history','session_timeout')};safe['has_background']=bool(cfg.get('login_background'))
        if s and s.get('role')=='user':safe.update(cfg.get('user_preferences',{}).get(s['username'],{}))
        self.json({'setup':setup,'authenticated':bool(s),'csrf':s['csrf'] if s else '', 'role':s.get('role','admin') if s else '', 'username':s.get('username','') if s else '', 'display_name':((cfg.get('nas_display_names',{}).get(s.get('username',''),s.get('username','')) if isinstance(cfg.get('nas_display_names',{}),dict) else s.get('username','')) if s and s.get('role')=='user' else (admin_record(cfg,s.get('username','')) or {}).get('display_name','') if s else ''), 'settings':safe,'hardware':hardware() if s and s.get('role')=='admin' else {'model':read('/proc/device-tree/model').replace('\x00','') or 'Raspberry Pi','suggested_hostname':suggested_hostname(read('/proc/device-tree/model').replace('\x00',''))},'cpu':cpu_history(cfg.get('cpu_history',10)) if s and s.get('role')=='admin' else {}})
    def do_POST(self):
        path=urlparse(self.path).path
        if path not in ('/api/pinas-upgrade','/api/reset-smb','/api/edit-share','/api/delete-share','/api/migrate-share','/api/setup','/api/login','/api/logout','/api/settings','/api/background','/api/nas-users','/api/admin-users','/api/edit-user','/api/nas-shares','/api/storage','/api/disk-destructive','/api/files','/api/user-preferences','/api/updates','/api/media-server','/api/config-backup','/api/config-restore'):self.json({'error':'Not found'},404);return
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
        if path=='/api/logout':SESSIONS.pop(token,None);self.json({'ok':True},cookie='pinas_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'+('; Secure' if isinstance(self.connection,ssl.SSLSocket) else ''));return
        if path=='/api/user-preferences':
            if s.get('role')!='user':self.json({'error':'NAS user access required'},403);return
            theme,font,avatar=data.get('theme'),data.get('font'),data.get('avatar','')
            if theme not in ('light','dark') or type(font)!=int or font not in (10,12,14,16) or not isinstance(avatar,str) or len(avatar)>360000:
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
                    name=data.get('name',''),content=data.get('content',''),dest=data.get('dest',''),token=data.get('token',''),offset=data.get('offset',0),size=data.get('size',0),password=data.get('password') if action=='delete' else None)
                self.json(result)
            except (RuntimeError,OSError,ValueError,subprocess.TimeoutExpired) as exc:
                self.json({'error':str(exc)},400)
            return
        if s.get('role')!='admin':self.json({'error':'Administrator access required'},403);return
        if path=='/api/media-server':
            action=data.get('action')
            if action not in ('install','save','start','stop','restart','rescan','grant','rebuild','setup-library'):
                self.json({'error':'Unsupported media action'},400);return
            if action in ('install','save','grant','rebuild','setup-library'):
                password=data.get('admin_password')
                if not isinstance(password,str) or not verify(password,(admin_record(cfg,s['username']) or {}).get('password','')):
                    time.sleep(.35);self.json({'error':'Administrator password is incorrect'},403);return
            if action in ('save','grant','setup-library') and not isinstance(data.get('settings'),dict):
                self.json({'error':'Invalid media settings'},400);return
            try:self.json(media_server_action(action,data.get('settings') if action in ('save','grant','setup-library') else None))
            except (RuntimeError,OSError,ValueError,subprocess.TimeoutExpired) as exc:
                self.json({'error':str(exc)},503)
            return
        if path=='/api/updates':
            action=data.get('action')
            if action not in ('refresh','upgrade','schedule','reboot','history-retention','restart-auto'):self.json({'error':'Unsupported update action'},400);return
            if action=='history-retention':
                months=data.get('months')
                if type(months) is not int or months not in (6,12):
                    self.json({'error':'Select a 6- or 12-month history retention period.'},400);return
                try:
                    proc=subprocess.run(['/usr/bin/sudo','-n','/usr/local/libexec/pinas-apt-index','prune',str(months)],
                                        capture_output=True,text=True,timeout=20,check=False)
                    if proc.returncode:raise RuntimeError((proc.stderr or 'Unable to prune update history')[-350:])
                    with SETUP_LOCK:
                        latest=load();latest['update_history_months']=months;save(latest)
                except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:
                    self.json({'error':'Unable to update history retention: '+str(exc)},503);return
                self.json({'ok':True,'months':months});return
            if action=='restart-auto':
                unit=data.get('unit');pw=data.get('admin_password')
                if unit not in ('timer','service'):
                    self.json({'error':'Unsupported update unit'},400);return
                if not isinstance(pw,str) or not verify(pw,(admin_record(cfg,s['username']) or {}).get('password','')):
                    self.json({'error':'Administrator password is incorrect'},403);return
                health=service_health()
                item=next((i for i in health['services'] if i['unit']=='pinas-auto-updates.'+unit),None)
                if not item or item.get('restart_action')!=unit:
                    self.json({'error':'This update service is not in a recoverable warning state'},409);return
                try:
                    proc=subprocess.run(['/usr/bin/sudo','-n','/usr/local/libexec/pinas-apt-index','restart-auto',unit],
                                        capture_output=True,text=True,timeout=35,check=False)
                    if proc.returncode:raise RuntimeError((proc.stderr or 'Could not restart update unit')[-400:])
                except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:
                    self.json({'error':str(exc)},503);return
                self.json({'ok':True,'message':'PiNAS automatic update '+unit+' restart requested'});return
            if action=='reboot':
                # Require the current administrator's password in addition to session CSRF.
                confirmation=data.get('admin_password')
                if not isinstance(confirmation,str) or not verify(confirmation,(admin_record(cfg,s['username']) or {}).get('password','')):
                    self.json({'error':'Incorrect administrator password'},403);return
                with UPDATE_LOCK:
                    if UPDATE_STATUS['running']:
                        self.json({'error':'Wait for the current update operation to finish'},409);return
                if not Path('/run/reboot-required').exists():
                    self.json({'error':'No update requires a reboot'},409);return
                try:
                    proc=subprocess.run(
                        ['/usr/bin/sudo','-n','/usr/local/libexec/pinas-apt-index','reboot'],
                        capture_output=True,text=True,timeout=20,check=False,
                    )
                except (OSError,subprocess.TimeoutExpired) as exc:
                    self.json({'error':'Unable to schedule reboot: '+str(exc)},503);return
                if proc.returncode:
                    self.json({'error':(proc.stderr.strip() or 'Unable to schedule reboot')[-500:]},503);return
                self.json({'ok':True,'message':'System reboot scheduled'});return
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
            create_home=data.get('create_home_share',False);home_volume=data.get('home_volume');admin_password=data.get('admin_password')
            if type(create_home) is not bool:
                self.json({'error':'Invalid private home share option.'},400);return
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
            if create_home:
                if username.casefold() in ('global','homes','printers','print$','ipc$'):
                    self.json({'error':'Username conflicts with a reserved Samba share name.'},400);return
                if not re.fullmatch(r'[a-z][a-z0-9_-]{2,31}',username):
                    self.json({'error':'Private home share names must start with a letter.'},400);return
                if not isinstance(home_volume,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',home_volume) or '..' in home_volume:
                    self.json({'error':'Select a valid persistent disk for the private home share.'},400);return
                if not isinstance(admin_password,str) or not verify(admin_password,(admin_record(cfg,s['username']) or {}).get('password','')):
                    time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
                if any(username.casefold()==item.get('name','').casefold() for item in nas_share_list()):
                    self.json({'error':'A share with this username already exists.'},409);return
                available=[v for d in hardware_discovery().get('disks',[]) for v in d.get('volumes',[])
                           if v.get('path')==home_volume and v.get('persistent') and v.get('mounts')
                           and v.get('fs') in ('ext4','xfs','btrfs') and not v.get('read_only')]
                if len(available)!=1:
                    self.json({'error':'Selected home share disk is not mounted and persistent.'},409);return
            try:provision_nas_user(username,password)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:
                self.json({'error':str(exc)},503);return
            with SETUP_LOCK:
                latest=load();names=latest.get('nas_display_names',{})
                if not isinstance(names,dict):names={}
                names[username]=display_name;latest['nas_display_names']=names;save(latest)
            global DISCOVERY_AT
            DISCOVERY_AT=0
            if create_home:
                try:
                    # Share creation runs in the root-owned broker and applies
                    # Samba valid users + root-owned POSIX ACLs for this user.
                    create_nas_share(username,home_volume,{username:'rw'})
                except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:
                    self.json({'error':'NAS user was created, but the private home share failed: '+str(exc),
                               'created_user':True,'username':username},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'username':username,'display_name':display_name,
                       'created_home_share':create_home});return
        if path=='/api/storage':
            if s.get('role')!='admin':self.json({'error':'Administrator access required'},403);return
            device=data.get('device');password=data.get('admin_password')
            if not isinstance(device,str) or not re.fullmatch(r'/dev/[A-Za-z0-9_./-]{1,90}',device) or '..' in device:
                self.json({'error':'Invalid device'},400);return
            if not isinstance(password,str) or not verify(password,(admin_record(cfg,s['username']) or {}).get('password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect'},403);return
            # Re-read hardware immediately before an operation; do not trust a
            # cached browser disk list after USB disks are removed/reordered.
            try:
                fresh=hardware_discovery()
                matches=[v for d in fresh.get('disks',[]) if not d.get('read_only')
                         for v in d.get('volumes',[])
                         if v.get('path')==device and not v.get('read_only')
                         and v.get('fs') in ('ext4','xfs','btrfs') and v.get('uuid')]
                if len(matches)!=1:
                    self.json({'error':'Selected data filesystem is missing, read-only or ineligible. Refresh Storage and review the device before retrying.'},409);return
                result=configure_nas_mount(device)
            except (OSError,subprocess.TimeoutExpired,RuntimeError,ValueError) as exc:
                self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json(result);return
        if path=='/api/disk-destructive':
            # High-risk, administrator-only action; confirmation and password
            # are checked again here, not merely in the browser dialog.
            if s.get('role')!='admin':
                self.json({'error':'Administrator access required'},403);return
            action=data.get('action');device=data.get('device')
            filesystem=data.get('filesystem');confirmation=data.get('confirm')
            expected_size=data.get('expected_size')
            password=data.get('admin_password')
            if action not in ('wipe','format') or confirmation is not True:
                self.json({'error':'Explicit Yes confirmation is required'},400);return
            if not isinstance(device,str) or not re.fullmatch(r'/dev/[A-Za-z0-9_-]{1,64}',device):
                self.json({'error':'Select a valid whole disk'},400);return
            if type(expected_size) is not int or expected_size<128*1024*1024:
                self.json({'error':'Disk size is missing or invalid'},400);return
            if (action=='format' and filesystem not in ('ext4','xfs','btrfs')) or (action=='wipe' and filesystem is not None):
                self.json({'error':'Unsupported filesystem choice'},400);return
            if not isinstance(password,str) or not verify(password,(admin_record(cfg,s['username']) or {}).get('password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect'},403);return
            # Do not trust an old browser disk list or a stale discovery cache.
            # The privileged helper independently repeats stronger checks.
            try:
                fresh=hardware_discovery()
                targets=[d for d in fresh.get('disks',[]) if d.get('path')==device and
                         d.get('type')=='disk' and not d.get('read_only') and d.get('size')==expected_size]
                if len(targets)!=1:
                    self.json({'error':'Selected data drive changed or is protected. Refresh Storage.'},409);return
                payload=json.dumps({'device':device,'expected_size':expected_size,'filesystem':filesystem,
                                    'confirm':'WIPE' if action=='wipe' else 'FORMAT'})
                proc=subprocess.run(['/usr/bin/sudo','-n','/usr/local/libexec/pinas-disk-erase',action],
                                    input=payload,capture_output=True,text=True,timeout=970,check=False)
                if proc.returncode:
                    self.json({'error':(proc.stderr or 'Disk operation was refused')[-600:]},409);return
                result=json.loads(proc.stdout)
                if result.get('ok') is not True:
                    raise RuntimeError('Disk helper returned an invalid result')
                with DISCOVERY_LOCK:
                    DISCOVERY_CACHE.clear()
                self.json(result);return
            except (OSError,subprocess.TimeoutExpired,ValueError,RuntimeError) as exc:
                self.json({'error':'Disk operation failed: '+str(exc)[:500]},503);return
        if path=='/api/edit-share':
            name=data.get('name');new_name=data.get('new_name');access=data.get('access');password=data.get('admin_password');public=data.get('public',False);public_write=data.get('public_write',False)
            if not all(isinstance(x,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',x) for x in (name,new_name)):
                self.json({'error':'Invalid share name.'},400);return
            if type(public)!=bool or type(public_write)!=bool or (public_write and not public) or (public and access!={}):self.json({'error':'Invalid public sharing policy.'},400);return
            if not isinstance(access,dict) or (not public and not 1<=len(access)<=64) or (public and access!={}) or any(not isinstance(u,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):
                self.json({'error':'Assign at least one valid user access.'},400);return
            if not isinstance(password,str) or not verify(password,(admin_record(cfg,s['username']) or {}).get('password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not set(access).issubset({u['name'] for u in nas_user_list()}):
                self.json({'error':'Unknown NAS user.'},409);return
            if not any(isinstance(item,dict) and item.get('name')==name for item in nas_share_list()):
                self.json({'error':'Only PiNAS-managed shares can be edited.'},404);return
            try:edit_nas_share(name,new_name,access,public,public_write)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':new_name});return
        if path=='/api/migrate-share':
            if s.get('role')!='admin':self.json({'error':'Administrator access required'},403);return
            name=data.get('name');password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):
                self.json({'error':'Invalid share name.'},400);return
            if data.get('confirm')!='MOVE SHARE':
                self.json({'error':'Explicit migration confirmation required.'},400);return
            if not isinstance(password,str) or not verify(password,(admin_record(cfg,s['username']) or {}).get('password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            try:result=migrate_nas_share(name)
            except (OSError,subprocess.TimeoutExpired,RuntimeError,ValueError) as exc:
                self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json(result);return
        if path=='/api/delete-share':
            name=data.get('name');password=data.get('admin_password')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):
                self.json({'error':'Invalid share name.'},400);return
            if not isinstance(password,str) or not verify(password,(admin_record(cfg,s['username']) or {}).get('password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not any(isinstance(item,dict) and item.get('name')==name for item in nas_share_list()):
                self.json({'error':'Only PiNAS-managed shares can be removed.'},404);return
            try:delete_nas_share(name)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name,'files_preserved':True});return
        if path=='/api/nas-shares':
            name=data.get('name');volume=data.get('volume');access=data.get('access');admin_password=data.get('admin_password');public=data.get('public',False);public_write=data.get('public_write',False)
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):
                self.json({'error':'Choose a share name of 1–32 letters, digits, spaces, underscores or hyphens.'},400);return
            if not isinstance(volume,str) or not re.fullmatch(r'/dev/[a-zA-Z0-9_./-]{1,90}',volume) or '..' in volume:
                self.json({'error':'Invalid storage selection.'},400);return
            if type(public)!=bool or type(public_write)!=bool or (public_write and not public) or (public and access!={}):self.json({'error':'Invalid public sharing policy.'},400);return
            if not isinstance(access,dict) or (not public and not access) or len(access)>64 or any(not isinstance(k,str) or v not in ('ro','rw') for k,v in access.items()):
                self.json({'error':'Assign at least one user Read Only or Read & Write access.'},400);return
            if not isinstance(admin_password,str) or not verify(admin_password,(admin_record(cfg,s['username']) or {}).get('password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect.'},403);return
            if not storage_is_ready():self.json({'error':'A mounted, persistent data filesystem is required.'},409);return
            valid_users={u['name'] for u in nas_user_list()}
            if not set(access).issubset(valid_users):self.json({'error':'One or more users are not valid Samba accounts.'},409);return
            if any(name.casefold()==s.casefold() for s in discover().get('shares',[])):
                self.json({'error':'A share with this name already exists.'},409);return
            try:create_nas_share(name,volume,access,public,public_write)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:self.json({'error':str(exc)},503);return
            DISCOVERY_AT=0
            self.json({'ok':True,'share':name});return
        if path=='/api/reset-smb':
            password=data.get('admin_password')
            if s.get('role')!='admin':self.json({'error':'Administrator required'},403);return
            if data.get('confirm')!='RESET SMB CONFIGURATION':self.json({'error':'Explicit confirmation required'},400);return
            if not isinstance(password,str) or not verify(password,(admin_record(cfg,s['username']) or {}).get('password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect'},403);return
            try:
                result=subprocess.run(['sudo','-n','/usr/local/libexec/pinas-smb-reset','reset'],capture_output=True,text=True,timeout=45,check=True)
                self.json(json.loads(result.stdout));return
            except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired,ValueError) as exc:
                self.json({'error':'SMB reset failed: '+str(exc)},503);return
        if path=='/api/pinas-upgrade':
            if not s or s.get('role')!='admin':self.json({'error':'Administrator access required'},403);return
            pw=data.get('admin_password')
            if not isinstance(pw,str) or not verify(pw,(admin_record(cfg,s['username']) or {}).get('password','')):
                time.sleep(.35);self.json({'error':'Administrator password is incorrect'},403);return
            filename=data.get('filename','');digest=data.get('sha256','');encoded=data.get('package_b64','')
            if not isinstance(filename,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}\.py',filename) or not isinstance(encoded,str) or len(encoded)>3*1024*1024 or not isinstance(digest,str) or not re.fullmatch('[a-fA-F0-9]{64}',digest):
                self.json({'error':'Invalid PiNAS update package'},400);return
            try:
                raw=base64.b64decode(encoded,validate=True)
                if not raw or len(raw)>2*1024*1024 or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),digest.lower()):
                    self.json({'error':'Package size or SHA-256 mismatch'},400);return
                proc=subprocess.run(['/usr/bin/sudo','-n','/usr/local/libexec/pinas-upgrader','apply'],input=raw,capture_output=True,timeout=30)
                if proc.returncode:raise RuntimeError((proc.stderr.decode(errors='replace') or 'Update was rejected')[-1200:])
                self.json({'accepted':True,'message':'Update scheduled; service will restart'});return
            except (OSError,RuntimeError,subprocess.TimeoutExpired) as exc:
                self.json({'error':str(exc)},503);return
        if path in ('/api/config-backup','/api/config-restore'):
            confirmation=data.get('admin_password')
            if not isinstance(confirmation,str) or not verify(confirmation,(admin_record(cfg,s['username']) or {}).get('password','')):
                self.json({'error':'Incorrect administrator password'},403);return
            if path=='/api/config-backup':
                try:backup=configuration_backup(cfg)
                except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
                    self.json({'error':'Unable to collect backup inventory: '+str(exc)},503);return
                self.json({'backup':backup});return
            try:settings,names=validate_configuration_restore(data.get('backup'))
            except ValueError as exc:self.json({'error':str(exc)},400);return
            if data.get('confirm')!='RESTORE SETTINGS':
                self.json({'error':'Explicit restore confirmation required'},400);return
            with SETUP_LOCK:
                latest=load()
                latest.update(settings)
                latest['nas_display_names']=names
                save(latest)
            self.json({'ok':True,'settings':{key:latest.get(key) for key in BACKUP_SETTINGS},
                       'message':'Settings restored. Accounts, shares, disks and files were not modified.'});return
        if path=='/api/settings':
            theme,font=data.get('theme'),data.get('font')
            interval,history=data.get('cpu_interval',cfg.get('cpu_interval',5)),data.get('cpu_history',cfg.get('cpu_history',10))
            session_timeout=data.get('session_timeout',cfg.get('session_timeout',5))
            if theme not in ('light','dark') or type(font)!=int or font not in (10,12,14,16) or type(interval)!=int or interval not in (2,5,10) or type(history)!=int or history not in (10,15,30,60) or type(session_timeout)!=int or session_timeout not in (5,10,15,30,60):self.json({'error':'Invalid appearance settings'},400);return
            cfg.update(theme=theme,font=font,cpu_interval=interval,cpu_history=history,session_timeout=session_timeout)
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
        save(cfg);self.json({'settings':dict({k:cfg.get(k) for k in ('theme','font','cpu_interval','cpu_history','session_timeout')},has_background=bool(cfg.get('login_background')))} )

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

SMB_RESET_HELPER = r"""#!/usr/bin/env python3
# Root-only Samba reset. No filesystem/share data deletion.
import json, os, pathlib, shutil, subprocess, tempfile, time
SMB=pathlib.Path('/etc/samba/smb.conf')
SHARES=pathlib.Path('/etc/samba/pinas-shares.conf')
DB=pathlib.Path('/var/lib/pinas/shares.json')
MARKER=pathlib.Path('/etc/samba/.pinas-managed')
DEFAULT='''[global]
   workgroup = WORKGROUP
   server role = standalone server
   security = user
   map to guest = Bad User
   guest account = nobody
   server min protocol = SMB2
   load printers = no
   disable spoolss = yes
   include = /etc/samba/pinas-shares.conf
'''
def atomic(path,content):
    fd,tmp=tempfile.mkstemp(prefix='.pinas-',dir=str(path.parent))
    try:
        os.fchmod(fd,0o644)
        with os.fdopen(fd,'w') as out:
            out.write(content);out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def reset():
    if os.geteuid()!=0:raise RuntimeError('Root required')
    if not SMB.is_file():raise RuntimeError('Samba configuration missing')
    # Never replace an unmanaged installation automatically.
    previous=SMB.read_text()
    previous_shares=SHARES.read_text() if SHARES.exists() else None
    if previous_shares is not None:
        # Keep managed share definitions intact, including their permissions.
        shares=previous_shares
    else:
        shares=''
    stamp=time.strftime('%Y%m%d-%H%M%S',time.gmtime())
    backup=SMB.with_name('smb.conf.pinas-backup-'+stamp)
    if backup.exists():raise RuntimeError('Backup already exists')
    shutil.copy2(SMB,backup)
    if previous_shares is not None:
        share_backup=SHARES.with_name('pinas-shares.conf.pinas-backup-'+stamp)
        shutil.copy2(SHARES,share_backup)
    try:
        if not SHARES.exists():atomic(SHARES,shares)
        atomic(SMB,DEFAULT)
        subprocess.run(['/usr/bin/testparm','-s'],check=True,capture_output=True,text=True,timeout=20)
        subprocess.run(['/usr/bin/systemctl','reload','smbd'],check=True,capture_output=True,text=True,timeout=20)
        MARKER.write_text('managed by PiNAS\n')
        os.chmod(MARKER,0o600)
    except Exception:
        atomic(SMB,previous)
        if previous_shares is None:SHARES.unlink(missing_ok=True)
        try:subprocess.run(['/usr/bin/systemctl','reload','smbd'],check=False,timeout=20)
        except Exception:pass
        raise
    print(json.dumps({'ok':True,'backup':str(backup)}))
if __name__=='__main__':
    import sys
    if len(sys.argv)!=2 or sys.argv[1]!='reset':raise SystemExit('Usage: pinas-smb-reset reset')
    reset()
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

def guest_mapping(config):
    lines=config.splitlines(keepends=True)
    inside=False;seen=False;found=False
    for i,line in enumerate(lines):
        stripped=line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            inside=stripped.lower()=='[global]'
            if inside:found=True
        elif inside and re.match(r'^map\s+to\s+guest\s*=',stripped,re.I):
            if seen:raise ValueError('Duplicate Samba guest mapping')
            lines[i]='   map to guest = Bad User\n';seen=True
    if not found:raise ValueError('Samba [global] section missing')
    if not seen:
        for i,line in enumerate(lines):
            if line.strip().lower()=='[global]':
                lines.insert(i+1,'   map to guest = Bad User\n');break
    return ''.join(lines)

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
                if len(mount)==1:
                    base=pathlib.Path(mount[0]);name=item.get('name','')
                    # Historical records without an explicit folder remain on their
                    # original path; never implicitly move existing data.
                    legacy=base/'PiNAS Shares'/name
                    modern=base/'pinas-shares'/name
                    item['folder']=str(legacy if legacy.is_dir() else modern)
            except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired):pass
        print(json.dumps(items));return
    if len(sys.argv)==2 and sys.argv[1]=='migrate':
        # Explicit, non-destructive legacy-directory migration. No source
        # directory is removed or overwritten; os.rename is same-filesystem.
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('Request too large')
        request=json.loads(raw);name=request.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name):
            raise ValueError('Invalid share name')
        current=read_db()
        matches=[item for item in current if isinstance(item,dict) and item.get('name')==name]
        if len(matches)!=1:raise ValueError('Share is not managed by PiNAS')
        item=matches[0];mount=check_volume(item.get('volume'))
        legacy_root=mount/'PiNAS Shares'
        legacy=legacy_root/name
        target_root=mount/'pinas-shares'
        target=target_root/name
        if pathlib.Path(item.get('folder') or str(legacy))!=legacy:
            raise ValueError('Share is not using the legacy directory')
        if legacy_root.is_symlink() or legacy.is_symlink() or not legacy.is_dir() or legacy.stat().st_uid!=0:
            raise ValueError('Unsafe legacy share directory')
        if legacy.stat().st_dev!=mount.stat().st_dev:
            raise ValueError('Legacy share is on another filesystem')
        # Refuse moving a tree with nested mountpoints or bind mounts.
        mounted=run(['/usr/bin/findmnt','-rn','-o','TARGET']).stdout.splitlines()
        if any(point==str(legacy) or point.startswith(str(legacy)+'/') for point in mounted):
            raise ValueError('Share contains an active mountpoint; unmount it first')
        if target_root.is_symlink() or target.exists() or target.is_symlink():
            raise ValueError('Destination already exists or is unsafe')
        # No existing folder is adopted or overwritten.
        target_root.mkdir(mode=0o711,exist_ok=True)
        if target_root.stat().st_uid!=0 or (target_root.stat().st_mode & 0o022):
            raise ValueError('Unsafe new shares directory')
        oldconf=CONF.read_text();olddb=DB.read_text()
        section=re.compile(r'(?m)^\['+re.escape(name)+r'\][ \t]*\n(?:(?!\[).*(?:\n|$))*')
        sections=list(section.finditer(oldconf))
        if len(sections)!=1:raise ValueError('Managed Samba section missing or ambiguous')
        previous=sections[0].group(0)
        old_path='   path = '+str(legacy)+'\n'
        if previous.count(old_path)!=1:raise ValueError('Samba path differs from recorded legacy folder')
        newconf=oldconf[:sections[0].start()]+previous.replace(old_path,'   path = '+str(target)+'\n')+oldconf[sections[0].end():]
        moved=False
        try:
            legacy.rename(target);moved=True
            item['folder']=str(target)
            atomic(CONF,newconf,0o644)
            run(['/usr/bin/testparm','-s'])
            run(['/usr/bin/systemctl','reload','smbd'])
            atomic(DB,json.dumps(current,indent=2),0o600)
        except Exception:
            atomic(CONF,oldconf,0o644)
            atomic(DB,olddb,0o600)
            try:run(['/usr/bin/systemctl','reload','smbd'])
            except Exception:pass
            if moved:
                try:target.rename(legacy)
                except OSError:raise ValueError('Migration failed and manual folder recovery is required: '+str(target))
            raise
        print(json.dumps({'ok':True,'name':name,'folder':str(target)}));return
    if len(sys.argv)==2 and sys.argv[1]=='edit':
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('Request too large')
        request=json.loads(raw)
        name=request.get('name');new_name=request.get('new_name');access=request.get('access');public=request.get('public',False);public_write=request.get('public_write',False)
        valid=lambda n:isinstance(n,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',n)
        if not valid(name) or not valid(new_name):raise ValueError('Invalid share name')
        if type(public)!=bool or type(public_write)!=bool or (public_write and not public) or (public and access!={}):raise ValueError('Invalid public policy')
        if not isinstance(access,dict) or (not public and not 1<=len(access)<=64) or len(access)>64 or any(not isinstance(u,str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):raise ValueError('Invalid permissions')
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
        if folder.parent not in (mount/'PiNAS Shares',mount/'pinas-shares') or folder.is_symlink() or not folder.is_dir() or folder.stat().st_uid!=0:raise ValueError('Unsafe managed share folder')
        oldconf=CONF.read_text()
        old_smb=SMB.read_text()
        new_smb=guest_mapping(old_smb) if public else old_smb
        section=re.compile(r'(?m)^\['+re.escape(name)+r'\][ \t]*\n(?:(?!\[).*(?:\n|$))*')
        found=list(section.finditer(oldconf))
        if len(found)!=1:raise ValueError('Managed share section missing or ambiguous')
        if new_name!=name:
            existing=run(['/usr/bin/testparm','-s']).stdout
            if any(line.strip().casefold()=='['+new_name.casefold()+']' for line in existing.splitlines()):raise ValueError('Share name already used by Samba')
        rw=[u for u,p in access.items() if p=='rw']
        stanza='['+new_name+']\n   path = '+str(folder)+'\n   browseable = yes\n   read only = '+('no' if public and public_write else 'yes')+'\n'
        if public:
            stanza+='   guest ok = yes\n   guest only = yes\n   guest account = nobody\n   force user = nobody\n'
        else:
            stanza+='   guest ok = no\n   valid users = '+', '.join(access)+'\n'
            if rw:stanza+='   write list = '+', '.join(rw)+'\n'
        stanza+='   create mask = 0660\n   directory mask = 0770\n   follow symlinks = no\n   wide links = no\n'
        newconf=oldconf[:found[0].start()]+stanza+oldconf[found[0].end():]
        olddb=DB.read_text()
        oldacl=run(['/usr/bin/getfacl','-p',str(folder)]).stdout
        acl=['u::rwx','g::---','o::---','m::rwx']+(['u:nobody:'+('rwx' if public_write else 'r-x')] if public else [f'u:{u}:'+('rwx' if p=='rw' else 'r-x') for u,p in access.items()])
        try:
            run(['/usr/bin/setfacl','-b',str(folder)])
            run(['/usr/bin/setfacl','-k',str(folder)])
            run(['/usr/bin/setfacl','-m',','.join(acl+['d:'+entry for entry in acl]),str(folder)])
            if public:os.chmod(folder,0o777)
            else:os.chmod(folder,0o700)
            if new_smb!=old_smb:atomic(SMB,new_smb,0o644)
            atomic(CONF,newconf,0o644)
            run(['/usr/bin/testparm','-s'])
            run(['/usr/bin/systemctl','reload','smbd'])
            item['name']=new_name;item['access']=access;item['folder']=str(folder);item['public']=public;item['public_write']=public_write
            atomic(DB,json.dumps(current,indent=2),0o600)
        except Exception:
            atomic(CONF,oldconf,0o644)
            if new_smb!=old_smb:atomic(SMB,old_smb,0o644)
            atomic(DB,olddb,0o600)
            try:subprocess.run(['/usr/bin/setfacl','--restore=-'],input=oldacl,text=True,capture_output=True,timeout=15,check=True)
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
    name=request.get('name');access=request.get('access');device=request.get('volume');public=request.get('public',False);public_write=request.get('public_write',False)
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,31}',name) or name.lower() in ('global','homes','printers','print$','ipc$'):raise ValueError('Invalid share name')
    if type(public)!=bool or type(public_write)!=bool or (public_write and not public) or (public and access!={}):raise ValueError('Invalid public policy')
    if not isinstance(access,dict) or (not public and not 1<=len(access)<=64) or len(access)>64 or any(not re.fullmatch(r'[a-z_][a-z0-9_-]{2,31}',u) or perm not in ('ro','rw') for u,perm in access.items()):raise ValueError('Invalid access policy')
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
    root=mount/'pinas-shares'
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
    if public:amended=guest_mapping(amended)
    # Explicit per-user access; default deny for other NAS accounts.
    ro=[u for u,p in access.items() if p=='ro'];rw=[u for u,p in access.items() if p=='rw']
    stanza='\n['+name+']\n   path = '+str(folder)+'\n   browseable = yes\n   read only = '+('no' if public and public_write else 'yes')+'\n'
    if public:
        stanza+='   guest ok = yes\n   guest only = yes\n   guest account = nobody\n   force user = nobody\n'
    else:
        stanza+='   guest ok = no\n   valid users = '+', '.join(access)+'\n'
        if rw:stanza+='   write list = '+', '.join(rw)+'\n'
    stanza+='   create mask = 0660\n   directory mask = 0770\n   follow symlinks = no\n   wide links = no\n'
    oldconf=CONF.read_text() if CONF.exists() else ''
    if '['+name+']' in oldconf:raise ValueError('Duplicate managed share')
    folder.mkdir(mode=0o700)
    try:
        # Root-owned folder; Samba creates files as authenticated Unix users.
        os.chown(folder,0,0)
        os.chmod(folder,0o777 if public else 0o700)
        acl=['u::rwx','g::---','o::---','m::rwx']+(['u:nobody:'+('rwx' if public_write else 'r-x')] if public else [f'u:{u}:'+('rwx' if p=='rw' else 'r-x') for u,p in access.items()])
        default=['d:'+entry for entry in acl]
        run(['/usr/bin/setfacl','-m',','.join(acl+default),str(folder)])
        if public:os.chmod(folder,0o777)
        if amended!=original:atomic(SMB,amended,0o644)
        atomic(CONF,oldconf+stanza,0o644)
        run(['/usr/bin/testparm','-s'])
        run(['/usr/bin/systemctl','reload','smbd'])
        current.append({'name':name,'volume_label':mount.name,'volume':device,'folder':str(folder),'access':access,'public':public,'public_write':public_write})
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
    root=pathlib.Path(s.get('folder') or str(mount/'PiNAS Shares'/s['name']))
    if root.parent not in (mount/'PiNAS Shares',mount/'pinas-shares') or root.name!=s['name'] or root.is_symlink() or not root.is_dir():
        raise ValueError('Share folder unavailable')
    if root.parent.is_symlink():raise ValueError('Unsafe share root')
    relative=q.get('path','');target=safe_path(root,relative)
    writable=s['access'][user]=='rw'
    if action in ('mkdir','delete','rename','move','copy','upload','upload_start','upload_chunk','upload_finish','upload_cancel') and not writable:raise ValueError('Read-only share')
    if action=='delete':
        # Validate the current Samba password while still privileged; all actual
        # filesystem mutations below run with the user's restricted UID/GID.
        password=q.get('password')
        if not isinstance(password,str) or not 1<=len(password)<=256 or not hmac.compare_digest(md4(password.encode('utf-16le')),samba_hash(user)):
            raise ValueError('Current account password is incorrect')
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
        base_stat=os.lstat(target)
        if stat.S_ISLNK(base_stat.st_mode):raise ValueError('Symbolic links cannot be deleted via the web interface')
        if stat.S_ISREG(base_stat.st_mode):
            target.unlink()
        elif stat.S_ISDIR(base_stat.st_mode):
            # Full preflight: reject symlinks, filesystem boundaries and device nodes.
            folders=[];files=[];count=0
            for directory,dirs,names in os.walk(target,topdown=True,followlinks=False):
                folder=pathlib.Path(directory)
                details=os.lstat(folder)
                if not stat.S_ISDIR(details.st_mode) or details.st_dev!=base_stat.st_dev:
                    raise ValueError('Unsafe folder or mounted filesystem in deletion')
                folders.append(folder)
                for name in dirs+names:
                    node=folder/name;details=os.lstat(node)
                    if details.st_dev!=base_stat.st_dev or not (stat.S_ISDIR(details.st_mode) or stat.S_ISREG(details.st_mode)):
                        raise ValueError('Deletion cannot cross filesystems or contain symbolic links/special files')
                    count+=1
                    if count>10000:raise ValueError('Folder contains more than 10,000 items; use SMB for large deletions')
                    if stat.S_ISREG(details.st_mode):files.append(node)
            for node in files:node.unlink()
            for folder in reversed(folders):folder.rmdir()
        else:raise ValueError('Only regular files and folders can be deleted')
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
# Restricted APT and schedule helper, root-owned, no shell input.
import grp,json,os,re,sqlite3,subprocess,sys,tempfile,time
from pathlib import Path

ALLOWED={'off':None,'daily':'*-*-* 01:00:00','weekly':'Fri *-*-* 01:00:00','monthly':'*-*-28 01:00:00'}
DB_DIR=Path('/var/lib/pinas-update-history')
DB=DB_DIR/'updates.sqlite3'
CFG=Path('/var/lib/pinas/config.json')
UNITS={'timer':'pinas-auto-updates.timer','service':'pinas-auto-updates.service'}

def retention_months():
    try:
        value=json.loads(CFG.read_text()).get('update_history_months',6)
        return value if type(value) is int and value in (6,12) else 6
    except (OSError,ValueError,TypeError):
        return 6

def database():
    if DB_DIR.is_symlink() or (DB.exists() and DB.is_symlink()):
        raise ValueError('Update history storage cannot be a symlink')
    group=grp.getgrnam('pinas').gr_gid
    DB_DIR.mkdir(mode=0o750,exist_ok=True)
    if not DB_DIR.is_dir():raise ValueError('Invalid update history location')
    os.chown(DB_DIR,0,group);os.chmod(DB_DIR,0o750)
    connection=sqlite3.connect(str(DB),timeout=5)
    connection.execute('PRAGMA journal_mode=DELETE')
    connection.execute('PRAGMA busy_timeout=5000')
    connection.execute('PRAGMA auto_vacuum=INCREMENTAL')
    connection.execute('''CREATE TABLE IF NOT EXISTS update_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at INTEGER NOT NULL,
        completed_at INTEGER NOT NULL,
        source TEXT NOT NULL CHECK(source IN ('manual','automatic')),
        result TEXT NOT NULL CHECK(result IN ('success','failed')),
        packages TEXT NOT NULL,
        summary TEXT NOT NULL
    )''')
    os.chown(DB,0,group);os.chmod(DB,0o640)
    return connection

def prune(connection,months):
    connection.execute("DELETE FROM update_events WHERE started_at < CAST(strftime('%s','now',?) AS INTEGER)",('-'+str(months)+' months',))
    # Cap event count as a second bound in case scheduling is unusually frequent.
    connection.execute('DELETE FROM update_events WHERE id NOT IN (SELECT id FROM update_events ORDER BY id DESC LIMIT 2000)')
    connection.execute('PRAGMA incremental_vacuum(24)')

def record(source,result,started,packages,summary):
    try:
        with database() as db:
            db.execute('INSERT INTO update_events(started_at,completed_at,source,result,packages,summary) VALUES (?,?,?,?,?,?)',
                       (started,int(time.time()),source,result,json.dumps(sorted(packages)[:120]),summary[-800:]))
            prune(db,retention_months())
    except (sqlite3.Error,OSError,ValueError,KeyError) as exc:
        print('Warning: update history could not be saved: '+str(exc)[:150],file=sys.stderr)

def run(cmd,timeout=30):
    p=subprocess.run(cmd,timeout=timeout,check=False)
    if p.returncode:sys.exit(p.returncode)

def upgrade(source):
    started=int(time.time())
    packages=set()
    outcome='failed'
    code=1
    details='APT did not complete'
    try:
        with tempfile.TemporaryFile(mode='w+t',encoding='utf-8') as output:
            p=subprocess.run(['/usr/bin/apt-get','upgrade','-y','--no-remove',
                              '-o','Dpkg::Options::=--force-confold'],
                             stdout=output,stderr=subprocess.STDOUT,timeout=3300,check=False)
            code=p.returncode
            output.seek(0)
            tail=''
            for line in output:
                tail=(tail+line)[-1500:]
                match=re.match(r'^(?:Setting up|Unpacking) ([A-Za-z0-9.+:_-]+)',line)
                if match and len(packages)<120:packages.add(match.group(1))
            details=tail.strip()[-800:] or 'APT returned no output'
            print(tail[-1500:])
            outcome='success' if code==0 else 'failed'
    except (OSError,subprocess.TimeoutExpired) as exc:
        details='APT operation failed: '+str(exc)[:450]
        print(details,file=sys.stderr)
    record(source,outcome,started,packages,details)
    if code:sys.exit(code)

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
            if timer.exists():run(['systemctl','disable','--now','pinas-auto-updates.timer'])
            timer.unlink(missing_ok=True)
            run(['systemctl','daemon-reload'])
        marker=Path('/var/lib/pinas/update-schedule')
        marker.write_text(schedule+'\n');os.chmod(marker,0o644)
        return
    if len(args)==2 and args[0]=='prune' and args[1] in ('6','12'):
        with database() as db:prune(db,int(args[1]))
        return
    if len(args)==2 and args[0]=='restart-auto' and args[1] in UNITS:
        try:schedule=Path('/var/lib/pinas/update-schedule').read_text().strip()
        except OSError:schedule='off'
        if schedule not in ('daily','weekly','monthly'):
            sys.exit('Automatic updates are not enabled')
        unit=UNITS[args[1]]
        run(['systemctl','reset-failed',unit],15)
        if args[1]=='timer':
            run(['systemctl','enable','--now',unit],25)
            run(['systemctl','restart',unit],25)
        else:
            # One-shot services normally become inactive after success.
            # --no-block avoids holding the HTTP request during APT.
            run(['systemctl','start','--no-block',unit],20)
        return
    if args==['firmware-check']:
        import shutil
        checker=shutil.which('rpi-eeprom-update')
        if not checker:
            print('rpi-eeprom-update unavailable',file=sys.stderr);sys.exit(2)
        run([checker],40)
        return
    if args==['reboot']:
        if not Path('/run/reboot-required').is_file():
            sys.exit('No system reboot is required')
        if not Path('/usr/bin/systemd-run').is_file():
            sys.exit('systemd-run is unavailable')
        run(['/usr/bin/systemd-run','--quiet','--unit=pinas-update-reboot',
             '--on-active=10s','/usr/bin/systemctl','reboot'],15)
        return
    if args==['automatic']:
        started=int(time.time())
        try:
            run(['/usr/bin/apt-get','update'],210)
        except (SystemExit,OSError,subprocess.TimeoutExpired) as exc:
            record('automatic','failed',started,[], 'APT index refresh failed: '+str(exc))
            raise
        upgrade('automatic')
        return
    if args==['upgrade']:
        upgrade('manual')
    elif args==['refresh']:
        run(['/usr/bin/apt-get','update'],210)
    else:sys.exit('Unsupported operation')
if __name__=='__main__':main()
"""

