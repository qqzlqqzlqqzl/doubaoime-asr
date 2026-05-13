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
| E01 | `dist\DoubaoASRHelper.exe --self-test` | 自测报告 `ok=true` |
| E02 | `release\DoubaoASRHelper-portable.exe --self-test` | 自测报告 `ok=true` |
| E03 | 强制激活配置自测 | 报告里 `license_config.require_activation=true`，未激活状态不让主流程通过 |
| E04 | 分发 zip 完整性 | 完整包包含安装器、便携版、README 和 HELP；免安装包包含便携版、README 和 HELP |
| E05 | 安装器静默安装 | 安装到临时目录成功 |
| E06 | 安装后 EXE 自测 | 安装目录里的 EXE 自测通过 |
| E07 | 安装后可见 UI 截图和布局报告 | 启动可见窗口并写出 `release\test-reports\installed-ui-smoke.png`、`installed-ui-smoke-narrow.png`、`installed-ui-smoke-minimum.png`、`installed-ui-smoke-scale200-default.png` 及对应 `*-layout.json`，自动断言正常/窄/最小窗口下主界面不需要滚动、控件不溢出、输入框和底部按钮都在单页可见区域内；同时用 `--ui-scale-factor` 模拟 150% 和 200% 缩放并断言布局仍不溢出、200% 控件物理尺寸不偏小，200% 默认窗口会按 DPI 放大而不是停留在固定 `900x680` |
| E08 | 托盘图标烟测 | `--tray-self-test` 能创建并删除 Windows 系统托盘图标，报告 `started=true`、`stopped=true` |
| E09 | 关闭窗口后台保活 | 对安装后主窗口发送关闭消息后，进程保持运行且主窗口不可见 |
| E10 | 安装后后台保活烟测 | `--hidden` 启动后进程保持运行，主窗口隐藏时可通过系统托盘继续后台监听 |
| E11 | Windows 兼容性审计 | `test-windows-compat.ps1` 写出 `release\test-reports\windows-compatibility.json`，明确 Win10/Win11 为正式目标、Win7/Win8 不支持 |
| E12 | 悬浮窗长文本布局 | `--float-layout-test` 写出 `installed-float-layout-long-text.json`，断言类似实测截图长度的识别文本可完整显示且窗口不超出屏幕 |
| E13 | 普通打字和误触发热键保护 | `--self-test` 断言裸字母/数字、危险单修饰键、带额外按键的近似组合都不能作为空闲状态启动录音的全局快捷键，避免输入 `xian` 或按 `Ctrl + Alt + D` 时误触发 |
| E14 | 按住说松开清理 | `--self-test` 断言通用 `Ctrl/Win` 松开事件能停止左右修饰键触发的按住说，且按住说/按住+发送松开后不会继续弹出悬浮窗；旧 ASR 会话回调会被忽略 |

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
| U02 | 按住说录音 | 在文本框里按住默认 `右 Ctrl` 说话后松开 | 识别文字插入回原窗口，悬浮窗只显示录音过程，松开后自动收起 |
| U03 | 自由说录音 | 按一次默认 `鼠标侧键 1` 开始，再按一次结束 | 录音开始/结束可靠，识别文字插入回原窗口 |
| U04 | 按住+发送 | 在聊天输入框里按住默认 `左 Ctrl + 左 Win` 后松开 | 识别文字插入并按发送延迟触发 Enter |
| U05 | 取消录音 | 录音过程中按默认 `Esc` | 本次输入取消，不插入也不自动发送 |
| U06 | 快捷键自定义 | 点击“录制”并输入新组合键后保存 | 配置保存成功，重启后仍生效 |
| U07 | 快捷键冲突 | 配置重复快捷键、裸字母键或 Windows 保留组合键，例如 `Alt + Tab` | 弹窗提示冲突或不可用风险，不能保存问题配置 |
| U08 | 一键恢复默认 | 修改快捷键、延迟、剪贴板保护和开机自启动后点击“恢复默认” | 热键、延迟、剪贴板保护和启动项回到初始值并保存；凭据文件路径保留 |
| U09 | 悬浮窗操作 | 录音后在悬浮窗点击清空、复制、插入 | 三个操作都生效，窗口不遮挡主流程 |
| U10 | 帮助文档 | 打开“使用说明”和 release `HELP.md` | 能看到首次运行、默认快捷键、系统托盘、长文本测试、一键恢复默认和卸载说明 |
| U11 | 延迟设置 | 调整插入延迟、发送延迟并保存后重启 | 数值保持在允许范围内，滑块和输入框同步显示 |
| U12 | UI 截图复核 | 打开 `release\test-reports\installed-ui-smoke.png`、`installed-ui-smoke-narrow.png`、`installed-ui-smoke-minimum.png` 和对应 `*-layout.json`，再查看 `installed-ui-smoke-scale150-minimum-layout.json`、`installed-ui-smoke-scale200-narrow-layout.json`、`installed-ui-smoke-scale200-minimum-layout.json`、`installed-ui-smoke-scale200-default-layout.json` | 主界面没有滚动条，文字、输入框、录制按钮和底部操作按钮不被截断，窄窗口、最小窗口、150% 和 200% 缩放下控件自动压缩和重排，200% 默认窗口不是小窗，布局报告显示 `fits_horizontally=true` 且 `fits_vertically=true` |
| U13 | 系统托盘后台运行 | 点击主窗口 X 或“隐藏窗口”，再点击/右键托盘图标 | 主窗口隐藏后进程继续运行；左键托盘图标恢复窗口；右键菜单可显示、隐藏、打开配置目录和退出 |

## 发版前建议

1. 先跑 `.\test-activation.ps1`。
2. 跑 `.\test-license-stress.ps1`。
3. 再按正式授权服务器设置环境变量，跑 `.\build-desktop-exe.ps1`。
4. 跑 `.\test-desktop-exe.ps1`。
5. 有 ASR 凭据时跑 `.\test-long-text-asr.ps1`。
6. 手工验收 U01-U13，重点看首次启动无登录/授权弹窗、语音输入闭环、主界面缩放截图、一键恢复默认和系统托盘后台运行。
