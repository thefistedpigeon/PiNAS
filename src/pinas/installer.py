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
    # Browser-based upgrades invoke --extract-modules as root. Synchronise the
    # narrowly scoped APT helper and sudo rule too, otherwise scheduled updates
    # would continue to use the older, non-logging helper after a GUI upgrade.
    # Keep destructive operations isolated from the non-destructive adoption helper.
    # Existing browser-driven upgrades update the root helper and its sudoers rule.
    install_privileged_helper('pinas-disk-erase',NAS_DISK_ERASE_HELPER,["wipe","format"])
    if Path('/usr/local/libexec/pinas-apt-index').is_file():
        install_privileged_helper('pinas-apt-index',APT_INDEX_HELPER,
          ["refresh","upgrade","firmware-check","schedule off","schedule daily",
           "schedule weekly","schedule monthly","reboot","prune 6","prune 12",
           "restart-auto timer","restart-auto service"])

def install_privileged_helper(name, source, allowed_commands):
    """Install a root-owned helper with a validated, narrowly scoped sudoers rule."""
    if not re.fullmatch(r'pinas-[a-z-]+', name):
        raise ValueError('Invalid privileged helper name')
    helper=Path('/usr/local/libexec')/name
    helper.write_text(source)
    os.chown(helper,0,0)
    os.chmod(helper,0o700)
    rule=Path('/etc/sudoers.d')/name
    commands=', '.join('/usr/local/libexec/'+name+(' '+arg if arg else '') for arg in allowed_commands)
    rule.write_text('pinas ALL=(root) NOPASSWD: '+commands+'\n')
    os.chown(rule,0,0)
    os.chmod(rule,0o440)
    if shutil.which('visudo') and subprocess.run(['visudo','-cf',str(rule)],capture_output=True).returncode:
        rule.unlink(missing_ok=True)
        raise RuntimeError('Invalid PiNAS sudoers configuration for '+name)
    return helper

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
    existing=target/'pinas.py'
    previous=target/'pinas.py.previous'
    staged=target/'pinas.py.new'
    # Never clobber a running installation before validating and preserving its
    # previous code. This does not touch /var/lib/pinas or any NAS data volumes.
    source=Path(__file__).resolve()
    source_bytes=source.read_bytes()
    if len(source_bytes)>2*1024*1024:raise RuntimeError('PiNAS installer exceeds supported size')
    compile(source_bytes,str(source),'exec')
    if existing.exists():
        shutil.copy2(existing,previous)
        os.chmod(previous,0o600)
    try:
        staged.write_bytes(source_bytes)
        os.chmod(staged,0o755)
        os.replace(staged,existing)
        expand_modules(target)
    except Exception:
        staged.unlink(missing_ok=True)
        if not first_install and previous.is_file():
            shutil.copy2(previous,existing)
            os.chmod(existing,0o755)
            expand_modules(target)
        raise
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
    user_helper=install_privileged_helper('pinas-nas-user',NAS_USER_HELPER,["create *","password *","list"])
    reset_helper=install_privileged_helper('pinas-smb-reset',SMB_RESET_HELPER,["reset"])
    if first_install and Path('/etc/samba/smb.conf').is_file():
        subprocess.run(['/usr/bin/python3',str(reset_helper),'reset'],check=True,timeout=45)
    share_helper=install_privileged_helper('pinas-nas-share',NAS_SHARE_HELPER,["list","create","delete","edit"])
    files_helper=install_privileged_helper('pinas-nas-files',NAS_FILES_HELPER,[""])
    updater_helper=install_privileged_helper('pinas-upgrader',NAS_UPDATER_HELPER,["apply","status"])
    storage_helper=install_privileged_helper('pinas-nas-storage',NAS_STORAGE_HELPER,["adopt"])
    erase_helper=install_privileged_helper('pinas-disk-erase',NAS_DISK_ERASE_HELPER,["wipe","format"])
    smart_helper=install_privileged_helper('pinas-smart-health',SMART_HEALTH_HELPER,[""])
    apt_helper=install_privileged_helper('pinas-apt-index',APT_INDEX_HELPER,["refresh","upgrade","firmware-check","schedule off","schedule daily","schedule weekly","schedule monthly","reboot","prune 6","prune 12","restart-auto timer","restart-auto service"])
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
    # Privileged helpers run through narrowly scoped sudoers rules. The service
    # mount namespace must permit those helpers to reach system configuration.
    service='''[Unit]\nDescription=PiNAS web dashboard\nAfter=network.target\n[Service]\nType=simple\nUser=pinas\nGroup=pinas\nExecStart=/usr/bin/python3 /opt/pinas/pinas.py --serve --tls --host %s --port %d\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=false\nProtectSystem=false\nReadWritePaths=/var/lib/pinas\nPrivateTmp=true\n[Install]\nWantedBy=multi-user.target\n'''%(bind_host,args.port)
    Path('/etc/systemd/system/pinas.service').write_text(service)
    subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','enable','--now','pinas-hostname.path'],check=True);subprocess.run(['systemctl','start','pinas-hostname.service'],check=True);subprocess.run(['systemctl','enable','pinas.service'],check=True);subprocess.run(['systemctl','restart','pinas.service'],check=True)
    print(f'PiNAS installed. For localhost access: https://127.0.0.1:{args.port} (self-signed certificate)')
    if args.lan:print(f'LAN TLS MODE: open https://<PI-IP>:{args.port}. Certificate is self-signed; use the .local hostname for name matching. Do not expose this port to the internet.')
    else:print('Localhost-only mode; re-run installer with --lan to enable direct LAN access for testing.')

class PiNASProtocolServer(ThreadingHTTPServer):
    """Accept HTTPS and redirect plain HTTP on the same bound port.

    TLS detection happens per connection in the existing server's worker
    thread, so a slow plaintext connection cannot block the accept loop.
    No second listener, privilege or extra daemon is required.
    """
    daemon_threads=True
    tls_context=None

    def finish_request(self,request,client_address):
        if self.tls_context is None:
            return super().finish_request(request,client_address)
        try:
            request.settimeout(5)
            initial=request.recv(1,socket.MSG_PEEK)
            if initial==b'\x16':
                with self.tls_context.wrap_socket(request,server_side=True) as secure:
                    secure.settimeout(None)
                    super().finish_request(secure,client_address)
                return
            # Redirect ordinary HTTP methods only. Never reflect an untrusted
            # Host header or unvalidated request path into the Location value.
            if initial in (b'G',b'H',b'P',b'O',b'D',b'T',b'C'):
                local_ip=request.getsockname()[0]
                address=('['+local_ip+']') if ':' in local_ip else local_ip
                location='https://'+address+':'+str(self.server_address[1])+'/'
                response=('HTTP/1.1 307 Temporary Redirect\r\n'
                          'Location: '+location+'\r\n'
                          'Content-Length: 0\r\n'
                          'Connection: close\r\n'
                          'Cache-Control: no-store\r\n\r\n')
                request.sendall(response.encode('ascii'))
        except (OSError,ssl.SSLError,ValueError):
            # Unknown/failed TLS handshakes must not be treated as HTTP.
            return

def main():
    ap=argparse.ArgumentParser(description='PiNAS Raspberry Pi NAS')
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
        server=PiNASProtocolServer((a.host,a.port),Handler)
        if a.tls:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(TLS_CERT),str(TLS_KEY))
            server.tls_context=context
        print('PiNAS running on %s://%s:%s'%('https' if a.tls else 'http',a.host,a.port))
        threading.Thread(target=cpu_sampler,daemon=True).start();server.serve_forever();return
    ap.print_help()
