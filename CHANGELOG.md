# 变更记录

## 2026-05-14：悬浮窗长句滚动与蓝色音量条

- 悬浮窗识别结果区从静态 `Text` 改为只读多行 `Edit`，不再把长句截断到 96 字；每次实时文本更新后会通过 Win32 消息把光标和滚动位置追到最新内容。
- 结果区视觉从白底边框改为浅蓝底，麦克风图标和关闭符号统一蓝色系，避免浮窗中间出现突兀白框。
- 顶部音量条改为蓝色分层色板，并按音量、中心峰值和轻微波形相位动态调整高度/宽度，静音时保持低蓝色柱，说话时中心柱会更明显。
- `test-desktop-exe.ps1` 的浮窗枚举改为 `WM_GETTEXT` 读取控件当前内容，能正确验证只读 Edit 中的完整长文本。

### 本轮验证

- AHK 源码 `--float-self-test`：通过。
- `build-desktop-exe.ps1`：通过，重新生成 `dist` 和 `release` 产物。
- `test-desktop-exe.ps1`：通过，输出 `AHK bridge desktop tests passed.`。
- `.venv\Scripts\python.exe -m pytest -q`：`16 passed, 1 warning`。

## 2026-05-14：恢复上游 AHK 设置页布局

- 设置页视觉布局恢复为 `xiaohu31/doubao-voice-helper/src/gui.ahk` 的上游实现：`Gui("+Resize -MaximizeBox")`、`SetFont("s10", "Microsoft YaHei")`、固定 `w400 h630`，各分组、输入框、录制按钮、分隔线、高级设置、保存/取消和状态栏坐标均与参考客户端一致。
- 移除上一轮为截图/DPI 临时加入的 `-DPIScale`、`s6` 字体和按 DPI 手动放大窗口逻辑，避免继续偏离参考 repo。
- 保留唯一必要的非视觉差异：`Space/Enter/Esc/Backspace/Delete/Insert/CapsLock` 等热键显示和反向转换兼容。当前默认键位会用到 `Ctrl+Alt+Space`、`Ctrl+Alt+Enter` 和 `Esc`，不保留会影响配置显示和保存。
- 已覆盖 `%LOCALAPPDATA%\DoubaoASRHelper` 下的 `DoubaoASRHelper.exe` 和 `asr_bridge.exe`，桌面快捷方式指向的安装目录会打开本轮版本。

### 本轮验证

- 对照参考 repo：`git diff --no-index .devtools\reference\doubao-voice-helper\src\gui.ahk ahk_client\src\gui.ahk` 只剩热键名称兼容差异，设置页视觉布局段无 diff。
- `.venv\Scripts\python.exe -m pytest`：`16 passed, 1 warning`。
- `build-desktop-exe.ps1`：通过，重新生成 `dist` 和 `release` 产物。
- `test-desktop-exe.ps1`：bridge self-test、HTTP health/status、悬浮窗 self-test、AHK 客户端启动与配置迁移均已执行到安装器阶段；随后被 Windows 应用控制策略拦截未签名 `dist\DoubaoASRHelperSetup.exe`，因此完整安装器烟测不按通过计算。
- 源码设置页截图：`release\test-reports\source-ahk-settings-reference-restored.png`，窗口 `400x630`。
- 安装版 DPI-aware 设置页截图：`release\test-reports\installed-ahk-settings-reference-restored-dpiaware.png`，窗口 `826x1331` 物理像素，对应参考客户端 `400x630` 逻辑窗口，控件完整显示。

## 2026-05-14：悬浮窗音量指示与长文本显示修复

- 顶部蓝色波形不再使用假动画；`asr_bridge.exe` 在录音回调中计算 `audio_level/audio_peak`，`/status` 返回真实音量，AHK 浮窗按音量重画柱高。静音或底噪时保持低柱，不会无故大幅波动。
- 悬浮窗结果框高度从 `132` 提升到 `166`，文本区加宽加高，长文本显示上限从 48 字提升到 96 字，避免连续说长句时结果区看起来“消失”。
- `--float-self-test` 改成长文本样本，用于覆盖多行显示。
- bridge self-test 新增音量断言：静音必须返回 0，非静音必须返回正音量。
- 已覆盖 `%LOCALAPPDATA%\DoubaoASRHelper` 下的 `DoubaoASRHelper.exe` 和 `asr_bridge.exe`。

### 本轮验证

- `.venv\Scripts\python.exe -m compileall doubaoime_asr\asr_bridge.py`：通过。
- `.venv\Scripts\python.exe -m pytest`：`16 passed, 1 warning`。
- `build-desktop-exe.ps1`：通过。
- `test-desktop-exe.ps1`：通过，输出 `AHK bridge desktop tests passed.`。
- 安装版 bridge 录音态状态：`release\test-reports\installed-bridge-audio-level-status.json`，`has_audio_level=true`，无说话底噪 `audio_level=3`。
- 安装版长文本浮窗：`release\test-reports\installed-long-float-final.json` 和 `installed-long-float-final.png`，窗口 `457x167`，子控件包含长文本及 `清空 / 复制 / 插入`。

## 2026-05-14：参考图紧凑设置页与小尺寸悬浮窗

- 历史记录：这一轮曾为高 DPI 截图临时加入 `-DPIScale` 和更小字体；后续已在“恢复上游 AHK 设置页布局”中撤销，设置页以 `xiaohu31/doubao-voice-helper` 原始 AHK 布局为准。
- 保留的有效结论是：设置页继续沿用 `xiaohu31/doubao-voice-helper` 的控件文案和分组顺序，后续不要再改回旧 Python/Tk 大界面。
- 识别悬浮窗从 `560x178` 压缩为 `457x133`，保留顶部蓝色声波、结果文本、关闭符号以及 `清空 / 复制 / 插入` 三个操作，去掉大面积空白。
- 已把新版 AHK 主程序覆盖到 `%LOCALAPPDATA%\DoubaoASRHelper\DoubaoASRHelper.exe`；桌面快捷方式仍指向该安装目录。由于本轮新打包的 `dist\asr_bridge.exe` 被 Windows 应用控制策略拦截，安装目录中的 bridge 未被覆盖。

### 本轮验证

- 历史截图：`release\test-reports\source-ahk-settings-panel-fit.png` 和 `installed-final-settings-panel-fit.png` 曾用于验证这一轮临时紧凑方案；该证据已被上方“恢复上游 AHK 设置页布局”的新截图取代。
- 已安装 AHK 悬浮窗：`release\test-reports\installed-final-compact-float-test.json`，窗口 `457x133`，控件文本包含测试识别文本和 `清空 / 复制 / 插入`。
- `build-desktop-exe.ps1`：通过，重新生成 `dist` 和 `release` 产物。
- `.venv\Scripts\python.exe -m pytest`：`16 passed, 1 warning`。
- `test-desktop-exe.ps1`：本轮被 Windows 应用控制策略拦截在 `dist\asr_bridge.exe --self-test`；`Unblock-File` 后仍被拦截，需代码签名或放行策略后才能完整重跑。

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

### 2026-05-14 补充：悬浮窗可见性修复

用户反馈录音时仍没有悬浮框。本次修复把 AHK 悬浮窗显示提前到 bridge 启动之前，热键触发后先显示“正在准备录音”，再启动录音后端，避免后端启动或麦克风初始化期间没有任何视觉反馈。

同时新增 `DoubaoASRHelper.exe --float-self-test`，`test-desktop-exe.ps1` 会启动打包后的 AHK EXE 并通过 Win32 枚举窗口确认 `DoubaoASRHelperFloat` 可见且尺寸不小于阈值。当前报告 `release\test-reports\ahk-float-self-test.json` 为 `ok=true`，窗口尺寸 `521x113`。

后续按用户参考图继续增强悬浮窗：待说话时显示蓝色麦克风图和“点击/长按说话”，录音中显示蓝色声波条和“点击结束语音输入”。这两个状态由 AHK 控件绘制，不依赖外部图片文件，避免打包遗漏资源。

同时新增日志体系：AHK 客户端写 `%APPDATA%\DoubaoASRHelper\logs\client-YYYYMMDD.log`，Python bridge 写 `%APPDATA%\DoubaoASRHelper\logs\asr_bridge-YYYYMMDD.log`。日志覆盖客户端启动、热键、bridge 调用、插入、未处理异常、bridge 服务启动、录音会话、ASR 错误和线程异常。`test-desktop-exe.ps1` 已断言两类日志都能生成。

再补充修复结果输入框：悬浮窗中间新增识别结果框，实时/最终文本显示在框内，底部提供 `清空`、`复制`、`插入` 三个操作。`test-desktop-exe.ps1` 现在会枚举打包 EXE 的子控件，确认识别文本、清空、复制、插入都真实出现在 `DoubaoASRHelperFloat` 中。
