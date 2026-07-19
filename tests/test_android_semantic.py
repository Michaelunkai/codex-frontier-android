import importlib.util
import pathlib
import unittest
from unittest import mock


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME_PATH = PROJECT_ROOT / "bin" / "codex_runtime.py"
SPEC = importlib.util.spec_from_file_location("codex_frontier_runtime", RUNTIME_PATH)
RUNTIME = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNTIME)


UI_XML = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout"
        package="com.example.app" content-desc="" checkable="false" checked="false"
        clickable="false" enabled="true" focusable="false" focused="false"
        scrollable="false" long-clickable="false" password="false" selected="false"
        bounds="[0,0][1080,2400]">
    <node index="1" text="Search" resource-id="com.example.app:id/search"
          class="android.widget.Button" package="com.example.app"
          content-desc="Search everything" checkable="false" checked="false"
          clickable="true" enabled="true" focusable="true" focused="false"
          scrollable="false" long-clickable="true" password="false" selected="false"
          bounds="[100,200][500,320]" />
    <node index="2" text="draft" resource-id="com.example.app:id/input"
          class="android.widget.EditText" package="com.example.app"
          content-desc="Prompt" checkable="false" checked="false"
          clickable="true" enabled="true" focusable="true" focused="true"
          scrollable="false" long-clickable="true" password="false" selected="false"
          bounds="[50,1800][1000,2000]" />
    <node index="3" text="should-not-leak" resource-id="com.example.app:id/password"
          class="android.widget.EditText" package="com.example.app"
          content-desc="Password" checkable="false" checked="false"
          clickable="true" enabled="true" focusable="true" focused="false"
          scrollable="false" long-clickable="true" password="true" selected="false"
          bounds="[50,2050][1000,2200]" />
  </node>
</hierarchy>"""


class AndroidSemanticTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "root": PROJECT_ROOT / "runtime" / ".codex",
            "test_mode": True,
            "env": {},
        }

    def test_parse_hierarchy_and_redact_password(self):
        hierarchy = RUNTIME.parse_android_ui_xml(UI_XML)
        self.assertEqual(hierarchy["elementCount"], 4)
        self.assertEqual(hierarchy["packages"], ["com.example.app"])
        search = hierarchy["elements"][1]
        self.assertEqual(search["center"], {"x": 300, "y": 260})
        self.assertTrue(search["clickable"])
        self.assertTrue(hierarchy["elements"][2]["editable"])
        self.assertEqual(hierarchy["elements"][3]["text"], "")
        self.assertTrue(hierarchy["elements"][3]["password"])

    def test_selector_supports_all_semantic_fields(self):
        elements = RUNTIME.parse_android_ui_xml(UI_XML)["elements"]
        selectors = (
            {"text": "search"},
            {"textContains": "ear"},
            {"contentDescription": "search everything"},
            {"descriptionContains": "everything"},
            {"resourceId": "com.example.app:id/search"},
            {"resourceIdContains": "id/search"},
            {"className": "android.widget.Button"},
            {"classContains": "button"},
            {"package": "com.example.app", "clickable": True, "editable": False},
            {"contains": "everything"},
            {"textRegex": "^sea.*h$"},
        )
        for selector in selectors:
            with self.subTest(selector=selector):
                self.assertIn(1, [item["index"] for item in RUNTIME.select_ui_elements(elements, selector)])

    def test_match_index_is_deterministic(self):
        elements = RUNTIME.parse_android_ui_xml(UI_XML)["elements"]
        matches = RUNTIME.select_ui_elements(
            elements, {"package": "com.example.app", "clickable": True, "matchIndex": 1}
        )
        self.assertEqual([item["index"] for item in matches], [2])

    def test_alias_and_fuzzy_package_scoring(self):
        self.assertIn("com.facebook.katana", RUNTIME.ANDROID_APP_ALIASES["facebook"])
        direct = RUNTIME.android_package_score("com.spotify.music", "spotify", "spotify")
        unrelated = RUNTIME.android_package_score("com.example.reader", "spotify", "spotify")
        self.assertGreater(direct, unrelated)

    def test_display_label_scoring_handles_unrelated_package_names(self):
        self.assertEqual(RUNTIME.android_label_score("Google Wallet", "google wallet"), 9000)
        self.assertGreater(
            RUNTIME.android_label_score("Samsung Health", "health"),
            RUNTIME.android_label_score("Samsung Health", "browser"),
        )

    def test_verified_launch_uses_component_and_foreground_readback(self):
        resolved = {
            "query": "Example",
            "package": "com.example.app",
            "component": "com.example.app/.MainActivity",
            "score": 9000,
            "alternatives": [],
            "inventoryCount": 20,
            "inventoryBackend": "test",
            "componentEvidence": {},
        }
        before = {"package": "com.other", "component": "com.other/.Main"}
        foreground = {"package": "com.example.app", "component": "com.example.app/.MainActivity"}
        with mock.patch.object(RUNTIME, "resolve_android_app", return_value=resolved), \
             mock.patch.object(RUNTIME, "android_foreground", side_effect=[before, foreground]), \
             mock.patch.object(RUNTIME, "wait_for_android_package", return_value=(foreground, [])), \
             mock.patch.object(RUNTIME, "run_privileged", return_value=RUNTIME.command_result(backend="test")), \
             mock.patch.object(RUNTIME.time, "sleep", return_value=None):
            result = RUNTIME.launch_android_app("Example", {**self.context, "test_mode": False})
        self.assertTrue(result["verified"])
        self.assertEqual(result["package"], "com.example.app")
        self.assertEqual(result["attempts"][0]["command"][-1], "com.example.app/.MainActivity")

    def test_sequence_compiles_structured_selectors(self):
        arguments = RUNTIME.android_sequence_step_arguments(
            {
                "action": "tap-element",
                "selector": {"text": "Continue", "clickable": True},
                "after_selector": {"text": "Done"},
                "timeout": 8,
            }
        )
        self.assertEqual(arguments[0], "tap-element")
        self.assertIn("--selector", arguments)
        self.assertIn('{"text":"Continue","clickable":true}', arguments)
        self.assertIn("--after-selector", arguments)

    def test_sequence_preserves_per_step_verification(self):
        steps = [{"action": "focus"}, {"action": "capabilities"}]
        with mock.patch.object(
            RUNTIME, "handle_android", return_value=RUNTIME.command_result(verified=True)
        ):
            result = RUNTIME.execute_android_sequence(steps, self.context)
        self.assertTrue(result["verified"])
        self.assertEqual(result["completedSteps"], 2)

    def test_protected_package_guard_blocks_destructive_shell_routes(self):
        for command in (
            ["am", "force-stop", "com.michaelovsky.codexapplauncher"],
            ["pm", "clear", "com.michaelovsky.codexnvidia.isolated"],
            ["pm", "uninstall", "com.michaelovsky.codexsubscription.isolated"],
            ["pm", "uninstall", "com.termux"],
        ):
            with self.subTest(command=command):
                with self.assertRaises(RUNTIME.CommandFailure):
                    RUNTIME.guard_android_shell_command(command)

    def test_android_text_encoding_preserves_words(self):
        self.assertEqual(RUNTIME.encode_android_input_text("hello world"), "hello%sworld")
        self.assertEqual(RUNTIME.encode_android_input_text("100% ready"), "100%25%sready")

    def test_github_secret_redaction_and_export_guard(self):
        secret = "gho_" + "A" * 36
        redacted = RUNTIME.redact_github_secrets({"stdout": "Token: " + secret + " gho_************************************"})
        self.assertNotIn(secret, redacted["stdout"])
        self.assertNotIn("gho_", redacted["stdout"])
        self.assertIn("[REDACTED]", redacted["stdout"])
        with self.assertRaises(RUNTIME.CommandFailure):
            RUNTIME.handle_github(["gh", "auth", "token"], self.context)

    def test_windows_health_actions_use_bounded_retries(self):
        with mock.patch.object(RUNTIME, "windows_gateway_request", return_value={"ok": True}) as request:
            result = RUNTIME.handle_win(["diagnostics"], self.context)
        self.assertTrue(result["ok"])
        self.assertEqual(request.call_args.kwargs["retries"], 3)


if __name__ == "__main__":
    unittest.main()
