"""Desktop interface for the Open Fire Toolkit service."""

from __future__ import annotations

from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import TYPE_CHECKING
import webbrowser

if TYPE_CHECKING:
    from .service import Plan, Toolkit
    from .workflows import TransportPlan, WorkflowPlan


PLATFORM_TOOLS = "https://developer.android.com/tools/releases/platform-tools"
BUILD_TOOLS = "https://developer.android.com/tools/releases/build-tools"
AMAZON_DEVICES = "https://www.amazon.com/mycd"


class Worker:
    """Run one operation off-thread and deliver callbacks from the polling thread."""

    def __init__(self):
        self.busy = False
        self._events = Queue()

    def submit(self, action, on_success, on_error, on_log=None):
        if self.busy:
            return False
        self.busy = True

        def log(line):
            if on_log is not None:
                self._events.put((False, on_log, line))

        def run():
            try:
                result = action(log)
            except Exception as error:
                self._events.put((True, on_error, error))
            else:
                self._events.put((True, on_success, result))

        try:
            Thread(target=run, daemon=True).start()
        except RuntimeError:
            self.busy = False
            raise
        return True

    def drain(self):
        while True:
            try:
                finished, callback, value = self._events.get_nowait()
            except Empty:
                return
            if finished:
                self.busy = False
            callback(value)


class App:
    """Build a Tk interface. The injected toolkit also supports isolated GUI tests."""

    def __init__(self, root, toolkit: Toolkit | None = None, demo: bool = False):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        from .service import OPTIONAL_APPS, ToolConfig, Toolkit

        if demo:
            from .demo import DemoToolkit

            toolkit = DemoToolkit()

        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.dialog = messagebox
        self.files = filedialog
        self.demo = demo
        self.toolkit = toolkit
        self.fixed_toolkit = toolkit is not None
        self.ToolConfig = ToolConfig
        self.Toolkit = Toolkit
        self.optional_apps = OPTIONAL_APPS
        self.device = None
        self.devices = []
        self.apk_paths: list[Path] = []
        self.loaded_apps = []
        self.worker = Worker()
        self.review = None
        self.controls = []

        root.title("Fire Tools" + (" · Demo" if demo else ""))
        root.geometry("920x760")
        root.minsize(680, 660)
        root.protocol("WM_DELETE_WINDOW", self._close)
        self._style()
        self._layout()
        self._sync_controls()
        self.root.after(50, self._poll)

    def _style(self):
        from tkinter.font import nametofont

        style = self.ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self.root.configure(background="#eef3f7")
        style.configure(".", background="#f7f9fc", foreground="#172c41")
        style.configure("TFrame", background="#eef3f7")
        style.configure("TLabel", background="#eef3f7")
        style.configure("Panel.TFrame", background="#f7f9fc")
        style.configure("Panel.TLabel", background="#f7f9fc")
        base_font = nametofont("TkDefaultFont", root=self.root)
        self.title_font = base_font.copy()
        self.title_font.configure(size=20, weight="bold")
        self.heading_font = base_font.copy()
        self.heading_font.configure(size=14, weight="bold")
        self.activity_font = base_font.copy()
        self.activity_font.configure(weight="bold")
        style.configure("Heading.TLabel", background="#f7f9fc", font=self.heading_font)
        style.configure("TButton", padding=(10, 5))
        style.configure("Compact.TButton", padding=(8, 1))
        style.configure("Primary.TButton", background="#205883", foreground="#ffffff")
        style.map(
            "Primary.TButton",
            background=[("disabled", "#dbe4ec"), ("active", "#17456a")],
            foreground=[("disabled", "#53687c")],
        )
        style.configure("TNotebook.Tab", padding=(13, 8))
        style.configure("Treeview", rowheight=25, fieldbackground="#ffffff")

    def _layout(self):
        from .advanced_gui import AdvancedTools
        from .feature_catalog import FEATURES

        tk, ttk = self.tk, self.ttk
        header = tk.Frame(self.root, background="#17304a", padx=22, pady=13)
        header.pack(fill="x")
        tk.Label(
            header, text="Fire Tools", font=self.title_font,
            background="#17304a", foreground="#ffffff", anchor="w",
        ).pack(side="left")
        self.status = tk.StringVar(value="No tablet selected")
        tk.Label(
            header, textvariable=self.status, background="#17304a",
            foreground="#e1edf6", anchor="e", wraplength=300,
        ).pack(side="right")
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(12, 8))
        self._connection_tab()
        self._play_tab()
        self._ads_tab()
        self._apps_tab()
        self.advanced = AdvancedTools(self, FEATURES)

        footer = ttk.Frame(self.root, padding=(16, 0, 16, 12))
        footer.pack(side="bottom", fill="x", before=self.tabs)
        ttk.Label(footer, text="Activity", font=self.activity_font).pack(anchor="w")
        self.log_box = self._text_box(footer, height=3)
        self._append_log(
            "Demo mode uses simulated devices and APK metadata. No device commands run."
            if self.demo else "Configure ADB, connect your Fire tablet, and scan for devices."
        )

    def _panel(self, name, heading, description):
        tab = self.ttk.Frame(self.tabs, padding=(16, 12), style="Panel.TFrame")
        self.tabs.add(tab, text=name)
        self.ttk.Label(tab, text=heading, style="Heading.TLabel").pack(anchor="w")
        self._description(tab, description).pack(fill="x", pady=(4, 10))
        return tab

    def _description(self, parent, text="", variable=None):
        label = self.ttk.Label(
            parent, text=text, textvariable=variable, style="Panel.TLabel",
            justify="left", wraplength=740,
        )
        label.bind("<Configure>", lambda event: label.configure(wraplength=max(1, event.width)))
        return label

    def _button(self, parent, text, command, *, condition=None, primary=False):
        style = "Primary.TButton" if primary else "TButton"
        button = self.ttk.Button(parent, text=text, command=command, style=style)
        self.controls.append((button, condition))
        return button

    def _text_box(self, parent, height):
        frame = self.ttk.Frame(parent, style="Panel.TFrame")
        frame.pack(fill="both", expand=True)
        box = self.tk.Text(
            frame, height=height, wrap="word", padx=8, pady=5, state="disabled",
            background="#ffffff", foreground="#172c41", relief="flat", takefocus=True,
        )
        scrollbar = self.ttk.Scrollbar(frame, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        box.pack(side="left", fill="both", expand=True)
        return box

    def _connection_tab(self):
        tab = self._panel(
            "Connection", "Connect your Fire tablet",
            "In Settings, open Device Options › About Fire Tablet and tap Serial Number seven times. "
            "Under Developer Options, enable USB debugging. Connect by USB and approve the prompt.",
        )
        ttk = self.ttk
        config = ttk.Frame(tab, style="Panel.TFrame")
        config.pack(fill="x")
        config.columnconfigure(1, weight=1)
        self.paths = []
        for row, (label, examples) in enumerate((
            ("ADB", "adb / adb.exe"),
            ("AAPT", "aapt / aapt.exe"),
            ("APK signer", "apksigner.jar"),
            ("Java", "java / java.exe"),
        )):
            value = self.tk.StringVar()
            self.paths.append(value)
            ttk.Label(config, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w")
            entry = ttk.Entry(config, textvariable=value)
            entry.grid(row=row, column=1, sticky="ew", padx=(10, 8), pady=2)
            value.trace_add("write", self._paths_changed)
            self.controls.append((entry, lambda: not self.fixed_toolkit))
            browse = self._button(
                config, "Browse...", lambda var=value, name=examples: self._browse_tool(var, name),
                condition=lambda: not self.fixed_toolkit,
            )
            browse.configure(style="Compact.TButton")
            browse.grid(row=row, column=2, pady=2)
        guides = ttk.Frame(tab, style="Panel.TFrame")
        guides.pack(fill="x", pady=(5, 8))
        self._button(guides, "Google Platform-Tools", lambda: self._open(PLATFORM_TOOLS)).pack(side="left")
        self._button(guides, "Google Build Tools", lambda: self._open(BUILD_TOOLS)).pack(side="left", padx=6)
        if self.fixed_toolkit:
            self._description(guides, "Tool paths are managed by the active toolkit.").pack(side="left", padx=5)
        else:
            self._description(
                tab, "ADB is required. Google Play also needs aapt, lib/apksigner.jar, and Java.",
            ).pack(fill="x", pady=(0, 7))
        self.firmware = self.tk.StringVar(value="Select a scanned tablet to see firmware and Android details.")
        self._description(tab, variable=self.firmware).pack(side="bottom", fill="x")
        choices = ttk.Frame(tab, style="Panel.TFrame")
        choices.pack(side="bottom", fill="x", pady=(7, 6))
        self._button(
            choices, "Scan devices", self._scan, primary=True,
        ).pack(side="left")
        self._button(
            choices, "Use selected tablet", self._select_device,
            condition=lambda: bool(self.device_table.selection()),
        ).pack(side="left", padx=6)
        self._button(
            choices, "Review reboot...", self._plan_reboot, condition=self._connected,
        ).pack(side="right")
        self.device_table = self._table(
            tab, (("serial", "Serial", 180), ("state", "ADB state", 110), ("model", "Model", 180)), 3,
            self._sync_controls,
        )

    def _play_tab(self):
        tab = self._panel(
            "Google Play", "Install Google Play",
            "For a fresh Android 11 ARM64 setup, choose standalone APKs for Google Account Manager, "
            "Google Services Framework, Google Play services and Play Store. Calendar Sync and "
            "Contacts Sync are optional. To add sync to an existing setup, choose just the adapters.",
        )
        self.apk_table = self._table(
            tab, (("file", "Local APK files", 440),), 7, self._sync_controls,
        )
        actions = self.ttk.Frame(tab, style="Panel.TFrame")
        actions.pack(fill="x", pady=8)
        self._button(actions, "Choose APKs...", self._choose_apks).pack(side="left")
        if self.demo:
            self._button(actions, "Use demo sample", self._demo_apks).pack(side="left", padx=(6, 0))
        self._button(
            actions, "Clear list", self._clear_apks, condition=lambda: bool(self.apk_paths),
        ).pack(side="left", padx=6)
        self._button(
            actions, "Verify and review...", self._plan_play,
            condition=lambda: self._connected() and bool(self.apk_paths), primary=True,
        ).pack(side="right")
        guides = self.ttk.Frame(tab, style="Panel.TFrame")
        guides.pack(fill="x", pady=(0, 8))
        self._button(
            guides, "Find Google APK sources", lambda: self.advanced.show_feature("source-catalog"),
        ).pack(side="left")
        if not self.demo:
            self._button(
                guides, "Check scan records", self._check_apk_files,
                condition=lambda: bool(self.apk_paths),
            ).pack(side="left", padx=6)
        self._button(
            guides, "Battery exemption...", lambda: self.advanced.show_feature("battery-exemption"),
        ).pack(side="left", padx=6)
        self._description(
            tab, "Use APKs from a source you trust. If one install fails, earlier packages "
                 "may remain installed. Reboot is a separate action on the Connection tab.",
        ).pack(fill="x")

    def _ads_tab(self):
        tab = self._panel(
            "Lock-screen ads", "Manage lock-screen ads",
            "Amazon offers paid removal of Special Offers when available for your device. "
            "Open your Amazon device settings, select your Fire tablet and look for Special Offers.",
        )
        self._button(
            tab, "Open Amazon device settings", lambda: self._open(AMAZON_DEVICES),
        ).pack(anchor="w", pady=(0, 20))
        self.ttk.Label(tab, text="Experimental setting", style="Heading.TLabel").pack(anchor="w")
        self._description(
            tab, "This changes one Android setting and saves its earlier value for restore. "
                 "Fire OS may ignore or reset the setting, and ads may continue to appear.",
        ).pack(fill="x", pady=(4, 10))
        actions = self.ttk.Frame(tab, style="Panel.TFrame")
        actions.pack(fill="x")
        self._button(
            actions, "Review setting change...", lambda: self._plan_ads(restore=False),
            condition=self._connected, primary=True,
        ).pack(side="left")
        self._button(
            actions, "Review restore...", lambda: self._plan_ads(restore=True),
            condition=self._connected,
        ).pack(side="left", padx=6)

        self.ttk.Label(
            tab, text="Package and helper controls", style="Heading.TLabel",
        ).pack(anchor="w", pady=(16, 0))
        self._description(
            tab, "Fire OS may block Special Offers package changes. The optional helper "
                 "requires installation, a settings permission, and a visible service on the tablet.",
        ).pack(fill="x", pady=(4, 8))
        paired = self.ttk.Frame(tab, style="Panel.TFrame")
        paired.pack(fill="x", pady=(0, 6))
        self._button(
            paired, "Suppress with setting and package...",
            lambda: self._plan_ads(restore=False, paired=True), condition=self._connected,
        ).pack(side="left")
        self._button(
            paired, "Undo setting and package...",
            lambda: self._plan_ads(restore=True, paired=True), condition=self._connected,
        ).pack(side="left", padx=6)
        packages = self.ttk.Frame(tab, style="Panel.TFrame")
        packages.pack(fill="x", pady=(0, 6))
        self._button(
            packages, "Disable Special Offers package...",
            lambda: self.advanced.show_feature("ads-package-disable"),
        ).pack(side="left")
        self._button(
            packages, "Restore Special Offers package...",
            lambda: self.advanced.show_feature("ads-package-restore"),
        ).pack(side="left", padx=6)
        helper = self.ttk.Frame(tab, style="Panel.TFrame")
        helper.pack(fill="x")
        self._button(
            helper, "Set up ad helper...", lambda: self.advanced.show_feature("helper-start"),
        ).pack(side="left")
        self._button(
            helper, "Stop ad helper...", lambda: self.advanced.show_feature("helper-stop"),
        ).pack(side="left", padx=6)
        self._button(
            helper, "Restore helper setting...", lambda: self.advanced.show_feature("helper-restore"),
        ).pack(side="left")

    def _apps_tab(self):
        from .feature_catalog import BY_KEY

        tab = self._panel(
            "Apps", "Optional Amazon apps",
            "Compare debloat presets before connecting. Select a tablet to review a preset "
            "or read app states and choose an individual app.",
        )
        self.app_table = self._table(
            tab, (("label", "Application", 155), ("package", "Package", 310), ("state", "State", 95)),
            7, self._sync_controls,
        )
        actions = self.ttk.Frame(tab, style="Panel.TFrame")
        actions.pack(fill="x", pady=8)
        self._button(
            actions, "Read app states", self._read_apps, condition=self._connected,
        ).pack(side="left")
        self._button(
            actions, "Review disable...", lambda: self._plan_app(enable=False),
            condition=lambda: self._selected_app_state() == "Enabled",
        ).pack(side="left", padx=6)
        self._button(
            actions, "Review enable...", lambda: self._plan_app(enable=True),
            condition=lambda: self._selected_app_state() == "Disabled",
        ).pack(side="left")
        packages = self.ttk.Frame(tab, style="Panel.TFrame")
        packages.pack(fill="x")
        self._button(
            packages, "Debloat Amazon apps...", lambda: self.advanced.show_feature("debloat"),
        ).pack(side="left")
        self._button(
            packages, "Compare debloat presets...",
            lambda: self._run_tool(BY_KEY["debloat-presets"], dict),
        ).pack(side="left", padx=6)
        self._button(
            packages, "Package inventory...",
            lambda: self.advanced.show_feature("packages-inventory"),
        ).pack(side="left")
        recovery = self.ttk.Frame(tab, style="Panel.TFrame")
        recovery.pack(fill="x", pady=(6, 0))
        self._button(
            recovery, "Restore Everything...", lambda: self.advanced.show_feature("debloat-restore"),
        ).pack(side="left")
        self._button(
            recovery, "Undo saved package changes...", lambda: self.advanced.show_feature("packages-undo"),
        ).pack(side="left", padx=6)

    def _table(self, parent, columns, height, on_selection, *, selectmode="browse"):
        container = self.ttk.Frame(parent, style="Panel.TFrame")
        container.pack(fill="both", expand=True)
        table = self.ttk.Treeview(
            container, columns=[key for key, _, _ in columns], show="headings",
            height=height, selectmode=selectmode,
        )
        for key, label, width in columns:
            table.heading(key, text=label, anchor="w")
            table.column(key, width=width, minwidth=70)
        scrollbar = self.ttk.Scrollbar(container, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        table.pack(side="left", fill="both", expand=True)
        table.bind("<<TreeviewSelect>>", lambda event: on_selection())
        return table

    def _connected(self):
        return self.device is not None

    def _sync_controls(self):
        blocked = self.worker.busy or self.review is not None
        for widget, condition in self.controls:
            enabled = not blocked and (condition is None or condition())
            widget.state(["!disabled"] if enabled else ["disabled"])
        for table in (self.device_table, self.apk_table, self.app_table):
            table.state(["disabled"] if blocked else ["!disabled"])
        self.advanced.sync_controls()
        prefix = "Demo · " if self.demo else ""
        if self.device is not None:
            detail = f"{self.device.model or 'Fire tablet'} · {self.device.serial}"
        else:
            detail = "No tablet selected"
        if self.worker.busy:
            detail = f"Working · {detail}"
        self.status.set(prefix + detail)

    def _append_log(self, message):
        self._write_text(self.log_box, str(message) + "\n", append=True)
        self.log_box.see("end")

    @staticmethod
    def _write_text(box, text, append=False):
        box.configure(state="normal")
        if not append:
            box.delete("1.0", "end")
        box.insert("end", text)
        box.configure(state="disabled")

    def _poll(self):
        try:
            self.worker.drain()
        except Exception as error:
            self._show_error("Update the interface", error)
        finally:
            self._sync_controls()
            self.root.after(50, self._poll)

    def _start(self, title, action, complete):
        if self.worker.busy or self.review is not None:
            self.root.bell()
            return
        self._append_log(title + "...")
        try:
            self.worker.submit(
                action, complete, lambda error: self._show_error(title, error), self._append_log,
            )
        except RuntimeError as error:
            self._show_error(title, error)
        self._sync_controls()

    def _show_error(self, title, error):
        message = str(error).strip() or type(error).__name__
        self._append_log(f"{title} failed. {message}")
        self.dialog.showerror(f"{title} failed", message, parent=self.root)

    def _close(self):
        if self.worker.busy:
            self.dialog.showinfo(
                "Operation in progress", "Wait for the current operation to finish before closing.",
                parent=self.root,
            )
        else:
            self.root.destroy()

    def _open(self, url):
        if self.demo:
            self._append_log(f"Demo link: {url}")
            return
        try:
            if not webbrowser.open_new_tab(url):
                raise RuntimeError(f"Open this address in your web browser: {url}")
        except (OSError, webbrowser.Error, RuntimeError) as error:
            self._show_error("Open web page", error)

    def _browse_tool(self, variable, name):
        file = self.files.askopenfilename(parent=self.root, title=f"Choose {name}")
        if file:
            variable.set(file)

    def _clear_table(self, table):
        table.delete(*table.get_children())

    def _forget_apps(self):
        self.loaded_apps = []
        self._clear_table(self.app_table)

    def _forget_device(self):
        self.device = None
        self.firmware.set("Select a scanned tablet to see firmware and Android details.")
        self._forget_apps()

    def _paths_changed(self, *_):
        self.toolkit = None
        self.devices = []
        self._clear_table(self.device_table)
        self._forget_device()
        self._sync_controls()

    def _configured_tools(self, title):
        config = self.ToolConfig(*(value.get().strip() for value in self.paths))
        if config.adb_path:
            return config
        self._show_error(title, ValueError(
            "Choose adb from Google Platform-Tools in the ADB field on the Connection tab.",
        ))
        return None

    def _scan(self):
        if self.worker.busy:
            return
        toolkit = self.toolkit
        config = None
        if toolkit is None:
            config = self._configured_tools("Scan devices")
            if config is None:
                return

        self.devices = []
        self._clear_table(self.device_table)
        self._forget_device()

        def scan(log):
            active = toolkit if toolkit is not None else self.Toolkit(config)
            return active, active.devices()

        def complete(result):
            self.toolkit, self.devices = result
            for index, device in enumerate(self.devices):
                self.device_table.insert(
                    "", "end", iid=str(index), values=(device.serial, device.state, device.model),
                )
            if self.devices:
                self._append_log("Select your tablet in the list, then choose Use selected tablet.")
            else:
                self._append_log("No devices found. Check the USB data cable and USB debugging, then scan again.")

        self._start("Scan devices", scan, complete)

    def _select_device(self):
        selected = self.device_table.selection()
        if not selected or self.worker.busy:
            return
        candidate = self.devices[int(selected[0])]
        self._forget_device()
        if candidate.state != "device":
            self._show_error("Use selected tablet", ValueError(
                f"{candidate.serial} is {candidate.state}. Unlock the tablet, approve USB "
                "debugging, confirm the USB data cable is connected, and scan again.",
            ))
            self._sync_controls()
            return
        toolkit = self.toolkit

        def complete(device):
            self.device = device
            abis = ", ".join(device.abis) or "not reported"
            self.firmware.set(
                f"{device.manufacturer} {device.model} · Fire OS {device.fire_os or 'unknown'} · "
                f"Android {device.android_release or 'unknown'} · SDK {device.sdk} · User {device.user_id}\n"
                f"ABIs: {abis}"
            )
            self._append_log(f"Selected tablet {device.serial}.")

        self._start("Read tablet details", lambda log: toolkit.device_info(candidate.serial), complete)

    def _choose_apks(self):
        selected = self.files.askopenfilenames(
            parent=self.root, title="Select local Google Play APKs", filetypes=(("APK files", "*.apk"),),
        )
        self._add_apks(selected)

    def _demo_apks(self):
        self._clear_apks()
        self._add_apks(("demo-account-manager.apk", "demo-framework.apk", "demo-play-services.apk", "demo-play-store.apk"))

    def _add_apks(self, filenames):
        for filename in filenames:
            path = Path(filename)
            if path not in self.apk_paths:
                self.apk_paths.append(path)
                self.apk_table.insert("", "end", values=(str(path),))
        self._sync_controls()

    def _clear_apks(self):
        self.apk_paths.clear()
        self._clear_table(self.apk_table)
        self._sync_controls()

    def _plan(self, title, make_plan):
        if self.device is None:
            return
        toolkit, serial = self.toolkit, self.device.serial
        self._start(title, lambda log: make_plan(toolkit, serial),
                    lambda plan: self._review_plan(toolkit, plan))

    def _run_tool(self, feature, collect_values):
        """Snapshot Tk field values and the selected tablet before dispatching."""
        from .feature_catalog import run_feature

        if feature.requires_device and self.device is None:
            self._show_error(feature.label, ValueError("Select a tablet on the Connection tab first."))
            return
        if self.worker.busy or self.review is not None:
            self.root.bell()
            return

        values = dict(collect_values())
        toolkit = self.toolkit
        serial = self.device.serial if feature.requires_device else ""
        if feature.read_only:
            self._start(
                feature.label, lambda _log: run_feature(toolkit, serial, feature, values),
                lambda result: self._show_tool_output(feature.label, serial, result),
            )
            return

        config = None
        if toolkit is None:
            config = self._configured_tools(feature.label)
            if config is None:
                return

        def plan(_log):
            active = toolkit if toolkit is not None else self.Toolkit(config)
            return active, run_feature(active, serial, feature, values)

        self._start(feature.label, plan, lambda result: self._review_plan(*result))

    def _tool_window(self, title, serial):
        window = self.tk.Toplevel(self.root)
        window.title(title)
        window.geometry("655x425")
        window.minsize(455, 285)
        window.transient(self.root)
        window.bind("<Escape>", lambda _event: window.destroy())
        panel = self.ttk.Frame(window, padding=16, style="Panel.TFrame")
        panel.pack(fill="both", expand=True)
        self.ttk.Label(panel, text=title, style="Heading.TLabel").pack(anchor="w")
        if serial:
            self._description(panel, f"Target tablet · {serial}").pack(fill="x", pady=(3, 9))
        return window, panel

    def _show_tool_output(self, title, serial, result):
        window, panel = self._tool_window(title, serial)
        box = self._text_box(panel, height=12)
        if isinstance(result, list):
            result = "\n".join(
                f"{row['package']}  ·  {row['state']}  ·  {row['label']}" for row in result
            )
        self._write_text(box, result or "No results.")
        close = self.ttk.Button(panel, text="Close", command=window.destroy)
        close.pack(anchor="e", pady=(10, 0))
        close.focus_set()
        target = f" for {serial}" if serial else ""
        self._append_log(f"{title} read completed{target}.")

    def _check_apk_files(self):
        from .apk_checks import check_apk_files
        paths = tuple(self.apk_paths)
        title = "APK scan records"
        self._start(title, lambda _log: check_apk_files(paths)[0],
                    lambda report: self._show_tool_output(title, "", report))

    def _plan_play(self):
        paths = tuple(self.apk_paths)
        self._plan("Verify local APKs", lambda toolkit, serial: toolkit.plan_google_play(serial, paths))

    def _plan_ads(self, restore, paired=False):
        self._plan("Review lock-screen ad changes",
                   lambda toolkit, serial: toolkit.plan_ads(serial, restore=restore, paired=paired))

    def _plan_reboot(self):
        self._plan("Prepare reboot", lambda toolkit, serial: toolkit.plan_reboot(serial))

    def _read_apps(self):
        self._forget_apps()
        toolkit, serial = self.toolkit, self.device.serial

        def read(log):
            packages = set(toolkit.packages(serial))
            disabled = set(toolkit.packages(serial, disabled_only=True))
            return packages, disabled

        def complete(result):
            packages, disabled = result
            for package, label in self.optional_apps.items():
                if package in disabled:
                    state = "Disabled"
                elif package in packages:
                    state = "Enabled"
                else:
                    state = "Unavailable"
                index = str(len(self.loaded_apps))
                self.loaded_apps.append((package, state))
                self.app_table.insert("", "end", iid=index, values=(label, package, state))
            self._append_log(f"Read optional app states for {serial}.")

        self._start("Read optional app states", read, complete)

    def _selected_app_state(self):
        selected = self.app_table.selection()
        if selected:
            return self.loaded_apps[int(selected[0])][1]
        return None

    def _plan_app(self, enable):
        selected = self.app_table.selection()
        if selected:
            package, _ = self.loaded_apps[int(selected[0])]
            self._plan("Check optional app",
                       lambda toolkit, serial: toolkit.plan_package(serial, package, enable=enable))

    def _review_plan(self, toolkit, plan: Plan | WorkflowPlan | TransportPlan):
        window = self.tk.Toplevel(self.root)
        self.review = window
        self._sync_controls()
        window.title("Review plan")
        window.geometry("690x480")
        window.minsize(465, 340)
        window.transient(self.root)
        panel = self.ttk.Frame(window, padding=16, style="Panel.TFrame")
        panel.pack(fill="both", expand=True)
        self.ttk.Label(panel, text=plan.title, style="Heading.TLabel").pack(anchor="w")
        mode = "Demo tablet" if self.demo else "Target tablet"
        target = f"{mode} · {plan.device.model} · {plan.serial}" if plan.serial else plan.device.model
        self._description(panel, target).pack(fill="x", pady=(3, 9))
        box = self._text_box(panel, height=12)
        self._write_text(box, self._plan_text(plan))
        actions = self.ttk.Frame(panel, style="Panel.TFrame")
        actions.pack(fill="x", pady=(10, 0))

        def dismiss():
            self.review = None
            window.destroy()
            self._sync_controls()

        def confirm():
            dismiss()
            self._execute(toolkit, plan)

        window.protocol("WM_DELETE_WINDOW", dismiss)
        window.bind("<Escape>", lambda event: dismiss())
        confirm_label = "Confirm simulation" if self.demo else "Confirm and run"
        self.ttk.Button(
            actions, text=confirm_label, command=confirm, style="Primary.TButton",
        ).pack(side="right")
        cancel = self.ttk.Button(actions, text="Cancel", command=dismiss)
        cancel.pack(side="right", padx=8)
        window.wait_visibility()
        window.grab_set()
        cancel.focus_set()

    @staticmethod
    def _plan_text(plan):
        sections = ["\n".join(plan.details)]
        if plan.warnings:
            sections.append("Before you run this plan\n" + "\n".join(plan.warnings))
        apk_metadata = getattr(plan, "apks", ())
        if apk_metadata:
            apks = []
            for apk in apk_metadata:
                abis = ", ".join(apk.abis) or "no native ABI requirement"
                signers = "\n".join(apk.signer_sha256)
                apks.append(
                    f"{apk.package} · version {apk.version_name} ({apk.version_code})\n"
                    f"{apk.path}\nMinimum SDK {apk.min_sdk} · {abis}\n"
                    f"APK SHA-256: {apk.sha256}\nSigner SHA-256:\n{signers}"
                )
            sections.append("APK metadata in install order\n\n" + "\n\n".join(apks))
        return "\n\n".join(sections)

    def _execute(self, toolkit, plan):
        if (
            plan.action in ("reboot", "transport")
            or (plan.action == "device_workflow" and plan.operation in ("reboot", "shutdown", "user-switch"))
            or (plan.action == "extra_workflow" and plan.operation in ("wireless-enable", "wireless-usb"))
        ):
            self._forget_device()
            self.devices = []
            self._clear_table(self.device_table)
        else:
            self._forget_apps()

        def execute(log):
            emitted = []

            def report(line):
                emitted.append(line)
                log(line)

            results = toolkit.execute(plan, confirmed=True, log=report)
            for result in results:
                if result not in emitted:
                    log(result)
            return results

        def complete(results):
            if not results:
                self._append_log("The operation returned no step results.")
            self._append_log(
                "Simulation finished. No tablet was changed."
                if self.demo else "Operation finished. See the step results above."
            )

        self._start(plan.title, execute, complete)


def main(demo=False):
    """Launch the desktop interface when Tk and a display are available."""
    try:
        import tkinter as tk
    except ImportError as error:
        raise SystemExit("Install Python's tkinter package to open the desktop interface.") from error

    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise SystemExit(f"The desktop interface needs a graphical display. {error}") from error
    App(root, demo=demo)
    root.mainloop()
