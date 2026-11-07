#!/usr/bin/env python3
"""Vendor pinned, unmodified web fonts and their licences for offline PiNAS builds.

Run only when updating the vendored fonts. The installed PiNAS service never
downloads fonts, and normal builds use the checked-in assets.
"""
import hashlib
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "assets" / "fonts"
ASSETS = (
    ("ClearSans-Regular.woff", "intel/clear-sans",
     "1993725b24a36af21e7ebaa8977103983b608572",
     "WOFF/ClearSans-Regular.woff", "f4aacf79dac8d55cf0f07952716c81d23ddd8d70"),
    ("ClearSans-Medium.woff", "intel/clear-sans",
     "1993725b24a36af21e7ebaa8977103983b608572",
     "WOFF/ClearSans-Medium.woff", "702fb8aed30587c98d61bb3ba7d88a53f95e42ba"),
    ("ClearSans-Bold.woff", "intel/clear-sans",
     "1993725b24a36af21e7ebaa8977103983b608572",
     "WOFF/ClearSans-Bold.woff", "bda6eb27a530f5b6fdc943ca0daa97f65fe991e2"),
    ("SourceCodePro-Regular.woff2", "adobe-fonts/source-code-pro",
     "803b7e23ec97ae58b6232ea76519a76d428ba268",
     "WOFF2/TTF/SourceCodePro-Regular.ttf.woff2", "40826f1a67950d4c2cf0e835c9862141587d43c2"),
    ("SourceCodePro-Bold.woff2", "adobe-fonts/source-code-pro",
     "803b7e23ec97ae58b6232ea76519a76d428ba268",
     "WOFF2/TTF/SourceCodePro-Bold.ttf.woff2", "5ce97745e3b492ddfbde21a6268c0a433bada842"),
    ("LICENSE-ClearSans.txt", "intel/clear-sans",
     "1993725b24a36af21e7ebaa8977103983b608572",
     "LICENSE.txt", "d645695673349e3947e8e5ae42332d0ac3164cd7"),
    ("LICENSE-SourceCodePro.md", "adobe-fonts/source-code-pro",
     "803b7e23ec97ae58b6232ea76519a76d428ba268",
     "LICENSE.md", "70288a864f8dfd1314aa0315748eece0cf80fdda"),
)

def git_blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()

def vendor():
    DEST.mkdir(parents=True, exist_ok=True)
    for name, repository, commit, upstream_path, sha in ASSETS:
        path = DEST / name
        if path.is_file() and git_blob_sha(path.read_bytes()) == sha:
            print("Verified", name)
            continue
        url = f"https://raw.githubusercontent.com/{repository}/{commit}/{upstream_path}"
        request = Request(url, headers={"User-Agent": "PiNAS-font-vendor"})
        with urlopen(request, timeout=30) as response:
            data = response.read(2_000_000)
        if git_blob_sha(data) != sha:
            raise RuntimeError(f"Unexpected upstream content for {name}")
        if name.endswith(".woff") and not data.startswith(b"wOFF"):
            raise RuntimeError(f"Invalid WOFF file: {name}")
        if name.endswith(".woff2") and not data.startswith(b"wOF2"):
            raise RuntimeError(f"Invalid WOFF2 file: {name}")
        path.write_bytes(data)
        print("Vendored", name, len(data), "bytes")

if __name__ == "__main__":
    vendor()
