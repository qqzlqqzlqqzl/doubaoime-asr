# Windows 兼容性结论

当前主发布包是 64 位 Windows 包，正式目标是 Windows 10/11 x64，构建链路为 Python 3.13 + PyInstaller 6.20。Win7/Win8 不提供支持。

## 支持矩阵

| 系统 | 结论 | 说明 |
|------|------|------|
| Windows 7 SP1 x64 | 不支持 | 不做适配和发版测试 |
| Windows 8.x x64 | 不支持 | 不做适配和发版测试 |
| Windows 10 x64 | 正式支持目标 | 建议作为最低正式分发目标 |
| Windows 11 x64 | 正式支持目标，已实测 | 当前开发机上自测、托盘自测、安装器和 UI 测试通过 |
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
- 当前构建对 Win10、Win11 的支持状态，以及 Win7/Win8 不支持结论。

## 依据

- Python 3.13 Windows 文档：`https://docs.python.org/3.13/using/windows.html`
- PyInstaller 6.20 requirements：`https://pyinstaller.org/en/v6.20.0/requirements.html`
