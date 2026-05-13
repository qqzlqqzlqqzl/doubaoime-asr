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
```

覆盖项：

| 编号 | 测试项 | 预期 |
|------|------|------|
| E01 | `dist\DoubaoASRHelper.exe --self-test` | 自测报告 `ok=true` |
| E02 | `release\DoubaoASRHelper-portable.exe --self-test` | 自测报告 `ok=true` |
| E03 | 强制激活配置自测 | 报告里 `license_config.require_activation=true`，未激活状态不让主流程通过 |
| E04 | 分发 zip 完整性 | zip 包含安装器、便携版、README 和 HELP |
| E05 | 安装器静默安装 | 安装到临时目录成功 |
| E06 | 安装后 EXE 自测 | 安装目录里的 EXE 自测通过 |
| E07 | 安装后可见 UI 截图和布局报告 | 启动可见窗口并写出 `release\test-reports\installed-ui-smoke.png`、`installed-ui-smoke-narrow.png`、`installed-ui-smoke-minimum.png` 及对应 `*-layout.json`，自动断言正常/窄/最小窗口下主界面不需要滚动、控件不溢出、输入框和底部按钮都在单页可见区域内 |
| E08 | 安装后启动烟测 | `--hidden` 启动后进程保持运行 |

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
| U01 | 首次启动受控版 | 用强制激活构建启动 EXE | 弹出授权激活窗口 |
| U02 | 未激活时录音 | 未激活状态按录音快捷键 | 不开始录音，提示需要激活 |
| U03 | 输入有效激活码 | 在授权窗口输入有效激活码 | 提示已激活，窗口自动关闭或可关闭 |
| U04 | 输入错误激活码 | 输入不存在、停用、过期的码 | 显示对应错误，不写入授权 |
| U05 | 设备数已满 | 用同一个单设备码在第二台电脑激活 | 提示设备数已满 |
| U06 | 复制安装包给另一台电脑 | 在新电脑安装同一 EXE | 仍要求输入激活码 |
| U07 | 复制本地 `license.json` | 把一台电脑的授权文件复制到另一台 | 校验失败并清理授权 |
| U08 | 授权服务器不可达 | 断网或停掉授权服务器后启动/校验 | 显示服务器不可达，不崩溃 |
| U09 | 帮助文档 | 打开“使用说明”和 release `HELP.md` | 能看到授权激活说明 |
| U10 | 快捷键冲突 | 配置重复快捷键 | 弹窗提示冲突，不能保存重复配置 |
| U11 | UI 截图复核 | 打开 `release\test-reports\installed-ui-smoke.png`、`installed-ui-smoke-narrow.png`、`installed-ui-smoke-minimum.png` 和对应 `*-layout.json` | 主界面没有滚动条，文字、输入框、录制按钮和底部操作按钮不被截断，窄窗口和最小窗口下控件自动压缩和重排，布局报告显示 `fits_horizontally=true` 且 `fits_vertically=true` |

## 发版前建议

1. 先跑 `.\test-activation.ps1`。
2. 跑 `.\test-license-stress.ps1`。
3. 再按正式授权服务器设置环境变量，跑 `.\build-desktop-exe.ps1`。
4. 跑 `.\test-desktop-exe.ps1`。
5. 有 ASR 凭据时跑 `.\test-long-text-asr.ps1`。
6. 手工验收 U01-U11，重点看授权窗口、未激活拦截和主界面缩放截图。
