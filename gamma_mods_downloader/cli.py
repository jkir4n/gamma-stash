"""
CLI for the Gamma Mods Downloader.

Usage:
    gamma-mods-downloader init           Generate default config.yaml
    gamma-mods-downloader status          Show download progress
    gamma-mods-downloader list [--pending] [--moddb | --github]
    gamma-mods-downloader download        Download all pending mods
"""

import argparse
import os
import sys
from typing import List, Optional

from .config import DEFAULT_CONFIG, load_config
from .downloader import Downloader, LinksFile, _parse_entry, _is_category_header


def _abspath(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p))


def cmd_init(args: argparse.Namespace) -> int:
    """Generate a default config.yaml pointing to GAMMA's mods.txt."""
    path = args.config or "config.yaml"
    if os.path.exists(path):
        print(f"{path} already exists. Delete it first or use a different path.")
        return 1

    # Try to auto-detect GAMMA's mods.txt location
    gamma_candidates = [
        r"D:\GAMMA\.Grok's Modpack Installer\mods.txt",
        r"C:\GAMMA\.Grok's Modpack Installer\mods.txt",
        os.path.expanduser("~/GAMMA/.Grok's Modpack Installer/mods.txt"),
        "mods.txt",
    ]
    mods_file = ""
    for c in gamma_candidates:
        if os.path.exists(c):
            mods_file = c
            break

    if not mods_file:
        mods_file = "mods.txt"  # fallback

    download_dirs = [
        r"D:\gamma\mods",
        os.path.join(os.path.dirname(mods_file), "..", "downloads"),
        os.path.expanduser("~/gamma_mods_downloads"),
    ]
    dd = download_dirs[0]
    for d in download_dirs:
        expanded = os.path.expandvars(os.path.expanduser(d))
        p = os.path.abspath(expanded)
        if os.path.exists(p) or os.path.exists(os.path.dirname(p)):
            dd = d
            break

    lines = f"""# Gamma Mods Downloader Configuration
# Edit this file to match your setup.
# Alternatively, use GMD_* environment variables to override individual values.

# Path to GAMMA's mods.txt (tab-separated mod manifest)
links_file: {mods_file}

# Directory where downloaded mods are stored temporarily
download_dir: {dd}

# Delay in seconds between downloads
download_delay: 2

# Flaresolverr instance for bypassing Cloudflare challenges on ModDB
flaresolverr:
  url: http://localhost:8191/v1
  timeout_ms: 60000

# Destination for downloaded mods
destination:
  local_path: {dd}

# Where to save download tracking state (status, actual_md5 per entry)
tracking_file: {os.path.join(dd, "_tracking.json")}
"""
    with open(path, "w") as f:
        f.write(lines)
    print(f"Config written to {_abspath(path)}")
    print(f"links_file: {mods_file}")
    if not os.path.exists(mods_file):
        print(f"WARN: {mods_file} not found -- set GMD_LINKS_FILE or edit config.yaml")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show download progress summary."""
    cfg = load_config(args.config)
    links = LinksFile(local_path=cfg["links_file"])
    try:
        total, downloaded, pending, moddb, github = links.status_summary()
    except FileNotFoundError:
        print(f"Links file not found: {cfg['links_file']}")
        return 1

    print(f"\nG.A.M.M.A. Mod Status")
    print(f"{'-'*40}")
    print(f"Total mods:  {total}")
    print(f"Downloaded:  {downloaded}")
    print(f"Pending:     {pending}")
    print(f"{'-'*40}")
    print(f"MODDB:       {moddb}")
    print(f"GitHub:      {github}")

    # Show by category
    try:
        cats, entries_by_cat = links.read_with_categories()
        print(f"\n  By category:")
        for i, cat_name in enumerate(cats):
            cat_entries = entries_by_cat[i]
            dl = sum(1 for e in cat_entries if e["status"] == "DOWNLOADED")
            total_cat = len(cat_entries)
            print(f"   {cat_name:40s} {dl:>3}/{total_cat}")
    except Exception:
        pass  # category parsing is best-effort

    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List mod entries, optionally filtered."""
    cfg = load_config(args.config)
    links = LinksFile(local_path=cfg["links_file"])
    entries = links.read()

    # Apply filters
    if args.pending:
        entries = [e for e in entries if e["status"] == "PENDING"]
    if args.moddb:
        entries = [e for e in entries if e["source"] == "MODDB"]
    if args.github:
        entries = [e for e in entries if e["source"] == "GITHUB"]

    if not entries:
        print("No entries matching filters.")
        return 0

    has_md5 = any(e.get("expected_md5") for e in entries)

    for e in entries:
        src_icon = "[GH]" if e["source"] == "GITHUB" else "[M]"
        desc = e.get("description", "")
        author = e.get("author", "")
        md5_str = f" [{e['expected_md5'][:8]}...]" if e.get("expected_md5") else " [no MD5]"
        status_icon = "[D]" if e["status"] == "DOWNLOADED" else "[P]"
        print(f"  {status_icon} {src_icon} {e['filename']}{md5_str}")
        if desc and args.verbose:
            print(f"        {desc} -- by {author}")

    print(f"\n{len(entries)} entries")

    if not args.pending:
        total = len(links.read())
        print(f"   (filtering: {'pending' if args.pending else 'all'}"
              f"{' / MODDB' if args.moddb else ''}"
              f"{' / GitHub' if args.github else ''})")
        if args.pending:
            print(f"   Use without --pending to see all entries")

    return 0


def cmd_download(args: argparse.Namespace) -> int:
    """Download all pending mods."""
    cfg = load_config(args.config)
    downloader = Downloader(cfg)
    results = downloader.download_all()
    return 0 if results["fail"] == 0 else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gamma Mods Downloader -- batch download G.A.M.M.A. mods",
    )
    parser.add_argument("--config", "-c", default=None,
                        help="Path to config.yaml (default: auto-detect)")
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Generate default config.yaml")
    p_init.set_defaults(func=cmd_init)

    # status
    p_status = sub.add_parser("status", help="Show download progress")
    p_status.set_defaults(func=cmd_status)

    # list
    p_list = sub.add_parser("list", help="List mod entries")
    p_list.add_argument("--pending", "-p", action="store_true",
                        help="Show only PENDING entries")
    p_list.add_argument("--moddb", action="store_true",
                        help="Show only MODDB entries")
    p_list.add_argument("--github", action="store_true",
                        help="Show only GitHub entries")
    p_list.add_argument("--verbose", "-v", action="store_true",
                        help="Show description and author")
    p_list.set_defaults(func=cmd_list)

    # download
    p_dl = sub.add_parser("download", help="Download all pending mods")
    p_dl.set_defaults(func=cmd_download)

    parsed = parser.parse_args(args=argv)
    try:
        return parsed.func(parsed)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        if os.environ.get("GMD_DEBUG"):
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
