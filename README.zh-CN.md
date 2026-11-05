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
4. 打开**编辑 → 设置 → LLMs-powered Translator**，填写 GLM API Key 和模型名称。

### Windows 桌面版

安装 Python 3.10 或更新版本，在 PowerShell 中构建：

```powershell
cd desktop
./build-windows.ps1
./dist/LLMs-powered-Translator/LLMs-powered-Translator.exe
```

保留完整的 `dist/LLMs-powered-Translator` 文件夹。在托盘菜单中设置 GLM Coding Plan API Key，并选择划词自动查询或 `Ctrl + Alt + W` 快捷键。默认模型为 `glm-5.3-flash`。

### macOS 桌面版

在目标 Mac 上安装 Python 3.10 或更新版本并构建：

```sh
cd desktop
./build-macos.sh
open dist/LLMs-powered-Translator.app
```

按系统提示授予辅助功能和输入监控权限。在托盘菜单中设置 API Key 和触发方式；快捷键为 `⌘ + ⌥ + W`。

选中文本与可获取的附近上下文会发送给 GLM。桌面版密钥保存在系统凭据管理器，Zotero 密钥使用 Zotero 加密存储；请勿将密钥提交到仓库。Zotero 插件也支持配置经授权的柯林斯 API。

## 测试

```sh
node zotero/test.js
python -m pip install -r desktop/requirements.txt
python -m unittest discover -s desktop -p test_desktop.py -v
```

在 Windows 上执行 `python desktop/test_windows_integration.py`，可检查 UI Automation 划词、单词补全和上下文获取。
