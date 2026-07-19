# Codex Frontier 2.0 research record

Research was performed headlessly before implementation. The resulting defaults deliberately use supported platform behavior instead of UI-launch workarounds.

## Codex

- OpenAI's Codex long-running work documentation defines durable goals with view, edit, pause, resume, and clear behavior; goal text is applied before the first turn and does not broaden permissions: <https://learn.chatgpt.com/docs/long-running-work>
- The current model guide identifies the GPT-5.6 Sol/Terra/Luna family and the reasoning defaults used by Codex: <https://learn.chatgpt.com/docs/models>
- Plugins package skills, apps, and MCP servers into installable capabilities: <https://learn.chatgpt.com/docs/plugins>
- MCP is the supported protocol for extending Codex with external tools and context: <https://learn.chatgpt.com/docs/extend/mcp>
- CodexApp source and its current source-release history were inspected from: <https://github.com/friuns2/codexui>

## Android and Termux

- `BOOT_COMPLETED` remains an exempt implicit broadcast suitable for boot recovery: <https://developer.android.com/develop/background-work/background-tasks/broadcasts/broadcast-exceptions>
- Android foreground-service launch restrictions and boot rules informed the dedicated watchdog service: <https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start>
- The uncategorized `specialUse` foreground-service type is the supported fit for this local runtime watchdog: <https://developer.android.com/develop/background-work/services/fgs/service-types>
- Foreground services must publish a notification, while denial of notification permission does not prevent service launch: <https://developer.android.com/develop/ui/compose/notifications/notification-permission>
- Termux `RUN_COMMAND` supports background execution with a result `PendingIntent`; Frontier uses that interface without opening Termux or the app activity: <https://github.com/termux/termux-app/wiki/RUN_COMMAND-Intent>

## Applied decisions

- Separate Android package, WebView data, source tree, signing material, port, HOME, CODEX_HOME, auth snapshot, databases, workspace, logs, skills, and plugins.
- Project-local Codex CLI 0.144.6 and current provenance-recorded CodexApp source build.
- Headless boot receiver and sticky foreground watchdog; exact port/PID ownership and serialized startup.
- Real `thread/goal/*` RPC integration and desktop-oriented slash commands in the composer.
- Supported stable capabilities enabled explicitly; unsafe or under-development feature flags remain disabled.
