"""Rendered advanced GUI smoke test. Run with a Tk display using demo only."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from open_fire_toolkit.adb import Device, DeviceInfo
from open_fire_toolkit.feature_catalog import FEATURES
from open_fire_toolkit.gui import App
from open_fire_toolkit.package_catalog import DEBLOAT_TITLES
from open_fire_toolkit.workflows import TransportPlan


def descendants(parent):
    for child in parent.winfo_children():
        yield child
        yield from descendants(child)


def button(parent, label):
    matches = [
        widget for widget in descendants(parent)
        if isinstance(widget, ttk.Button) and widget.cget("text") == label
        and widget.winfo_viewable()
    ]
    assert len(matches) == 1, label
    return matches[0]


def click(parent, label):
    widget = button(parent, label)
    assert widget.instate(["!disabled"]), label
    widget.invoke()
    parent.update()


def wait(root, condition, description):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        root.update()
        value = condition()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {description}")


def text_box(window):
    return next(widget for widget in descendants(window) if isinstance(widget, tk.Text))


def displayed_window(root, title):
    return next(
        (item for item in root.winfo_children()
         if isinstance(item, tk.Toplevel) and item.title() == title and item.winfo_viewable()),
        None,
    )


def smoke(root):
    app = App(root, demo=True)
    root.geometry("680x660")
    root.update()
    assert root.winfo_viewable()
    assert root.title() == "Fire Tools · Demo"
    assert app.log_box.winfo_height() > 50
    assert [app.tabs.tab(tab, "text") for tab in app.tabs.tabs()] == [
        "Connection", "Google Play", "Lock-screen ads", "Apps", "Tools",
    ]

    app.tabs.select(4)
    root.update()
    assert app.advanced.action.instate(["disabled"])
    assert app.advanced.tool_list.get_children() == tuple(feature.key for feature in FEATURES)
    for feature in FEATURES:
        app.advanced.show_feature(feature.key)
        root.update()
        assert app.advanced.feature == feature
        assert app.advanced.action.winfo_viewable()
        assert app.advanced._values() == {field.key: field.default for field in feature.fields}

    app.tabs.select(0)
    root.update()
    click(root, "Scan devices")
    wait(root, lambda: not app.worker.busy, "device scan")
    app.device_table.selection_set("0")
    root.update()
    click(root, "Use selected tablet")
    wait(root, lambda: app.device is not None and not app.worker.busy, "tablet selection")
    serial = app.device.serial

    app.tabs.select(3)
    root.update()
    click(root, "Debloat Amazon apps...")
    assert app.tabs.tab(app.tabs.select(), "text") == "Tools"
    assert app.advanced.feature.key == "debloat"
    assert serial in app.status.get()
    assert app.advanced.form_canvas.winfo_height() > 100
    initially_disabled = app.toolkit.disabled.copy()

    def review():
        click(root, "Review...")
        window = wait(root, lambda: app.review, "plan review")
        assert window.grab_current() is window
        labels = [item.cget("text") for item in descendants(window) if isinstance(item, ttk.Label)]
        assert any(serial in label for label in labels)
        preview = text_box(window)
        assert preview.cget("state") == "disabled"
        return window, preview.get("1.0", "end")

    window, preview = review()
    review_labels = [str(widget.cget("text")) for widget in descendants(window) if isinstance(widget, ttk.Label)]
    assert any("SIMULATED" in label and "Standard Debloat (Recommended)" in label for label in review_labels)
    assert "com.amazon.kindle" in preview and "com.amazon.cloud9" not in preview
    click(window, "Cancel")
    assert app.review is None and app.toolkit.disabled == initially_disabled
    assert "Simulation finished" not in app.log_box.get("1.0", "end")

    app.advanced.show_feature("packages-disable")
    root.update()
    inventory = app.toolkit.package_inventory
    finish_inventory = threading.Event()
    callback_errors = []
    root.report_callback_exception = lambda _kind, error, _stack: callback_errors.append(error)

    def delayed_inventory(*args, **kwargs):
        assert finish_inventory.wait(5), "Package inventory was not released"
        return inventory(*args, **kwargs)

    app.toolkit.package_inventory = delayed_inventory
    try:
        click(root, "Choose packages...")
        assert app.worker.busy
        tools = app.advanced.tool_list
        x, y, width, height = tools.bbox("packages-enable")
        point = {"x": x + width // 2, "y": y + height // 2}
        tools.event_generate("<ButtonPress-1>", **point)
        tools.event_generate("<ButtonRelease-1>", **point)
        root.update()
    finally:
        finish_inventory.set()
        app.toolkit.package_inventory = inventory
    picker = wait(root, lambda: displayed_window(root, "Choose packages"), "package picker")
    table = next(item for item in descendants(picker) if isinstance(item, ttk.Treeview))
    assert str(table.cget("selectmode")) == "extended"
    assert len(table.get_children()) >= 2
    chosen = table.get_children()[:2]
    package_ids = [table.set(row, "package") for row in chosen]
    table.selection_set(chosen)
    root.update()
    click(picker, "Add selected packages")
    assert not callback_errors, callback_errors
    assert not picker.winfo_exists()
    assert app.advanced.feature.key == "packages-disable"
    window, preview = review()
    assert all(package in preview for package in package_ids)
    click(window, "Cancel")
    assert app.toolkit.disabled == initially_disabled

    app.advanced.show_feature("settings-set")
    root.update()
    fields = [item for item in descendants(app.advanced.form) if type(item) is ttk.Entry]
    assert len(fields) == 2
    for entry, value in zip(fields, ("screen_off_timeout", "30000"), strict=True):
        entry.delete(0, "end")
        entry.insert(0, value)
    window, preview = review()
    assert "screen_off_timeout" in preview and "30000" in preview
    click(window, "Cancel")

    app.advanced.show_feature("settings-list")
    root.update()
    click(root, "Read")
    output = wait(
        root, lambda: displayed_window(root, app.advanced.feature.label), "settings read result",
    )
    assert text_box(output).cget("state") == "disabled"
    assert "SIMULATED" in text_box(output).get("1.0", "end")
    click(output, "Close")
    assert app.review is None

    app.advanced.show_feature("packages-inventory")
    root.update()
    click(root, "Read")
    output = wait(
        root, lambda: displayed_window(root, app.advanced.feature.label), "package inventory",
    )
    assert "com.amazon." in text_box(output).get("1.0", "end")
    click(output, "Close")

    category = next(item for item in descendants(app.advanced.tab) if isinstance(item, ttk.Combobox))
    category.set("All categories")
    category.event_generate("<<ComboboxSelected>>")
    app.advanced.search.set("screenshot")
    root.update()
    assert "screenshot" in app.advanced.tool_list.get_children()
    app.advanced.tool_list.selection_set("screenshot")
    root.update()
    assert app.advanced.feature.key == "screenshot"
    with TemporaryDirectory() as directory:
        main_thread = threading.get_ident()
        destination = Path(directory) / "Fire preview.png"

        def choose_save_path(**_params):
            assert threading.get_ident() == main_thread
            return str(destination)

        app.files = SimpleNamespace(asksaveasfilename=choose_save_path)
        click(root, "Browse...")
        window, preview = review()
        assert str(destination) in preview
        click(window, "Cancel")
        assert "Simulation finished" not in app.log_box.get("1.0", "end")
        assert not destination.exists()

        window, _ = review()
        click(window, "Confirm simulation")
        wait(root, lambda: not app.worker.busy, "simulated screenshot completion")
        assert "Simulation finished" in app.log_box.get("1.0", "end")
        assert not destination.exists()

    check_debloat_presets(app, review)
    app.tabs.select(2)
    root.update()
    click(root, "Disable Special Offers package...")
    assert app.advanced.feature.key == "ads-package-disable"
    app.tabs.select(2)
    root.update()
    click(root, "Set up ad helper...")
    assert app.advanced.feature.key == "helper-start"
    assert serial in app.status.get()
    assert not callback_errors, callback_errors


def check_debloat_presets(app, review):
    root = app.root
    initially_disabled = app.toolkit.disabled.copy()
    app.tabs.select(3)
    root.update()
    click(root, "Debloat Amazon apps...")
    form = app.advanced.form
    preset, mode = [item for item in descendants(form) if isinstance(item, ttk.Combobox)]
    custom_file = next(item for item in descendants(form) if type(item) is ttk.Entry)

    def choose(combo, title):
        combo.current(combo.cget("values").index(title))
        combo.event_generate("<<ComboboxSelected>>")
        root.update()

    def form_labels():
        return " ".join(str(w.cget("text")) for w in descendants(form)
                        if isinstance(w, ttk.Label) and w.winfo_ismapped())

    assert preset.get() == "Standard Debloat (Recommended)"
    assert not custom_file.winfo_ismapped()
    standard_help = form_labels()
    assert all(name in standard_help for name in ("Appstore", "Silk", "Camera"))
    assert app.advanced._values()["profile"] == "standard"
    assert len(preset.cget("values")) == 5
    for legacy in ("standard-v0.2", "complete-v0.2"):
        choose(preset, DEBLOAT_TITLES[legacy])
        assert app.advanced._values()["profile"] == legacy
    choose(preset, DEBLOAT_TITLES["custom"])
    assert custom_file.winfo_ismapped()
    custom_file.insert(0, "custom fixture.debloat")
    assert app.advanced._values()["list_file"] == "custom fixture.debloat"
    choose(preset, "Complete Debloat")
    assert not custom_file.winfo_ismapped()
    assert app.advanced._values() == {"profile": "complete", "list_file": "", "mode": "auto"}
    complete_help = form_labels()
    assert complete_help != standard_help
    assert all(name in complete_help for name in ("Appstore", "Silk", "Camera", "Device Setup"))
    for title, action in zip(mode.cget("values"), ("auto", "disable", "enable", "uninstall"), strict=True):
        choose(mode, title)
        assert app.advanced._values()["mode"] == action
    choose(mode, mode.cget("values")[0])

    window, preview = review()
    assert "com.amazon.cloud9" in preview
    assert preset.instate(["disabled"]) and mode.instate(["disabled"])
    assert app.toolkit.disabled == initially_disabled
    click(window, "Confirm simulation")
    wait(root, lambda: not app.worker.busy, "Complete Debloat simulation")
    assert "com.amazon.cloud9" in app.toolkit.disabled
    assert "com.amazon.kindle.otter.oobe" not in app.toolkit.disabled
    after_complete = app.toolkit.disabled.copy()
    app.tabs.select(3)
    root.update()
    click(root, "Restore Everything...")
    window, preview = review()
    assert "com.amazon.cloud9" in preview and "com.android.calendar" in preview
    assert app.advanced.action.instate(["disabled"])
    app.advanced.show_feature("packages-undo")
    assert app.advanced.feature.key == "debloat-restore"
    click(window, "Cancel")
    assert app.toolkit.disabled == after_complete
    window, _ = review()
    click(window, "Confirm simulation")
    wait(root, lambda: not app.worker.busy, "Restore Everything simulation")
    assert "com.amazon.cloud9" not in app.toolkit.disabled
    assert "com.android.calendar" in initially_disabled - app.toolkit.disabled
    app.tabs.select(3)
    root.update()
    click(root, "Undo saved package changes...")
    window, _ = review()
    click(window, "Confirm simulation")
    wait(root, lambda: not app.worker.busy, "Undo of Restore Everything")
    assert app.toolkit.disabled == after_complete


def connection_layout(root):
    app = App(root)
    root.geometry("680x660")
    root.update()
    assert app.device_table.winfo_viewable()
    assert app.device_table.winfo_height() >= 50
    button(root, "Scan devices")


def tools_without_tablet(root):
    app = App(root)
    root.update()
    app.tabs.select(3)
    root.update()
    click(root, "Compare debloat presets...")
    output = wait(root, lambda: displayed_window(root, "Compare debloat presets"), "offline preset list")
    comparison = text_box(output).get("1.0", "end")
    assert all(term in comparison for term in ("Standard", "Complete", "com.amazon.cloud9"))
    click(output, "Close")
    assert app.tabs.tab(app.tabs.select(), "text") == "Apps"
    assert app.toolkit is None and app.device is None
    for label, key in (("Restore Everything...", "debloat-restore"),
                       ("Undo saved package changes...", "packages-undo")):
        app.tabs.select(3)
        root.update()
        click(root, label)
        assert app.advanced.feature.key == key
        assert app.advanced.action.instate(["disabled"])
    app.advanced.show_feature("source-catalog")
    root.update()
    assert app.device is None and app.toolkit is None
    click(root, "Read")
    output = wait(
        root, lambda: displayed_window(root, app.advanced.feature.label), "offline source directory",
    )
    assert "https://f-droid.org" in text_box(output).get("1.0", "end")
    click(output, "Close")
    assert app.toolkit is None and app.device is None

    endpoint = "fire-tablet.local:5555"
    executions = []

    class RecordingToolkit:
        connected = False
        connections = 0

        def plan_extra_action(self, serial, operation, **params):
            assert serial == "" and operation in ("wireless-connect", "wireless-disconnect")
            return TransportPlan("Change ADB transport", (params["endpoint"],), (), operation, tuple(params.items()))

        def execute(self, plan, confirmed=False, log=print):
            executions.append((plan, confirmed))
            self.connected = plan.operation == "wireless-connect"
            if self.connected:
                self.connections += 1
            return ["Simulated ADB transport change completed."]

        def devices(self):
            return [Device(endpoint, "device", f"Fire_fixture_{self.connections}")] if self.connected else []

        def device_info(self, serial):
            assert self.connected and serial == endpoint
            model = f"Fire tablet {self.connections}"
            return DeviceInfo(serial, model, "Amazon", "8", "11", 30, ("arm64-v8a",), 0)

    toolkit = RecordingToolkit()
    app.Toolkit = lambda config: toolkit
    app.paths[0].set("/fixture/adb")

    def preview_transport(key):
        app.advanced.show_feature(key)
        root.update()
        field = next(widget for widget in descendants(app.advanced.form) if isinstance(widget, ttk.Entry))
        field.delete(0, "end")
        field.insert(0, endpoint)
        before = len(executions)
        click(root, "Review...")
        window = wait(root, lambda: app.review, "connection review")
        assert endpoint in text_box(window).get("1.0", "end")
        assert len(executions) == before
        return window

    def confirm_transport(key):
        click(preview_transport(key), "Confirm and run")
        wait(root, lambda: not app.worker.busy, "reviewed connection execution")

    def scan():
        app.tabs.select(0)
        root.update()
        click(root, "Scan devices")
        wait(root, lambda: not app.worker.busy, "device scan")
        assert app.device is None
        assert app.device_table.get_children() == ("0",)
        assert button(root, "Use selected tablet").instate(["disabled"])

    def select_tablet(expected_model):
        app.tabs.select(0)
        app.device_table.selection_set("0")
        root.update()
        click(root, "Use selected tablet")
        wait(root, lambda: app.device and not app.worker.busy, "network tablet selection")
        assert app.device.serial == endpoint
        assert app.device.model == expected_model

    def tablet_actions_enabled():
        app.advanced.show_feature("settings-list")
        root.update()
        return button(root, "Read").instate(["!disabled"])

    click(preview_transport("wireless-connect"), "Cancel")
    assert app.review is None and not executions and app.device is None
    confirm_transport("wireless-connect")
    [(plan, confirmed)] = executions
    assert confirmed and plan.serial == ""
    assert plan.params == {"endpoint": endpoint}
    scan()
    select_tablet("Fire tablet 1")
    assert tablet_actions_enabled()

    click(preview_transport("wireless-disconnect"), "Cancel")
    assert app.device.model == "Fire tablet 1"
    assert app.device_table.get_children() == ("0",)
    confirm_transport("wireless-disconnect")
    assert app.device is None and not app.device_table.get_children()
    assert not tablet_actions_enabled()
    confirm_transport("wireless-connect")
    assert app.toolkit is toolkit and toolkit.connected
    assert app.device is None and not app.device_table.get_children()
    assert not tablet_actions_enabled()

    scan()
    assert not tablet_actions_enabled()
    select_tablet("Fire tablet 2")
    assert tablet_actions_enabled()


if __name__ == "__main__":
    desktop = tk.Tk()
    try:
        smoke(desktop)
        connection_layout(tk.Toplevel(desktop))
        tools_without_tablet(tk.Toplevel(desktop))
    finally:
        desktop.destroy()
    print("PASS: rendered preset comparison, Complete Debloat, Restore Everything, saved undo, package picker, "
          "tool navigation and ADB transport reselection")
