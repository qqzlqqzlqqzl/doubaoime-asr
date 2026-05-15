; ============================================
; 轻量 UI 样式辅助
; ============================================
#Requires AutoHotkey v2.0

class UiStyle {
    static RoundButton(ctrl, cornerRadius := 4) {
        if ctrl = ""
            return
        try {
            rect := Buffer(16, 0)
            if !DllCall("User32\GetWindowRect", "ptr", ctrl.Hwnd, "ptr", rect)
                return
            width := NumGet(rect, 8, "int") - NumGet(rect, 0, "int")
            height := NumGet(rect, 12, "int") - NumGet(rect, 4, "int")
            if width <= 0 || height <= 0
                return
            dpi := this.GetDpiForWindow(ctrl.Hwnd)
            diameter := Max(2, Round(cornerRadius * 2 * dpi / 96))
            diameter := Min(diameter, width, height)
            region := DllCall(
                "Gdi32\CreateRoundRectRgn",
                "int", 0,
                "int", 0,
                "int", width + 1,
                "int", height + 1,
                "int", diameter,
                "int", diameter,
                "ptr"
            )
            if region && DllCall("User32\SetWindowRgn", "ptr", ctrl.Hwnd, "ptr", region, "int", true) {
                DllCall("User32\InvalidateRect", "ptr", ctrl.Hwnd, "ptr", 0, "int", true)
                DllCall("User32\RedrawWindow", "ptr", ctrl.Hwnd, "ptr", 0, "ptr", 0, "uint", 0x0105)
            } else if region {
                DllCall("Gdi32\DeleteObject", "ptr", region)
            }
        } catch as e {
            Logger.Exception("round_button_failed", e)
        }
    }

    static RoundButtons(controls, cornerRadius := 4) {
        for ctrl in controls
            this.RoundButton(ctrl, cornerRadius)
    }

    static GetDpiForWindow(hwnd) {
        try {
            dpi := DllCall("User32\GetDpiForWindow", "ptr", hwnd, "uint")
            if dpi > 0
                return dpi
        }
        return A_ScreenDPI ? A_ScreenDPI : 96
    }

    static GetClassName(hwnd) {
        className := Buffer(512, 0)
        length := DllCall("User32\GetClassNameW", "ptr", hwnd, "ptr", className, "int", 256)
        if length <= 0
            return ""
        return StrGet(className, length, "UTF-16")
    }

    static SetControlText(ctrl, text) {
        if ctrl = ""
            return
        try {
            if this.GetClassName(ctrl.Hwnd) = "Button" {
                ctrl.Text := text
                return
            }
        } catch {
        }
        try {
            ctrl.Value := text
            return
        } catch {
            try ctrl.Text := text
        }
    }
}
