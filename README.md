# LLMs-powered Translator

<img src="desktop/assets/icon.png" width="112" alt="LLMs-powered Translator 图标">

面向论文阅读的词汇学习工具：在阅读器或其他应用中选中英文单词，结合附近上下文生成释义、词形和同词族；常见搭配、词根和近义词按需展开。

项目包含两个独立组件：

- [`zotero/`](zotero/)：Zotero 10 插件，当前版本 0.11.0。
- [`desktop/`](desktop/)：Windows 和 macOS 桌面版源码，当前版本 0.3.0。Windows 已构建和基本测试；macOS 需要在 Mac 上构建，尚未实机验证。

## 安装和构建

### Zotero 插件

需要 Python 3。运行：

```sh
python tools/build_zotero.py
```

在 Zotero 中选择 **工具 → 插件 → 齿轮 → 从文件安装插件**，选择生成在 `dist/` 中的 XPI。详细设置与限制见 [Zotero 使用说明](zotero/README.md)。

### Windows 桌面版

需要 Python 3.10 或更新版本。在 Windows 的 PowerShell 中运行：

```powershell
cd desktop
./build-windows.ps1
```

构建完成后运行 `desktop/dist/LLMs-powered-Translator/LLMs-powered-Translator.exe`；整个目录需保留。详见 [桌面版使用说明](desktop/README.md)。

### macOS 桌面版

在 Mac 上安装 Python 3.10 或更新版本，进入 `desktop` 目录并执行 `./build-macos.sh`。构建生成 `.app`；可能需要辅助功能和输入监控权限。macOS 支持尚未实机验证，应用也尚未签名或公证。

## 配置与数据

首次使用时在程序设置中填写自己的智谱 GLM API Key，**不要将密钥提交到仓库**。桌面版使用 Coding Plan 接口，默认模型为 `glm-5.3-flash`，并默认直连；智谱对 Coding Plan 的适用工具有限制，独立词汇工具是否适用请向智谱确认。[智谱使用须知](https://docs.bigmodel.cn/cn/coding-plan/usage-notes)

当选区上下文可用时，附近原文会与选词一起发送给 GLM。桌面版密钥保存在系统凭据管理器或钥匙串；Zotero 插件使用 Zotero 的加密密钥存储。模型生成内容可能有误。当前默认解释由 GLM 生成，并未内置或离线下载柯林斯词典；Zotero 插件提供可选的柯林斯授权 API 配置入口。

## 测试

```sh
node zotero/test.js
python -m unittest discover -s desktop -p test_desktop.py -v
```

桌面版测试需要先安装 `desktop/requirements.txt` 中适用于当前平台的依赖。初次查询的完整响应时间取决于网络与模型服务，不保证在 500 毫秒内完成。
