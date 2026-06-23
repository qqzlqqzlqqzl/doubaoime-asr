# Doubao ASR Windows Helper 项目复盘

最后更新：2026-06-16

项目状态：冻结。本仓库保留为一次失败的前瞻性验证、工程样本和经验档案，不再按产品化方向推进。

## 0. 最重要的结论：哪些东西值得复用

这个项目本身不值得继续做成产品，但中间沉淀出来的工程资产很值得保留。以后做 Windows 桌面工具、语音工具、热键工具、剪贴板工具、后台托盘工具时，最应该复用的是下面这些。

| 可复用资产 | 价值 |
|---|---|
| AHK 主客户端 + Python bridge 双进程架构 | AHK 做热键、托盘、窗口和粘贴；Python 做协议、音频、测试和后端逻辑，职责清楚 |
| 本地 HTTP bridge | `/health /status /start /stop /cancel /reset` 让 UI 和后端解耦，便于自检、重启、日志和打包测试 |
| 全局热键系统 | 按住说、自由说、按住+发送、取消键、左右 Ctrl/Alt/Shift、危险热键检查、注册失败自愈 |
| 托盘后台保活 | 关闭窗口不退出、托盘菜单、单实例保护、重复进程清理 |
| 剪贴板保护 | 插入文本后恢复原剪贴板，覆盖文本、`CF_DIB` 图片和 `CF_HDROP` 文件列表 |
| 悬浮窗状态反馈 | 录音状态、音量条、识别文本框、非阻塞等待最终文本 |
| 打包分发链路 | AHK EXE + PyInstaller bridge + 安装器 + 免安装包 + HELP 文档 |
| 启动体检和冲突自愈 | 清理旧启动项、重复快捷方式、孤儿 bridge、坏热键配置 |
| Windows 测试方法 | 枚举窗口控件、截图验证、启动性能、托盘、自启动、剪贴板、安装器、便携包 |
| 音频处理小模块 | 20ms PCM 帧级去 DC、噪声门、AGC、限幅和内存压力测试 |
| 模拟音频闭环 | 自生成 TTS、降级样本、raw vs processed ASR 对照，适合做语音管道验证 |
| 文档纪律 | `PASS / PARTIAL / BLOCKED / NOT_RUN` 分层，避免把 smoke test 当完整闭环 |

如果以后只拿走一部分，优先拿这三块：

1. **AHK + Python bridge 架构**
2. **热键 / 托盘 / 剪贴板 / 插入闭环**
3. **打包、测试、证据文档体系**

这才是项目真正有价值的地方。

## 1. 为什么冻结

项目没有达到“可日常使用的 Windows 语音输入助手”标准。

主要失败点不是 UI，也不是打包，而是核心识别体验：

- 长一点的句子容易被提前截断。
- 停顿后上下文保持不稳定。
- 分词、断句、标点质量差。
- 最终文本合并不可控。
- 真实输入场景下修字成本太高。

继续做 UI、安装包、激活码、热键和分发控制，都是在包装一个不够可靠的识别核心。这个方向不该继续投入。

还有一个产品窗口期问题：macOS 和手机端已经有官方豆包输入法，Windows 官方版一旦出现，这套自研方案的意义会快速消失。

## 2. 这类文档叫什么

常见名称：

- `Project Postmortem`
- `Retrospective`
- `Lessons Learned`
- `Post-Implementation Review`
- `Blameless Postmortem`

本文件按 `Project Postmortem + Lessons Learned` 写：不追责，重点沉淀经验和复用资产。

## 3. 做过哪些核心能力

### 3.1 桌面架构

最终架构是：

| 层 | 产物 | 职责 |
|---|---|---|
| AHK 主客户端 | `DoubaoASRHelper.exe` | UI、热键、托盘、悬浮窗、剪贴板、插入、自动发送 |
| Python bridge | `asr_bridge.exe` | 录音、音频处理、ASR、文本合并、本地 HTTP API |
| Python ASR SDK | `doubaoime_asr` | 非官方豆包协议、Opus 编码、实时响应解析 |

这个架构是正确的。早期 Python/Tk 单体 UI 不适合 Windows 全局热键和托盘场景，后面收敛到 AHK + Python 是一次正确转向。

### 3.2 UI 和交互

实现过：

- 设置页三种模式：按着说、自由说、按着说+自动发送。
- 热键录制。
- 热键冲突检测。
- 一键复位默认值。
- 托盘后台运行。
- 双击桌面图标打开设置页。
- 开机自启动静默进托盘。
- 悬浮窗录音状态和识别文本显示。
- 松开按键自动插入。

经验：用户给了参考 repo 和截图时，应该尽量 1:1 复刻。不要在工具软件上过度发挥 UI。

### 3.3 音频和 ASR

实现过：

- 16kHz mono int16 20ms PCM 帧。
- Opus 编码。
- 实时 WebSocket ASR。
- `TranscriptAccumulator` 文本合并。
- 去 DC、噪声门、AGC、限幅。
- 3 分钟模拟音频闭环。
- raw vs processed 对照。

经验：音频增强能改善输入条件，但不能拯救识别模型本身。ASR 质量不过关时，AGC 和降噪只能提供边际收益。

### 3.4 打包和分发

实现过：

- `DoubaoASRHelper.exe`
- `asr_bridge.exe`
- 安装器
- 免安装包
- 桌面快捷方式
- 开始菜单
- 离线 HELP
- 安装/卸载清理
- 本地配置目录
- 未签名 EXE 风险记录

经验：Windows 分发必须重视代码签名。未签名 EXE 可能被 SmartScreen、Smart App Control 或企业策略拦截。

### 3.5 自动化测试和证据

实现过：

- pytest 单元测试。
- bridge self-test。
- AHK bridge self-check。
- 悬浮窗布局测试。
- 剪贴板文本/图片/文件恢复测试。
- 启动性能测试。
- 打包版 smoke test。
- 安装器和便携包检查。
- 长文本 ASR。
- 模拟音频 ASR。
- 耳机声学闭环。

经验：文档里明确区分 `PASS / PARTIAL / BLOCKED / NOT_RUN` 非常重要。没有这个分层，很容易把局部通过误判为产品可用。

## 4. 关键实验结论

### 4.1 3 分钟整段流式测试

结果：

| 项 | 结果 |
|---|---:|
| 时长 | 180.0s |
| raw degraded | 919 字 |
| processed degraded | 924 字 |
| 关键词 | 9/9 |
| 错误 | 0 |

结论：20ms PCM 帧整段流式传输可以跑通，音频处理没有破坏长音频。

但它只证明管道可运行，不证明真实用户体验可用。

### 4.2 静音切片实验

测试过按静音区域切分 utterance：

- RMS 低于阈值持续约 600ms。
- 切点放在静音附近。
- 前后保留 200ms padding。
- 每段最长约 45s。

结果：

| 方案 | 段数 | 识别字数 | 关键词 | 错误 |
|---|---:|---:|---:|---:|
| 整段 processed baseline | 1 | 924 | 9/9 | 0 |
| 静音切分，最长约 45s | 5 | 909 | 8/9 | 0 |
| 每个静音点切 utterance | 18 | 902 | 9/9 | 0 |

结论：**不要采纳本地静音切片。**

它没有改善，反而降低字数，还丢过关键词。当前豆包服务端自己的 VAD 和长流处理比客户端粗切更稳。

### 4.3 模拟音频闭环

模拟音频闭环证明：

- 自己生成 TTS。
- 降级为低音量、底噪、DC 偏移。
- raw 和 processed 两路进入同一个 `transcribe_realtime`。
- 打包版和安装目录 EXE 都能跑。

结论：音频管道和处理器是可验证的，但这不能替代真人讲话、真实热键、真实窗口插入。

## 5. 主要失败原因

### 5.1 核心识别质量不够

这是根因。长句、停顿、断句、标点、最终文本合并不稳定。一个语音输入工具，如果最后插入的文字还要大量人工修正，那就是负收益。

### 5.2 非官方协议风险

项目依赖非官方豆包输入法协议，没有官方 SLA。协议、认证、字段、风控都可能变化。这不适合做长期分发产品。

### 5.3 Windows 输入工具复杂度高

语音输入不是普通桌面 app。它要处理：

- 全局热键。
- 焦点窗口。
- 剪贴板。
- 聊天软件误发。
- 托盘。
- 开机自启动。
- DPI。
- 多屏。
- 安装卸载。
- 安全策略。

这些复杂度很容易吞掉大量时间。

### 5.4 过早产品化

项目太早进入 UI、安装包、激活码、分发控制。正确顺序应该是：

1. 先证明核心 ASR 质量。
2. 再证明真实窗口输入闭环。
3. 再做 UI。
4. 最后才做安装包和分发控制。

## 6. 做对了什么

- 从 Python/Tk UI 收敛到 AHK + Python bridge。
- 复用参考 AHK 客户端，而不是继续自创 UI。
- 建立了完整测试证据文档。
- 把 bridge 做成可自检、可 reset、可修复。
- 对安装版、免安装版、本地安装目录分别测试。
- 对模拟音频和真实耳机链路做了区分。
- silence segmentation 实验证明无收益后，没有加入主链路。

## 7. 做错了什么

- 太晚承认核心识别体验不够。
- 太早投入产品化细节。
- UI 返工太多。
- 对 Windows 分发签名风险预估不足。
- 没有一开始设定明确 kill criteria。
- 把很多工程问题处理好了，但没有先守住产品第一性问题。

## 8. 未来 V2 条件

只有满足这些条件，才值得考虑 V2：

- 有官方、稳定、可合法分发的 ASR API。
- 真人长句、停顿、改口、小声、噪声下识别可用。
- 断句、标点、上下文合并质量达标。
- 真实窗口插入闭环先通过。
- Windows 官方豆包输入法仍不存在，且自研有明确窗口期。
- 分发前准备代码签名和干净 Win10/Win11 验证。

V2 不应该复用“先做完整桌面壳，再补核心识别”的路线。

## 9. B 方案

如果不做语音输入产品，可以把本项目拆成工程资产：

- Windows AHK + Python bridge 模板。
- 热键/托盘/剪贴板工具模板。
- PyInstaller + AHK 打包模板。
- Windows 桌面自动化测试样板。
- 音频处理和模拟音频测试工具。
- 非官方 ASR 协议研究样本。

B 方案不追求日常输入法，只复用工程组件。

## 10. 类似项目检查清单

立项前先问：

- 核心能力是否可控？
- 是否依赖非官方协议？
- 官方产品是否即将覆盖？
- 是否能 1-2 天验证核心体验？
- 是否有停止条件？

开发前 48 小时必须验证：

- 真人单句。
- 真人长句。
- 停顿和改口。
- 低音量和噪声。
- 真实目标窗口插入。
- 错误恢复。

产品化前必须验证：

- 物理热键。
- 记事本、浏览器、微信/企业微信。
- 剪贴板文本/图片/文件。
- 150%/200% DPI。
- 多屏。
- 开机自启动。
- 安装卸载。
- 代码签名。
- 干净 Win10/Win11。

证据口径：

- 模拟 TTS 不等于真人。
- 文件 ASR 不等于实时 ASR。
- 源码通过不等于打包版通过。
- smoke test 不等于真实 E2E。
- `PARTIAL` 不能写成 `PASS`。

## 11. 仓库冻结状态

冻结后建议：

- 保留源码。
- 保留测试文档。
- 保留上游差异审计。
- 保留构建脚本作为参考。
- 不再继续修 UI 小问题。
- 不再继续扩展激活码分发。
- 不再继续做 silence segmentation。
- 不再默认推进 release。

接手者应先读：

1. `PROJECT_POSTMORTEM.md`
2. `E2E_TEST_EVIDENCE.md`
3. `HANDOFF.md`
4. `UPSTREAM_DIFF_AUDIT.md`
5. `TEST_PLAN.md`

## 12. 参考资料

- Atlassian: Incident postmortem template and process, https://www.atlassian.com/incident-management/postmortem/templates
- Atlassian: Postmortems handbook, https://www.atlassian.com/incident-management/handbook/postmortems
- Google SRE: Blameless Postmortem Culture, https://sre.google/sre-book/postmortem-culture/
- Google SRE Workbook: Postmortem Culture: Learning from Failure, https://sre.google/workbook/postmortem-culture/

复盘的价值不是证明“当时为什么失败”，而是让下一次更快判断什么值得做、什么应该停。
