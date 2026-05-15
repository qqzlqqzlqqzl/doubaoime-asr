; ============================================
; 语音悬浮窗
; 显示录音/识别状态和实时转写文本，不抢前台焦点
; ============================================
#Requires AutoHotkey v2.0

class VoiceFloat {
    static FloatGui := ""
    static TitleCtrl := ""
    static HintCtrl := ""
    static TopPanelCtrl := ""
    static GearCtrl := ""
    static MinCtrl := ""
    static MicCircleCtrl := ""
    static MicIconCtrl := ""
    static CloseCtrl := ""
    static WaveCanvasCtrl := ""
    static WaveBitmap := 0
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
    static Width := 420
    static Height := 152
    static ResultHeight := 110
    static WaveTick := 0
    static WaveTimer := 0
    static WaveSlotHeights := [4, 4, 4, 5, 4, 5, 5, 6, 5, 6, 7, 9, 12, 18, 24, 28, 24, 18, 12, 9, 7, 6, 5, 6, 5, 5, 4, 5, 4, 4]

    static Ensure() {
        if this.FloatGui != ""
            return

        this.FloatGui := Gui("+AlwaysOnTop -Caption +ToolWindow +Border +E0x08000000", "DoubaoASRHelperFloat")
        this.FloatGui.BackColor := "FFFFFF"
        this.FloatGui.MarginX := 0
        this.FloatGui.MarginY := 0
        this.FloatGui.SetFont("s11 c233A63", "Microsoft YaHei")
        this.TitleCtrl := this.FloatGui.AddText("x28 y16 w105 h28 BackgroundTrans", "")
        this.TopPanelCtrl := this.FloatGui.AddText("x330 y8 w78 h34 Border BackgroundFFFFFF", "")
        this.FloatGui.SetFont("s17 c6F7896", "Segoe MDL2 Assets")
        this.GearCtrl := this.FloatGui.AddText("x342 y12 w28 h28 Center BackgroundTrans", Chr(0xE713))
        this.FloatGui.SetFont("s13 c6F7896", "Microsoft YaHei")
        this.MinCtrl := this.FloatGui.AddText("x386 y12 w18 h26 Center BackgroundTrans", "−")

        this.FloatGui.SetFont("s1 cFFFFFF", "Microsoft YaHei")
        this.MicCircleCtrl := this.FloatGui.AddText("x0 y0 w1 h1 BackgroundTrans", "")
        this.MicIconCtrl := this.FloatGui.AddText("x0 y0 w1 h1 BackgroundTrans", "")

        this.WaveCanvasCtrl := this.FloatGui.AddPicture("x34 y70 w352 h44 0xE", "")

        this.FloatGui.SetFont("s10 c65708E", "Microsoft YaHei")
        this.StateCtrl := this.FloatGui.AddText("x0 y0 w1 h1 BackgroundTrans", "")
        this.TextCtrl := this.FloatGui.AddText("x0 y0 w1 h1 BackgroundTrans", "")
        this.FloatGui.SetFont("s14 c5A6688", "Microsoft YaHei")
        this.HintCtrl := this.FloatGui.AddText("x90 y124 w240 h34 Center BackgroundTrans", "点击结束语音输入")

        this.ResultBgCtrl := this.FloatGui.AddText("x18 y42 w420 h78 Border BackgroundFFFFFF", "")
        this.FloatGui.SetFont("s19 c2563EB", "Segoe MDL2 Assets")
        this.ResultMicCtrl := this.FloatGui.AddText("x0 y0 w1 h1 Center BackgroundTrans", Chr(0xE720))
        this.FloatGui.SetFont("s11 c243B63", "Microsoft YaHei")
        this.ResultTextCtrl := this.FloatGui.AddText("x18 y12 w360 h84 Border BackgroundFFFFFF c243B63", "识别内容会显示在这里")
        this.FloatGui.SetFont("s11 c5B75B7", "Microsoft YaHei")
        this.CloseCtrl := this.FloatGui.AddText("x390 y12 w20 h22 Center BackgroundTrans", "×")
        this.FloatGui.SetFont("s9 c555B6E", "Microsoft YaHei")
        this.ClearBtn := this.FloatGui.AddText("x170 y88 w58 h26 Center Border BackgroundF7F8FA c30343B 0x200", "清空")
        this.CopyBtn := this.FloatGui.AddText("x234 y88 w58 h26 Center Border BackgroundF7F8FA c30343B 0x200", "复制")
        this.InsertBtn := this.FloatGui.AddText("x298 y88 w72 h26 Center Border BackgroundEFF6FF c2563EB 0x200", "插入")
        this.ClearBtn.OnEvent("Click", (*) => this.ClearText())
        this.CopyBtn.OnEvent("Click", (*) => this.CopyText())
        this.InsertBtn.OnEvent("Click", (*) => this.InsertText())
        this.CloseCtrl.OnEvent("Click", (*) => this.Hide())
        this.ShowResultBox(false)
        this.UpdateVolume(0)
    }

    static Show(text := "开始说话...", state := "正在聆听", mode := "ready") {
        this.Ensure()
        this.SetMode(mode)
        this.Update(text, state)
        x := Round((A_ScreenWidth - this.Width) / 2)
        y := Round(A_ScreenHeight * 0.62)
        this.FloatGui.Show("NA x" . x . " y" . y . " w" . this.Width . " h" . this.CurrentHeight())
        this.ApplyStyles()
        try {
            WinSetAlwaysOnTop(1, this.FloatGui.Hwnd)
            WinSetTransparent(255, this.FloatGui.Hwnd)
        }
    }

    static ApplyStyles() {
        UiStyle.RoundControl(this.FloatGui, 10)
        UiStyle.RoundButtons([this.ClearBtn, this.CopyBtn, this.InsertBtn], 5)
        this.HideDecorationControls()
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
        hasResult := this.LastText != ""
        this.WaveCanvasCtrl.Visible := !hasResult
        if showMic {
            this.StopWave()
        } else {
            this.StopWave()
        }
        this.UpdateVolume(0)
        this.ShowResultBox(hasResult)
    }

    static Update(text := "", state := "") {
        this.Ensure()
        if state != ""
            this.StateCtrl.Value := state
        if text != "" {
            this.LastText := text
            this.TextCtrl.Value := ""
            this.HintCtrl.Visible := false
            this.ResultTextCtrl.Value := this.FormatResultText(text)
            this.ScrollResultToLatest()
            this.ShowResultBox(true)
            this.ResizeForContent()
        } else if this.LastText = "" {
            this.TextCtrl.Value := ""
            this.ResultTextCtrl.Value := "识别内容会显示在这里"
            this.ScrollResultToLatest()
            this.HintCtrl.Visible := true
            this.ShowResultBox(false)
            this.ResizeForContent()
        }
    }

    static ShowResultBox(visible := true) {
        this.ResultMicCtrl.Visible := false
        this.GearCtrl.Visible := !visible
        this.MinCtrl.Visible := !visible
        for ctrl in [this.ResultTextCtrl, this.CloseCtrl]
            ctrl.Visible := visible
        for ctrl in [this.ClearBtn, this.CopyBtn, this.InsertBtn]
            ctrl.Visible := false
        this.HideDecorationControls()
        if this.WaveCanvasCtrl != ""
            this.WaveCanvasCtrl.Visible := !visible
        if this.HintCtrl != ""
            this.HintCtrl.Visible := !visible && this.LastText = ""
    }

    static HideDecorationControls() {
        if this.TopPanelCtrl != ""
            this.TopPanelCtrl.Visible := false
        if this.ResultBgCtrl != ""
            this.ResultBgCtrl.Visible := false
    }

    static CurrentHeight() {
        return this.LastText != "" ? this.ResultHeight : this.Height
    }

    static ResizeForContent() {
        if this.FloatGui = ""
            return
        try {
            if WinExist("ahk_id " . this.FloatGui.Hwnd)
                this.FloatGui.Show("NA w" . this.Width . " h" . this.CurrentHeight())
        }
    }

    static FormatResultText(text) {
        if text = ""
            return "识别内容会显示在这里"
        return text
    }

    static ScrollResultToLatest() {
        if this.ResultTextCtrl = ""
            return
        try DllCall("User32\InvalidateRect", "ptr", this.ResultTextCtrl.Hwnd, "ptr", 0, "int", true)
    }

    static UpdateVolume(level := 0) {
        this.Ensure()
        if level = ""
            level := 0
        level := Max(0, Min(100, Integer(level)))
        this.WaveTick += 1
        this.RenderWaveSlots(level)
    }

    static RenderWaveSlots(level := 0) {
        if this.WaveCanvasCtrl = ""
            return
        width := 352
        height := 44
        screenDc := DllCall("User32\GetDC", "ptr", 0, "ptr")
        memDc := DllCall("Gdi32\CreateCompatibleDC", "ptr", screenDc, "ptr")
        hBitmap := DllCall("Gdi32\CreateCompatibleBitmap", "ptr", screenDc, "int", width, "int", height, "ptr")
        oldBitmap := DllCall("Gdi32\SelectObject", "ptr", memDc, "ptr", hBitmap, "ptr")

        bgBrush := DllCall("Gdi32\CreateSolidBrush", "uint", this.ColorRef("FFFFFF"), "ptr")
        rc := Buffer(16, 0)
        NumPut("int", 0, "int", 0, "int", width, "int", height, rc)
        DllCall("User32\FillRect", "ptr", memDc, "ptr", rc, "ptr", bgBrush)
        DllCall("Gdi32\DeleteObject", "ptr", bgBrush)

        slotWidth := 4
        slotGap := 8
        totalWidth := (this.WaveSlotHeights.Length * slotWidth) + ((this.WaveSlotHeights.Length - 1) * slotGap)
        startX := Round((width - totalWidth) / 2)
        centerY := Round(height / 2)
        activeColor := this.ColorRef("5B7CFA")
        quietColor := this.ColorRef("5E7CFF")
        isQuiet := level < 6

        for index, baseHeight in this.WaveSlotHeights {
            wave := 0.86 + (0.14 * Sin((this.WaveTick + index * 3) / 4.2))
            centerBoost := index >= 13 && index <= 18 ? 1.2 : 0.92
            slotHeight := isQuiet ? 3 : Max(4, Round(baseHeight * Max(level, 18) / 72 * wave * centerBoost))
            slotHeight := Min(32, slotHeight)
            x := startX + ((index - 1) * (slotWidth + slotGap))
            y := centerY - Round(slotHeight / 2)
            color := isQuiet ? quietColor : activeColor
            this.DrawRoundedSlot(memDc, x, y, slotWidth, slotHeight, color)
        }

        DllCall("Gdi32\SelectObject", "ptr", memDc, "ptr", oldBitmap)
        DllCall("Gdi32\DeleteDC", "ptr", memDc)
        DllCall("User32\ReleaseDC", "ptr", 0, "ptr", screenDc)
        oldImage := DllCall("User32\SendMessageW", "ptr", this.WaveCanvasCtrl.Hwnd, "uint", 0x0172, "ptr", 0, "ptr", hBitmap, "ptr")
        if oldImage
            DllCall("Gdi32\DeleteObject", "ptr", oldImage)
        if this.WaveBitmap && this.WaveBitmap != oldImage
            DllCall("Gdi32\DeleteObject", "ptr", this.WaveBitmap)
        this.WaveBitmap := hBitmap
        DllCall("User32\InvalidateRect", "ptr", this.WaveCanvasCtrl.Hwnd, "ptr", 0, "int", true)
    }

    static DrawRoundedSlot(hdc, x, y, width, height, colorRef) {
        brush := DllCall("Gdi32\CreateSolidBrush", "uint", colorRef, "ptr")
        pen := DllCall("Gdi32\CreatePen", "int", 0, "int", 1, "uint", colorRef, "ptr")
        oldBrush := DllCall("Gdi32\SelectObject", "ptr", hdc, "ptr", brush, "ptr")
        oldPen := DllCall("Gdi32\SelectObject", "ptr", hdc, "ptr", pen, "ptr")
        radius := Max(width, Min(height, width * 2))
        DllCall("Gdi32\RoundRect", "ptr", hdc, "int", x, "int", y, "int", x + width, "int", y + height, "int", radius, "int", radius)
        DllCall("Gdi32\SelectObject", "ptr", hdc, "ptr", oldBrush)
        DllCall("Gdi32\SelectObject", "ptr", hdc, "ptr", oldPen)
        DllCall("Gdi32\DeleteObject", "ptr", brush)
        DllCall("Gdi32\DeleteObject", "ptr", pen)
    }

    static ColorRef(hex) {
        value := Integer("0x" . hex)
        return ((value & 0xFF) << 16) | (value & 0xFF00) | ((value >> 16) & 0xFF)
    }

    static ClearText() {
        this.LastText := ""
        this.TextCtrl.Value := ""
        this.ResultTextCtrl.Value := "识别内容会显示在这里"
        this.ScrollResultToLatest()
        this.HintCtrl.Visible := true
        this.ShowResultBox(false)
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
        this.UpdateVolume(0)
    }

    static Hide() {
        this.StopWave()
        if this.FloatGui != ""
            this.FloatGui.Hide()
        this.LastText := ""
        if this.ResultTextCtrl != ""
            this.ResultTextCtrl.Value := "识别内容会显示在这里"
        this.ScrollResultToLatest()
        if this.HintCtrl != ""
            this.HintCtrl.Visible := true
        this.ShowResultBox(false)
        this.Mode := ""
    }
}
