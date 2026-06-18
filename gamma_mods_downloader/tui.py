"""
Textual TUI for G.A.M.M.A. STASH — interactive setup + download wizard.
"""

import os
import asyncio
from typing import Any, Dict, Optional

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static
from textual.worker import Worker, WorkerState
from textual import work

from . import __version__
from .setup import (
    check_all_dependencies, _install_curl, _install_docker,
    validate_flaresolverr,
    _find_docker, _docker_daemon_ok, _docker_container_exists,
    _docker_container_running, _docker_run_flaresolverr,
    _is_gamma_folder, _find_mods_txt, _find_downloads_folder,
    scan_modlist, cleanup_docker, _check_virtualization, _is_windows,
)
from .downloader import Downloader


# ---------------------------------------------------------------------------
# Modal confirm dialog
# ---------------------------------------------------------------------------

class ConfirmScreen(ModalScreen[bool]):
    CSS = """
    #dialog {
        background: $surface;
        border: thick $accent;
        padding: 2 3;
        width: 52;
        height: auto;
        align: center middle;
    }
    #buttons {
        align: center middle;
        margin-top: 1;
    }
    Button { margin: 0 1; }
    """

    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self.question, id="q"),
            Horizontal(
                Button("Yes", variant="primary", id="yesbtn"),
                Button("No", variant="error", id="nobtn"),
                id="buttons",
            ),
            id="dialog",
        )

    @on(Button.Pressed, "#yesbtn")
    def _yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#nobtn")
    def _no(self) -> None:
        self.dismiss(False)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

class StashApp(App):
    """G.A.M.M.A. STASH — TUI wizard."""

    CSS_PATH = None  # use inline CSS below

    CSS = """
    Screen {
        background: #0a0c0a;
    }
    #banner {
        text-align: center;
        width: 100%;
        height: auto;
        padding: 1 0;
        color: #00ff00;
    }
    #steps {
        height: auto;
        padding: 0 2;
    }
    #content {
        height: auto;
        margin: 1 2;
    }
    #buttons {
        dock: bottom;
        height: auto;
        padding: 1 2;
        align: center middle;
    }
    .title {
        color: #ff8c00;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    .ok { color: #00ff00; }
    .err { color: #ff4444; }
    .warn { color: #ff8c00; }
    .dim { color: #888888; }
    .bold { text-style: bold; }
    Button { margin: 0 1; }
    Input { width: 100%; margin: 1 0; }
    RichLog { height: auto; max-height: 22; margin: 1 0; }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self):
        super().__init__()
        self.state: Dict[str, Any] = {
            "fs_url": "",
            "fs_mode": "",
            "mods_path": "",
            "downloads_dir": "",
            "scan_ok": frozenset(),
            "need_total": 0,
        }

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="banner")
        yield Static(id="steps")
        yield Container(id="content")
        yield Horizontal(id="buttons")
        yield Footer()

    def on_mount(self) -> None:
        self._title("")
        self.query_one("#banner", Static).update(
            f"[bold green]G.A.M.M.A. STASH[/] [dim]v{__version__}[/]\n"
            f"[dim]Batch download G.A.M.M.A. mods[/]"
        )
        self._welcome()

    # ── ui helpers ──────────────────────────────────────────────────

    def _title(self, text: str) -> None:
        self.query_one("#steps", Static).update(
            f"[bold orange1]{text}[/]" if text else ""
        )

    def _clear(self) -> None:
        self.query_one("#content", Container).remove_children()
        self.query_one("#buttons", Horizontal).remove_children()

    async def _confirm(self, question: str) -> bool:
        return await self.push_screen(ConfirmScreen(question), wait_for_dismiss=True)

    def _btn(self, label: str, cb: str, variant: str = "primary") -> None:
        self.query_one("#buttons", Horizontal).mount(
            Button(label, variant=variant, id=cb)
        )

    def _log(self, text: str) -> None:
        self.query_one("#content", Container).mount(RichLog(write=text))

    # ── welcome ─────────────────────────────────────────────────────

    def _welcome(self) -> None:
        self._clear()
        self.query_one("#content", Container).mount(Label(
            "Welcome to the [bold]G.A.M.M.A. STASH[/] setup wizard.\n\n"
            "This will guide you through downloading all\n"
            "your G.A.M.M.A. mods from ModDB and GitHub.\n"
        ))
        self._btn("Start", "start_setup")

    @on(Button.Pressed, "#start_setup")
    def _on_start(self) -> None:
        self._check_deps()

    # ── dependencies ─────────────────────────────────────────────────

    def _check_deps(self) -> None:
        self._clear()
        self._title("Checking System Dependencies")
        c = self.query_one("#content", Container)
        all_ok, missing, _ = check_all_dependencies()
        log = RichLog()
        if all_ok:
            log.write("[green]OK[/] curl is available")
            log.write("[dim]docker (optional, for self-hosting)[/]")
            c.mount(log)
            self._btn("Next", "flare_choice")
        else:
            log.write("[red]MISSING[/] curl")
            c.mount(log)
            c.mount(Label("[red]curl is required.[/]"))
            self._btn("Install curl", "install_curl")
            self._btn("Skip & Exit", "done")

    @on(Button.Pressed, "#install_curl")
    def _install_curl_btn(self) -> None:
        self._clear()
        c = self.query_one("#content", Container)
        c.mount(Label("Installing curl via winget ..."))
        self.install_curl_worker()

    @work(thread=True, exclusive=True)
    def install_curl_worker(self) -> bool:
        return _install_curl()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name == "install_curl_worker" and event.state == WorkerState.SUCCESS:
            self._clear()
            c = self.query_one("#content", Container)
            if event.worker.result:
                c.mount(Label("[green]curl installed.[/]\n[dim]Restart the app to take effect.[/]"))
            else:
                c.mount(Label("[red]Failed to install curl. Install manually.[/]"))
            self._btn("Exit", "done")

    # ── flaresolverr choice ──────────────────────────────────────────

    @on(Button.Pressed, "#flare_choice")
    def _flare_choice(self) -> None:
        self._flare_choice_show()

    def _flare_choice_show(self) -> None:
        self._clear()
        self._title("Flaresolverr Configuration")
        c = self.query_one("#content", Container)
        c.mount(Label(
            "Flaresolverr bypasses Cloudflare on ModDB.\n"
            "How would you like to configure it?"
        ))
        self._btn("Enter IP manually", "flare_manual")
        self._btn("Self-host via Docker", "flare_docker")

    @on(Button.Pressed, "#flare_manual")
    def _flare_manual(self) -> None:
        self._manual_ip_show()

    @on(Button.Pressed, "#flare_docker")
    def _flare_docker(self) -> None:
        self._docker_setup()

    # ── manual IP ────────────────────────────────────────────────────

    def _manual_ip_show(self, error: str = "") -> None:
        self._clear()
        self._title("Enter Flaresolverr Address")
        c = self.query_one("#content", Container)
        c.mount(Label("Enter IP of your Flaresolverr instance.\n"
                       "[dim]Example: http://192.168.1.50:8191/[/]"))
        if error:
            c.mount(Label(f"[red]{error}[/]"))
        inp = Input(placeholder="http://192.168.1.50:8191/", id="fsip")
        c.mount(inp)
        self._btn("Validate", "validate_ip")
        self._btn("Back", "flare_choice", "default")

    @on(Button.Pressed, "#validate_ip")
    def _validate_ip_btn(self) -> None:
        self._validate_ip()

    @work(thread=True)
    def _validate_ip(self) -> None:
        url = self.query_one("#fsip", Input).value.strip()
        if not url.startswith("http"):
            self.call_from_thread(self._manual_ip_show, "URL must start with http:// or https://")
            return
        ok, msg = validate_flaresolverr(url)
        if ok:
            self.state["fs_url"] = url.rstrip("/") + "/v1"
            self.state["fs_mode"] = "manual"
            self.call_from_thread(self._gamma_folder_show)
        else:
            self.call_from_thread(self._manual_ip_show, f"FAIL: {msg}")

    # ── docker self-host ─────────────────────────────────────────────

    def _docker_setup(self) -> None:
        self._clear()
        self._title("Docker — Self-host Flaresolverr")
        c = self.query_one("#content", Container)
        log = RichLog(id="dklog", wrap=True)
        c.mount(log)
        self.state["fs_mode"] = "docker"
        self.docker_worker()

    @work(thread=True, exclusive=True)
    def docker_worker(self) -> None:
        log = self.query_one("#dklog", RichLog)

        def w(s):
            self.call_from_thread(log.write, s)

        docker_path = _find_docker()
        if not docker_path:
            w("[yellow]Docker not found.[/]")
            if _is_windows():
                v = _check_virtualization()
                if not v:
                    # Need async confirm, so we handle via call_from_thread
                    w("[red]No WSL2 or Hyper-V detected.[/]")
                    w("Docker Desktop requires one of these on Windows.")
                    w("See the README for manual setup.")
                    self.call_from_thread(self._show_done, 1)
                    return
                w(f"[green]Virtualization ready ({v})[/]")

            # Install docker
            w("Installing Docker Desktop via winget ...")
            import subprocess
            subprocess.run(
                ["winget", "install", "--id", "Docker.DockerDesktop",
                 "--silent", "--accept-package-agreements"],
                capture_output=False, timeout=600,
            )
            if not _find_docker():
                w("[yellow]Docker installed. Restart the app for PATH changes.[/]")
                self.call_from_thread(self._show_done, 0)
                return
            w("[green]Docker installed.[/]")

        if not _docker_daemon_ok():
            w("[red]Docker daemon not running.[/]")
            w("Start Docker Desktop and wait for it to fully start, then retry.")
            self.call_from_thread(self._show_done, 1)
            return

        w("[green]Docker available[/]")

        if _docker_container_running("flaresolverr"):
            w("[green]Flaresolverr already running.[/]")
        elif _docker_container_exists("flaresolverr"):
            w("Starting existing container ...")
            import subprocess
            subprocess.run(["docker", "start", "flaresolverr"], capture_output=True)
        else:
            w("Pulling flaresolverr/flaresolverr ...")
            import subprocess
            subprocess.run(["docker", "pull", "flaresolverr/flaresolverr"], capture_output=False)
            subprocess.run(
                ["docker", "run", "-d", "--name", "flaresolverr",
                 "-p", "8191:8191", "flaresolverr/flaresolverr"],
                capture_output=True,
            )

        url = "http://localhost:8191/v1"
        w("Waiting for Flaresolverr ...")
        for _ in range(20):
            ok, msg = validate_flaresolverr(url, timeout_sec=3)
            if ok:
                w(f"[green]{msg}[/]")
                break
            import time
            time.sleep(1)

        self.state["fs_url"] = url
        self.call_from_thread(self._gamma_folder_show)

    # ── GAMMA folder ─────────────────────────────────────────────────

    def _gamma_folder_show(self, error: str = "") -> None:
        self._clear()
        self._title("Locate GAMMA Installation")
        c = self.query_one("#content", Container)
        c.mount(Label("Enter the path to your GAMMA folder.\n[dim]Example: D:\\GAMMA[/]"))
        if error:
            c.mount(Label(f"[red]{error}[/]"))
        inp = Input(placeholder=r"D:\GAMMA", id="gpath")
        c.mount(inp)
        self._btn("Validate", "validate_gamma")

    @on(Button.Pressed, "#validate_gamma")
    def _validate_gamma(self) -> None:
        path = self.query_one("#gpath", Input).value.strip().strip('"')
        if not path:
            self._gamma_folder_show("Please enter a path.")
            return
        expanded = os.path.expandvars(os.path.expanduser(path))
        ok, reason = _is_gamma_folder(expanded)
        if not ok:
            self._gamma_folder_show(reason)
            return
        self.state["mods_path"] = _find_mods_txt(expanded)
        self.state["downloads_dir"] = _find_downloads_folder(self.state["mods_path"])
        os.makedirs(self.state["downloads_dir"], exist_ok=True)
        self._scan_modlist()

    # ── modlist scan ─────────────────────────────────────────────────

    def _scan_modlist(self) -> None:
        self._clear()
        self._title("Scanning Modlist")
        c = self.query_one("#content", Container)
        c.mount(Label("Checking existing files against expected MD5s ...\n\n"
                       "[dim]This may take several minutes for large modlists.[/]"))
        self.scan_worker()

    @work(thread=True, exclusive=True)
    def scan_worker(self) -> None:
        stats = scan_modlist(
            self.state["mods_path"],
            self.state["downloads_dir"],
        )
        if stats is None:
            self.call_from_thread(self._show_done, 1)
            return

        from .downloader import LinksFile
        entries = LinksFile(self.state["mods_path"]).read()
        self.state["scan_ok"] = frozenset(
            e["filename"] for e in entries
            if os.path.exists(os.path.join(self.state["downloads_dir"], e["filename"]))
            and e.get("expected_md5")
        )
        self.state["need_total"] = stats["need_download"] + stats["need_redownload"]
        self.call_from_thread(
            self._scan_done,
            stats["already_ok"], stats["need_download"],
            stats["need_redownload"], stats["total"],
        )

    def _scan_done(self, ok: int, need: int, redo: int, total: int) -> None:
        self._clear()
        c = self.query_one("#content", Container)
        c.mount(Label(
            f"Scan complete.\n\n"
            f"[green]{ok} OK[/]  •  [yellow]{need} need download[/]"
            f"{'  •  [red]'+str(redo)+' need re-download[/]' if redo else ''}\n"
            f"[dim]Total: {total} mods[/]"
        ))

        if need == 0 and redo == 0:
            c.mount(Label("\n[green]All mods already downloaded![/]"))
            if self.state["fs_mode"] == "docker":
                self._btn("Clean up Docker", "cleanup_docker")
            self._btn("Exit", "done")
            return

        self._btn(f"Download {need + redo} mods", "start_download")
        self._btn("Cancel", "done", "default")

    # ── download ────────────────────────────────────────────────────

    @on(Button.Pressed, "#start_download")
    def _start_download(self) -> None:
        self._clear()
        self._title("Downloading Mods")
        c = self.query_one("#content", Container)
        log = RichLog(id="dllog", wrap=True, max_lines=12)
        c.mount(log)
        self.download_worker()

    @work(thread=True, exclusive=True)
    def download_worker(self) -> None:
        config = {
            "links_file": self.state["mods_path"],
            "download_dir": self.state["downloads_dir"],
            "download_delay": 2,
            "max_concurrent": 1,
            "flaresolverr": {"url": self.state["fs_url"], "timeout_ms": 60000},
            "destination": {"local_path": self.state["downloads_dir"]},
            "tracking_file": "",
        }

        d = Downloader(config)
        results = d.download_all(self.state["scan_ok"])
        self.call_from_thread(self._download_done, results)

    def _download_done(self, results: dict) -> None:
        self._clear()
        c = self.query_one("#content", Container)
        c.mount(Label(
            f"[bold]Download complete.[/]\n\n"
            f"[green]{results['success']} OK[/]"
            f"{' [red]'+str(results['fail'])+' FAIL[/]' if results['fail'] else ''}"
            f" of {results['total_pending']}"
        ))
        if self.state["fs_mode"] == "docker":
            self._btn("Clean up Docker", "cleanup_docker")
        self._btn("Exit", "done")

    # ── cleanup ─────────────────────────────────────────────────────

    @on(Button.Pressed, "#cleanup_docker")
    def _cleanup_btn(self) -> None:
        self._clear()
        self._title("Cleaning up Docker")
        c = self.query_one("#content", Container)
        c.mount(Label("Stopping and removing Flaresolverr ..."))
        self.cleanup_worker()

    @work(thread=True, exclusive=True)
    def cleanup_worker(self) -> None:
        cleanup_docker()
        self.call_from_thread(self._show_done, 0)

    # ── done ────────────────────────────────────────────────────────

    @on(Button.Pressed, "#done")
    def _on_done_btn(self) -> None:
        self._show_done(0)

    def _show_done(self, code: int) -> None:
        self._clear()
        self._title("")
        c = self.query_one("#content", Container)
        if code == 0:
            c.mount(Label("[green]All done![/]\n\nYou can close this window."))
        else:
            c.mount(Label("[red]Setup stopped.[/]\n\nFix the issue and try again."))
        self._btn("Exit", "quit_app")

    @on(Button.Pressed, "#quit_app")
    def _quit_app(self) -> None:
        self.exit()


def run_tui() -> None:
    app = StashApp()
    app.run()
