# G.A.M.M.A. STASH

[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**G.A.M.M.A. STASH** is a Windows CLI tool that batch-downloads S.T.A.L.K.E.R. G.A.M.M.A. mods using the official `mods.txt` manifest from your GAMMA installation.

---

## Features

- **Next-Gen TUI & CLI managers** — rich Textual TUI with live `DataTable`, dual progress bars, speed telemetry, and a dedicated `--cli` fallback
- **High-throughput concurrent downloads** — parallel worker pool for GitHub direct downloads alongside sequential ModDB handling
- **Sub-second hash caching** — `.stash_cache.json` metadata cache avoids redundant full-disk re-hashing
- **HTTP `Range` resume** — interrupted downloads resume from their last byte on partial `.part` files
- **Flaresolverr session pooling** — persistent browser sessions drop Cloudflare resolution times from ~12s to ~2s per link
- **Auto-discovery & disk safety** — auto-detects G.A.M.M.A. paths across all drives and verifies available disk space
- **Atomic downloads & retries** — downloads stage to `.part` files and rename atomically upon verified HTTP status and MD5 matches
- **Auto-cleanup** — after downloads, offers safe cleanup of Flaresolverr containers without removing existing Docker setups

## Quick Start

### Download

Grab the latest `gamma-stash.exe` from [Releases](https://github.com/jkir4n/gamma-stash/releases).

### Run

Double-click `gamma-stash.exe` — the setup wizard walks you through everything:

1. **Dependency check** — ensures `curl` is on PATH (auto-installs via winget if missing)
2. **Flaresolverr setup** — enter IP of an existing instance, or let the tool self-host via Docker
3. **Locate GAMMA** — auto-detects installation paths or lets you enter a custom folder
4. **Scan modlist** — fast cached MD5 verification shows missing or corrupted mods
5. **Download** — high-speed concurrent batch downloading with resume support
6. **Cleanup** — optionally removes Flaresolverr containers

### Command Line

```
gamma-stash                                 Launch the TUI wizard (default)
gamma-stash setup                           Run the CLI wizard (no TUI)
gamma-stash --cli                           Force CLI mode for default flow
gamma-stash setup --gamma-dir "D:\GAMMA"    Specify GAMMA folder directly
gamma-stash setup -y                        Run unattended (auto-yes to prompts)
gamma-stash cleanup                         Stop/remove Flaresolverr container
gamma-stash --version                       Show version
gamma-stash --help                          Show help
```

## Requirements

- Windows 10 or later
- `curl` — included with Windows 10+; auto-installed via winget if missing
- Flaresolverr — enter an existing instance IP, or let the tool self-host via Docker
- Docker Desktop (optional) — only needed if you choose self-hosted Flaresolverr

## Docker Desktop Setup (Windows)

Docker Desktop requires WSL 2 or Hyper-V on Windows.

### Option 1: WSL 2 (Recommended)

1. Open **PowerShell as Administrator**
2. Install WSL:
   ```
   wsl --install
   ```
3. Restart your PC when prompted
4. Download and install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)
5. During Docker Desktop install, ensure **"Use WSL 2 instead of Hyper-V"** is checked
6. Start Docker Desktop from the Start menu — wait for the engine to start (whale icon stops animating)

### Option 2: Hyper-V

1. Open **PowerShell as Administrator**
2. Enable Hyper-V:
   ```
   Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All
   ```
3. Restart your PC
4. Download and install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)
5. Start Docker Desktop from the Start menu

### Verify

```powershell
docker --version
docker run hello-world
```

The tool can also auto-install Docker Desktop via `winget` if missing — just say yes when prompted.

## How It Works

1. Parses your GAMMA `mods.txt` (tab-separated format: `URL | install_path | author | description | moddb_page | filename | MD5`)
2. For each mod, checks if the file already exists in `downloads/` with the correct MD5 — skips if match, flags for re-download if corrupt
3. Downloads missing files:
   - **MODDB links** → resolves via Flaresolverr (Cloudflare bypass), extracts mirror URL, downloads with `curl`
   - **GitHub links** → downloads directly with `curl`
4. Downloads stage to `.part` files, verify HTTP status, verify MD5, retry on failure, and atomically finalize

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

## Antivirus Notice

PyInstaller single-file executables can trigger **false positives** in some antivirus engines. This is a known issue with PyInstaller — the way it bundles Python and extracts to a temp directory at runtime mimics certain malware behaviors.

- The entire source code is available in this repository — nothing is hidden
- Every release is built via a **public GitHub Actions workflow** you can inspect
- Scan the exe yourself at [VirusTotal](https://www.virustotal.com) if concerned
- The executable only: reads your GAMMA `mods.txt`, downloads files via `curl`, and optionally manages Docker containers
