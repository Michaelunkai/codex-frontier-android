#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
source_root="$script_dir/source-unpacked/termux-api-package-master"
runtime_prefix="$script_dir/runtime"

test -f "$source_root/termux-api.c"
test -f "$source_root/termux-api-broadcast.c"

mkdir -p "$runtime_prefix/bin" "$runtime_prefix/libexec"

clang \
  -O2 \
  -fPIE \
  -pthread \
  -DPREFIX=\"$runtime_prefix\" \
  "$source_root/termux-api.c" \
  "$source_root/termux-api-broadcast.c" \
  -o "$runtime_prefix/libexec/termux-api-broadcast"
chmod 700 "$runtime_prefix/libexec/termux-api-broadcast"

ln -sfn termux-api-broadcast "$runtime_prefix/libexec/termux-api"
ln -sfn /data/data/com.termux/files/usr/bin/bash "$runtime_prefix/bin/bash"
ln -sfn /data/data/com.termux/files/usr/bin/sh "$runtime_prefix/bin/sh"
ln -sfn /data/data/com.termux/files/usr/bin/am "$runtime_prefix/bin/am"

for template in "$source_root"/scripts/*.in; do
  name=$(basename "$template" .in)
  output="$runtime_prefix/bin/$name"
  sed "s|@TERMUX_PREFIX@|$runtime_prefix|g" "$template" > "$output"
  chmod 700 "$output"
  ln -sfn "../vendor/termux-api-client/runtime/bin/$name" "$project_root/bin/$name"
done

sed "s|@TERMUX_PREFIX@|$runtime_prefix|g" \
  "$source_root/termux-callback.in" \
  > "$runtime_prefix/libexec/termux-callback"
chmod 700 "$runtime_prefix/libexec/termux-callback"

printf 'TERMUX_API_PROJECT_CLIENT_BUILT\n'
