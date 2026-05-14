# 变更记录

## 2026-05-14：AHK 客户端桥接版与上游差异审计

这一版是一次大的架构收敛，不是普通 UI 微调。目标从“自己写一个桌面壳”改为“尽量复用两个参考仓库，只写必要胶水”：

- ASR 协议和 Python API 以 `yangmoling/doubaoime-asr` 为基线。
- 桌面交互、热键、托盘、剪贴板和设置页以 `xiaohu31/doubao-voice-helper` 为基线。
- 本项目新增的核心胶水是本地 HTTP bridge：AHK 负责用户交互，Python 负责录音和 ASR。

### 架构变化

旧路线：

- Python/Tkinter 同时负责设置页、热键、录音、识别、悬浮窗、托盘和打包。
- 好处是单进程简单；坏处是 UI、录音和识别容易互相卡住，和参考工具的行为差异也越来越大。

新路线：

- `ahk_client` 是主桌面客户端，基于 AutoHotkey v2。
- `dist\DoubaoASRHelper.exe` 是 AHK 主程序，负责设置页、热键、托盘、悬浮窗、剪贴板保护、插入和自动发送。
- `dist\asr_bridge.exe` 是 Python 后端，负责麦克风录音、调用豆包 ASR、合并中间/最终识别结果。
- AHK 启动时会自动拉起同目录的 `asr_bridge.exe`，通过 `127.0.0.1:18765` 调用 `/health`、`/status`、`/start`、`/stop`、`/cancel`。
- 免安装包和安装目录必须同时包含 `DoubaoASRHelper.exe` 与 `asr_bridge.exe`。

### 用户可见变化

- 主设置界面按参考图收敛为三块：`按着说`、`自由说`、`按着说+自动发送`。
- 默认热键改为更适合普通键盘的组合：
  - 按着说：`右Ctrl`
  - 自由说：`Ctrl+Alt+Space`
  - 按着说+自动发送：`Ctrl+Alt+Enter`
  - 取消：`Esc`
  - 豆包快捷键兼容项：`Ctrl+Alt+D`
- 默认值避开鼠标侧键、裸字母、`Ctrl+D`、`Ctrl+Q`、`Win+H` 和容易影响打字的组合。
- 录音期间显示 AHK 本地悬浮窗，悬浮窗轮询 bridge 的实时文本。
- 松开按着说热键后自动插入识别结果，不需要再手动点悬浮窗“插入”。
- `POST /stop` 支持非阻塞完成，AHK 用定时器等待最终文本，避免说话或收尾识别时整个界面冻结。
- 托盘右键菜单可以启用/禁用语音监听，并展示当前热键。
- 配置目录统一为 `%APPDATA%\DoubaoASRHelper`。如果旧版存在 `%APPDATA%\DouBaoVoiceHelper\config.ini`，会迁移到新目录。

### 上游差异审计

新增 [UPSTREAM_DIFF_AUDIT.md](UPSTREAM_DIFF_AUDIT.md)，逐项说明当前仓库和两个参考仓库的文件级差异。

这次审计发现并修复了 3 个解释不通的 drift：

| 问题 | 影响 | 修复 |
|---|---|---|
| `DoubaoASR(config=None)` 保留 `self.config = None` | 公开 helper 允许 `config=None`，但音频编码会访问 `None.sample_rate` 崩溃 | 默认创建 `ASRConfig()` |
| AHK 配置仍写入旧上游目录 `DouBaoVoiceHelper` | 产品、安装器、帮助文档使用 `DoubaoASRHelper`，目录不一致会增加排障成本 | 写入 `%APPDATA%\DoubaoASRHelper`，并迁移旧配置 |
| 源码 self-test 依赖手工设置 Opus DLL 路径 | 直接运行 `python -m doubaoime_asr.desktop_app --self-test` 会因找不到 Opus 失败 | `audio.py` 自动加载 PyInstaller bundle 或 `.devtools\opus\bin` |

同时恢复了 AHK 上游辅助文件：

- `ahk_client/.gitignore`
- `ahk_client/tools/window-spy.ahk`

恢复原因：它们不影响运行路径，但属于参考客户端的开发/诊断能力，保留后更容易继续同步上游，避免无理由裁剪。

### 测试与证据

这一版已跑过：

- `python -m compileall doubaoime_asr\audio.py doubaoime_asr\asr.py doubaoime_asr\desktop_app.py doubaoime_asr\desktop_help.py doubaoime_asr\asr_bridge.py`
- `python -m pytest -q`：`16 passed, 1 warning`
- `python -m doubaoime_asr.desktop_app --self-test --self-test-report release\test-reports\e2e-source-self-test.json`：通过，报告 `ok=true`
- `build-desktop-exe.ps1`：通过，重新生成 AHK 主程序、Python bridge、安装器和 zip
- `test-desktop-exe.ps1`：通过，包含 bridge 自测、AHK 拉起 bridge、安装器、zip 完整性，以及 AHK 旧配置迁移断言
- `git diff --check`：通过，仅有 CRLF 归一化提示

### 对后续接手者的重要提醒

- 不要把 `DoubaoASRHelper.exe` 当成唯一运行文件。当前桌面版需要同目录的 `asr_bridge.exe`。
- AHK 客户端是主交互面，Python Tk 桌面代码现在主要保留为测试、帮助、历史兼容和部分自动化入口。
- 修改热键、托盘、剪贴板、悬浮窗时，优先看 `ahk_client/src/*.ahk`。
- 修改 ASR 协议、音频、凭据、实时文本合并时，优先看 `doubaoime_asr/asr.py`、`audio.py`、`asr_bridge.py`、`transcript.py`。
- 改 AHK 配置路径或默认热键后，必须重跑 `test-desktop-exe.ps1`，它现在会验证旧配置迁移。
- 正式分发仍需要代码签名；未签名 EXE 在 SmartScreen、Smart App Control 或企业 Code Integrity 环境可能被拦截。

