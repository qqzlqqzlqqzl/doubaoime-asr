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
    static CloseCtrl := ""
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
    static Width := 456
    static Height := 132
    static WaveTick := 0
    static WaveTimer := 0

    static Ensure() {
        if this.FloatGui != ""
            return

        this.FloatGui := Gui("+AlwaysOnTop -Caption +ToolWindow +Border +E0x08000000", "DoubaoASRHelperFloat")
        this.FloatGui.BackColor := "FFFFFF"
        this.FloatGui.MarginX := 0
        this.FloatGui.MarginY := 0
        this.FloatGui.SetFont("s1 cFFFFFF", "Microsoft YaHei")
        this.TitleCtrl := this.FloatGui.AddText("x0 y0 w1 h1 BackgroundTrans", "")
        this.GearCtrl := this.FloatGui.AddText("x0 y0 w1 h1 BackgroundTrans", "")
        this.MinCtrl := this.FloatGui.AddText("x0 y0 w1 h1 BackgroundTrans", "")

        this.FloatGui.SetFont("s1 cFFFFFF", "Microsoft YaHei")
        this.MicCircleCtrl := this.FloatGui.AddText("x0 y0 w1 h1 BackgroundTrans", "")
        this.MicIconCtrl := this.FloatGui.AddText("x0 y0 w1 h1 BackgroundTrans", "")

        for index, height in [4, 5, 4, 6, 5, 4, 6, 7, 5, 6, 8, 10, 13, 18, 24, 28, 24, 18, 13, 10, 8, 7, 6, 6, 5, 4, 5, 4] {
            x := 60 + ((index - 1) * 12)
            y := 18 - Round(height / 2)
            this.WaveBars.Push(this.FloatGui.AddProgress("x" . x . " y" . y . " w4 h" . height . " c5A79FF BackgroundFFFFFF Range0-100 -Smooth", 100))
        }

        this.FloatGui.SetFont("s1 cFFFFFF", "Microsoft YaHei")
        this.HintCtrl := this.FloatGui.AddText("x0 y0 w1 h1 BackgroundTrans", "")
        this.FloatGui.SetFont("s10 c65708E", "Microsoft YaHei")
        this.StateCtrl := this.FloatGui.AddText("x0 y0 w1 h1 BackgroundTrans", "")
        this.TextCtrl := this.FloatGui.AddText("x0 y0 w1 h1 BackgroundTrans", "")

        this.ResultBgCtrl := this.FloatGui.AddText("x12 y34 w432 h86 +Border BackgroundFFFFFF", "")
        this.FloatGui.SetFont("s19 c5F9D68", "Segoe MDL2 Assets")
        this.ResultMicCtrl := this.FloatGui.AddText("x28 y54 w30 h34 Center BackgroundTrans", Chr(0xE720))
        this.FloatGui.SetFont("s12 c3B4258", "Microsoft YaHei")
        this.ResultTextCtrl := this.FloatGui.AddText("x68 y50 w252 h34 BackgroundTrans +Wrap", "识别内容会显示在这里")
        this.FloatGui.SetFont("s11 c9AA0AD", "Microsoft YaHei")
        this.CloseCtrl := this.FloatGui.AddText("x416 y42 w20 h22 Center BackgroundTrans", "×")
        this.FloatGui.SetFont("s9 c555B6E", "Microsoft YaHei")
        this.ClearBtn := this.FloatGui.AddButton("x220 y86 w56 h26", "清空")
        this.CopyBtn := this.FloatGui.AddButton("x284 y86 w56 h26", "复制")
        this.InsertBtn := this.FloatGui.AddButton("x348 y86 w72 h26 Default", "插入")
        this.ClearBtn.OnEvent("Click", (*) => this.ClearText())
        this.CopyBtn.OnEvent("Click", (*) => this.CopyText())
        this.InsertBtn.OnEvent("Click", (*) => this.InsertText())
        this.CloseCtrl.OnEvent("Click", (*) => this.Hide())
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
        this.MicCircleCtrl.Visible := false
        this.MicIconCtrl.Visible := false
        for bar in this.WaveBars
            bar.Visible := true
        if showMic {
            this.StopWave()
        } else {
            this.StartWave()
        }
        this.ShowResultBox(true)
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
        for ctrl in [this.ResultBgCtrl, this.ResultMicCtrl, this.ResultTextCtrl, this.CloseCtrl, this.ClearBtn, this.CopyBtn, this.InsertBtn]
            ctrl.Visible := visible
    }

    static FormatResultText(text) {
        if text = ""
            return "识别内容会显示在这里"
        return StrLen(text) > 48 ? SubStr(text, 1, 48) . "..." : text
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
