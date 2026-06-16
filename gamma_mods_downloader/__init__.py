"""
G.A.M.M.A. Mods Downloader.

Batch download G.A.M.M.A. mods from ModDB (via Flaresolverr) and GitHub,
using the official mods.txt manifest from G.A.M.M.A. itself.
"""

__description__ = "Batch download G.A.M.M.A. mods using the official mods.txt manifest"

from .config import load_config
from .downloader import LinksFile, Downloader, md5_file
