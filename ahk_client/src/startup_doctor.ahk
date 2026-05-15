; ============================================
; 启动体检和安全自动修复
; ============================================
#Requires AutoHotkey v2.0

class StartupDoctor {
    static Run(autoStartEnabled := true, repairHotkeys := true) {
        report := { fixed: [], warnings: [] }
        Logger.Info("startup_doctor_start auto_start=" . (autoStartEnabled ? "1" : "0"))

        if repairHotkeys
            this.RepairHotkeyConfig(report)

        try this.CloseDuplicateAppProcesses(report)
        catch as e
            this.Warn(report, "duplicate_process_scan_failed " . e.Message)
        try this.CloseOrphanBridgeProcesses(report)
        catch as e
            this.Warn(report, "bridge_process_scan_failed " . e.Message)
        try this.RepairStartupEntries(autoStartEnabled, report)
        catch as e
            this.Warn(report, "startup_entry_repair_failed " . e.Message)

        Logger.Info("startup_doctor_done fixed=" . report.fixed.Length . " warnings=" . report.warnings.Length)
        return report
    }

    static RepairHotkeyConfig(report := "") {
        if !IsObject(report)
            report := { fixed: [], warnings: [] }
        try {
            if Config.RepairHotkeyConfig()
                this.Fixed(report, "hotkey_config_repaired")
        } catch as e {
            this.Warn(report, "hotkey_config_repair_failed " . e.Message)
        }
        return report
    }

    static RepairStartupEntries(autoStartEnabled, report) {
        startupDir := Config.StartupDir()
        canonical := Config.StartupPath()
        if startupDir = ""
            return
        if !FileExist(startupDir)
            DirCreate(startupDir)

        Loop Files startupDir . "\*.*", "F" {
            path := A_LoopFileFullPath
            if this.SamePath(path, canonical)
                continue
            if this.IsKnownStartupConflict(path) {
                this.DeleteStartupEntry(path, report, "legacy_or_duplicate_startup")
            }
        }

        if autoStartEnabled {
            if Config.SetAutoStart(true)
                this.Fixed(report, "startup_refreshed path=" . canonical)
            else
                this.Warn(report, "startup_refresh_failed path=" . canonical)
        } else {
            if FileExist(canonical)
                this.DeleteStartupEntry(canonical, report, "autostart_disabled")
        }
    }

    static IsKnownStartupConflict(path) {
        SplitPath(path, &name)
        lowerName := StrLower(name)
        if lowerName = "doubaoime-asr.bat"
            return true
        if lowerName = "doubao asr helper.lnk" || lowerName = "doubaoasrhelper.lnk" || lowerName = "豆包语音助手.bat"
            return true

        if !(InStr(lowerName, "doubao") || InStr(lowerName, "豆包") || InStr(lowerName, "asr"))
            return false

        lowerPath := StrLower(path)
        if InStr(lowerPath, ".lnk")
            return this.ShortcutLooksLikeThisApp(path)
        if InStr(lowerPath, ".bat") || InStr(lowerPath, ".cmd")
            return this.ScriptLooksLikeThisApp(path)
        return false
    }

    static ShortcutLooksLikeThisApp(path) {
        try {
            shortcut := ComObject("WScript.Shell").CreateShortcut(path)
            text := StrLower(shortcut.TargetPath . " " . shortcut.Arguments . " " . shortcut.WorkingDirectory)
            return InStr(text, "doubaoasrhelper") || InStr(text, "doubaoime-asr") || InStr(text, "豆包-asr") || InStr(text, "豆包语音")
        } catch {
            return false
        }
    }

    static ScriptLooksLikeThisApp(path) {
        try {
            text := StrLower(FileRead(path, "UTF-8"))
            return InStr(text, "doubaoasrhelper") || InStr(text, "doubaoime-asr") || InStr(text, "豆包-asr") || InStr(text, "豆包语音")
        } catch {
            try {
                text := StrLower(FileRead(path))
                return InStr(text, "doubaoasrhelper") || InStr(text, "doubaoime-asr") || InStr(text, "豆包-asr") || InStr(text, "豆包语音")
            }
        }
        return false
    }

    static DeleteStartupEntry(path, report, reason) {
        try {
            FileDelete(path)
            this.Fixed(report, reason . " deleted=" . path)
            return true
        } catch as e {
            this.Warn(report, reason . " delete_failed=" . path . " error=" . e.Message)
            return false
        }
    }

    static CloseDuplicateAppProcesses(report) {
        currentPid := this.CurrentPid()
        query := "SELECT ProcessId, Name, ExecutablePath FROM Win32_Process WHERE Name='DoubaoASRHelper.exe'"
        for proc in ComObjGet("winmgmts:").ExecQuery(query) {
            pid := Integer(proc.ProcessId)
            if pid = currentPid
                continue
            if this.PathLooksRelated(proc.ExecutablePath) {
                this.CloseProcess(pid, report, "duplicate_app", proc.ExecutablePath)
            }
        }
    }

    static CloseOrphanBridgeProcesses(report) {
        query := "SELECT ProcessId, Name, ExecutablePath FROM Win32_Process WHERE Name='asr_bridge.exe'"
        for proc in ComObjGet("winmgmts:").ExecQuery(query) {
            if this.PathLooksRelated(proc.ExecutablePath)
                this.CloseProcess(Integer(proc.ProcessId), report, "orphan_bridge", proc.ExecutablePath)
        }
    }

    static CloseProcess(pid, report, reason, path := "") {
        try {
            ProcessClose(pid)
            this.Fixed(report, reason . " closed pid=" . pid . " path=" . path)
            return true
        } catch as e {
            this.Warn(report, reason . " close_failed pid=" . pid . " path=" . path . " error=" . e.Message)
            return false
        }
    }

    static PathLooksRelated(path) {
        if path = ""
            return false
        lower := StrLower(path)
        return InStr(lower, "doubaoasrhelper") || InStr(lower, "doubaoime-asr") || InStr(lower, "豆包-asr")
    }

    static SamePath(left, right) {
        return StrLower(left) = StrLower(right)
    }

    static CurrentPid() {
        return DllCall("GetCurrentProcessId", "UInt")
    }

    static Fixed(report, text) {
        report.fixed.Push(text)
        Logger.Info("startup_doctor_fixed " . text)
    }

    static Warn(report, text) {
        report.warnings.Push(text)
        Logger.Warn("startup_doctor_warning " . text)
    }
}

RunStartupDoctorSelfTest(reportPath := "") {
    sandbox := A_Temp . "\DoubaoASRHelper-startup-doctor-" . A_TickCount
    startupDir := sandbox . "\Startup"
    if FileExist(sandbox)
        DirDelete(sandbox, true)
    DirCreate(startupDir)
    EnvSet("DOUBAO_ASR_STARTUP_DIR", startupDir)

    Config.FilePath := sandbox . "\config.ini"
    Config.Init()
    Config.Set("HoldToTalkKey", "x")
    Config.Set("FreeToTalkKey", "x")
    Config.Set("AutoSendKey", "^!Enter")
    Config.Set("CancelKey", "Escape")
    Config.Set("DouBaoHotkey", "^!d")
    Config.Save()

    legacyBat := startupDir . "\doubaoime-asr.bat"
    duplicateShortcut := startupDir . "\Doubao ASR Helper.lnk"
    canonicalShortcut := Config.StartupPath()
    unrelated := startupDir . "\unrelated.txt"

    FileAppend('@echo off`r`nstart "" "' . A_ScriptFullPath . '" --hidden`r`n', legacyBat, "UTF-8")
    FileCreateShortcut(A_ScriptFullPath, duplicateShortcut, A_ScriptDir, "--hidden")
    FileAppend("keep", unrelated, "UTF-8")

    report := StartupDoctor.Run(true)
    Config.Load()

    shortcutTarget := ""
    shortcutArgs := ""
    try {
        FileGetShortcut(canonicalShortcut, &shortcutTarget, , &shortcutArgs)
    }

    ok := (
        !FileExist(legacyBat)
        && !FileExist(duplicateShortcut)
        && FileExist(canonicalShortcut)
        && FileExist(unrelated)
        && InStr(shortcutArgs, "--hidden")
        && Config.Get("HoldToTalkKey") = "RCtrl"
        && Config.Get("FreeToTalkKey") = "^!Space"
        && Config.Get("AutoSendKey") = "^!Enter"
        && Config.Get("CancelKey") = "Escape"
        && Config.Get("DouBaoHotkey") = "^!d"
    )

    if reportPath = ""
        reportPath := sandbox . "\startup-doctor-report.json"
    else if DirExist(reportPath)
        reportPath := RTrim(reportPath, "\/") . "\startup-doctor-report.json"
    reportDir := DirName(reportPath)
    if reportDir != "" && !FileExist(reportDir)
        DirCreate(reportDir)
    if FileExist(reportPath) {
        try FileDelete(reportPath)
        catch as e {
            Logger.Warn("startup_doctor_report_delete_failed path=" . reportPath . " error=" . e.Message)
            reportPath := reportDir . "\startup-doctor-report-" . A_TickCount . ".json"
        }
    }
    q := Chr(34)
    json := "{`n"
    json .= "  " . q . "ok" . q . ": " . (ok ? "true" : "false") . ",`n"
    json .= "  " . q . "sandbox" . q . ": " . q . StartupDoctorJsonEscape(sandbox) . q . ",`n"
    json .= "  " . q . "startup_dir" . q . ": " . q . StartupDoctorJsonEscape(startupDir) . q . ",`n"
    json .= "  " . q . "canonical_shortcut" . q . ": " . q . StartupDoctorJsonEscape(canonicalShortcut) . q . ",`n"
    json .= "  " . q . "shortcut_target" . q . ": " . q . StartupDoctorJsonEscape(shortcutTarget) . q . ",`n"
    json .= "  " . q . "shortcut_args" . q . ": " . q . StartupDoctorJsonEscape(shortcutArgs) . q . ",`n"
    json .= "  " . q . "legacy_bat_removed" . q . ": " . (!FileExist(legacyBat) ? "true" : "false") . ",`n"
    json .= "  " . q . "duplicate_shortcut_removed" . q . ": " . (!FileExist(duplicateShortcut) ? "true" : "false") . ",`n"
    json .= "  " . q . "unrelated_preserved" . q . ": " . (FileExist(unrelated) ? "true" : "false") . ",`n"
    json .= "  " . q . "hotkeys_repaired" . q . ": " . ((Config.Get("HoldToTalkKey") = "RCtrl" && Config.Get("FreeToTalkKey") = "^!Space") ? "true" : "false") . ",`n"
    json .= "  " . q . "fixed_count" . q . ": " . report.fixed.Length . ",`n"
    json .= "  " . q . "warning_count" . q . ": " . report.warnings.Length . "`n"
    json .= "}`n"
    FileAppend(json, reportPath, "UTF-8")

    if !ok
        ExitApp(2)
}

StartupDoctorJsonEscape(text) {
    quote := Chr(34)
    text := StrReplace(text, "\", "\\")
    text := StrReplace(text, quote, "\" . quote)
    text := StrReplace(text, "`r", "\r")
    text := StrReplace(text, "`n", "\n")
    return text
}

DirName(path) {
    SplitPath(path, , &dir)
    return dir
}
