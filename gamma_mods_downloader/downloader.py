"""
Links file parser for the Gamma Mods Downloader.

Handles GAMMA's official mods.txt format (tab-separated):
  URL\tinstall_path\t - author\tdescription\tmoddb_page_url\tfilename\tMD5

Lines starting with a bare category name (no URL) are category headers.
Some entries lack an MD5 checksum (field 7 missing).
"""

import hashlib
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from .config import load_config
from .ssh_utils import SSHClient


def md5_file(path: str) -> str:
    """Compute MD5 hash of a file."""
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
    """Check if a line is a bare category header (no URL)."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return True
    # Lines without http(s) are category headers or blank
    if not stripped.startswith("http"):
        return True
    return False


def _parse_entry(line: str) -> Optional[Dict[str, str]]:
    """
    Parse a single tab-separated mod entry line.
    Fields: URL | install_path | - author | description | moddb_page_url | filename | MD5

    Returns None if the line is a category header or blank.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if _is_category_header(stripped):
        # This is a category header, not an entry
        return None

    parts = stripped.split("\t")

    if len(parts) < 1:
        return None

    url = parts[0].strip()
    if not url.startswith("http"):
        return None

    # Defaults
    install_path = parts[1].strip() if len(parts) > 1 else ""
    author_raw = parts[2].strip() if len(parts) > 2 else ""
    description = parts[3].strip() if len(parts) > 3 else ""

    # Clean up author (remove leading "- ")
    author = author_raw
    if author.startswith("- "):
        author = author[2:]
    elif author.startswith("-"):
        author = author[1:]
    author = author.strip()

    moddb_page = parts[4].strip() if len(parts) > 4 else ""
    filename = parts[5].strip() if len(parts) > 5 else ""
    expected_md5 = parts[6].strip() if len(parts) > 6 else ""

    # Determine source
    source = "GITHUB" if "github.com" in url.lower() else "MODDB"

    # Generate a safe filename if none provided
    if not filename:
        # Extract from URL
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
        "actual_md5": "",  # Will be filled after download
        "source": source,
        "status": "PENDING",
    }


def format_entry(entry: Dict[str, str]) -> str:
    """Format a single entry back to tab-separated line."""
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


class LinksFile:
    """
    Manages GAMMA's mods.txt file — tab-separated, with category headers.
    """

    def __init__(self, local_path: str, ssh: Optional[SSHClient] = None,
                 remote_path: Optional[str] = None):
        self.local_path = local_path
        self.ssh = ssh
        self.remote_path = remote_path or local_path

    def read(self) -> List[Dict[str, str]]:
        """Parse the mods.txt file and return a list of entry dicts."""
        content = self._read_content()
        entries = []
        for line in content.splitlines():
            entry = _parse_entry(line)
            if entry:
                entries.append(entry)
        return entries

    def read_with_categories(self) -> Tuple[List[str], List[List[Dict[str, str]]]]:
        """
        Parse mods.txt preserving category structure.
        Returns (categories, entries_by_category) where each category entry
        is a list of mod entries under that category.
        """
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
                # Only add the previous category if it had entries
                if current_entries:
                    entries_by_cat.append(current_entries)
                    categories.append(current_cat)
                current_cat = stripped
                current_entries = []
                continue

            entry = _parse_entry(line)
            if entry:
                current_entries.append(entry)

        # Don't forget last category
        if current_entries:
            entries_by_cat.append(current_entries)
            categories.append(current_cat)

        return categories, entries_by_cat

    def _read_content(self) -> str:
        """Read the links file from either local or remote source."""
        if self.ssh and self._is_remote_primary():
            content = self.ssh.read_file(self.remote_path)
            if content is None:
                raise FileNotFoundError(
                    f"Cannot read remote links file: {self.remote_path}"
                )
            return content

        with open(self.local_path, "r") as f:
            return f.read()

    def _is_remote_primary(self) -> bool:
        """Check if the primary source is remote (local file doesn't exist)."""
        return not os.path.exists(self.local_path)

    def update_entry_status(self, entries: List[Dict[str, str]]) -> bool:
        """
        Rewrite mods.txt with updated actual_md5 and status fields.
        Since mods.txt only has expected_md5 (field 7), we store actual_md5
        in the expected_md5 slot for entries that were previously missing it,
        or update status by appending a comment after the line.
        """
        # TODO: For now, status is tracked in a separate tracking file
        # since mods.txt doesn't have a natural place for status/actual_md5
        pass

    def status_summary(self) -> Tuple[int, int, int, int, int]:
        """Return (total, downloaded, pending, moddb, github) counts."""
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

        # Set up Flaresolverr (only needed for MODDB entries)
        self.flare = None
        fs_cfg = config.get("flaresolverr", {})
        if fs_cfg.get("url"):
            from .flaresolverr_client import FlaresolverrClient
            self.flare = FlaresolverrClient(
                url=fs_cfg["url"],
                timeout_ms=fs_cfg.get("timeout_ms", 60000),
            )
        else:
            print("⚠️  No Flaresolverr configured — MODDB downloads will fail")

        # Set up destination
        self.dest_mode = config["destination"]["mode"]
        self.ssh_client: Optional[SSHClient] = None
        if self.dest_mode == "ssh":
            ssh_cfg = config["destination"]["ssh"]
            if ssh_cfg.get("host") and ssh_cfg.get("user"):
                self.ssh_client = SSHClient(
                    host=ssh_cfg["host"],
                    user=ssh_cfg["user"],
                    port=ssh_cfg.get("port", 22),
                    key_file=ssh_cfg.get("key_file"),
                )

        # Set up links file
        self.links = LinksFile(
            local_path=config["links_file"],
            ssh=self.ssh_client,
            remote_path=config.get("destination", {}).get("ssh", {}).get("remote_links_file"),
        )

        os.makedirs(self.download_dir, exist_ok=True)

    def download_entry(self, entry: Dict[str, str]) -> bool:
        """
        Download a single PENDING entry, verify MD5, copy to destination.

        Returns True on success, False on failure.
        """
        url = entry["url"]
        filename = entry["filename"]
        expected_md5 = entry.get("expected_md5", "")
        source = entry.get("source", "MODDB")
        local_path = os.path.join(self.download_dir, filename)

        print(f"\n{'='*60}")
        print(f"📦 File: {filename}")
        print(f"🔖 Description: {entry.get('description', 'N/A')}")
        print(f"👤 Author: {entry.get('author', 'N/A')}")
        if expected_md5:
            print(f"🔍 Expected MD5: {expected_md5}")
        else:
            print(f"🔍 Expected MD5: (none — will skip verification)")
        print(f"🌐 Source: {source}")

        # Check if already downloaded locally with correct MD5
        if os.path.exists(local_path):
            if expected_md5:
                actual_md5 = md5_file(local_path)
                if actual_md5 == expected_md5:
                    print(f"  ✅ Already downloaded with correct MD5")
                    entry["actual_md5"] = actual_md5
                    if self._copy_to_destination(local_path, filename):
                        entry["status"] = "DOWNLOADED"
                        return True
                else:
                    print(f"  ⚠️  Local MD5 mismatch (got {actual_md5}), re-downloading")
            else:
                # No MD5 to verify — skip redownload if file exists and has size
                if os.path.getsize(local_path) > 100:
                    print(f"  ✅ Already exists (no MD5 to verify)")
                    if self._copy_to_destination(local_path, filename):
                        entry["status"] = "DOWNLOADED"
                        return True

        # Download based on source
        if source == "GITHUB":
            ok = self._download_github(url, local_path)
        else:
            ok = self._download_moddb(url, local_path)

        if not ok:
            return False

        size_kb = os.path.getsize(local_path) / 1024
        print(f"  ✅ Downloaded: {size_kb:.0f} KB")

        # Verify MD5 (if we have one)
        if expected_md5:
            actual_md5 = md5_file(local_path)
            entry["actual_md5"] = actual_md5
            if actual_md5 != expected_md5:
                print(f"  ❌ MD5 MISMATCH: expected {expected_md5}, got {actual_md5}")
                os.remove(local_path)
                return False
            print(f"  ✅ MD5 OK")
        else:
            print(f"  ⚠️  No MD5 to verify — skipped")
            entry["actual_md5"] = md5_file(local_path)

        # Copy to destination
        if self._copy_to_destination(local_path, filename):
            entry["status"] = "DOWNLOADED"
            return True
        else:
            return False

    def _download_moddb(self, url: str, local_path: str) -> bool:
        """Download a MODDB-hosted file via Flaresolverr."""
        if not self.flare:
            print(f"  ❌ Flaresolverr not configured, cannot download MODDB link")
            return False

        import subprocess

        print(f"  🌐 Resolving ModDB page via Flaresolverr...")
        try:
            result = self.flare.resolve(url)
        except Exception as e:
            print(f"  ❌ Flaresolverr error: {e}")
            return False

        sol = result.get("solution", {})
        html = sol.get("response", "")

        # Extract mirror download URL
        mirror_url = self.flare.extract_mirror_url(html)
        if not mirror_url:
            print(f"  ❌ Could not extract mirror link from page")
            return False

        cookies = sol.get("cookies", [])
        user_agent = sol.get("userAgent", "")

        # Download the file
        print(f"  ⬇️  Downloading from mirror...")
        cookie_header = self.flare.build_cookie_header(cookies)

        cmd = [
            "curl", "-sL",
            "-A", user_agent,
            "-H", f"Cookie: {cookie_header}",
            "-o", local_path,
            "-w", "%{http_code}",
            "--max-time", "120",
            mirror_url,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
            http_code = result.stdout.strip()
        except Exception as e:
            print(f"  ❌ Download failed: {e}")
            return False

        if os.path.exists(local_path) and os.path.getsize(local_path) > 100:
            return True

        print(f"  ❌ Download failed (HTTP {http_code})")
        return False

    def _download_github(self, url: str, local_path: str) -> bool:
        """Download a GitHub-hosted file directly (no Flaresolverr needed)."""
        import subprocess

        print(f"  ⬇️  Downloading from GitHub...")
        # GitHub downloads work with -L (follow redirects)
        cmd = [
            "curl", "-sL",
            "-o", local_path,
            "-w", "%{http_code}",
            "--max-time", "120",
            url,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
            http_code = result.stdout.strip()
        except Exception as e:
            print(f"  ❌ Download failed: {e}")
            return False

        if os.path.exists(local_path) and os.path.getsize(local_path) > 100:
            return True

        print(f"  ❌ Download failed (HTTP {http_code})")
        return False

    def _copy_to_destination(self, local_path: str, filename: str) -> bool:
        """Copy a downloaded file to its configured destination."""
        if self.dest_mode == "ssh" and self.ssh_client:
            remote_path = self.config["destination"]["ssh"]["remote_path"] + "\\" + filename
            remote_path_scp = remote_path.replace("\\", "/")
            if self.ssh_client.copy_to(local_path, remote_path_scp):
                print(f"  ✅ Copied to remote: {remote_path}")
                return True
            else:
                print(f"  ❌ SCP to remote failed")
                return False

        else:
            import shutil
            dest_dir = self.config["destination"]["local_path"]
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, filename)

            if os.path.exists(dest):
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(dest):
                    dest = os.path.join(dest_dir, f"{base}_{counter}{ext}")
                    counter += 1

            shutil.copy2(local_path, dest)
            print(f"  ✅ Copied to: {dest}")
            return True

    def download_all(self) -> Dict[str, int]:
        """Download all PENDING entries. Returns {success, fail, total_pending}."""
        entries = self.links.read()
        pending = [e for e in entries if e["status"] == "PENDING"]
        total, dl, pend, moddb, github = self.links.status_summary()

        print(f"\n📊 Total: {total} | DOWNLOADED: {dl} | PENDING: {pend}")
        print(f"   MODDB: {moddb} | GITHUB: {github}")

        if not pending:
            print("🎉 Nothing to download!")
            return {"success": 0, "fail": 0, "total_pending": 0}

        success = 0
        fail = 0
        progress_file = os.path.join(self.download_dir, "_progress.txt")

        for i, entry in enumerate(pending, 1):
            print(f"\n--- [{i}/{len(pending)}] ---")
            ok = self.download_entry(entry)
            if ok:
                success += 1
            else:
                fail += 1

            with open(progress_file, "w") as pf:
                pf.write(f"{i}/{len(pending)} | OK:{success} FAIL:{fail}\n")

            if i < len(pending):
                time.sleep(self.delay)

        print(f"\n{'='*60}")
        print(f"🏁 DONE: {success} OK, {fail} FAIL of {len(pending)} PENDING")

        return {"success": success, "fail": fail, "total_pending": len(pending)}
