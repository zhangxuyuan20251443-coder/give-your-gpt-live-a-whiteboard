#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
app="$root/运行时/Dot 白板.app"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
xcrun swiftc -O -DWHITEBOARD_PLUGIN -module-name DotWhiteboard \
  "$root/Sources/Whiteboard.swift" "$root/Sources/ExerciseScenes.swift" \
  -framework AppKit -framework QuartzCore -o "$stage/DotWhiteboard"
install -m 755 "$stage/DotWhiteboard" "$app/Contents/MacOS/DotWhiteboard"
codesign --force --sign - "$app"
codesign --verify --strict "$app"
