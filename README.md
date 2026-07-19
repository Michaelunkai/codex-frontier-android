# Codex Frontier for Android

Codex Frontier is an isolated Android workspace for the native OpenAI Codex app-server. It combines a polished mobile chat interface, exact model/reasoning selection, durable goals, plugins and skills, Android automation tools, a reboot-safe local supervisor, and independent project/session storage.

![Codex Frontier icon](artwork/codex-frontier-icon-master.png)

## Release

- Android package: `com.michaelovsky.codexsubscription.isolated`
- Version: `2.8.0` (`versionCode 11`)
- Local UI: `http://127.0.0.1:5902`
- APK: `Codex-Frontier-2.8.0.apk` in the GitHub release
- APK SHA-256: `3fbed12dc34015d25ea49e4480adf0e854aaec7da42cedc5b0b16c006bf0dd56`
- Signing certificate SHA-256: `4d735fd7eecdc74492fab715b49c5879c250162aed3553dc13c09394b5d72a66`

## What 2.7 fixes

The connection control now performs a state-preserving soft recovery instead of reloading the entire page. Local RPC requests have bounded timeouts, the notification WebSocket has server-side ping/pong health checks and automatic SSE fallback, and visible sessions reconcile with the app-server every eight seconds so a missed stream event cannot strand a running turn. New-thread model and effort controls render immediately from durable defaults while live metadata hydrates.

Transient upstream reconnect progress remains visible without being rendered as a permanent red failure. The 2.6 stable native loading surface, visual-frame gating, renderer recovery, and reboot watchdog remain intact.

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

## Verification performed for 2.8.0

- Native and header refreshes preserve the active route, thread, and composer instead of reloading the WebView.
- Startup metadata and pending-request calls have bounded read/write deadlines.
- WebSocket heartbeat, SSE fallback, and race-safe SSE cleanup recover transport failures in place.

- 34 Python/source contract tests passed
- 167 frontend unit tests passed
- Vue TypeScript and production frontend/CLI builds passed
- APK v1/v2/v3 signature verification passed
- WebSocket remained healthy across heartbeat, SSE emitted ready, and 32 concurrent RPC reads passed
- Simulated package-targeted `BOOT_COMPLETED` restored the runtime in seven polling attempts
- Five repeated boot broadcasts remained idempotent with one unchanged runtime PID
- Boot verification created zero `MainActivity` records
- Protected sibling Android packages remained byte-for-byte unchanged

## Security and privacy

This repository intentionally excludes authentication snapshots, account files, runtime databases, sessions, memories, logs, vaults, private workspaces, Android signing keys, and local device evidence. Read [SECURITY.md](SECURITY.md) before publishing forks or diagnostic bundles.

The web interface is based on the MIT-licensed [codexui](https://github.com/friuns2/codexui) project. OpenAI Codex remains subject to OpenAI's terms and the user's own account entitlements.
