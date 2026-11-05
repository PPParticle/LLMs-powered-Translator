# LLMs-powered Translator

<img src="desktop/assets/icon.png" width="96" alt="LLMs-powered Translator">

中文 | [English](README.md)

## 部署

### Zotero 插件

1. 安装 Python 3 和 Zotero 10。
2. 在仓库根目录构建插件：

   ```sh
   python tools/build_zotero.py
   ```

3. 在 Zotero 选择**工具 → 插件 → 齿轮 → 从文件安装插件**，选择 `dist/` 中生成的 XPI。
4. 打开**编辑 → 设置 → LLMs-powered Translator**，选择接口，填写对应的模型名称和 API Key。自定义服务需填写完整的 HTTPS Chat Completions 地址。

### Windows 桌面版

安装 Python 3.10 或更新版本，在 PowerShell 中构建：

```powershell
cd desktop
./build-windows.ps1
./dist/LLMs-powered-Translator/LLMs-powered-Translator.exe
```

保留完整的 `dist/LLMs-powered-Translator` 文件夹。在托盘菜单中选择接口并填写对应的 API Key 和模型，选择划词自动查询或 `Ctrl + Alt + W` 快捷键。新安装默认选择智谱标准 API；升级时保留已有配置。

选中英文即可翻译为中文；包含中文的选区会被忽略。

### macOS 桌面版

在目标 Mac 上安装 Python 3.10 或更新版本并构建：

```sh
cd desktop
./build-macos.sh
open dist/LLMs-powered-Translator.app
```

按系统提示授予辅助功能和输入监控权限。在托盘菜单中设置 API Key 和触发方式；快捷键为 `⌘ + ⌥ + W`。

选中文本与可获取的附近上下文会发送给所选服务。桌面版密钥保存在系统凭据管理器，Zotero 密钥使用 Zotero 加密存储；不同地址使用各自的密钥，请勿将密钥提交到仓库。Zotero 插件也支持配置经授权的柯林斯 API。Coding Plan 请遵守其[指定工具和使用规则](https://docs.bigmodel.cn/cn/coding-plan/usage-notes)。

例如，使用 DeepSeek 时选择“其他 OpenAI 兼容 API”，地址填写 `https://api.deepseek.com/chat/completions`，模型填写 `deepseek-flash`，并使用自己的 DeepSeek API Key；按服务商实际用量计费。

## 测试

```sh
node zotero/test.js
python -m pip install -r desktop/requirements.txt
python -m unittest discover -s desktop -p test_desktop.py -v
```

在 Windows 上执行 `python desktop/test_windows_integration.py`，可检查 UI Automation 划词、单词补全和上下文获取。
