# PiNAS

**PiNAS** is a lightweight, browser-based network-attached storage (NAS) manager designed primarily for Raspberry Pi hardware, including the Raspberry Pi 3B/3B+. It targets Raspberry Pi OS Lite and related Debian-based Linux systems, with an emphasis on low CPU, memory and disk-I/O overhead.

> **Current release: PiNAS v1.1.4.** This Shares-page consistency update standardises icon-and-text buttons and their order, while preserving the account, sharing and log functionality introduced in v1.1.3. PiNAS remains lightweight and NAS-focused; keep independent backups, especially before deleting folders.

## Features

### Typography
- **Clear Sans (Intel)** is self-hosted for login, navigation, buttons, labels and forms (regular, medium and bold).
- **Source Code Pro (Adobe)** is self-hosted for CLI-style output, code/log blocks and configuration path lists (regular and bold).
- The fonts are embedded in the standalone Python distribution, served locally by PiNAS and cached by the browser. No client font installation or internet connection is required.
- Licences are retained under `assets/fonts/` (Apache 2.0 for Clear Sans; SIL Open Font License 1.1 for Source Code Pro).


### Overview
- Per-disk storage usage bars showing disk name, used and available space. System/boot storage is excluded from NAS disk listings.
- Per-drive SMART health status and temperature alongside the Overview storage bars, checked **automatically on page load and every 10 minutes while the Overview/Storage page remains open**; standby drives are not deliberately woken and unsupported adapters are explained.
- Compact Disks / Shares / Users counters with links to their respective pages.
- CPU activity history with configurable sampling and history length.
- Memory usage and CPU-temperature doughnut charts.
- Raspberry Pi model, hostname, throttling status, uptime, OS and kernel in System health.
- NAS service health and reboot warnings, checked when Overview is opened or refreshed.

### System Updates and recovery
- Track manual and scheduled APT upgrade attempts in a separate, bounded SQLite history database (1–52 weeks retention; 12 weeks by default).
- Show automatic-update timer and one-shot service status on Updates and Overview. Failed units can be restarted after administrator re-authentication.
- Installed update history is shown as compact, collapsed date-only cards; expand an entry to view each package and the APT summary.
- **Download Logs** exports all retained recorded update attempts (including package names and APT summaries) to a locally generated UTF-8 text file. The download requires an active administrator session and never contacts external services.

### Sessions
- Session idle timeouts follow the selected 5/10/15/30/60-minute setting. Automatic polling does not extend sessions; genuine browser activity renews them, and the WebUI returns to the login screen on expiry.

### Storage and RAID
- **v1.0.8:** Wipe Disk and Format Disk require an explicit Yes checkbox, administrator password, and independent protected-disk validation. Wipe removes signatures, not securely erased data. Format creates an ext4/XFS/Btrfs filesystem directly on the whole drive. Do not use on active NAS storage.
- Warn about missing, unmounted or mismatched PiNAS-managed UUID data mounts and degraded mdadm arrays, without automatic repairs.
- Revalidate the selected filesystem against current hardware before a privileged storage adoption operation.
- Discover attached drives and supported **ext4, XFS and Btrfs** filesystems, including additional Btrfs detection where required.
- Inspect mounts and adopt existing formatted drives, with persistent mounting and applicable filesystem options.
- Run a manual **File Type Scan** separately for each mounted PiNAS data volume on Storage. The scan classifies allocated file sizes as Video, Pictures, Music and Other / filesystem, with a free-space segment; it never opens file contents.
- Access RAID management and discovery using `mdadm` when supported by the hardware and connected drives.
- The RAID tab is shown only when at least two writable, non-system data disks are detected, or when an existing mdadm array needs monitoring (including degraded arrays). System/boot disks and virtual devices such as ZRAM do not count.
- Storage operations with confirmation and appropriate administrative safeguards.

**Caution:** Destructive operations can cause permanent data loss. Confirm drive identities, RAID membership and available backups before applying changes. Not every filesystem or RAID workflow has been validated on all hardware.

### Users, shares and files
- The Shares page uses standard icon-and-text buttons: **Create Share** at the top, and **Edit Share → Stop Sharing → Repair Access → Delete Folder** for each share. Stop Sharing and Repair Access use dedicated icons. Legacy folder migration remains separately available when relevant.
- Remove NAS users from the Users page with administrator password and exact username confirmation. Account deletion removes Samba and its managed Linux identity, invalidates active NAS-user sessions, and preserves share folders and files. Remove the user from all share permissions first; private home shares must be stopped before deleting the account.
- Secondary PiNAS administrators can be removed using the same confirmation flow; the primary administrator and currently signed-in administrator are protected.
- **Stop Sharing** removes a PiNAS-managed SMB share without deleting any folder or file. **Delete Folder** removes the SMB share and permanently deletes its exact managed folder and contents after explicit confirmation, password re-entry and independent root-helper checks (system/boot disks and nested mounts are protected). Folder deletion cannot be undone.
- Create and manage NAS users and Samba (SMB) shares.
- Configure share access for selected users.
- Browser-based file explorer for authorised share users, with folder creation, upload, rename, delete and refresh.
- Shared files are accessible through SMB and the web file explorer, subject to their permissions.

### System updates
- **Check for updates** refreshes APT package information and checks Raspberry Pi EEPROM bootloader firmware status where the hardware and `rpi-eeprom-update` support it.
- Review and install available **OS package updates**.
- Configure basic automatic OS update schedules.
- View reboot-required and service-health information.

**Firmware checking is read-only.** PiNAS does not currently install or flash EEPROM firmware through the interface; the check is distinct from ordinary APT upgrades.

### Settings
A wider Settings popup with independently expandable sections, **collapsed by default**:
- **Appearance:** Light or Dark theme and font size.
- **Device storage:** System storage capacity and usage.
- **CPU monitoring:** Sampling interval and history length.
- **Security:** HTTPS information and session idle timeout.
- **Login screen:** Upload or remove the background image.
- **Administration:** Reset PiNAS-managed SMB configuration with safeguards.
- **Update PiNAS:** Upload a standalone PiNAS Python release to update the application.

### Media Server (optional MiniDLNA)
- Install, configure and control the lightweight MiniDLNA/ReadyMedia service only when needed. No containers or heavyweight media-management stack.
- Create a ready-to-use `pinas-media` library on a mounted NAS disk with **Movies**, **Television**, **Music** and **Pictures** folders.
- Configure DLNA folders, grant the service read/traverse ACL access, restart indexing or rebuild the media database.
- Upload supported videos, music, images and subtitles directly into a configured media folder through the administrator WebUI. Transfers use small chunks, progress reporting and cancellation; completed files receive MiniDLNA read access. Existing filenames are not overwritten.
- DLNA discovery is intended for a **trusted local network**. DLNA does not enforce individual Samba-user permissions; only add folders you intend to make available to DLNA clients.

### Security and administration
- Restart or shut down PiNAS from the administrator header after password confirmation. Device power actions interrupt active NAS connections.
- HTTPS web access (with a locally generated self-signed certificate by default).
- Administrator authentication and password confirmation for protected operations.
- Privileged helper commands restricted to supported operations.
- Separation between administration and share-user access.

## Install

Download the **standalone `pinas.py`** from the intended PiNAS branch or release onto your Raspberry Pi, then run:

```bash
sudo python3 pinas.py --install --lan
```

This installs the required NAS dependencies through APT unless they are deliberately skipped. If the required packages are already installed, use:

```bash
sudo python3 pinas.py --install --lan --skip-packages
```

PiNAS uses **HTTPS port 8765 by default**. Open `https://<pi-ip-address>:8765` in a browser on your local network; your browser may warn about the self-signed certificate. Keep PiNAS on a trusted network, not exposed directly to the internet.

The installer configures a systemd service and extracts its bundled source sections under `/opt/pinas/modules/`. Existing configuration and NAS data are intended to be preserved during application updates.

### Configuration backup and restore

In **Settings → Configuration backup & recovery**, an administrator can export a JSON manifest after re-entering their password. It contains portable interface/monitoring/security preferences, account display names, and a read-only inventory of NAS users and shares. Administrator credentials, SMB passwords, certificates, login backgrounds and file contents are excluded.

**Restore settings from file** requires administrator authentication and confirmation. It applies only validated device preferences and display names. It does **not** automatically recreate Samba users, shares, mounts, mdadm RAID, filesystem contents or passwords. Those components must be restored separately by an administrator. The backup is a recovery reference, **not a full NAS backup**, and is not a substitute for independent copies of your data.

### Update PiNAS

There are two supported deployment paths for the **same standalone `pinas.py`**:

**Command line** — obtain the newer `pinas.py` and run:

```bash
sudo python3 pinas.py --install --lan --skip-packages
```

Omit `--skip-packages` if system dependencies also need installing.

**WebUI** — open **Settings → Update PiNAS**, expand the section, select the trusted `pinas.py` release and confirm the update with the administrator password.

The WebUI updater checks the uploaded file's size, SHA-256 integrity, Python syntax and expected PiNAS package structure. It then schedules a privileged update process, retains a previous application copy, replaces the application, extracts the modules and restarts the service; it attempts rollback if installation fails.

**Important:** SHA-256 here verifies integrity, **not publisher authenticity**. Only install code from a source you trust. When moving from an older pre-modular installation or when updater permissions change, a one-time command-line installation may be required to register the current privileged helpers.

### Verify an installation

```bash
systemctl is-active pinas.service
ls -lah /opt/pinas/modules/
```

A modular build contains these seven extracted source sections:

```text
/opt/pinas/
├── pinas.py
└── modules/
    ├── core.py
    ├── web_ui.py
    ├── storage_breakdown.py
    ├── http_api.py
    ├── privileged_helpers.py
    ├── media_server.py
    └── installer.py
```

If the standalone modular release is installed but the directory is missing, extract its embedded sections without reinstalling NAS dependencies:

```bash
sudo python3 /opt/pinas/pinas.py --extract-modules
```

## Development and release structure

PiNAS development now uses logically separated source sections:

```text
src/pinas/
├── core.py
├── web_ui.py
├── storage_breakdown.py
├── http_api.py
├── privileged_helpers.py
├── media_server.py
└── installer.py

tools/build_release.py
pinas.py
```

The Python-standard-library release builder combines the source sections into a **single downloadable, self-extracting `pinas.py`**:

```bash
python3 tools/build_release.py
python3 tools/build_release.py --check
python3 -m py_compile pinas.py
```

Edit the files in `src/pinas/` and regenerate `pinas.py`; **do not maintain the generated release file independently**.

**Architecture note:** These files are currently ordered source sections executed in a shared Python namespace for compatibility. They are extracted during installation but are not yet fully independent, importable runtime modules. The standalone bundled release remains the application entry point.

### Branches

- `main`: reviewed/tested baseline.
- Release workflows publish version-tagged downloadable `pinas.py` files after automated checks.
- Feature and fix branches: proposed changes reviewed using pull requests.

## Scope and known limitations

PiNAS intentionally prioritises simple NAS functionality and Raspberry Pi efficiency over container orchestration and heavyweight applications. The former **Applications** page was removed. The optional **Media Server** page manages MiniDLNA and guided media folders, but is never installed by default.

- EEPROM firmware **installation** through the UI is not implemented; checking only.
- The modular source structure has not yet been fully refactored into independently importable Python modules.
- Disk, RAID, permissions and update paths should be tested on the specific Raspberry Pi model and filesystem before use with valuable data.
- Application backup/rollback is not a substitute for backing up NAS data.

## Licence

No licence has been selected yet. Help yourself to use the code as you see fit. Free and open source for all.

## v1.0.1 maintenance release

See [v1.0.1 code-quality and UI-consistency notes](docs/releases/v1.0.1.md). The standalone application remains lightweight and standard-library-only. This maintenance update consolidates shared styling and helper routines and adds automated quality checks.

## Recent releases

- **v1.1.0 (current):** [Official release notes](docs/releases/v1.1.0.md) — optional MiniDLNA Media Server, guided library setup, administrator browser uploads, on-demand per-disk file-type scans, SMART diagnostics, power controls and UI consistency.
- **v1.0.8 (historical):** [Official release notes](docs/releases/v1.0.8.md) — update history and service health, final button consistency, and guarded Wipe Disk / Format Disk.

- **v1.0.6:** [Official release notes](docs/releases/v1.0.6.md) — storage safety and recovery, Overview disk health/temperature, standardised buttons and improved automatic browser reload after an application update.
- **v1.0.5 (development milestone):** [Storage safety and testing notes](docs/releases/v1.0.5.md).
- **v1.0.4 (development milestone):** [Reliability and recovery notes](docs/releases/v1.0.4.md).

For installable builds, use the [PiNAS GitHub Releases](https://github.com/thefistedpigeon/PiNAS/releases) page rather than a development branch.

## v1.0.7 development milestone

The [v1.0.7 update history and service-health notes](docs/releases/v1.0.7.md) describe the improvements included in the official v1.0.8 release.

## v1.0.8 official release

See the [v1.0.8 Wipe Disk and Format Disk notes](docs/releases/v1.0.8.md) for supported actions, safety limitations, and disposable-disk testing guidance.

## Current PiNAS module layout (v1.1.0)

The standalone `pinas.py` is generated from seven ordered source sections: `core.py`, `web_ui.py`, `storage_breakdown.py`, `http_api.py`, `privileged_helpers.py`, `media_server.py`, and `installer.py`. The sections execute in a shared namespace for portable deployment; changes require rebuilding with `python3 tools/build_release.py`. The `--check` command verifies the full generated output.

**Media Server:** MiniDLNA remains optional. Media folders live on managed, mounted PiNAS data disks; the administrator can upload media from the browser. DLNA access is separate from SMB permissions. Each disk's **File Type Scan** is started manually from Storage; Overview displays a simpler usage bar. See [v1.1.0 release notes](docs/releases/v1.1.0.md).
