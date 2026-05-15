# 测试项清单

## 自动化测试

### 授权源码测试

运行：

```powershell
.\test-activation.ps1
```

覆盖项：

| 编号 | 测试项 | 预期 |
|------|------|------|
| A01 | 默认开发配置 | 不强制激活，`verify_license` 返回通过 |
| A02 | 环境变量覆盖授权配置 | `DOUBAO_ASR_REQUIRE_ACTIVATION` 和 `DOUBAO_ASR_LICENSE_URL` 生效，URL 会去掉尾部 `/` |
| A03 | 强制激活但未配置服务器 | 返回明确错误，不崩溃 |
| A04 | 正常激活闭环 | 未激活时失败，输入有效激活码后保存 token，再次校验通过 |
| A05 | 无效激活码 | 返回 `UNKNOWN_CODE`，不写入本地授权状态 |
| A06 | 激活码设备数上限 | 第二台设备被拒绝，返回 `DEVICE_LIMIT` |
| A07 | 停用激活码 | 返回 `DISABLED_CODE` |
| A08 | 过期激活码 | 返回 `EXPIRED_CODE` |
| A09 | 复制授权文件到另一台电脑 | 设备码不匹配，本地授权被清理 |
| A10 | 授权服务器地址变更 | 本地旧授权被清理，要求重新激活 |
| A11 | token 被篡改 | 返回 `BAD_TOKEN`，本地授权被清理 |
| A12 | 授权服务器临时不可达 | 返回校验失败，但保留本地 token，避免误删有效授权 |

### 授权服务器压力测试

运行：

```powershell
.\test-license-stress.ps1
```

覆盖项：

| 编号 | 测试项 | 预期 |
|------|------|------|
| S01 | 单设备激活码并发激活 | 64 个不同设备同时抢同一个单设备码时，只有 1 个成功，其余返回 `DEVICE_LIMIT` |
| S02 | 同一设备重复激活幂等 | 64 个并发请求使用同一设备码和同一激活码时全部成功，不增加设备数 |
| S03 | token 并发校验 | 200 个并发校验请求全部通过 |
| S04 | 无效码并发请求 | 64 个无效激活码请求全部返回 `UNKNOWN_CODE` |
| S05 | 压测报告 | 写出 `release\test-reports\license-stress.json`，包含成功数、失败数、状态码分布和延迟统计 |

### EXE 和安装器测试

运行：

```powershell
.\build-desktop-exe.ps1
.\test-desktop-exe.ps1
.\test-windows-compat.ps1
```

覆盖项：

| 编号 | 测试项 | 预期 |
|------|------|------|
| E01 | `dist\asr_bridge.exe --self-test` | bridge 自测退出码为 0 |
| E02 | AHK 主客户端启动烟测 | `dist\DoubaoASRHelper.exe` 启动后能自动拉起 `asr_bridge.exe`，`/health` 返回 `ok=true` |
| E03 | 强制激活配置自测 | 报告里 `license_config.require_activation=true`，未激活状态不让主流程通过 |
| E04 | 分发 zip 完整性 | 完整包包含安装器、便携版、README 和 HELP；免安装包包含便携版、README 和 HELP |
| E05 | 安装器静默安装 | 安装到临时目录成功 |
| E06 | 安装后 EXE 自测 | 安装目录同时包含 `DoubaoASRHelper.exe` 和 `asr_bridge.exe`，bridge 自测通过 |
| E07 | 安装后 AHK 设置页截图 | 启动安装目录里的 `DoubaoASRHelper.exe`，确认首次运行设置页使用 `xiaohu31/doubao-voice-helper` 上游 AHK 布局：`Gui("+Resize -MaximizeBox")`、`SetFont("s10", "Microsoft YaHei")`、`Show("w400 h630")`；保存 DPI-aware 截图到 `release\test-reports\installed-ahk-settings-reference-restored-dpiaware.png`，并确认三种模式、豆包快捷键、插入延迟、剪贴板保护/开机自启动、高级设置、保存/取消和状态栏完整可见 |
| E08 | 托盘图标烟测 | `--tray-self-test` 能创建并删除 Windows 系统托盘图标，报告 `started=true`、`stopped=true` |
| E09 | 关闭窗口后台保活 | 对安装后主窗口发送关闭消息后，进程保持运行且主窗口不可见 |
| E10 | 安装后后台保活烟测 | `--hidden` 启动后进程保持运行，主窗口隐藏时可通过系统托盘继续后台监听 |
| E10b | 托盘启用/禁用与热键展示 | 右键托盘菜单显示启用状态和当前热键；切到禁用后全局录音热键不启动录音，再切回启用恢复 |
| E11 | Windows 兼容性审计 | `test-windows-compat.ps1` 写出 `release\test-reports\windows-compatibility.json`，明确 Win10/Win11 为正式目标、Win7/Win8 不支持 |
| E12 | 悬浮窗长文本布局 | `--float-layout-test` 写出 `installed-float-layout-long-text.json`，断言类似实测截图长度的识别文本可完整显示且窗口不超出屏幕 |
| E13 | 普通打字和误触发热键保护 | `--self-test` 断言裸字母/数字、危险单修饰键、带额外按键的近似组合都不能作为空闲状态启动录音的全局快捷键，避免输入 `xian` 或按 `Ctrl + Alt + D` 时误触发 |
| E14 | 按住说松开清理 | `--self-test` 断言通用 `Ctrl/Win` 松开事件能停止左右修饰键触发的按住说，且按住说/按住+发送松开后不会继续弹出悬浮窗；旧 ASR 会话回调会被忽略 |
| E15 | 单实例托盘保护 | 启动安装版隐藏实例后再启动便携版，第二个进程必须快速退出，系统里只保留一个豆包 ASR 进程和一个托盘图标 |
| E16 | 字号和对齐一致性 | UI 布局报告断言标题字号不压过输入控件、三种模式块内的触发键/取消键 entry 和录制按钮纵向对齐、设置标签高度一致、说明文字对齐到对应标签下方，剪贴板保护/开机自启动开关不退回默认小 checkbox，避免主界面出现明显大小不一和列错位 |
| E17 | 剪贴板文本插入/恢复烟测 | 安装版运行 `--clipboard-insert-test`，写出 `installed-clipboard-insert-test.json`，断言临时文本框成功粘贴测试文本且剪贴板恢复为原文本；该项不等价于真实录音热键闭环 |
| E18 | 隔离卸载清理烟测 | 安装器在临时 `APPDATA`、`LOCALAPPDATA`、`USERPROFILE` 沙箱中创建快捷方式和启动项，再运行卸载脚本，写出 `isolated-uninstall-cleanup-test.json` 或 `installer-uninstall-startup-cleanup.json` 并断言安装目录、开始菜单、桌面快捷方式、旧 `doubaoime-asr.bat` 和当前 `豆包语音助手.lnk` 启动项都被清理 |
| E19 | 剪贴板图片/文件格式恢复烟测 | 安装版运行 `--clipboard-complex-test`，写出 `installed-clipboard-complex-test.json`，断言 `CF_DIB` 图片剪贴板和 `CF_HDROP` 文件列表在临时文本插入后恢复；跳过 Windows 自动派生的 `CF_BITMAP/CF_DIBV5`，避免冻结 EXE 读取不可搬运句柄 |
| E20 | 开机启动脚本无重启烟测 | 安装版运行 `--startup-script-test`，写出 `installed-startup-script-test.json`，在隔离 `APPDATA` 中验证 Startup bat 会写入当前 EXE 路径和 `--hidden`，取消后能删除；该项不等价于真实重启闭环 |
| E21 | 授权断网打包版烟测 | 安装版运行 `--license-network-test`，写出 `installed-license-network-test.json`，验证普通版不受授权断网影响，受控版服务器不可达时阻止使用但保留本地 token |
| E22 | AHK 旧配置迁移烟测 | `test-desktop-exe.ps1` 在隔离 `APPDATA` 下预置旧目录 `%APPDATA%\DouBaoVoiceHelper\config.ini` | AHK 主客户端启动后创建 `%APPDATA%\DoubaoASRHelper\config.ini`，并把旧默认 `XButton1/F9/F12/Ctrl+Alt+Shift+D` 迁移为 `Ctrl+Alt+Space/Ctrl+Alt+Enter/Esc/Ctrl+Alt+D`，`ConfigVersion=3` |
| E23 | 上游差异审计复核 | 阅读 [UPSTREAM_DIFF_AUDIT.md](UPSTREAM_DIFF_AUDIT.md)，并用两个参考仓库当前 HEAD 对照源码 | 每个新增/修改/保留差异都有 why；解释不成立的差异必须修复或补测试，不能只写文档掩盖 |
| E24 | AHK 悬浮窗可见性烟测 | `test-desktop-exe.ps1` 启动 `DoubaoASRHelper.exe --float-self-test` 并枚举 Win32 窗口及子控件 | 能找到可见的 `DoubaoASRHelperFloat`，窗口宽高达到阈值，识别结果框内出现测试文本，并且不能枚举到 `清空`、`复制`、`插入` 三个手动操作，报告写入 `release\test-reports\ahk-float-self-test.json` |
| E25 | 崩溃排查日志烟测 | `test-desktop-exe.ps1` 在隔离 `APPDATA` 中运行 bridge self-test 和 AHK float self-test | 生成 `client-YYYYMMDD.log` 和 `asr_bridge-YYYYMMDD.log`，并包含关键事件如 `float_self_test_start`、`self_test_ok` |
| E26 | 首屏 500ms 完整 UI 性能 | `test-startup-performance.ps1` 启动安装版或免安装版 EXE，并枚举设置页子控件 | 设置页窗口和 `【按着说】模式`、`【自由说】模式`、`【按着说+自动发送】模式`、`高级设置`、`保存`、`取消`、`状态: ● 已就绪` 全部在 `500ms` 内出现；报告写入 `release\test-reports\startup-performance*.json` |
| E27 | AHK 启动体检与冲突自愈烟测 | `test-desktop-exe.ps1` 运行 `DoubaoASRHelper.exe selftest --startup-doctor-test --startup-doctor-report ...`，或单独运行源码/安装版同名参数 | 报告 `ok=true`，旧启动 bat 被删除、重复快捷方式被删除、无关文件保留、标准 `豆包语音助手.lnk` 带 `--hidden`、重复/危险热键恢复默认；真实重启仍归入 T13 手工闭环 |

### 上游差异审计测试

这类测试用于防止项目偏离两个参考仓库后没人知道原因。它不是运行时功能测试，但每次大改架构、热键、打包或 AHK 客户端时都要做。

| 编号 | 测试项 | 操作 | 预期 |
|------|------|------|------|
| D01 | ASR 上游基线确认 | `git ls-remote https://github.com/yangmoling/doubaoime-asr.git HEAD` | 文档记录的 commit 和实际审计时使用的 commit 一致，或明确说明更新原因 |
| D02 | AHK 上游基线确认 | `git ls-remote https://github.com/xiaohu31/doubao-voice-helper.git HEAD` | 文档记录的 commit 和实际审计时使用的 commit 一致，或明确说明更新原因 |
| D03 | 文件级差异解释 | 对照 `git ls-files` 和 `UPSTREAM_DIFF_AUDIT.md` | 新增、修改、删除、保留文件都能在文档中找到解释 |
| D04 | 无理由 drift 修复 | 对解释不通的 diff 做代码修复 | 修复后必须补对应自动化或 smoke 证据，例如配置迁移、默认配置、DLL 搜索路径 |
| D05 | 文档闭环 | 更新 `CHANGELOG.md`、`README.md`、`HANDOFF.md`、`REFERENCE_PARITY.md` | 接手者不需要翻聊天记录即可理解这一版为什么这样做 |

### 长文本 ASR 测试

运行：

```powershell
.\test-long-text-asr.ps1
```

覆盖项：

| 编号 | 测试项 | 预期 |
|------|------|------|
| L01 | 约 500 字中文样本生成 | 生成 WAV 样本，包含停顿和音量高低起伏 |
| L02 | 打包 EXE 调用 ASR | 报告 `ok=true` |
| L03 | 识别长度门槛 | 识别字数达到脚本设定阈值 |
| L04 | 关键词命中门槛 | 命中关键词数达到脚本设定阈值 |
| L05 | 授权状态写入报告 | 报告包含 `license_config` 和 `license_state` |

## 手工验收测试

这些项目不适合完全自动化，发版前建议人工点一遍：

| 编号 | 测试项 | 操作 | 预期 |
|------|------|------|------|
| U01 | 首次启动桌面版 | 启动普通安装版 EXE | 直接进入主界面，不弹登录或授权窗口 |
| U02 | 按住说录音 | 在文本框里按住默认 `右Ctrl` 说话后松开 | 识别文字插入回原窗口，悬浮窗只显示录音过程，松开后自动收起 |
| U03 | 自由说录音 | 按一次默认 `Ctrl+Alt+Space` 开始，再按一次结束 | 录音开始/结束可靠，识别文字插入回原窗口 |
| U04 | 按住+发送 | 在聊天输入框里按住默认 `Ctrl+Alt+Enter` 后松开 | 识别文字插入并按发送延迟触发 Enter |
| U05 | 取消录音 | 录音过程中按默认 `Esc` | 本次输入取消，不插入也不自动发送 |
| U06 | 快捷键自定义 | 点击“录制”并输入新组合键后保存 | 配置保存成功，重启后仍生效 |
| U07 | 快捷键冲突 | 配置重复快捷键、裸字母键或 Windows 保留组合键，例如 `Alt + Tab` | 弹窗提示冲突或不可用风险，不能保存问题配置 |
| U08 | 默认值复核 | 清空配置后首次启动设置页 | 默认值显示为 `右Ctrl`、`Ctrl+Alt+Space`、`Ctrl+Alt+Enter`、`Esc`、`Ctrl+Alt+D`、插入延迟 `0.3 秒`、剪贴板超时 `100ms`、发送延迟 `50ms` |
| U09 | 悬浮窗结果态 | 录音后查看悬浮窗结果态 | 结果态像输入框一样显示识别文本，不出现 `清空`、`复制`、`插入` 手动按钮；松开按键后自动插入并收起 |
| U10 | 帮助文档 | 打开“使用说明”和 release `HELP.md` | 能看到首次运行、默认快捷键、系统托盘、长文本测试和卸载说明 |
| U11 | 延迟设置 | 调整插入延迟、剪贴板超时、发送延迟并保存后重启 | 数值保持在允许范围内，插入延迟滑块按 50ms 吸附并显示秒数，两个高级延迟输入框按 50ms 吸附 |
| U12 | UI 截图复核 | 打开 `release\test-reports\installed-ahk-settings-reference-restored-dpiaware.png` 和 `source-ahk-settings-reference-restored.png`；再用 `git diff --no-index .devtools\reference\doubao-voice-helper\src\gui.ahk ahk_client\src\gui.ahk` 复核当前差异 | 设置页应按 `xiaohu31/doubao-voice-helper` 的 AHK 上游布局显示三种模式块、豆包快捷键、插入延迟、剪贴板保护、开机自启动、高级设置、保存/取消和状态；视觉布局 diff 应为零，允许保留 `Space/Enter/Esc/...` 热键显示与反向转换兼容 |
| U13 | 系统托盘后台运行 | 点击主窗口 X 或“取消”，再点击/右键托盘图标 | 主窗口隐藏后进程继续运行；左键托盘图标恢复窗口；右键菜单可显示、隐藏、打开配置目录和退出 |
| U14 | 重复启动保护 | 已经运行后再次双击安装版、免安装版或开机自启动脚本 | 不出现第二个主窗口和第二个托盘图标；已有窗口被唤醒或保持后台运行 |

## 端到端闭环测试清单

这些项目用于确认用户拿到 EXE 后的真实可用性。音频相关测试必须显式选择耳机输出，禁止使用电脑扬声器、默认声音映射器或任何名称包含 `扬声器` / `speaker` 的输出端点。

| 编号 | 测试项 | 操作 | 预期 |
|------|------|------|------|
| T01 | 记事本按着说闭环 | 打开记事本，放好光标，按住默认 `右Ctrl` 说一句，松开 | 识别文本自动插入记事本，不需要点击悬浮窗“插入”；悬浮窗在松开后自动收起 |
| T02 | 浏览器输入框闭环 | 在浏览器文本框里用按着说输入一段 30 字以上文本 | 文本插入到正确输入框，不跳焦点，不覆盖其他窗口 |
| T03 | 企业微信/微信聊天框闭环 | 在聊天输入框用按着说输入，不自动发送 | 文本只进入输入框，不误发消息 |
| T04 | 自动发送闭环 | 在可控聊天窗口按住 `Ctrl+Alt+Enter` 说话后松开 | 文本插入后按发送延迟触发 Enter；只发送一次 |
| T05 | 自由说闭环 | 按默认 `Ctrl+Alt+Space` 开始，说两段有停顿的话，再按一次结束 | 识别文本合并插入；开始/结束状态清楚，没有残留录音 |
| T06 | 取消录音闭环 | 录音中按 `Esc` | 本次结果丢弃，不插入、不发送，悬浮窗收起 |
| T07 | 热键录制保存闭环 | 点某个“录制”，输入新组合键，保存，退出重启，再用新热键录音 | 新热键生效，旧热键不再触发，配置重启后保留 |
| T08 | 热键冲突弹窗闭环 | 尝试保存重复热键、裸字母热键、`Alt + Tab` 等保留组合键 | 保存被阻止并弹出明确提示，不写入坏配置 |
| T09 | 剪贴板文本保护闭环 | 复制一段原文本，开启剪贴板保护后录音插入 | 识别文本插入成功，原文本剪贴板恢复 |
| T10 | 剪贴板图片/文件保护闭环 | 剪贴板放图片或文件后录音插入 | 程序不崩溃；若复杂剪贴板不能完整恢复，行为和说明一致 |
| T11 | 耳机声学闭环 | 显式使用 `耳机 (2- Realtek(R) Audio)` 播放测试样本，用 `外部麦克风 (2- Realtek(R) Audio)` 录回并送 ASR | 不使用电脑扬声器；报告记录设备名、耳机音量恢复状态、录回音频相关性、识别字数和关键词 |
| T12 | 真人讲话闭环 | 使用外部麦克风真人说正常音量、小声、长停顿和长句 | ASR 能返回可用文本；停顿后仍保留上下文顺序 |
| T13 | 开机自启动闭环 | 勾选开机自启动，重启 Windows 后登录 | 程序后台启动并出现在托盘，不弹前台窗口，热键可用，不出现双实例 |
| T14 | 干净电脑安装包闭环 | 在无 Python/无项目环境的 Win10/Win11 上运行安装器 | 安装成功，快捷方式/图标/帮助可用，首次启动能创建配置和凭据 |
| T15 | 干净电脑免安装闭环 | 在无 Python/无项目环境的 Win10/Win11 上直接运行便携版 | 免安装启动成功，托盘、热键、帮助和配置目录正常 |
| T16 | 卸载闭环 | 安装后启用开机自启动，再运行卸载 | 开始菜单/桌面快捷方式和启动项按预期清理；运行中进程处理正常 |
| T17 | 长时间后台稳定闭环 | 后台运行 2 到 8 小时，中间录音 50 到 100 次 | 托盘不丢失，热键不失效，悬浮窗不残留，内存/句柄无异常增长 |
| T18 | 多屏/DPI 真实机器闭环 | 在 1080p 150%、2K 150%、4K 200%、多显示器环境分别启动 | UI 不需要滚动条，控件不截断，窗口大小符合 DPI，拖动不卡顿 |
| T19 | 受控激活版闭环 | 打包强制激活版，输入有效/无效/过期/停用激活码，并换电脑验证设备绑定 | 未激活不能使用；有效码绑定本机；换电脑、过期、停用都有明确提示 |
| T20 | 网络异常闭环 | 断网或授权服务器不可达时启动、录音、验证授权状态 | 普通版核心录音不受影响；受控版提示明确，不误删本地有效授权 |

## 发版前建议

1. 先跑 `.\test-activation.ps1`。
2. 跑 `.\test-license-stress.ps1`。
3. 再按正式授权服务器设置环境变量，跑 `.\build-desktop-exe.ps1`。
4. 跑 `.\test-desktop-exe.ps1`。
5. 有 ASR 凭据时跑 `.\test-long-text-asr.ps1`。
6. 手工验收 U01-U14，重点看首次启动无登录/授权弹窗、语音输入闭环、主界面缩放截图、一键恢复默认和系统托盘后台运行。
7. 发外部用户前至少补跑 T01-T12；正式分发前再补 T13-T20。
