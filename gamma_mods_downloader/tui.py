"""
Textual TUI for G.A.M.M.A. STASH — interactive setup + next-gen download manager.
"""

import os
import sys
import time
from typing import Any, Dict, List, Optional, Set

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen, ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static, ProgressBar, DataTable, SelectionList
from textual.widgets.selection_list import Selection
from textual.worker import Worker, WorkerState

from . import __version__
from .setup import (
    check_all_dependencies, _install_curl, _install_docker,
    validate_flaresolverr,
    _find_docker, _docker_daemon_ok, _docker_container_exists,
    _docker_container_running, _docker_run_flaresolverr,
    _is_gamma_folder, _find_mods_txt, _find_downloads_folder,
    scan_modlist, cleanup_docker, _check_virtualization, _is_windows,
    discover_gamma_paths, check_disk_space,
    get_windows_downloads_dir, play_pda_cue, play_pda_error_cue,
    copy_to_clipboard, fetch_latest_mods_txt,
)
from .downloader import Downloader, open_in_browser, watch_browser_download, LinksFile


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
# Base Screen with common layout
# ---------------------------------------------------------------------------

class BaseStashScreen(Screen):
    """Base screen providing standard G.A.M.M.A. header and styling."""

    def compose_header(self, title: str = "") -> ComposeResult:
        yield Header()
        yield Static(
            f"[bold #00ff41]G.A.M.M.A. STASH[/] [dim]v{__version__}[/]\n"
            f"[dim]Next-Gen Mod Manager & Batch Downloader[/]",
            id="banner",
        )
        if title:
            yield Static(f"[bold #ffb000]{title}[/]", id="steps")


# ---------------------------------------------------------------------------
# Mod Action Modal (Click/Enter on DataTable Row)
# ---------------------------------------------------------------------------

class ModActionModal(ModalScreen[None]):
    """Modal dialog for individual mod actions (open in browser, retry, copy link)."""

    def __init__(self, mod_info: Dict[str, Any]) -> None:
        super().__init__()
        self.mod_info = mod_info

    def compose(self) -> ComposeResult:
        fn = self.mod_info.get("filename", "")
        src = self.mod_info.get("source", "MODDB")
        url = self.mod_info.get("url", "")
        page = self.mod_info.get("moddb_page", "") or url
        md5 = self.mod_info.get("expected_md5", "")

        yield Vertical(
            Label(f"[bold #ffb000]{fn}[/]\n"),
            Label(f"Source: [cyan]{src}[/]"),
            Label(f"URL: [dim]{page[:50]}...[/]"),
            Label(f"MD5: [dim]{md5[:16]}...[/]\n"),
            Horizontal(
                Button("Open in Browser", variant="primary", id="act_browser"),
                Button("Copy Link", variant="default", id="act_copy"),
                Button("Close", variant="error", id="act_close"),
                id="action_buttons",
            ),
            id="action_dialog",
        )

    @on(Button.Pressed, "#act_browser")
    def on_browser(self) -> None:
        url = self.mod_info.get("moddb_page", "") or self.mod_info.get("url", "")
        open_in_browser(url)
        self.notify("Opened link in browser! Monitoring Downloads folder...")
        self.dismiss(None)

    @on(Button.Pressed, "#act_copy")
    def on_copy(self) -> None:
        url = self.mod_info.get("moddb_page", "") or self.mod_info.get("url", "")
        copy_to_clipboard(url)
        self.notify("Link copied to clipboard!")
        self.dismiss(None)

    @on(Button.Pressed, "#act_close")
    def on_close(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

class WelcomeScreen(BaseStashScreen):
    def compose(self) -> ComposeResult:
        yield from self.compose_header("Welcome")
        yield Container(
            Vertical(
                Label(
                    "\n[bold #00ff41]Welcome to G.A.M.M.A. STASH[/]\n\n"
                    "• [white]Concurrent downloads & Multi-segment acceleration for large files[/]\n"
                    "• [white]Sub-second hash caching & HTTP Range resume[/]\n"
                    "• [white]Zero-Docker Browser-Assisted mode or Flaresolverr session pooling[/]\n"
                    "• [white]Auto-discovery of G.A.M.M.A. installations & selective category downloads[/]\n"
                ),
                classes="status-panel",
            ),
            id="content",
        )
        yield Horizontal(
            Button("Start Wizard", variant="primary", id="start_setup"),
            Button("Exit", variant="error", id="quit_btn"),
            id="buttons",
        )
        yield Footer()

    @on(Button.Pressed, "#start_setup")
    def on_start(self) -> None:
        self.app.push_screen(DepsScreen())

    @on(Button.Pressed, "#quit_btn")
    def on_quit(self) -> None:
        self.app.exit()


class DepsScreen(BaseStashScreen):
    def compose(self) -> ComposeResult:
        yield from self.compose_header("Checking System Dependencies")
        all_ok, missing, _ = check_all_dependencies()
        log = RichLog(wrap=True, id="deps_log")

        content_widgets = []
        if all_ok:
            log.write("[green]✓[/] curl is available on PATH")
            log.write("[dim]✓ docker (optional, for self-hosting Flaresolverr)[/]")
            content_widgets.append(log)
            buttons = [
                Button("Next", variant="primary", id="next_btn"),
                Button("Back", variant="default", id="back_btn"),
            ]
        else:
            log.write("[red]✗ MISSING[/] curl (required)")
            content_widgets.extend([
                log,
                Label("[red]curl is required to download mods.[/]"),
            ])
            buttons = [
                Button("Auto-Install curl", variant="primary", id="install_curl_btn"),
                Button("Exit", variant="error", id="quit_btn"),
            ]

        yield Container(*content_widgets, id="content")
        yield Horizontal(*buttons, id="buttons")
        yield Footer()

    @on(Button.Pressed, "#next_btn")
    def on_next(self) -> None:
        self.app.push_screen(FlareChoiceScreen())

    @on(Button.Pressed, "#back_btn")
    def on_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#install_curl_btn")
    def on_install_curl(self) -> None:
        self.install_curl_worker()

    @work(thread=True, exclusive=True)
    def install_curl_worker(self) -> None:
        log = self.query_one("#deps_log", RichLog)
        self.app.call_from_thread(log.write, "Installing curl via winget ...")
        ok = _install_curl()
        if ok:
            self.app.call_from_thread(log.write, "[green]curl installed successfully! Please restart the app.[/]")
        else:
            self.app.call_from_thread(log.write, "[red]Failed to install curl. Please install manually.[/]")

    @on(Button.Pressed, "#quit_btn")
    def on_quit(self) -> None:
        self.app.exit()


class FlareChoiceScreen(BaseStashScreen):
    def compose(self) -> ComposeResult:
        yield from self.compose_header("Download Strategy")
        yield Container(
            Vertical(
                Label(
                    "Choose how to bypass Cloudflare challenges on ModDB:\n\n"
                    "• [green]Browser-Assisted[/]: Zero Docker required. Downloads directly via browser watcher.\n"
                    "• [cyan]Docker Auto-Launch[/]: Runs local Flaresolverr in background container.\n"
                    "• [yellow]Remote IP[/]: Connects to existing Flaresolverr instance on your network."
                ),
                classes="status-panel",
            ),
            id="content",
        )
        yield Horizontal(
            Button("Browser-Assisted (No Docker)", variant="warning", id="flare_browser_btn"),
            Button("Docker (Auto-Launch)", variant="primary", id="flare_docker_btn"),
            Button("Remote / Existing IP", variant="default", id="flare_manual_btn"),
            Button("Back", variant="default", id="back_btn"),
            id="buttons",
        )
        yield Footer()

    @on(Button.Pressed, "#flare_browser_btn")
    def on_browser_choice(self) -> None:
        self.app.push_screen(BrowserAssistedScreen())

    @on(Button.Pressed, "#flare_docker_btn")
    def on_docker(self) -> None:
        self.app.push_screen(DockerScreen())

    @on(Button.Pressed, "#flare_manual_btn")
    def on_manual(self) -> None:
        self.app.push_screen(ManualIPScreen())

    @on(Button.Pressed, "#back_btn")
    def on_back(self) -> None:
        self.app.pop_screen()


class BrowserAssistedScreen(BaseStashScreen):
    def compose(self) -> ComposeResult:
        yield from self.compose_header("Browser-Assisted Mode (Zero Docker)")
        default_dl = get_windows_downloads_dir()
        yield Container(
            Vertical(
                Label(
                    "[bold #00ff41]Zero-Docker Cloudflare Bypass Active[/]\n\n"
                    "• GitHub mods will download directly at maximum speed.\n"
                    "• ModDB links will open in your default web browser.\n"
                    "• STASH monitors your Downloads folder and auto-verifies and moves each mod.\n\n"
                    f"[dim]Browser Downloads Folder:[/]\n"
                ),
                Input(value=default_dl, id="browser_dl_path"),
                classes="status-panel",
            ),
            id="content",
        )
        yield Horizontal(
            Button("Continue", variant="primary", id="continue_browser_btn"),
            Button("Back", variant="default", id="back_btn"),
            id="buttons",
        )
        yield Footer()

    @on(Button.Pressed, "#continue_browser_btn")
    def on_continue(self) -> None:
        dl_path = self.query_one("#browser_dl_path", Input).value.strip()
        self.app.state["fs_mode"] = "browser"
        self.app.state["browser_downloads_dir"] = dl_path or get_windows_downloads_dir()
        self.app.push_screen(PathSelectScreen())

    @on(Button.Pressed, "#back_btn")
    def on_back(self) -> None:
        self.app.pop_screen()


class ManualIPScreen(BaseStashScreen):
    def compose(self) -> ComposeResult:
        yield from self.compose_header("Enter Flaresolverr Address")
        yield Container(
            Label("Enter URL of your Flaresolverr instance:\n[dim]Example: http://192.168.1.50:8191/[/]"),
            Input(placeholder="http://localhost:8191/v1", id="fsip"),
            Label("", id="error_msg"),
            id="content",
        )
        yield Horizontal(
            Button("Validate & Continue", variant="primary", id="validate_ip_btn"),
            Button("Back", variant="default", id="back_btn"),
            id="buttons",
        )
        yield Footer()

    @on(Button.Pressed, "#validate_ip_btn")
    def on_validate(self) -> None:
        url = self.query_one("#fsip", Input).value.strip()
        if not url:
            url = "http://localhost:8191/v1"
        self.validate_worker(url)

    @work(thread=True)
    def validate_worker(self, url: str) -> None:
        err_label = self.query_one("#error_msg", Label)
        if not url.startswith("http"):
            self.app.call_from_thread(err_label.update, "[red]URL must start with http:// or https://[/]")
            return

        self.app.call_from_thread(err_label.update, "[yellow]Connecting to Flaresolverr ...[/]")
        ok, msg = validate_flaresolverr(url)
        if ok:
            fs_clean = url.rstrip("/") + ("/v1" if not url.endswith("/v1") else "")
            self.app.state["fs_url"] = fs_clean
            self.app.state["fs_mode"] = "manual"
            self.app.call_from_thread(self.app.push_screen, PathSelectScreen())
        else:
            self.app.call_from_thread(err_label.update, f"[red]Connection error: {msg}[/]")

    @on(Button.Pressed, "#back_btn")
    def on_back(self) -> None:
        self.app.pop_screen()


class DockerScreen(BaseStashScreen):
    def compose(self) -> ComposeResult:
        yield from self.compose_header("Docker — Flaresolverr Container")
        yield Container(
            RichLog(id="dklog", wrap=True),
            id="content",
        )
        yield Horizontal(
            Button("Cancel", variant="error", id="cancel_btn"),
            id="buttons",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.app.state["fs_mode"] = "docker"
        self.docker_worker()

    @work(thread=True, exclusive=True)
    def docker_worker(self) -> None:
        log = self.query_one("#dklog", RichLog)

        def w(s):
            self.app.call_from_thread(log.write, s)

        docker_path = _find_docker()
        if not docker_path:
            w("[yellow]Docker not detected.[/]")
            if _is_windows():
                v = _check_virtualization()
                if not v:
                    w("[red]No WSL2 or Hyper-V detected.[/]")
                    w("Docker requires WSL2 or Hyper-V on Windows.")
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
                return

        if not _docker_daemon_ok():
            w("[red]Docker daemon not running.[/]")
            w("Please start Docker Desktop and wait for it to initialize, then retry.")
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
            time.sleep(1)

        self.app.state["fs_url"] = url
        self.app.call_from_thread(self.app.push_screen, PathSelectScreen())

    @on(Button.Pressed, "#cancel_btn")
    def on_cancel(self) -> None:
        self.app.pop_screen()


class PathSelectScreen(BaseStashScreen):
    def compose(self) -> ComposeResult:
        yield from self.compose_header("Locate G.A.M.M.A. Folder")

        widgets = []
        try:
            discovered = discover_gamma_paths()
        except Exception:
            discovered = []

        if discovered:
            widgets.append(Label("[bold #ffb000]Auto-Discovered Installation(s):[/]\n"))
            for i, d in enumerate(discovered):
                btn_id = f"autopath_{i}"
                has_space, free_gb, _ = check_disk_space(d["path"])
                space_str = f"({free_gb:.1f} GB free)"
                widgets.append(Button(f"Use {d['path']} {space_str}", id=btn_id, variant="primary"))
            widgets.append(Label("\n[dim]Or enter folder manually:[/]\n"))

        widgets.extend([
            Input(placeholder=r"D:\GAMMA", id="gpath"),
            Label("", id="path_err"),
        ])

        yield Container(*widgets, id="content")
        yield Horizontal(
            Button("Validate Path", variant="primary", id="validate_path_btn"),
            Button("Fetch mods.txt from GitHub", variant="default", id="fetch_manifest_btn"),
            Button("Back", variant="default", id="back_btn"),
            id="buttons",
        )
        yield Footer()

    @on(Button.Pressed)
    def on_button_click(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("autopath_"):
            idx = int(btn_id.split("_")[1])
            discovered = discover_gamma_paths()
            if 0 <= idx < len(discovered):
                selected = discovered[idx]
                self.app.state["mods_path"] = selected["mods_txt"]
                self.app.state["downloads_dir"] = _find_downloads_folder(selected["mods_txt"])
                os.makedirs(self.app.state["downloads_dir"], exist_ok=True)
                self.app.push_screen(CategorySelectScreen())

    @on(Button.Pressed, "#validate_path_btn")
    def on_validate(self) -> None:
        path = self.query_one("#gpath", Input).value.strip().strip('"')
        err = self.query_one("#path_err", Label)
        if not path:
            err.update("[red]Please enter a path.[/]")
            return
        expanded = os.path.expandvars(os.path.expanduser(path))
        ok, reason = _is_gamma_folder(expanded)
        if not ok:
            err.update(f"[red]{reason}[/]")
            return
        self.app.state["mods_path"] = _find_mods_txt(expanded)
        self.app.state["downloads_dir"] = _find_downloads_folder(self.app.state["mods_path"])
        os.makedirs(self.app.state["downloads_dir"], exist_ok=True)
        self.app.push_screen(CategorySelectScreen())

    @on(Button.Pressed, "#fetch_manifest_btn")
    def on_fetch_manifest(self) -> None:
        path = self.query_one("#gpath", Input).value.strip().strip('"')
        err = self.query_one("#path_err", Label)
        if not path:
            err.update("[red]Enter destination folder first.[/]")
            return
        expanded = os.path.expandvars(os.path.expanduser(path))
        fetched = fetch_latest_mods_txt(expanded)
        if fetched:
            self.notify("Successfully downloaded official mods.txt from GitHub!")
            self.app.state["mods_path"] = fetched
            self.app.state["downloads_dir"] = _find_downloads_folder(fetched)
            os.makedirs(self.app.state["downloads_dir"], exist_ok=True)
            self.app.push_screen(CategorySelectScreen())
        else:
            err.update("[red]Failed to fetch mods.txt from GitHub.[/]")

    @on(Button.Pressed, "#back_btn")
    def on_back(self) -> None:
        self.app.pop_screen()


class CategorySelectScreen(BaseStashScreen):
    def compose(self) -> ComposeResult:
        yield from self.compose_header("Select Mod Categories")
        links = LinksFile(self.app.state["mods_path"])
        cats, entries_by_cat = links.read_with_categories()

        items = []
        for i, c in enumerate(cats):
            cnt = len(entries_by_cat[i])
            items.append(Selection(f"{c} ({cnt} mods)", c, True))

        yield Container(
            Label("[bold #00ff41]Select Categories to Process:[/]\n[dim]Toggle checkboxes with Space/Click to download specific categories, or proceed with All.[/]\n"),
            SelectionList[str](*items, id="cat_list"),
            id="content",
        )
        yield Horizontal(
            Button("Select All", id="sel_all_btn"),
            Button("Deselect All", id="desel_all_btn"),
            Button("Start Download", variant="primary", id="start_btn"),
            Button("Back", variant="default", id="back_btn"),
            id="buttons",
        )
        yield Footer()

    @on(Button.Pressed, "#sel_all_btn")
    def on_select_all(self) -> None:
        self.query_one("#cat_list", SelectionList).select_all()

    @on(Button.Pressed, "#desel_all_btn")
    def on_deselect_all(self) -> None:
        self.query_one("#cat_list", SelectionList).deselect_all()

    @on(Button.Pressed, "#start_btn")
    def on_start(self) -> None:
        sel = self.query_one("#cat_list", SelectionList).selected
        if not sel:
            self.notify("Please select at least one category to proceed.", severity="warning")
            return
        links = LinksFile(self.app.state["mods_path"])
        cats, _ = links.read_with_categories()
        if len(sel) == len(cats):
            self.app.state["selected_categories"] = None
        else:
            self.app.state["selected_categories"] = set(sel)
        self.app.push_screen(ScanScreen())

    @on(Button.Pressed, "#back_btn")
    def on_back(self) -> None:
        self.app.pop_screen()


class ScanScreen(BaseStashScreen):
    def compose(self) -> ComposeResult:
        yield from self.compose_header("Scanning Modlist (Fast Hash Cache)")
        yield Container(
            Vertical(
                Label("Checking existing archives against expected MD5 hashes ...\n", id="scan_status"),
                ProgressBar(total=100, id="scan_bar"),
                classes="status-panel",
            ),
            id="content",
        )
        yield Horizontal(
            Button("Cancel", variant="error", id="cancel_btn"),
            id="buttons",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.scan_worker()

    @work(thread=True, exclusive=True)
    def scan_worker(self) -> None:
        pbar = self.query_one("#scan_bar", ProgressBar)
        status_lbl = self.query_one("#scan_status", Label)

        def prog_cb(cur: int, tot: int, fn: str) -> None:
            self.app.call_from_thread(pbar.update, total=tot, progress=cur)
            self.app.call_from_thread(status_lbl.update, f"Scanning [{cur}/{tot}] {fn[:35]}")

        stats = scan_modlist(
            self.app.state["mods_path"],
            self.app.state["downloads_dir"],
            log_cb=lambda m: None,
            progress_cb=prog_cb,
        )
        if stats is None:
            self.app.call_from_thread(self.app.push_screen, SummaryScreen(results={"success": 0, "fail": 1, "total_pending": 0}))
            return

        self.app.state["scan_stats"] = stats
        self.app.state["scan_ok"] = frozenset(stats.get("ok_filenames", []))
        self.app.state["need_total"] = stats["need_download"] + stats["need_redownload"]

        self.app.call_from_thread(self.app.push_screen, ScanSummaryScreen(stats))

    @on(Button.Pressed, "#cancel_btn")
    def on_cancel(self) -> None:
        self.app.pop_screen()


class ScanSummaryScreen(BaseStashScreen):
    def __init__(self, stats: Dict[str, Any]) -> None:
        super().__init__()
        self.stats = stats

    def compose(self) -> ComposeResult:
        yield from self.compose_header("Scan Summary")
        ok = self.stats["already_ok"]
        need = self.stats["need_download"]
        redo = self.stats["need_redownload"]
        total = self.stats["total"]

        has_space, free_gb, _ = check_disk_space(self.app.state["downloads_dir"])
        space_warn = f"\n[yellow]Drive free space: {free_gb:.1f} GB[/]" if free_gb else ""

        yield Container(
            Vertical(
                Label(
                    f"[bold #00ff41]Verification Scan Complete[/]\n\n"
                    f"• [green]{ok} Verified & Ready[/]\n"
                    f"• [yellow]{need} Missing / Pending[/]\n"
                    f"{'• [red]'+str(redo)+' Corrupted / Need Re-download[/]\n' if redo else ''}"
                    f"• [dim]Total Mods: {total}[/]{space_warn}"
                ),
                classes="status-panel",
            ),
            id="content",
        )

        buttons = []
        if need == 0 and redo == 0:
            buttons.append(Button("Done", variant="primary", id="done_btn"))
        else:
            buttons.extend([
                Button(f"Download {need + redo} Mods", variant="primary", id="start_dl_btn"),
                Button("Back", variant="default", id="back_btn"),
            ])

        yield Horizontal(*buttons, id="buttons")
        yield Footer()

    @on(Button.Pressed, "#start_dl_btn")
    def on_start_dl(self) -> None:
        self.app.push_screen(DownloadScreen())

    @on(Button.Pressed, "#done_btn")
    def on_done(self) -> None:
        self.app.push_screen(SummaryScreen({"success": self.stats["total"], "fail": 0, "total_pending": 0}))

    @on(Button.Pressed, "#back_btn")
    def on_back(self) -> None:
        self.app.pop_screen()


class DownloadScreen(BaseStashScreen):
    BINDINGS = [
        ("slash", "focus_search", "Search Filter"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.entries_info: Dict[str, Dict[str, Any]] = {}
        self.start_time: float = time.time()
        self.total_bytes_transferred: int = 0
        self.peak_speed: float = 0.0

    def compose(self) -> ComposeResult:
        yield from self.compose_header("Downloading G.A.M.M.A. Mods")
        overall_pbar = ProgressBar(total=self.app.state["need_total"] or 1, id="pbar_overall", show_eta=True)
        active_pbar = ProgressBar(total=100, id="pbar_active")
        telemetry = Label("Initializing worker threads...", id="telemetry_label", classes="telemetry")

        search_bar = Input(placeholder="Search mods by name or author (press /)...", id="table_search")

        filter_chips = Horizontal(
            Button("All", variant="primary", id="filter_all"),
            Button("Active", variant="default", id="filter_active"),
            Button("Failed", variant="error", id="filter_failed"),
            Button("Completed", variant="default", id="filter_completed"),
            id="filter_chips",
        )

        table = DataTable(id="mod_table")
        table.cursor_type = "row"
        table.add_columns("Status", "Source", "Filename", "Transfer Speed")

        log = RichLog(id="dllog", wrap=True, max_lines=40)

        yield Container(
            Vertical(
                telemetry,
                Label("[dim]Overall Progress:[/]", classes="dim"),
                overall_pbar,
                Label("[dim]Active File:[/]", classes="dim"),
                active_pbar,
                search_bar,
                filter_chips,
                table,
                log,
            ),
            id="content",
        )
        yield Horizontal(
            Button("Hide Logs [L]", variant="default", id="toggle_log_btn"),
            Button("Exit", variant="error", id="quit_btn"),
            id="buttons",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.start_time = time.time()
        self.download_worker()

    def action_focus_search(self) -> None:
        try:
            self.query_one("#table_search", Input).focus()
        except Exception:
            pass

    @on(Input.Changed, "#table_search")
    def on_search_changed(self, event: Input.Changed) -> None:
        query = event.value.strip().lower()
        table = self.query_one("#mod_table", DataTable)
        for row_key in table.rows:
            if query in str(row_key.value).lower():
                try:
                    table.move_cursor(row=table.get_row_index(row_key))
                    break
                except Exception:
                    pass

    @on(DataTable.RowSelected, "#mod_table")
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        fn = str(event.row_key.value) if event.row_key else ""
        info = self.entries_info.get(fn, {"filename": fn})
        self.app.push_screen(ModActionModal(info))

    @work(thread=True, exclusive=True)
    def download_worker(self) -> None:
        log = self.query_one("#dllog", RichLog)
        table = self.query_one("#mod_table", DataTable)
        overall_pbar = self.query_one("#pbar_overall", ProgressBar)
        active_pbar = self.query_one("#pbar_active", ProgressBar)
        telemetry = self.query_one("#telemetry_label", Label)

        def dl_log(msg: str) -> None:
            self.app.call_from_thread(log.write, msg)

        def on_event(event_type: str, data: dict) -> None:
            fn = data.get("filename", "")
            if fn and fn not in self.entries_info:
                self.entries_info[fn] = data

            if event_type == "entry_start":
                src = data.get("source", "MODDB")
                self.app.call_from_thread(
                    table.add_row,
                    "[bold cyan]📥 DL[/]", src, fn, "Starting...",
                    key=fn
                )
                self.app.call_from_thread(table.scroll_end, animate=False)
                self.app.call_from_thread(active_pbar.update, progress=0)
            elif event_type == "entry_browser_waiting":
                try:
                    self.app.call_from_thread(table.update_cell, fn, "Status", "[bold yellow]🌐 BROWSER[/]")
                    self.app.call_from_thread(table.update_cell, fn, "Transfer Speed", "Waiting ~/Downloads")
                except Exception:
                    pass
            elif event_type == "entry_progress":
                speed_str = data.get("speed_str", "")
                size_str = data.get("size_str", "")
                speed_bps = data.get("speed", 0)
                if speed_bps > self.peak_speed:
                    self.peak_speed = speed_bps

                elapsed = time.time() - self.start_time
                self.app.call_from_thread(
                    telemetry.update,
                    f"[bold #ffb000]{fn[:28]}[/] • [green]{speed_str}[/] • [white]{size_str}[/] • [dim]Peak: {self.peak_speed/(1024*1024):.1f} MB/s[/]"
                )
                try:
                    self.app.call_from_thread(table.update_cell, fn, "Transfer Speed", speed_str)
                except Exception:
                    pass
            elif event_type == "entry_complete":
                try:
                    self.app.call_from_thread(table.update_cell, fn, "Status", "[bold green]✓ OK[/]")
                    self.app.call_from_thread(table.update_cell, fn, "Transfer Speed", "Verified")
                except Exception:
                    pass
            elif event_type == "entry_error":
                try:
                    self.app.call_from_thread(table.update_cell, fn, "Status", "[bold red]✗ FAIL[/]")
                    self.app.call_from_thread(table.update_cell, fn, "Transfer Speed", "Failed (Click for options)")
                except Exception:
                    pass
            elif event_type == "overall_progress":
                comp = data.get("completed", 0)
                tot = data.get("total", 1)
                self.app.call_from_thread(overall_pbar.update, total=tot, progress=comp)

        config = {
            "links_file": self.app.state["mods_path"],
            "download_dir": self.app.state["downloads_dir"],
            "download_delay": 1,
            "max_concurrent": 3,
            "flaresolverr": {"url": self.app.state["fs_url"], "timeout_ms": 60000},
            "destination": {"local_path": self.app.state["downloads_dir"]},
            "fs_mode": self.app.state.get("fs_mode", "manual"),
            "browser_downloads_dir": self.app.state.get("browser_downloads_dir", ""),
            "selected_categories": self.app.state.get("selected_categories", None),
        }

        d = Downloader(config, log_callback=dl_log, on_event=on_event)
        results = d.download_all(self.app.state["scan_ok"])
        play_pda_cue()
        self.app.call_from_thread(self.app.push_screen, SummaryScreen(results))

    @on(Button.Pressed, "#toggle_log_btn")
    def on_toggle_log(self) -> None:
        log = self.query_one("#dllog", RichLog)
        log.display = not log.display

    @on(Button.Pressed, "#quit_btn")
    def on_quit(self) -> None:
        self.app.exit()


class SummaryScreen(BaseStashScreen):
    def __init__(self, results: Dict[str, Any]) -> None:
        super().__init__()
        self.results = results

    def compose(self) -> ComposeResult:
        yield from self.compose_header("Downloads Finished")
        success = self.results.get("success", 0)
        fail = self.results.get("fail", 0)
        total = self.results.get("total_pending", 0)

        yield Container(
            Vertical(
                Label(
                    f"[bold #00ff41]Download Batch Summary[/]\n\n"
                    f"• [green]{success} Succeeded[/]\n"
                    f"{'• [red]'+str(fail)+' Failed[/]\n' if fail else ''}"
                    f"• [white]Total Processed: {total}[/]"
                ),
                classes="status-panel",
            ),
            id="content",
        )

        buttons = []
        if fail > 0:
            buttons.append(Button("Retry Failed Mods", variant="warning", id="retry_btn"))
            buttons.append(Button("Open Failure Report", variant="default", id="report_btn"))
        if self.app.state.get("fs_mode") == "docker":
            buttons.append(Button("Clean up Docker", variant="primary", id="cleanup_btn"))
        buttons.append(Button("Exit", variant="error", id="exit_btn"))

        yield Horizontal(*buttons, id="buttons")
        yield Footer()

    def on_mount(self) -> None:
        if getattr(self.app, "sound_enabled", True):
            if self.results.get("fail", 0) > 0:
                play_pda_error_cue()
            else:
                play_pda_cue()

    @on(Button.Pressed, "#report_btn")
    def on_open_report(self) -> None:
        report = self.results.get("failed_report")
        if not report:
            dl_dir = self.app.state.get("downloads_dir", "")
            report = os.path.join(dl_dir, "failed_mods.html")
        if report and os.path.exists(report):
            open_in_browser(report)
        else:
            self.notify("No failure report found.", severity="warning")

    @on(Button.Pressed, "#retry_btn")
    def on_retry(self) -> None:
        self.app.push_screen(ScanScreen())

    @on(Button.Pressed, "#cleanup_btn")
    def on_cleanup(self) -> None:
        self.cleanup_worker()

    @work(thread=True, exclusive=True)
    def cleanup_worker(self) -> None:
        cleanup_docker(interactive=False, uninstall_docker=False)
        self.app.exit()

    @on(Button.Pressed, "#exit_btn")
    def on_exit(self) -> None:
        self.app.exit()


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class StashApp(App):
    """G.A.M.M.A. STASH — Next-Gen Screen-Based TUI."""

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
    #filter_chips {
        height: auto;
        margin: 1 0;
        align: center middle;
    }
    #filter_chips Button {
        margin: 0 1;
        min-width: 10;
        height: 1;
    }
    #action_dialog {
        background: #0d140d;
        border: thick #00ff41;
        padding: 2 3;
        width: 72;
        height: auto;
        align: center middle;
    }
    #action_buttons {
        align: center middle;
        margin-top: 1;
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
    SelectionList {
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
        ("m", "toggle_sound", "Toggle Sound"),
    ]

    def __init__(self):
        super().__init__()
        self.sound_enabled: bool = True
        self.state: Dict[str, Any] = {
            "fs_url": "",
            "fs_mode": "",
            "browser_downloads_dir": "",
            "mods_path": "",
            "downloads_dir": "",
            "scan_ok": frozenset(),
            "need_total": 0,
            "scan_stats": {},
            "selected_categories": None,
        }

    def action_toggle_sound(self) -> None:
        self.sound_enabled = not getattr(self, "sound_enabled", True)
        status = "ENABLED 🔔" if self.sound_enabled else "MUTED 🔕"
        self.notify(f"PDA Audio {status}", timeout=2.0)

    def on_mount(self) -> None:
        self.register_theme(_make_gamma_theme())
        self.theme = "gamma"
        self.push_screen(WelcomeScreen())


def run_tui() -> None:
    app = StashApp()
    app.run()
