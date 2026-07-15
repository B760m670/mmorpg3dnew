#!/usr/bin/env bash
# Шаблоны iOS с НАТИВНЫМ Metal — исполняется в CI на macos-15 (Xcode + Metal SDK).
set -euo pipefail
DIR="${1:-$HOME/godot-fork}"
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/UPSTREAM"
cd "$DIR"
scons platform=ios target=template_release arch=arm64 -j"$(sysctl -n hw.ncpu)"
scons platform=ios target=template_debug   arch=arm64 -j"$(sysctl -n hw.ncpu)"
# упаковка ios.zip по образцу официальных шаблонов (misc/dist/ios_xcode)
rm -rf ios_xcode out
cp -r misc/dist/ios_xcode ios_xcode
cp bin/libgodot.ios.template_release.arm64.a ios_xcode/libgodot.ios.release.xcframework/ios-arm64/libgodot.a
cp bin/libgodot.ios.template_debug.arm64.a   ios_xcode/libgodot.ios.debug.xcframework/ios-arm64/libgodot.a
# MoltenVK: pbxproj шаблона ссылается на него БЕЗУСЛОВНО (vulkan-фоллбек);
# бинарь берём из ОФИЦИАЛЬНЫХ шаблонов той же версии
curl -sSL -o official.tpz "https://github.com/godotengine/godot/releases/download/${GODOT_TAG}/Godot_v${GODOT_TAG}_export_templates.tpz"
unzip -qo official.tpz "templates/ios.zip" -d official_tpl
unzip -qo official_tpl/templates/ios.zip "MoltenVK.xcframework/*" -d ios_xcode
test -d ios_xcode/MoltenVK.xcframework
mkdir -p out
(cd ios_xcode && zip -qr ../out/ios.zip .)
echo "iOS templates: $DIR/out/ios.zip (с MoltenVK.xcframework)"
