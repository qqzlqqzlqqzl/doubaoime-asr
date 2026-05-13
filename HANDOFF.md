# Doubao ASR Helper Handoff

这份文档是给下一个接手的 AI 或开发者看的。目标是让接手者不用重新翻聊天记录，也能快速理解当前项目状态、重要决策、构建测试方法、常见坑和下一步方向。

最后更新：2026-05-13  
当前主要分支：`main`  
远端仓库：`https://github.com/qqzlqqzlqqzl/doubaoime-asr.git`

## 0. 多电脑协作同步备注

当前项目正在两台 Windows 电脑之间协作开发。接手前不要直接覆盖本地文件或强推，请先：

```powershell
git fetch origin
git status --short --branch
git log --oneline --decorate HEAD..origin/main
```

如果本机有未提交改动，优先用：

```powershell
git pull --rebase --autostash
```

2026-05-13，本机已同步另一台电脑推上来的文档提交，并额外提交：

- `64e49f0 Fix settings layout in compact windows`
  - 修复设置页在 `820x680`、`760x520`、`560x420` 和 150%/200% DPI 下被挤出的问题。
  - 高度不足时隐藏非必要副标题、帮助文案和高级设置，保留模式块、核心热键、插入延迟、选项、状态和底部按钮。
  - 增大“剪贴板保护 / 开机自启动”开关的点击尺寸，并在最小窗口下横排显示。

这次提交已经推到 `origin/main`。另一台电脑继续工作前必须先拉到至少 `64e49f0`，否则很容易把已通过测试的响应式 UI 修复覆盖掉。

## 1. 当前项目定位

这个仓库最初是 `doubaoime-asr` Python 客户端，现在已经扩展成一个 Windows 桌面语音输入助手。

主要能力：

- 调用豆包输入法 ASR 协议做语音识别。
- 提供 Windows 桌面 UI，支持后台监听全局热键。
- 支持按住说、自由说、按住说并自动发送三种模式。
- 录音时显示悬浮识别窗，识别完成后把文本插入回用户开始录音前的窗口。
- 支持系统托盘后台保活，关闭主窗口不退出进程。
- 支持热键录制、冲突检测、一键恢复默认。
- 支持普通免激活开发版，也支持带激活码和设备绑定的受控分发版。
- 支持 one-file EXE、安装器、免安装 zip 分发。

正式桌面发布目标：

- Windows 10 x64
- Windows 11 x64

不再支持：

- Windows 7
- Windows 8 / 8.1
- 32 位 Windows

相关文档：

- `README.md`：用户和开发者入口说明。
- `TEST_PLAN.md`：自动化和手工验收清单。
- `E2E_TEST_EVIDENCE.md`：真实端到端证据矩阵，包含已通过、部分通过、阻塞和未运行的项目；接手时不要只看测试计划。
- `WINDOWS_COMPATIBILITY.md`：Windows 版本兼容结论。
- `wave_protocol.md`：协议相关背景。
- `HANDOFF.md`：当前交接文档。

## 2. 接手后先做什么

建议接手顺序：

1. 运行 `git status --short`，确认工作区是否干净。
2. 阅读 `README.md` 的“桌面语音输入助手”部分。
3. 阅读 `E2E_TEST_EVIDENCE.md`，先弄清哪些端到端项目是真的 PASS，哪些只是 PARTIAL 或 NOT_RUN；当前不能把 T01 默认热键闭环和 T09 剪贴板插入闭环算作通过。
4. 阅读本文件的“核心文件地图”和“桌面应用架构”。
5. 如果要改 UI 或分发包，先运行一次：

```powershell
. .\enter-dev.ps1
python -m compileall -q doubaoime_asr
python -m doubaoime_asr.desktop_app --self-test --self-test-report release\test-reports\source-self-test.json
```

6. 修改后至少运行对应的源码自测。涉及 EXE、托盘、UI、安装器、打包资源时必须重新跑：

```powershell
.\build-desktop-exe.ps1
.\test-desktop-exe.ps1
```

如果改了激活码、授权服务器或设备绑定：

```powershell
.\test-activation.ps1
.\test-license-stress.ps1
```

如果改了 Windows 兼容、PyInstaller、依赖或系统 DLL：

```powershell
.\test-windows-compat.ps1
```

如果改了长文本、音频、ASR 实际效果：

```powershell
.\test-long-text-asr.ps1
```

## 3. 本地开发环境

当前项目使用工作区内的隔离工具和虚拟环境，尽量不要污染用户全局环境。

入口脚本：

```powershell
. .\enter-dev.ps1
```

这个脚本会设置：

- `.venv\Scripts` 到 PATH
- `.devtools\cargo\bin` 到 PATH
- `.devtools\w64devkit\bin` 到 PATH
- `.devtools\opus\bin` 到 PATH
- `RUSTUP_HOME=.devtools\rustup`
- `CARGO_HOME=.devtools\cargo`
- `PIP_CACHE_DIR=.devtools\pip-cache`
- `UV_CACHE_DIR=.devtools\uv-cache`
- `NPM_CONFIG_CACHE=.devtools\npm-cache`

注意：

- 不要把依赖安装到系统 Python。
- 不要删除 `.devtools`，里面有便携 Rust、w64devkit、Opus、参考项目资源等。
- 构建脚本依赖 `uv`、PyInstaller、项目内 Opus DLL。
- 如果路径在 PowerShell 输出里出现乱码，多半是控制台编码显示问题，不一定是实际路径损坏。

## 4. 依赖和生成代码注意事项

接手者很容易在依赖上踩坑，集中记在这里：

- `pyproject.toml` 的 `requires-python` 是 `>=3.11`，但当前工作区 `.python-version` 是 `3.13`，近期 Windows EXE 测试也在 Python 3.13 上完成。
- `build-desktop-exe.ps1` 会执行 `uv pip install pyinstaller`，脚本没有 pin PyInstaller 版本。最近测试日志里使用的是 PyInstaller 6.20。改兼容性结论前请以 `release\test-reports\windows-compatibility.json` 和实际构建日志为准。
- `doubaoime_asr/asr_pb2.py` 和 `doubaoime_asr/asr_pb2.pyi` 是由 `doubaoime_asr/asr.proto` 生成的代码。改 proto 后要重新生成，不要手写大段生成代码。
- `pyproject.toml` 的 package data 必须包含 `license-config.json` 和 `assets/*.ico`，否则 one-file EXE 的激活配置或托盘图标会丢。
- `examples` extra 当前是空的；README 的示例依赖以主依赖和直接 `pip install sounddevice numpy` 为准。
- `uv.lock` 存在，但打包脚本里部分命令仍会按当前可解析版本安装工具。升级依赖后必须重跑 EXE 测试和 Windows 兼容审计。

## 5. 核心文件地图

### 桌面主程序

`doubaoime_asr/desktop_app.py`

这是当前最重要的文件，包含：

- Tkinter 主 UI。
- DPI 感知和响应式布局。
- 热键解析、热键录制、热键冲突检测。
- Windows 托盘图标和菜单。
- 麦克风采集和 ASR 流式识别。
- 悬浮窗显示和插入/复制/清空操作。
- 激活窗口。
- 自测入口：
  - `--self-test`
  - `--tray-self-test`
  - `--float-layout-test`
  - `--ui-layout-report`
  - `--long-text-test`

改这个文件时要非常小心，因为它同时影响用户交互、自动化测试、打包 EXE 和后台行为。

### 桌面帮助文档

`doubaoime_asr/desktop_help.py`

包含内置帮助文本。打包时会生成 `release\HELP.md`。如果新增用户可见功能，要同步更新这里。

### 图标资源

`doubaoime_asr/assets/app.ico`

来自参考项目 `doubao-voice-helper` 的图标资源。现在用于：

- 主窗口图标。
- 托盘图标。
- PyInstaller EXE 图标。
- 安装器图标。

不要删除。`test-desktop-exe.ps1` 会检查托盘自测报告里的 `icon_loaded_from_file=true`，避免回退到 Windows 默认图标。

### ASR 客户端

`doubaoime_asr/asr.py`

主要 ASR 客户端逻辑：

- WebSocket 连接。
- 音频发送。
- `transcribe`
- `transcribe_stream`
- `transcribe_realtime`
- 响应解析。

### 音频编码

`doubaoime_asr/audio.py`

负责 PCM 到 Opus frame 的转换。桌面版和文件识别都会依赖。

### 凭据和配置

`doubaoime_asr/config.py`  
`doubaoime_asr/device.py`  
`doubaoime_asr/constants.py`

用于设备注册、token、默认设备信息等。

### 激活码和授权

`doubaoime_asr/activation.py`

客户端授权逻辑：

- 读取构建内置授权配置。
- 环境变量覆盖授权配置。
- 设备指纹。
- 激活码激活。
- 本地 token 保存和校验。
- 授权服务器不可达时保留本地 token。

`tools/license_server.py`

最小示例授权服务器，支持：

- `POST /api/activate`
- `POST /api/verify`
- `GET /health`

`tools/license_stress_test.py`

授权服务器压力测试。

### 打包脚本

`build-desktop-exe.ps1`

生成：

- `dist\DoubaoASRHelper.exe`
- `dist\DoubaoASRHelperSetup.exe`
- `release\DoubaoASRHelper-portable.exe`
- `release\DoubaoASRHelperSetup.exe`
- `release\DoubaoASRHelper-Portable.zip`
- `release\DoubaoASRHelper-Windows.zip`
- `release\HELP.md`
- `release\README-Windows.txt`
- `release\README-Portable.txt`

重要细节：

- 会运行 `. .\enter-dev.ps1`。
- 会把 `doubaoime_asr/assets/app.ico` 作为 EXE 图标。
- 会把 `app.ico` 加到 PyInstaller data。
- 会把 `.devtools\opus\bin\opus.dll` 加为 binary。
- 会根据环境变量生成 `build\license-config\license-config.json` 并嵌入 EXE。

授权分发环境变量：

```powershell
$env:DOUBAO_ASR_REQUIRE_ACTIVATION = "1"
$env:DOUBAO_ASR_LICENSE_URL = "https://你的授权服务器域名"
.\build-desktop-exe.ps1
```

### 安装器

`windows_installer.py`

安装器逻辑：

- 从 PyInstaller `_MEIPASS` 中取主程序 `DoubaoASRHelper.exe`。
- 安装到 `%LOCALAPPDATA%\DoubaoASRHelper`。
- 创建开始菜单快捷方式、桌面快捷方式、Help 快捷方式、卸载快捷方式。
- 写 `uninstall.cmd`。

自动测试会用：

```powershell
DoubaoASRHelperSetup.exe --silent --no-shortcuts --no-run --target <temp path>
```

### 测试脚本

`test-desktop-exe.ps1`

最重要的桌面分发测试。覆盖：

- dist EXE 自测。
- portable EXE 自测。
- 托盘图标自测。
- 强制激活配置自测。
- zip 完整性。
- 安装器静默安装。
- 安装后 EXE 自测。
- 悬浮窗长文本布局。
- 关闭主窗口后后台保活。
- UI 截图和布局报告。
- 150% 和 200% DPI 缩放布局。
- 默认 200% DPI 下窗口应按比例放大。
- `--hidden` 后台启动保活。

`test-activation.ps1`

Python 层授权测试，调用 `tests/test_activation.py`。

`test-license-stress.ps1`

授权服务器压测。

`test-windows-compat.ps1`

检查发布目标和二进制依赖，确认 Win10/Win11 为正式目标。

`test-long-text-asr.ps1`

生成 500 字中文长文本样本，并尝试用打包 EXE 跑 ASR。

## 6. 桌面应用架构

### UI

桌面 UI 使用 Tkinter + `sv_ttk` light theme。没有引入 WebView 或前端框架。

核心原则：

- 单窗口设置界面，不加滚动条。
- UI 要适配普通、窄窗口、最小窗口、150% DPI、200% DPI。
- 不要用固定绝对坐标。
- 不要增加会撑爆最小窗口的长文案。
- 底部 action buttons 当前有 6 个：
  - 保存
  - 取消
  - 恢复默认
  - 显示悬浮窗
  - 使用说明
  - 打开配置目录

布局关键函数：

- `_build_settings_ui`
- `_build_mode_group`
- `layout_settings_controls`
- `layout_action_buttons`
- `write_ui_layout_report`

设置界面结构：

- 主界面按参考图的交互骨架组织：`【按着说】模式`、`【自由说】模式`、`【按着说+自动发送】模式` 三个模式块先出现。
- 三个模式块之后是通用设置：`豆包快捷键`、`插入延迟`、`剪贴板保护`、`开机自启动`。
- `高级设置` 放 `凭据文件`、`剪贴板超时`、`发送延迟`；极窄/极矮窗口下会隐藏标题、说明、凭据路径或高级区域来保证单页无滚动。
- `insert_delay_ms` 用滑块并显示秒数；`clipboard_restore_delay_ms` 和 `auto_send_delay_ms` 用 ms 输入框，三者都按 50ms 吸附。

通用设置选项：

- `剪贴板保护` 和 `开机自启动` 使用 `tk.Checkbutton(indicatoron=False)` 做成大号开关，不再用默认 `ttk.Checkbutton` 小方框。
- 相关 helper 是 `_create_option_toggle`、`_sync_option_toggle_style`、`_sync_option_toggle_styles`。
- `settings_option_buttons` 会把两个开关按 key 保存，`settings_mode_groups` 会保存三个模式块，`write_ui_layout_report` 会输出 `mode-0/1/2`、`setting-<key>-entry/button/scale/value`、`option-protect_clipboard` 和 `option-startup` 的 bounds。
- `test-desktop-exe.ps1` 会断言两个 option 开关存在、普通窗口不小于基础尺寸，高 DPI 下不小于 `120x38`，避免回退成默认小控件。

已知优化：

- root `<Configure>` 事件只触发节流布局。
- `layout_settings_controls` 用签名缓存，避免拖动窗口时大量 `grid_forget/grid` 重排。
- `layout_action_buttons` 也有签名缓存。
- `write_ui_layout_report` 会强制布局并避免写空 widgets 报告。

如果改 UI：

1. 先检查 `layout_settings_controls` 的 tiny/short/narrow/compact 判断。
2. 改底部按钮数量时同步 `test-desktop-exe.ps1` 的 `$ExpectedActionButtons`。
3. 改模式块、通用设置或系统选项时同步 `settings_mode_groups`、`settings_option_buttons`、`write_ui_layout_report` 和 `Assert-UiVisualSizeAtScale` 的语义化布局/尺寸断言。
4. 重新跑 `.\test-desktop-exe.ps1`。
5. 查看 `release\test-reports\installed-ui-smoke*.png` 和对应 layout JSON。

### DPI 和窗口大小

入口：

- `configure_process_dpi_awareness`
- `current_ui_scale_factor`
- `scaled_window_size`

默认窗口会根据 DPI 放大，避免 200% 下变成很小的窗口。

测试覆盖：

- `--ui-scale-factor 1.5`
- `--ui-scale-factor 2.0`
- `--ui-window-size 560x420`
- `--ui-window-size 760x520`
- 默认窗口在 200% 下是否放大。

### 热键

默认：

- `hold_key = rctrl`
- `toggle_key = xbutton1`
- `hold_send_key = lctrl+lwin`
- `cancel_key = esc`
- `doubao_hotkey = ctrl+d`

关键函数：

- `parse_hotkey`
- `generic_hotkey`
- `key_name`
- `mouse_name`
- `active_matches`
- `idle_start_hotkey_allowed`
- `idle_start_mode_for_active_keys`
- `hotkey_conflict_from_values`
- `system_hotkey_conflict`
- `_on_key_press`
- `_on_key_release`
- `_finish_key_record`

当前热键检测行为：

- 阻止空热键。
- 阻止普通打字场景危险的裸字母或数字作为启动热键。
- 阻止工具内部重复配置。
- 识别 `Alt/Ctrl/Shift/Win` 通用键和左右键。
- `atl` 会归一为 `alt`，用于容错。
- `Delete` 会归一为 `del`。
- 明确拦截常见 Windows 保留键，例如 `Alt+Tab`、`Alt+F4`、`Win+L`。
- Windows 上用 `RegisterHotKey` 做临时注册探测，发现系统或其他软件占用则提示。
- 鼠标侧键不是 `RegisterHotKey` 能检测的，仍按内部规则处理。

历史问题：

- 之前 `Alt+M` 只识别成 `m`，原因是 Windows 下 `pynput` 可能给 `Key.alt`，旧逻辑只认 `alt_l/alt_r`。现在已修。
- 之前输入 `xian` 可能误触发录音。现在裸字母启动热键被拦截，`idle_start_mode_for_active_keys` 也要求当前按下键属于目标热键，避免残留修饰键状态触发。

### 一键恢复默认

功能：

- 底部按钮“恢复默认”。
- 调用纯函数 `reset_config_to_defaults` 和 UI 方法 `reset_settings_to_defaults`。
- 恢复：
  - 所有热键
  - 插入延迟
  - 剪贴板超时
  - 自动发送延迟
  - 剪贴板保护
  - 开机自启动
- 保留：
  - `credential_path`
  - 凭据文件本身
  - 设备注册/token 缓存

注意：

- 复位会立即保存配置。
- 复位会同步开机自启动脚本，因为 `save_config` 会调用 `sync_startup`。

### 系统托盘

托盘实现完全在 `desktop_app.py` 内，用 Win32 API 手写：

- 注册隐藏窗口。
- `Shell_NotifyIconW` 添加/删除图标。
- 右键菜单。
- 左键显示窗口。
- 退出时清理图标。

关键类：

- `WindowsTrayIcon`

托盘图标：

- `doubaoime_asr/assets/app.ico`
- 由 `app_icon_path()` 查找。
- one-file EXE 中路径为 PyInstaller `_MEIPASS\doubaoime_asr\assets\app.ico`。

测试：

- `--tray-self-test`
- `test-desktop-exe.ps1` 会检查 `icon_exists` 和 `icon_loaded_from_file`。

### 悬浮窗

悬浮窗用于显示识别文本和操作按钮。

关键函数：

- `_build_float_window`
- `show_float`
- `_resize_float_window_for_text`
- `write_float_layout_report`

已修问题：

- 长文本显示不完整。
- 宽度和高度不随文本变化。
- 500 字样本或长断续文本容易溢出。

当前策略：

- 动态计算文本行数。
- 限制最大行数和窗口最大宽度。
- 确保窗口不超出屏幕。
- `--float-layout-test` 自动验证。

### 录音和插入

录音流程：

1. 全局热键触发 `start_recording`。
2. 保存开始录音前的前台窗口句柄。
3. 通过 `sounddevice.InputStream` 获取 PCM。
4. `transcribe_realtime` 流式识别。
5. 中间结果和最终结果进入 `TranscriptAccumulator`。
6. 结束后把文本插入回原窗口。

插入逻辑：

- 使用剪贴板临时放入识别文本。
- `keyboard.Controller` 发送粘贴快捷键。
- 如果启用剪贴板保护，尽量恢复原文本剪贴板。
- 复杂剪贴板内容，比如图片、富文本、文件列表，可能不能完整恢复。

模式：

- `hold`：按住说，松开结束。
- `toggle`：按一次开始，再按一次结束。
- `hold_send`：按住说并自动发送，结束后按 Enter。
- `cancel`：录音中按取消键停止并丢弃结果。

### 激活码

默认开发构建：

- 不强制激活。
- `license-config.json` 里 `require_activation=false`。

受控分发构建：

```powershell
$env:DOUBAO_ASR_REQUIRE_ACTIVATION = "1"
$env:DOUBAO_ASR_LICENSE_URL = "https://你的授权服务器域名"
.\build-desktop-exe.ps1
```

客户端行为：

- 首次启动发现需要激活但本地无有效授权，会显示激活窗口。
- 激活成功后保存 token 到 `%APPDATA%\DoubaoASRHelper\license.json`。
- token 绑定设备指纹。
- 复制授权文件到另一台电脑会失效并清理本地状态。
- 授权服务器地址变更会清理旧授权。
- 授权服务器暂时不可达时保留本地 token，避免误删。

示例服务器：

```powershell
python tools/license_server.py --codes tools/license-codes.sample.json --host 127.0.0.1 --port 8765
```

生产提醒：

- 一定要配置 HTTPS。
- 一定要设置 `DOUBAO_ASR_LICENSE_SECRET`。
- 客户端激活只能防止普通转发滥用，不能防强逆向。
- 如果要强控制，应把 ASR 请求代理到后端，由后端按激活状态放行。

## 7. 构建和分发

普通开发构建：

```powershell
.\build-desktop-exe.ps1
```

受控激活构建：

```powershell
$env:DOUBAO_ASR_REQUIRE_ACTIVATION = "1"
$env:DOUBAO_ASR_LICENSE_URL = "https://你的授权服务器域名"
.\build-desktop-exe.ps1
```

产物：

| 路径 | 用途 |
|------|------|
| `dist\DoubaoASRHelper.exe` | 主程序 one-file EXE |
| `dist\DoubaoASRHelperSetup.exe` | 安装器 one-file EXE |
| `release\DoubaoASRHelper-portable.exe` | 免安装单文件 |
| `release\DoubaoASRHelperSetup.exe` | 给用户的安装器 |
| `release\DoubaoASRHelper-Portable.zip` | 免安装 zip |
| `release\DoubaoASRHelper-Windows.zip` | 完整分发 zip |
| `release\HELP.md` | 离线帮助 |

分发建议：

- 想要最省事：给用户 `release\DoubaoASRHelper-Portable.zip`。
- 想要开始菜单和桌面快捷方式：给用户 `release\DoubaoASRHelper-Windows.zip` 里的安装器。
- 未签名 EXE 会触发 Windows SmartScreen，这是预期现象。
- 如果要正式商业分发，应该做代码签名。

## 8. 测试矩阵

### 快速源码测试

```powershell
. .\enter-dev.ps1
python -m compileall -q doubaoime_asr
python -m doubaoime_asr.desktop_app --self-test --self-test-report release\test-reports\source-self-test.json
```

覆盖：

- 配置目录可写。
- 凭据路径可写。
- 热键规则。
- Opus 编码。
- 音频设备。
- 输入控制 API。
- 系统托盘 API。
- app icon。
- help text。
- license config。
- license state。
- 一键恢复默认保留凭据路径。

### 桌面 EXE 测试

```powershell
.\build-desktop-exe.ps1
.\test-desktop-exe.ps1
```

这是 UI、托盘、安装器、便携包最重要的测试。运行时间较长，通常 2 到 4 分钟。

检查报告和截图：

- `release\test-reports\installed-ui-smoke.png`
- `release\test-reports\installed-ui-smoke-narrow.png`
- `release\test-reports\installed-ui-smoke-minimum.png`
- `release\test-reports\installed-ui-smoke-scale200-default.png`
- 对应的 `*-layout.json`

### 授权测试

```powershell
.\test-activation.ps1
.\test-license-stress.ps1
```

`test-activation.ps1` 是单元测试。  
`test-license-stress.ps1` 会启动示例授权服务器并做并发压测。

### Windows 兼容测试

```powershell
.\test-windows-compat.ps1
```

输出：

```text
release\test-reports\windows-compatibility.json
```

### 长文本 ASR 测试

```powershell
.\test-long-text-asr.ps1
```

输出：

- `.devtools\samples\long-text-volume-stress.wav`
- `release\test-reports\long-text-asr.json`

这个测试需要真实 ASR 可用凭据和网络可用。如果没有凭据或服务端协议变化，可能失败。

## 9. 最近关键改动

最近重要提交：

- `64e49f0 Fix settings layout in compact windows`
  - 这是本机在两电脑协作期间完成并推送的响应式 UI 修复。
  - 修复 `test-desktop-exe.ps1` 中普通、窄窗口、最小窗口和高 DPI 布局报告失败。
  - 高度不足时折叠非核心说明和高级设置，确保状态、6 个底部按钮、三种模式、热键输入、插入延迟和选项开关都在单页内可见。
  - 相关验证已在本机跑过：`build-desktop-exe.ps1`、`test-desktop-exe.ps1`、`test-windows-compat.ps1`、`test-activation.ps1`、`test-license-stress.ps1`、`test-long-text-asr.ps1`。

- 本轮 `Match desktop settings reference layout`
  - 设置界面改成参考图式三模式块：按着说、自由说、按着说+自动发送。
  - 通用区保留豆包快捷键、插入延迟、剪贴板保护和开机自启动；高级设置新增可配置的剪贴板超时。
  - 布局报告和 EXE 测试改用 `mode-*`、`setting-<key>-*` 等语义化控件名，覆盖 150%/200% DPI、窄窗口和最小窗口。
  - README、TEST_PLAN、内置 HELP 和 HANDOFF 同步更新。

- `bfcfa16 Enlarge desktop option toggles`
  - 将“剪贴板保护 / 开机自启动”从默认小 checkbox 改成大号响应式开关。
  - 布局报告新增 `option-protect_clipboard`、`option-startup`。
  - `test-desktop-exe.ps1` 增加普通和 200% DPI 下的开关尺寸断言。

- `af68841 Polish desktop typography alignment`
  - 统一桌面 UI 标题、标签、说明文字和底部按钮的字号/对齐。
  - 布局报告增加字号一致性检查。

- `21b70d8 Prevent duplicate desktop instances`
  - 防止安装版、便携版重复启动导致多个托盘图标和热键冲突。
  - 第二个实例会快速退出并尽量唤醒已有窗口。

- `1c5508c Add one-click settings reset`
  - 增加“恢复默认”按钮。
  - 复位热键、延迟、剪贴板保护、开机自启动。
  - 保留凭据路径。
  - UI 测试 action button 数量更新为 6。

- `c1885ff Add Windows hotkey conflict checks`
  - 保存和录制热键时检查内部重复、危险裸键、Windows 保留键和可探测的系统占用。
  - 用 `RegisterHotKey` 临时探测全局组合键是否可用。

- `5bc4ff3 Fix Alt hotkey capture`
  - 修复 `Alt+M` 只录成 `m`。
  - 增加通用 `Alt/Ctrl/Shift/Win` 映射。

- `f8be9bb Add bundled desktop tray icon`
  - 增加项目图标资源。
  - 托盘、主窗口、EXE、安装器统一图标。

- `5a21f96 Improve desktop UI responsiveness and hotkey safety`
  - 修复拖动窗口卡顿。
  - 修复长文本悬浮窗显示。
  - 修复输入 `xian` 误触发。
  - 移除 Win7/Win8 legacy 支持路径。

- `51ecd09 Prioritize Win10 Win11 desktop builds`
  - 明确 Win10/Win11 为正式目标。

更多历史可运行：

```powershell
git log --oneline -n 20
```

## 10. 重要已知边界

### ASR 协议不是官方 API

项目依赖对豆包输入法协议的分析，服务端协议可能变化。出现识别失败时，不一定是 UI 或音频问题，可能是协议或 token 逻辑变化。

### 热键占用检测不是全知

`RegisterHotKey` 能检测很多键盘组合是否被系统或其他软件占用，但不是所有输入都能检测：

- 鼠标侧键不走 `RegisterHotKey`。
- 某些程序可能用低级键盘钩子，不会表现为注册冲突。
- 录制后仍需要用户实际试一下。

### 剪贴板保护不是完整剪贴板备份

当前主要保护文本剪贴板。图片、文件列表、富文本可能无法完整恢复。

### 系统托盘是 Win32 手写实现

没有依赖 pystray。优点是打包依赖少，缺点是代码更底层。改托盘时一定跑 `--tray-self-test` 和 `test-desktop-exe.ps1`。

### UI 不能随便加内容

用户明确要求：

- 不要滚动条。
- 单个界面要放得下。
- 150% 和 200% 缩放要正常。
- 拖动不能卡。

所以新增 UI 控件要非常克制。底部按钮已经有 6 个，再加按钮前请优先考虑是否能合并到现有按钮或菜单。

### Win7/Win8 不再作为目标

不要恢复 legacy 构建脚本。当前发布链路就是面向 Win10/Win11；近期审计基线是 Python 3.13 和 PyInstaller 6.20，但 PyInstaller 版本以实际构建日志和 `windows-compatibility.json` 为准。

### 未签名 EXE

SmartScreen 警告属于预期。正式发布要代码签名。

## 11. 改动时的检查清单

### 改 UI

必须：

```powershell
python -m compileall -q doubaoime_asr
python -m doubaoime_asr.desktop_app --self-test --self-test-report release\test-reports\source-self-test.json
.\build-desktop-exe.ps1
.\test-desktop-exe.ps1
```

检查：

- `installed-ui-smoke*.png`
- `*-layout.json`
- action button 数量。
- `option-protect_clipboard` 和 `option-startup` 的 width/height，尤其是 200% DPI 报告。
- 150%/200% 缩放报告。

### 改热键

必须关注：

- `parse_hotkey`
- `key_name`
- `active_matches`
- `idle_start_mode_for_active_keys`
- `hotkey_conflict_from_values`
- `system_hotkey_conflict`
- `run_self_test` 里的 `hotkey_check`

至少跑：

```powershell
python -m doubaoime_asr.desktop_app --self-test --self-test-report release\test-reports\source-self-test-hotkey.json
.\build-desktop-exe.ps1
.\test-desktop-exe.ps1
```

手工建议：

- 录制 `alt+m`，确认显示 `alt+m`。
- 录制重复键，确认弹冲突。
- 录制 `alt+tab`，确认提示不可用。
- 输入拼音 `xian`，确认不触发录音。

### 改托盘

必须：

```powershell
python -m doubaoime_asr.desktop_app --tray-self-test --tray-self-test-report release\test-reports\source-tray-test.json
.\build-desktop-exe.ps1
.\test-desktop-exe.ps1
```

确认：

- `icon_loaded_from_file=true`
- 关闭主窗口后进程保活。
- 左键托盘恢复。
- 右键菜单可用。

### 改打包

必须：

```powershell
.\build-desktop-exe.ps1
.\test-desktop-exe.ps1
.\test-windows-compat.ps1
```

检查：

- `release\DoubaoASRHelper-Portable.zip`
- `release\DoubaoASRHelper-Windows.zip`
- `release\README-Windows.txt`
- `release\README-Portable.txt`
- `release\HELP.md`

### 改授权

必须：

```powershell
.\test-activation.ps1
.\test-license-stress.ps1
.\build-desktop-exe.ps1
.\test-desktop-exe.ps1
```

手工建议：

- 本地启动 `tools/license_server.py`。
- 用 `DOUBAO_ASR_REQUIRE_ACTIVATION=1` 打包。
- 首次启动输入有效码。
- 换无效码和过期码。
- 修改服务器 URL 后确认旧授权失效。

### 改 ASR 协议或音频

必须：

```powershell
python -m compileall -q doubaoime_asr
.\test-long-text-asr.ps1
```

如果没有有效凭据，至少跑自测和桌面测试，并在提交说明里明确未跑真实 ASR。

## 12. 用户偏好和项目要求

这些是从当前开发过程里沉淀下来的要求，后续接手要尊重：

- 优先打磨核心桌面功能，不要再做登录界面。
- 重点支持 Win10/Win11，不考虑 Win7/Win8。
- UI 要比原始 Tk 风格好看，不能像 WinXP。
- UI 不能拖动卡顿。
- UI 要适配 150%/200% 缩放和不同分辨率。
- UI 不要用滚动条，单界面要动态压缩和重排。
- 文本不能显示不完整。
- 热键不能和正常打字冲突。
- 热键要能自定义，并且要提示冲突。
- 托盘要有图标，要能后台保活。
- EXE 要能实际跑闭环。
- 要有免安装包，其他电脑尽量直接运行。
- 文档要足够完整，便于 AI 接手。
- 有成果要 commit。

## 13. 常见问题定位

### 托盘图标空白

检查：

1. `doubaoime_asr/assets/app.ico` 是否存在。
2. `build-desktop-exe.ps1` 是否有 `--icon "$AppIcon"`。
3. PyInstaller 是否有 `--add-data "$AppIcon;doubaoime_asr\assets"`。
4. `--tray-self-test` 报告是否有 `icon_loaded_from_file=true`。

### UI 在 200% 下很小

检查：

1. `configure_process_dpi_awareness` 是否正常执行。
2. `scaled_window_size` 是否被默认窗口路径使用。
3. `write_ui_layout_report` 的 `default_window_scaled`。
4. `test-desktop-exe.ps1` 的 `Assert-DefaultScaleWindowComfortable`。

### UI 拖动卡

检查：

1. 是否又在 `<Configure>` 里直接做大量布局。
2. `_layout_after_id` 节流是否还在。
3. `_layout_signature` 和 `_action_layout_signature` 是否被绕过。
4. 是否新增了频繁 `grid_forget/grid` 的逻辑。

### 录制 `Alt+M` 只剩 `m`

检查：

1. `key_name` 是否映射 `keyboard.Key.alt`。
2. 自测里 `format_hotkey({key_name(keyboard.Key.alt), "m"}) == "alt+m"` 是否仍在。

### 输入拼音误触发录音

检查：

1. `idle_start_hotkey_allowed` 是否仍拒绝裸字母/数字。
2. `idle_start_mode_for_active_keys` 是否要求当前按下键属于目标热键。
3. `hotkey_check` 里 `xian` 模拟是否仍在。

### 一键恢复默认误删凭据

检查：

1. `reset_config_to_defaults(..., preserve_credential_path=True)`。
2. 自测里 reset 后 `credential_path` 是否保持 custom path。
3. `reset_settings_to_defaults` 不要删除任何 credential/license 文件。

### 安装器跑完但没有快捷方式

检查：

1. 是否使用了 `--no-shortcuts`。
2. `windows_installer.py` 的 `create_shortcut` PowerShell COM 是否成功。
3. 目标路径是否在 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Doubao ASR Helper`。

### 激活版启动没有要求激活

检查：

1. 打包前是否设置：

```powershell
$env:DOUBAO_ASR_REQUIRE_ACTIVATION = "1"
$env:DOUBAO_ASR_LICENSE_URL = "..."
```

2. `build\license-config\license-config.json` 是否生成正确。
3. 打包后 `--self-test` 报告里的 `license_config.require_activation`。

## 14. 不建议做的事

- 不要重新引入 Win7/Win8 legacy 脚本。
- 不要把依赖装进系统 Python。
- 不要删除 `.devtools` 里的本地工具链。
- 不要把 UI 改成需要滚动条才能完整使用。
- 不要新增大型前端/WebView 依赖，除非明确重构路线。
- 不要在热键中默认使用普通字母。
- 不要把用户凭据、license state 或 activation code 写进 git。
- 不要把生成的 `dist/`、`release/` 大文件提交进仓库，除非用户明确要求版本化产物。
- 不要回退用户已有未提交改动。

## 15. 建议的下一步

如果继续打磨，优先级建议：

1. 增加真正的交互式热键录制 UI 自动化测试。目前主要靠逻辑自测和手工。
2. 增加真实麦克风短录音 smoke test，但要避免自动化测试卡住。
3. 做代码签名和发布版本号策略。
4. 把 `desktop_app.py` 拆分成 UI、热键、托盘、录音、激活几个模块。当前文件过大，但不要在功能开发中顺手大拆，最好单独做重构 PR。
5. 改进剪贴板保护，支持更多剪贴板格式备份和恢复。
6. 增加 crash log 和用户可导出的诊断包。
7. 给授权服务器补一个更正式的管理端或激活码生成工具。

## 16. 提交流程建议

常规提交前：

```powershell
git status --short
git diff --check
```

按改动范围运行测试。提交：

```powershell
git add <files>
git commit -m "<clear message>"
git push origin main
```

本项目当前直接推 `main`。如果后续团队化，建议改成 feature branch + PR。

## 17. 最小接手摘要

如果你只想快速继续干活，记住这几条：

- 主逻辑在 `doubaoime_asr/desktop_app.py`。
- 构建用 `.\build-desktop-exe.ps1`。
- 桌面分发测试用 `.\test-desktop-exe.ps1`。
- 正式目标只管 Win10/Win11 x64。
- UI 必须单页、无滚动条、支持 150%/200% DPI。
- 热键必须防打字误触、支持冲突提示。
- 托盘必须有图标且后台保活。
- 凭据和配置默认在 `%APPDATA%\DoubaoASRHelper`。
- 免安装包在 `release\DoubaoASRHelper-Portable.zip`。
- 有用户可见功能时同步 `README.md`、`desktop_help.py`、`TEST_PLAN.md`。
