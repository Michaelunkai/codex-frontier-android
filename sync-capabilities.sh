#!/data/data/com.termux/files/usr/bin/bash
set -eu

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SOURCE_CODEX="/data/data/com.termux/files/home/.codex"
DEST_CODEX="$PROJECT_ROOT/runtime/.codex"
STAGING_ROOT="$PROJECT_ROOT/runtime/import-staging"
MODE="${1:-all}"

case "$MODE" in all|skills|plugins) ;; *) printf 'usage: %s [all|skills|plugins]\n' "$0" >&2; exit 2 ;; esac
mkdir -p "$DEST_CODEX/skills" "$DEST_CODEX/plugins" "$STAGING_ROOT"

copy_snapshot() {
  source_path="$1"
  destination="$2"
  label="$3"
  [ -e "$source_path" ] || return 0
  if [ -e "$destination" ] || [ -L "$destination" ]; then
    printf '%s:skipped-existing:%s\n' "$label" "${destination##*/}"
    return 0
  fi
  stage="$STAGING_ROOT/${label}.$$.${destination##*/}"
  cp -a "$source_path" "$stage"
  if find "$stage" -type l | grep -q .; then
    find "$stage" -depth -delete
    printf '%s:refused-symlink:%s\n' "$label" "${source_path##*/}" >&2
    exit 78
  fi
  mv "$stage" "$destination"
  printf '%s:imported:%s\n' "$label" "${destination##*/}"
}

if [ "$MODE" = all ] || [ "$MODE" = skills ]; then
  for source_skill in "$SOURCE_CODEX"/skills/*; do
    [ -d "$source_skill" ] || continue
    skill_name="${source_skill##*/}"
    [ "$skill_name" = michnvidiaapp-current-setup ] && continue
    [ -f "$source_skill/SKILL.md" ] || continue
    copy_snapshot "$source_skill" "$DEST_CODEX/skills/$skill_name" skill
  done
fi

if [ "$MODE" = all ] || [ "$MODE" = plugins ]; then
  if [ -d "$SOURCE_CODEX/plugins/cache" ]; then
    copy_snapshot "$SOURCE_CODEX/plugins/cache" "$DEST_CODEX/plugins/cache" plugin-cache
  fi
fi

printf 'CAPABILITY_SNAPSHOT_COMPLETE mode=%s policy=copy-only\n' "$MODE"
