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

from .setup import run_setup_wizard, cleanup_docker
from .terminal import (
    RED, RESET,
)
from . import __version__


def cmd_setup(args: argparse.Namespace) -> int:
    return run_setup_wizard()


def cmd_cleanup(args: argparse.Namespace) -> int:
    cleanup_docker()
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
    sub = parser.add_subparsers(dest="command")

    p_setup = sub.add_parser("setup", help="Run the setup + download wizard (CLI)")
    p_setup.set_defaults(func=cmd_setup)

    p_clean = sub.add_parser("cleanup", help="Stop/remove Flaresolverr Docker container")
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
        if sys.platform == "win32":
            try:
                input("Press Enter to exit ...")
            except Exception:
                pass
        rc = 1

    return rc


if __name__ == "__main__":
    sys.exit(main())
