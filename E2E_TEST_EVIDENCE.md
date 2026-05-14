# 端到端闭环测试证据

运行日期：2026-05-13 至 2026-05-14

结论：没有全部测完。当前环境已经跑完一部分能自动化闭合的链路；需要真人按键、真实外部应用、重启、干净电脑、长时间运行或受控授权服务器的项目，下面明确标为 `BLOCKED` 或 `NOT_RUN`，不按通过计算。

协作备注：2026-05-13 本机已拉取另一台电脑的最新文档提交，并推送 `64e49f0 Fix settings layout in compact windows`。这个提交修复设置页在普通、窄窗口、最小窗口和 150%/200% DPI 下的布局测试失败。另一台电脑继续前应先 `git fetch origin` 并确认已包含该提交，避免用旧版 `desktop_app.py` 覆盖。

自查修正：

- `release/test-reports/*` 被 `.gitignore` 忽略，只是本机证据，不会随 GitHub 提交保存。下面的表格保留本机路径，同时把关键数值写进本文档，避免只有不可追溯的本地文件引用。
- `T01-direct` 使用源码里的 `DesktopApp` 直接调起录音流程，不是打包 EXE 的完整热键闭环，也绕过了物理 `右 Ctrl` 热键层。它只能证明“真实记事本 + 外部麦克风 + ASR + 插入”这段核心链路，不证明用户双击 EXE 后按默认热键可用。
- `T11` 是耳机声学链路和 ASR 服务闭环，不是桌面 UI/热键/插入目标应用的完整闭环。
- `T09` 新增了安装版 `--clipboard-insert-test`，能证明文本剪贴板保护下“测试文本进入临时文本框且原文本剪贴板恢复”。但它使用临时 Tk 文本框和 paste 事件，不是录音热键触发，也不是真实外部应用前台焦点闭环。
- `T10` 新增了安装版 `--clipboard-complex-test`，能证明常见图片 `CF_DIB` 和文件列表 `CF_HDROP` 在插入测试文本后恢复；它仍是临时 Tk 文本框烟测，不是真实录音热键和外部应用闭环。
- `T13` 新增了安装版 `--startup-script-test`，能证明 Startup bat 写入当前 EXE 路径和 `--hidden` 后可删除；它没有重启 Windows，因此不算完整开机自启动闭环。
- `T20` 新增了安装版 `--license-network-test`，能证明普通版授权断网不阻塞、受控版服务器不可达时保留本地 token 并给出错误；它没有覆盖系统级断网、弱网和真实 ASR 服务异常。
- 2026-05-14 新增 `--hold-release-auto-insert-test`：证明 `hold` 和 `hold_send` 在释放触发键后会自动调度插入，不需要点击悬浮窗“插入”；取消、空文本以及“松手后很快开始下一段”的延迟插入场景均不会丢上一句。源码证据 `release/test-reports/hold-release-auto-insert.json` 和 `source-self-test-auto-insert.json` 均为 `ok=true`；打包测试 `test-desktop-exe.ps1` 也已覆盖 `dist-hold-release-auto-insert.json`、`portable-hold-release-auto-insert.json`、`installed-hold-release-auto-insert.json`。该项证明释放后的插入逻辑，不替代物理右 Ctrl 热键 + 真实记事本完整验收。
- 2026-05-14 按参考仓库新增托盘启用/禁用和托盘热键展示。源码 `--self-test` 和 `--tray-self-test` 通过，`test-desktop-exe.ps1` 通过 dist/portable 自测、自动插入烟测和托盘烟测；进入安装器隔离测试时被当前 Windows 应用控制策略拦截未签名安装器，安装版后续项本轮不按通过计算。

音频约束：所有音频测试禁止使用电脑扬声器。已使用的输出端点是 `耳机 (2- Realtek(R) Audio)`，输入端点是 `外部麦克风 (2- Realtek(R) Audio)`。测试后确认 `扬声器 (2- Realtek(R) Audio)` 仍为 `volume=0.0, mute=true`。

分发阻断备注：2026-05-13 最后一轮为恢复测试配置/授权状态重新打包后，本机 Windows 11 Smart App Control / Code Integrity 拦截了未签名主 EXE，事件日志提示 `did not meet Enterprise signing level requirements`。在此之前，同轮新增的安装版复杂剪贴板、启动脚本、授权断网测试已跑通；最后一轮源码级对应测试也已跑通。该阻断说明正式外部分发必须做可信代码签名，不能把当前未签名包视为已覆盖所有 Windows 11 安全策略环境。

紧凑 UI 复测备注：2026-05-13 本轮将默认主窗口基准改为 `760x520`，热键行改成“标签 + 输入框 + 录制/选择按钮”的参考图顺序，并同步更新 200% 默认窗口断言。源码布局报告已重新生成并通过本地 JSON 断言：`source-ui-default-layout.json` 为 `root=1519x1039`、`content=1509x934`、`widgets=73`；`source-ui-compact-layout.json` 为 `root=760x567`、`content=754x557`、`widgets=50`；`source-ui-narrow-layout.json` 为 `root=760x567`、`content=754x470`；`source-ui-minimum-layout.json` 为 `root=756x567`、`content=750x557`。这些报告均为 `fits_horizontally=true` 且 `fits_vertically=true`。随后单独重跑 `test-desktop-exe.ps1` 已通过，并重新生成安装版 UI 截图和布局报告。

参考图 UI 复刻备注：2026-05-14，本轮按用户截图将设置页收敛为 `【按着说】模式`、`【自由说】模式`、`【按着说+自动发送】模式`、豆包快捷键、插入延迟、剪贴板保护、开机自启动、高级设置、`保存`、`取消` 和底部状态文案，移除主界面多余按钮和说明。隔离配置安装版布局报告 `installed-reference-ui-default-layout.json`：默认 200% DPI 窗口 `root=783x1294`、`content.right=767`、`content.bottom=1217`，`fits_horizontally=true`、`fits_vertically=true`。2026-05-14 追加调整默认热键，避开 `Ctrl+Q`、`Ctrl+D`、裸字母、鼠标侧键、AltGr 和 Windows 自带语音输入 `Win+H`：`右Ctrl`、`Ctrl+Alt+Space`、`Ctrl+Alt+Enter`、`Esc`、`Ctrl+Alt+D`，延迟仍为 `300/100/50ms`。本轮源码编译、自测、pytest、重打包和 `test-desktop-exe.ps1` 均通过；旧默认迁移烟测输出 `Ctrl+Alt+Space / Ctrl+Alt+Enter / Esc / Ctrl+Alt+D`。

AHK bridge 改造备注：2026-05-14，本轮将主客户端切换为 `xiaohu31/doubao-voice-helper` 风格的 AutoHotkey v2 客户端，Python 新增 `asr_bridge.exe` 只提供本地 HTTP `start/stop/cancel/status/health`。`build-desktop-exe.ps1` 已改为构建 AHK 主程序 `DoubaoASRHelper.exe` 和 Python 后端 `asr_bridge.exe`；便携包和安装包都包含两个 EXE。验证：源码和打包版 bridge self-test 通过，打包版 `/health` 和 `/status` 返回 `ok=true/state=idle`，AHK 主程序启动后能自动拉起 bridge，静默安装目录包含 `DoubaoASRHelper.exe`、`asr_bridge.exe` 和 `install.json`，`test-desktop-exe.ps1` 输出 `AHK bridge desktop tests passed.`。

AHK 悬浮窗和不卡 UI 修复：2026-05-14，新增 `ahk_client/src/float.ahk`，录音期间显示本地悬浮窗并通过 `/status` 轮询实时转写；松手后改用非阻塞 `/stop`，由 AHK 定时器轮询完成状态，避免同步等待 ASR 时冻结主界面。验证：AHK 编译通过，`build-desktop-exe.ps1` 成功，`test-desktop-exe.ps1` 输出 `AHK bridge desktop tests passed.`，`python -m pytest -q` 为 `16 passed`，正式 `dist\DoubaoASRHelper.exe` 启动后仍能自动拉起 `asr_bridge.exe` 且 `/health` 为 `ok=true`。

耳机声学当前复测备注：2026-05-14，本机重新执行耳机声学录回 + ASR，显式选择 `外部麦克风 (2- Realtek(R) Audio)` 输入 index 15 和 `耳机 (2- Realtek(R) Audio)` 输出 index 12，拒绝 `Microsoft 声音映射器 - Output`、所有 `扬声器` 和 `Speakers` 输出端点。报告 `headset-loopback-asr-current.json` 中 `no_pc_speaker_used=true`、`ok=true`，录回 `raw_rms=0.0177557`、`raw_peak=0.77187`、包络相关性 `corr=0.2486`，ASR `recognized_chars=77`、关键词命中 8 个、`errors=[]`。该项当前可按 T11 PASS 计算。

## 汇总表

| 编号 | 测试项 | 状态 | 证据 |
|------|------|------|------|
| T01 | 记事本按着说闭环 | PARTIAL | 核心链路 PASS 但不是完整 EXE 热键闭环：`release/test-reports/e2e-t01-notepad-direct-record.json`，源码 `DesktopApp` 直接录音，真实记事本 + 外部麦克风 + ASR + 插入，插入 70 字并命中 `清晨/早餐/城市/测试`。新增释放自动插入逻辑证据 `release/test-reports/hold-release-auto-insert.json` 和打包 EXE 证据 `dist-hold-release-auto-insert.json`、`portable-hold-release-auto-insert.json`、`installed-hold-release-auto-insert.json`：`hold` 松开后 `inserted[0].auto_send=false`，`hold_send` 松开后 `inserted[0].auto_send=true`，均不需要点击悬浮窗“插入”；快速开始下一段也不会吞掉上一句延迟插入。默认右 Ctrl 物理热键自动化 BLOCKED：`release/test-reports/e2e-t01-notepad-hold.json`，合成键盘事件未驱动打包 EXE 完成录音。 |
| T02 | 浏览器输入框闭环 | NOT_RUN | 未跑。依赖物理热键或更底层输入设备自动化，以及真实浏览器输入窗口；当前合成按键不能作为证据。 |
| T03 | 企业微信/微信聊天框闭环 | NOT_RUN | 未跑。需要登录状态和真实聊天窗口；当前环境没有可安全发送/验证的受控聊天目标。 |
| T04 | 自动发送闭环 | NOT_RUN | 未跑。需要真实可控聊天窗口和物理 `Ctrl+Alt+Enter` 触发，避免误发真实消息。 |
| T05 | 自由说闭环 | NOT_RUN | 未跑。默认 `Ctrl+Alt+Space` 需要真实前台窗口输入闭环；当前合成按键不能作为证据。 |
| T06 | 取消录音闭环 | NOT_RUN | 未跑。需要物理录音触发后按 `Esc` 取消；当前无人值守热键触发层被合成按键限制阻塞。 |
| T07 | 热键录制保存闭环 | PARTIAL | 逻辑规则 PASS：`release/test-reports/e2e-source-self-test.json` 覆盖热键解析、显示、冲突规则和默认恢复。真实 UI 点击“录制”、保存、重启后生效尚未跑。 |
| T08 | 热键冲突弹窗闭环 | PARTIAL | 逻辑规则 PASS：`release/test-reports/e2e-source-self-test.json` 覆盖重复/危险/保留热键检查。真实弹窗交互尚未跑。 |
| T09 | 剪贴板文本保护闭环 | PARTIAL | 新证据 `release/test-reports/installed-clipboard-insert-test.json`：`text_inserted=true`、`clipboard_restored=true`、`restore_delay_ms=500`，目标是临时 Tk 文本框，`paste_method=clipboard helper plus Tk <<Paste>> event`。旧证据 `release/test-reports/e2e-t09-clipboard-text.json` 仍记录真实前台自动化未闭合，`text_inserted=false`。所以该项证明了文本剪贴板保护逻辑，但还不能算“录音 + 外部应用 + 物理热键”完整闭环。 |
| T10 | 剪贴板图片/文件保护闭环 | PARTIAL | 新证据 `release/test-reports/installed-clipboard-complex-test.json`：`ok=true`，`CF_DIB image` 和 `CF_HDROP file list` 两个 case 均 `text_inserted=true`、`format_restored=true`；报告明确跳过 `CF_BITMAP` 和 `CF_DIBV5` 这类 Windows 派生/不可搬运格式。该项仍未覆盖“真实录音 + 物理热键 + 外部应用焦点”的完整闭环，也未覆盖富文本等所有复杂格式。 |
| T11 | 耳机声学闭环 | PASS | 当前证据 `release/test-reports/headset-loopback-asr-current.json`：只用 `耳机 (2- Realtek(R) Audio)` 输出和 `外部麦克风 (2- Realtek(R) Audio)` 输入，`no_pc_speaker_used=true`；明确拒绝声音映射器、`扬声器` 和 `Speakers` 输出。录回 `raw_rms=0.0177557`、`raw_peak=0.77187`、相关性 `0.2486`；ASR `recognized_chars=77`，关键词命中 8 个，`errors=[]`，`ok=true`。旧长文本耳机证据 `headset-loopback-asr.json` 也为 `ok=true`，识别 552 字、关键词 9 个。 |
| T12 | 真人讲话闭环 | NOT_RUN | 未跑。需要真人对外部麦克风说正常音量/小声/长停顿/长句，不能由 TTS 完全替代。 |
| T13 | 开机自启动闭环 | PARTIAL | 新证据 `release/test-reports/installed-startup-script-test.json`：隔离 `APPDATA` 中 Startup bat 创建/删除均成功，内容包含安装版 EXE 路径和 `--hidden`。没有真实重启 Windows，也没有登录后验证托盘、热键和单实例，因此不能算完整 PASS。 |
| T14 | 干净电脑安装包闭环 | NOT_RUN | 未跑。需要一台无 Python、无项目环境的 Win10/Win11。当前机器是开发机，不符合“干净电脑”条件。 |
| T15 | 干净电脑免安装闭环 | NOT_RUN | 未跑。需要一台无 Python、无项目环境的 Win10/Win11。当前机器是开发机，不符合“干净电脑”条件。 |
| T16 | 卸载闭环 | PARTIAL | 新证据 `release/test-reports/isolated-uninstall-cleanup-test.json`：沙箱环境安装成功，开始菜单/桌面快捷方式和启动项均创建；运行卸载脚本后 `uninstall_exit_code=0`、`install_dir_removed=true`、`start_menu_dir_removed=true`、`desktop_shortcut_removed=true`、`startup_bat_removed=true`。该项仍未在真实用户开始菜单/真实开机自启动状态下人工验证，运行中进程处理只由脚本 smoke 覆盖。 |
| T17 | 长时间后台稳定闭环 | NOT_RUN | 未跑。需要 2 到 8 小时后台运行和 50 到 100 次录音。 |
| T18 | 多屏/DPI 真实机器闭环 | PARTIAL | 旧安装版自动化 DPI 截图和布局曾 PASS：`release/test-reports/installed-ui-smoke-scale150-minimum-layout.json`、`installed-ui-smoke-scale200-default-layout.json` 等。本轮紧凑 UI 源码布局 PASS：`source-ui-default-layout.json`、`source-ui-compact-layout.json`、`source-ui-narrow-layout.json`、`source-ui-minimum-layout.json` 均不溢出；但新打包 EXE 被 Windows 应用控制策略阻止，未产出新安装版截图。真实 1080p/2K/4K、多屏、主副屏 DPI 不一致尚未跑。 |
| T19 | 受控激活版闭环 | PARTIAL | 激活逻辑测试 PASS：`test-activation.ps1` 产生 12 passed；强制激活配置自测证据 `release/test-reports/activation-required-self-test.json`。真实受控分发 EXE、换电脑绑定、过期/停用人工流程尚未跑。 |
| T20 | 网络异常闭环 | PARTIAL | 新证据 `release/test-reports/installed-license-network-test.json`：`ordinary_build_ok=true`、`required_build_blocks=true`、`cached_token_preserved=true`，服务器地址为不可达的 `http://127.0.0.1:9`。该项覆盖授权服务器不可达的打包版烟测，但仍未覆盖系统级断网/弱网、真实 ASR 服务异常和完整用户录音流程。 |

## 已完成的基础证据

- 源码自测：`release/test-reports/e2e-source-self-test.json`，状态 PASS；追加 `release/test-reports/source-self-test-auto-insert.json`，新增 `auto_insert` 检查 PASS。
- 按着说释放自动插入烟测：`release/test-reports/hold-release-auto-insert.json`，状态 PASS，覆盖 `hold`、`hold_send`、取消和空文本。
- 打包 EXE/UI/托盘/安装版测试：`test-desktop-exe.ps1` 最新重跑已通过，证据在 `release/test-reports/dist-self-test.json`、`portable-self-test.json`、`installed-self-test.json`、`dist-hold-release-auto-insert.json`、`portable-hold-release-auto-insert.json`、`installed-hold-release-auto-insert.json`、`installed-tray-self-test.json`、`installed-ui-smoke*.json/png`、`installed-clipboard-insert-test.json`、`installed-clipboard-complex-test.json`、`installed-startup-script-test.json`、`installed-license-network-test.json`、`isolated-uninstall-cleanup-test.json`。
- 本机追加验证：在 `64e49f0` 之前的工作区运行过 `build-desktop-exe.ps1`、`test-desktop-exe.ps1`、`test-windows-compat.ps1`、`test-activation.ps1`、`test-license-stress.ps1`、`test-long-text-asr.ps1`。本轮紧凑 UI 后已重新运行 `python -m compileall doubaoime_asr`、`python -m pytest -q`、源码 UI 布局 JSON 断言、源码按钮点击烟测、`build-desktop-exe.ps1`、`test-activation.ps1`、`test-license-stress.ps1`、`test-windows-compat.ps1`、`test-desktop-exe.ps1`、`test-long-text-asr.ps1`。
- 长文本文件 ASR：`release/test-reports/long-text-asr.json`，`ok=true`，识别 556 字，关键词 9 个。
- 耳机声学 ASR：`release/test-reports/headset-loopback-asr-current.json`，`ok=true`，识别 77 字，关键词 8 个；旧长文本证据 `headset-loopback-asr.json` 也为 `ok=true`，识别 552 字，关键词 9 个。

## 后续要真正补齐的项目

优先级最高的是 T01 的物理右 Ctrl 热键人工验收、T02-T06 三种模式在真实目标窗口里的人工验收、T07-T10 的 UI/剪贴板人工验收。T13-T15、T17-T20 仍需要重启、干净电脑、长时间运行、多屏、系统级网络异常或受控授权服务器环境，必须单独安排；T16 已有沙箱卸载清理烟测，但仍建议真实安装后人工点一次。
