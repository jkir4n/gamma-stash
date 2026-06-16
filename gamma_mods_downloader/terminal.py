"""
STALKER GAMMA themed terminal output — colors, spinners, progress bars.
Uses ANSI escape codes (Windows 10+ supported natively).
"""

import os
import sys
import time
from typing import Optional


def _enable_ansi() -> None:
    """Enable ANSI escape code processing and UTF-8 on Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass
    # Reconfigure stdout for UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def ensure_admin() -> bool:
    """
    Re-launch with admin rights via UAC if needed.
    Returns True if already elevated, re-launches and exits otherwise.
    """
    if sys.platform != "win32":
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return True
        print("This tool requires root privileges for Docker operations.")
        print("Run with: sudo gamma-stash")
        sys.exit(1)

    try:
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True

        # Set inherited env var so the elevated child knows it was re-launched
        ctypes.windll.kernel32.SetEnvironmentVariableW("GAMMA_STASH_ELEVATED", "1")

        params = " ".join(f'"{a}"' for a in sys.argv)
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        sys.exit(0 if ret > 32 else 1)
    except Exception:
        pass

    return True


_enable_ansi()

# ── Colors ──────────────────────────────────────────────────────────
GREEN = "\033[38;5;46m"
DARK_GREEN = "\033[38;5;22m"
AMBER = "\033[38;5;214m"
RED = "\033[38;5;196m"
DARK_RED = "\033[38;5;88m"
CYAN = "\033[38;5;51m"
GRAY = "\033[38;5;245m"
DARK_GRAY = "\033[38;5;240m"
WHITE = "\033[38;5;255m"

BG_GREEN = "\033[48;5;22m"
BG_DARK = "\033[48;5;232m"
BG_RED = "\033[48;5;88m"

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

ASYNC = sys.stdout.encoding != "utf-8" if hasattr(sys.stdout, "encoding") else False

SPINNER_FRAMES = ["|", "/", "-", "\\"]
BOX_H = "\u2500"
BOX_V = "\u2502"
BOX_TL = "\u250c"
BOX_TR = "\u2510"
BOX_BL = "\u2514"
BOX_BR = "\u2518"

OK_MARK = "OK"
FAIL_MARK = "FAIL"
WARN_MARK = "WARN"


class Spinner:
    """Indeterminate spinner for long operations."""

    def __init__(self, message: str = ""):
        self.message = message
        self._running = False
        self._idx = 0

    def _spin(self) -> None:
        frame = SPINNER_FRAMES[self._idx % len(SPINNER_FRAMES)]
        self._idx += 1
        sys.stdout.write(f"\r  {GREEN}{frame}{RESET} {self.message}  ")
        sys.stdout.flush()

    def start(self, message: str = "") -> None:
        if message:
            self.message = message
        self._running = True
        self._spin()

    def stop(self, final: str = "OK") -> None:
        self._running = False
        if final:
            sys.stdout.write(f"\r  {GREEN}{final}{RESET}  {self.message}\n")
        else:
            sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()

    def fail(self, reason: str = "") -> None:
        self._running = False
        sys.stdout.write(f"\r  {RED}FAIL{RESET}  {self.message}")
        if reason:
            sys.stdout.write(f" {GRAY}{reason}{RESET}")
        sys.stdout.write("\n")
        sys.stdout.flush()

    def update(self, message: str) -> None:
        self.message = message
        self._spin()

    def tick(self) -> None:
        if self._running:
            self._spin()


class ProgressBar:
    """Render an inline progress bar that overwrites itself."""

    def __init__(self, total: int, width: int = 30, label: str = ""):
        self.total = max(total, 1)
        self.width = width
        self.label = label
        self.current = 0
        self._start_time = time.time()
        self._last_draw = 0

    def update(self, current: int, extra: str = "") -> None:
        self.current = current
        now = time.time()
        if now - self._last_draw < 0.2 and current < self.total:
            return
        self._last_draw = now

        pct = min(current * 100 // self.total, 100)
        filled = pct * self.width // 100
        bar_str = "█" * filled + "░" * (self.width - filled)
        bar_colored = GREEN + bar_str + RESET

        label = f"{self.label}  " if self.label else ""
        line = (f"\r  {label}{GRAY}{current}/{self.total}{RESET} "
                f"{bar_colored} {pct:3d}%  {extra}")

        sys.stdout.write(line + " " * 20)
        sys.stdout.flush()

    def done(self, extra: str = "") -> None:
        self.update(self.total, extra)
        sys.stdout.write("\n")
        sys.stdout.flush()


OFF = " " * 4

def print_banner() -> None:
    """Print the G.A.M.M.A. STASH banner with version."""
    from gamma_mods_downloader import __version__, __app_name__

    W = 42  # total width including borders
    inner = W - 2  # usable width inside box

    # Center the title line
    title = f"{__app_name__}  v{__version__}"
    pad = (inner - 3 - len(title))  # 3 spaces left margin
    if pad < 1:
        pad = 1

    tagline = "Batch download G.A.M.M.A. mods"
    pad2 = (inner - 3 - len(tagline))
    if pad2 < 1:
        pad2 = 1

    top = f"{GREEN}   {BOX_TL}{BOX_H * W}{BOX_TR}{RESET}"
    ln1 = f"{GREEN}   {BOX_V}   {AMBER}{BOLD}{title}{RESET}{GREEN}{' ' * pad}{BOX_V}{RESET}"
    ln2 = f"{GREEN}   {BOX_V}   {GRAY}{tagline}{' ' * pad2}{GREEN}{BOX_V}{RESET}"
    bot = f"{GREEN}   {BOX_BL}{BOX_H * W}{BOX_BR}{RESET}"

    print(f"\n{top}\n{ln1}\n{ln2}\n{bot}\n")


def print_status_bar(flaresolverr_url: str = "", fs_version: str = "",
                     gamma_path: str = "", mods_total: int = 0, mods_ok: int = 0) -> None:
    """Show persistent status bar with app state."""
    from gamma_mods_downloader import __app_name__, __version__
    W = 54
    print(f"\n{GREEN}{DIM}{BOX_H * W}{RESET}")

    name_line = f" {__app_name__} v{__version__}"
    print(f"{GREEN}{BOLD}{name_line}{RESET}")

    if flaresolverr_url:
        fs_url_short = flaresolverr_url.replace("/v1", "")
        fs_info = f"{GREEN}Connected{RESET}  {fs_url_short}"
        if fs_version:
            fs_info += f"  {DIM}({fs_version}){RESET}"
    else:
        fs_info = f"{RED}Not configured{RESET}"
    print(f" {GRAY}Flaresolverr:{RESET} {fs_info}")

    if gamma_path:
        m = f"{mods_total} mods"
        if mods_ok:
            m += f", {mods_ok} OK"
        print(f" {GRAY}GAMMA:{RESET}       {gamma_path}  {DIM}({m}){RESET}")
    else:
        print(f" {GRAY}GAMMA:{RESET}       {RED}Not configured{RESET}")

    print(f"{GREEN}{DIM}{BOX_H * W}{RESET}\n")


def print_header(text: str) -> None:
    print(f"\n{GREEN}{DIM}{BOX_H * 52}{RESET}")
    print(f"{GREEN}{BOLD}  {text}{RESET}")
    print(f"{GREEN}{DIM}{BOX_H * 52}{RESET}\n")


def print_section(text: str) -> None:
    print(f"\n{AMBER}{BOLD}  >> {text}{RESET}")


def print_ok(text: str) -> None:
    print(f"  {GREEN}[OK]{RESET} {text}")


def print_error(text: str) -> None:
    print(f"  {RED}[!!]{RESET} {text}")


def print_warn(text: str) -> None:
    print(f"  {AMBER}[**]{RESET} {text}")


def print_info(text: str) -> None:
    print(f"  {CYAN}>>{RESET} {text}")


def print_field(label: str, value: str) -> None:
    print(f"  {GRAY}{label}:{RESET} {WHITE}{value}{RESET}")


def print_divider() -> None:
    print(f"{GRAY}{DIM}{BOX_H * 56}{RESET}")
