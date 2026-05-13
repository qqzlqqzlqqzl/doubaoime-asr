# Windows 兼容性结论

当前主发布包是 64 位 Windows 包，正式目标是 Windows 10/11 x64。近期审计基线为 Python 3.13 + PyInstaller 6.20；PyInstaller 版本以实际构建日志和 `release\test-reports\windows-compatibility.json` 为准。Win7/Win8/Win8.1 不提供支持。

分发风险：未签名 PyInstaller EXE 可能被 Windows SmartScreen 或 Windows 11 Smart App Control / Code Integrity 拦截。2026-05-13 本机重打包后的主程序被 Smart App Control 以 “did not meet Enterprise signing level requirements” 拦截，事件日志位于 `Microsoft-Windows-CodeIntegrity/Operational`。正式外部分发前应做可信代码签名；仅靠安装器或 zip 不能保证绕过该策略。

## 支持矩阵

| 系统 | 结论 | 说明 |
|------|------|------|
| Windows 7 SP1 x64 | 不支持 | 不做适配和发版测试 |
| Windows 8.x x64 | 不支持 | 包括 Win8 和 Win8.1，不做适配和发版测试 |
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
- 当前构建对 Win10、Win11 的支持状态，以及 Win7/Win8/Win8.1 不支持结论。

## 依据

- Python 3.13 Windows 文档：`https://docs.python.org/3.13/using/windows.html`
- PyInstaller requirements：`https://pyinstaller.org/en/stable/requirements.html`
