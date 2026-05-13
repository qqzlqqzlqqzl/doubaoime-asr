# Windows 兼容性结论

当前主发布包是 64 位 Windows 包，构建链路为 Python 3.13 + PyInstaller 6.20。

## 支持矩阵

| 系统 | 结论 | 说明 |
|------|------|------|
| Windows 7 SP1 x64 | 不支持 | Python 3.13 和 PyInstaller 6.20 都不再把 Win7 作为目标平台 |
| Windows 8.0 x64 | 不支持 | Python 3.13 的 Windows 支持从 Windows 8.1 开始，当前运行时还导入了 Win8.1+ 的 Process Snapshotting API |
| Windows 8.1 x64 | 条件兼容 | 静态审计通过运行时平台要求，但当前没有 Win8.1 虚拟机实跑，不能作为正式发版承诺 |
| Windows 10 x64 | 支持目标 | 建议作为最低正式分发目标 |
| Windows 11 x64 | 已实测 | 当前开发机上自测、托盘自测、安装器和 UI 测试通过 |
| 32 位 Windows | 不支持 | 当前 EXE 是 x64 PE 文件 |

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

## 如果必须支持 Win7 或 Win8.0

需要单独做 legacy 构建，不建议拿当前包硬兼容：

1. 降级到对应系统支持的 Python 运行时。
2. 重新验证 Tk、pynput、sounddevice、OpenSSL、PortAudio、cryptography 等依赖版本。
3. 在真实 Win7/Win8 虚拟机里跑安装、启动、托盘、热键、录音、ASR、卸载全链路。
4. 单独标注 legacy 包，避免和主发布包混发。
