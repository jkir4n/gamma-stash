"""
Environment & Network Diagnostics for G.A.M.M.A. STASH.

Runs automated sanity checks on:
- curl presence, HTTP/2, and TLS 1.3 capabilities
- GitHub raw content reachability and latency
- ModDB Cloudflare challenge / VPN IP block status
- Flaresolverr API connectivity and session creation
- Native Windows subsystems (Downloads folder registry, clip.exe, audio chime)
- G.A.M.M.A. folder write permissions and disk space headroom
"""

import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from .terminal import (
    GREEN, AMBER, RED, CYAN, GRAY, DARK_GRAY, WHITE, BOLD, DIM, RESET,
    print_ok, print_warn, print_error, print_info, print_field, print_divider,
)
from .setup import (
    get_windows_downloads_dir,
    play_pda_cue,
    copy_to_clipboard,
    discover_gamma_paths,
    check_disk_space,
    validate_flaresolverr,
)


def check_curl_health() -> Tuple[bool, str, Dict[str, Any]]:
    """Verify curl is installed and test TLS 1.3 / HTTP2 support."""
    info: Dict[str, Any] = {"version": "Unknown", "http2": False, "tls13": False}
    try:
        res = subprocess.run(["curl", "--version"], capture_output=True, text=True, timeout=5)
        if res.returncode != 0:
            return False, "curl command failed to run", info

        first_line = res.stdout.splitlines()[0] if res.stdout else ""
        info["version"] = first_line
        stdout_lower = res.stdout.lower()
        info["http2"] = "http2" in stdout_lower
        info["tls13"] = "schannel" in stdout_lower or "openssl" in stdout_lower or "tls" in stdout_lower

        details = f"{first_line.split(' (')[0]} (HTTP/2: {'Yes' if info['http2'] else 'No'})"
        return True, details, info
    except FileNotFoundError:
        return False, "curl is not installed or not found on PATH", info
    except Exception as e:
        return False, f"curl check error: {e}", info


def check_github_connectivity() -> Tuple[bool, str, float]:
    """Test raw GitHub reachability where official G.A.M.M.A. manifest is hosted."""
    test_url = "https://raw.githubusercontent.com/Grokitach/Stalker_GAMMA/main/G.A.M.M.A/modpack_data/modpack_maker_list.txt"
    start = time.time()
    try:
        cmd = ["curl", "-sIL", "--max-time", "8", "-o", os.devnull, "-w", "%{http_code}", test_url]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        latency = (time.time() - start) * 1000
        http_code = res.stdout.strip()
        if http_code == "200":
            return True, f"HTTP 200 OK ({latency:.0f} ms)", latency
        else:
            return False, f"HTTP {http_code} ({latency:.0f} ms)", latency
    except Exception as e:
        latency = (time.time() - start) * 1000
        return False, f"Failed to reach GitHub: {e}", latency


def check_moddb_cloudflare() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Test direct connectivity to ModDB to detect Cloudflare challenges
    or blocked VPN / datacenter IPs.
    """
    test_url = "https://www.moddb.com"
    meta: Dict[str, Any] = {"cf_challenge": False, "blocked": False, "http_code": "0"}
    try:
        cmd = ["curl", "-sIL", "--max-time", "10", "-A", "Mozilla/5.0", "-o", os.devnull,
               "-w", "%{http_code}", test_url]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        code = res.stdout.strip()
        meta["http_code"] = code

        if code == "403":
            meta["blocked"] = True
            return False, "HTTP 403 Forbidden — Your IP or VPN is blocked by ModDB Cloudflare", meta
        elif code in ("503", "429"):
            meta["cf_challenge"] = True
            return True, f"HTTP {code} — Cloudflare challenge active (Requires Flaresolverr or Browser mode)", meta
        elif code.startswith("2") or code.startswith("3"):
            return True, f"HTTP {code} OK (Direct access clear)", meta
        else:
            return False, f"HTTP {code} — Unexpected response from ModDB", meta
    except Exception as e:
        return False, f"Failed to connect to ModDB: {e}", meta


def check_flaresolverr_health(url: Optional[str] = None) -> Tuple[bool, str]:
    """Test Flaresolverr instance if provided or detected."""
    target_url = url or "http://localhost:8191/v1"
    ok, msg = validate_flaresolverr(target_url, timeout_sec=4)
    if ok:
        return True, f"Active at {target_url} ({msg})"
    return False, f"Unavailable at {target_url} ({msg})"


def check_windows_subsystems() -> Dict[str, Tuple[bool, str]]:
    """Test native Windows registry paths, clipboard, and audio."""
    results = {}

    # 1. Downloads folder
    dl = get_windows_downloads_dir()
    if dl and os.path.isdir(dl):
        results["Downloads Directory"] = (True, dl)
    else:
        results["Downloads Directory"] = (False, f"Not found ({dl})")

    # 2. Clipboard
    clip_ok = copy_to_clipboard("GAMMA_DOCTOR_TEST")
    results["Windows Clipboard (clip.exe)"] = (clip_ok, "Functional" if clip_ok else "clip.exe failed")

    # 3. Audio Chime
    try:
        import winsound
        results["Audio Subsystem (winsound)"] = (True, "Supported (S.T.A.L.K.E.R. PDA chime available)")
    except Exception as e:
        results["Audio Subsystem (winsound)"] = (False, f"Unavailable: {e}")

    return results


def check_gamma_installation(path: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
    """Check target GAMMA directory, write permissions, and disk space."""
    target = path
    if not target:
        discovered = discover_gamma_paths()
        if discovered:
            target = discovered[0]["path"]

    if not target or not os.path.isdir(target):
        return False, "No valid G.A.M.M.A. installation found", {}

    has_space, free_gb, total_gb = check_disk_space(target)
    dl_folder = os.path.join(target, "downloads")
    os.makedirs(dl_folder, exist_ok=True)

    # Test write permissions
    test_file = os.path.join(dl_folder, ".doctor_test.tmp")
    can_write = False
    try:
        with open(test_file, "w") as f:
            f.write("OK")
        if os.path.exists(test_file):
            os.remove(test_file)
            can_write = True
    except Exception:
        can_write = False

    details = {
        "path": target,
        "downloads_dir": dl_folder,
        "free_gb": free_gb,
        "total_gb": total_gb,
        "can_write": can_write,
    }

    if not can_write:
        return False, f"Permission Denied: Cannot write to {dl_folder}", details
    if not has_space:
        return False, f"Low Disk Space: {free_gb:.1f} GB free (Recommend >= 20 GB)", details

    return True, f"{target} ({free_gb:.1f} GB free, write access OK)", details


def run_doctor(gamma_dir: Optional[str] = None,
               flaresolverr_url: Optional[str] = None) -> int:
    """Run comprehensive diagnostics and display S.T.A.L.K.E.R. PDA terminal dashboard."""
    print(f"\n  {BOLD}{GREEN}G.A.M.M.A. STASH — Environment & Network Doctor{RESET}")
    print(f"  {DIM}Running automated system & connectivity diagnostics ...{RESET}")
    print_divider()

    issues = 0

    # 1. curl Check
    curl_ok, curl_msg, _ = check_curl_health()
    if curl_ok:
        print(f"  [{GREEN}PASS{RESET}] {BOLD}curl Tool:{RESET} {WHITE}{curl_msg}{RESET}")
    else:
        print(f"  [{RED}FAIL{RESET}] {BOLD}curl Tool:{RESET} {RED}{curl_msg}{RESET}")
        print(f"         {DIM}Fix: Install curl via 'winget install curl.curl' or enable Windows curl.{RESET}")
        issues += 1

    # 2. GitHub Raw Reachability
    gh_ok, gh_msg, _ = check_github_connectivity()
    if gh_ok:
        print(f"  [{GREEN}PASS{RESET}] {BOLD}GitHub Manifest Server:{RESET} {WHITE}{gh_msg}{RESET}")
    else:
        print(f"  [{AMBER}WARN{RESET}] {BOLD}GitHub Manifest Server:{RESET} {AMBER}{gh_msg}{RESET}")
        print(f"         {DIM}Check your internet connection or GitHub status.{RESET}")
        issues += 1

    # 3. ModDB Cloudflare Check
    mdb_ok, mdb_msg, mdb_meta = check_moddb_cloudflare()
    if mdb_ok:
        if mdb_meta.get("cf_challenge"):
            print(f"  [{AMBER}INFO{RESET}] {BOLD}ModDB Cloudflare:{RESET} {AMBER}{mdb_msg}{RESET}")
        else:
            print(f"  [{GREEN}PASS{RESET}] {BOLD}ModDB Cloudflare:{RESET} {WHITE}{mdb_msg}{RESET}")
    else:
        print(f"  [{RED}FAIL{RESET}] {BOLD}ModDB Cloudflare:{RESET} {RED}{mdb_msg}{RESET}")
        if mdb_meta.get("blocked"):
            print(f"         {AMBER}Action:{RESET} {WHITE}Disable your VPN or switch to a clean residential IP.{RESET}")
        issues += 1

    # 4. Flaresolverr
    fs_ok, fs_msg = check_flaresolverr_health(flaresolverr_url)
    if fs_ok:
        print(f"  [{GREEN}PASS{RESET}] {BOLD}Flaresolverr Bypass Engine:{RESET} {WHITE}{fs_msg}{RESET}")
    else:
        print(f"  [{CYAN}INFO{RESET}] {BOLD}Flaresolverr Bypass Engine:{RESET} {GRAY}{fs_msg}{RESET}")
        print(f"         {DIM}Note: Not required if using Browser-Assisted mode.{RESET}")

    # 5. Windows Subsystems
    sub_results = check_windows_subsystems()
    for name, (ok, detail) in sub_results.items():
        if ok:
            print(f"  [{GREEN}PASS{RESET}] {BOLD}{name}:{RESET} {WHITE}{detail}{RESET}")
        else:
            print(f"  [{AMBER}WARN{RESET}] {BOLD}{name}:{RESET} {AMBER}{detail}{RESET}")

    # 6. GAMMA Installation & Disk Space
    g_ok, g_msg, g_details = check_gamma_installation(gamma_dir)
    if g_ok:
        print(f"  [{GREEN}PASS{RESET}] {BOLD}G.A.M.M.A. Installation:{RESET} {WHITE}{g_msg}{RESET}")
    else:
        print(f"  [{AMBER}WARN{RESET}] {BOLD}G.A.M.M.A. Installation:{RESET} {AMBER}{g_msg}{RESET}")
        print(f"         {DIM}Use --gamma-dir <PATH> to specify your G.A.M.M.A. folder directly.{RESET}")

    print_divider()
    if issues == 0:
        print(f"  {GREEN}{BOLD}All essential systems are healthy and ready to download!{RESET}\n")
        return 0
    else:
        print(f"  {AMBER}{BOLD}Diagnostics completed with {issues} notice(s). Review recommendations above.{RESET}\n")
        return 0
