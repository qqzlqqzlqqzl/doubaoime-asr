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
| E11 | Windows 兼容性审计 | `test-windows-compat.ps1` 写出 `release\test-reports\windows-compatibility.json`，明确 Win7/Win8.0 不支持、Win8.1 条件兼容、Win10/Win11 为推荐目标 |

### 可选 Win7/Win8 Legacy 包测试

Win7/Win8 不作为主支持目标。只有确实要给老系统用户发实验包时，才需要跑这一组测试；主发版优先看上面的 EXE、安装器、UI 缩放、托盘和兼容性审计。

运行：

```powershell
.\build-desktop-exe-legacy.ps1
.\test-windows-compat-legacy.ps1
```

覆盖项：

| 编号 | 测试项 | 预期 |
|------|------|------|
| W01 | Python 3.8 legacy 源码编译 | `compileall` 通过，证明代码语法可被 Python 3.8 解析 |
| W02 | legacy 依赖安装 | `.venv-win7` 使用 `requirements-win7-legacy.txt` 安装固定版本依赖，不污染主 `.venv` |
| W03 | legacy EXE 自测 | `dist-legacy\DoubaoASRHelper.exe --self-test` 报告 `ok=true` |
| W04 | legacy 托盘自测 | `--tray-self-test` 能创建并删除 Windows 系统托盘图标 |
| W05 | legacy 静态兼容审计 | 报告 `release\test-reports\windows-compatibility-legacy.json`，确认打包运行时使用 `python38.dll` 且不再导入主包里的 Win8.1+ PSS API |
| W06 | legacy 分发包完整性 | `release\legacy` 生成安装包 zip、免安装 zip、README 和 HELP |
| W07 | Win7/Win8 VM 实跑 | 在干净 Win7 SP1 x64、Win8.0 x64、Win8.1 x64 VM 里手工跑启动、托盘、热键、录音、ASR、安装、卸载；当前工作区没有 VM 时标记为未认证 |

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
| U02 | 按住说录音 | 在文本框里按住默认 `rctrl` 说话后松开 | 识别文字插入回原窗口，悬浮窗显示过程状态 |
| U03 | 自由说录音 | 按一次默认 `xbutton1` 开始，再按一次结束 | 录音开始/结束可靠，识别文字插入回原窗口 |
| U04 | 按住+发送 | 在聊天输入框里按住默认 `lctrl+lwin` 后松开 | 识别文字插入并按发送延迟触发 Enter |
| U05 | 取消录音 | 录音过程中按默认 `z` | 本次输入取消，不插入也不自动发送 |
| U06 | 快捷键自定义 | 点击“录制”并输入新组合键后保存 | 配置保存成功，重启后仍生效 |
| U07 | 快捷键冲突 | 配置重复快捷键 | 弹窗提示冲突，不能保存重复配置 |
| U08 | 悬浮窗操作 | 录音后在悬浮窗点击清空、复制、插入 | 三个操作都生效，窗口不遮挡主流程 |
| U09 | 帮助文档 | 打开“使用说明”和 release `HELP.md` | 能看到首次运行、默认快捷键、系统托盘、长文本测试和卸载说明 |
| U10 | 延迟设置 | 调整插入延迟、发送延迟并保存后重启 | 数值保持在允许范围内，滑块和输入框同步显示 |
| U11 | UI 截图复核 | 打开 `release\test-reports\installed-ui-smoke.png`、`installed-ui-smoke-narrow.png`、`installed-ui-smoke-minimum.png` 和对应 `*-layout.json`，再查看 `installed-ui-smoke-scale150-minimum-layout.json`、`installed-ui-smoke-scale200-narrow-layout.json`、`installed-ui-smoke-scale200-minimum-layout.json`、`installed-ui-smoke-scale200-default-layout.json` | 主界面没有滚动条，文字、输入框、录制按钮和底部操作按钮不被截断，窄窗口、最小窗口、150% 和 200% 缩放下控件自动压缩和重排，200% 默认窗口不是小窗，布局报告显示 `fits_horizontally=true` 且 `fits_vertically=true` |
| U12 | 系统托盘后台运行 | 点击主窗口 X 或“隐藏窗口”，再点击/右键托盘图标 | 主窗口隐藏后进程继续运行；左键托盘图标恢复窗口；右键菜单可显示、隐藏、打开配置目录和退出 |

## 发版前建议

1. 先跑 `.\test-activation.ps1`。
2. 跑 `.\test-license-stress.ps1`。
3. 再按正式授权服务器设置环境变量，跑 `.\build-desktop-exe.ps1`。
4. 跑 `.\test-desktop-exe.ps1`。
5. 如果确实需要老系统实验包，再跑 `.\build-desktop-exe-legacy.ps1` 和 `.\test-windows-compat-legacy.ps1`，并放进 Win7/Win8 VM 实跑；这一步不阻塞 Win10/Win11 主包发版。
6. 有 ASR 凭据时跑 `.\test-long-text-asr.ps1`。
7. 手工验收 U01-U12，重点看首次启动无登录/授权弹窗、语音输入闭环、主界面缩放截图和系统托盘后台运行。
