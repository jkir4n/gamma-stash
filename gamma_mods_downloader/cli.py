"""
CLI for G.A.M.M.A. STASH.

Usage:
    gamma-stash                   Run the setup + download wizard
    gamma-stash setup             Same as above
    gamma-stash cleanup           Stop/remove Flaresolverr Docker container
"""

import argparse
import os
import sys
from typing import List, Optional

from .setup import check_all_dependencies, run_setup_wizard, cleanup_docker
from .terminal import (
    GREEN, AMBER, RED, CYAN, GRAY, DIM, BOLD, RESET,
    print_banner, print_ok, print_error, print_warn, print_info, print_divider,
)
from . import __version__


def cmd_setup(args: argparse.Namespace) -> int:
    return run_setup_wizard()


def cmd_cleanup(args: argparse.Namespace) -> int:
    cleanup_docker()
    return 0


def _default_flow(parsed: argparse.Namespace) -> int:
    all_ok, missing_req, missing_opt = check_all_dependencies()
    if not all_ok:
        print_error("Required dependencies missing:")
        for dep in missing_req:
            print(f"    {RED}[!!]{RESET} {dep}")
        print()
        print_info("Run 'gamma-stash setup' to install them.")
        return 1

    print_info("Starting setup wizard ...")
    print()
    return cmd_setup(parsed)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="G.A.M.M.A. STASH -- batch download G.A.M.M.A. mods",
    )
    parser.add_argument("--version", "-V", action="version",
                        version=f"G.A.M.M.A. STASH {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_setup = sub.add_parser("setup", help="Run the setup + download wizard")
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
        else:
            rc = _default_flow(parsed)
    except SystemExit:
        raise
    except Exception as e:
        print(f"{RED}ERROR:{RESET} {e}", file=sys.stderr)
        if os.environ.get("GMD_DEBUG"):
            import traceback
            traceback.print_exc()
        rc = 1

    _maybe_wait_for_exit(argv)
    return rc


def _maybe_wait_for_exit(argv: Optional[List[str]]) -> None:
    if argv is not None:
        return
    if not sys.stdout.isatty():
        return
    try:
        print()
        input(f"{GRAY}Press Enter to exit ...{RESET}")
    except EOFError:
        pass


if __name__ == "__main__":
    sys.exit(main())
