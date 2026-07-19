#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
CODEX_HOME_DIR="$PROJECT_ROOT/runtime/.codex"
ISOLATED_HOME="$PROJECT_ROOT/runtime/home"
APK="$PROJECT_ROOT/dist/Codex-Frontier-2.6.0.apk"
HASH_FILE="$APK.sha256"
PROTECTED_BASELINE="$PROJECT_ROOT/isolation/protected-preinstall-baseline.json"
SELECTION_EVIDENCE="$PROJECT_ROOT/isolation/headless-selection-verification.json"
RISH="/data/data/com.termux/files/home/.local/bin/rish"
ORIGINAL_PACKAGE="com.michaelovsky.codexapplauncher"
NVIDIA_PACKAGE="com.michaelovsky.codexnvidia.isolated"
CODEX_PACKAGE="com.michaelovsky.codexsubscription.isolated"

"$PROJECT_ROOT/isolation-preflight.sh"
test -f "$APK"
test -f "$HASH_FILE"
test -f "$PROTECTED_BASELINE"
test -f "$SELECTION_EVIDENCE"
test -f "$PROJECT_ROOT/isolation/pinned-thread-import-verification.json"
test -f "$PROJECT_ROOT/models/subscription-models.json"
test -f "$PROJECT_ROOT/workspace/AGENTS.md"
test -f "$CODEX_HOME_DIR/skills/codex-frontier-current-setup/SKILL.md"
test -x "$PROJECT_ROOT/build-codex-frontier.sh"
test -x "$PROJECT_ROOT/sync-capabilities.sh"
test -x "$PROJECT_ROOT/vendor/termux-api-client/runtime/libexec/termux-api-broadcast"
test "$(find "$PROJECT_ROOT/bin" -maxdepth 1 -type l -name 'termux-*' | wc -l)" -eq 57

PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s "$PROJECT_ROOT/tests" >/dev/null
LOCAL_CODEX="$PROJECT_ROOT/vendor/codex-cli-frontier/node_modules/.bin/codex"
test "$(HOME="$ISOLATED_HOME" CODEX_HOME="$CODEX_HOME_DIR" "$LOCAL_CODEX" --version)" = "codex-cli 0.144.6"
auth_status=$(HOME="$ISOLATED_HOME" CODEX_HOME="$CODEX_HOME_DIR" "$LOCAL_CODEX" login status 2>&1)
grep -Fq 'Logged in using ChatGPT' <<< "$auth_status"
python - "$CODEX_HOME_DIR/models_cache.json" "$PROJECT_ROOT/models/subscription-models.json" <<'PY'
import json
import sys
live = json.load(open(sys.argv[1], encoding="utf-8"))
documented = json.load(open(sys.argv[2], encoding="utf-8"))
expected = {item["id"] for item in documented["models"]}
actual = {item.get("slug") for item in live.get("models", []) if isinstance(item, dict)}
assert expected <= actual
assert documented["defaultModel"] == "gpt-5.6-sol"
PY

capabilities=$(HOME="$ISOLATED_HOME" CODEX_RUNTIME_ROOT="$CODEX_HOME_DIR" "$PROJECT_ROOT/bin/codex-android" capabilities)
grep -Fq '"termuxApiCommandCount": 57' <<< "$capabilities"
battery_status=$("$PROJECT_ROOT/bin/termux-battery-status")
grep -Fq '"present": true' <<< "$battery_status"
curl -fsS --connect-timeout 2 --max-time 5 http://127.0.0.1:5902/codex-api/meta/methods >/dev/null
curl -fsS --connect-timeout 2 --max-time 5 http://127.0.0.1:5900/codex-api/meta/methods >/dev/null
# NVIDIA may be intentionally stopped by its owner. Its APK identity is verified
# below without starting, stopping, or otherwise changing that sibling app.

expected_apk_sha="$(awk 'NR==1 {print $1}' "$HASH_FILE")"
test -n "$expected_apk_sha"
printf '%s  %s\n' "$expected_apk_sha" "$APK" | sha256sum -c - >/dev/null
zipalign -c 4 "$APK" >/dev/null
apksigner verify --verbose --print-certs "$APK" >/dev/null
aapt dump badging "$APK" | grep -Fq "package: name='$CODEX_PACKAGE' versionCode='9' versionName='2.6.0'"

installed_fact=$("$RISH" -c "apk=\$(pm path $CODEX_PACKAGE | sed -n 's/^package://p' | head -n 1); test -n \"\$apk\"; toybox sha256sum \"\$apk\"; dumpsys package $CODEX_PACKAGE | grep -m1 versionName=2.6.0" 2>&1)
printf '%s\n' "$installed_fact" | grep -Fq "$expected_apk_sha"
printf '%s\n' "$installed_fact" | grep -Fq 'versionName=2.6.0'

read -r ORIGINAL_SHA256 NVIDIA_SHA256 < <(python - "$PROTECTED_BASELINE" "$ORIGINAL_PACKAGE" "$NVIDIA_PACKAGE" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
packages = payload["packages"]
print(packages[sys.argv[2]]["sha256"], packages[sys.argv[3]]["sha256"])
PY
)

protected_facts=$("$RISH" -c 'for pkg in com.michaelovsky.codexapplauncher com.michaelovsky.codexnvidia.isolated; do apk=$(pm path "$pkg" | sed -n "s/^package://p" | head -n 1); echo "$pkg"; toybox sha256sum "$apk"; done' 2>&1)
printf '%s\n' "$protected_facts" | grep -Fq "$ORIGINAL_SHA256"
printf '%s\n' "$protected_facts" | grep -Fq "$NVIDIA_SHA256"
printf '%s\n' "$protected_facts" | grep -Fq "$ORIGINAL_PACKAGE"
printf '%s\n' "$protected_facts" | grep -Fq "$NVIDIA_PACKAGE"

test -s "$PROJECT_ROOT/isolation/headless-live-request.jsonl"
python - "$PROJECT_ROOT/isolation/headless-live-request.jsonl" <<'PY'
import json
import sys
identity_answers = []
types = []
errors = []
for line in open(sys.argv[1], encoding="utf-8"):
    event = json.loads(line)
    types.append(event.get("type"))
    values = [event.get("text"), event.get("message")]
    item = event.get("item")
    if isinstance(item, dict):
        values.extend([item.get("text"), item.get("content")])
    combined = " ".join(str(v) for v in values if v is not None).lower()
    if "openai codex" in combined and "gpt-5.6-" in combined:
        identity_answers.append(combined)
    if event.get("type") in {"error", "turn.failed"}:
        errors.append(event)
assert any("gpt-5.6-luna" in value and "low" in value for value in identity_answers)
assert any("gpt-5.6-sol" in value and "ultra" in value for value in identity_answers)
assert "turn.completed" in types
assert not errors
PY

python - "$SELECTION_EVIDENCE" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["provider"] == "openai"
assert {key: payload["newThread"][key] for key in (
    "requestedModel", "requestedEffort", "acceptedModel", "acceptedEffort", "completed"
)} == {
    "requestedModel": "gpt-5.6-luna",
    "requestedEffort": "low",
    "acceptedModel": "gpt-5.6-luna",
    "acceptedEffort": "low",
    "completed": True,
}
assert {key: payload["existingThreadSwitch"][key] for key in (
    "requestedModel", "requestedEffort", "acceptedModel", "acceptedEffort", "completed"
)} == {
    "requestedModel": "gpt-5.6-sol",
    "requestedEffort": "ultra",
    "acceptedModel": "gpt-5.6-sol",
    "acceptedEffort": "ultra",
    "completed": True,
}
assert payload["unsupportedPairBlocked"] is True
assert payload["newThread"]["selfReportVerified"] is True
assert "gpt-5.6-luna" in payload["newThread"]["assistantText"].lower()
assert "low" in payload["newThread"]["assistantText"].lower()
assert payload["existingThreadSwitch"]["selfReportVerified"] is True
assert "gpt-5.6-sol" in payload["existingThreadSwitch"]["assistantText"].lower()
assert "ultra" in payload["existingThreadSwitch"]["assistantText"].lower()
PY

python - "$PROJECT_ROOT/isolation/pinned-thread-import-verification.json" "$PROJECT_ROOT" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
root = sys.argv[2]
assert payload["source"]["mutated"] is False
assert len(payload["projects"]) == 3
assert payload["checks"] == {
    "exactTransformedHistoryMatch": True,
    "recursiveStructuredCwdRewrite": True,
    "independentSessionIds": True,
    "frontierOnlySessionPaths": True,
    "allImportedThreadsPinned": True,
}
assert all(item["projectPath"].startswith(root + "/workspace/projects/") for item in payload["projects"])
PY

test -z "$(find /sdcard/Download -maxdepth 1 \( -name '.codex-install-*' -o -name '.codex-frontier-ui-*' -o -name '.codex-frontier-screenshot-*' \) -print -quit)"
test -z "$("$RISH" -c 'find /data/local/tmp -maxdepth 1 -name "codex-install-*" -print -quit' 2>&1)"

printf 'APK_SHA256=%s\n' "$expected_apk_sha"
printf 'CODEX_FRONTIER_VERIFIED\n'
