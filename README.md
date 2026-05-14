# doubaoime-asr

豆包输入法语音识别 Python 客户端。

当前维护仓库：`https://github.com/qqzlqqzlqqzl/doubaoime-asr.git`。原始上游项目来自 `starccy/doubaoime-asr`，本仓库在其基础上补充了 Windows 桌面助手、打包、托盘、热键、激活码和测试文档。

最新大版本说明见 [CHANGELOG.md](CHANGELOG.md)。2026-05-14 起，桌面版收敛为“AutoHotkey 客户端 + Python ASR bridge”的薄桥接架构，并新增 [UPSTREAM_DIFF_AUDIT.md](UPSTREAM_DIFF_AUDIT.md) 解释本仓库相对两个参考仓库的每一类差异。

## 免责声明

本项目通过对安卓豆包输入法客户端通信协议分析并参考客户端代码实现，**非官方提供的 API**。

- 本项目仅供学习和研究目的
- 不保证未来的可用性和稳定性
- 服务端协议可能随时变更导致功能失效

## 安装

```bash
# 从本地安装
git clone https://github.com/qqzlqqzlqqzl/doubaoime-asr.git
cd doubaoime-asr
pip install -e .

# 或从 Git 仓库安装
pip install git+https://github.com/qqzlqqzlqqzl/doubaoime-asr.git
```

### 系统依赖

本项目依赖 Opus 音频编解码库，需要先安装系统库：

```bash
# Debian/Ubuntu
sudo apt install libopus0

# Arch Linux
sudo pacman -S opus

# macOS
brew install opus
```

## 快速开始

### 基本用法

```python
import asyncio
from doubaoime_asr import transcribe, ASRConfig

async def main():
    # 配置（首次运行会自动注册设备，并将凭据保存到指定文件）
    config = ASRConfig(credential_path="./credentials.json")

    # 识别音频文件
    result = await transcribe("audio.wav", config=config)
    print(f"识别结果: {result}")

asyncio.run(main())
```

### 流式识别

如果需要获取中间结果或更详细的状态信息，可以使用 `transcribe_stream`：

```python
import asyncio
from doubaoime_asr import transcribe_stream, ASRConfig, ResponseType

async def main():
    config = ASRConfig(credential_path="./credentials.json")

    async for response in transcribe_stream("audio.wav", config=config):
        match response.type:
            case ResponseType.INTERIM_RESULT:
                print(f"[中间结果] {response.text}")
            case ResponseType.FINAL_RESULT:
                print(f"[最终结果] {response.text}")
            case ResponseType.ERROR:
                print(f"[错误] {response.error_msg}")

asyncio.run(main())
```

### 实时麦克风识别

实时语音识别需要配合音频采集库使用，请参考 [examples/mic_realtime.py](examples/mic_realtime.py)。

运行示例需要安装额外依赖：

```bash
pip install sounddevice numpy
```

## API 参考

### transcribe

非流式语音识别，直接返回最终结果。

```python
async def transcribe(
    audio: str | Path | bytes,
    *,
    config: ASRConfig | None = None,
    on_interim: Callable[[str], None] | None = None,
    realtime: bool = False,
) -> str
```

参数：
- `audio`: 音频文件路径或 PCM 字节数据
- `config`: ASR 配置
- `on_interim`: 中间结果回调
- `realtime`: 是否模拟实时发送（每个音频数据帧之间加入固定的发送延迟）
    - `True`: 模拟实时发送，加入固定的延迟，表现得更像正常的客户端，但会增加整体识别时间
    - `False`: 尽可能快地发送所有数据帧，整体识别时间更短（貌似也不会被风控）

### transcribe_stream

流式语音识别，返回 `ASRResponse` 异步迭代器。

```python
async def transcribe_stream(
    audio: str | Path | bytes,
    *,
    config: ASRConfig | None = None,
    realtime: bool = False,
) -> AsyncIterator[ASRResponse]
```

### transcribe_realtime

实时流式语音识别，接收 PCM 音频数据的异步迭代器。

```python
async def transcribe_realtime(
    audio_source: AsyncIterator[bytes],
    *,
    config: ASRConfig | None = None,
) -> AsyncIterator[ASRResponse]
```

### ASRConfig

配置类，支持以下主要参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `credential_path` | str | None | 凭据缓存文件路径 |
| `device_id` | str | None | 设备 ID（空则自动注册） |
| `token` | str | None | 认证 Token（空则自动获取） |
| `sample_rate` | int | 16000 | 采样率 |
| `channels` | int | 1 | 声道数 |
| `enable_punctuation` | bool | True | 是否启用标点 |

### ResponseType

响应类型枚举：

| 类型 | 说明 |
|------|------|
| `TASK_STARTED` | 任务已启动 |
| `SESSION_STARTED` | 会话已启动 |
| `VAD_START` | 检测到语音开始 |
| `INTERIM_RESULT` | 中间识别结果 |
| `FINAL_RESULT` | 最终识别结果 |
| `SESSION_FINISHED` | 会话结束 |
| `ERROR` | 错误 |

## 凭据管理

首次使用时会自动向服务器注册虚拟设备（设备参数定义在 `constants.py` 的 `DEFAULT_DEVICE_CONFIG` 中）并获取认证 Token。

推荐指定 `credential_path` 参数，凭据会自动缓存到文件，避免重复注册：

```python
config = ASRConfig(credential_path="~/.config/doubaoime-asr/credentials.json")
```

## 本地开发环境

当前工作区额外包含项目本地开发环境脚本。开始开发前可以在 PowerShell 中运行：

```powershell
. .\enter-dev.ps1
```

这会启用 `.venv`、项目内 Rust/Cargo 工具链，以及 `.devtools` 下的便携构建工具。

## 桌面语音输入助手

Windows 桌面版的正式目标是 Windows 10/11 x64。Win7、Win8、Win8.1 和 32 位 Windows 不作为支持目标，对外分发优先使用主发布包。

当前桌面版改为薄桥接架构：`ahk_client` 直接使用 `xiaohu31/doubao-voice-helper` 的 AutoHotkey v2 客户端结构，保留设置页、热键、托盘、剪贴板保护和自动发送；`doubaoime_asr.asr_bridge` 复用 Python 豆包 ASR API，在本机提供 `health / start / stop / cancel / status`。AHK 只负责交互和粘贴，Python 只负责录音识别。两份参考仓库的差异解释见 [UPSTREAM_DIFF_AUDIT.md](UPSTREAM_DIFF_AUDIT.md)。

运行时进程关系：

| 组件 | 产物 | 职责 |
|------|------|------|
| AHK 主客户端 | `DoubaoASRHelper.exe` | 设置页、全局热键、托盘、悬浮窗、剪贴板保护、插入、自动发送 |
| Python ASR bridge | `asr_bridge.exe` | 录音、调用豆包 ASR、实时文本合并、本地 HTTP API |

免安装版或安装目录里必须同时保留这两个 EXE。只复制 `DoubaoASRHelper.exe` 会导致主界面能打开但无法识别语音。

本地开发建议先在 PowerShell 中启用项目隔离环境：

```powershell
. .\enter-dev.ps1
```

启动桌面 UI：

```powershell
doubaoime-asr-desktop
```

默认配置：

| 配置项 | 默认值 |
|------|------|
| 按着说触发键 | `右Ctrl` |
| 自由说触发键 | `Ctrl+Alt+Space` |
| 按着说+自动发送触发键 | `Ctrl+Alt+Enter` |
| 取消键 | `Esc` |
| 豆包快捷键 | `Ctrl+Alt+D` |
| 插入延迟 | `300ms` |
| 剪贴板超时 | `100ms` |
| 自动发送延迟 | `50ms` |

工具会在后台监听全局热键，录音时显示悬浮窗，识别完成后把文本粘贴回开始录音前的窗口。按着说和按着说+自动发送结束时使用非阻塞 stop：松手后 AHK 不会卡住等待 ASR，而是继续轮询 bridge 的最终文本，拿到结果后自动插入。
配置和凭据缓存默认保存在 `%APPDATA%\DoubaoASRHelper`，因此打包后不依赖项目目录。
如果检测到旧参考客户端目录 `%APPDATA%\DouBaoVoiceHelper\config.ini`，会自动迁移到 `%APPDATA%\DoubaoASRHelper\config.ini`，并把旧默认热键迁移为当前更安全的默认值。
录音悬浮窗有两种参考图式状态：待说话时显示蓝色麦克风图和“点击/长按说话”，录音中显示蓝色声波条和“点击结束语音输入”，帮助用户确认当前确实在录音。
悬浮窗中间会显示识别结果框，实时识别和最终文本都会出现在框内，底部提供「清空」「复制」「插入」三个操作。
设置界面按「按着说」「自由说」「按着说+自动发送」三种模式分块展示，下面统一放置豆包快捷键、插入延迟、剪贴板保护、开机自启动和高级延迟设置，和参考工具的操作路径保持一致。
「剪贴板保护」默认开启，会在插入识别文本后恢复原剪贴板。文本剪贴板会完整恢复；常见图片 `CF_DIB` 和文件列表 `CF_HDROP` 也有原生格式烟测覆盖。Windows 自动派生的 `CF_BITMAP/CF_DIBV5` 不会被重新发布，避免冻结 EXE 读取不可搬运句柄。

每个热键输入框右侧都有「录制」按钮，点击后直接按下想要的键盘组合键或鼠标侧键即可完成自定义。
保存配置和录制快捷键时会检查重复配置、危险裸字母键、Windows 保留组合键，以及可通过系统接口探测到的已占用全局组合键，并在发现冲突时弹窗提示。
空闲状态启动录音时会要求按下的键和设置项精确匹配，`Ctrl+D` 不会被 `Ctrl+Alt+D` 误触发；单独的左Ctrl、Alt、左Alt、Win、左Win、Shift 不会作为启动热键保存，默认右Ctrl 会保留。默认热键避开 `Ctrl+Q`、`Ctrl+D`、裸字母、鼠标侧键和 Windows 自带语音输入 `Win+H`。
托盘右键菜单可临时启用/禁用语音监听，并灰显展示当前按着说、自由说、按着说+发送和取消键配置。
EXE 内置「使用说明」窗口，安装后开始菜单也会生成 Help 快捷方式；分发包中还会包含离线 `HELP.md`。

日志默认写入 `%APPDATA%\DoubaoASRHelper\logs`：

| 日志 | 说明 |
|------|------|
| `client-YYYYMMDD.log` | AHK 主客户端日志，包含启动、热键触发、bridge 调用、插入、未处理异常 |
| `asr_bridge-YYYYMMDD.log` | Python ASR bridge 日志，包含服务启动、录音会话、ASR 错误、线程异常 |

如果用户反馈闪退或录音后无响应，优先让用户提供当天这两个日志文件。

打包桌面版和 Windows 分发包：

```powershell
.\build-desktop-exe.ps1
```

构建结果里 `DoubaoASRHelper.exe` 是 AHK 主客户端，`asr_bridge.exe` 是 Python ASR 后端。免安装版必须把这两个 EXE 放在同一个目录。

测试已打包的 exe、安装器和分发 zip：

```powershell
.\test-desktop-exe.ps1
```

这一步会覆盖 bridge 自测、HTTP health/status、AHK 主客户端自动拉起 bridge、安装目录包含双 EXE、便携 zip 包含 bridge。

其中按着说的核心闭环必须满足：松开触发键后自动插入识别文字，不需要点击悬浮窗“插入”。可单独跑：

```powershell
python -m doubaoime_asr.desktop_app --hold-release-auto-insert-test --hold-release-auto-insert-report release\test-reports\hold-release-auto-insert.json
```

测试激活码、设备绑定和授权服务器边界场景：

```powershell
.\test-activation.ps1
```

压测示例授权服务器的并发激活和校验：

```powershell
.\test-license-stress.ps1
```

完整测试项见 [TEST_PLAN.md](TEST_PLAN.md)。真实端到端闭环证据和未闭合项见 [E2E_TEST_EVIDENCE.md](E2E_TEST_EVIDENCE.md)；其中会明确区分 `PASS`、`PARTIAL`、`BLOCKED` 和 `NOT_RUN`，不要把计划项误当作已通过项。

和 `xiaohu31/doubao-voice-helper` 的功能复刻对照见 [REFERENCE_PARITY.md](REFERENCE_PARITY.md)。
和两个上游仓库的文件级差异审计见 [UPSTREAM_DIFF_AUDIT.md](UPSTREAM_DIFF_AUDIT.md)。如果后续发现某个 diff 解释不通，应优先当作 bug 修复，而不是继续堆新逻辑。

如果要让另一个 AI 或开发者接手维护，请先阅读 [HANDOFF.md](HANDOFF.md) 和 [E2E_TEST_EVIDENCE.md](E2E_TEST_EVIDENCE.md)。它们记录了当前桌面版架构、构建测试流程、近期关键改动、常见坑，以及哪些闭环测试仍缺真实证据。

生成约 500 字中文长文本样本，并用打包后的 exe 跑断续音量起伏 ASR 测试：

```powershell
.\test-long-text-asr.ps1
```

该测试会生成 `.devtools\samples\long-text-volume-stress.wav`，并输出 `release\test-reports\long-text-asr.json`。样本由多段中文 TTS 拼接而成，段间包含停顿，音量会按高低模式变化。

### 激活码分发控制

默认开发构建不要求激活。要做受控分发版，先准备一个授权服务器地址，然后在打包前设置环境变量：

```powershell
$env:DOUBAO_ASR_REQUIRE_ACTIVATION = "1"
$env:DOUBAO_ASR_LICENSE_URL = "https://你的授权服务器域名"
.\build-desktop-exe.ps1
```

打包脚本会把授权配置写进 EXE。用户首次启动受控分发版时需要输入激活码；激活码会和当前电脑设备码绑定，复制安装包到其他电脑后仍需要新的可用激活码。

项目里带了一个最小示例授权服务器，方便先跑通闭环：

```powershell
python tools/license_server.py --codes tools/license-codes.sample.json --host 127.0.0.1 --port 8765
```

本地测试受控构建时可使用：

```powershell
$env:DOUBAO_ASR_REQUIRE_ACTIVATION = "1"
$env:DOUBAO_ASR_LICENSE_URL = "http://127.0.0.1:8765"
.\build-desktop-exe.ps1
```

示例服务器协议：

| 接口 | 用途 |
|------|------|
| `POST /api/activate` | 提交 `activation_code`、`device_id`、`app_version`，成功后返回授权 token |
| `POST /api/verify` | 提交 `token`、`device_id`、`app_version`，校验本机授权是否仍有效 |

生产分发建议把授权服务器部署到 HTTPS 域名，修改 `tools/license-codes.sample.json` 为自己的激活码文件，并用 `DOUBAO_ASR_LICENSE_SECRET` 设置服务端签名密钥。客户端激活只能防止普通转发滥用，不能绝对防逆向；如果要更强控制，可以把 ASR 请求也代理到自己的后端，由后端按激活状态放行。

正式对外分发还需要可信代码签名。未签名 PyInstaller EXE 可能被 Windows SmartScreen 提示未知发布者；在开启 Smart App Control 或企业 Code Integrity 策略的 Windows 11 电脑上，也可能被直接阻止运行。2026-05-13 本机就出现过该策略拦截，事件日志提示 `did not meet Enterprise signing level requirements`。

产物：

| 文件 | 用途 |
|------|------|
| `dist\DoubaoASRHelper.exe` | 主程序 one-file exe |
| `dist\DoubaoASRHelperSetup.exe` | 当前用户安装器，会安装到 `%LOCALAPPDATA%\DoubaoASRHelper` 并创建快捷方式 |
| `release\DoubaoASRHelper-Windows.zip` | 给其他电脑分发的压缩包，包含安装器、便携版、简短说明和离线 `HELP.md` |

首次运行会自动在用户目录创建凭据缓存文件；也可以在 UI 里点击「选择」改用已有的 `credentials.json`。

Windows 版本支持说明见 [WINDOWS_COMPATIBILITY.md](WINDOWS_COMPATIBILITY.md)。
