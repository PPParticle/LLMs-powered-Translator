#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ "$(uname -s)" != "Darwin" ]; then
  echo "请在 macOS 上运行此脚本。" >&2
  exit 1
fi
python3 -m venv .venv-build
.venv-build/bin/python -m pip install --upgrade pip
.venv-build/bin/python -m pip install -r requirements.txt
.venv-build/bin/python -m unittest discover -s . -p 'test_desktop.py' -v
iconset='.venv-build/Translator.iconset'
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" assets/icon.png --out "$iconset/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" assets/icon.png --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$iconset" -o .venv-build/Translator.icns
.venv-build/bin/python -m PyInstaller --noconfirm --clean --windowed \
  --name LLMs-powered-Translator --icon .venv-build/Translator.icns --add-data 'assets:assets' --osx-bundle-identifier local.paperwordstudy.desktop \
  --collect-submodules keyring.backends --collect-submodules pynput \
  --hidden-import ApplicationServices app.py
echo "构建完成：dist/LLMs-powered-Translator.app"
