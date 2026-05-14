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
    static TextCtrl := ""
    static StateCtrl := ""
    static LastText := ""
    static Mode := ""
    static Width := 476
    static Height := 235
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
        this.HintCtrl := this.FloatGui.AddText("x70 y184 w336 h34 Center BackgroundTrans", "点击/长按说话")
        this.FloatGui.SetFont("s10 c65708E", "Microsoft YaHei")
        this.StateCtrl := this.FloatGui.AddText("x24 y154 w428 h22 Center BackgroundTrans", "")
        this.TextCtrl := this.FloatGui.AddText("x24 y152 w428 h26 Center BackgroundTrans", "")
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
    }

    static Update(text := "", state := "") {
        this.Ensure()
        if state != ""
            this.StateCtrl.Value := state
        if text != "" {
            this.LastText := text
            display := StrLen(text) > 90 ? SubStr(text, 1, 90) . "..." : text
            this.TextCtrl.Value := display
        } else if this.LastText = "" {
            this.TextCtrl.Value := ""
        }
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
        this.Mode := ""
    }
}
