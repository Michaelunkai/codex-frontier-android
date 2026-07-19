# Codex Frontier for Android

Codex Frontier is an isolated Android workspace for the native OpenAI Codex app-server. It combines a polished mobile chat interface, exact model/reasoning selection, durable goals, plugins and skills, Android automation tools, a reboot-safe local supervisor, and independent project/session storage.

![Codex Frontier icon](artwork/codex-frontier-icon-master.png)

## Release

- Android package: `com.michaelovsky.codexsubscription.isolated`
- Version: `2.6.0` (`versionCode 9`)
- Local UI: `http://127.0.0.1:5902`
- APK: `Codex-Frontier-2.6.0.apk` in the GitHub release
- APK SHA-256: `380f7fc9e99d76ad7d3134d9890e3b9ce8192590c0848532a3190ae2eda664bf`
- Signing certificate SHA-256: `4d735fd7eecdc74492fab715b49c5879c250162aed3553dc13c09394b5d72a66`

## What 2.6 fixes

The Android shell now keeps a stable native launch surface while Chromium loads. The WebView is revealed only after Android confirms a drawable visual frame. Duplicate load errors are coalesced into one recovery, dead renderers are removed and destroyed before recreation, reconnect status no longer pulses continuously, and brief mobile focus changes no longer trigger heavy synchronization.

The result is a cold-start path without white flashes or overlapping reload loops, while retaining pull-to-refresh, a visible refresh control, bounded page-load recovery, HTTP 5xx recovery, renderer recovery, and a persistent foreground watchdog.

## Capabilities

- Native ChatGPT-subscription authentication through the official Codex CLI
- Live authenticated model catalog with model-specific reasoning levels
- Exact model/effort frozen at Send and verified from app-server responses
- Per-thread queues and concurrent-session isolation
- Durable `/goal`, `/plan`, `/compact`, `/fork`, `/skills`, `/plugins`, `/apps`, `/mcp`, `/status`, and related controls
- Markdown, syntax-highlighted code, tables, attachments, terminals, review, projects, and automations
- Boot receiver plus a `START_STICKY` foreground watchdog
- Native completion notifications with sound and deduplication
- Manual and pull-to-refresh with bounded read-only RPC retry
- Separate Android package, WebView data, HOME, CODEX_HOME, port, workspace, and sessions

## Important installation boundary

The release APK is a real signed Android package, but it is the secure Android shell—not a bundled OpenAI account or a bundled Termux/Linux environment. Android sandboxing and OpenAI authentication prevent any legitimate APK from silently installing Termux, granting cross-app permissions, or embedding another person's ChatGPT credentials.

Accordingly, a new device needs Termux, the project runtime under the expected Termux home path, one-time `RUN_COMMAND` permission, and the owner's own Codex login. No credentials, sessions, vaults, signing keys, or device databases are included in this repository. See [INSTALL.md](INSTALL.md).

## Source layout

- `src/`, `res/`, `AndroidManifest.xml` — native launcher, stable loading surface, watchdog, boot receiver, and icon
- `vendor/codexapp-frontier-src/` — modified CodexApp web/server source
- `vendor/codex-cli-frontier/` — pinned Codex CLI package metadata and provenance
- `runtime-template/` — credential-free runtime defaults
- `tests/` — isolation, lifecycle, selection, concurrency, and capability contracts
- `build-codex-frontier.sh` — deterministic raw Android build
- `isolation-preflight.sh` and `verify-codex-frontier.sh` — non-UI safety verification

## Verification performed for 2.6.0

- 33 Python/source contract tests passed
- 167 frontend unit tests passed
- Vue TypeScript and production frontend/CLI builds passed
- APK v1/v2/v3 signature verification passed
- 48 concurrent local RPC reads passed with 12 workers
- Simulated package-targeted `BOOT_COMPLETED` restored the runtime in five seconds
- Boot verification created zero `MainActivity` records
- Protected sibling Android packages remained byte-for-byte unchanged

## Security and privacy

This repository intentionally excludes authentication snapshots, account files, runtime databases, sessions, memories, logs, vaults, private workspaces, Android signing keys, and local device evidence. Read [SECURITY.md](SECURITY.md) before publishing forks or diagnostic bundles.

The web interface is based on the MIT-licensed [codexui](https://github.com/friuns2/codexui) project. OpenAI Codex remains subject to OpenAI's terms and the user's own account entitlements.

