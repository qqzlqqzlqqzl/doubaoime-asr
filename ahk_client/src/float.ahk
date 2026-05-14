; ============================================
; 语音悬浮窗
; 显示录音/识别状态和实时转写文本，不抢前台焦点
; ============================================
#Requires AutoHotkey v2.0

class VoiceFloat {
    static FloatGui := ""
    static TextCtrl := ""
    static StateCtrl := ""
    static LastText := ""

    static Ensure() {
        if this.FloatGui != ""
            return

        this.FloatGui := Gui("+AlwaysOnTop -Caption +ToolWindow +Border")
        this.FloatGui.BackColor := "FFFFFF"
        this.FloatGui.MarginX := 0
        this.FloatGui.MarginY := 0
        this.FloatGui.SetFont("s10", "Microsoft YaHei")
        this.StateCtrl := this.FloatGui.AddText("x18 y12 w460 h22 c777777", "🎙 正在聆听")
        this.TextCtrl := this.FloatGui.AddText("x18 y38 w460 h56 c333333", "开始说话...")
    }

    static Show(text := "开始说话...", state := "🎙 正在聆听") {
        this.Ensure()
        this.Update(text, state)
        x := Round((A_ScreenWidth - 520) / 2)
        y := Round(A_ScreenHeight * 0.62)
        this.FloatGui.Show("NoActivate x" . x . " y" . y . " w520 h112")
        try WinSetTransparent(245, this.FloatGui.Hwnd)
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
            this.TextCtrl.Value := "开始说话..."
        }
    }

    static Hide() {
        if this.FloatGui != ""
            this.FloatGui.Hide()
        this.LastText := ""
    }
}
