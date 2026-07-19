#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_HOME="/data/data/com.termux/files/home/codex-subscription-isolated-app"
ANDROID_JAR="$APP_HOME/build-tools/android.jar"
KEYSTORE="$APP_HOME/build/codex-frontier.keystore"
SIGNING_PROPERTIES="$APP_HOME/build/signing.properties"
OUTPUT="$APP_HOME/dist/Codex-Frontier-2.8.0.apk"
EXPECTED_PACKAGE="com.michaelovsky.codexsubscription.isolated"

if [ ! -f "$ANDROID_JAR" ] || [ ! -f "$KEYSTORE" ] || [ ! -f "$SIGNING_PROPERTIES" ]; then
  printf 'Required project-local build material is missing.\n' >&2
  exit 2
fi

for command_name in aapt javac jar d8 zipalign apksigner; do
  command -v "$command_name" >/dev/null
done

set -a
. "$SIGNING_PROPERTIES"
set +a
umask 077
WORK_DIR=$(mktemp -d "$APP_HOME/build/.compile.XXXXXXXX")
cleanup() {
  case "$WORK_DIR" in
    "$APP_HOME"/build/.compile.*) find "$WORK_DIR" -depth -delete ;;
    *) printf 'Refusing unsafe build cleanup path: %s\n' "$WORK_DIR" >&2 ;;
  esac
}
trap cleanup EXIT INT TERM

mkdir -p "$WORK_DIR/gen" "$WORK_DIR/classes" "$WORK_DIR/dex"
aapt package -f -m -J "$WORK_DIR/gen" -M "$APP_HOME/AndroidManifest.xml" -S "$APP_HOME/res" -I "$ANDROID_JAR"
find "$APP_HOME/src" "$WORK_DIR/gen" -type f -name '*.java' -print0 \
  | sort -z \
  | xargs -0 javac -source 8 -target 8 -classpath "$ANDROID_JAR" -d "$WORK_DIR/classes"
jar cf "$WORK_DIR/classes.jar" -C "$WORK_DIR/classes" .
d8 --lib "$ANDROID_JAR" --min-api 23 --output "$WORK_DIR/dex" "$WORK_DIR/classes.jar"
aapt package -f -M "$APP_HOME/AndroidManifest.xml" -S "$APP_HOME/res" -I "$ANDROID_JAR" -F "$WORK_DIR/unsigned.apk"
jar uf "$WORK_DIR/unsigned.apk" -C "$WORK_DIR/dex" classes.dex
zipalign -f 4 "$WORK_DIR/unsigned.apk" "$WORK_DIR/aligned.apk"
apksigner sign \
  --ks "$KEYSTORE" \
  --ks-key-alias "$KEYSTORE_ALIAS" \
  --ks-pass env:KEYSTORE_PASSWORD \
  --key-pass env:KEYSTORE_PASSWORD \
  --v1-signing-enabled true \
  --v2-signing-enabled true \
  --v3-signing-enabled true \
  --v4-signing-enabled true \
  --out "$WORK_DIR/Codex-Frontier-2.8.0.apk" \
  "$WORK_DIR/aligned.apk"

zipalign -c 4 "$WORK_DIR/Codex-Frontier-2.8.0.apk"
apksigner verify --verbose --print-certs "$WORK_DIR/Codex-Frontier-2.8.0.apk" >/dev/null
aapt dump badging "$WORK_DIR/Codex-Frontier-2.8.0.apk" | grep -q "package: name='$EXPECTED_PACKAGE' versionCode='11' versionName='2.8.0'"
cp "$WORK_DIR/Codex-Frontier-2.8.0.apk" "$OUTPUT"
if [ -f "$WORK_DIR/Codex-Frontier-2.8.0.apk.idsig" ]; then
  cp "$WORK_DIR/Codex-Frontier-2.8.0.apk.idsig" "$OUTPUT.idsig"
fi
sha256sum "$OUTPUT" > "$OUTPUT.sha256"
cat "$OUTPUT.sha256"
