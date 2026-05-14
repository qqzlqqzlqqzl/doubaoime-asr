; ============================================
; 豆包语音助手 - 主程序入口
; ============================================
#Requires AutoHotkey v2.0
#SingleInstance Force

; 设置工作目录
SetWorkingDir(A_ScriptDir)

; 引入模块
#Include logger.ahk
#Include config.ahk
#Include clipboard.ahk
#Include window.ahk
#Include hotkey.ahk
#Include gui.ahk
#Include doubao.ahk
#Include bridge.ahk
#Include float.ahk

Logger.Init()
OnError(LogUnhandledError)

; ============================================
; 语音流程控制器
; ============================================
class VoiceController {
    ; 状态标志
    static IsProcessing := false
    static IsEnabled := true  ; 是否启用
    static IsAutoSendEnabled := false  ; 当前是否需要自动发送

    ; 防重复提示
    static LastTipTime := 0
    static TipDebounceInterval := 2000  ; 2秒内不重复相同提示
    static StatusPollTimer := 0
    static FinishPollTimer := 0
    static FinishStartedAt := 0

    ; 初始化
    static Init() {
        Logger.Info("voice_controller_init")
        VoiceFloat.InsertCallback := ObjBindMethod(this, "ManualInsertFromFloat")
        ; 加载配置并检查是否是首次运行（配置文件不存在）
        isFirstRun := !Config.Init()

        ; 设置热键回调
        HotkeyManager.SetCallbacks(
            (*) => this.OnVoiceStart(),
            (*) => this.OnHoldEnd(),
            (isStart) => this.OnFreeToggle(isStart),
            (*) => this.OnAutoSendVoiceStart(),
            (*) => this.OnAutoSendHoldEnd(),
            (*) => this.OnCancel()
        )

        ; 设置GUI保存回调
        GuiManager.OnSaveCallback := (*) => this.Reload()

        ; 初始化热键
        this.InitHotkeys()

        ; 提前拉起本地 ASR bridge；失败时热键触发也会再次尝试
        if !BridgeClient.EnsureRunning() {
            Logger.Warn("bridge_startup_deferred")
            this.ShowTrayTip("提示", "ASR bridge 暂未启动，首次录音时会再次尝试")
        }

        ; 设置托盘
        this.SetupTray()

        ; 如果是首次运行，弹出设置界面
        if isFirstRun
            GuiManager.Show()
    }

    ; 初始化热键
    static InitHotkeys() {
        holdKey := Config.Get("HoldToTalkKey")
        freeKey := Config.Get("FreeToTalkKey")
        autoSendKey := Config.Get("AutoSendKey")
        cancelKey := Config.Get("CancelKey")

        result := HotkeyManager.Init(holdKey, freeKey, autoSendKey, cancelKey)

        ; 检查注册结果并提供反馈
        if !result.hold && holdKey != "" {
            this.ShowTrayTip("热键注册失败", "按着说热键 '" holdKey "' 注册失败，可能与其他程序冲突")
        }

        if !result.free && freeKey != "" {
            this.ShowTrayTip("热键注册失败", "自由说热键 '" freeKey "' 注册失败，可能与其他程序冲突")
        }

        if !result.autoSend && autoSendKey != "" {
            this.ShowTrayTip("热键注册失败", "自动发送热键 '" autoSendKey "' 注册失败，可能与其他程序冲突")
        }

        if !result.cancel && cancelKey != "" {
            this.ShowTrayTip("热键注册失败", "取消键 '" cancelKey "' 注册失败，可能与其他程序冲突")
        }
    }

    ; 重新加载配置和热键
    static Reload() {
        Config.Load()
        this.InitHotkeys()
        ; 更新托盘菜单（刷新热键显示）
        this.UpdateTrayMenu()
    }

    ; 设置托盘图标（根据状态切换）
    ; state: "normal" | "disabled"
    static SetTrayIcon(state := "normal") {
        ; 优先使用自定义图标，不存在则使用系统图标
        switch state {
            case "normal":
                iconPath := A_ScriptDir . "\..\assets\icon.ico"
                if FileExist(iconPath)
                    TraySetIcon(iconPath)
                else if A_IsCompiled
                    TraySetIcon(A_ScriptFullPath)  ; 使用编译时嵌入的图标
                else
                    TraySetIcon("shell32.dll", 169)  ; 麦克风图标
            case "disabled":
                iconPath := A_ScriptDir . "\..\assets\icon-disabled.ico"
                if FileExist(iconPath)
                    TraySetIcon(iconPath)
                else
                    TraySetIcon("shell32.dll", 132)  ; 灰色图标
        }
    }

    ; 设置托盘图标和菜单
    static SetupTray() {
        ; 设置初始图标
        this.SetTrayIcon("normal")

        ; 设置托盘提示
        A_IconTip := "豆包语音助手"

        ; 创建托盘菜单
        this.UpdateTrayMenu()
    }

    ; 更新托盘菜单（支持动态刷新热键显示）
    static UpdateTrayMenu() {
        tray := A_TrayMenu
        tray.Delete()  ; 清除菜单

        ; 启用/禁用状态
        if this.IsEnabled
            tray.Add("✓ 已启用", (*) => this.ToggleEnabled())
        else
            tray.Add("○ 已禁用", (*) => this.ToggleEnabled())

        tray.Add()  ; 分隔线
        tray.Add("设置...", (*) => GuiManager.Show())
        tray.Add("帮助", (*) => this.ShowHelp())
        tray.Add()  ; 分隔线

        ; 显示当前热键（只读）
        holdKey := Config.Get("HoldToTalkKey")
        freeKey := Config.Get("FreeToTalkKey")
        autoSendKey := Config.Get("AutoSendKey")
        cancelKey := Config.Get("CancelKey")
        holdDisplay := GuiManager.KeyToDisplayName(holdKey)
        freeDisplay := GuiManager.KeyToDisplayName(freeKey)
        autoSendDisplay := GuiManager.KeyToDisplayName(autoSendKey)
        cancelDisplay := GuiManager.KeyToDisplayName(cancelKey)

        holdMenuItem := "🎤 按着说: " . holdDisplay
        freeMenuItem := "🗣️ 自由说: " . freeDisplay
        autoSendMenuItem := "📤 按着说+发送: " . autoSendDisplay
        cancelMenuItem := "❌ 取消键: " . cancelDisplay

        tray.Add(holdMenuItem, (*) => {})
        tray.Add(freeMenuItem, (*) => {})
        tray.Add(autoSendMenuItem, (*) => {})
        tray.Add(cancelMenuItem, (*) => {})
        tray.Disable(holdMenuItem)
        tray.Disable(freeMenuItem)
        tray.Disable(autoSendMenuItem)
        tray.Disable(cancelMenuItem)

        tray.Add()  ; 分隔线
        tray.Add("关于", (*) => this.ShowAbout())
        tray.Add()  ; 分隔线
        tray.Add("退出", (*) => this.Exit())

        ; 设置默认动作（双击托盘图标）
        tray.Default := "设置..."
    }

    ; 显示关于对话框
    static ShowAbout() {
        aboutText := "
        (
豆包语音助手 v1.1

增强豆包桌面版的语音输入体验

功能特点：
• 按着说 - 按住说话，松开自动插入
• 自由说 - 点击开始，再点击结束
• 剪贴板保护 - 不覆盖原有内容

项目地址：https://github.com/xiaohu31/doubao-voice-helper
开源协议：MIT License
        )"
        MsgBox(aboutText, "关于 - 豆包语音助手", 64)
    }

    ; 语音开始（按着说模式按下 或 自由说模式开始）
    static OnVoiceStart() {
        ; 如果已经在处理中或已禁用，忽略本次触发
        if this.IsProcessing || !this.IsEnabled
            return

        Logger.Info("voice_start mode=hold")
        this.IsProcessing := true
        VoiceFloat.Show("", "", "ready")

        ; 1. 记录当前焦点窗口
        WindowManager.SaveCurrentWindow()

        ; 2. 启动本地 ASR bridge 录音
        result := BridgeClient.Start("hold")
        if !result.ok {
            Logger.Error("voice_start_failed mode=hold error=" . result.error)
            this.IsProcessing := false
            HotkeyManager.ResetState()
            this.ShowTrayTip("错误", result.error)
            VoiceFloat.Hide()
            return
        }
        Logger.Info("voice_started mode=hold session=" . result.session_id)
        VoiceFloat.Show("", "", "recording")
        this.StartStatusPolling()
    }

    ; 按着说模式松开
    static OnHoldEnd() {
        if !this.IsProcessing
            return

        ; 执行插入流程
        this.DoInsertProcess()
    }

    ; 自由说模式切换
    static OnFreeToggle(isStart) {
        if isStart {
            ; 开始说话
            this.OnVoiceStart()
        } else {
            if this.IsProcessing
                this.DoInsertProcess()
        }
    }

    ; 按着说+自动发送模式开始
    static OnAutoSendVoiceStart() {
        ; 如果已经在处理中或已禁用，忽略本次触发
        if this.IsProcessing || !this.IsEnabled
            return

        Logger.Info("voice_start mode=autoSend")
        this.IsProcessing := true
        this.IsAutoSendEnabled := true  ; 标记需要自动发送
        VoiceFloat.Show("", "", "ready")

        ; 1. 记录当前焦点窗口
        WindowManager.SaveCurrentWindow()

        ; 2. 启动本地 ASR bridge 录音
        result := BridgeClient.Start("autoSend")
        if !result.ok {
            Logger.Error("voice_start_failed mode=autoSend error=" . result.error)
            this.IsProcessing := false
            this.IsAutoSendEnabled := false
            HotkeyManager.ResetState()
            this.ShowTrayTip("错误", result.error)
            VoiceFloat.Hide()
            return
        }
        Logger.Info("voice_started mode=autoSend session=" . result.session_id)
        VoiceFloat.Show("", "", "recording")
        this.StartStatusPolling()
    }

    ; 按着说+自动发送模式松开
    static OnAutoSendHoldEnd() {
        if !this.IsProcessing
            return

        ; 执行插入流程（会检查 IsAutoSendEnabled 标志）
        this.DoInsertProcess()
    }

    ; 取消语音输入（在按着说+自动发送模式下按取消键触发）
    static OnCancel() {
        if !this.IsProcessing
            return

        ; 通知本地 ASR bridge 取消本次录音
        Logger.Info("voice_cancel")
        BridgeClient.Cancel()
        this.StopStatusPolling()
        this.StopFinishPolling()
        VoiceFloat.Hide()

        ; 重置状态
        this.IsProcessing := false
        this.IsAutoSendEnabled := false
        HotkeyManager.ResetState()

        ; 显示提示（可选）
        this.ShowTrayTip("提示", "语音输入已取消")
    }

    ; 执行插入流程
    static DoInsertProcess() {
        ; 1. 非阻塞停止 bridge 录音，后续用定时器轮询最终结果，避免 AHK UI 卡死
        Logger.Info("voice_stop_async auto_send=" . (this.IsAutoSendEnabled ? "1" : "0"))
        this.StopStatusPolling()
        delay := Config.Get("InsertDelay")
        if delay > 0
            Sleep(delay)

        result := BridgeClient.StopAsync()
        if !result.ok {
            Logger.Error("voice_stop_failed error=" . result.error)
            this.ShowTrayTip("错误", result.error)
            this.ResetAfterFinish()
            return
        }
        VoiceFloat.Update(result.text, "正在识别...")
        this.FinishStartedAt := A_TickCount
        this.StartFinishPolling()
    }

    static StartStatusPolling() {
        this.StopStatusPolling()
        this.StatusPollTimer := ObjBindMethod(this, "PollRecordingStatus")
        SetTimer(this.StatusPollTimer, 250)
    }

    static StopStatusPolling() {
        if this.StatusPollTimer {
            SetTimer(this.StatusPollTimer, 0)
            this.StatusPollTimer := 0
        }
    }

    static PollRecordingStatus() {
        if !this.IsProcessing {
            this.StopStatusPolling()
            return
        }
        status := BridgeClient.Status()
        if status.error != "" {
            Logger.Error("recording_status_error error=" . status.error)
            this.ShowTrayTip("错误", status.error)
            this.ResetAfterFinish()
            return
        }
        if status.text != ""
            VoiceFloat.Update(status.text, "正在聆听")
        else
            VoiceFloat.Update("", "正在聆听")
        VoiceFloat.UpdateVolume(status.audio_level)
    }

    static StartFinishPolling() {
        this.StopFinishPolling()
        this.FinishPollTimer := ObjBindMethod(this, "PollInsertProcess")
        SetTimer(this.FinishPollTimer, 200)
    }

    static StopFinishPolling() {
        if this.FinishPollTimer {
            SetTimer(this.FinishPollTimer, 0)
            this.FinishPollTimer := 0
        }
    }

    static PollInsertProcess() {
        status := BridgeClient.Status()
        if status.text != ""
            VoiceFloat.Update(status.text, "正在识别...")
        VoiceFloat.UpdateVolume(0)

        if status.error != "" {
            Logger.Error("finish_status_error error=" . status.error)
            this.ShowTrayTip("错误", status.error)
            this.ResetAfterFinish()
            return
        }

        if !status.done {
            if (A_TickCount - this.FinishStartedAt) > 35000 {
                Logger.Error("finish_timeout")
                this.ShowTrayTip("错误", "识别超时")
                this.ResetAfterFinish()
            }
            return
        }

        text := status.final_text
        if text = ""
            text := status.text

        ; 2. 根据识别结果插入文本
        if text != "" {
            inserted := ClipboardManager.InsertText(text, Config.Get("ClipboardProtect"))
            if !inserted {
                Logger.Error("insert_failed chars=" . StrLen(text))
                this.ShowTrayTip("错误", "识别文本写入剪贴板失败")
            } else {
                Logger.Info("insert_ok chars=" . StrLen(text) . " auto_send=" . (this.IsAutoSendEnabled ? "1" : "0"))
                VoiceFloat.Update(text, "已插入")
            }
            ; 自动发送逻辑：如果是自动发送模式，发送回车键
            if this.IsAutoSendEnabled {
                autoSendDelay := Config.Get("AutoSendDelay")
                Sleep(autoSendDelay)  ; 等待内容完全粘贴
                SendInput("{Enter}")
            }
        } else {
            Logger.Warn("finish_empty_text")
            VoiceFloat.Update("没有识别到内容", "已结束")
        }
        SetTimer(() => VoiceFloat.Hide(), -800)
        this.ResetAfterFinish(false)
    }

    static ManualInsertFromFloat(text) {
        if text = ""
            return
        Logger.Info("manual_float_insert chars=" . StrLen(text))
        inserted := ClipboardManager.InsertText(text, Config.Get("ClipboardProtect"))
        if !inserted
            this.ShowTrayTip("错误", "识别文本写入剪贴板失败")
        else
            VoiceFloat.Update(text, "已插入")
    }

    static ResetAfterFinish(hideFloat := true) {
        this.StopStatusPolling()
        this.StopFinishPolling()
        if hideFloat
            VoiceFloat.Hide()
        ; 重置状态
        this.IsProcessing := false
        this.IsAutoSendEnabled := false  ; 重置自动发送标志
        HotkeyManager.ResetState()
    }

    ; 悬浮窗监控定时器引用
    static VoiceWindowMonitorTimer := 0

    ; 启动悬浮窗监控（自由说模式）
    static StartVoiceWindowMonitor() {
        ; 只在自由说模式且正在处理时启动
        if !HotkeyManager.IsFreeMode || !this.IsProcessing
            return

        ; 先检测一次悬浮窗是否弹出
        if !DoubaoWindow.IsVoiceWindowExist() {
            ; 悬浮窗未弹出，重置状态
            this.IsProcessing := false
            HotkeyManager.ResetState()
            this.ShowTrayTip("错误", "豆包悬浮窗未弹出，请检查豆包是否正常运行")
            return
        }

        ; 创建周期性定时器（每500ms检测一次）
        this.VoiceWindowMonitorTimer := ObjBindMethod(this, "CheckVoiceWindowStatus")
        SetTimer(this.VoiceWindowMonitorTimer, 500)
    }

    ; 停止悬浮窗监控
    static StopVoiceWindowMonitor() {
        if this.VoiceWindowMonitorTimer {
            SetTimer(this.VoiceWindowMonitorTimer, 0)
            this.VoiceWindowMonitorTimer := 0
        }
    }

    ; 检查悬浮窗状态（周期性调用）
    static CheckVoiceWindowStatus() {
        ; 安全检查：如果不在自由说模式或已完成处理，停止监控
        if !HotkeyManager.IsFreeMode || !this.IsProcessing {
            this.StopVoiceWindowMonitor()
            return
        }

        ; 检测悬浮窗是否被关闭
        if !DoubaoWindow.IsVoiceWindowExist() {
            ; 停止监控
            this.StopVoiceWindowMonitor()

            ; 重置状态
            this.IsProcessing := false
            HotkeyManager.ResetState()

            ; 提示用户
            currentTime := A_TickCount
            if (currentTime - this.LastTipTime) >= this.TipDebounceInterval {
                this.ShowTrayTip("提示", "豆包悬浮窗已关闭，语音输入已取消")
                this.LastTipTime := currentTime
            }
        }
    }

    ; 显示托盘提示
    static ShowTrayTip(title, message) {
        if Config.Get("ShowTrayTip")
            TrayTip(message, title, 1)
    }

    ; 切换启用状态
    static ToggleEnabled() {
        this.IsEnabled := !this.IsEnabled

        ; 更新托盘图标和菜单
        if this.IsEnabled {
            this.SetTrayIcon("normal")
            A_IconTip := "豆包语音助手"
        } else {
            this.SetTrayIcon("disabled")
            A_IconTip := "豆包语音助手 (已禁用)"
        }

        ; 重新构建菜单（更新启用/禁用显示）
        this.UpdateTrayMenu()
    }

    ; 显示帮助
    static ShowHelp() {
        helpText := "
        (
豆包语音助手 使用说明

【按着说模式】
按住触发键说话，松开后自动插入识别结果到光标位置。
如果按住时间太短（小于最小按住时长），会自动取消。

【自由说模式】
点击触发键开始说话，再次点击结束并插入识别结果。
适合长时间语音输入，不限时长。

【按着说+自动发送模式】
按住触发键说话，松开后自动插入识别结果并发送（按回车）。
适合快速聊天场景，说完即发。
在说话过程中按取消键可以取消本次输入。

【默认触发键】
- 按着说：右Ctrl (RCtrl)
- 自由说：Ctrl+Alt+Space
- 按着说+发送：Ctrl+Alt+Enter
- 取消键：Esc
- 可在设置中自定义任意按键或组合键

【配置说明】
- 识别延迟：松开后等待豆包识别完成的时间
- 剪贴板保护：开启后会恢复用户原来的剪贴板内容
- 最小按住时长：按着说模式的最短按住时间
- 剪贴板超时：等待识别结果的超时时间

【注意事项】
1. 需要先配置并运行本地 ASR 服务
2. 豆包快捷键默认保留为 Ctrl+Alt+D，仅用于兼容设置项
3. 识别结果会插入到当前焦点窗口的光标位置
4. 说话过程中可以切换窗口，内容会插入到新窗口

【常见问题】
Q: 为什么没有插入识别结果？
A: 请检查豆包是否正在运行，快捷键是否正确。

Q: 为什么插入了错误的内容？
A: 可能是识别延迟设置过短，请适当增加延迟时间。
        )"
        MsgBox(helpText, "豆包语音助手 - 帮助", 64)
    }

    ; 退出程序
    static Exit() {
        ExitApp()
    }
}

; ============================================
; 程序启动
; ============================================
if A_Args.Length > 0 && A_Args[1] = "--float-self-test" {
    Logger.Info("float_self_test_start")
    VoiceFloat.Show("", "", "ready")
    Sleep(900)
    VoiceFloat.Show("这是我用豆包语音输入的内容，效果 very nice，可以实时看到更长一点的文字。现在测试连续说很多内容时，浮窗应该保留多行文本，不应该因为内容变长就消失。", "正在聆听", "recording")
    Sleep(5000)
    VoiceFloat.Hide()
    Logger.Info("float_self_test_end")
    ExitApp(0)
}

VoiceController.Init()

; 保持脚本运行
Persistent()
