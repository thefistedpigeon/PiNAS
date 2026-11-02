# PiNAS modular source and standalone release (Phase 3)

PiNAS remains a **single downloadable `pinas.py`**. Source code is now maintained in `src/pinas/`:

- `core.py` — imports, settings, security, hardware and shared functionality
- `web_ui.py` — complete browser interface and central styling
- `http_api.py` — HTTP handler, APIs and embedded privileged helper sources
- `privileged_helpers.py` — storage, updater and other restricted helper definitions
- `installer.py` — CLI install, service setup and module extraction

These are **ordered source sections**, compiled and executed in a shared namespace for compatibility with the current code. They are not yet independently importable Python modules; that is a later internal refactor.

## Building

```bash
python3 tools/build_release.py
python3 tools/build_release.py --check
python3 -m py_compile pinas.py
```

The builder uses only the Python standard library and produces `pinas.py` with its modules embedded. Do not edit the generated `pinas.py` directly; modify the source sections and rebuild.

## Installing or upgrading

On a supported Raspberry Pi OS / Debian test server:

```bash
sudo python3 pinas.py --install --lan
```

Or upload the same generated `pinas.py` through **Settings → Update PiNAS** on an installation with Phase 2 already deployed.

The installer writes source sections into `/opt/pinas/modules/` for inspection and future extraction of truly independent modules. The runtime continues to load the **embedded** sections from the standalone release; this ensures WebUI upgrades do not load stale files. Upgrades re-extract sections and restore them on rollback. Existing NAS data under `/var/lib/pinas`, Samba settings and shares are not targeted by module extraction.

**Important:** Installing the phase 3 candidate for the first time should be done by command line for a baseline. Test WebUI upload and rollback with a disposable Pi before merging. The first refactor preserves behavioural compatibility but has not been runtime-tested on a Raspberry Pi.

## Deployment integrity

The Phase 2 updater checks the SHA-256 hash sent with uploads and parses the bundle's Python syntax. This is not a cryptographic signature. Install only a trusted PiNAS release, because uploaded code executes with elevated privileges.
