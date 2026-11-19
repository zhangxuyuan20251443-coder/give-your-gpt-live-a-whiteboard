#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
xcrun swiftc -O -DWHITEBOARD_PLUGIN -module-name DotWhiteboard \
  "$root/桌面白板/源码/白板.swift" "$root/桌面白板/源码/运动场景.swift" \
  -framework AppKit -framework QuartzCore -o "$stage/DotWhiteboard"
app="$root/白板插件/运行时/Dot 白板.app"
install -m 755 "$stage/DotWhiteboard" "$app/Contents/MacOS/DotWhiteboard"
codesign --force --sign - "$app"
codesign --verify --strict "$app"
/bin/bash "$root/白板插件/skills/dynamic-whiteboard/scripts/build.sh"
