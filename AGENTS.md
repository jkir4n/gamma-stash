# Agent Notes — Gamma Mods Downloader

Small Python 3.9+ CLI for batch-downloading G.A.M.M.A. mods. No test suite, no CI, no linter/formatter config.

## Build & run

```bash
pip install .
# or
pip install -r requirements.txt

gamma-mods-downloader --help
python -m gamma_mods_downloader --help
```

- Entry point: `gamma_mods_downloader.cli:main`
- `GMD_DEBUG=1` prints full tracebacks; otherwise errors print a one-line message.

## Build a single-file executable

```bash
pip install .[build]
python scripts/build_exe.py
```

Produces `dist/gamma-mods-downloader.exe` (Windows) or `dist/gamma-mods-downloader` (Linux/macOS). The executable still requires `curl` on `PATH`; Flaresolverr and ssh/scp are needed only for their respective optional features.

## CLI commands

| Command | Notes |
|---------|-------|
| `init` | Writes `config.yaml` in cwd. Auto-detects GAMMA `mods.txt` from hard-coded Windows paths (`D:\GAMMA\...`, `C:\GAMMA\...`) and falls back to `mods.txt`. |
| `status` | Prints totals + category breakdown. |
| `list` | Supports `--pending`, `--moddb`, `--github`, `--verbose`. |
| `download` | Downloads all `PENDING` entries sequentially. Writes `_progress.txt` to `download_dir` after each entry. `max_concurrent` is read but ignored. |

## External dependencies

- **PyYAML** — only runtime dependency (`requirements.txt`).
- **curl** — invoked via `subprocess` for all downloads; must be on `PATH`.
- **Flaresolverr** — required only for MODDB links; GitHub links download directly.
- **ssh/scp** — required only when `destination.mode == "ssh"`. Assumes a **Windows remote host** (commands use `type "file"`, `if exist "file"`).

## Links file format (important)

The parser expects **GAMMA's official `mods.txt`** format (tab-separated), not the `jdownloader_links_sample.txt` in `sample_data/`:

```text
Audio
https://www.moddb.com/addons/start/222467	0	 - Author	Description	moddb_page	filename.zip	MD5
https://github.com/.../archive/refs/heads/main.zip	install_path	 - Author	Description		filename.zip	MD5
```

Fields: `URL \t install_path \t - author \t description \t moddb_page_url \t filename \t MD5`

- Lines not starting with `http` are treated as category headers.
- `sample_data/jdownloader_links_sample.txt` uses pipe separators and a different schema; do not use it as a reference.
- `sample_data/mods_sample.txt` is a valid example of the tab-separated format the parser expects.
- GitHub entries have an empty `moddb_page_url` field (fifth field blank).

## Config

Load order: `--config` → `./config.yaml` → `~/.config/gamma-mods-downloader/config.yaml` → package-parent `config.yaml`.

The README mentions `./gamma-mods-downloader.yaml` and `/etc/...` — these are **not** in the code.

Environment overrides use `GMD_*` prefix (e.g. `GMD_FLARESOLVERR_URL`). See `_apply_env_overrides` in `config.py:112` for the full mapping — values are cast to bool/int based on the default's type.

Actual config keys in code (the README is partly stale):

```yaml
links_file: "mods.txt"        # path to GAMMA mods.txt
download_dir: "./downloads"
download_delay: 2
max_concurrent: 1             # currently ignored; downloads are sequential
flaresolverr:
  url: "http://localhost:8191/v1"
  timeout_ms: 60000
destination:
  mode: "local"               # or "ssh"
  local_path: "./completed"
  ssh:
    host: ""
    user: ""
    port: 22
    key_file: ""
    remote_path: ""           # Windows path like D:\\gamma\\downloads
    remote_links_file: ""     # path to remote mods.txt
tracking_file: ""             # reserved, not actively used
```

## Important gotchas

- **Status is not persisted back to `mods.txt`.** `LinksFile.update_entry_status()` is a no-op TODO. After `download`, the file is not rewritten; status exists only in memory.
- `max_concurrent` is read from config but has no effect — downloads run one at a time.
- SSH destination assumes a **Windows remote host** (`type "file"`, `if exist "file"`).
- For MODDB downloads, Flaresolverr must return a `/downloads/mirror/<hash>` link in the page HTML; mirror extraction is a single regex (`flaresolverr_client.py:74`).
- Downloads skip files smaller than ~100 bytes and treat them as failures.
- `download_all` writes progress to `_progress.txt` in `download_dir` after each entry (simple `N/M | OK:X FAIL:Y` format).
- GitHub downloads use `curl -sL` directly (no Flaresolverr). Only MODDB entries go through Flaresolverr for Cloudflare bypass.
