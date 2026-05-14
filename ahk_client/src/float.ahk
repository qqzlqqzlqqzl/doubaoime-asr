; ============================================
; 语音悬浮窗
; 显示录音/识别状态和实时转写文本，不抢前台焦点
; ============================================
#Requires AutoHotkey v2.0

class VoiceFloat {
    static FloatGui := ""
    static TitleCtrl := ""
    static HintCtrl := ""
    static GearCtrl := ""
    static MinCtrl := ""
    static MicCircleCtrl := ""
    static MicIconCtrl := ""
    static WaveBars := []
    static ResultBgCtrl := ""
    static ResultMicCtrl := ""
    static ResultTextCtrl := ""
    static ClearBtn := ""
    static CopyBtn := ""
    static InsertBtn := ""
    static TextCtrl := ""
    static StateCtrl := ""
    static LastText := ""
    static Mode := ""
    static InsertCallback := ""
    static Width := 476
    static Height := 286
    static WaveTick := 0
    static WaveTimer := 0

    static Ensure() {
        if this.FloatGui != ""
            return

        this.FloatGui := Gui("+AlwaysOnTop -Caption +ToolWindow +Border +E0x08000000", "DoubaoASRHelperFloat")
        this.FloatGui.BackColor := "FFFFFF"
        this.FloatGui.MarginX := 0
        this.FloatGui.MarginY := 0
        this.FloatGui.SetFont("s18 c28385F", "Microsoft YaHei")
        this.TitleCtrl := this.FloatGui.AddText("x28 y18 w86 h34 BackgroundTrans", "普通话")
        this.FloatGui.SetFont("s15 c7C8498", "Segoe MDL2 Assets")
        this.FloatGui.AddText("x120 y24 w22 h22 BackgroundTrans", Chr(0xE768))
        this.GearCtrl := this.FloatGui.AddText("x365 y20 w28 h28 BackgroundTrans", Chr(0xE713))
        this.FloatGui.SetFont("s18 c7C8498", "Microsoft YaHei")
        this.MinCtrl := this.FloatGui.AddText("x425 y14 w34 h26 Center BackgroundTrans", "-")

        this.FloatGui.SetFont("s88 c5578FF", "Microsoft YaHei")
        this.MicCircleCtrl := this.FloatGui.AddText("x171 y20 w135 h135 Center BackgroundTrans", "●")
        this.FloatGui.SetFont("s56 cFFFFFF", "Segoe MDL2 Assets")
        this.MicIconCtrl := this.FloatGui.AddText("x194 y67 w88 h76 Center BackgroundTrans", Chr(0xE720))

        for index, height in [6, 7, 6, 8, 7, 6, 8, 9, 7, 8, 10, 14, 20, 26, 31, 35, 30, 25, 18, 12, 9, 8, 7, 8, 6, 7] {
            x := 86 + ((index - 1) * 12)
            y := 104 - Round(height / 2)
            this.WaveBars.Push(this.FloatGui.AddProgress("x" . x . " y" . y . " w4 h" . height . " c5578FF BackgroundFFFFFF Range0-100 -Smooth", 100))
        }

        this.FloatGui.SetFont("s20 c65708E", "Microsoft YaHei")
        this.HintCtrl := this.FloatGui.AddText("x70 y171 w336 h34 Center BackgroundTrans", "点击/长按说话")
        this.FloatGui.SetFont("s10 c65708E", "Microsoft YaHei")
        this.StateCtrl := this.FloatGui.AddText("x24 y146 w428 h22 Center BackgroundTrans", "")
        this.TextCtrl := this.FloatGui.AddText("x24 y146 w428 h26 Center BackgroundTrans", "")

        this.ResultBgCtrl := this.FloatGui.AddText("x58 y118 w360 h138 +Border BackgroundFFFFFF", "")
        this.FloatGui.SetFont("s18 c5F9D68", "Segoe MDL2 Assets")
        this.ResultMicCtrl := this.FloatGui.AddText("x76 y137 w30 h34 Center BackgroundTrans", Chr(0xE720))
        this.FloatGui.SetFont("s13 c3B4258", "Microsoft YaHei")
        this.ResultTextCtrl := this.FloatGui.AddText("x112 y134 w282 h58 BackgroundTrans +Wrap", "识别内容会显示在这里")
        this.FloatGui.SetFont("s10 c555B6E", "Microsoft YaHei")
        this.ClearBtn := this.FloatGui.AddButton("x164 y212 w58 h30", "清空")
        this.CopyBtn := this.FloatGui.AddButton("x234 y212 w58 h30", "复制")
        this.InsertBtn := this.FloatGui.AddButton("x304 y210 w82 h34 Default", "插入")
        this.ClearBtn.OnEvent("Click", (*) => this.ClearText())
        this.CopyBtn.OnEvent("Click", (*) => this.CopyText())
        this.InsertBtn.OnEvent("Click", (*) => this.InsertText())
    }

    static Show(text := "开始说话...", state := "正在聆听", mode := "ready") {
        this.Ensure()
        this.SetMode(mode)
        this.Update(text, state)
        x := Round((A_ScreenWidth - this.Width) / 2)
        y := Round(A_ScreenHeight * 0.62)
        this.FloatGui.Show("NA x" . x . " y" . y . " w" . this.Width . " h" . this.Height)
        try {
            WinSetAlwaysOnTop(1, this.FloatGui.Hwnd)
            WinSetTransparent(245, this.FloatGui.Hwnd)
        }
    }

    static SetMode(mode) {
        if mode = ""
            mode := "recording"
        if this.Mode = mode
            return
        this.Mode := mode
        showMic := mode = "ready" || mode = "starting"
        this.MicCircleCtrl.Visible := showMic
        this.MicIconCtrl.Visible := showMic
        for bar in this.WaveBars
            bar.Visible := !showMic
        if showMic {
            this.HintCtrl.Value := "点击/长按说话"
            this.StopWave()
        } else {
            this.HintCtrl.Value := "点击结束语音输入"
            this.StartWave()
        }
        this.ShowResultBox(!showMic || this.LastText != "")
    }

    static Update(text := "", state := "") {
        this.Ensure()
        if state != ""
            this.StateCtrl.Value := state
        if text != "" {
            this.LastText := text
            display := StrLen(text) > 90 ? SubStr(text, 1, 90) . "..." : text
            this.TextCtrl.Value := ""
            this.ResultTextCtrl.Value := this.FormatResultText(text)
            this.ShowResultBox(true)
        } else if this.LastText = "" {
            this.TextCtrl.Value := ""
            this.ResultTextCtrl.Value := "识别内容会显示在这里"
        }
    }

    static ShowResultBox(visible := true) {
        for ctrl in [this.ResultBgCtrl, this.ResultMicCtrl, this.ResultTextCtrl, this.ClearBtn, this.CopyBtn, this.InsertBtn]
            ctrl.Visible := visible
    }

    static FormatResultText(text) {
        if text = ""
            return "识别内容会显示在这里"
        return StrLen(text) > 70 ? SubStr(text, 1, 70) . "..." : text
    }

    static ClearText() {
        this.LastText := ""
        this.TextCtrl.Value := ""
        this.ResultTextCtrl.Value := "识别内容会显示在这里"
        Logger.Info("float_clear")
    }

    static CopyText() {
        if this.LastText = ""
            return
        A_Clipboard := this.LastText
        Logger.Info("float_copy chars=" . StrLen(this.LastText))
    }

    static InsertText() {
        if this.LastText = ""
            return
        Logger.Info("float_insert_clicked chars=" . StrLen(this.LastText))
        if IsObject(this.InsertCallback)
            this.InsertCallback.Call(this.LastText)
    }

    static StartWave() {
        if this.WaveTimer
            return
        this.WaveTimer := ObjBindMethod(this, "AnimateWave")
        SetTimer(this.WaveTimer, 120)
    }

    static StopWave() {
        if this.WaveTimer {
            SetTimer(this.WaveTimer, 0)
            this.WaveTimer := 0
        }
    }

    static AnimateWave() {
        this.WaveTick += 1
        for index, bar in this.WaveBars {
            phase := Mod(this.WaveTick + index, 8)
            value := phase < 4 ? 100 : 65
            try bar.Value := value
        }
    }

    static Hide() {
        this.StopWave()
        if this.FloatGui != ""
            this.FloatGui.Hide()
        this.LastText := ""
        if this.ResultTextCtrl != ""
            this.ResultTextCtrl.Value := "识别内容会显示在这里"
        this.Mode := ""
    }
}
