# PiNAS

A lightweight, web-based NAS management application for Raspberry Pi OS and related Debian-based systems.

> **Development status:** Release candidate RC16.0. This software is under active development; test carefully before using it with important data.

## Current capabilities

- Browser-based administration and NAS user file access
- Local user accounts and Samba share management
- Storage discovery and non-destructive adoption of supported filesystems
- Existing RAID array discovery and monitoring
- OS update checking, installation and simple automatic scheduling
- HTTPS and authenticated administrative actions
- Basic system health information

**Not yet supported:** Destructive disk formatting/wiping and RAID array creation through the UI. Do not rely on PiNAS as your only backup.

## Install or update

Download `pinas.py` from this repository and run on the target machine:

```bash
sudo python3 pinas.py --install --lan --skip-packages
```

The installer is intended for supported Debian-family systems. Review the source and keep backups before deploying. By default, the web interface uses HTTPS on port 8765; the initial self-signed certificate may trigger a browser warning.

## Development workflow

- `main`: latest reviewed and tested baseline
- `develop`: ongoing release-candidate development
- Feature/fix branches: proposed changes reviewed through pull requests
- Releases: tagged, downloadable single-file `pinas.py` builds once validated

## Roadmap

- **RC16.1:** SMART disk health and temperatures
- **RC16.2:** NAS service health and warnings
- **RC16.3:** Restart, shutdown and maintenance controls
- **RC16.4:** UI consistency and regression pass
- **RC17:** Application self-update and backup/rollback safeguards

Hardware-dependent features must be tested on Raspberry Pi hardware before being considered validated.

## Licence

No licence has been selected yet. Repository visibility and copyright remain with the owner.
