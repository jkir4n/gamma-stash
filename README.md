# Gamma Mods Downloader

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

Batch download **G.A.M.M.A.** mods from ModDB with automated Cloudflare bypass, MD5 verification, and status tracking.

---

## Features

- 🛡️ **Cloudflare bypass** — Flaresolverr handles JS challenges automatically
- 🔐 **MD5 verification** — Every download is checksum-verified before marking complete
- 📋 **Status tracking** — Links file (URL | Filename | MD5 | Status) keeps a clear record of what's done and what's pending
- 🌐 **Local or remote destinations** — Save to a local folder or SCP to a remote machine (e.g., a Windows gaming PC)
- 📊 **HTML tracking page** — Generate a browsable table with download status, MD5 column, and sorting
- ⚙️ **Configurable** — YAML config file with environment variable overrides

---

## Requirements

- **Python 3.9+**
- **Flaresolverr** — A running instance (Docker is easiest)
- **curl** — Used for actual file downloads (more reliable for large files than `urllib`)
- **SSH client** (optional) — Only needed if copying files to a remote machine

---

## Quick Start

### 1. Install

```bash
# Clone or copy the project, then:
pip install .
```

Or install dependencies manually:

```bash
pip install -r requirements.txt
```

### 2. Start Flaresolverr

```bash
docker run -d --name flaresolverr -p 8191:8191 flaresolverr/flaresolverr
```

### 3. Create config

```bash
gamma-mods-downloader init
```

Edit the generated `config.yaml` for your setup.

### 4. Prepare your links file

Create a `jdownloader_links.txt` file with your mods:

```
# Format: URL | Filename | Expected MD5 | Status
https://www.moddb.com/addons/start/XXXXX | SomeMod.zip | abcdef1234567890abcdef1234567890 | PENDING
https://www.moddb.com/addons/start/YYYYY | AnotherMod.7z | 1234567890abcdef1234567890abcdef | DOWNLOADED
```

> **Getting MD5 hashes:** Download a file manually once, then run `md5sum filename` (Linux/macOS) or `certutil -hashfile filename MD5` (Windows). Add the hash to prevent re-downloading it.

### 5. Check status

```bash
gamma-mods-downloader status
```

### 6. Download!

```bash
gamma-mods-downloader download
```

---

## Usage

### Commands

| Command | Description |
|---------|-------------|
| `init` | Create a sample `config.yaml` |
| `status` | Show download summary (total / downloaded / pending) |
| `list` | List every entry with its status |
| `download` | Download all pending mods |
| `rebuild-html` | Rebuild the HTML tracking page |

### Options

| Flag | Description |
|------|-------------|
| `-c, --config PATH` | Path to config file (default: auto-detect) |
| `-V, --version` | Show version |

### Examples

```bash
# Show status with a custom config
gamma-mods-downloader -c /path/to/config.yaml status

# List all pending downloads
gamma-mods-downloader list | grep PENDING

# Download with defaults
gamma-mods-downloader download
```

---

## Configuration

### Lookup order

1. Path from `--config` CLI argument
2. `./config.yaml` (current directory)
3. `./gamma-mods-downloader.yaml`
4. `~/.config/gamma-mods-downloader/config.yaml`
5. `/etc/gamma-mods-downloader/config.yaml`

### Full config reference

```yaml
# Flaresolverr service (required)
flaresolverr:
  url: "http://localhost:8191/v1"
  timeout_ms: 60000

# Path to your mods list file
links_file: "jdownloader_links.txt"

# Temporary download directory
download_dir: "./downloads"

# Destination for completed downloads
destination:
  mode: "local"                # "local" or "ssh"
  local_path: "./completed"    # local destination
  ssh:                         # only used if mode == "ssh"
    host: "192.168.1.100"
    user: "username"
    port: 22
    key_file: "~/.ssh/id_ed25519"
    remote_path: "D:\\gamma\\downloads"
    remote_links_file: "D:\\gamma\\jdownloader_links.txt"

# Download behaviour
download_delay: 2              # seconds between downloads (be nice to ModDB)
max_concurrent: 1              # sequential only (default)

# HTML tracking page (optional)
html_output:
  enabled: false
  file: "mods_to_download.html"
  remote: false                # true if HTML file lives on SSH host
```

### Environment variable overrides

All config values can be overridden via environment variables. Prefix with `GMD_`:

```bash
export GMD_FLARESOLVERR_URL="http://192.168.1.50:8191/v1"
export GMD_DEST_MODE="ssh"
export GMD_SSH_HOST="192.168.1.100"
export GMD_SSH_USER="jkir4"
export GMD_DOWNLOAD_DIR="/tmp/mods"
gamma-mods-downloader download
```

Full list of env vars:

| Variable | Overrides |
|----------|-----------|
| `GMD_FLARESOLVERR_URL` | `flaresolverr.url` |
| `GMD_FLARESOLVERR_TIMEOUT` | `flaresolverr.timeout_ms` |
| `GMD_LINKS_FILE` | `links_file` |
| `GMD_DOWNLOAD_DIR` | `download_dir` |
| `GMD_DEST_MODE` | `destination.mode` |
| `GMD_DEST_LOCAL_PATH` | `destination.local_path` |
| `GMD_SSH_HOST` | `destination.ssh.host` |
| `GMD_SSH_USER` | `destination.ssh.user` |
| `GMD_SSH_PORT` | `destination.ssh.port` |
| `GMD_SSH_KEY_FILE` | `destination.ssh.key_file` |
| `GMD_SSH_REMOTE_PATH` | `destination.ssh.remote_path` |
| `GMD_SSH_REMOTE_LINKS_FILE` | `destination.ssh.remote_links_file` |
| `GMD_PROXY` | `proxy` |
| `GMD_MAX_CONCURRENT` | `max_concurrent` |
| `GMD_DOWNLOAD_DELAY` | `download_delay` |
| `GMD_HTML_ENABLED` | `html_output.enabled` |
| `GMD_HTML_FILE` | `html_output.file` |
| `GMD_HTML_REMOTE` | `html_output.remote` |

---

## Project Structure

```
gamma-mods-downloader/
├── README.md                     # This file
├── pyproject.toml                # Python package metadata
├── requirements.txt              # Dependencies
├── config.yaml                   # User configuration (generate with init)
├── gamma_mods_downloader/
│   ├── __init__.py               # Package metadata
│   ├── __main__.py               # `python -m gamma_mods_downloader` support
│   ├── cli.py                    # CLI entry point
│   ├── config.py                 # Config loading (YAML + env vars)
│   ├── flaresolverr_client.py    # Flaresolverr API client
│   ├── ssh_utils.py              # SSH/SCP utilities
│   ├── downloader.py             # Main download logic
│   └── html_rebuilder.py         # HTML tracking page builder
├── sample_data/
│   └── jdownloader_links_sample.txt
└── scripts/
    ├── download_all.sh            # Convenience launcher
    └── rebuild_html.sh            # Convenience launcher
```

---

## How It Works

1. **Parse** — Reads your `jdownloader_links.txt` and identifies `PENDING` entries
2. **Resolve** — For each pending mod, sends the ModDB URL to Flaresolverr, which runs the Cloudflare JS challenge and returns the resolved page with cookies
3. **Extract** — Parses the ModDB page HTML to find the mirror download link
4. **Download** — Downloads the file using `curl` with the Flaresolverr-provided cookies and User-Agent
5. **Verify** — Computes the MD5 of the downloaded file and compares it against the expected hash
6. **Deliver** — Copies the verified file to the destination (local folder or remote via SCP)
7. **Track** — Updates the links file status from `PENDING` to `DOWNLOADED`
8. **Report** — Optionally rebuilds an HTML tracking page

---

## Architecture

```
┌────────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  Gamma Mods        │────▶│  Flaresolverr    │────▶│  ModDB / Mod     │
│  Downloader        │     │  (Docker)        │     │  Download Page   │
│                    │◀────│  resolves JS     │◀────│  (Cloudflare)    │
│  - CLI entry point │     │  challenges      │     └──────────────────┘
│  - Config loader   │     └─────────────────┘
│  - Download engine │              │
│  - MD5 verifier    │              ▼
│  - SSH transport   │     ┌─────────────────┐
└────────────────────┘     │  curl download   │
         │                 │  from mirror     │
         ▼                 └─────────────────┘
┌────────────────────┐              │
│  Links File        │              ▼
│  (status tracking) │     ┌─────────────────┐
└────────────────────┘     │  MD5 verify     │
                           └─────────────────┘
                                    │
                                    ▼
                           ┌─────────────────┐
                           │  Destination    │
                           │  (local / SSH)   │
                           └─────────────────┘
```

---

## Troubleshooting

### Flaresolverr won't start

Make sure Docker is installed and the port isn't taken:

```bash
# Check if it's running
curl http://localhost:8191/v1
# Expected: {"msg":"FlareSolverr is ready.","startTime":...,"version":"..."}
```

### Downloads fail with HTTP 403

- Flaresolverr might be overloaded. Increase `timeout_ms` (try 90000)
- ModDB might have rate-limited you. Increase `download_delay` (try 5-10 seconds)
- Check that Flaresolverr can reach the internet: `docker logs flaresolverr`

### MD5 mismatch

- The file on ModDB might have been updated. Check the mod page for version changes
- Manually download and re-compute the MD5: `md5sum downloaded_file.zip`

### SCP to remote fails

- Verify SSH key is set up: `ssh user@host` works from your terminal
- Check the remote path exists and is writable
- For Windows destinations: the path format should use forward slashes for SCP

---

## License

MIT
