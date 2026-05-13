# Windows 兼容性结论

当前主发布包是 64 位 Windows 包，正式优先目标是 Windows 10/11 x64，构建链路为 Python 3.13 + PyInstaller 6.20。Win7/Win8 不作为主支持目标；项目只额外保留一条实验性 legacy 构建链路，方便确实有老系统需求时单独验证。

## 支持矩阵

| 系统 | 结论 | 说明 |
|------|------|------|
| Windows 7 SP1 x64 | 不支持 | Python 3.13 和 PyInstaller 6.20 都不再把 Win7 作为目标平台 |
| Windows 8.0 x64 | 不支持 | Python 3.13 的 Windows 支持从 Windows 8.1 开始，当前运行时还导入了 Win8.1+ 的 Process Snapshotting API |
| Windows 8.1 x64 | 条件兼容 | 静态审计通过运行时平台要求，但当前没有 Win8.1 虚拟机实跑，不能作为正式发版承诺 |
| Windows 10 x64 | 正式支持目标 | 建议作为最低正式分发目标 |
| Windows 11 x64 | 正式支持目标，已实测 | 当前开发机上自测、托盘自测、安装器和 UI 测试通过 |
| 32 位 Windows | 不支持 | 当前 EXE 是 x64 PE 文件 |

## 可选 Legacy 包

Legacy 包只用于 Win7/Win8 的实验性验证，不参与主发布包承诺。日常分发和问题修复优先处理 `release\DoubaoASRHelper-Windows.zip` 和 `release\DoubaoASRHelper-Portable.zip`。

运行：

```powershell
.\build-desktop-exe-legacy.ps1
.\test-windows-compat-legacy.ps1
```

产物：

```text
release\legacy\DoubaoASRHelper-Win7-Legacy-Portable.zip
release\legacy\DoubaoASRHelper-Win7-Legacy-Windows.zip
release\test-reports\windows-compatibility-legacy.json
```

| 系统 | Legacy 结论 | 说明 |
|------|-------------|------|
| Windows 7 SP1 x64 | 实验性兼容 | 使用 Python 3.8 和旧 PyInstaller，已通过本机自测和静态 PE 审计，但还没有 Win7 VM 实跑 |
| Windows 8.0 x64 | 实验性兼容 | 同上，需要 Win8.0 VM 启动、托盘、热键、录音、ASR 和安装卸载烟测 |
| Windows 8.1 x64 | 实验性兼容 | 比主包更保守，但仍需目标系统 VM 认证 |
| Windows 10/11 x64 | 可运行 | 推荐优先使用主发布包，legacy 包只用于老系统需求 |

Legacy 包不是把主包承诺改成 Win7/Win8 正式支持，而是提供一份更可能在老系统启动的独立分发包。真正对外承诺前，还需要拿同一个 EXE 在干净 Win7 SP1、Win8.0、Win8.1 虚拟机里跑完整链路。

## 自动化检查

运行：

```powershell
.\build-desktop-exe.ps1
.\test-windows-compat.ps1
```

脚本会生成：

```text
release\test-reports\windows-compatibility.json
```

检查内容：

- 当前 EXE 自测和托盘自测。
- 外层 EXE、`python313.dll`、Tk、OpenSSL、PortAudio 等关键 DLL 的 PE 架构和导入表。
- 当前构建对 Win7、Win8.0、Win8.1、Win10、Win11 的支持矩阵。
- 本机是否存在可用于 Win7/Win8 实跑的 VM 工具。

## 依据

- Python 3.13 Windows 文档：`https://docs.python.org/3.13/using/windows.html`
- PyInstaller 6.20 requirements：`https://pyinstaller.org/en/v6.20.0/requirements.html`
- Microsoft `PssQuerySnapshot` API：`https://learn.microsoft.com/windows/win32/api/processsnapshot/nf-processsnapshot-pssquerysnapshot`

## 如果必须试 Win7 或 Win8.0

使用 legacy 构建，不建议拿当前主包硬兼容：

1. 构建 `release\legacy\DoubaoASRHelper-Win7-Legacy-Portable.zip` 或 `release\legacy\DoubaoASRHelper-Win7-Legacy-Windows.zip`。
2. 在真实 Win7/Win8 虚拟机里跑安装、启动、托盘、热键、录音、ASR、卸载全链路。
3. 对外单独标注 legacy/experimental，避免和主发布包混发。
