"""
CLI for G.A.M.M.A. STASH.

Usage:
    gamma-stash                   Launch the TUI wizard
    gamma-stash setup             CLI wizard (no TUI)
    gamma-stash cleanup           Stop/remove Flaresolverr Docker container
    gamma-stash --cli             Force CLI mode for default flow
"""

import argparse
import sys
from typing import List, Optional

from .setup import run_setup_wizard, cleanup_docker, fetch_latest_mods_txt
from .terminal import (
    RED, RESET, print_ok, print_error,
)
from . import __version__


def cmd_setup(args: argparse.Namespace) -> int:
    if getattr(args, "update_manifest", False):
        gamma_dir = getattr(args, "gamma_dir", None)
        if gamma_dir:
            print_ok("Fetching latest official mods.txt from GitHub...")
            fetch_latest_mods_txt(gamma_dir)
        else:
            print_error("--update-manifest requires --gamma-dir to specify destination.")
            return 1

    return run_setup_wizard(
        gamma_dir=getattr(args, "gamma_dir", None),
        flaresolverr_url=getattr(args, "flaresolverr_url", None),
        mode=getattr(args, "mode", None),
        limit_rate=getattr(args, "limit_rate", None),
        no_sound=getattr(args, "no_sound", False),
        category=getattr(args, "category", None),
        browser_dir=getattr(args, "browser_dir", None),
        yes=getattr(args, "yes", False),
    )


def cmd_cleanup(args: argparse.Namespace) -> int:
    cleanup_docker(interactive=not getattr(args, "yes", False))
    return 0


def _default_flow_tui() -> int:
    from .tui import run_tui
    run_tui()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="G.A.M.M.A. STASH -- batch download G.A.M.M.A. mods",
    )
    parser.add_argument("--version", "-V", action="version",
                        version=f"G.A.M.M.A. STASH {__version__}")
    parser.add_argument("--cli", action="store_true",
                        help="Use CLI mode instead of TUI")
    parser.add_argument("--gamma-dir", type=str, default=None,
                        help="Path to GAMMA installation folder")
    parser.add_argument("--flaresolverr-url", type=str, default=None,
                        help="URL of Flaresolverr instance (e.g. http://localhost:8191)")
    parser.add_argument("--mode", choices=["docker", "manual", "browser"], default=None,
                        help="Cloudflare bypass strategy: docker, manual, or browser (zero-docker)")
    parser.add_argument("--limit-rate", type=str, default=None,
                        help="Limit download speed per stream (e.g. 5M, 500K)")
    parser.add_argument("--category", type=str, default=None,
                        help="Download only mods matching this category name")
    parser.add_argument("--browser-dir", type=str, default=None,
                        help="Path to browser downloads folder for Browser-Assisted mode")
    parser.add_argument("--no-sound", action="store_true",
                        help="Mute S.T.A.L.K.E.R. PDA completion chime")
    parser.add_argument("--update-manifest", action="store_true",
                        help="Download latest official mods.txt from GitHub before scanning")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Automatic yes to prompts; run unattended")
    sub = parser.add_subparsers(dest="command")

    p_setup = sub.add_parser("setup", help="Run the setup + download wizard (CLI)")
    p_setup.add_argument("--gamma-dir", type=str, default=None,
                         help="Path to GAMMA installation folder")
    p_setup.add_argument("--flaresolverr-url", type=str, default=None,
                         help="URL of Flaresolverr instance (e.g. http://localhost:8191)")
    p_setup.add_argument("--mode", choices=["docker", "manual", "browser"], default=None,
                         help="Cloudflare bypass strategy: docker, manual, or browser (zero-docker)")
    p_setup.add_argument("--limit-rate", type=str, default=None,
                         help="Limit download speed per stream (e.g. 5M, 500K)")
    p_setup.add_argument("--category", type=str, default=None,
                         help="Download only mods matching this category name")
    p_setup.add_argument("--browser-dir", type=str, default=None,
                         help="Path to browser downloads folder for Browser-Assisted mode")
    p_setup.add_argument("--no-sound", action="store_true",
                         help="Mute S.T.A.L.K.E.R. PDA completion chime")
    p_setup.add_argument("--update-manifest", action="store_true",
                         help="Download latest official mods.txt from GitHub before scanning")
    p_setup.add_argument("-y", "--yes", action="store_true",
                         help="Automatic yes to prompts; run unattended")
    p_setup.set_defaults(func=cmd_setup)

    p_clean = sub.add_parser("cleanup", help="Stop/remove Flaresolverr Docker container")
    p_clean.add_argument("-y", "--yes", action="store_true",
                         help="Automatic yes to prompts; run unattended")
    p_clean.set_defaults(func=cmd_cleanup)

    try:
        parsed = parser.parse_args(args=argv)
    except SystemExit as e:
        sys.exit(e.code if e.code is not None else 0)

    try:
        if parsed.command:
            rc = parsed.func(parsed)
        elif parsed.cli:
            rc = cmd_setup(parsed)
        else:
            rc = _default_flow_tui()
    except SystemExit:
        raise
    except Exception as e:
        print(f"{RED}ERROR:{RESET} {e}", file=sys.stderr)
        if sys.platform == "win32" and sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
            try:
                input("Press Enter to exit ...")
            except Exception:
                pass
        rc = 1

    return rc


if __name__ == "__main__":
    sys.exit(main())
