def expand_modules(target):
    """Write embedded modules to a versioned directory without changing NAS data."""
    if os.geteuid()!=0:raise PermissionError('Root required')
    directory=target/'modules'
    directory.mkdir(mode=0o755,parents=True,exist_ok=True)
    for name,source in PINAS_SOURCE_PARTS.items():
        if not re.fullmatch(r'[a-z_]+\.py',name):raise ValueError('Invalid module name')
        destination=directory/name
        tmp=directory/(name+'.new')
        tmp.write_text(source,encoding='utf-8')
        os.chmod(tmp,0o644)
        os.replace(tmp,destination)

def install(args):
    if sys.platform!='linux' or os.geteuid()!=0:sys.exit('Install requires Linux and sudo/root.')
    if not Path('/etc/os-release').exists():sys.exit('Unsupported OS')
    osinfo=read('/etc/os-release')
    if 'debian' not in osinfo.lower() and 'raspbian' not in osinfo.lower():sys.exit('Requires Raspberry Pi OS / Debian family')
    if not args.skip_packages:
        print('Installing NAS dependencies (requires network and may take time)...',flush=True)
        apt_env=os.environ.copy()
        apt_env.update({'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','DEBIAN_FRONTEND':'noninteractive','DEBIAN_PRIORITY':'critical'})
        subprocess.run(['apt-get','update'],check=True,env=apt_env)
        subprocess.run(['apt-get','install','-y','samba','xfsprogs','btrfs-progs','mdadm','parted','util-linux','e2fsprogs','avahi-daemon','acl','openssl'],check=True,env=apt_env)
    # Only take ownership of Samba automatically on a genuinely new PiNAS installation.
    first_install=not Path('/opt/pinas/pinas.py').exists()
    target=Path('/opt/pinas');target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(__file__).resolve(),target/'pinas.py');os.chmod(target/'pinas.py',0o755)
    expand_modules(target)
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
    reset_helper=Path('/usr/local/libexec/pinas-smb-reset')
    reset_helper.write_text(SMB_RESET_HELPER)
    os.chown(reset_helper,0,0);os.chmod(reset_helper,0o700)
    reset_sudoers=Path('/etc/sudoers.d/pinas-smb-reset')
    reset_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-smb-reset reset\n')
    os.chown(reset_sudoers,0,0);os.chmod(reset_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(reset_sudoers)],capture_output=True).returncode:
        reset_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS SMB reset sudoers configuration')
    if first_install and Path('/etc/samba/smb.conf').is_file():
        subprocess.run(['/usr/bin/python3',str(reset_helper),'reset'],check=True,timeout=45)
    share_helper=Path('/usr/local/libexec/pinas-nas-share')
    share_helper.write_text(NAS_SHARE_HELPER)
    os.chown(share_helper,0,0);os.chmod(share_helper,0o700)
    share_sudoers=Path('/etc/sudoers.d/pinas-nas-share')
    share_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-nas-share list, /usr/local/libexec/pinas-nas-share create, /usr/local/libexec/pinas-nas-share delete, /usr/local/libexec/pinas-nas-share edit\n')
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
    updater_helper=Path('/usr/local/libexec/pinas-upgrader')
    updater_helper.write_text(NAS_UPDATER_HELPER)
    os.chown(updater_helper,0,0);os.chmod(updater_helper,0o700)
    updater_sudoers=Path('/etc/sudoers.d/pinas-upgrader')
    updater_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-upgrader apply, /usr/local/libexec/pinas-upgrader status\n')
    os.chown(updater_sudoers,0,0);os.chmod(updater_sudoers,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(updater_sudoers)],capture_output=True).returncode:
        updater_sudoers.unlink(missing_ok=True);sys.exit('Invalid PiNAS updater sudoers configuration')
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
    apt_sudoers.write_text('pinas ALL=(root) NOPASSWD: /usr/local/libexec/pinas-apt-index refresh, /usr/local/libexec/pinas-apt-index upgrade, /usr/local/libexec/pinas-apt-index firmware-check, /usr/local/libexec/pinas-apt-index schedule off, /usr/local/libexec/pinas-apt-index schedule daily, /usr/local/libexec/pinas-apt-index schedule weekly, /usr/local/libexec/pinas-apt-index schedule monthly\n')
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
    ap.add_argument('--extract-modules',action='store_true',help=argparse.SUPPRESS)
    a=ap.parse_args()
    if a.extract_modules:
        if os.geteuid()!=0:sys.exit('Root required')
        expand_modules(Path('/opt/pinas'));return
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
