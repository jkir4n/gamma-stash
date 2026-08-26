"""
Interactive first-run setup wizard.

Checks system dependencies, configures Flaresolverr (manual IP or self-host
via Docker), locates the GAMMA installation, and starts the download.
"""

import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

from .terminal import (
    GREEN, AMBER, RED, CYAN, GRAY, DARK_GRAY, WHITE, DIM, BOLD, RESET,
    Spinner, ProgressBar,
    print_banner, print_header, print_section,
    print_ok, print_error, print_warn, print_info, print_field, print_divider,
    SPINNER_FRAMES,
)


_REQUIRED_DEPS = ["curl"]
_OPTIONAL_DEPS = ["docker"]

_GAMMA_MODS_RELATIVE = [
    os.path.join(".Grok's Modpack Installer", "mods.txt"),
    "mods.txt",
]


def _is_windows() -> bool:
    return sys.platform == "win32"


# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

def _offer_relaunch() -> None:
    """Tell user to restart the app after PATH-changing install."""
    print()
    print_info("Dependency installed. Please restart G.A.M.M.A. STASH for changes to take effect.")
    print(f"  {GRAY}The app will now exit. Double-click gamma-stash.exe to run again.{RESET}")
    print()
    if sys.stdout.isatty():
        try:
            input(f"{GRAY}Press Enter to exit ...{RESET}")
        except EOFError:
            pass
    sys.exit(0)


def check_dependency(name: str) -> Tuple[bool, str]:
    try:
        result = subprocess.run(
            [name, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            out = result.stdout.strip() or result.stderr.strip()
            return True, out.split("\n")[0]
        return False, result.stderr.strip() or "unknown error"
    except FileNotFoundError:
        return False, "not found on PATH"
    except Exception as e:
        return False, str(e)


def check_all_dependencies() -> Tuple[bool, List[str], List[str]]:
    missing_required = []
    missing_optional = []
    for dep in _REQUIRED_DEPS:
        ok, _ = check_dependency(dep)
        if not ok:
            missing_required.append(dep)
    for dep in _OPTIONAL_DEPS:
        ok, _ = check_dependency(dep)
        if not ok:
            missing_optional.append(dep)
    return len(missing_required) == 0, missing_required, missing_optional


def _prompt_yes_no(question: str) -> bool:
    while True:
        answer = input(f"  {AMBER}?{RESET} {question} {DIM}(y/n){RESET} ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def _install_curl() -> bool:
    """Auto-install curl via winget on Windows. Returns True if installed."""
    print()
    if _is_windows():
        print_info("Installing curl via winget ...")
        result = subprocess.run(
            ["winget", "install", "--id", "cURL.cURL", "--silent", "--accept-package-agreements"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            print_ok("curl installed. Restart your terminal if needed.")
            return True
        print_warn("Could not auto-install curl.")
        print_info(f"Download from: {GRAY}https://curl.se/windows/{RESET}")
    else:
        print_info("Install curl via your package manager:")
        print(f"  {GRAY}Ubuntu/Debian:  sudo apt install curl{RESET}")
        print(f"  {GRAY}Fedora:         sudo dnf install curl{RESET}")
        print(f"  {GRAY}macOS:          brew install curl{RESET}")
    print()
    return False


def _install_docker() -> bool:
    """Auto-install Docker via winget on Windows. Returns True if installed."""
    print()
    if _is_windows():
        print_info("Installing Docker Desktop via winget ...")
        result = subprocess.run(
            ["winget", "install", "--id", "Docker.DockerDesktop", "--silent", "--accept-package-agreements"],
            capture_output=False, timeout=600,
        )
        if result.returncode == 0:
            print_ok("Docker installed. Restart your terminal if needed.")
            return True
        print_warn("Could not auto-install Docker.")
        print_info("Download from: https://docs.docker.com/desktop/setup/install/windows-install/")
    elif sys.platform == "darwin":
        print_info("Install Docker Desktop from:")
        print(f"  {GRAY}https://docs.docker.com/desktop/setup/install/mac-install/{RESET}")
    else:
        print_info("Install Docker via your package manager:")
        print(f"  {GRAY}Ubuntu/Debian:  sudo apt install docker.io{RESET}")
        print(f"  {GRAY}Fedora:         sudo dnf install docker{RESET}")
        print()
        print_info("Then add your user to the docker group:")
        print(f"  {GRAY}sudo usermod -aG docker {os.environ.get('USER', '$USER')}{RESET}")
        print_info("Log out and back in for the change to take effect.")
    print()
    return False


def handle_dependencies() -> bool:
    print_section("Checking System Dependencies")

    spinner = Spinner("Checking required tools...")
    spinner.start()
    time.sleep(0.3)
    all_ok, missing_required, missing_optional = check_all_dependencies()
    spinner.stop("OK" if all_ok else None)

    if not all_ok:
        print()
        for dep in _REQUIRED_DEPS:
            ok, ver = check_dependency(dep)
            if ok:
                print_ok(f"{dep}  {DIM}{ver}{RESET}")
            else:
                print_error(f"{dep}  {DIM}not found{RESET}")
                for d in missing_required:
                    if d == dep:
                        if _prompt_yes_no("Install missing dependencies?"):
                            if dep == "curl":
                                if _install_curl():
                                    _offer_relaunch()
                            print("After installing, re-run this tool.")
                            return False
                        else:
                            print_error("Cannot continue without required dependencies.")
                            return False
    else:
        for dep in _REQUIRED_DEPS:
            _, ver = check_dependency(dep)
            print_ok(f"{dep}  {DIM}{ver}{RESET}")

    return True


# ---------------------------------------------------------------------------
# Flaresolverr
# ---------------------------------------------------------------------------

def validate_flaresolverr(url: str, timeout_sec: int = 10) -> Tuple[bool, str]:
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"

    payload = json.dumps({
        "cmd": "request.get",
        "url": "https://www.google.com",
        "maxTimeout": timeout_sec * 1000,
    }).encode()

    try:
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=timeout_sec + 10)
        data = json.loads(resp.read())
        if data.get("status") == "ok":
            version = data.get("version", "unknown")
            return True, f"Flaresolverr v{version}"
        return False, f"Unexpected response: {data.get('message', 'no status')}"
    except URLError:
        return False, "Cannot reach this address"
    except Exception as e:
        return False, str(e)


def setup_manual_flaresolverr() -> Optional[str]:
    print()
    print_info("Enter the Flaresolverr address.")
    print(f"  {DIM}Example:{RESET} {GRAY}http://192.168.1.50:8191/{RESET}")
    print(f"  {DIM}Press Enter on empty line to go back.{RESET}")
    print()

    while True:
        url = input(f"  {AMBER}Flaresolverr URL{RESET} {DIM}> {RESET}").strip()
        if not url:
            return None

        if not url.startswith("http"):
            print_error("URL must start with http:// or https://")
            continue

        spinner = Spinner(f"Testing {GRAY}{url}{RESET} ...")
        spinner.start()
        ok, msg = validate_flaresolverr(url)
        if ok:
            spinner.stop("OK")
            print_ok(msg)
            return url.rstrip("/") + "/v1"
        else:
            spinner.fail(msg)
            if not _prompt_yes_no("Try again?"):
                return None


def _find_docker() -> Optional[str]:
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return "docker"
    except FileNotFoundError:
        pass
    return None


def _docker_pull(image: str) -> bool:
    print_info(f"Pulling {image} ...")
    try:
        result = subprocess.run(
            ["docker", "pull", image],
            capture_output=False, timeout=300,
        )
        return result.returncode == 0
    except Exception as e:
        print_error(str(e))
        return False


def _docker_container_exists(name: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        return name in result.stdout.splitlines()
    except Exception:
        return False


def _docker_container_running(name: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        return name in result.stdout.splitlines()
    except Exception:
        return False


def _docker_run_flaresolverr() -> bool:
    if not _docker_pull("flaresolverr/flaresolverr"):
        return False

    print_info("Starting Flaresolverr container ...")
    try:
        result = subprocess.run(
            [
                "docker", "run", "-d",
                "--name", "flaresolverr",
                "-p", "8191:8191",
                "flaresolverr/flaresolverr",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print_ok(f"Container started: {result.stdout.strip()}")
            return True

        stderr = result.stderr.strip()
        if "docker daemon" in stderr.lower() or "cannot connect" in stderr.lower():
            print_error("Docker daemon is not running.")
            print_info("Please start Docker Desktop from the Start menu, then try again.")
            print(f"  {GRAY}Wait for the Docker engine to fully start before proceeding.{RESET}")
        else:
            print_error(stderr)
        return False
    except Exception as e:
        err_str = str(e)
        if "docker" in err_str.lower() and ("not running" in err_str.lower() or "connect" in err_str.lower()):
            print_error("Docker daemon is not running.")
            print_info("Please start Docker Desktop and try again.")
        else:
            print_error(str(e))
        return False


def _docker_daemon_ok() -> bool:
    """Check if the Docker daemon is running and reachable."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _check_virtualization() -> Optional[str]:
    """
    Check if WSL2 or Hyper-V is available for Docker.
    Returns 'wsl2', 'hyperv', or None if neither.
    """
    try:
        result = subprocess.run(
            ["wsl", "--status"],
            capture_output=True, text=True, timeout=10,
        )
        if "Default Version: 2" in result.stdout:
            return "wsl2"
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "(Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V).State"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and "Enabled" in result.stdout:
            return "hyperv"
    except Exception:
        pass

    return None


def setup_docker_flaresolverr() -> Optional[str]:
    print()

    docker_path = _find_docker()

    if docker_path:
        if not _docker_daemon_ok():
            print_error("Docker daemon is not running.")
            print_info("Please start Docker Desktop from the Start menu and wait for it to fully start.")
            print()
            if _prompt_yes_no("Retry?"):
                return setup_docker_flaresolverr()
            return None

        print_ok("Docker is available")

        # Already running — grab URL automatically, no prompts
        if _docker_container_running("flaresolverr"):
            print_ok("Flaresolverr container is already running.")
            url = "http://localhost:8191/v1"
            spinner = Spinner("Verifying Flaresolverr ...")
            spinner.start()
            ok, msg = validate_flaresolverr(url, timeout_sec=5)
            if ok:
                spinner.stop("OK")
                print_ok(msg)
                return url
            spinner.stop(None)
            return url

        # Container exists but stopped — ask to start
        if _docker_container_exists("flaresolverr"):
            if not _prompt_yes_no("Flaresolverr container exists but is stopped. Start it?"):
                return None
            print_info("Starting container ...")
            subprocess.run(["docker", "start", "flaresolverr"],
                           capture_output=True, timeout=30)
            return _wait_for_flaresolverr("http://localhost:8191/v1")

        # No container — ask to pull and run
        if not _prompt_yes_no("No flaresolverr container found. Pull and run one now?"):
            return None
        if not _docker_run_flaresolverr():
            return None
        return _wait_for_flaresolverr("http://localhost:8191/v1")

    # Docker not installed — check virtualization, then offer to install
    print_error("Docker is not installed or not on PATH.")

    if _is_windows():
        vtype = _check_virtualization()
        if not vtype:
            print()
            print_info("Docker Desktop requires WSL 2 or Hyper-V. Neither is currently enabled.")
            print(f"  {AMBER}1.{RESET} Enable WSL 2 (recommended)")
            print(f"  {AMBER}2.{RESET} Enable Hyper-V")
            print(f"  {AMBER}3.{RESET} Skip (manual setup)")
            print()
            choice = input(f"  {AMBER}Option{RESET} {DIM}(1/2/3)> {RESET}").strip()
            if choice == "1":
                print_info("Enabling WSL 2 ...")
                result = subprocess.run(
                    ["wsl", "--install", "--no-distribution"],
                    capture_output=False, timeout=300,
                )
                if result.returncode == 0:
                    print_ok("WSL 2 enabled. You must restart your PC before Docker will work.")
                else:
                    print_warn("Could not enable WSL 2 automatically.")
                    print_info("Run in admin PowerShell: wsl --install")
                _offer_relaunch()
                return None
            elif choice == "2":
                print_info("Enabling Hyper-V ...")
                result = subprocess.run(
                    ["powershell", "-Command",
                     "Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All"],
                    capture_output=False, timeout=300,
                )
                if result.returncode == 0:
                    print_ok("Hyper-V enabled. You must restart your PC before Docker will work.")
                else:
                    print_warn("Could not enable Hyper-V automatically.")
                    print_info("Run in admin PowerShell: Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All")
                _offer_relaunch()
                return None
            else:
                print_info("See the README for manual WSL 2 / Hyper-V setup instructions.")
                return None
        else:
            print_ok(f"Virtualization ready ({vtype})")
    if not _prompt_yes_no("Install Docker and set up Flaresolverr?"):
        return None

    if _install_docker():
        # winget installed — need relaunch for PATH to pick up docker
        if _find_docker():
            print_ok("Docker is available")
            if not _docker_run_flaresolverr():
                return None
            return _wait_for_flaresolverr("http://localhost:8191/v1")
        else:
            print_info("Docker installed but requires a fresh terminal session.")
            _offer_relaunch()
            return None

    # Auto-install failed or not on Windows — manual fallback
    input("  Press Enter after installing Docker ...")
    docker_path = _find_docker()
    if not docker_path:
        print_error("Docker still not found. Please install and try again.")
        return None

    print_ok("Docker is available")
    if not _docker_run_flaresolverr():
        return None
    return _wait_for_flaresolverr("http://localhost:8191/v1")


def _wait_for_flaresolverr(url: str) -> str:
    """Wait for Flaresolverr to be ready. Returns the URL."""
    spinner = Spinner("Waiting for Flaresolverr to be ready ...")
    spinner.start()
    for _ in range(30):
        ok, msg = validate_flaresolverr(url, timeout_sec=5)
        if ok:
            spinner.stop("OK")
            print_ok(msg)
            return url
        time.sleep(2)
        spinner.tick()

    spinner.stop(None)
    print_warn("Flaresolverr did not respond in time. It may still be starting.")
    print_info(f"URL: {url}")
    return url


def configure_flaresolverr() -> Optional[Tuple[str, str]]:
    """
    Returns (url, mode) on success — mode is 'manual', 'docker', or 'browser'.
    """
    print_header("Download & Cloudflare Strategy")
    print_info("Select how to handle ModDB Cloudflare challenges:")
    print()
    print(f"  {AMBER}1.{RESET} Remote / Existing Flaresolverr IP")
    print(f"  {AMBER}2.{RESET} Self-host Flaresolverr via Docker (this machine)")
    print(f"  {AMBER}3.{RESET} Browser-Assisted Mode {GREEN}(Zero Docker / Zero Setup){RESET}")
    print()

    while True:
        choice = input(f"  {AMBER}Option{RESET} {DIM}(1/2/3)> {RESET}").strip()
        if choice == "1":
            url = setup_manual_flaresolverr()
            return (url, "manual") if url else None
        elif choice == "2":
            url = setup_docker_flaresolverr()
            return (url, "docker") if url else None
        elif choice == "3":
            print_ok("Browser-Assisted Mode selected (watcher will monitor Downloads folder).")
            return ("", "browser")
        else:
            print_error("Enter 1, 2, or 3.")


# ---------------------------------------------------------------------------
# GAMMA folder location & Auto-Discovery
# ---------------------------------------------------------------------------

def _find_mods_txt(gamma_path: str) -> Optional[str]:
    for relative in _GAMMA_MODS_RELATIVE:
        candidate = os.path.join(gamma_path, relative)
        if os.path.isfile(candidate):
            return candidate
    return None


def _is_gamma_folder(path: str) -> Tuple[bool, str]:
    if not os.path.isdir(path):
        return False, f"'{path}' is not a valid directory"

    mods_path = _find_mods_txt(path)
    if mods_path:
        try:
            from .downloader import LinksFile
            entries = LinksFile(mods_path).read()
            if entries:
                return True, f"Found mods.txt with {len(entries)} mods"
            return False, "mods.txt exists but contains no mod entries"
        except Exception as e:
            return False, f"Error reading mods.txt: {e}"

    return False, "No mods.txt found in this folder"


def check_disk_space(path: str, required_gb: float = 25.0) -> Tuple[bool, float, float]:
    """Check available disk space in GB on the drive of the given path."""
    import shutil
    try:
        target = path if os.path.exists(path) else os.path.dirname(os.path.abspath(path))
        while not os.path.exists(target) and os.path.dirname(target) != target:
            target = os.path.dirname(target)
        usage = shutil.disk_usage(target)
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        return free_gb >= required_gb, free_gb, total_gb
    except Exception:
        return True, 0.0, 0.0


def discover_gamma_paths() -> List[Dict[str, Any]]:
    """Scan system drives and common paths to auto-detect GAMMA installations."""
    found: List[Dict[str, Any]] = []
    candidates = []

    if _is_windows():
        import string
        # Check all available drive letters
        for letter in string.ascii_uppercase:
            drive_root = f"{letter}:\\"
            if os.path.exists(drive_root):
                candidates.extend([
                    os.path.join(drive_root, "GAMMA"),
                    os.path.join(drive_root, "G.A.M.M.A"),
                    os.path.join(drive_root, "Anomaly"),
                    os.path.join(drive_root, "STALKER Anomaly"),
                    os.path.join(drive_root, "Games", "GAMMA"),
                    os.path.join(drive_root, "Games", "Anomaly"),
                ])
    else:
        home = os.path.expanduser("~")
        candidates.extend([
            os.path.join(home, "GAMMA"),
            os.path.join(home, "gamma"),
            os.path.join(home, ".local", "share", "gamma"),
        ])

    seen = set()
    for c in candidates:
        norm = os.path.normpath(c)
        if norm in seen or not os.path.isdir(norm):
            continue
        seen.add(norm)
        mods_txt = _find_mods_txt(norm)
        if mods_txt:
            _, free_gb, total_gb = check_disk_space(norm)
            found.append({
                "path": norm,
                "mods_txt": mods_txt,
                "free_gb": free_gb,
                "total_gb": total_gb,
            })

    return found


def get_windows_downloads_dir() -> str:
    """Detect the current Windows user's Downloads folder, falling back to ~/Downloads."""
    if _is_windows():
        try:
            import winreg
            sub_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
                    expanded = os.path.expandvars(val)
                    if os.path.isdir(expanded):
                        return expanded
                except FileNotFoundError:
                    val, _ = winreg.QueryValueEx(key, "{7D83EE9B-2244-4E70-B1F5-54E342E45351}")
                    expanded = os.path.expandvars(val)
                    if os.path.isdir(expanded):
                        return expanded
        except Exception:
            pass
    dl = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.isdir(dl):
        return dl
    return os.path.expanduser("~")


def play_pda_cue() -> None:
    """Play a classic high-tech S.T.A.L.K.E.R. PDA two-tone alert chime."""
    if not _is_windows():
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass
        return
    try:
        import winsound
        # High-tech double beep: 1800 Hz then 2400 Hz
        winsound.Beep(1800, 110)
        winsound.Beep(2400, 140)
    except Exception:
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard using native Windows clip.exe or fallback."""
    if not text:
        return False
    try:
        import subprocess
        subprocess.run(["clip.exe"], input=text.encode("utf-8"), check=True)
        return True
    except Exception:
        return False


def fetch_latest_mods_txt(target_dir: str) -> Optional[str]:
    """Fetch official G.A.M.M.A. modpack manifest from upstream GitHub repository."""
    import urllib.request
    urls = [
        "https://raw.githubusercontent.com/Grokitach/Stalker_GAMMA/main/G.A.M.M.A/modpack_data/modpack_maker_list.txt",
    ]
    target_path = os.path.join(target_dir, "mods.txt")
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "gamma-stash"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                if len(data) > 1000:
                    os.makedirs(target_dir, exist_ok=True)
                    with open(target_path, "wb") as f:
                        f.write(data)
                    return target_path
        except Exception:
            continue
    return None


def locate_gamma_folder() -> Optional[str]:
    print_header("Locate GAMMA Installation")

    # Check auto-discovered paths
    discovered = discover_gamma_paths()
    if discovered:
        print_info("Auto-discovered GAMMA installation(s):")
        for i, d in enumerate(discovered, 1):
            print(f"  {AMBER}{i}.{RESET} {WHITE}{d['path']}{RESET} {DIM}(Free: {d['free_gb']:.1f} GB){RESET}")
        print(f"  {AMBER}{len(discovered)+1}.{RESET} Enter path manually")
        print()
        choice = input(f"  {AMBER}Select option{RESET} {DIM}(1-{len(discovered)+1})> {RESET}").strip()
        try:
            c_idx = int(choice)
            if 1 <= c_idx <= len(discovered):
                selected = discovered[c_idx - 1]
                print_ok(f"Selected: {selected['path']}")
                return selected["mods_txt"]
        except ValueError:
            pass

    print_info("Enter the path to your GAMMA installation folder.")
    print(f"  {DIM}Example:{RESET} {GRAY}D:\\\\GAMMA{RESET}")
    print(f"  {DIM}The folder should contain a mods.txt file.{RESET}")
    print(f"  {DIM}Press Enter on an empty line to cancel.{RESET}")
    print()

    while True:
        path = input(f"  {AMBER}GAMMA folder{RESET} {DIM}> {RESET}").strip().strip('"')
        if not path:
            if _prompt_yes_no("Cancel and exit setup?"):
                return None
            continue

        expanded = os.path.expandvars(os.path.expanduser(path))

        spinner = Spinner(f"Validating {GRAY}{expanded}{RESET} ...")
        spinner.start()
        is_gamma, reason = _is_gamma_folder(expanded)
        if is_gamma:
            mods_path = _find_mods_txt(expanded)
            spinner.stop("OK")
            print_ok(reason)
            return mods_path
        else:
            spinner.fail(reason)
            print_error("Please enter a valid GAMMA folder path.")
            print()


def _find_downloads_folder(mods_path: str) -> str:
    mods_dir = os.path.dirname(os.path.abspath(mods_path))

    candidates = [
        os.path.join(mods_dir, "downloads"),
        os.path.join(os.path.dirname(mods_dir), "downloads"),
        os.path.join(os.path.dirname(os.path.dirname(mods_dir)), "downloads"),
    ]

    for path in candidates:
        if os.path.isdir(path):
            return path

    return os.path.join(os.path.dirname(mods_dir), "downloads")


# ---------------------------------------------------------------------------
# Modlist & download
# ---------------------------------------------------------------------------

def scan_modlist(mods_path: str, download_dir: str,
                 log_cb: Optional[Any] = None,
                 progress_cb: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    from .downloader import LinksFile, load_hash_cache, save_hash_cache, cached_md5_file

    if not log_cb:
        print_header("Scanning Modlist")
        print_field("Mods file", mods_path)
        print_field("Download dir", download_dir)
        print()
    else:
        log_cb(f"Scanning modlist: {mods_path}")

    try:
        links = LinksFile(mods_path)
        entries = links.read()
    except FileNotFoundError:
        if not log_cb:
            print_error(f"mods.txt not found at {mods_path}")
        else:
            log_cb(f"[ERROR] mods.txt not found at {mods_path}")
        return None
    except Exception as e:
        if not log_cb:
            print_error(f"Failed to parse mods.txt: {e}")
        else:
            log_cb(f"[ERROR] Failed to parse mods.txt: {e}")
        return None

    cache = load_hash_cache(download_dir)

    total = len(entries)
    already_ok = 0
    need_download = 0
    need_redownload = 0
    no_md5 = 0
    moddb = 0
    github = 0

    cats, entries_by_cat = links.read_with_categories()
    cat_pending = [0] * len(cats)
    cat_total = [len(ec) for ec in entries_by_cat]

    filename_to_cat = {}
    for ci, cat_entries in enumerate(entries_by_cat):
        for e in cat_entries:
            filename_to_cat[e["filename"]] = ci

    bar = None if log_cb else ProgressBar(total, width=36, label=f"{CYAN}Checking{RESET}")
    spinner_idx = 0

    ok_filenames: List[str] = []

    for idx, entry in enumerate(entries):
        spinner_idx += 1
        frame = SPINNER_FRAMES[spinner_idx % len(SPINNER_FRAMES)]

        source = entry.get("source", "MODDB")
        if source == "MODDB":
            moddb += 1
        elif source == "GITHUB":
            github += 1

        filename = entry["filename"]
        expected_md5 = entry.get("expected_md5", "")
        fpath = os.path.join(download_dir, filename)

        if os.path.exists(fpath):
            if expected_md5:
                actual = cached_md5_file(fpath, cache)
                if actual == expected_md5:
                    already_ok += 1
                    ok_filenames.append(filename)
                else:
                    need_redownload += 1
                    ci = filename_to_cat.get(filename)
                    if ci is not None:
                        cat_pending[ci] += 1
            else:
                if os.path.getsize(fpath) > 100:
                    already_ok += 1
                    ok_filenames.append(filename)
                    no_md5 += 1
                else:
                    need_download += 1
                    ci = filename_to_cat.get(filename)
                    if ci is not None:
                        cat_pending[ci] += 1
        else:
            need_download += 1
            ci = filename_to_cat.get(filename)
            if ci is not None:
                cat_pending[ci] += 1

        if bar:
            extra = f"  {frame} {GREEN}{already_ok}{RESET}/{GRAY}ok{RESET}"
            bar.update(idx + 1, extra)
        elif progress_cb:
            progress_cb(idx + 1, total, filename)

    if bar:
        bar.done()
        print()

    save_hash_cache(download_dir, cache)

    # Summary
    if not log_cb:
        print_field("Total mods", str(total))
        print_ok(f"Already verified: {already_ok}")
        if need_download:
            print_info(f"Need download: {need_download}")
        if need_redownload:
            print_warn(f"Need re-download: {need_redownload}")

        # Category breakdown with bar chart
        print(f"\n  {AMBER}{BOLD}By category:{RESET}")
        max_name = max((len(c) for c in cats), default=20)
        for i, cat_name in enumerate(cats):
            pending = cat_pending[i]
            ct = cat_total[i]
            if pending > 0:
                bar_w = min(pending * 20 // max(ct, 1), 20) or 1
                pbar = RED + "█" * bar_w + RESET
                print(f"    {cat_name:<{max_name+2}} {pbar} {AMBER}{pending}{RESET}/{ct}")
            else:
                bar_w = min(ct * 20 // max(ct, 1), 20)
                pbar = GREEN + "█" * bar_w + RESET
                print(f"    {cat_name:<{max_name+2}} {pbar} {DIM}{ct}/{ct}{RESET}")

    if need_download == 0 and need_redownload == 0:
        if not log_cb:
            print()
            print_ok("All mods are already downloaded and verified!")
        return {
            "mods_path": mods_path,
            "total": total,
            "already_ok": already_ok,
            "need_download": 0,
            "need_redownload": 0,
            "moddb": moddb,
            "github": github,
            "ok_filenames": ok_filenames,
        }

    return {
        "mods_path": mods_path,
        "total": total,
        "already_ok": already_ok,
        "need_download": need_download,
        "need_redownload": need_redownload,
        "moddb": moddb,
        "github": github,
        "entries": entries,
        "ok_filenames": ok_filenames,
    }


def run_download(config: Dict[str, Any], skip_filenames: Optional[frozenset] = None) -> int:
    from .downloader import Downloader
    downloader = Downloader(config)
    results = downloader.download_all(skip_filenames)
    return 0 if results["fail"] == 0 else 1


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def write_config(config_path: str, flaresolverr_url: str, links_file: str,
                 download_dir: str, fs_mode: str = "manual") -> None:
    import yaml

    config = {
        "links_file": links_file,
        "download_dir": download_dir,
        "download_delay": 2,
        "flaresolverr": {
            "url": flaresolverr_url,
            "timeout_ms": 60000,
            "mode": fs_mode,
        },
        "destination": {
            "local_path": download_dir,
        },
    }

    with open(config_path, "w", encoding="utf-8") as f:
        f.write("# Gamma Mods Downloader Configuration\n")
        f.write("# Generated by setup wizard.\n")
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
    print_ok(f"Config written to {os.path.abspath(config_path)}")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup_docker(interactive: bool = True, uninstall_docker: bool = False) -> bool:
    """
    Stop and remove the flaresolverr container and image.
    Optionally offers/performs Docker uninstall if requested.
    """
    if interactive:
        print_header("Cleanup")
    performed = False

    if _docker_container_exists("flaresolverr"):
        if interactive:
            print_info("Stopping flaresolverr container ...")
        subprocess.run(["docker", "stop", "flaresolverr"],
                       capture_output=True, timeout=30)

        if interactive:
            print_info("Removing flaresolverr container ...")
        subprocess.run(["docker", "rm", "flaresolverr"],
                       capture_output=True, timeout=30)

        if interactive:
            print_ok("Flaresolverr container stopped and removed.")
        performed = True
    else:
        if interactive:
            print_info("No flaresolverr container found.")

    if interactive:
        print_info("Removing Flaresolverr image ...")
    subprocess.run(["docker", "rmi", "flaresolverr/flaresolverr"],
                   capture_output=True, timeout=30)
    if interactive:
        print_ok("Flaresolverr image cleaned up.")

    should_uninstall = uninstall_docker
    if interactive:
        print()
        if _prompt_yes_no("Uninstall Docker Desktop from this machine?"):
            print()
            print_warn("Uninstalling Docker will remove it completely.")
            print_warn("If other applications depend on Docker, they will break.")
            if _prompt_yes_no("Are you sure you want to uninstall Docker?"):
                should_uninstall = True

    if not should_uninstall:
        return performed

    if interactive:
        print_info("Uninstalling Docker ...")

    if _is_windows():
        result = subprocess.run(
            ["winget", "uninstall", "Docker.DockerDesktop"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            if interactive:
                print_ok("Docker uninstalled via winget.")
            performed = True
        else:
            if interactive:
                print_warn("Could not uninstall Docker automatically.")
                print_info("Uninstall manually from Settings > Apps > Docker Desktop.")
    elif sys.platform == "darwin":
        if interactive:
            print_info("Remove Docker.app from /Applications to uninstall.")
    else:
        result = subprocess.run(
            ["sudo", "apt", "purge", "-y", "docker.io"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            if interactive:
                print_ok("Docker uninstalled.")
            performed = True
        else:
            result2 = subprocess.run(
                ["sudo", "apt", "purge", "-y", "docker-ce"],
                capture_output=True, text=True, timeout=120,
            )
            if result2.returncode == 0:
                if interactive:
                    print_ok("Docker uninstalled.")
                performed = True
            elif interactive:
                print_warn("Could not uninstall Docker automatically.")
                print_info("Run: sudo apt purge docker.io")

    return performed


# ---------------------------------------------------------------------------
# Main wizard
# ---------------------------------------------------------------------------

def should_run_setup(config_path: str = "config.yaml") -> bool:
    if not os.path.exists(config_path):
        return True

    try:
        from .config import load_config
        cfg = load_config(config_path)
        fs_url = cfg.get("flaresolverr", {}).get("url", "")
        if not fs_url:
            return True
        ok, _ = validate_flaresolverr(fs_url, timeout_sec=3)
        if not ok:
            print_warn(f"Flaresolverr at {fs_url} is not reachable.")
            return _prompt_yes_no("Re-run setup wizard?")
    except Exception:
        return True

    return False


def run_setup_wizard(gamma_dir: Optional[str] = None,
                     flaresolverr_url: Optional[str] = None,
                     mode: Optional[str] = None,
                     limit_rate: Optional[str] = None,
                     no_sound: bool = False,
                     category: Optional[str] = None,
                     browser_dir: Optional[str] = None,
                     yes: bool = False) -> int:
    print_banner()

    # Step 1: Dependencies
    if not handle_dependencies():
        return 1

    # Step 2: Flaresolverr / Bypass Strategy
    fs_mode = mode or "manual"
    fs_url = ""

    if mode == "browser":
        fs_mode = "browser"
        print_ok("Strategy: Browser-Assisted Mode (Zero Docker)")
    elif flaresolverr_url:
        fs_url = flaresolverr_url.rstrip("/") + ("/v1" if not flaresolverr_url.endswith("/v1") else "")
        ok, msg = validate_flaresolverr(fs_url)
        if not ok:
            print_error(f"Provided Flaresolverr URL failed check: {msg}")
            if not yes and not _prompt_yes_no("Continue anyway?"):
                return 1
        else:
            print_ok(f"Flaresolverr ready: {fs_url}")
    elif mode == "docker":
        fs_url = setup_docker_flaresolverr()
        fs_mode = "docker"
    else:
        fs_result = configure_flaresolverr()
        if not fs_result:
            print()
            print_error("A download strategy is required for ModDB downloads.")
            return 1
        fs_url, fs_mode = fs_result

    # Step 3: Locate GAMMA folder
    if gamma_dir:
        expanded = os.path.expandvars(os.path.expanduser(gamma_dir.strip('"')))
        mods_path = _find_mods_txt(expanded)
        if not mods_path:
            print_error(f"No mods.txt found at provided gamma-dir: {gamma_dir}")
            return 1
        print_ok(f"Using GAMMA path: {expanded}")
    else:
        mods_path = locate_gamma_folder()
        if not mods_path:
            print()
            print_error("GAMMA folder is required to find the mod list.")
            print_info("Run this tool again when you have GAMMA installed.")
            return 1

    downloads_dir = _find_downloads_folder(mods_path)
    os.makedirs(downloads_dir, exist_ok=True)
    print_field("Download folder", downloads_dir)

    # Pre-flight disk space check
    has_space, free_gb, total_gb = check_disk_space(downloads_dir, required_gb=25.0)
    if not has_space:
        print_warn(f"Low disk space! Drive has {free_gb:.1f} GB free (25+ GB recommended).")

    # Step 4: Scan modlist
    stats = scan_modlist(mods_path, downloads_dir)
    if stats is None:
        return 1

    need_total = stats["need_download"] + stats["need_redownload"]
    if need_total == 0:
        print()
        print_ok("All mods already downloaded and verified.")
        if not no_sound:
            play_pda_cue()
        return 0

    print()
    print_info(f"{need_total} mods need downloading ({GREEN}{stats['already_ok']} already OK{RESET}).")
    if not yes and not _prompt_yes_no("Start downloading now?"):
        return 0

    # Step 5: Download
    print_divider()

    skip_set = frozenset(stats.get("ok_filenames", []))

    config = {
        "links_file": mods_path,
        "download_dir": downloads_dir,
        "download_delay": 1,
        "max_concurrent": 3,
        "flaresolverr": {
            "url": fs_url,
            "timeout_ms": 60000,
        },
        "destination": {
            "local_path": downloads_dir,
        },
        "fs_mode": fs_mode,
        "browser_downloads_dir": browser_dir or get_windows_downloads_dir(),
        "limit_rate": limit_rate or "",
        "category_filter": category or "",
    }

    result = run_download(config, skip_set)

    if result == 0 and not no_sound:
        play_pda_cue()

    if fs_mode == "docker" and not yes:
        print()
        if _prompt_yes_no("Downloads complete. Clean up Flaresolverr container?"):
            cleanup_docker(interactive=True)

    return result
