#!/data/data/com.termux/files/usr/bin/bash
set -eu

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
EXPECTED_ROOT="/data/data/com.termux/files/home/codex-subscription-isolated-app"
CODEX_PACKAGE="com.michaelovsky.codexsubscription.isolated"
ORIGINAL_PACKAGE="com.michaelovsky.codexapplauncher"
NVIDIA_PACKAGE="com.michaelovsky.codexnvidia.isolated"
GUI_PORT="5902"
ORIGINAL_GUI_PORT="5900"
NVIDIA_GUI_PORT="5901"
MODEL="gpt-5.6-sol"
LOCAL_CODEX="$PROJECT_ROOT/vendor/codex-cli-frontier/node_modules/.bin/codex"
CODEX_ENGINE="$(readlink -f -- "$LOCAL_CODEX")"

fail() {
  printf 'ISOLATION_PREFLIGHT_FAILED: %s\n' "$1" >&2
  exit 78
}

[ "$PROJECT_ROOT" = "$EXPECTED_ROOT" ] || fail "unexpected project root"
[ "$CODEX_PACKAGE" != "$ORIGINAL_PACKAGE" ] || fail "original package collision"
[ "$CODEX_PACKAGE" != "$NVIDIA_PACKAGE" ] || fail "NVIDIA package collision"
[ "$GUI_PORT" != "$ORIGINAL_GUI_PORT" ] || fail "original GUI port collision"
[ "$GUI_PORT" != "$NVIDIA_GUI_PORT" ] || fail "NVIDIA GUI port collision"

grep -Fq "package=\"$CODEX_PACKAGE\"" "$PROJECT_ROOT/AndroidManifest.xml" || fail "wrong Android package"
grep -Fq "APP_HOME = \"$EXPECTED_ROOT\"" "$PROJECT_ROOT/src/com/michaelovsky/codexsubscription/isolated/RuntimeContract.java" || fail "wrong application root"
grep -Fq 'START_SCRIPT = APP_HOME + "/codex-frontier-start.sh"' "$PROJECT_ROOT/src/com/michaelovsky/codexsubscription/isolated/RuntimeContract.java" || fail "wrong launcher path"
grep -Fq 'RUN_COMMAND_WORKDIR", APP_HOME' "$PROJECT_ROOT/src/com/michaelovsky/codexsubscription/isolated/RuntimeContract.java" || fail "wrong launcher workdir"
grep -Fq "PORT=$GUI_PORT" "$PROJECT_ROOT/codex-frontier-start.sh" || fail "wrong GUI port"
grep -Fq 'HOME="$ISOLATED_HOME"' "$PROJECT_ROOT/codex-frontier-start.sh" || fail "HOME is not isolated"
grep -Fq 'CODEX_HOME="$ISOLATED_CODEX_ROOT"' "$PROJECT_ROOT/codex-frontier-start.sh" || fail "CODEX_HOME is not isolated"
grep -Fq 'PATH="$APP_HOME/bin:$LOCAL_CODEX_BIN:' "$PROJECT_ROOT/codex-frontier-start.sh" || fail "project commands and Codex CLI are not first in PATH"
grep -Fq 'RUNTIME_ENTRY="$APP_HOME/vendor/codexapp-frontier-src/dist-cli/index.js"' "$PROJECT_ROOT/codex-frontier-start.sh" || fail "web runtime is not the Frontier-owned build"
grep -Fq "model = \"$MODEL\"" "$PROJECT_ROOT/runtime/.codex/config.toml" || fail "wrong default model"
grep -Fq 'model_reasoning_effort = "ultra"' "$PROJECT_ROOT/runtime/.codex/config.toml" || fail "wrong reasoning default"

test -s "$PROJECT_ROOT/runtime/.codex/auth.json" || fail "subscription snapshot is missing"
test -s "$PROJECT_ROOT/runtime/.codex/models_cache.json" || fail "subscription model cache is missing"
test ! -e "$PROJECT_ROOT/runtime/.codex/webui-custom-providers.json" || fail "custom provider state is forbidden"
test ! -e "$PROJECT_ROOT/runtime-template/.codex/webui-custom-providers.json" || fail "custom provider template is forbidden"
if grep -Fq 'model_provider' "$PROJECT_ROOT/runtime/.codex/config.toml" "$PROJECT_ROOT/runtime-template/.codex/config.toml"; then
  fail "custom model provider is forbidden"
fi

python - "$PROJECT_ROOT/runtime/.codex/auth.json" "$PROJECT_ROOT/runtime/.codex/models_cache.json" <<'PY' || exit 78
import json
import sys
auth = json.load(open(sys.argv[1], encoding="utf-8"))
assert auth.get("auth_mode") == "chatgpt"
assert isinstance(auth.get("tokens"), dict) and auth["tokens"]
assert not auth.get("OPENAI_API_KEY")
models = json.load(open(sys.argv[2], encoding="utf-8")).get("models", [])
ids = {item.get("slug") for item in models if isinstance(item, dict)}
assert "gpt-5.6-sol" in ids
PY

test -s "$PROJECT_ROOT/vendor/codexapp-frontier-src/dist-cli/index.js" || fail "project web runtime is missing"
test -x "$LOCAL_CODEX" || fail "project-local Codex CLI is missing"
test "$(HOME="$PROJECT_ROOT/runtime/home" CODEX_HOME="$PROJECT_ROOT/runtime/.codex" "$LOCAL_CODEX" --version)" = "codex-cli 0.144.6" || fail "wrong project-local Codex CLI version"
test -x "$PROJECT_ROOT/build-codex-frontier.sh" || fail "build script is missing"
test -x "$PROJECT_ROOT/vendor/termux-api-client/build-project-client.sh" || fail "Termux API builder is missing"
test -x "$PROJECT_ROOT/vendor/termux-api-client/runtime/libexec/termux-api-broadcast" || fail "Termux API client is missing"
test "$(find "$PROJECT_ROOT/bin" -maxdepth 1 -type l -name 'termux-*' | wc -l)" -eq 57 || fail "Termux API command set is incomplete"

for file in \
  "$PROJECT_ROOT/AndroidManifest.xml" \
  "$PROJECT_ROOT/codex-frontier-start.sh" \
  "$PROJECT_ROOT/build-codex-frontier.sh" \
  "$PROJECT_ROOT/src/com/michaelovsky/codexsubscription/isolated/MainActivity.java"; do
  if grep -Eq 'nvidia-isolated-app|codexnvidia|nemotron|18769|model_provider|customBaseUrl|/files/home/\.codex' "$file"; then
    fail "foreign provider or state reference in $file"
  fi
done

while IFS= read -r link; do
  resolved="$(readlink -f -- "$link")"
  case "$resolved" in
    "$PROJECT_ROOT"/*|"$CODEX_ENGINE"|/data/data/com.termux/files/usr/lib/node_modules/@openai/codex-*/vendor/*/bin/codex|/data/data/com.termux/files/usr/bin/am|/data/data/com.termux/files/usr/bin/bash|/data/data/com.termux/files/usr/bin/dash|/data/data/com.termux/files/usr/bin/sh) ;;
    *) fail "external symlink: $link -> $resolved" ;;
  esac
done < <(find "$PROJECT_ROOT" -type l -print)

printf 'ISOLATION_PREFLIGHT_OK\n'
