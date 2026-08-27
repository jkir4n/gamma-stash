"""
G.A.M.M.A. Mods Downloader — "Gamma Ray"

Batch download G.A.M.M.A. mods from ModDB (via Flaresolverr) and GitHub,
using the official mods.txt manifest from G.A.M.M.A. itself.
"""

__version__ = "0.6.1"
__app_name__ = "G.A.M.M.A. STASH"

from .config import load_config
from .downloader import LinksFile, Downloader, md5_file, verify_archive_integrity, export_failed_report
from .doctor import run_doctor
from .setup import run_diff_command, inspect_modlist_diff
