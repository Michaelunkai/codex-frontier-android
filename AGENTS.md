# Codex Frontier Isolation Contract

This repository belongs only to the independent Codex Frontier Android application.

## Fixed boundaries

- Project root: `/data/data/com.termux/files/home/codex-subscription-isolated-app`
- Android package: `com.michaelovsky.codexsubscription.isolated`
- GUI port: `5902`
- Provider: native OpenAI Codex through a ChatGPT subscription session
- Default model: `gpt-5.6-sol`; the UI may select any model returned by the authenticated Codex catalog
- Original app: `com.michaelovsky.codexapplauncher`, port `5900` — never modify, reinstall, uninstall, clear, force-stop, or reconfigure it
- NVIDIA app: `com.michaelovsky.codexnvidia.isolated`, port `5901` — never modify, reinstall, uninstall, clear, force-stop, or reconfigure it

All writable HOME, CODEX_HOME, workspace, sessions, memories, logs, plugins, skills, models, build output, APKs, and signing material must remain below this repository. Shared Termux, Node, Java, Android SDK, Shizuku, and Codex executables may be invoked as read-only dependencies but must never be patched by this project.

The active web runtime is `vendor/codexapp-frontier-src/dist-cli/index.js`. The active Codex executable is the project-local `vendor/codex-cli-frontier/node_modules/.bin/codex` at version 0.144.6. Never replace it with, update, or configure the shared global Codex installation.

The subscription credential is an independent file snapshot at `runtime/.codex/auth.json`. It may refresh only that file. Never symlink it, replace the original `$HOME/.codex/auth.json`, create an API key, or enable a custom provider endpoint. Model availability is determined by the live authenticated Codex model catalog, not an API catalog.

Skills and plugins may be imported only as validated, one-way copies. Never share writable directories, bind-mount, symlink, mirror with deletion, or overwrite an existing destination. Provider config, authentication, databases, sessions, memories, vault data, logs, launchers, APKs, signing material, and app source are never eligible for exchange.

For every future change:

1. Run `./isolation-preflight.sh`.
2. Record hashes and HTTP health for both protected apps without stopping them.
3. Keep package ID, port, HOME, CODEX_HOME, and workspace isolated.
4. Build and install only `com.michaelovsky.codexsubscription.isolated`.
5. If this project runtime must be restarted, target only a PID whose full command line contains this exact project root or port 5902; never use a broad process pattern.
6. Keep `RuntimeWatchdogService`, `BootReceiver`, and `codex-frontier-start.sh` headless; never launch `MainActivity` as a build or verification step.
7. Preserve durable `/goal` RPC support and the source-level slash-command tests.
8. Run `./verify-codex-frontier.sh` without opening the Android UI.
9. Recheck both protected APK hashes, running processes, and ports.

If any boundary cannot be proven, stop without applying or installing the change.
