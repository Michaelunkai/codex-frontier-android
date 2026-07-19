#!/data/data/com.termux/files/usr/bin/bash
set -eu

TERMUX_HOME="/data/data/com.termux/files/home"
APP_HOME="$TERMUX_HOME/codex-subscription-isolated-app"
ISOLATED_CODEX_ROOT="$APP_HOME/runtime/.codex"
ISOLATED_WORKSPACE="$APP_HOME/workspace"
ISOLATED_HOME="$APP_HOME/runtime/home"
LOCAL_CODEX_BIN="$APP_HOME/vendor/codex-cli-frontier/node_modules/.bin"
RUNTIME_ENTRY="$APP_HOME/vendor/codexapp-frontier-src/dist-cli/index.js"
PORT=5902
LOG_DIR="$ISOLATED_CODEX_ROOT/logs"
RUN_DIR="$ISOLATED_CODEX_ROOT/run"
PID_FILE="$RUN_DIR/codexapp.pid"
LOCK_FILE="$RUN_DIR/start.lock"
STATE_FILE="$RUN_DIR/runtime-state.json"

export PATH="$APP_HOME/bin:$LOCAL_CODEX_BIN:/data/data/com.termux/files/usr/bin:$TERMUX_HOME/.local/bin:$PATH"

health_ready() {
  curl -fsS --connect-timeout 1 --max-time 2 \
    "http://127.0.0.1:$PORT/codex-api/meta/methods" >/dev/null 2>&1
}

write_state() {
  state="$1"
  pid_value="${2:-0}"
  printf '{"state":"%s","pid":%s,"port":%s,"updatedAt":%s}\n' \
    "$state" "$pid_value" "$PORT" "$(date +%s)" > "$STATE_FILE"
}

is_owned_pid() {
  pid_value="$1"
  case "$pid_value" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ -r "/proc/$pid_value/cmdline" ] || return 1
  command_line="$(tr '\000' ' ' < "/proc/$pid_value/cmdline" 2>/dev/null || true)"
  case "$command_line" in
    *"$RUNTIME_ENTRY"*"-p $PORT"*) return 0 ;;
    *) return 1 ;;
  esac
}

terminate_owned_runtime() {
  pid_value="$1"
  is_owned_pid "$pid_value" || return 1
  stat_line="$(sed -n '1p' "/proc/$pid_value/stat" 2>/dev/null || true)"
  stat_tail="${stat_line#*) }"
  set -- $stat_tail
  process_group="${3:-0}"
  session_id="${4:-0}"
  if [ "$process_group" != "$pid_value" ] || [ "$session_id" != "$pid_value" ]; then
    printf 'refusing to stop pid %s because it is not its own Frontier process group\n' "$pid_value" >> "$LOG_DIR/startup-error.log"
    return 1
  fi
  kill -TERM -- "-$pid_value" 2>/dev/null || true
  wait_attempt=0
  while is_owned_pid "$pid_value" && [ "$wait_attempt" -lt 10 ]; do
    wait_attempt=$((wait_attempt + 1))
    sleep 1
  done
  if is_owned_pid "$pid_value"; then
    kill -KILL -- "-$pid_value" 2>/dev/null || true
    sleep 1
  fi
  ! is_owned_pid "$pid_value"
}

"$APP_HOME/isolation-preflight.sh"
mkdir -p \
  "$ISOLATED_CODEX_ROOT/archived_sessions" \
  "$ISOLATED_CODEX_ROOT/artifacts" \
  "$ISOLATED_CODEX_ROOT/audit" \
  "$ISOLATED_CODEX_ROOT/evidence" \
  "$ISOLATED_CODEX_ROOT/logs" \
  "$ISOLATED_CODEX_ROOT/memory" \
  "$ISOLATED_CODEX_ROOT/memories" \
  "$ISOLATED_CODEX_ROOT/plugins" \
  "$ISOLATED_CODEX_ROOT/sessions" \
  "$ISOLATED_CODEX_ROOT/skills" \
  "$ISOLATED_CODEX_ROOT/tmp" \
  "$ISOLATED_CODEX_ROOT/run" \
  "$ISOLATED_WORKSPACE" \
  "$ISOLATED_HOME"

if [ ! -f "$ISOLATED_CODEX_ROOT/config.toml" ]; then
  cp "$APP_HOME/runtime-template/.codex/config.toml" "$ISOLATED_CODEX_ROOT/config.toml"
fi
if [ ! -s "$ISOLATED_CODEX_ROOT/auth.json" ]; then
  printf 'isolated ChatGPT subscription snapshot missing\n' >> "$LOG_DIR/startup-error.log"
  exit 78
fi
chmod 600 "$ISOLATED_CODEX_ROOT/auth.json" "$ISOLATED_CODEX_ROOT/config.toml"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  if health_ready; then
    exit 0
  fi
  printf 'runtime startup already in progress\n' >> "$LOG_DIR/startup-error.log"
  exit 75
fi

if health_ready; then
  current_pid="$(sed -n '1p' "$PID_FILE" 2>/dev/null || true)"
  write_state ready "${current_pid:-0}"
  exit 0
fi

previous_pid="$(sed -n '1p' "$PID_FILE" 2>/dev/null || true)"
if is_owned_pid "$previous_pid"; then
  attempt=0
  while [ "$attempt" -lt 30 ]; do
    if health_ready; then
      write_state ready "$previous_pid"
      exit 0
    fi
    attempt=$((attempt + 1))
    sleep 1
  done
  write_state recovering "$previous_pid"
  printf 'owned runtime pid %s stayed unresponsive; restarting its verified isolated process group\n' "$previous_pid" >> "$LOG_DIR/startup-error.log"
  if ! terminate_owned_runtime "$previous_pid"; then
    write_state unresponsive "$previous_pid"
    exit 75
  fi
fi

printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ) launching Frontier runtime" >> "$LOG_DIR/codex-web.log"
setsid env \
  HOME="$ISOLATED_HOME" \
  CODEX_HOME="$ISOLATED_CODEX_ROOT" \
  CODEX_RUNTIME_ROOT="$ISOLATED_CODEX_ROOT" \
  CODEXAPP_GUI_OWNER_MODE="codex-frontier" \
  NODE_ENV="production" \
  PATH="$PATH" \
  /data/data/com.termux/files/usr/bin/node \
  "$RUNTIME_ENTRY" \
  "$ISOLATED_WORKSPACE" \
  -p "$PORT" \
  --no-open \
  --no-login \
  --no-tunnel \
  --approval-policy never \
  --sandbox-mode danger-full-access \
  >> "$LOG_DIR/codex-web.log" 2>&1 </dev/null &
runtime_pid=$!
printf '%s\n' "$runtime_pid" > "$PID_FILE"
write_state starting "$runtime_pid"

attempt=0
while [ "$attempt" -lt 90 ]; do
  if health_ready; then
    write_state ready "$runtime_pid"
    exit 0
  fi
  if ! is_owned_pid "$runtime_pid"; then
    write_state exited "$runtime_pid"
    printf 'Frontier runtime exited before becoming healthy (pid %s)\n' "$runtime_pid" >> "$LOG_DIR/startup-error.log"
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep 1
done

write_state timeout "$runtime_pid"
printf 'Frontier runtime did not become healthy within 90 seconds (pid %s)\n' "$runtime_pid" >> "$LOG_DIR/startup-error.log"
exit 1
