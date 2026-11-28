"""Searchable Tk forms for the package and device tool catalog."""

from __future__ import annotations

import json

from .apk import FDROID_APK_URL, FDROID_KEYS_URL
from .feature_catalog import package_values
from .package_catalog import DEBLOAT_TITLES


DEBLOAT_HELP = {
    "standard": (
        "Includes Kindle, Prime Video and Amazon Music. Appstore, Silk and Camera are outside this preset."
    ),
    "complete": (
        "Adds Appstore, Silk, Camera and other everyday apps to Standard. Fire Tools skips protected Device Setup."
    ),
    "custom": (
        "Choose a Toolbox .debloat file or a plain package list. Automatic follows the file’s list type. "
        "Fire Tools skips protected packages, including Device Setup."
    ),
    "standard-v0.2": (
        "The Fire Tools v0.2 Standard list includes Email, Calendar and Contacts. It excludes Appstore, Silk and Camera."
    ),
    "complete-v0.2": (
        "The Fire Tools v0.2 Complete list adds Appstore, messaging and metrics services to the older Standard list. "
        "It excludes Silk and Camera."
    ),
}


class AdvancedTools:
    ALL_CATEGORIES = "All categories"
    FILE_FIELDS = {
        "file": "askopenfilename",
        "save": "asksaveasfilename",
        "directory": "askdirectory",
        "files": "askopenfilenames",
    }

    def __init__(self, app, features):
        self.app = app
        self.features = {feature.key: feature for feature in features}
        self.feature = None
        self.field_sources = {}
        self.form_controls = []
        self.package_button = None
        self.package_picker = None
        tk, ttk = app.tk, app.ttk
        self.tab = app._panel(
            "Tools", "Tablet tools", "Search by tool name or choose a category.",
        )

        filters = ttk.Frame(self.tab, style="Panel.TFrame")
        filters.pack(fill="x", pady=(0, 10))
        filters.columnconfigure(1, weight=1)
        self.search = tk.StringVar()
        self.category = tk.StringVar(value=self.ALL_CATEGORIES)
        categories = sorted({feature.category for feature in self.features.values()})
        ttk.Label(filters, text="Search tools", style="Panel.TLabel").grid(row=0, column=0)
        search_box = ttk.Entry(filters, textvariable=self.search)
        search_box.grid(row=0, column=1, sticky="ew", padx=(6, 12))
        ttk.Label(filters, text="Category", style="Panel.TLabel").grid(row=0, column=2)
        category_box = ttk.Combobox(
            filters, textvariable=self.category, state="readonly", width=19,
            values=(self.ALL_CATEGORIES, *categories),
        )
        category_box.grid(row=0, column=3, sticky="ew", padx=(6, 0))

        body = ttk.Frame(self.tab, style="Panel.TFrame")
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        browser = ttk.Frame(body, style="Panel.TFrame")
        browser.grid(row=0, column=0, sticky="ns", padx=(0, 14))
        self.tool_list = app._table(browser, (("tool", "Tool", 218),), 8, self._selection_changed)
        self.browser_controls = (search_box, category_box, self.tool_list)

        details = ttk.Frame(body, style="Panel.TFrame")
        details.grid(row=0, column=1, sticky="nsew")
        self.heading = tk.StringVar()
        heading = app._description(details, variable=self.heading)
        heading.configure(style="Heading.TLabel")
        heading.pack(fill="x", pady=(0, 7))
        form_frame = ttk.Frame(details, style="Panel.TFrame")
        form_frame.pack(fill="both", expand=True)
        self.form_canvas = tk.Canvas(
            form_frame, background="#f7f9fc", highlightthickness=0, width=1, height=1,
        )
        scroll = ttk.Scrollbar(form_frame, orient="vertical", command=self.form_canvas.yview)
        self.form_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.form_canvas.pack(side="left", fill="both", expand=True)
        self.form = ttk.Frame(self.form_canvas, style="Panel.TFrame", padding=(1, 0, 8, 0))
        form_id = self.form_canvas.create_window(0, 0, window=self.form, anchor="nw")
        self.form_canvas.bind(
            "<Configure>", lambda event: self.form_canvas.itemconfigure(form_id, width=event.width),
        )
        self.form.bind(
            "<Configure>", lambda _event: self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all")),
        )
        self._bind_wheel(self.form_canvas)
        self._bind_wheel(self.form)

        action_row = ttk.Frame(details, style="Panel.TFrame")
        action_row.pack(fill="x", pady=(8, 0))
        self.action = ttk.Button(action_row, style="Primary.TButton", command=self._submit)
        self.action.pack(side="right")
        self.search.trace_add("write", self._refresh_list)
        category_box.bind("<<ComboboxSelected>>", self._refresh_list)
        self._refresh_list()

    def show_feature(self, key):
        """Open the form selected by an Apps or Lock-screen ads shortcut."""
        if self._navigation_blocked():
            return
        feature = self.features[key]
        self.app.tabs.select(self.tab)
        self.category.set(feature.category)
        if self.search.get():
            self.search.set("")
        else:
            self._refresh_list()
        self.tool_list.selection_set(key)
        self.tool_list.focus(key)
        self.tool_list.see(key)
        self.tool_list.focus_set()
        self._selection_changed()

    def _refresh_list(self, *_):
        if self._navigation_blocked():
            return
        query = self.search.get().casefold().split()
        category = self.category.get()
        keys = []
        self.tool_list.delete(*self.tool_list.get_children())
        for feature in self.features.values():
            if category not in (self.ALL_CATEGORIES, feature.category):
                continue
            text = f"{feature.key} {feature.label} {feature.category} {feature.description}".casefold()
            if all(term in text for term in query):
                self.tool_list.insert("", "end", iid=feature.key, values=(feature.label,))
                keys.append(feature.key)
        if keys:
            selected = self.feature.key if self.feature and self.feature.key in keys else keys[0]
            self.tool_list.selection_set(selected)
            self.tool_list.focus(selected)
            self.tool_list.see(selected)
        self._selection_changed()

    def _selection_changed(self):
        selection = self.tool_list.selection()
        if self._navigation_blocked():
            # Tk's Treeview class bindings can select rows even when disabled.
            current = (self.feature.key,) if self.feature else ()
            if selection != current:
                self.tool_list.selection_set(current)
                if current:
                    self.tool_list.focus(current[0])
            return
        feature = self.features[selection[0]] if selection else None
        if feature == self.feature:
            return
        self.feature = feature
        for widget in self.form.winfo_children():
            widget.destroy()
        self.field_sources.clear()
        self.form_controls.clear()
        self.package_button = None
        self.form_canvas.yview_moveto(0)
        if feature is None:
            self.heading.set("No tools match")
            self.action.configure(text="Review...")
        else:
            self.heading.set(feature.label)
            self.action.configure(text="Read" if feature.read_only else "Review...")
            if feature.description:
                description = self.app._description(self.form, feature.description)
                description.pack(fill="x", pady=(0, 8))
                self._bind_wheel(description)
            if feature.key in {"sideload", "sideload-folder", "install-fdroid"}:
                self._add_fdroid_links(feature.key)
            if feature.key == "debloat":
                self._add_debloat_fields(feature.fields)
            else:
                for field in feature.fields:
                    self._add_field(field)
        self.sync_controls()

    def _add_fdroid_links(self, feature_key):
        row = self.app.ttk.Frame(self.form, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 8))
        download = self.app.ttk.Button(
            row, text="Download official F-Droid APK", command=lambda: self.app._open(FDROID_APK_URL),
        )
        if feature_key == "install-fdroid":
            guide = self.app.ttk.Button(row, text="F-Droid signing keys", command=lambda: self.app._open(FDROID_KEYS_URL))
        else:
            guide = self.app.ttk.Button(row, text="Install F-Droid...", command=lambda: self.show_feature("install-fdroid"))
        for button in (download, guide):
            button.pack(anchor="w", pady=(0, 3))
            self._field_control(button, row)

    def _add_debloat_fields(self, fields):
        fields = {field.key: field for field in fields}
        profile_row, profile_box = self._add_field(fields["profile"], DEBLOAT_TITLES)
        summary = self.app._description(profile_row)
        summary.pack(fill="x", pady=(4, 0))
        self._bind_wheel(summary)
        file_row, _ = self._add_field(fields["list_file"])
        mode_row, _ = self._add_field(fields["mode"], {
            "auto": "Automatic (follow list type)", "disable": "Disable apps",
            "enable": "Enable apps", "uninstall": "Remove for owner (keep data)",
        })

        read_profile = self.field_sources["profile"]
        read_file = self.field_sources["list_file"]
        self.field_sources["list_file"] = lambda: read_file() if read_profile() == "custom" else ""

        def select_profile(_event=None):
            profile = read_profile()
            summary.configure(text=DEBLOAT_HELP[profile])
            if profile == "custom":
                file_row.pack(fill="x", pady=(0, 8), before=mode_row)
            else:
                file_row.pack_forget()

        profile_box.bind("<<ComboboxSelected>>", select_profile)
        select_profile()

    def _add_field(self, field, choice_labels=None):
        tk, ttk = self.app.tk, self.app.ttk
        row = ttk.Frame(self.form, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 8))
        label = self.app._description(row, field.label)
        label.pack(fill="x", pady=(0, 3))
        self._bind_wheel(row)
        self._bind_wheel(label)
        inputs = ttk.Frame(row, style="Panel.TFrame")
        inputs.pack(fill="x")

        if field.kind == "multiline":
            box = tk.Text(
                inputs, width=20, height=4, wrap="word", padx=5, pady=4,
                background="#ffffff", foreground="#172c41", takefocus=True,
            )
            box.insert("1.0", field.default)
            scroll = ttk.Scrollbar(inputs, orient="vertical", command=box.yview)
            box.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y")
            box.pack(side="left", fill="x", expand=True)
            box.bind("<Tab>", self._text_focus_next)
            box.bind("<Shift-Tab>", self._text_focus_previous)
            box.bind("<ISO_Left_Tab>", self._text_focus_previous)
            self.field_sources[field.key] = lambda: box.get("1.0", "end-1c")
            self._field_control(box, row)
            if field.key == "packages":
                self.package_button = ttk.Button(
                    row, text="Choose packages...", command=lambda: self._choose_packages(box),
                )
                self.package_button.pack(anchor="w", pady=(4, 0))
                self._field_control(self.package_button, row)
            return row, box
        else:
            value = tk.StringVar(value=field.default)
            choices = field.choices
            if choice_labels:
                keys_by_title = {title: key for key, title in choice_labels.items()}
                choices = tuple(keys_by_title)
                value.set(choice_labels[field.default])
                self.field_sources[field.key] = lambda: keys_by_title[value.get()]
            else:
                self.field_sources[field.key] = value.get
            if choices:
                entry = ttk.Combobox(inputs, textvariable=value, values=choices, state="readonly")
            else:
                entry = ttk.Entry(inputs, textvariable=value)
            entry.pack(side="left", fill="x", expand=True)
            self._field_control(entry, row)
            if field.kind in self.FILE_FIELDS:
                browse = ttk.Button(inputs, text="Browse...", command=lambda: self._browse(field, value))
                browse.pack(side="right", padx=(6, 0))
                self._field_control(browse, row)
            return row, entry

    def _field_control(self, widget, row):
        self.form_controls.append(widget)
        widget.bind("<FocusIn>", lambda _event: self._reveal(row))

    def _reveal(self, row):
        height = self.form_canvas.winfo_height()
        top = self.form_canvas.canvasy(0)
        first = row.winfo_y()
        last = first + row.winfo_height()
        if first < top:
            self.form_canvas.yview_moveto(first / self.form.winfo_height())
        elif last > top + height:
            target = min(first, last - height)
            self.form_canvas.yview_moveto(target / self.form.winfo_height())

    def _bind_wheel(self, widget):
        widget.bind("<MouseWheel>", lambda event: self._scroll(-1 if event.delta > 0 else 1))
        widget.bind("<Button-4>", lambda _event: self._scroll(-1))
        widget.bind("<Button-5>", lambda _event: self._scroll(1))

    def _scroll(self, direction):
        self.form_canvas.yview_scroll(direction, "units")
        return "break"

    @staticmethod
    def _text_focus_next(event):
        event.widget.tk_focusNext().focus_set()
        return "break"

    @staticmethod
    def _text_focus_previous(event):
        event.widget.tk_focusPrev().focus_set()
        return "break"

    def sync_controls(self):
        blocked = self.app.worker.busy or self.app.review is not None
        state = ["disabled"] if blocked else ["!disabled"]
        for widget in self.browser_controls:
            widget.state(["disabled"] if self.package_picker else state)
        for widget in self.form_controls:
            if isinstance(widget, self.app.tk.Text):
                widget.configure(state="disabled" if blocked else "normal")
            else:
                widget.state(state)
        connected = self.app._connected()
        if self.package_button is not None:
            self.package_button.state(["!disabled"] if not blocked and connected else ["disabled"])
        action_ready = not blocked and self.feature and (connected or not self.feature.requires_device)
        self.action.state(["!disabled"] if action_ready else ["disabled"])

    def _navigation_blocked(self):
        return self.app.worker.busy or self.app.review is not None or self.package_picker is not None

    def _browse(self, field, value):
        dialog = getattr(self.app.files, self.FILE_FIELDS[field.kind])
        options = {"parent": self.app.root, "title": field.label}
        if field.key == "list_file":
            options["filetypes"] = (("Fire Toolbox lists", "*.debloat"), ("Text lists", "*.txt"),
                                    ("All files", "*"))
        elif self.feature.key == "install-fdroid" and field.key == "path":
            options["filetypes"] = (("Android APK", "*.apk"),)
        selected = dialog(**options)
        if selected:
            value.set(json.dumps(list(selected)) if field.kind == "files" else selected)

    def _submit(self):
        if self.feature is not None:
            self.app._run_tool(self.feature, self._values)

    def _values(self):
        return {key: collect() for key, collect in self.field_sources.items()}

    def _choose_packages(self, box):
        app = self.app
        toolkit, serial = app.toolkit, app.device.serial
        mode = "uninstalled" if self.feature.operation == "restore" else "all"
        app._start(
            "Read package inventory",
            lambda _log: toolkit.package_inventory(serial, mode=mode),
            lambda rows: self._show_package_picker(serial, rows, box),
        )

    def _show_package_picker(self, serial, rows, box):
        app, ttk = self.app, self.app.ttk

        def current_form():
            return (
                app.device is not None and app.device.serial == serial
                and box in self.form_controls and box.winfo_exists()
            )

        if not current_form():
            return
        window, panel = app._tool_window("Choose packages", serial)
        self.package_picker = window

        def forget_picker(event):
            if event.widget is window:
                self.package_picker = None

        window.bind("<Destroy>", forget_picker)
        app._description(
            panel, "Use Shift or Ctrl/Command to select several packages. "
                   "Their IDs will be added to the form.",
        ).pack(fill="x", pady=(0, 8))
        search = app.tk.StringVar()
        ttk.Label(panel, text="Find packages", style="Panel.TLabel").pack(anchor="w")
        entry = ttk.Entry(panel, textvariable=search)
        entry.pack(fill="x", pady=(3, 8))

        def update_selection():
            add.state(["!disabled"] if table.selection() else ["disabled"])

        table = app._table(
            panel, (("package", "Package", 270), ("state", "State", 100), ("label", "Application", 165)),
            6, update_selection, selectmode="extended",
        )
        actions = ttk.Frame(panel, style="Panel.TFrame")
        actions.pack(fill="x", pady=(8, 0))

        def add_packages():
            if not current_form():
                window.destroy()
                return
            prior = package_values(box.get("1.0", "end-1c"))
            chosen = (table.set(item, "package") for item in table.selection())
            unique = dict.fromkeys((*prior, *chosen))
            box.delete("1.0", "end")
            box.insert("1.0", "\n".join(unique))
            window.destroy()
            box.focus_set()

        add = ttk.Button(
            actions, text="Add selected packages", command=add_packages, style="Primary.TButton",
        )
        add.pack(side="right")
        ttk.Button(actions, text="Cancel", command=window.destroy).pack(side="right", padx=8)

        def refresh(*_):
            query = search.get().strip().casefold()
            selected = set(table.selection())
            table.delete(*table.get_children())
            for index, row in enumerate(rows):
                values = (row["package"], row["state"], row["label"])
                if query in " ".join(values).casefold():
                    item = table.insert("", "end", iid=str(index), values=values)
                    if item in selected:
                        table.selection_add(item)
            if table.get_children():
                table.focus(table.get_children()[0])
            update_selection()

        search.trace_add("write", refresh)
        refresh()
        window.wait_visibility()
        window.grab_set()
        entry.focus_set()
