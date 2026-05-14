; ============================================
; 本地 ASR Bridge 调用模块
; 只负责启动 Python bridge，并通过 HTTP 调用 start/stop/cancel/status
; ============================================
#Requires AutoHotkey v2.0

class BridgeClient {
    static Host := "127.0.0.1"
    static Port := 18765
    static ProcessHandle := ""

    static BaseUrl() {
        return "http://" . this.Host . ":" . this.Port
    }

    static BridgeExePath() {
        candidates := [
            A_ScriptDir . "\asr_bridge.exe",
            A_ScriptDir . "\..\asr_bridge.exe",
            A_ScriptDir . "\..\dist\asr_bridge.exe",
            A_ScriptDir . "\..\..\dist\asr_bridge.exe"
        ]
        for path in candidates {
            if FileExist(path)
                return path
        }
        return ""
    }

    static EnsureRunning() {
        if this.IsAvailable()
            return true

        exe := this.BridgeExePath()
        if exe = ""
            return false

        try {
            Run('"' . exe . '" --host ' . this.Host . ' --port ' . this.Port, , "Hide", &pid)
        } catch {
            return false
        }

        startTime := A_TickCount
        while (A_TickCount - startTime) < 5000 {
            if this.IsAvailable()
                return true
            Sleep(150)
        }
        return false
    }

    static IsAvailable() {
        try {
            response := this.Request("GET", "/health", "", 800)
            return InStr(response, '"ok": true') || InStr(response, '"ok":true')
        } catch {
            return false
        }
    }

    static Start(mode := "hold") {
        if !this.EnsureRunning()
            return { ok: false, error: "ASR bridge 未启动" }
        body := '{"mode":"' . mode . '"}'
        response := this.Request("POST", "/start", body, 3000)
        return this.ParseResult(response)
    }

    static Stop(timeoutMs := 30000) {
        if !this.EnsureRunning()
            return { ok: false, text: "", error: "ASR bridge 未启动" }
        body := '{"timeout_ms":' . timeoutMs . '}'
        response := this.Request("POST", "/stop", body, timeoutMs + 5000)
        return this.ParseResult(response)
    }

    static StopAsync() {
        if !this.EnsureRunning()
            return { ok: false, text: "", error: "ASR bridge 未启动" }
        response := this.Request("POST", "/stop", '{"wait":false,"timeout_ms":1}', 2000)
        return this.ParseResult(response)
    }

    static Cancel() {
        if !this.EnsureRunning()
            return { ok: true, error: "" }
        response := this.Request("POST", "/cancel", "{}", 3000)
        return this.ParseResult(response)
    }

    static Status() {
        if !this.EnsureRunning()
            return { ok: false, state: "offline", text: "", error: "ASR bridge 未启动" }
        response := this.Request("GET", "/status", "", 1000)
        return this.ParseResult(response)
    }

    static Request(method, path, body := "", timeoutMs := 3000) {
        http := ComObject("WinHttp.WinHttpRequest.5.1")
        http.SetTimeouts(1000, 1000, timeoutMs, timeoutMs)
        http.Open(method, this.BaseUrl() . path, false)
        if body != "" {
            http.SetRequestHeader("Content-Type", "application/json; charset=utf-8")
            http.Send(body)
        } else {
            http.Send()
        }
        if http.Status < 200 || http.Status >= 300
            throw Error("HTTP " . http.Status)
        return http.ResponseText
    }

    static ParseResult(jsonText) {
        return {
            ok: this.JsonBool(jsonText, "ok", false),
            text: this.JsonString(jsonText, "text", ""),
            final_text: this.JsonString(jsonText, "final_text", ""),
            state: this.JsonString(jsonText, "state", ""),
            error: this.JsonString(jsonText, "error", ""),
            done: this.JsonBool(jsonText, "done", false),
            cancelled: this.JsonBool(jsonText, "cancelled", false)
        }
    }

    static JsonBool(jsonText, key, defaultValue := false) {
        pattern := '"' . key . '"\s*:\s*(true|false)'
        if RegExMatch(jsonText, pattern, &match)
            return match[1] = "true"
        return defaultValue
    }

    static JsonString(jsonText, key, defaultValue := "") {
        pattern := '"' . key . '"\s*:\s*"((?:\\.|[^"\\])*)"'
        if RegExMatch(jsonText, pattern, &match)
            return this.JsonUnescape(match[1])
        return defaultValue
    }

    static JsonUnescape(value) {
        value := StrReplace(value, '\"', '"')
        value := StrReplace(value, "\\", "\")
        value := StrReplace(value, "\n", "`n")
        value := StrReplace(value, "\r", "`r")
        value := StrReplace(value, "\t", "`t")
        return value
    }
}
