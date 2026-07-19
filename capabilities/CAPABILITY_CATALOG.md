# Codex Frontier Capability Catalog

The isolated app prepends `bin/` to `PATH` and stores command state under `runtime/.codex`. The command runtime is an independent project-owned copy; Shizuku bridge files are also copied beneath the isolated HOME.

## Codex desktop parity

- Project-local Codex CLI 0.144.6 with native ChatGPT subscription authentication and live web search
- Live GPT-5.6 Sol/Terra/Luna model catalog, Sol default, Ultra reasoning, model switching, and fast mode
- Durable goal RPCs and UI: `/goal`, view, edit, pause, resume, clear, status, token/time progress, and first-turn goal creation
- Slash commands: `/plan`, `/fast`, `/compact`, `/fork`, `/new`, `/skills`, `/plugins`, `/apps`, `/mcp`, `/automations`, `/model`, `/status`, `/review`, `/permissions`
- Stable Codex capabilities enabled: goals, multi-agent, apps, plugins, hooks, browser/computer use, image generation, shell tools, unified execution, workspace dependencies, MCP elicitation, and remote compaction
- Files, folders, photos, camera, voice dictation, terminal panels, reviews, skills/prompts, connected apps, MCP servers, plugin hub, and automations
- Headless boot/runtime watchdog with exclusive launch locking and exact PID/port ownership
- Reboot-persistent native completion alerts with one deduplicated Android notification ringtone per terminal turn

## Android and apps

- `codex-android capabilities`: verifies the direct Shizuku/UI Automator backend and lists the complete semantic/raw/device-API surface
- `codex-android index-apps|resolve|open|focus|wait-package`: local APK launcher-label indexing, fuzzy label/package resolution, launcher-component discovery, bounded launch fallbacks, and foreground readback
- `codex-android elements|find|wait-element|wait-stable`: temporary-file-clean hierarchy capture and semantic targeting by text, description, resource-id, class, package, state, regex, and match index
- `codex-android tap-element|longtap-element|type-into|scroll|sequence`: selector-based action, Unicode clipboard fallback, display-relative gestures, postcondition checks, and bounded JSON workflows
- `codex-android screenshot`: stores a hash-verified PNG beneath isolated runtime evidence by default and removes shared staging
- `codex-android tap|swipe|text|key|back|home|recents|notifications|quick-settings|url|settings|shell`: raw fallback controls with protected-package guards
- `codex-app`, `codex-action`, `codex-ui`, `codex-browser`: app adapters, normalized actions, UI goals, and browser automation
- `codex-pm`, `codex-package`, `codex-install`, `codex-uninstall`: package inspection, silent installation, guarded removal, and read-back verification
- `codex-privilege`, `codex-shizuku`: Shizuku/rish privilege status and shell routing
- `codex-media`, `codex-notification`: media sessions/actions and notification inspection/actions
- 57 project-local `termux-*` commands: battery/audio, clipboard, contacts/call log, camera, location, sensors, notifications, media/microphone, NFC, SAF storage, SMS/telephony, speech/TTS, torch, vibration, volume, wallpaper, Wi-Fi, and related Android APIs

### Semantic Android examples

- `codex-android resolve "YouTube Music"`
- `codex-android index-apps --refresh`
- `codex-android open "YouTube Music" --timeout 20`
- `codex-android find --desc-contains "Search" --clickable true`
- `codex-android tap-element --text "Continue" --after-text "Done"`
- `codex-android type-into --class android.widget.EditText --value "query" --clear --submit`
- `codex-android wait-stable --stable-for 1 --timeout 15`
- `termux-battery-status`
- `termux-location -p gps -r once`

## Internet and acquisition

- `codex-search`, `codex-source`, `codex-fetch`: headless search, source selection, and page/API reading
- `codex-download`, `codex-acquire`, `codex-update`: resumable acquisition, provenance, hashes, and updates
- `codex-open-url`: visible URL opening only when requested
- `codex-network`, `codex-net`, `codex-protocol`: connectivity and protocol diagnostics

## Files, verification, and recovery

- `codex-fs`, `codex-delete`, `codex-restore`: guarded filesystem operations
- `codex-artifact`, `codex-capability`, `codex-verify`: provenance, registration, and independent verification
- `codex-recover`, `codex-audit`, `codex-undo`, `codex-health`: bounded recovery and evidence

## Agent continuity and information

- `codex-job`, `codex-goal`, `codex-schedule`: durable multi-step work
- `codex-memory`, `codex-learn`, `codex-lessons`: isolated persistent lessons and memory
- `codex-account`, `codex-entitlement`: official account and entitlement inspection
- `codex-ocr`, `codex-speech`: visual text and speech workflows
- `codex-win`: signed Tailscale Windows automation gateway with bounded health retries and latency evidence
- `codex-github status|gh|git`: GitHub and Git delegated to the authenticated Windows account without copying credentials to Android; credential-exporting commands are blocked and token patterns are redacted
- Native Codex memory generation/recall plus `codex-learn`/`codex-lessons`: cross-session learning with explicit secret-exclusion rules
- Protected external project references for the requested Codex subscription and NVIDIA folders; visible in the project list and read-only by default
- Native and web refresh: pull down at the top of the Android workspace or tap the live Online/Reconnecting refresh control; both preserve server-side thread state
- Bounded WebView recovery: main-frame timeout, HTTP 5xx recovery, renderer-process recreation, and watchdog-assisted cold startup
- Resilient transport: idempotent read RPCs recover from transient network/429/502/503/504 failures, while state-changing requests are never automatically replayed
- Mobile presentation polish: readable 15px+ response typography, touch-scrolling code/tables, distinct inline code, and responsive headings

Capabilities are exercised only for user-authorized tasks. Package-manager and deletion operations retain protected-package/path guards.
