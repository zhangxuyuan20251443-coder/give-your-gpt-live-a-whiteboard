#!/bin/bash
# 编译新播放器「动态白板.app」。需要 Xcode 命令行工具：xcode-select --install
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/动态白板.app"
SRC="$ROOT/native"
if ! command -v swiftc >/dev/null 2>&1; then
  echo "需要 swiftc：先运行 xcode-select --install，装好后再运行本脚本。" >&2
  exit 1
fi
STAGE=$(mktemp -d "$ROOT/.wb-build.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
TMP="$STAGE/动态白板.app"
mkdir -p "$TMP/Contents/MacOS" "$TMP/Contents/Resources"
swiftc -target "$(uname -m)-apple-macos12.0" -O -swift-version 5 -o "$TMP/Contents/MacOS/DynamicWhiteboard" "$SRC/main.swift" -framework Cocoa -framework WebKit
cp "$SRC/Info.plist" "$TMP/Contents/Info.plist"
codesign --force --sign - "$TMP"
codesign --verify --strict "$TMP"
rm -rf "$APP"
mv "$TMP" "$APP"
echo "已编译：$APP"
