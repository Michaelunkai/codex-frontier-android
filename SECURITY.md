# Security policy

## Never commit

- `runtime/` or any `.codex` account/session state
- `auth.json`, `accounts.json`, tokens, cookies, or API keys
- SQLite databases, logs, memories, vaults, or imported transcripts
- `workspace/` user projects
- `build/` signing keys or signing properties
- Android package dumps, device paths, or private verification evidence

The repository `.gitignore` blocks these paths. Run a secret scanner before every publication and inspect the staged file list manually.

## Reporting

Use GitHub's private security-advisory flow for vulnerabilities that could expose authentication, cross the package boundary, execute an unintended command, or let a remote origin access the localhost runtime.

## Trust boundary

The WebView accepts its application from `127.0.0.1:5902`. External HTTP(S) navigation is delegated to Android rather than loaded into the privileged WebView. Runtime recovery can stop only an exact Frontier-owned process group. State-changing RPC calls are never automatically replayed.

