from __future__ import annotations

import sys
from pathlib import Path


HELP_TEXT = """豆包 ASR 助手使用说明

一、这是什么
豆包 ASR 助手是一个 Windows 桌面语音输入工具。它会在后台监听你设置的快捷键，录音结束后把识别出来的文字粘贴回你原来正在输入的窗口。

二、首次运行
1. 双击 DoubaoASRHelper.exe，或通过开始菜单打开 Doubao ASR Helper。
2. 第一次使用时，程序会在当前 Windows 用户目录下创建配置和凭据缓存：
   %APPDATA%\\DoubaoASRHelper
3. 凭据文件默认是：
   %APPDATA%\\DoubaoASRHelper\\credentials.json
4. 如果你已经有可用的 credentials.json，可以在主界面点“选择”改成已有文件。

三、核心使用流程
1. 在要输入文字的窗口里放好光标。
2. 按住或按下你设置的语音快捷键开始录音。
3. 结束录音后，程序会把识别文字插入回原窗口。
4. 当前桌面版先打磨语音输入核心功能，主界面不需要登录或激活。

四、默认快捷键
按着说触发键：rctrl
按住右 Ctrl 开始录音，松开后识别并插入文字。

自由说触发键：xbutton1
按一次鼠标侧键 1 开始录音，再按一次结束录音。

按着说+自动发送触发键：lctrl+lwin
按住左 Ctrl + 左 Win 开始录音，松开后插入文字并发送 Enter。

取消键：z
录音过程中按 z 可以取消本次输入，尤其适合自动发送模式。

五、自定义按键
1. 在主界面找到要修改的快捷键。
2. 点击输入框右侧的“录制”。
3. 直接按下你想要的键盘组合键，或者按鼠标侧键。
4. 点击“保存配置”生效。

保存配置和录制快捷键时，程序会检查本工具内部的快捷键是否重复；如果重复，会弹窗提示。它不能保证发现其他软件已经占用的全局快捷键。

六、悬浮窗
录音时会显示悬浮窗。悬浮窗里可以查看识别结果，也可以手动清空、复制或插入文字。

七、剪贴板保护
默认启用剪贴板保护。程序插入文字时会临时使用剪贴板，随后尽量恢复原来的剪贴板文本。某些复杂剪贴板内容，例如图片、富文本或文件列表，可能无法完整恢复。

八、开机自启动
勾选“开机自启动”并保存配置后，程序会在当前用户的启动目录写入一个启动脚本。取消勾选并保存后会移除它。

九、分发和安装
推荐发给其他电脑的文件是 DoubaoASRHelper-Windows.zip。

zip 里通常包含：
DoubaoASRHelperSetup.exe：安装器，安装到当前用户目录并创建快捷方式。
DoubaoASRHelper-portable.exe：便携版，双击即可运行。
HELP.md：这份使用说明。

安装器默认安装到：
%LOCALAPPDATA%\\DoubaoASRHelper

十、常见问题
1. Windows 提示未知发布者：
   当前构建未做代码签名，所以 SmartScreen 可能提示未知发布者。

2. 没有反应或没有识别：
   先确认麦克风可用，系统没有禁止桌面应用访问麦克风。再打开配置目录，确认 credentials.json 能正常创建。

3. 快捷键没触发：
   换一个不容易被系统或其他软件占用的组合键。鼠标侧键在部分鼠标驱动里可能会被拦截。

4. 自动发送发错窗口：
   开始录音前先把光标放在目标输入框里。程序会尽量回到录音前的窗口粘贴文字，但 Windows 对前台窗口切换有限制。

5. 想检查 EXE 是否能在当前电脑运行：
   开发目录里可以运行 test-desktop-exe.ps1。普通用户也可以在命令行运行：
   DoubaoASRHelper.exe --self-test --self-test-report report.json

6. 想做长文本语音识别压力测试：
   开发目录里可以运行 test-long-text-asr.ps1。它会生成约 500 字中文语音样本，样本包含断续停顿和音量高低起伏，然后用打包后的 EXE 调用 ASR 并写出报告。

十一、卸载
如果使用安装器安装，可以在开始菜单运行 Uninstall Doubao ASR Helper。
便携版直接删除 exe 即可。
配置和凭据缓存位于 %APPDATA%\\DoubaoASRHelper，如需彻底清理可以手动删除该目录。
"""


def write_help(path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(HELP_TEXT, encoding="utf-8")
    return destination


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python -m doubaoime_asr.desktop_help OUTPUT_PATH")
        return 2
    write_help(args[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
