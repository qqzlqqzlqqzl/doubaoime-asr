; ============================================
; 简单文件日志
; ============================================
#Requires AutoHotkey v2.0

class Logger {
    static LogDir := ""
    static LogFile := ""

    static Init() {
        appDataDir := EnvGet("APPDATA")
        if appDataDir = ""
            appDataDir := A_AppData
        this.LogDir := appDataDir . "\DoubaoASRHelper\logs"
        if !FileExist(this.LogDir)
            DirCreate(this.LogDir)
        this.LogFile := this.LogDir . "\client-" . FormatTime(, "yyyyMMdd") . ".log"
        this.Info("client_start compiled=" . (A_IsCompiled ? "1" : "0") . " exe=" . A_ScriptFullPath)
    }

    static Write(level, message) {
        if this.LogFile = ""
            this.Init()
        line := FormatTime(, "yyyy-MM-dd HH:mm:ss") . " [" . level . "] " . message . "`n"
        try FileAppend(line, this.LogFile, "UTF-8")
    }

    static Info(message) {
        this.Write("INFO", message)
    }

    static Warn(message) {
        this.Write("WARN", message)
    }

    static Error(message) {
        this.Write("ERROR", message)
    }

    static Exception(context, err) {
        detail := context . " | " . err.Message
        try detail .= " | file=" . err.File . " line=" . err.Line
        try detail .= " | what=" . err.What
        try detail .= " | extra=" . err.Extra
        this.Error(detail)
    }

    static Path() {
        if this.LogFile = ""
            this.Init()
        return this.LogFile
    }
}

LogUnhandledError(err, mode) {
    Logger.Exception("unhandled mode=" . mode, err)
    return false
}
