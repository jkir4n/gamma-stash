"""
Links file parser + downloader for the Gamma Mods Downloader.

Handles GAMMA's official mods.txt format (tab-separated):
  URL\tinstall_path\t - author\tdescription\tmoddb_page_url\tfilename\tMD5

Lines starting with a bare category name (no URL) are category headers.
"""

import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import load_config
from .terminal import (
    GREEN, AMBER, RED, CYAN, GRAY, DARK_GRAY, WHITE, DIM, BOLD, RESET,
    ProgressBar, Spinner,
    print_ok, print_error, print_warn, print_info, print_field, print_divider,
)

CACHE_FILENAME = ".stash_cache.json"


def md5_file(path: str) -> str:
    """Compute MD5 hash of a file using fast file_digest (Python 3.11+) or 1MB chunking."""
    with open(path, "rb") as f:
        if hasattr(hashlib, "file_digest"):
            return hashlib.file_digest(f, "md5").hexdigest()
        h = hashlib.md5()
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
        return h.hexdigest()


def load_hash_cache(download_dir: str) -> Dict[str, Dict[str, Any]]:
    """Load metadata hash cache from download directory."""
    cache_path = os.path.join(download_dir, CACHE_FILENAME)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_hash_cache(download_dir: str, cache: Dict[str, Dict[str, Any]]) -> None:
    """Save metadata hash cache to download directory."""
    cache_path = os.path.join(download_dir, CACHE_FILENAME)
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def cached_md5_file(path: str, cache: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """Compute or retrieve MD5 hash with mtime/size cache validation."""
    if not os.path.exists(path):
        return ""

    filename = os.path.basename(path)
    try:
        stat = os.stat(path)
        mtime = stat.st_mtime
        size = stat.st_size
    except Exception:
        return md5_file(path)

    if cache is not None and filename in cache:
        c_entry = cache[filename]
        if c_entry.get("mtime") == mtime and c_entry.get("size") == size and c_entry.get("md5"):
            return c_entry["md5"]

    computed_md5 = md5_file(path)
    if cache is not None:
        cache[filename] = {"mtime": mtime, "size": size, "md5": computed_md5}
    return computed_md5


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


def open_in_browser(url: str) -> None:
    """Open a URL in the user's default browser."""
    try:
        webbrowser.open(url)
    except Exception:
        pass


def watch_browser_download(filename: str,
                           expected_md5: str,
                           browser_downloads_dir: str,
                           target_dir: str,
                           timeout_sec: int = 300,
                           status_cb: Optional[Callable[[str], None]] = None) -> bool:
    """
    Watches the user's browser download folder for the expected file or a newly completed file,
    verifies MD5, and atomically moves it to the target downloads directory.
    """
    if not browser_downloads_dir or not os.path.isdir(browser_downloads_dir):
        return False

    start_time = time.time()
    dest_path = os.path.join(target_dir, filename)

    while time.time() - start_time < timeout_sec:
        # 1. Direct match in browser downloads dir
        candidate = os.path.join(browser_downloads_dir, filename)
        temp_markers = [
            candidate + ".crdownload",
            candidate + ".part",
            candidate + ".tmp",
            candidate + ".download",
        ]

        # Check if browser is actively writing to a temp file
        is_in_progress = any(os.path.exists(m) for m in temp_markers)
        if is_in_progress:
            if status_cb:
                status_cb("Downloading via browser...")
            time.sleep(1)
            continue

        if os.path.isfile(candidate):
            # Verify file size stability (ensure browser finished writing)
            sz1 = os.path.getsize(candidate)
            time.sleep(0.8)
            sz2 = os.path.getsize(candidate)
            if sz1 == sz2 and sz1 > 100:
                if expected_md5:
                    actual = md5_file(candidate)
                    if actual == expected_md5:
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        shutil.move(candidate, dest_path)
                        return True
                else:
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    shutil.move(candidate, dest_path)
                    return True

        # 2. Check for browser-renamed files (e.g. filename (1).zip) modified recently
        try:
            now = time.time()
            for entry in os.scandir(browser_downloads_dir):
                if entry.is_file() and (now - entry.stat().st_mtime < 600):
                    name = entry.name
                    if any(name.endswith(ext) for ext in [".crdownload", ".part", ".tmp", ".download"]):
                        continue
                    # If same extension and size > 100 bytes
                    if os.path.splitext(name)[1].lower() == os.path.splitext(filename)[1].lower():
                        if expected_md5 and entry.stat().st_size > 100:
                            if md5_file(entry.path) == expected_md5:
                                if os.path.exists(dest_path):
                                    os.remove(dest_path)
                                shutil.move(entry.path, dest_path)
                                return True
        except Exception:
            pass

        time.sleep(1)

    return False


class LinksFile:
    """Manages GAMMA's mods.txt file -- tab-separated, with category headers."""

    def __init__(self, local_path: str):
        self.local_path = local_path

    def read(self) -> List[Dict[str, str]]:
        content = self._read_content()
        entries = []
        current_cat = "Uncategorized"
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _is_category_header(stripped):
                current_cat = stripped
                continue
            entry = _parse_entry(line)
            if entry:
                entry["category"] = current_cat
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
        with open(self.local_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


class Downloader:
    """Downloads mods from ModDB via Flaresolverr and GitHub directly with concurrency & resume."""

    def __init__(self, config: Dict[str, Any],
                 log_callback: Optional[Callable[[str], None]] = None,
                 progress_callback: Optional[Callable[[int, int, str], None]] = None,
                 on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None):
        self.config = config
        self.download_dir = config["download_dir"]
        self.delay = config.get("download_delay", 1)
        self.max_concurrent = config.get("max_concurrent", 3)
        self.fs_mode = config.get("fs_mode", "manual")
        self.browser_downloads_dir = config.get("browser_downloads_dir", "")
        self.limit_rate = config.get("limit_rate", "")
        self.category_filter = config.get("category_filter", "")
        self.selected_categories = config.get("selected_categories", None)
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        self.on_event = on_event

        self.flare = None
        fs_cfg = config.get("flaresolverr", {})
        if fs_cfg.get("url") and self.fs_mode != "browser":
            from .flaresolverr_client import FlaresolverrClient
            self.flare = FlaresolverrClient(
                url=fs_cfg["url"],
                timeout_ms=fs_cfg.get("timeout_ms", 60000),
            )
            try:
                self.flare.create_session()
            except Exception:
                pass
        elif self.fs_mode == "browser":
            self._log_ok(f"Browser-Assisted mode active (monitoring: {self.browser_downloads_dir or 'Downloads'})")
        else:
            self._log_warn("No Flaresolverr configured -- MODDB downloads will fail")

        self.links = LinksFile(local_path=config["links_file"])
        os.makedirs(self.download_dir, exist_ok=True)
        self.cache = load_hash_cache(self.download_dir)
        self._lock = threading.Lock()

    def _emit(self, event: str, data: Dict[str, Any]) -> None:
        if self.on_event:
            try:
                self.on_event(event, data)
            except Exception:
                pass

    def _log(self, msg: str) -> None:
        if self.log_callback:
            self.log_callback(msg)
        else:
            print(msg)

    def _log_ok(self, msg: str) -> None:
        if self.log_callback:
            self.log_callback(f"[OK] {msg}")
        else:
            print_ok(msg)

    def _log_warn(self, msg: str) -> None:
        if self.log_callback:
            self.log_callback(f"[WARN] {msg}")
        else:
            print_warn(msg)

    def _log_error(self, msg: str) -> None:
        if self.log_callback:
            self.log_callback(f"[ERROR] {msg}")
        else:
            print_error(msg)

    def download_entry(self, entry: Dict[str, str], max_retries: int = 3) -> bool:
        url = entry["url"]
        filename = entry["filename"]
        expected_md5 = entry.get("expected_md5", "")
        source = entry.get("source", "MODDB")
        local_path = os.path.join(self.download_dir, filename)
        part_path = f"{local_path}.part"

        desc = entry.get("description", "") or filename
        author = entry.get("author", "")
        src_tag = "GH" if source == "GITHUB" else "MDB"

        if not self.log_callback:
            src_tag_fmt = f"{CYAN}GH{RESET}" if source == "GITHUB" else f"{AMBER}MDB{RESET}"
            print(f"\n  {BOLD}{filename}{RESET}")
            if desc and desc != filename:
                print(f"  {DIM}{desc}{RESET}")
            if author:
                print(f"  {DIM}by {author}{RESET}  [{src_tag_fmt}]")
            else:
                print(f"  [{src_tag_fmt}]")
            if expected_md5:
                print(f"  {DIM}MD5: {expected_md5[:16]}...{RESET}")
        else:
            self._log(f"Downloading [{src_tag}] {filename} ({desc})")

        self._emit("entry_start", {"filename": filename, "source": source, "description": desc, "url": url, "moddb_page": entry.get("moddb_page", "")})

        # Check if already downloaded and verified
        if os.path.exists(local_path):
            if expected_md5:
                actual_md5 = cached_md5_file(local_path, self.cache)
                if actual_md5 == expected_md5:
                    self._log_ok(f"{filename} already verified")
                    entry["actual_md5"] = actual_md5
                    if self._copy_to_destination(local_path, filename):
                        entry["status"] = "DOWNLOADED"
                        self._emit("entry_complete", {"filename": filename, "status": "OK", "cached": True})
                        return True
                else:
                    self._log_warn(f"MD5 mismatch for {filename} (got {actual_md5[:16]}...), re-downloading")
            else:
                if os.path.getsize(local_path) > 100:
                    self._log_ok(f"{filename} already exists (no MD5 to verify)")
                    if self._copy_to_destination(local_path, filename):
                        entry["status"] = "DOWNLOADED"
                        self._emit("entry_complete", {"filename": filename, "status": "OK", "cached": True})
                        return True

        # Browser-Assisted Mode for ModDB links
        if source != "GITHUB" and self.fs_mode == "browser":
            mod_url = entry.get("moddb_page") or url
            self._log_warn(f"Opening {filename} in your browser...")
            open_in_browser(mod_url)
            self._emit("entry_browser_waiting", {"filename": filename, "url": mod_url})

            def status_cb(st: str):
                self._emit("entry_progress", {
                    "filename": filename,
                    "speed_str": st,
                    "size_str": "",
                })

            ok = watch_browser_download(
                filename=filename,
                expected_md5=expected_md5,
                browser_downloads_dir=self.browser_downloads_dir,
                target_dir=self.download_dir,
                timeout_sec=300,
                status_cb=status_cb,
            )
            if ok:
                entry["status"] = "DOWNLOADED"
                actual_md5 = cached_md5_file(local_path, self.cache)
                entry["actual_md5"] = actual_md5
                self._copy_to_destination(local_path, filename)
                self._emit("entry_complete", {"filename": filename, "status": "OK", "cached": False})
                return True
            else:
                self._log_error(f"Browser download for {filename} timed out or cancelled.")
                self._emit("entry_error", {"filename": filename, "error": "Browser download timeout"})
                return False

        # Retry loop for automated download with HTTP Range resume support
        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                self._log_warn(f"Retry {attempt}/{max_retries} for {filename} ...")
                time.sleep(1.5 * attempt)

            if source == "GITHUB":
                ok = self._download_github(url, part_path, filename)
            else:
                ok = self._download_moddb(url, part_path, filename)

            if not ok or not os.path.exists(part_path):
                continue

            # Verify MD5 on the .part file before moving to final destination
            if expected_md5:
                actual_md5 = md5_file(part_path)
                entry["actual_md5"] = actual_md5
                if actual_md5 != expected_md5:
                    self._log_error(f"MD5 verification failed for {filename} (expected {expected_md5[:12]}, got {actual_md5[:12]})")
                    try:
                        os.remove(part_path)
                    except Exception:
                        pass
                    continue
            else:
                entry["actual_md5"] = md5_file(part_path)

            # Atomic rename from .part to final destination
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
                os.replace(part_path, local_path)
            except Exception as e:
                self._log_error(f"Failed to finalize file {filename}: {e}")
                self._emit("entry_error", {"filename": filename, "error": str(e)})
                return False

            with self._lock:
                try:
                    stat = os.stat(local_path)
                    self.cache[filename] = {
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "md5": entry.get("actual_md5", ""),
                    }
                except Exception:
                    pass

            if self._copy_to_destination(local_path, filename):
                entry["status"] = "DOWNLOADED"
                self._emit("entry_complete", {"filename": filename, "status": "OK", "cached": False})
                return True

        self._log_error(f"Failed to download {filename} after {max_retries} attempts.")
        self._emit("entry_error", {"filename": filename, "error": f"Failed after {max_retries} retries", "url": url, "moddb_page": entry.get("moddb_page", "")})
        return False

    def _probe_url(self, url: str) -> Tuple[int, bool]:
        """Check Content-Length and Range support via curl HEAD request."""
        try:
            res = subprocess.run(
                ["curl", "-sIL", "--head", "--max-time", "8", url],
                capture_output=True, text=True, timeout=10
            )
            headers = res.stdout.lower()
            range_ok = "accept-ranges: bytes" in headers
            size = 0
            for line in headers.splitlines():
                if line.startswith("content-length:"):
                    try:
                        size = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass
            return size, range_ok
        except Exception:
            return 0, False

    def _download_segmented(self, url: str, part_path: str, display_name: str, total_size: int, num_chunks: int = 3) -> bool:
        """Download large file in parallel byte-range chunks."""
        chunk_size = total_size // num_chunks
        chunk_files = []
        chunk_tasks = []

        for i in range(num_chunks):
            start = i * chunk_size
            end = (start + chunk_size - 1) if i < num_chunks - 1 else (total_size - 1)
            cf = f"{part_path}.chk{i}"
            chunk_files.append(cf)
            chunk_tasks.append((start, end, cf))

        def get_chunk(args):
            s, e, out = args
            cmd = ["curl", "-sL", "-r", f"{s}-{e}", "-o", out, "--max-time", "600"]
            if self.limit_rate:
                cmd.extend(["--limit-rate", self.limit_rate])
            cmd.append(url)
            r = subprocess.run(cmd, capture_output=True, timeout=660)
            return r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) == (e - s + 1)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_chunks) as executor:
            results = list(executor.map(get_chunk, chunk_tasks))

        if all(results) and all(os.path.exists(cf) for cf in chunk_files):
            try:
                with open(part_path, "wb") as outfile:
                    for cf in chunk_files:
                        with open(cf, "rb") as infile:
                            shutil.copyfileobj(infile, outfile)
                        try:
                            os.remove(cf)
                        except Exception:
                            pass
                return True
            except Exception:
                pass

        for cf in chunk_files:
            if os.path.exists(cf):
                try:
                    os.remove(cf)
                except Exception:
                    pass
        return False

    def _download_github(self, url: str, part_path: str, display_name: str) -> bool:
        # Check size and range support for large file parallel acceleration
        size, range_ok = self._probe_url(url)
        if range_ok and size >= 50 * 1024 * 1024:
            self._log(f"Accelerating {display_name} via 3 parallel segments ({_format_size(size)})")
            ok = self._download_segmented(url, part_path, display_name, size, num_chunks=3)
            if ok:
                return True
        return self._curl_download(url, part_path, display_name)

    def _download_moddb(self, url: str, part_path: str, display_name: str) -> bool:
        if not self.flare:
            self._log_error("Flaresolverr not configured, cannot download MODDB link")
            return False

        spinner = None if self.log_callback else Spinner("Resolving ModDB page via Flaresolverr ...")
        if spinner:
            spinner.start()
        try:
            result = self.flare.resolve(url)
        except Exception as e:
            if spinner:
                spinner.fail(str(e))
            else:
                self._log_error(f"Flaresolverr error: {e}")
            return False

        sol = result.get("solution", {})
        html = sol.get("response", "")

        mirror_url = self.flare.extract_mirror_url(html)
        if not mirror_url:
            if spinner:
                spinner.fail("Could not extract mirror link")
            else:
                self._log_error(f"Could not extract mirror link for {url}")
            return False

        if spinner:
            spinner.stop("OK")
        cookies = sol.get("cookies", [])
        user_agent = sol.get("userAgent", "")

        ok = self._curl_download(mirror_url, part_path, display_name, user_agent,
                                 self.flare.build_cookie_header(cookies))
        if ok:
            return True

        # Mirror Failover: if initial mirror failed, try fallback endpoint
        self._log_warn(f"Primary mirror failed for {display_name}, attempting mirror failover...")
        alt_url = url.replace("/downloads/start/", "/downloads/mirror/").rstrip("/all")
        if alt_url != mirror_url and alt_url != url:
            return self._curl_download(alt_url, part_path, display_name, user_agent,
                                       self.flare.build_cookie_header(cookies))
        return False

    def _curl_download(self, url: str, part_path: str, display_name: str,
                       user_agent: str = "", cookie: str = "") -> bool:
        short_name = display_name if len(display_name) <= 35 else display_name[:32] + "..."

        # Enable resume (-C -) if partial file exists
        cmd = ["curl", "-sL", "-o", part_path, "-w", "%{http_code}", "--max-time", "600"]
        if os.path.exists(part_path) and os.path.getsize(part_path) > 0:
            cmd.extend(["-C", "-"])
        if self.limit_rate:
            cmd.extend(["--limit-rate", self.limit_rate])
        if user_agent:
            cmd.extend(["-A", user_agent])
        if cookie:
            cmd.extend(["-H", f"Cookie: {cookie}"])
        cmd.append(url)

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except Exception as e:
            self._log_error(f"Failed to start curl download: {e}")
            return False

        start_time = time.time()
        last_size = 0
        last_time = start_time
        bar = None if self.log_callback else ProgressBar(100, width=28, label=f"{CYAN}{short_name}{RESET}")

        while proc.poll() is None:
            time.sleep(0.3)
            if os.path.exists(part_path):
                current_size = os.path.getsize(part_path)
                now = time.time()
                dt = now - last_time

                if dt >= 0.5 and current_size > last_size:
                    speed_bps = (current_size - last_size) / dt if dt > 0 else 0
                    speed_str = _format_speed(speed_bps)
                    size_str = _format_size(current_size)
                    if bar:
                        pct = min(int(current_size / max(current_size + speed_bps * 10, 1) * 100), 99)
                        bar.update(pct, f"{GREEN}{size_str}{RESET}  {GRAY}{speed_str}{RESET}")
                    self._emit("entry_progress", {
                        "filename": display_name,
                        "bytes": current_size,
                        "speed": speed_bps,
                        "speed_str": speed_str,
                        "size_str": size_str,
                    })
                    last_size = current_size
                    last_time = now

        http_code = proc.stdout.read().strip() if proc.stdout else "0"
        if bar:
            final_sz = _format_size(os.path.getsize(part_path) if os.path.exists(part_path) else 0)
            bar.done(f"{GREEN}{final_sz}{RESET}")

        # Check HTTP status code (200, 206 Partial Content, 304 Not Modified)
        if not (http_code.startswith("2") or http_code == "304" or http_code == "416"):
            self._log_error(f"Download returned HTTP {http_code}")
            return False

        if os.path.exists(part_path) and os.path.getsize(part_path) > 100:
            return True

        self._log_error(f"Downloaded file is too small or missing ({part_path})")
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

        # Filter by category if requested
        if self.selected_categories:
            pending = [e for e in pending if e.get("category") in self.selected_categories]
        elif self.category_filter:
            pending = [e for e in pending if self.category_filter.lower() in e.get("category", "").lower()]

        if not self.log_callback:
            print(f"\n  {BOLD}Downloading{RESET}  {GRAY}{len(pending)} mods{RESET}")
            print_divider()
        else:
            self._log(f"Starting batch download for {len(pending)} pending mods...")

        if not pending:
            self._log_ok("Nothing to download!")
            return {"success": 0, "fail": 0, "total_pending": 0}

        success = 0
        fail = 0
        total = len(pending)
        progress_file = os.path.join(self.download_dir, "_progress.txt")

        # Split into GitHub (can run concurrently) and ModDB (sequential Flaresolverr queue)
        github_mods = [e for e in pending if e.get("source") == "GITHUB"]
        moddb_mods = [e for e in pending if e.get("source") != "GITHUB"]

        completed_count = 0

        def run_single(entry):
            nonlocal success, fail, completed_count
            ok = self.download_entry(entry)
            with self._lock:
                completed_count += 1
                if ok:
                    success += 1
                else:
                    fail += 1
                if self.progress_callback:
                    self.progress_callback(completed_count, total, entry["filename"])
                self._emit("overall_progress", {
                    "completed": completed_count,
                    "total": total,
                    "success": success,
                    "fail": fail,
                    "current": entry["filename"],
                })
                try:
                    with open(progress_file, "w", encoding="utf-8") as pf:
                        pf.write(f"{completed_count}/{total} | OK:{success} FAIL:{fail}\n")
                except Exception:
                    pass
            return ok

        # Phase 1: GitHub downloads in parallel
        if github_mods:
            workers = min(self.max_concurrent, len(github_mods))
            if workers > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                    list(executor.map(run_single, github_mods))
            else:
                for entry in github_mods:
                    run_single(entry)
                    time.sleep(self.delay)

        # Phase 2: ModDB downloads
        for entry in moddb_mods:
            run_single(entry)
            time.sleep(self.delay)

        save_hash_cache(self.download_dir, self.cache)

        if not self.log_callback:
            print_divider()
            ok_str = f"{GREEN}{success} OK{RESET}"
            fail_str = f"{RED}{fail} FAIL{RESET}" if fail > 0 else ""
            print(f"\n  {BOLD}Done:{RESET} {ok_str}  {fail_str}  {GRAY}of {total}{RESET}\n")
        else:
            self._log(f"Downloads completed: {success} OK, {fail} FAIL of {total}")

        return {"success": success, "fail": fail, "total_pending": total}
