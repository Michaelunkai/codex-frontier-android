# Installation

## Existing configured device

Download `Codex-Frontier-2.7.0.apk` from the GitHub release, verify its SHA-256 is `3fbed12dc34015d25ea49e4480adf0e854aaec7da42cedc5b0b16c006bf0dd56`, and install it as an update. The package signature is unchanged from earlier Frontier builds.

The update does not launch the app during installation. On the next icon tap, the native loading surface waits for the isolated runtime and reveals the UI only after a stable visual frame is ready.

## New Android device

Codex Frontier uses a Termux-hosted Node/Codex runtime. A new device therefore requires:

1. Android 6.0 or newer.
2. Termux and Termux:API from the same trusted distribution/signing source.
3. Termux packages: `nodejs`, `openjdk-21`, `aapt`, `apksigner`, `d8`, `curl`, and `git`.
4. This repository cloned exactly to `$HOME/codex-subscription-isolated-app`.
5. `npm ci` and `npm run build` inside `vendor/codexapp-frontier-src`.
6. `npm ci` inside `vendor/codex-cli-frontier`, plus the official `@openai/codex@0.144.6-linux-arm64` optional package when npm omits it on Android.
7. A one-time Codex login performed with this project's isolated `CODEX_HOME`.
8. A one-time Android grant for `com.termux.permission.RUN_COMMAND`.
9. Installation of the signed release APK.

The user's login is created locally and is never part of the repository or APK. Android may show first-install permission or package-installer confirmation; those system security prompts cannot and should not be bypassed. After setup, reboot recovery is headless and does not open the app or Termux.

## Build from source

The raw build expects an Android platform `android.jar` at `build-tools/android.jar` and local signing material under `build/`. Those files are intentionally excluded. Create your own keystore and `build/signing.properties`, then run:

```sh
npm --prefix vendor/codexapp-frontier-src ci
npm --prefix vendor/codexapp-frontier-src run build
./build-codex-frontier.sh
```

Changing the signing key prevents in-place updates over the official Frontier APK, which is normal Android signature enforcement.

## Runtime start

The installed package requests Termux to execute `codex-frontier-start.sh` in the background. The script:

- runs the isolation preflight;
- validates the isolated auth/config state;
- serializes startup with a lock;
- reuses a healthy port 5902 runtime;
- restarts only a PID whose exact command line, process group, and session belong to this project;
- never opens an Android activity or browser.
