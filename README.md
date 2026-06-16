# G.A.M.M.A. STASH

[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**G.A.M.M.A. STASH** is a Windows CLI tool that batch-downloads S.T.A.L.K.E.R. G.A.M.M.A. mods using the official `mods.txt` manifest from your GAMMA installation.

---

## Features

- **Interactive setup wizard** — checks dependencies, auto-installs missing tools via `winget`, configures Flaresolverr (manual IP or Docker self-host)
- **MD5-aware scanning** — checks existing files against expected hashes, skips already-downloaded mods
- **Cloudflare bypass** — MODDB downloads via Flaresolverr; GitHub downloads directly
- **Live progress bars** — download speed, file size, and percentage during transfers
- **Auto-cleanup** — after downloads, offers to stop/remove Docker containers and uninstall Docker
- **Zero persistence** — no config files, no leftover state; every run is self-contained

## Quick Start

### Download

Grab the latest `gamma-stash.exe` from [Releases](https://github.com/your-org/gamma-stash/releases).

### Run

Double-click `gamma-stash.exe` — the setup wizard walks you through everything:

1. **Dependency check** — ensures `curl` is on PATH (auto-installs via winget if missing)
2. **Flaresolverr setup** — enter IP of an existing instance, or let the tool self-host via Docker
3. **Locate GAMMA** — point it at your GAMMA installation folder (e.g., `D:\GAMMA`)
4. **Scan modlist** — MD5-checks every downloaded file, shows what's missing
5. **Download** — fetches only the mods you need with live progress bars
6. **Cleanup** — optionally removes Docker containers and Docker itself

### Command Line

```
gamma-stash             Run the setup + download wizard
gamma-stash setup        Same as above
gamma-stash cleanup      Stop/remove Flaresolverr container, uninstall Docker
gamma-stash --version    Show version
gamma-stash --help       Show help
```

## Requirements

- Windows 10 or later
- `curl` — included with Windows 10+; auto-installed via winget if missing
- Flaresolverr — enter an existing instance IP, or let the tool self-host via Docker
- Docker Desktop (optional) — only needed if you choose self-hosted Flaresolverr

## How It Works

1. Parses your GAMMA `mods.txt` (tab-separated format: `URL | install_path | author | description | moddb_page | filename | MD5`)
2. For each mod, checks if the file already exists in `downloads/` with the correct MD5 — skips if match
3. Downloads missing files:
   - **MODDB links** → resolves via Flaresolverr (Cloudflare bypass), extracts mirror URL, downloads with `curl`
   - **GitHub links** → downloads directly with `curl`
4. Verifies MD5 after download, deletes and retries on mismatch

## Building from Source

```bash
pip install .[build]
python scripts/build_exe.py
```

Produces `dist/gamma-stash.exe`.

To generate the icon:

```bash
pip install Pillow
python scripts/generate_icon.py
```

## Project Structure

```
gamma_mods_downloader/
├── cli.py                      CLI entry point + commands
├── setup.py                    Interactive setup wizard
├── terminal.py                 STALKER-themed colors, spinners, progress bars
├── downloader.py               Mods.txt parser + download engine + MD5 verifier
├── flaresolverr_client.py      Flaresolverr API client
├── config.py                   Config loading (YAML, env vars)
├── __init__.py                 Package metadata (version, app name)
└── __main__.py                 python -m support

scripts/
├── build_exe.py                PyInstaller single-file build
└── generate_icon.py            Icon generator

.github/workflows/
├── ci.yml                      CI: install + smoke test on Python 3.9-3.13
└── release.yml                 Build exe on tag push, attach to GitHub Release
```

## License

MIT
