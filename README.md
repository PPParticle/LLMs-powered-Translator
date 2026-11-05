# LLMs-powered Translator

<img src="desktop/assets/icon.png" width="96" alt="LLMs-powered Translator">

[中文](README.zh-CN.md) | English

## Setup

### Zotero plugin

1. Install Python 3 and Zotero 10.
2. Build the plugin from the repository root:

   ```sh
   python tools/build_zotero.py
   ```

3. In Zotero, select **Tools → Plugins → gear → Install Add-on From File**, and choose the XPI in `dist/`.
4. Open **Edit → Settings → LLMs-powered Translator**, choose an API, and enter its model and API key. For a custom service, enter its full HTTPS Chat Completions URL.

### Windows desktop

Install Python 3.10 or newer and build in PowerShell:

```powershell
cd desktop
./build-windows.ps1
./dist/LLMs-powered-Translator/LLMs-powered-Translator.exe
```

Keep the complete `dist/LLMs-powered-Translator` folder. Open the tray menu to configure an API, model and key, and choose automatic selection or `Ctrl + Alt + W`. A new installation defaults to the standard Zhipu API; upgrades preserve existing settings.

Select English text for translation into Chinese. Selections containing Chinese are ignored.

### macOS desktop

Install Python 3.10 or newer and build on the target Mac:

```sh
cd desktop
./build-macos.sh
open dist/LLMs-powered-Translator.app
```

Grant Accessibility and Input Monitoring permissions when prompted. Configure the API key and trigger mode in the tray menu; the shortcut is `⌘ + ⌥ + W`.

Selected text and available surrounding context are sent to the selected provider. Desktop keys are stored in the system credential store; Zotero keys use Zotero's encrypted key storage. Keys are isolated by API address. Keep keys out of the repository. The Zotero plugin also supports an optional licensed Collins API. For Coding Plan, follow its [tool and usage rules](https://docs.bigmodel.cn/cn/coding-plan/usage-notes).

For example, choose a custom OpenAI compatible API, set `https://api.deepseek.com/chat/completions` as the URL and `deepseek-flash` as the model, then enter your own DeepSeek API key. The provider bills actual usage.

## Tests

```sh
node zotero/test.js
python -m pip install -r desktop/requirements.txt
python -m unittest discover -s desktop -p test_desktop.py -v
```

On Windows, `python desktop/test_windows_integration.py` checks selection, word completion, and context through UI Automation.
