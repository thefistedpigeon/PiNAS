# PiNAS

**PiNAS** is a lightweight, browser-based network-attached storage (NAS) manager designed primarily for Raspberry Pi hardware, including the Raspberry Pi 3B/3B+. It targets Raspberry Pi OS Lite and related Debian-based Linux systems, with an emphasis on low CPU, memory and disk-I/O overhead.

> **Release status:** PiNAS v1.0.6 is the current official release, incorporating the tested v1.0.4 reliability/recovery and v1.0.5 storage-safety milestones. Keep independent backups of important files, particularly before changing storage or RAID configurations.

## Features

### Overview
- Per-disk storage usage bars showing disk name, used and available space. System/boot storage is excluded from NAS disk listings.
- Per-drive SMART health status and temperature alongside the Overview storage bars, checked when Overview opens and manually refreshed on demand; unsupported adapters show unavailable values.
- Compact Disks / Shares / Users counters with links to their respective pages.
- CPU activity history with configurable sampling and history length.
- Memory usage and CPU-temperature doughnut charts.
- Raspberry Pi model, hostname, throttling status, uptime, OS and kernel in System health.
- NAS service health and reboot warnings, checked when Overview is opened or refreshed.

### System Updates and recovery
- Track manual and scheduled APT upgrade attempts in a separate, bounded SQLite history database (6 or 12 months retention).
- Show automatic-update timer and one-shot service status on Updates and Overview. Failed units can be restarted after administrator re-authentication.

### Storage and RAID
- **v1.0.8 test candidate:** Wipe Disk and Format Disk require an explicit Yes checkbox, administrator password, and independent protected-disk validation. Wipe removes signatures, not securely erased data. Format creates an ext4/XFS/Btrfs filesystem directly on the whole drive. Do not use on active NAS storage.
- Warn about missing, unmounted or mismatched PiNAS-managed UUID data mounts and degraded mdadm arrays, without automatic repairs.
- Revalidate the selected filesystem against current hardware before a privileged storage adoption operation.
- Discover attached drives and supported **ext4, XFS and Btrfs** filesystems, including additional Btrfs detection where required.
- Inspect mounts and adopt existing formatted drives, with persistent mounting and applicable filesystem options.
- Access RAID management and discovery using `mdadm` when supported by the hardware and connected drives.
- Storage operations with confirmation and appropriate administrative safeguards.

**Caution:** Destructive operations can cause permanent data loss. Confirm drive identities, RAID membership and available backups before applying changes. Not every filesystem or RAID workflow has been validated on all hardware.

### Users, shares and files
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

### Security and administration
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

### Configuration backup and restore (v1.0.4 candidate)

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

A modular build should contain these five extracted files:

```text
/opt/pinas/
├── pinas.py
└── modules/
    ├── core.py
    ├── web_ui.py
    ├── http_api.py
    ├── privileged_helpers.py
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
├── http_api.py
├── privileged_helpers.py
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

PiNAS intentionally prioritises simple NAS functionality and Raspberry Pi efficiency over container orchestration and heavyweight applications. The former **Applications** page and MiniDLNA integration were removed; a dedicated **Media Server** page may return once a reliable implementation has been tested.

- EEPROM firmware **installation** through the UI is not implemented; checking only.
- The modular source structure has not yet been fully refactored into independently importable Python modules.
- Disk, RAID, permissions and update paths should be tested on the specific Raspberry Pi model and filesystem before use with valuable data.
- Application backup/rollback is not a substitute for backing up NAS data.

## Licence

No licence has been selected yet. Help yourself to use the code as you see fit. Free and open source for all.

## v1.0.1 maintenance release

See [v1.0.1 code-quality and UI-consistency notes](docs/releases/v1.0.1.md). The standalone application remains lightweight and standard-library-only. This maintenance update consolidates shared styling and helper routines and adds automated quality checks.

## Recent releases

- **v1.0.6:** [Official release notes](docs/releases/v1.0.6.md) — storage safety and recovery, Overview disk health/temperature, standardised buttons and improved automatic browser reload after an application update.
- **v1.0.5 (development milestone):** [Storage safety and testing notes](docs/releases/v1.0.5.md).
- **v1.0.4 (development milestone):** [Reliability and recovery notes](docs/releases/v1.0.4.md).

For installable builds, use the [PiNAS GitHub Releases](https://github.com/thefistedpigeon/PiNAS/releases) page rather than a development branch.

## v1.0.7 development candidate

The [v1.0.7 update history and service-health notes](docs/releases/v1.0.7.md) describe the unreleased candidate for Raspberry Pi testing. **v1.0.6 remains the latest official release** until this candidate is reviewed and published.

## v1.0.8 development candidate

See the [v1.0.8 Wipe Disk and Format Disk safety notes](docs/releases/v1.0.8.md). This candidate is not a published release and must be tested on disposable disks before merging. The latest official release remains v1.0.6.
