# Agent Notes — G.A.M.M.A. STASH

Single-file Windows CLI to batch-download G.A.M.M.A. mods. No tests, no lint config, no config files persisted.

## Commands

```
gamma-stash              → runs setup + download wizard (default)
gamma-stash setup        → same as above
gamma-stash cleanup      → stop/rm Flaresolverr container, prune Docker, optional uninstall
gamma-stash --version    → prints version
```

Entry point: `gamma_mods_downloader.cli:main`. `GMD_DEBUG=1` for full tracebacks.

## Build

```bash
pip install .[build]       # pyyaml + pyinstaller
python scripts/build_exe.py  # → dist/gamma-stash.exe
```

Icon is pre-generated at `icon.ico` (built from `scripts/generate_icon.py` with Pillow).

## Architecture

```
setup.py          WIZARD — deps check, Flaresolverr config (manual IP or winget/Docker),
                  GAMMA folder prompt, mods.txt scan + MD5 check, download dispatch, cleanup
downloader.py     ENGINE — mods.txt parser (tab-separated), LinksFile, Downloader,
                  MD5 verification, curl subprocess downloads with progress bars
terminal.py       UI — ANSI colors, Spinner, ProgressBar, print helpers
cli.py            ENTRY — argparse with 2 subcommands + default flow
flaresolverr_client.py  — HTTP client for Flaresolverr API
config.py         — YAML config loader (used internally only, not persisted to disk)
```

## mods.txt format (tab-separated)

```
URL \t install_path \t - author \t description \t moddb_page \t filename \t MD5
```

Lines not starting with `http` are category headers. GitHub entries have an empty 5th field.

## Key behaviors

- **No persistent state** — config.yaml is never written. Every run is self-contained.
- **MD5 skip** — scanner checks existing files in GAMMA's `downloads/` folder. MD5 match → skip.
- **MD5 mismatch** → re-downloads. No MD5 + file >100 bytes → skips.
- **Downloads are sequential** (`max_concurrent` ignored).
- **Progress bars** update via `\r` carriage return (keep terminal ≥90 cols wide).
- **Docker auto-detect** — if Docker is installed and Flaresolverr container is running, grabs URL automatically.
- **Dependency install** — curl and Docker installed via `winget` (Windows only).
- **Docker cleanup** — stop container → rm container → rmi image → optional uninstall via winget + leftover file sweep + `MoveFileEx` for locked files.

## Versioning (semver)

Bump `__version__` in both `gamma_mods_downloader/__init__.py` and `pyproject.toml`, then:
```bash
git tag v0.X.Y && git push origin --tags
```
Patch = bug fix, minor = new feature. Release workflow builds Windows exe and attaches to GitHub Release.

## Gotchas

- `LinksFile.update_entry_status()` is a no-op — status is never persisted to mods.txt.
- `windows-latest` only in release workflow (no Linux/macOS builds).
- `curl` must be on PATH (built into Windows 10+).
- Flaresolverr required only for MODDB; GitHub downloads go direct.
- ANSI codes must stay inside `{RESET}` boundaries on ProgressBar lines or they break width calculation.
- `_copy_to_destination` no-ops when `download_dir == destination.local_path`.
