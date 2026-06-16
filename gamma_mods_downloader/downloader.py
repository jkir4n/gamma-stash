"""
Links file parser + downloader for the Gamma Mods Downloader.

Handles GAMMA's official mods.txt format (tab-separated):
  URL\tinstall_path\t - author\tdescription\tmoddb_page_url\tfilename\tMD5

Lines starting with a bare category name (no URL) are category headers.
"""

import hashlib
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from .config import load_config
from .terminal import (
    GREEN, AMBER, RED, CYAN, GRAY, DARK_GRAY, WHITE, DIM, BOLD, RESET,
    ProgressBar, Spinner, BOX_H,
    print_ok, print_error, print_warn, print_info, print_field, print_divider,
)


def md5_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


CATEGORY_PATTERNS = [
    "Audio", "Visual", "Animations", "Gameplay", "Stashes", "Gunplay",
    "QoL", "Craft and Repair", "Progression", "UI", "High Priority",
    "Shaders", "Icons", "DLTX", "Optional",
    "Good addons with issues and bugs", "Newly added addons", "Minimap (pick one)",
]


def _is_category_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return True
    if not stripped.startswith("http"):
        return True
    return False


def _parse_entry(line: str) -> Optional[Dict[str, str]]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if _is_category_header(stripped):
        return None

    parts = stripped.split("\t")
    if len(parts) < 1:
        return None

    url = parts[0].strip()
    if not url.startswith("http"):
        return None

    install_path = parts[1].strip() if len(parts) > 1 else ""
    author_raw = parts[2].strip() if len(parts) > 2 else ""
    description = parts[3].strip() if len(parts) > 3 else ""

    author = author_raw
    if author.startswith("- "):
        author = author[2:]
    elif author.startswith("-"):
        author = author[1:]
    author = author.strip()

    moddb_page = parts[4].strip() if len(parts) > 4 else ""
    filename = parts[5].strip() if len(parts) > 5 else ""
    expected_md5 = parts[6].strip() if len(parts) > 6 else ""

    source = "GITHUB" if "github.com" in url.lower() else "MODDB"

    if not filename:
        url_parts = url.rstrip("/").split("/")
        filename = url_parts[-1] if url_parts else "unknown.zip"
        if not filename:
            filename = f"mod_{hash(url) % 1000000:06d}.zip"

    return {
        "url": url,
        "install_path": install_path,
        "author": author,
        "description": description,
        "moddb_page": moddb_page,
        "filename": filename,
        "expected_md5": expected_md5,
        "actual_md5": "",
        "source": source,
        "status": "PENDING",
    }


def format_entry(entry: Dict[str, str]) -> str:
    parts = [
        entry["url"],
        entry.get("install_path", ""),
        f"- {entry['author']}" if entry.get("author") else "",
        entry.get("description", ""),
        entry.get("moddb_page", ""),
        entry.get("filename", ""),
        entry.get("expected_md5", "") if entry.get("expected_md5") else "",
    ]
    return "\t".join(parts)


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _format_speed(bytes_per_sec: float) -> str:
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.0f} KB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"


class LinksFile:
    """Manages GAMMA's mods.txt file -- tab-separated, with category headers."""

    def __init__(self, local_path: str):
        self.local_path = local_path

    def read(self) -> List[Dict[str, str]]:
        content = self._read_content()
        entries = []
        for line in content.splitlines():
            entry = _parse_entry(line)
            if entry:
                entries.append(entry)
        return entries

    def read_with_categories(self) -> Tuple[List[str], List[List[Dict[str, str]]]]:
        content = self._read_content()
        categories: List[str] = []
        entries_by_cat: List[List[Dict[str, str]]] = []
        current_cat = "Uncategorized"
        current_entries: List[Dict[str, str]] = []

        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _is_category_header(stripped):
                if current_entries:
                    entries_by_cat.append(current_entries)
                    categories.append(current_cat)
                current_cat = stripped
                current_entries = []
                continue

            entry = _parse_entry(line)
            if entry:
                current_entries.append(entry)

        if current_entries:
            entries_by_cat.append(current_entries)
            categories.append(current_cat)

        return categories, entries_by_cat

    def _read_content(self) -> str:
        with open(self.local_path, "r") as f:
            return f.read()

    def update_entry_status(self, entries: List[Dict[str, str]]) -> bool:
        pass

    def status_summary(self) -> Tuple[int, int, int, int, int]:
        entries = self.read()
        total = len(entries)
        downloaded = sum(1 for e in entries if e["status"] == "DOWNLOADED")
        pending = total - downloaded
        moddb = sum(1 for e in entries if e.get("source") == "MODDB")
        github = sum(1 for e in entries if e.get("source") == "GITHUB")
        return total, downloaded, pending, moddb, github


class Downloader:
    """Downloads mods from ModDB via Flaresolverr and GitHub directly."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.download_dir = config["download_dir"]
        self.delay = config.get("download_delay", 2)
        self.max_concurrent = config.get("max_concurrent", 1)

        self.flare = None
        fs_cfg = config.get("flaresolverr", {})
        if fs_cfg.get("url"):
            from .flaresolverr_client import FlaresolverrClient
            self.flare = FlaresolverrClient(
                url=fs_cfg["url"],
                timeout_ms=fs_cfg.get("timeout_ms", 60000),
            )
        else:
            print_warn("No Flaresolverr configured -- MODDB downloads will fail")

        self.links = LinksFile(local_path=config["links_file"])
        os.makedirs(self.download_dir, exist_ok=True)

    def download_entry(self, entry: Dict[str, str]) -> bool:
        url = entry["url"]
        filename = entry["filename"]
        expected_md5 = entry.get("expected_md5", "")
        source = entry.get("source", "MODDB")
        local_path = os.path.join(self.download_dir, filename)

        # Print file header
        desc = entry.get("description", "") or filename
        author = entry.get("author", "")
        src_tag = f"{CYAN}GH{RESET}" if source == "GITHUB" else f"{AMBER}MDB{RESET}"

        print(f"\n  {BOLD}{filename}{RESET}")
        if desc and desc != filename:
            print(f"  {DIM}{desc}{RESET}")
        if author:
            print(f"  {DIM}by {author}{RESET}  [{src_tag}]")
        else:
            print(f"  [{src_tag}]")
        if expected_md5:
            print(f"  {DIM}MD5: {expected_md5[:16]}...{RESET}")

        # Check if already downloaded
        if os.path.exists(local_path):
            if expected_md5:
                spinner = Spinner(f"Checking existing file ...")
                spinner.start()
                actual_md5 = md5_file(local_path)
                if actual_md5 == expected_md5:
                    spinner.stop("OK")
                    entry["actual_md5"] = actual_md5
                    if self._copy_to_destination(local_path, filename):
                        entry["status"] = "DOWNLOADED"
                        return True
                else:
                    spinner.stop(None)
                    print_warn(f"MD5 mismatch (got {actual_md5[:16]}...), re-downloading")
            else:
                if os.path.getsize(local_path) > 100:
                    print_ok("Already exists (no MD5 to verify)")
                    if self._copy_to_destination(local_path, filename):
                        entry["status"] = "DOWNLOADED"
                        return True

        # Download
        if source == "GITHUB":
            ok = self._download_github(url, local_path)
        else:
            ok = self._download_moddb(url, local_path)

        if not ok:
            return False

        # Post-download MD5 verification
        if expected_md5:
            spinner = Spinner("Verifying MD5 ...")
            spinner.start()
            actual_md5 = md5_file(local_path)
            entry["actual_md5"] = actual_md5
            if actual_md5 != expected_md5:
                spinner.fail(f"expected {expected_md5[:16]}..., got {actual_md5[:16]}...")
                os.remove(local_path)
                return False
            spinner.stop("OK")
        else:
            entry["actual_md5"] = md5_file(local_path)

        if self._copy_to_destination(local_path, filename):
            entry["status"] = "DOWNLOADED"
            return True
        return False

    def _download_moddb(self, url: str, local_path: str) -> bool:
        if not self.flare:
            print_error("Flaresolverr not configured, cannot download MODDB link")
            return False

        spinner = Spinner("Resolving ModDB page via Flaresolverr ...")
        spinner.start()
        try:
            result = self.flare.resolve(url)
        except Exception as e:
            spinner.fail(str(e))
            return False

        sol = result.get("solution", {})
        html = sol.get("response", "")

        mirror_url = self.flare.extract_mirror_url(html)
        if not mirror_url:
            spinner.fail("Could not extract mirror link")
            return False

        spinner.stop("OK")
        cookies = sol.get("cookies", [])
        user_agent = sol.get("userAgent", "")

        return self._curl_download(mirror_url, local_path, user_agent,
                                   self.flare.build_cookie_header(cookies))

    def _download_github(self, url: str, local_path: str) -> bool:
        return self._curl_download(url, local_path)

    def _curl_download(self, url: str, local_path: str,
                       user_agent: str = "", cookie: str = "") -> bool:
        filename = os.path.basename(local_path)
        if len(filename) > 35:
            filename = filename[:32] + "..."

        cmd = ["curl", "-sL", "-o", local_path, "-w", "%{http_code}", "--max-time", "600", url]
        if user_agent:
            cmd.insert(1, user_agent)
            cmd.insert(1, "-A")
        if cookie:
            cmd.insert(1, f"Cookie: {cookie}")
            cmd.insert(1, "-H")

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except Exception as e:
            print_error(f"Failed to start download: {e}")
            return False

        start_time = time.time()
        last_size = 0
        last_time = start_time
        bar = ProgressBar(100, width=28, label=f"{CYAN}{filename}{RESET}")

        while proc.poll() is None:
            time.sleep(0.3)
            if os.path.exists(local_path):
                current_size = os.path.getsize(local_path)
                now = time.time()
                elapsed = now - start_time
                dt = now - last_time

                if dt >= 0.5 and current_size > last_size:
                    speed_bps = (current_size - last_size) / dt if dt > 0 else 0
                    speed_str = _format_speed(speed_bps)
                    size_str = _format_size(current_size)
                    pct = min(int(current_size / max(current_size + speed_bps * 10, 1) * 100), 99)
                    bar.update(pct, f"{GREEN}{size_str}{RESET}  {GRAY}{speed_str}{RESET}")
                    last_size = current_size
                    last_time = now

        http_code = proc.stdout.read().strip() if proc.stdout else "0"
        bar.done(f"{GREEN}{_format_size(os.path.getsize(local_path) if os.path.exists(local_path) else 0)}{RESET}")

        if os.path.exists(local_path) and os.path.getsize(local_path) > 100:
            return True

        print_error(f"Download failed (HTTP {http_code})")
        return False

    def _copy_to_destination(self, local_path: str, filename: str) -> bool:
        import shutil
        dest_dir = self.config["destination"]["local_path"]

        if os.path.normpath(local_path) == os.path.normpath(os.path.join(dest_dir, filename)):
            return True

        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, filename)

        if os.path.exists(dest):
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(dest):
                dest = os.path.join(dest_dir, f"{base}_{counter}{ext}")
                counter += 1

        shutil.copy2(local_path, dest)
        return True

    def download_all(self, skip_filenames: Optional[frozenset] = None) -> Dict[str, int]:
        entries = self.links.read()
        pending_all = [e for e in entries if e["status"] == "PENDING"]
        if skip_filenames:
            pending = [e for e in pending_all if e["filename"] not in skip_filenames]
        else:
            pending = pending_all

        print(f"\n  {BOLD}Downloading{RESET}  {GRAY}{len(pending)} mods{RESET}")
        print_divider()

        if not pending:
            print_ok("Nothing to download!")
            return {"success": 0, "fail": 0, "total_pending": 0}

        success = 0
        fail = 0
        total = len(pending)
        progress_file = os.path.join(self.download_dir, "_progress.txt")

        for i, entry in enumerate(pending, 1):
            ok = self.download_entry(entry)
            if ok:
                success += 1
            else:
                fail += 1

            with open(progress_file, "w") as pf:
                pf.write(f"{i}/{total} | OK:{success} FAIL:{fail}\n")

            if i < total:
                time.sleep(self.delay)

        print_divider()
        ok_str = f"{GREEN}{success} OK{RESET}"
        fail_str = f"{RED}{fail} FAIL{RESET}" if fail > 0 else ""
        print(f"\n  {BOLD}Done:{RESET} {ok_str}  {fail_str}  {GRAY}of {total}{RESET}\n")
        return {"success": success, "fail": fail, "total_pending": total}
