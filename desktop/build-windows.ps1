$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $IsWindows -and $env:OS -ne 'Windows_NT') { throw '请在 Windows 上运行此脚本。' }
python -m venv .venv-build
& .\.venv-build\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败。' }
& .\.venv-build\Scripts\python.exe -m unittest discover -s . -p test_desktop.py -v
if ($LASTEXITCODE -ne 0) { throw '测试失败。' }
& .\.venv-build\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name LLMs-powered-Translator --icon assets/icon.ico --add-data 'assets;assets' --collect-all uiautomation --collect-submodules keyring.backends --collect-submodules pynput app.py
if ($LASTEXITCODE -ne 0) { throw '打包失败。' }
Write-Output '构建完成：dist\LLMs-powered-Translator\LLMs-powered-Translator.exe'
