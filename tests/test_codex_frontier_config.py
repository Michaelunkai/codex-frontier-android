import json
import pathlib
import shutil
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_MODELS = {
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.3-codex-spark",
    "codex-auto-review",
}


class CodexFrontierConfigTests(unittest.TestCase):
    def test_manifest_has_independent_identity(self):
        root = ET.parse(ROOT / "AndroidManifest.xml").getroot()
        android = "{http://schemas.android.com/apk/res/android}"
        self.assertEqual(root.attrib["package"], "com.michaelovsky.codexsubscription.isolated")
        self.assertEqual(root.attrib[android + "versionCode"], "11")
        self.assertEqual(root.attrib[android + "versionName"], "2.8.0")

    def test_launcher_uses_independent_root_and_port(self):
        source = (ROOT / "src/com/michaelovsky/codexsubscription/isolated/RuntimeContract.java").read_text()
        self.assertIn("/codex-subscription-isolated-app", source)
        self.assertIn("/codex-frontier-start.sh", source)
        self.assertIn("http://127.0.0.1:5902/", source)
        self.assertNotIn("nvidia-isolated-app", source)
        self.assertNotIn("http://127.0.0.1:5900/", source)
        self.assertNotIn("http://127.0.0.1:5901/", source)

    def test_native_codex_provider_and_default(self):
        config = (ROOT / "runtime/.codex/config.toml").read_text()
        self.assertIn('model = "gpt-5.6-sol"', config)
        self.assertIn('model_reasoning_effort = "ultra"', config)
        for feature in ("goals", "multi_agent", "apps", "plugins", "hooks", "browser_use", "computer_use", "image_generation", "unified_exec"):
            self.assertIn(f"{feature} = true", config)
        self.assertNotIn("model_provider", config)
        self.assertFalse((ROOT / "runtime/.codex/webui-custom-providers.json").exists())

    def test_maximum_persistent_memory_is_enabled_without_secret_storage(self):
        config = (ROOT / "runtime/.codex/config.toml").read_text()
        agents = (ROOT / "workspace/AGENTS.md").read_text()
        for setting in (
            "generate_memories = true",
            "use_memories = true",
            "disable_on_external_context = false",
            "min_rate_limit_remaining_percent = 0",
        ):
            self.assertIn(setting, config)
        self.assertIn("codex-lessons", agents)
        self.assertIn("Never put passwords, tokens, private keys", agents)

    def test_secure_windows_github_delegation_is_available(self):
        runtime = (ROOT / "bin/codex_runtime.py").read_text()
        agents = (ROOT / "workspace/AGENTS.md").read_text()
        self.assertIn('"codex-github"', runtime)
        self.assertIn("credential-exporting GitHub CLI commands are blocked", runtime)
        self.assertIn("GITHUB_SECRET_PATTERNS", runtime)
        self.assertIn("credentials remain in the Windows credential store", agents)

    def test_external_project_roots_are_visible_but_protected(self):
        config = (ROOT / "runtime/.codex/config.toml").read_text()
        identity = (ROOT / "vendor/codexapp-frontier-src/src/runtimeIdentity.ts").read_text()
        for root in (
            "/data/data/com.termux/files/home/com.michaelovsky.codexsubscription.isolated",
            "/data/data/com.termux/files/home/nvidia-isolated-app",
        ):
            self.assertIn(root, config)
            self.assertIn(root, identity)
        self.assertIn("protected read-only references", identity)

    def test_auth_is_chatgpt_subscription_not_api_key(self):
        auth = json.loads((ROOT / "runtime/.codex/auth.json").read_text())
        self.assertEqual(auth.get("auth_mode"), "chatgpt")
        self.assertTrue(auth.get("tokens"))
        self.assertFalse(auth.get("OPENAI_API_KEY"))

    def test_complete_subscription_catalog_is_preserved(self):
        documented = json.loads((ROOT / "models/subscription-models.json").read_text())
        cached = json.loads((ROOT / "runtime/.codex/models_cache.json").read_text())
        self.assertEqual(documented["defaultModel"], "gpt-5.6-sol")
        self.assertEqual({item["id"] for item in documented["models"]}, EXPECTED_MODELS)
        self.assertTrue(EXPECTED_MODELS <= {item.get("slug") for item in cached["models"]})

    def test_all_three_apps_are_protected_by_command_runtime(self):
        runtime = (ROOT / "bin/codex_runtime.py").read_text()
        uninstall = (ROOT / "bin/codex-uninstall").read_text()
        for package in (
            "com.michaelovsky.codexapplauncher",
            "com.michaelovsky.codexnvidia.isolated",
            "com.michaelovsky.codexsubscription.isolated",
        ):
            self.assertIn(package, runtime)
            self.assertIn(package, uninstall)

    def test_icon_resources_are_codex_frontier_specific(self):
        launcher = (ROOT / "res/mipmap-anydpi-v33/ic_launcher.xml").read_text()
        self.assertIn("codex_frontier", launcher)
        self.assertNotIn("nvidia", launcher.lower())
        self.assertTrue((ROOT / "res/drawable-nodpi/ic_codex_frontier_master.png").stat().st_size > 100_000)
        ET.parse(ROOT / "res/drawable/ic_codex_frontier_foreground.xml")
        ET.parse(ROOT / "res/drawable/ic_codex_frontier_monochrome.xml")

    def test_no_foreign_writable_symlink(self):
        allowed = {
            pathlib.Path("/data/data/com.termux/files/usr/bin/am"),
            pathlib.Path("/data/data/com.termux/files/usr/bin/bash"),
            pathlib.Path("/data/data/com.termux/files/usr/bin/dash"),
            pathlib.Path("/data/data/com.termux/files/usr/bin/sh"),
            pathlib.Path(shutil.which("codex")).resolve(),
        }
        for path in ROOT.rglob("*"):
            if not path.is_symlink():
                continue
            resolved = path.resolve()
            read_only_codex_engine = (
                str(resolved).startswith(
                    "/data/data/com.termux/files/usr/lib/node_modules/@openai/codex-"
                )
                and str(resolved).endswith("/bin/codex")
            )
            self.assertTrue(
                str(resolved).startswith(str(ROOT) + "/")
                or resolved in allowed
                or read_only_codex_engine
            )

    def test_goal_and_slash_commands_are_real_runtime_features(self):
        gateway = (ROOT / "vendor/codexapp-frontier-src/src/api/codexGateway.ts").read_text()
        composer = (ROOT / "vendor/codexapp-frontier-src/src/components/content/ThreadComposer.vue").read_text()
        for method in ("thread/goal/get", "thread/goal/set", "thread/goal/clear"):
            self.assertIn(method, gateway)
        for command in ("/goal", "/plan", "/compact", "/fork", "/skills", "/plugins", "/apps", "/mcp", "/status"):
            self.assertIn(command, composer)

    def test_model_and_effort_selection_is_exact_and_fail_closed(self):
        gateway = (ROOT / "vendor/codexapp-frontier-src/src/api/codexGateway.ts").read_text()
        state = (ROOT / "vendor/codexapp-frontier-src/src/composables/useDesktopState.ts").read_text()
        server = (ROOT / "vendor/codexapp-frontier-src/src/server/codexAppServerBridge.ts").read_text()
        identity = (ROOT / "vendor/codexapp-frontier-src/src/runtimeIdentity.ts").read_text()
        self.assertIn("params.config = { model_reasoning_effort: effort }", gateway)
        self.assertIn("Codex accepted ${acceptedModel", gateway)
        self.assertIn("recordRequestedTurnSelection", state)
        self.assertIn("verifyAcceptedTurnSelection", state)
        self.assertNotIn("retryPendingTurnWithFallback", state)
        self.assertIn("params.model = settings.model", server)
        self.assertIn("params.effort = settings.reasoningEffort", server)
        self.assertIn("buildRuntimeIdentityDeveloperInstructions", gateway)
        self.assertIn("buildRuntimeIdentityDeveloperInstructions", server)
        self.assertIn("withAuthoritativeRuntimeIdentity", server)
        self.assertIn("supersedes every conflicting identity claim", identity)
        self.assertIn("Never infer identity from conversation history", identity)

    def test_boot_watchdog_is_declared_and_headless(self):
        manifest = (ROOT / "AndroidManifest.xml").read_text()
        watchdog = (ROOT / "src/com/michaelovsky/codexsubscription/isolated/RuntimeWatchdogService.java").read_text()
        self.assertIn("android.intent.action.BOOT_COMPLETED", manifest)
        self.assertIn("RuntimeWatchdogService", manifest)
        self.assertIn("START_STICKY", watchdog)
        self.assertNotIn("startActivity", watchdog)

    def test_refresh_reconnect_and_renderer_recovery_are_permanent_contracts(self):
        activity = (ROOT / "src/com/michaelovsky/codexsubscription/isolated/MainActivity.java").read_text()
        rpc = (ROOT / "vendor/codexapp-frontier-src/src/api/codexRpcClient.ts").read_text()
        app = (ROOT / "vendor/codexapp-frontier-src/src/App.vue").read_text()
        conversation = (ROOT / "vendor/codexapp-frontier-src/src/components/content/ThreadConversation.vue").read_text()
        for native_contract in (
            "PAGE_LOAD_TIMEOUT_MS",
            "pull-to-refresh",
            "onReceivedHttpError",
            "onRenderProcessGone",
            "renderer-process-gone",
            "page-load-timeout",
        ):
            self.assertIn(native_contract, activity)
        self.assertIn("RETRYABLE_RPC_STATUS", rpc)
        self.assertIn("isRetryableRpcMethod", rpc)
        self.assertIn("X-Codex-Retry-Attempt", rpc)
        self.assertIn("codex-connection-state", rpc)
        self.assertIn("content-header-connection", app)
        self.assertNotIn("window.location.reload()", app)
        self.assertIn("restartNotificationStream", app)
        self.assertIn("forceThreadRefresh: true", app)
        self.assertIn("codex-frontier-soft-refresh", app)
        self.assertIn("codex-frontier-soft-refresh", activity)
        self.assertNotIn("webView.reload()", activity)
        self.assertIn("AbortSignal.timeout", rpc)
        self.assertIn("BRIDGE_READ_TIMEOUT_MS", rpc)
        self.assertIn("BRIDGE_WRITE_TIMEOUT_MS", rpc)
        self.assertIn("WEBSOCKET_FALLBACK_AFTER_ATTEMPTS", rpc)
        self.assertIn("BACKGROUND_STATUS_RECONCILE_MS", (ROOT / "vendor/codexapp-frontier-src/src/composables/useDesktopState.ts").read_text())
        self.assertNotIn("animation: frontier-connection-pulse", app)
        self.assertIn("MOBILE_RESUME_RELOAD_MIN_HIDDEN_MS = 5_000", app)
        self.assertIn("-webkit-overflow-scrolling: touch", conversation)

    def test_webview_is_revealed_only_after_a_stable_visual_frame(self):
        activity = (ROOT / "src/com/michaelovsky/codexsubscription/isolated/MainActivity.java").read_text()
        self.assertIn("FrameLayout rootContainer", activity)
        self.assertIn("TextView loadingOverlay", activity)
        self.assertIn("postVisualStateCallback", activity)
        self.assertIn("onPageCommitVisible", activity)
        self.assertIn("recoveryScheduled", activity)
        self.assertIn("disposeWebView(view)", activity)
        self.assertIn("rootContainer.removeView(view)", activity)
        self.assertIn("view.destroy()", activity)
        self.assertNotIn("loadDataWithBaseURL", activity)
        self.assertNotIn("Restoring Codex Frontier…", activity)

    def test_concurrency_remains_isolated_per_thread(self):
        state = (ROOT / "vendor/codexapp-frontier-src/src/composables/useDesktopState.ts").read_text()
        bridge = (ROOT / "vendor/codexapp-frontier-src/src/server/codexAppServerBridge.ts").read_text()
        self.assertIn("queueProcessingByThreadId", state)
        self.assertIn("queueDrainTimersByThreadId", bridge)
        self.assertIn("queueDrainDueAtByThreadId", bridge)

    def test_transport_and_hydration_have_independent_recovery_guards(self):
        rpc = (ROOT / "vendor/codexapp-frontier-src/src/api/codexRpcClient.ts").read_text()
        server = (ROOT / "vendor/codexapp-frontier-src/src/server/httpServer.ts").read_text()
        bridge = (ROOT / "vendor/codexapp-frontier-src/src/server/codexAppServerBridge.ts").read_text()
        state = (ROOT / "vendor/codexapp-frontier-src/src/composables/useDesktopState.ts").read_text()
        app = (ROOT / "vendor/codexapp-frontier-src/src/App.vue").read_text()
        self.assertIn("AbortSignal.timeout", rpc)
        self.assertIn("WEBSOCKET_FALLBACK_AFTER_ATTEMPTS", rpc)
        self.assertIn("client.ping()", server)
        self.assertIn("client.terminate()", server)
        self.assertIn("ws.on('pong'", server)
        self.assertIn("Codex app-server request timed out", bridge)
        self.assertIn("const writeEvent = (payload: string): boolean", bridge)
        self.assertIn("if (closed) return", bridge)
        self.assertIn("CODEX_DEFAULT_MODEL_ID = 'gpt-5.6-sol'", state)
        self.assertIn("BACKGROUND_STATUS_RECONCILE_MS", state)
        self.assertIn("restartNotificationStream", state)
        self.assertIn("forceThreadRefresh: true", app)
        self.assertNotIn("window.location.reload()", app)

    def test_terminal_turn_notifications_are_native_sound_and_deduplicated(self):
        watchdog = (ROOT / "src/com/michaelovsky/codexsubscription/isolated/RuntimeWatchdogService.java").read_text()
        contract = (ROOT / "src/com/michaelovsky/codexsubscription/isolated/RuntimeContract.java").read_text()
        bridge = (ROOT / "vendor/codexapp-frontier-src/src/server/codexAppServerBridge.ts").read_text()
        store = (ROOT / "vendor/codexapp-frontier-src/src/server/frontierCompletionEvents.ts").read_text()
        self.assertIn("codex_frontier_turn_complete_v1", watchdog)
        self.assertIn("RingtoneManager.TYPE_NOTIFICATION", watchdog)
        self.assertIn("lastCompletionSequence", watchdog)
        self.assertIn("frontier-completion-events", contract)
        self.assertIn("frontier-completion-events", bridge)
        self.assertIn("turn/completed", store)

    def test_safe_bulk_session_cleanup_is_confirmed_and_preserves_projects(self):
        app = (ROOT / "vendor/codexapp-frontier-src/src/App.vue").read_text()
        gateway = (ROOT / "vendor/codexapp-frontier-src/src/api/codexGateway.ts").read_text()
        bridge = (ROOT / "vendor/codexapp-frontier-src/src/server/codexAppServerBridge.ts").read_text()
        purge = (ROOT / "vendor/codexapp-frontier-src/src/server/sessionPurge.ts").read_text()
        self.assertIn("Delete all sessions and threads", app)
        self.assertIn("DELETE ALL SESSIONS", app)
        self.assertIn("/codex-api/threads/delete-all", gateway)
        self.assertIn("purgeAllSessionsAndThreads", bridge)
        for preserved in ("plugins and skills", "authentication and accounts", "models and settings", "project directories and files"):
            self.assertIn(preserved, purge)
        self.assertNotIn("project-automations", purge)

    def test_imported_pins_receive_fully_isolated_identity_and_cwd_metadata(self):
        bridge = (ROOT / "vendor/codexapp-frontier-src/src/server/codexAppServerBridge.ts").read_text()
        self.assertIn("rewriteImportedStructuredCwd", bridge)
        self.assertIn("payload.session_id = importedThreadId", bridge)
        self.assertIn("payload.imported_forked_from_id = payload.forked_from_id", bridge)
        self.assertIn("registerImportedSessionsInStateDb(importedSessionRecords)", bridge)

    def test_startup_recovers_only_verified_frontier_process_group(self):
        launcher = (ROOT / "codex-frontier-start.sh").read_text()
        self.assertIn("terminate_owned_runtime", launcher)
        self.assertIn('process_group" != "$pid_value', launcher)
        self.assertIn('session_id" != "$pid_value', launcher)
        self.assertIn('kill -TERM -- "-$pid_value"', launcher)


if __name__ == "__main__":
    unittest.main()
