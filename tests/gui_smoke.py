"""Run in a graphical session: python tests/gui_smoke.py. Demo only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import time
import tkinter as tk
from tkinter import ttk

from open_fire_toolkit.gui import App

root = tk.Tk()
app = App(root, demo=True)


def wait_until(predicate):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for GUI operation")


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


def button(label, parent=None):
    buttons = [
        item for item in widgets(parent or root)
        if isinstance(item, ttk.Button) and item.cget("text") == label
    ]
    assert len(buttons) == 1, label
    return buttons[0]


def click(label, parent=None):
    item = button(label, parent)
    assert item.instate(["!disabled"]), label
    item.invoke()
    root.update()


def tab(index):
    app.tabs.select(index)
    root.update()


def review(label):
    click(label)
    wait_until(lambda: app.review is not None and app.review.grab_current() is app.review)
    assert button("Scan devices").instate(["disabled"])
    return app.review


def confirm(window):
    click("Confirm simulation", window)
    wait_until(lambda: not app.worker.busy)
    assert app.review is None


root.update()
assert root.winfo_viewable()
assert "Demo" in app.status.get()
assert button("Use selected tablet").instate(["disabled"])
click("Scan devices")
wait_until(lambda: not app.worker.busy)
assert app.device is None
assert len(app.device_table.get_children()) == 1
app.device_table.selection_set("0")
root.update()
click("Use selected tablet")
wait_until(lambda: app.device is not None and not app.worker.busy)
assert "DEMO_FIRE_HD10" in app.status.get()
assert "SDK 30" in app.firmware.get()


tab(1)
click("Use demo sample")
assert len(app.apk_table.get_children()) == 4
window = review("Verify and review...")
preview = next(item for item in widgets(window) if isinstance(item, tk.Text))
assert "SIMULATED" in preview.get("1.0", "end")
click("Cancel", window)
assert "Simulation finished" not in app.log_box.get("1.0", "end")
confirm(review("Verify and review..."))
assert "Simulation finished" in app.log_box.get("1.0", "end")

tab(2)
errors = []


def dismiss_error():
    dialogs = root.tk.call("winfo", "children", ".")
    expected = ".__tk__messagebox"
    if expected not in dialogs:
        root.after(15, dismiss_error)
        return
    errors.append(root.tk.call(expected + ".msg", "cget", "-text"))
    root.tk.call(expected + ".ok", "invoke")


root.after(20, dismiss_error)
click("Review restore...")
wait_until(lambda: not app.worker.busy)
assert len(errors) == 1 and "suppression first" in errors[0], errors
assert app.review is None
assert button("Review setting change...").instate(["!disabled"])
window = review("Review setting change...")
assert app.toolkit.value == "1"
confirm(window)
assert app.toolkit.value == "0"
confirm(review("Review restore..."))
assert app.toolkit.value == "1"

confirm(review("Suppress with setting and package..."))
assert app.toolkit.value == "0" and "com.amazon.kindle.kso" in app.toolkit.disabled
confirm(review("Undo setting and package..."))
assert app.toolkit.value == "1" and "com.amazon.kindle.kso" not in app.toolkit.disabled

tab(3)
click("Read app states")
wait_until(lambda: not app.worker.busy)
assert app.loaded_apps
app.app_table.selection_set("0")
root.update()
package, _ = app.loaded_apps[0]
initially_disabled = app.toolkit.disabled.copy()
confirm(review("Review disable..."))
assert app.toolkit.disabled == initially_disabled | {package}
click("Read app states")
wait_until(lambda: not app.worker.busy)
app.app_table.selection_set("0")
root.update()
confirm(review("Review enable..."))
assert app.toolkit.disabled == initially_disabled

tab(0)
confirm(review("Review reboot..."))
assert app.device is None
assert app.device_table.get_children() == ()
root.destroy()
print("PASS: rendered demo, explicit scan/selection, Play preview/cancel/confirmation, ads validation error/modify/restore, app disable/enable, reboot")
