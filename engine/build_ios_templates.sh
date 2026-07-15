#!/usr/bin/env bash
# Шаблоны iOS с НАТИВНЫМ Metal — исполняется в CI на macos-15 (Xcode + Metal SDK).
set -euo pipefail
DIR="${1:-$HOME/godot-fork}"
cd "$DIR"
scons platform=ios target=template_release arch=arm64 -j"$(sysctl -n hw.ncpu)"
scons platform=ios target=template_debug   arch=arm64 -j"$(sysctl -n hw.ncpu)"
# упаковка ios.zip по образцу официальных шаблонов (misc/dist/ios_xcode)
cp -r misc/dist/ios_xcode ios_xcode
cp bin/libgodot.ios.template_release.arm64.a ios_xcode/libgodot.ios.release.xcframework/ios-arm64/libgodot.a
cp bin/libgodot.ios.template_debug.arm64.a   ios_xcode/libgodot.ios.debug.xcframework/ios-arm64/libgodot.a
mkdir -p out
(cd ios_xcode && zip -qr ../out/ios.zip .)
echo "iOS templates: $DIR/out/ios.zip"
