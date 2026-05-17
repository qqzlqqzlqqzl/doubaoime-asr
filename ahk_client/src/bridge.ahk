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
    static LaunchInProgress := false
    static LaunchStartedAt := 0

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
            this.LaunchInProgress := false
            return true
        }

        if this.WarmupStarted || this.LaunchInProgress {
            waitMs := this.LaunchInProgress ? 12000 : 10000
            if this.WaitForAvailable(waitMs)
                return true
            if this.LaunchInProgress {
                Logger.Warn("bridge_launch_still_starting elapsed_ms=" . (A_TickCount - this.LaunchStartedAt))
                if this.WaitForAvailable(5000)
                    return true
            }
            if this.ProcessHandle != "" && ProcessExist(this.ProcessHandle) {
                elapsedMs := A_TickCount - this.LaunchStartedAt
                if elapsedMs < 25000 {
                    Logger.Warn("bridge_warmup_waiting pid=" . this.ProcessHandle . " elapsed_ms=" . elapsedMs)
                    if this.WaitForAvailable(25000 - elapsedMs)
                        return true
                }
                Logger.Error("bridge_warmup_not_ready pid=" . this.ProcessHandle)
                return false
            }
            if this.LaunchInProgress && (A_TickCount - this.LaunchStartedAt) < 15000 {
                Logger.Error("bridge_launch_no_pid_yet elapsed_ms=" . (A_TickCount - this.LaunchStartedAt))
                return false
            }
            this.WarmupStarted := false
            this.LaunchInProgress := false
            this.ProcessHandle := ""
        }

        if !this.LaunchBridge("bridge_launch", "bridge_launch_pid")
            return false

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
        if this.WarmupStarted || this.LaunchInProgress
            return true
        if this.IsAvailableFast() {
            this.WarmupStarted := true
            return true
        }

        return this.LaunchBridge("bridge_warmup_launch", "bridge_warmup_pid")
    }

    static LaunchBridge(launchEvent, pidEvent) {
        exe := this.BridgeExePath()
        if exe = "" {
            Logger.Error(launchEvent . "_exe_missing")
            return false
        }

        this.WarmupStarted := true
        this.LaunchInProgress := true
        this.LaunchStartedAt := A_TickCount
        try {
            Logger.Info(launchEvent . " exe=" . exe . " port=" . this.Port)
            Run('"' . exe . '" --host ' . this.Host . ' --port ' . this.Port, , "Hide", &pid)
            this.ProcessHandle := pid
            this.LaunchInProgress := false
            Logger.Info(pidEvent . " pid=" . pid)
            return true
        } catch as e {
            this.WarmupStarted := false
            this.LaunchInProgress := false
            this.ProcessHandle := ""
            Logger.Exception(launchEvent . "_failed exe=" . exe, e)
            return false
        }
    }

    static SelfCheck(repair := true, reason := "manual") {
        Logger.Info("bridge_self_check_start reason=" . reason)
        if !this.EnsureRunning() {
            Logger.Error("bridge_self_check_failed reason=" . reason . " error=unavailable")
            return { ok: false, repaired: false, error: "ASR bridge 未启动", state: "offline" }
        }

        try {
            status := this.ParseResult(this.Request("GET", "/status", "", 1200))
        } catch as e {
            Logger.Exception("bridge_self_check_status_exception reason=" . reason, e)
            if repair
                return this.Repair(reason . "_status_exception")
            return { ok: false, repaired: false, error: e.Message, state: "offline" }
        }

        if status.error != "" {
            Logger.Warn("bridge_self_check_dirty reason=" . reason . " state=" . status.state . " error=" . status.error)
            if repair
                return this.Repair(reason . "_dirty_status")
            return { ok: false, repaired: false, error: status.error, state: status.state }
        }

        Logger.Info("bridge_self_check_ok reason=" . reason . " state=" . status.state)
        return { ok: true, repaired: false, error: "", state: status.state }
    }

    static Repair(reason := "manual") {
        Logger.Warn("bridge_repair_start reason=" . reason)
        reset := this.Reset(reason)
        if reset.ok {
            Logger.Warn("bridge_repair_reset_ok reason=" . reason . " state=" . reset.state)
            return { ok: true, repaired: true, error: "", state: reset.state }
        }

        Logger.Warn("bridge_repair_reset_failed reason=" . reason . " error=" . reset.error)
        this.StopManagedBridge()
        if this.EnsureRunning() {
            Logger.Warn("bridge_repair_restart_ok reason=" . reason)
            return { ok: true, repaired: true, error: "", state: "ready" }
        }
        Logger.Error("bridge_repair_failed reason=" . reason)
        return { ok: false, repaired: false, error: "ASR bridge 自动修复失败", state: "offline" }
    }

    static Reset(reason := "manual") {
        if !this.EnsureRunning()
            return { ok: false, text: "", final_text: "", state: "offline", error: "ASR bridge 未启动", done: false, cancelled: false, session_id: 0, audio_level: 0 }
        try {
            Logger.Warn("bridge_reset_request reason=" . reason)
            response := this.Request("POST", "/reset", "{}", 3000)
            return this.ParseResult(response)
        } catch as e {
            Logger.Exception("bridge_reset_exception reason=" . reason, e)
            return { ok: false, text: "", final_text: "", state: "error", error: e.Message, done: false, cancelled: false, session_id: 0, audio_level: 0 }
        }
    }

    static StopManagedBridge() {
        if this.ProcessHandle != "" {
            try {
                Logger.Warn("bridge_process_close pid=" . this.ProcessHandle)
                RunWait("taskkill /F /T /PID " . this.ProcessHandle, , "Hide")
            }
            this.ProcessHandle := ""
            this.WarmupStarted := false
            this.LaunchInProgress := false
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
        check := this.SelfCheck(true, "before_start_" . mode)
        if !check.ok
            return { ok: false, error: check.error }
        body := '{"mode":"' . mode . '"}'
        try {
            response := this.Request("POST", "/start", body, 3000)
            result := this.ParseResult(response)
            if !result.ok && result.error = "already_recording"
                return this.RecoverAlreadyRecording(mode, body, result)
            if !result.ok
                Logger.Error("bridge_start_rejected mode=" . mode . " error=" . result.error)
            return result
        } catch as e {
            Logger.Exception("bridge_start_exception mode=" . mode, e)
            return { ok: false, text: "", final_text: "", state: "error", error: e.Message, done: false, cancelled: false, session_id: 0, audio_level: 0 }
        }
    }

    static RecoverAlreadyRecording(mode, body, firstResult) {
        Logger.Warn("bridge_start_already_recording_recover mode=" . mode . " state=" . firstResult.state . " session=" . firstResult.session_id)
        this.Cancel()
        Sleep(200)
        try {
            response := this.Request("POST", "/start", body, 3000)
            result := this.ParseResult(response)
            if result.ok {
                Logger.Info("bridge_start_recovered mode=" . mode . " session=" . result.session_id)
                return result
            }
            Logger.Error("bridge_start_recovery_failed mode=" . mode . " error=" . result.error)
            return result
        } catch as e {
            Logger.Exception("bridge_start_recovery_exception mode=" . mode, e)
            return { ok: false, text: "", final_text: "", state: "error", error: "上一次录音还在收尾，请稍后再试", done: false, cancelled: false, session_id: 0, audio_level: 0 }
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
