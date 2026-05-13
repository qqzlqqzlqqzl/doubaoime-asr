# 端到端闭环测试证据

运行日期：2026-05-13

结论：没有全部测完。当前环境已经跑完一部分能自动化闭合的链路；需要真人按键、真实外部应用、重启、干净电脑、长时间运行或受控授权服务器的项目，下面明确标为 `BLOCKED` 或 `NOT_RUN`，不按通过计算。

自查修正：

- `release/test-reports/*` 被 `.gitignore` 忽略，只是本机证据，不会随 GitHub 提交保存。下面的表格保留本机路径，同时把关键数值写进本文档，避免只有不可追溯的本地文件引用。
- `T01-direct` 使用源码里的 `DesktopApp` 直接调起录音流程，不是打包 EXE 的完整热键闭环，也绕过了物理 `右 Ctrl` 热键层。它只能证明“真实记事本 + 外部麦克风 + ASR + 插入”这段核心链路，不证明用户双击 EXE 后按默认热键可用。
- `T11` 是耳机声学链路和 ASR 服务闭环，不是桌面 UI/热键/插入目标应用的完整闭环。
- `T09` 只能证明文本剪贴板恢复路径生效，不能证明目标应用粘贴闭环通过；当前自动化里 `text_inserted=false`。

音频约束：所有音频测试禁止使用电脑扬声器。已使用的输出端点是 `耳机 (2- Realtek(R) Audio)`，输入端点是 `外部麦克风 (2- Realtek(R) Audio)`。测试后确认 `扬声器 (2- Realtek(R) Audio)` 仍为 `volume=0.0, mute=true`。

## 汇总表

| 编号 | 测试项 | 状态 | 证据 |
|------|------|------|------|
| T01 | 记事本按着说闭环 | PARTIAL | 核心链路 PASS 但不是完整 EXE 热键闭环：`release/test-reports/e2e-t01-notepad-direct-record.json`，源码 `DesktopApp` 直接录音，真实记事本 + 外部麦克风 + ASR + 插入，插入 70 字并命中 `清晨/早餐/城市/测试`。默认右 Ctrl 物理热键自动化 BLOCKED：`release/test-reports/e2e-t01-notepad-hold.json`，合成键盘事件未驱动打包 EXE 完成录音。 |
| T02 | 浏览器输入框闭环 | NOT_RUN | 未跑。依赖物理热键或更底层输入设备自动化，以及真实浏览器输入窗口；当前合成按键不能作为证据。 |
| T03 | 企业微信/微信聊天框闭环 | NOT_RUN | 未跑。需要登录状态和真实聊天窗口；当前环境没有可安全发送/验证的受控聊天目标。 |
| T04 | 自动发送闭环 | NOT_RUN | 未跑。需要真实可控聊天窗口和物理 `左 Ctrl + 左 Win` 触发，避免误发真实消息。 |
| T05 | 自由说闭环 | NOT_RUN | 未跑。默认 `鼠标侧键 1` 需要真实鼠标侧键输入或底层 HID 自动化。 |
| T06 | 取消录音闭环 | NOT_RUN | 未跑。需要物理录音触发后按 `Esc` 取消；当前无人值守热键触发层被合成按键限制阻塞。 |
| T07 | 热键录制保存闭环 | PARTIAL | 逻辑规则 PASS：`release/test-reports/e2e-source-self-test.json` 覆盖热键解析、显示、冲突规则和默认恢复。真实 UI 点击“录制”、保存、重启后生效尚未跑。 |
| T08 | 热键冲突弹窗闭环 | PARTIAL | 逻辑规则 PASS：`release/test-reports/e2e-source-self-test.json` 覆盖重复/危险/保留热键检查。真实弹窗交互尚未跑。 |
| T09 | 剪贴板文本保护闭环 | PARTIAL | `release/test-reports/e2e-t09-clipboard-text.json` 显示 `clipboard_restored=true`；但目标应用插入未闭合，`text_inserted=false`，需人工点测或补更可靠的前台窗口自动化。 |
| T10 | 剪贴板图片/文件保护闭环 | NOT_RUN | 未跑。需要准备图片/文件剪贴板并人工判断复杂格式恢复行为。 |
| T11 | 耳机声学闭环 | PASS | `release/test-reports/headset-loopback-asr.json`：只用耳机输出和外部麦克风输入；`recognized_chars=552`、关键词 9 个、相关性 `0.7176`、`ok=true`。这证明音频和 ASR 闭环，不证明桌面热键/插入闭环。 |
| T12 | 真人讲话闭环 | NOT_RUN | 未跑。需要真人对外部麦克风说正常音量/小声/长停顿/长句，不能由 TTS 完全替代。 |
| T13 | 开机自启动闭环 | NOT_RUN | 未跑。需要真实重启 Windows 并登录后验证后台托盘、热键和单实例。 |
| T14 | 干净电脑安装包闭环 | NOT_RUN | 未跑。需要一台无 Python、无项目环境的 Win10/Win11。当前机器是开发机，不符合“干净电脑”条件。 |
| T15 | 干净电脑免安装闭环 | NOT_RUN | 未跑。需要一台无 Python、无项目环境的 Win10/Win11。当前机器是开发机，不符合“干净电脑”条件。 |
| T16 | 卸载闭环 | NOT_RUN | 未跑。需要先完成安装状态，再验证快捷方式、启动项和运行中进程处理。 |
| T17 | 长时间后台稳定闭环 | NOT_RUN | 未跑。需要 2 到 8 小时后台运行和 50 到 100 次录音。 |
| T18 | 多屏/DPI 真实机器闭环 | PARTIAL | 自动化 DPI 截图和布局 PASS：`release/test-reports/installed-ui-smoke-scale150-minimum-layout.json`、`installed-ui-smoke-scale200-default-layout.json` 等。真实 1080p/2K/4K、多屏、主副屏 DPI 不一致尚未跑。 |
| T19 | 受控激活版闭环 | PARTIAL | 激活逻辑测试 PASS：`test-activation.ps1` 产生 12 passed；强制激活配置自测证据 `release/test-reports/activation-required-self-test.json`。真实受控分发 EXE、换电脑绑定、过期/停用人工流程尚未跑。 |
| T20 | 网络异常闭环 | NOT_RUN | 未跑。需要断网或授权服务器不可达环境，分别验证普通版和受控版行为。 |

## 已完成的基础证据

- 源码自测：`release/test-reports/e2e-source-self-test.json`，状态 PASS。
- 打包 EXE/UI/托盘/安装版测试：`test-desktop-exe.ps1` 已通过，证据在 `release/test-reports/dist-self-test.json`、`portable-self-test.json`、`installed-self-test.json`、`installed-tray-self-test.json`、`installed-ui-smoke*.json/png`。
- 长文本文件 ASR：`release/test-reports/long-text-asr.json`，`ok=true`，识别 556 字，关键词 9 个。
- 耳机声学 ASR：`release/test-reports/headset-loopback-asr.json`，`ok=true`，识别 552 字，关键词 9 个。

## 后续要真正补齐的项目

优先级最高的是 T01 的物理右 Ctrl 热键人工验收、T02-T06 三种模式在真实目标窗口里的人工验收、T07-T10 的 UI/剪贴板人工验收。T13-T20 需要重启、干净电脑、长时间运行、多屏或授权服务器环境，必须单独安排。
