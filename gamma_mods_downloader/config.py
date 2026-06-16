"""
Configuration for the Gamma Mods Downloader.

Config is loaded from YAML files with environment variable overrides (GMD_*).
"""

import os
from typing import Any, Dict, Optional


def _find_config() -> str:
    """Locate config.yaml -- search order: cwd, ~/.config, script dir."""
    search_paths = [
        os.path.join(os.getcwd(), "config.yaml"),
        os.path.expanduser("~/.config/gamma-mods-downloader/config.yaml"),
    ]
    # Also check the parent of the script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    proj_dir = os.path.dirname(script_dir)
    search_paths.append(os.path.join(proj_dir, "config.yaml"))

    # Default: use the first existing one
    for p in search_paths:
        if os.path.exists(p):
            return p
    return search_paths[0]  # fallback: cwd/config.yaml


DEFAULT_CONFIG: Dict[str, Any] = {
    "links_file": "",
    "download_dir": "",
    "download_delay": 2,
    "max_concurrent": 1,
    "flaresolverr": {
        "url": "http://localhost:8191/v1",
        "timeout_ms": 60000,
    },
    "destination": {
        "local_path": "",
    },
    "tracking_file": "",
}


def load_config(config_path: Optional[str] = None,
                env_prefix: str = "GMD_") -> Dict[str, Any]:
    """
    Load configuration from YAML + env var overrides.

    Env vars override YAML values. Use GMD_FLARESOLVERR_URL, GMD_DOWNLOAD_DIR,
    GMD_DEST_HOST, GMD_DEST_MODE, etc.

    If PyYAML is not available, falls back to defaults + env overrides.
    """
    config = dict(DEFAULT_CONFIG)

    if config_path is None:
        config_path = _find_config()

    # Try to load YAML
    try:
        import yaml
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                user_cfg = yaml.safe_load(f) or {}
            _deep_merge(config, user_cfg)
    except (ImportError, FileNotFoundError, yaml.YAMLError):
        pass

    # Apply env var overrides
    _apply_env_overrides(config, env_prefix)

    # Derive defaults for empty paths
    _set_default_paths(config)

    # Validate
    if not config["links_file"]:
        raise ValueError(
            "links_file not set. Use GMD_LINKS_FILE env var or set in config.yaml"
        )
    if not config["download_dir"]:
        raise ValueError(
            "download_dir not set. Use GMD_DOWNLOAD_DIR env var or set in config.yaml"
        )

    return config


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    """Recursively merge override dict into base dict."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _apply_env_overrides(config: Dict[str, Any], prefix: str) -> None:
    """Apply GMD_* env vars as overrides into the config dict."""
    flatten = _flatten_dict(config)

    for key, value in flatten.items():
        env_key = f"{prefix}{key.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            # Cast to appropriate type
            if isinstance(value, bool):
                env_val = env_val.lower() in ("true", "1", "yes")
            elif isinstance(value, int):
                try:
                    env_val = int(env_val)
                except ValueError:
                    continue
            _set_nested(config, key.split("."), env_val)


def _flatten_dict(d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Flatten nested config dict into dot-separated keys."""
    result = {}
    for key, value in d.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten_dict(value, full_key))
        else:
            result[full_key] = value
    return result


def _set_nested(d: Dict[str, Any], keys: list, value: Any) -> None:
    """Set a value in nested dict using a list of keys."""
    current = d
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        current = current[k]
    current[keys[-1]] = value


def _set_default_paths(config: Dict[str, Any]) -> None:
    """Set reasonable default paths for empty config values."""
    if not config["destination"]["local_path"]:
        config["destination"]["local_path"] = config["download_dir"]
