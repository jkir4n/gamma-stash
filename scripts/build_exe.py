#!/usr/bin/env python3
"""Build a single-file executable with PyInstaller.

Usage:
    pip install .[build]
    python scripts/build_exe.py

Output:
    dist/gamma-mods-downloader.exe   (Windows)
    dist/gamma-mods-downloader       (Linux/macOS)
"""
import os
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed.")
        print("Install it with:  pip install .[build]")
        return 1

    # Clean previous builds
    for d in (DIST_DIR, BUILD_DIR):
        if os.path.isdir(d):
            shutil.rmtree(d)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name", "gamma-mods-downloader",
        "--console",
        "--clean",
        "--noconfirm",
        "--distpath", DIST_DIR,
        "--workpath", BUILD_DIR,
        "--specpath", BUILD_DIR,
        os.path.join(PROJECT_ROOT, "gamma_mods_downloader", "__main__.py"),
    ]

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        return result.returncode

    exe = "gamma-mods-downloader.exe" if sys.platform == "win32" else "gamma-mods-downloader"
    exe_path = os.path.join(DIST_DIR, exe)
    if os.path.exists(exe_path):
        print(f"\nBuilt: {exe_path}")
        print("\nNote: The executable still requires 'curl' on PATH.")
        print("      Flaresolverr is needed only for MODDB downloads.")
    else:
        print("\nBuild finished but executable not found in dist/")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
