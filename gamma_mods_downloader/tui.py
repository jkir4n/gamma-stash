"""
Textual TUI for G.A.M.M.A. STASH — interactive setup + next-gen download manager.
"""

import os
import asyncio
from typing import Any, Dict, List, Optional

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static, ProgressBar, DataTable
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
    discover_gamma_paths, check_disk_space,
)
from .downloader import Downloader


# ── G.A.M.M.A. PDA Theme ─────────────────────────────────────────────

GAMMA_THEME_VARS = {
    "block-cursor-text-style": "none",
    "footer-key-foreground": "#00ff41",
    "input-selection-background": "#00ff41 30%",
    "border-focus": "#00ff41",
    "scrollbar-color": "#00ff41 30%",
    "scrollbar-color-hover": "#00ff41 50%",
    "scrollbar-color-active": "#00ff41 70%",
}


def _make_gamma_theme() -> "Theme":
    from textual.theme import Theme
    return Theme(
        name="gamma",
        primary="#00ff41",
        secondary="#228800",
        accent="#ffb000",
        foreground="#d4edd4",
        background="#060906",
        success="#00ff41",
        warning="#ffb000",
        error="#ff3333",
        surface="#0d140d",
        panel="#131c13",
        dark=True,
        variables=GAMMA_THEME_VARS,
    )


# ---------------------------------------------------------------------------
# Modal confirm dialog
# ---------------------------------------------------------------------------

class ConfirmScreen(ModalScreen[bool]):
    CSS = """
    #dialog {
        background: #0d140d;
        border: thick #ffb000;
        padding: 2 3;
        width: 54;
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
    """G.A.M.M.A. STASH — Next-Gen TUI."""

    CSS = """
    Screen {
        background: #060906;
    }
    Header {
        background: #0d140d;
        color: #00ff41;
    }
    Footer {
        background: #0d140d;
    }
    Footer > .footer--key {
        color: #00ff41;
        background: #131c13;
    }
    #banner {
        text-align: center;
        width: 100%;
        height: auto;
        padding: 1 0 0 0;
        color: #00ff41;
    }
    #steps {
        height: auto;
        padding: 0 2;
        text-align: center;
    }
    #content {
        height: 1fr;
        margin: 1 2;
    }
    #buttons {
        dock: bottom;
        height: auto;
        padding: 1 2;
        align: center middle;
    }
    Button {
        margin: 0 1;
        border: solid #00ff41;
    }
    Button:focus {
        border: solid #ffb000;
    }
    Button:hover {
        border: solid #ffb000;
    }
    Input {
        width: 100%;
        margin: 1 0;
        border: solid #335533;
    }
    Input:focus {
        border: solid #00ff41;
    }
    DataTable {
        height: 1fr;
        margin: 1 0;
        border: solid #1c2b1c;
        background: #060906;
    }
    RichLog {
        height: 8;
        margin: 1 0;
        background: #060906;
        border: solid #1c2b1c;
    }
    ProgressBar {
        margin: 1 0;
    }
    .status-panel {
        background: #0d140d;
        border: solid #1c2b1c;
        padding: 1 2;
        margin: 1 0;
    }
    .telemetry {
        color: #ffb000;
        text-align: center;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("l", "toggle_log", "Toggle Log"),
    ]

    def __init__(self):
        super().__init__()
        self.state: Dict[str, Any] = {
            "fs_url": "",
            "fs_mode": "",
            "mods_path": "",
            "downloads_dir": "",
            "scan_ok": frozenset(),
            "need_total": 0,
            "scan_stats": {},
            "show_log": True,
        }

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="banner")
        yield Static(id="steps")
        yield Container(id="content")
        yield Horizontal(id="buttons")
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(_make_gamma_theme())
        self.theme = "gamma"
        self._title("")
        self.query_one("#banner", Static).update(
            f"[bold #00ff41]G.A.M.M.A. STASH[/] [dim]v{__version__}[/]\n"
            f"[dim]Next-Gen Mod Manager & Batch Downloader[/]"
        )
        self._welcome()

    # ── ui helpers ──────────────────────────────────────────────────

    def _title(self, text: str) -> None:
        self.query_one("#steps", Static).update(
            f"[bold #ffb000]{text}[/]" if text else ""
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

    def action_toggle_log(self) -> None:
        try:
            log_widget = self.query_one("#dllog", RichLog)
            log_widget.display = not log_widget.display
        except Exception:
            pass

    # ── welcome ─────────────────────────────────────────────────────

    def _welcome(self) -> None:
        self._clear()
        c = self.query_one("#content", Container)
        c.mount(Vertical(
            Label(
                "\n[bold #00ff41]Welcome to G.A.M.M.A. STASH[/]\n\n"
                "• [white]Concurrent downloads for GitHub direct links[/]\n"
                "• [white]Sub-second hash caching & HTTP Range resume[/]\n"
                "• [white]Flaresolverr session pooling for fast ModDB mirror resolution[/]\n"
                "• [white]Auto-discovery of G.A.M.M.A. installations & free disk space[/]\n"
            ),
            classes="status-panel"
        ))
        self._btn("Start Wizard", "start_setup")

    @on(Button.Pressed, "#start_setup")
    def _on_start(self) -> None:
        self._check_deps()

    # ── dependencies ─────────────────────────────────────────────────

    def _check_deps(self) -> None:
        self._clear()
        self._title("Checking System Dependencies")
        c = self.query_one("#content", Container)
        all_ok, missing, _ = check_all_dependencies()
        log = RichLog(wrap=True)
        if all_ok:
            log.write("[green]✓[/] curl is available on PATH")
            log.write("[dim]✓ docker (optional, for self-hosting Flaresolverr)[/]")
            c.mount(log)
            self._btn("Next", "flare_choice")
        else:
            log.write("[red]✗ MISSING[/] curl (required)")
            c.mount(log)
            c.mount(Label("[red]curl is required to download mods.[/]"))
            self._btn("Auto-Install curl", "install_curl")
            self._btn("Exit", "done", "default")

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
                c.mount(Label("[green]curl successfully installed.[/]\n[dim]Please restart the app.[/]"))
            else:
                c.mount(Label("[red]Failed to install curl. Please install manually.[/]"))
            self._btn("Exit", "done")

    # ── Flaresolverr choice ──────────────────────────────────────────

    @on(Button.Pressed, "#flare_choice")
    def _flare_choice(self) -> None:
        self._flare_choice_show()

    def _flare_choice_show(self) -> None:
        self._clear()
        self._title("Flaresolverr Cloudflare Bypass")
        c = self.query_one("#content", Container)
        c.mount(Vertical(
            Label(
                "Flaresolverr is used to resolve Cloudflare challenges on ModDB.\n\n"
                "Select configuration mode:"
            ),
            classes="status-panel"
        ))
        self._btn("Docker (Auto-Launch)", "flare_docker")
        self._btn("Remote / Existing IP", "flare_manual")
        self._btn("Back", "start_setup", "default")

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
        c.mount(Label("Enter URL of your Flaresolverr instance:\n"
                       "[dim]Example: http://192.168.1.50:8191/[/]"))
        if error:
            c.mount(Label(f"[red]{error}[/]"))
        inp = Input(placeholder="http://localhost:8191/v1", id="fsip")
        c.mount(inp)
        self._btn("Validate & Continue", "validate_ip")
        self._btn("Back", "flare_choice", "default")

    @on(Button.Pressed, "#validate_ip")
    def _validate_ip_btn(self) -> None:
        url = self.query_one("#fsip", Input).value.strip()
        self._validate_ip(url)

    @work(thread=True)
    def _validate_ip(self, url: str) -> None:
        if not url.startswith("http"):
            self.call_from_thread(self._manual_ip_show, "URL must start with http:// or https://")
            return
        ok, msg = validate_flaresolverr(url)
        if ok:
            self.state["fs_url"] = url.rstrip("/") + ("/v1" if not url.endswith("/v1") else "")
            self.state["fs_mode"] = "manual"
            self.call_from_thread(self._gamma_folder_show)
        else:
            self.call_from_thread(self._manual_ip_show, f"Connection error: {msg}")

    # ── docker self-host ─────────────────────────────────────────────

    def _docker_setup(self) -> None:
        self._clear()
        self._title("Docker — Flaresolverr Container")
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
            w("[yellow]Docker not detected.[/]")
            if _is_windows():
                v = _check_virtualization()
                if not v:
                    w("[red]No WSL2 or Hyper-V detected.[/]")
                    w("Docker requires WSL2 or Hyper-V on Windows.")
                    self.call_from_thread(self._show_done, 1)
                    return
                w(f"[green]Virtualization ready: {v}[/]")

            w("Installing Docker Desktop via winget ...")
            import subprocess
            subprocess.run(
                ["winget", "install", "--id", "Docker.DockerDesktop",
                 "--silent", "--accept-package-agreements"],
                capture_output=True, text=True, timeout=600,
            )
            if not _find_docker():
                w("[yellow]Docker installed. Please restart the app.[/]")
                self.call_from_thread(self._show_done, 0)
                return

        if not _docker_daemon_ok():
            w("[red]Docker daemon not running.[/]")
            w("Please start Docker Desktop and wait for it to initialize, then retry.")
            self.call_from_thread(self._show_done, 1)
            return

        w("[green]Docker daemon ready[/]")

        if _docker_container_running("flaresolverr"):
            w("[green]Flaresolverr container is already running.[/]")
        elif _docker_container_exists("flaresolverr"):
            w("Starting existing Flaresolverr container ...")
            import subprocess
            subprocess.run(["docker", "start", "flaresolverr"], capture_output=True, timeout=30)
        else:
            w("Launching Flaresolverr container ...")
            import subprocess
            subprocess.run(
                ["docker", "run", "-d", "--name", "flaresolverr",
                 "-p", "8191:8191", "flaresolverr/flaresolverr"],
                capture_output=True, timeout=60,
            )

        url = "http://localhost:8191/v1"
        w("Waiting for Flaresolverr endpoint ...")
        for _ in range(25):
            ok, msg = validate_flaresolverr(url, timeout_sec=3)
            if ok:
                w(f"[green]Flaresolverr active: {msg}[/]")
                break
            import time
            time.sleep(1)

        self.state["fs_url"] = url
        self.call_from_thread(self._gamma_folder_show)

    # ── GAMMA folder & auto-discovery ─────────────────────────────────

    def _gamma_folder_show(self, error: str = "") -> None:
        self._clear()
        self._title("Locate G.A.M.M.A. Folder")
        c = self.query_one("#content", Container)

        discovered = discover_gamma_paths()
        if discovered:
            c.mount(Label("[bold #ffb000]Auto-Discovered Installations:[/]\n"))
            for i, d in enumerate(discovered):
                btn_id = f"autopath_{i}"
                has_space, free_gb, _ = check_disk_space(d["path"])
                space_str = f"[green]{free_gb:.1f} GB free[/]" if has_space else f"[red]{free_gb:.1f} GB free (low)[/]"
                c.mount(Button(f"Use {d['path']} ({space_str})", id=btn_id, variant="primary"))
            c.mount(Label("\n[dim]Or enter path manually:[/]\n"))

        if error:
            c.mount(Label(f"[red]{error}[/]"))
        inp = Input(placeholder=r"D:\GAMMA", id="gpath")
        c.mount(inp)
        self._btn("Validate Path", "validate_gamma")
        self._btn("Back", "flare_choice", "default")

    @on(Button.Pressed)
    def _on_path_button(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("autopath_"):
            idx = int(btn_id.split("_")[1])
            discovered = discover_gamma_paths()
            if 0 <= idx < len(discovered):
                selected = discovered[idx]
                self.state["mods_path"] = selected["mods_txt"]
                self.state["downloads_dir"] = _find_downloads_folder(selected["mods_txt"])
                os.makedirs(self.state["downloads_dir"], exist_ok=True)
                self._scan_modlist()

    @on(Button.Pressed, "#validate_gamma")
    def _validate_gamma(self) -> None:
        path = self.query_one("#gpath", Input).value.strip().strip('"')
        if not path:
            self._gamma_folder_show("Please enter a valid path.")
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
        self._title("Scanning Modlist (Fast Hash Cache)")
        c = self.query_one("#content", Container)
        pbar = ProgressBar(total=100, id="scan_bar")
        c.mount(Vertical(
            Label("Checking existing archives against expected MD5 hashes ...\n"),
            pbar,
            classes="status-panel"
        ))
        self.scan_worker()

    @work(thread=True, exclusive=True)
    def scan_worker(self) -> None:
        pbar = self.query_one("#scan_bar", ProgressBar)

        def log_cb(msg: str) -> None:
            pass

        def prog_cb(cur: int, tot: int, fn: str) -> None:
            self.call_from_thread(pbar.update, total=tot, progress=cur)
            self.call_from_thread(self._title, f"Scanning [{cur}/{tot}] {fn[:30]}")

        stats = scan_modlist(
            self.state["mods_path"],
            self.state["downloads_dir"],
            log_cb=log_cb,
            progress_cb=prog_cb,
        )
        if stats is None:
            self.call_from_thread(self._show_done, 1)
            return

        self.state["scan_stats"] = stats
        self.state["scan_ok"] = frozenset(stats.get("ok_filenames", []))
        self.state["need_total"] = stats["need_download"] + stats["need_redownload"]
        self.call_from_thread(
            self._scan_done,
            stats["already_ok"], stats["need_download"],
            stats["need_redownload"], stats["total"],
        )

    def _scan_done(self, ok: int, need: int, redo: int, total: int) -> None:
        self._clear()
        self._title("Scan Summary")
        c = self.query_one("#content", Container)

        has_space, free_gb, _ = check_disk_space(self.state["downloads_dir"])
        space_warn = f"\n[yellow]Drive free space: {free_gb:.1f} GB[/]" if free_gb else ""

        c.mount(Vertical(
            Label(
                f"[bold #00ff41]Verification Scan Complete[/]\n\n"
                f"• [green]{ok} Verified & Ready[/]\n"
                f"• [yellow]{need} Missing / Pending[/]\n"
                f"{'• [red]'+str(redo)+' Corrupted / Need Re-download[/]\n' if redo else ''}"
                f"• [dim]Total Mods: {total}[/]{space_warn}"
            ),
            classes="status-panel"
        ))

        if need == 0 and redo == 0:
            c.mount(Label("\n[green]All mods are completely downloaded and verified![/]"))
            if self.state["fs_mode"] == "docker":
                self._btn("Clean up Docker", "cleanup_docker")
            self._btn("Exit", "done")
            return

        self._btn(f"Download {need + redo} Mods", "start_download")
        self._btn("Cancel", "done", "default")

    # ── download with DataTable & Telemetry ───────────────────────────

    @on(Button.Pressed, "#start_download")
    def _start_download(self) -> None:
        self._clear()
        self._title("Downloading G.A.M.M.A. Mods")
        c = self.query_one("#content", Container)

        # Header gauges
        overall_pbar = ProgressBar(total=self.state["need_total"] or 1, id="pbar_overall", show_eta=True)
        active_pbar = ProgressBar(total=100, id="pbar_active")
        telemetry = Label("Initializing worker threads...", id="telemetry_label", classes="telemetry")

        # Mod Table
        table = DataTable(id="mod_table")
        table.cursor_type = "row"
        table.add_columns("Status", "Source", "Filename", "Transfer Speed")

        log = RichLog(id="dllog", wrap=True, max_lines=50)

        c.mount(Vertical(
            telemetry,
            Label("[dim]Overall Progress:[/]", classes="dim"),
            overall_pbar,
            Label("[dim]Active File:[/]", classes="dim"),
            active_pbar,
            table,
            log,
        ))

        self.download_worker()

    @work(thread=True, exclusive=True)
    def download_worker(self) -> None:
        log = self.query_one("#dllog", RichLog)
        table = self.query_one("#mod_table", DataTable)
        overall_pbar = self.query_one("#pbar_overall", ProgressBar)
        active_pbar = self.query_one("#pbar_active", ProgressBar)
        telemetry = self.query_one("#telemetry_label", Label)

        def dl_log(msg: str) -> None:
            self.call_from_thread(log.write, msg)

        def on_event(event_type: str, data: dict) -> None:
            fn = data.get("filename", "")
            if event_type == "entry_start":
                src = data.get("source", "MODDB")
                self.call_from_thread(
                    table.add_row,
                    "[bold cyan]📥 DL[/]", src, fn, "Starting...",
                    key=fn
                )
                self.call_from_thread(table.scroll_end, animate=False)
                self.call_from_thread(active_pbar.update, progress=0)
            elif event_type == "entry_progress":
                speed_str = data.get("speed_str", "")
                size_str = data.get("size_str", "")
                self.call_from_thread(
                    telemetry.update,
                    f"[bold #ffb000]{fn[:30]}[/]  •  [green]{speed_str}[/]  •  [white]{size_str}[/]"
                )
                try:
                    self.call_from_thread(table.update_cell, fn, "Transfer Speed", speed_str)
                except Exception:
                    pass
            elif event_type == "entry_complete":
                try:
                    self.call_from_thread(table.update_cell, fn, "Status", "[bold green]✓ OK[/]")
                    self.call_from_thread(table.update_cell, fn, "Transfer Speed", "Verified")
                except Exception:
                    pass
            elif event_type == "entry_error":
                try:
                    self.call_from_thread(table.update_cell, fn, "Status", "[bold red]✗ FAIL[/]")
                    self.call_from_thread(table.update_cell, fn, "Transfer Speed", "Failed")
                except Exception:
                    pass
            elif event_type == "overall_progress":
                comp = data.get("completed", 0)
                tot = data.get("total", 1)
                ok_c = data.get("success", 0)
                fail_c = data.get("fail", 0)
                self.call_from_thread(overall_pbar.update, total=tot, progress=comp)
                self.call_from_thread(
                    self._title,
                    f"Downloading [{comp}/{tot}] • OK: {ok_c} • FAIL: {fail_c}"
                )

        config = {
            "links_file": self.state["mods_path"],
            "download_dir": self.state["downloads_dir"],
            "download_delay": 1,
            "max_concurrent": 3,
            "flaresolverr": {"url": self.state["fs_url"], "timeout_ms": 60000},
            "destination": {"local_path": self.state["downloads_dir"]},
        }

        d = Downloader(config, log_callback=dl_log, on_event=on_event)
        results = d.download_all(self.state["scan_ok"])
        self.call_from_thread(self._download_done, results)

    def _download_done(self, results: dict) -> None:
        self._clear()
        self._title("Downloads Finished")
        c = self.query_one("#content", Container)
        c.mount(Vertical(
            Label(
                f"[bold #00ff41]Download Batch Complete[/]\n\n"
                f"• [green]{results['success']} Succeeded[/]\n"
                f"{'• [red]'+str(results['fail'])+' Failed[/]\n' if results['fail'] else ''}"
                f"• [white]Total Processed: {results['total_pending']}[/]"
            ),
            classes="status-panel"
        ))
        if results.get("fail", 0) > 0:
            self._btn("Retry Failed Mods", "start_download", "warning")
        if self.state["fs_mode"] == "docker":
            self._btn("Clean up Docker", "cleanup_docker")
        self._btn("Exit", "done")

    # ── cleanup ─────────────────────────────────────────────────────

    @on(Button.Pressed, "#cleanup_docker")
    def _cleanup_btn(self) -> None:
        self._clear()
        self._title("Cleaning up Docker")
        c = self.query_one("#content", Container)
        c.mount(Label("Stopping and removing Flaresolverr container ..."))
        self.cleanup_worker()

    @work(thread=True, exclusive=True)
    def cleanup_worker(self) -> None:
        cleanup_docker(interactive=False, uninstall_docker=False)
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
            c.mount(Label("[bold green]All done![/]\n\nYou may close this window or press Exit."))
        else:
            c.mount(Label("[red]Setup stopped.[/]\n\nPlease check logs and retry."))
        self._btn("Exit", "quit_app")

    @on(Button.Pressed, "#quit_app")
    def _quit_app(self) -> None:
        self.exit()


def run_tui() -> None:
    app = StashApp()
    app.run()
