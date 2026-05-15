; ============================================
; 本地 ASR Bridge 调用模块
; 只负责启动 Python bridge，并通过 HTTP 调用 start/stop/cancel/status
; ============================================
#Requires AutoHotkey v2.0

class BridgeClient {
    static Host := "127.0.0.1"
    static Port := 18765
    static ProcessHandle := ""
    static WarmupStarted := false

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
        if this.IsAvailable() {
            this.WarmupStarted := true
            return true
        }

        if this.WarmupStarted {
            if this.WaitForAvailable(5000)
                return true
            if this.ProcessHandle != "" && ProcessExist(this.ProcessHandle) {
                Logger.Error("bridge_warmup_not_ready pid=" . this.ProcessHandle)
                return false
            }
            this.WarmupStarted := false
            this.ProcessHandle := ""
        }

        exe := this.BridgeExePath()
        if exe = "" {
            Logger.Error("bridge_exe_missing")
            return false
        }

        try {
            Logger.Info("bridge_launch exe=" . exe . " port=" . this.Port)
            Run('"' . exe . '" --host ' . this.Host . ' --port ' . this.Port, , "Hide", &pid)
            Logger.Info("bridge_launch_pid pid=" . pid)
            this.ProcessHandle := pid
            this.WarmupStarted := true
        } catch {
            Logger.Error("bridge_launch_failed exe=" . exe)
            return false
        }

        return this.WaitForAvailable(5000)
    }

    static WaitForAvailable(timeoutMs := 5000) {
        startTime := A_TickCount
        while (A_TickCount - startTime) < timeoutMs {
            if this.IsAvailable()
                return true
            Sleep(150)
        }
        return false
    }

    static Warmup() {
        if this.WarmupStarted
            return true
        if this.IsAvailableFast() {
            this.WarmupStarted := true
            return true
        }

        exe := this.BridgeExePath()
        if exe = "" {
            Logger.Error("bridge_warmup_exe_missing")
            return false
        }

        try {
            Logger.Info("bridge_warmup_launch exe=" . exe . " port=" . this.Port)
            Run('"' . exe . '" --host ' . this.Host . ' --port ' . this.Port, , "Hide", &pid)
            Logger.Info("bridge_warmup_pid pid=" . pid)
            this.ProcessHandle := pid
            this.WarmupStarted := true
            return true
        } catch as e {
            Logger.Exception("bridge_warmup_launch_failed exe=" . exe, e)
            return false
        }
    }

    static IsAvailable() {
        try {
            response := this.Request("GET", "/health", "", 800)
            return InStr(response, '"ok": true') || InStr(response, '"ok":true')
        } catch {
            return false
        }
    }

    static IsAvailableFast() {
        try {
            response := this.Request("GET", "/health", "", 80)
            return InStr(response, '"ok": true') || InStr(response, '"ok":true')
        } catch {
            return false
        }
    }

    static Start(mode := "hold") {
        if !this.EnsureRunning()
            return { ok: false, error: "ASR bridge 未启动" }
        body := '{"mode":"' . mode . '"}'
        try {
            response := this.Request("POST", "/start", body, 3000)
            result := this.ParseResult(response)
            if !result.ok
                Logger.Error("bridge_start_rejected mode=" . mode . " error=" . result.error)
            return result
        } catch as e {
            Logger.Exception("bridge_start_exception mode=" . mode, e)
            return { ok: false, text: "", final_text: "", state: "error", error: e.Message, done: false, cancelled: false, session_id: 0, audio_level: 0 }
        }
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
        try {
            response := this.Request("POST", "/stop", '{"wait":false,"timeout_ms":1}', 2000)
            return this.ParseResult(response)
        } catch as e {
            Logger.Exception("bridge_stop_async_exception", e)
            return { ok: false, text: "", final_text: "", state: "error", error: e.Message, done: false, cancelled: false, session_id: 0, audio_level: 0 }
        }
    }

    static Cancel() {
        if !this.EnsureRunning()
            return { ok: true, error: "" }
        try {
            response := this.Request("POST", "/cancel", "{}", 3000)
            return this.ParseResult(response)
        } catch as e {
            Logger.Exception("bridge_cancel_exception", e)
            return { ok: false, error: e.Message }
        }
    }

    static Status() {
        if !this.EnsureRunning()
            return { ok: false, state: "offline", text: "", error: "ASR bridge 未启动" }
        try {
            response := this.Request("GET", "/status", "", 1000)
            return this.ParseResult(response)
        } catch as e {
            Logger.Exception("bridge_status_exception", e)
            return { ok: false, state: "offline", text: "", final_text: "", error: e.Message, done: false, cancelled: false, session_id: 0, audio_level: 0 }
        }
    }

    static Request(method, path, body := "", timeoutMs := 3000) {
        http := ComObject("WinHttp.WinHttpRequest.5.1")
        phaseTimeout := Min(1000, Max(50, timeoutMs))
        http.SetTimeouts(phaseTimeout, phaseTimeout, timeoutMs, timeoutMs)
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
            cancelled: this.JsonBool(jsonText, "cancelled", false),
            session_id: this.JsonNumber(jsonText, "session_id", 0),
            audio_level: this.JsonNumber(jsonText, "audio_level", 0)
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

    static JsonNumber(jsonText, key, defaultValue := 0) {
        pattern := '"' . key . '"\s*:\s*(-?\d+)'
        if RegExMatch(jsonText, pattern, &match)
            return Integer(match[1])
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
