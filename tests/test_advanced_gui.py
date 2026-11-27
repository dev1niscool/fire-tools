"""Headless tests for the advanced tool dispatch and review boundary."""

from types import SimpleNamespace
from dataclasses import replace
import unittest

from open_fire_toolkit.adb import DeviceInfo
from open_fire_toolkit.feature_catalog import BY_KEY
from open_fire_toolkit.gui import App, Worker
from open_fire_toolkit.service import Plan, ToolConfig
from open_fire_toolkit.workflows import TransportPlan, WorkflowPlan


DEVICE = DeviceInfo("fire-one", "Fire HD", "Amazon", "8", "11", 30, ("arm64-v8a",), 0)
OTHER_DEVICE = DeviceInfo("fire-two", "Fire HD", "Amazon", "8", "11", 30, ("arm64-v8a",), 0)


class InMemoryToolkit:
    def __init__(self):
        self.requests = []
        self.writes = []

    def plan_package_action(self, serial, operation, packages, **params):
        self.requests.append(("package", serial, operation, packages, params))
        return Plan("Package preview", serial, packages, (), "package_workflow", DEVICE)

    def plan_device_action(self, serial, operation, **params):
        self.requests.append(("device", serial, operation, params))
        return Plan("Device preview", serial, tuple(params.values()), (), "device_workflow", DEVICE)

    def plan_extra_action(self, serial, operation, **params):
        self.requests.append(("extra", serial, operation, params))
        return TransportPlan("ADB transport preview", tuple(params.values()), (), operation, tuple(params.items()))

    def read_device_tool(self, serial, operation, **params):
        self.requests.append(("read", serial, operation, params))
        return "screen_off_timeout=30000"

    def package_inventory(self, serial, mode):
        self.requests.append(("inventory", serial, mode))
        return [{"package": "com.amazon.mp3", "state": "disabled", "label": "Amazon Music"}]

    def execute(self, plan, **_kwargs):
        self.writes.append(plan)


class DeferredApp(App):
    def __init__(self):
        self.device = DEVICE
        self.toolkit = InMemoryToolkit()
        self.worker = Worker()
        self.review = None
        self.output = None
        self.error = None
        self.pending = None

    def _start(self, title, action, complete):
        self.pending = (action, complete)

    def finish_background_action(self):
        action, complete = self.pending
        self.pending = None
        complete(action(lambda _line: None))

    def _review_plan(self, toolkit, plan):
        self.review = (toolkit, plan)

    def _show_tool_output(self, title, serial, result):
        self.output = (title, serial, result)

    def _show_error(self, title, error):
        self.error = (title, str(error))


class DeviceSelectionApp(DeferredApp):
    def __init__(self):
        super().__init__()
        self.devices = [DEVICE]
        self.device_table = ["0"]
        self.app_table = ["0"]
        self.firmware = SimpleNamespace(set=lambda _text: None)

    def _clear_table(self, table):
        table.clear()


class AdvancedToolDispatchTests(unittest.TestCase):
    def setUp(self):
        self.app = DeferredApp()

    def test_package_review_uses_selected_tablet_and_splits_bulk_package_ids(self):
        tool = BY_KEY["packages-disable"]
        self.app._run_tool(tool, lambda: {"packages": " com.amazon.mp3,\ncom.amazon.kindle \n"})
        self.app.finish_background_action()
        self.assertEqual(
            self.app.toolkit.requests,
            [("package", "fire-one", "disable", ("com.amazon.mp3", "com.amazon.kindle"), {})],
        )
        self.assertEqual(self.app.review[1].serial, "fire-one")
        self.assertEqual(self.app.toolkit.writes, [])

    def test_new_physical_tablet_at_selected_address_invalidates_selection_before_review(self):
        app = DeviceSelectionApp()
        app._sync_controls = lambda: None
        address = '192.0.2.10:5555'
        selected = replace(DEVICE, serial=address, hardware_serial_sha256='1' * 64)
        app.device = selected
        replacement = replace(selected, hardware_serial_sha256='2' * 64)
        plan = Plan("Restart tablet", address, (), (), "reboot", replacement)
        # Exercise the review gate used by both the dedicated tabs and catalog tools.
        App._review_plan(app, app.toolkit, plan)
        self.assertIsNone(app.review)
        self.assertIsNone(app.device)
        self.assertEqual(app.device_table, [])
        self.assertEqual(app.app_table, [])
        self.assertIn('scan', app.error[1].lower())
        self.assertEqual(app.toolkit.writes, [])

    def test_device_review_freezes_fields_before_dispatch(self):
        tool = BY_KEY["settings-set"]
        original_toolkit = self.app.toolkit
        fields = {"namespace": "system", "key": "screen_off_timeout", "value": "30000"}
        self.app._run_tool(tool, lambda: fields)
        fields["value"] = "60000"
        self.app.device = OTHER_DEVICE
        self.app.toolkit = InMemoryToolkit()
        self.app.finish_background_action()
        self.assertEqual(
            original_toolkit.requests,
            [("device", "fire-one", "setting", {
                "namespace": "system", "key": "screen_off_timeout", "value": "30000",
            })],
        )
        self.assertIs(self.app.review[0], original_toolkit)
        self.assertEqual(self.app.toolkit.requests, [])

    def test_inventory_passes_mode_and_presents_result_without_review(self):
        tool = BY_KEY["packages-inventory"]
        self.app._run_tool(tool, lambda: {"mode": "disabled"})
        self.app.finish_background_action()
        self.assertEqual(self.app.toolkit.requests, [("inventory", "fire-one", "disabled")])
        self.assertEqual(self.app.output, (tool.label, "fire-one", [
            {"package": "com.amazon.mp3", "state": "disabled", "label": "Amazon Music"},
        ]))
        self.assertIsNone(self.app.review)

    def test_device_read_uses_read_only_api(self):
        tool = BY_KEY["settings-list"]
        self.app._run_tool(tool, lambda: {"namespace": "system"})
        self.app.finish_background_action()
        self.assertEqual(
            self.app.toolkit.requests, [("read", "fire-one", "settings-list", {"namespace": "system"})],
        )
        self.assertEqual(self.app.output, (tool.label, "fire-one", "screen_off_timeout=30000"))
        self.assertIsNone(self.app.review)

    def test_no_tablet_refuses_before_collecting_fields(self):
        self.app.device = None
        tool = BY_KEY["screenshot"]
        self.app._run_tool(tool, lambda: self.fail("No fields should be read without a tablet"))
        self.assertIsNone(self.app.pending)
        self.assertEqual(self.app.toolkit.requests, [])
        self.assertEqual(self.app.error[0], tool.label)
        self.assertIn("Connection", self.app.error[1])

    def test_source_directory_is_available_without_tablet_or_toolkit(self):
        self.app.device = None
        self.app.toolkit = None
        tool = BY_KEY["source-catalog"]
        self.app._run_tool(tool, dict)
        self.assertIsNotNone(self.app.pending, self.app.error)
        self.app.finish_background_action()
        title, serial, result = self.app.output
        self.assertEqual((title, serial), (tool.label, ""))
        self.assertIn("https://f-droid.org", result)
        self.assertIsNone(self.app.review)

    def test_transport_review_loads_configured_adb_without_selecting_tablet(self):
        toolkit = self.app.toolkit
        self.app.device = None
        self.app.toolkit = None
        self.app.ToolConfig = ToolConfig
        configured = []

        def new_toolkit(config):
            configured.append(config)
            return toolkit

        self.app.paths = [
            SimpleNamespace(get=lambda value=value: value)
            for value in ("/test-tools/adb", "", "", "")
        ]
        self.app.Toolkit = new_toolkit
        tool = BY_KEY["wireless-connect"]
        self.app._run_tool(tool, lambda: {"endpoint": "fire-tablet.local:5555"})
        self.assertIsNotNone(self.app.pending, self.app.error)
        self.app.paths.clear()
        self.app.finish_background_action()
        self.assertEqual(configured, [ToolConfig("/test-tools/adb")])
        self.assertEqual(toolkit.requests, [
            ("extra", "", "wireless-connect", {"endpoint": "fire-tablet.local:5555"}),
        ])
        self.assertIs(self.app.review[0], toolkit)
        self.assertEqual(toolkit.writes, [])
        self.assertIn("fire-tablet.local:5555", self.app._plan_text(self.app.review[1]))

    def test_transport_changes_discard_selection_before_uncertain_execution(self):
        endpoint = (("endpoint", "fire-tablet.local:5555"),)
        plans = (
            TransportPlan("Connect", (), (), "wireless-connect", endpoint),
            TransportPlan("Disconnect", (), (), "wireless-disconnect", endpoint),
            WorkflowPlan("Enable wireless ADB", DEVICE.serial, (), (), "extra_workflow", DEVICE, "wireless-enable"),
            WorkflowPlan("Return to USB ADB", DEVICE.serial, (), (), "extra_workflow", DEVICE, "wireless-usb"),
        )

        def fail(plan, confirmed, log):
            self.assertTrue(confirmed)
            raise RuntimeError("ADB transport state is uncertain")

        for plan in plans:
            with self.subTest(operation=plan.operation):
                app = DeviceSelectionApp()
                toolkit = app.toolkit
                toolkit.execute = fail
                app._execute(toolkit, plan)
                self.assertIsNone(app.device)
                self.assertEqual(app.devices, [])
                self.assertEqual(app.device_table, [])
                with self.assertRaisesRegex(RuntimeError, "state is uncertain"):
                    app.finish_background_action()
                self.assertIsNone(app.device)
                self.assertIs(app.toolkit, toolkit)
