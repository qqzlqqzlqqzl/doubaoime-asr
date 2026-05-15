; ============================================
; 配置管理模块
; ============================================
#Requires AutoHotkey v2.0

class Config {
    static Version := 3

    ; 默认配置
    static Default := Map(
        "HoldToTalkKey", "RCtrl",
        "FreeToTalkKey", "^!Space",
        "AutoSendKey", "^!Enter",
        "CancelKey", "Escape",
        "AutoSendDelay", 50,
        "DouBaoHotkey", "^!d",
        "InsertDelay", 300,
        "ClipboardProtect", 1,
        "AutoStart", 1,
        "FocusRecovery", 1,
        "ShowTrayTip", 1,
        "ClipboardTimeout", 100
    )

    ; 当前配置
    static Current := Map()

    ; 配置文件路径（优先使用外部文件，不存在则使用用户目录）
    static FilePath := ""

    ; 获取配置文件路径
    static GetFilePath() {
        if this.FilePath != ""
            return this.FilePath

        ; 优先使用程序同目录的 config.ini
        localConfig := A_ScriptDir . "\..\config.ini"
        if FileExist(localConfig) {
            this.FilePath := localConfig
            return this.FilePath
        }

        ; 如果不存在，使用用户目录（支持单文件运行）
        appDataDir := EnvGet("APPDATA")
        if appDataDir = ""
            appDataDir := A_AppData

        userDir := appDataDir . "\DoubaoASRHelper"
        if !FileExist(userDir)
            DirCreate(userDir)

        userConfig := userDir . "\config.ini"
        legacyConfig := appDataDir . "\DouBaoVoiceHelper\config.ini"
        if !FileExist(userConfig) && FileExist(legacyConfig) {
            try {
                FileCopy(legacyConfig, userConfig, 1)
            } catch {
                try {
                    FileAppend(FileRead(legacyConfig, "UTF-8"), userConfig, "UTF-8")
                }
            }
        }

        this.FilePath := userConfig
        return this.FilePath
    }

    ; 初始化配置
    ; 返回值：true = 配置文件存在（非首次运行），false = 配置文件不存在（首次运行）
    static Init() {
        ; 先加载默认值
        for key, value in this.Default {
            this.Current[key] := value
        }

        ; 从文件加载（如果存在）
        return this.Load()
    }

    ; 从INI文件加载配置
    static Load() {
        filePath := this.GetFilePath()
        if !FileExist(filePath)
            return false

        try {
            filePath := this.GetFilePath()
            ; General 部分
            this.Current["HoldToTalkKey"] := IniRead(filePath, "General", "HoldToTalkKey", this.Default["HoldToTalkKey"])
            this.Current["FreeToTalkKey"] := IniRead(filePath, "General", "FreeToTalkKey", this.Default["FreeToTalkKey"])
            this.Current["AutoSendKey"] := IniRead(filePath, "General", "AutoSendKey", this.Default["AutoSendKey"])
            this.Current["CancelKey"] := IniRead(filePath, "General", "CancelKey", this.Default["CancelKey"])
            this.Current["AutoSendDelay"] := Integer(IniRead(filePath, "General", "AutoSendDelay", this.Default["AutoSendDelay"]))
            this.Current["DouBaoHotkey"] := IniRead(filePath, "General", "DouBaoHotkey", this.Default["DouBaoHotkey"])
            this.Current["InsertDelay"] := Integer(IniRead(filePath, "General", "InsertDelay", this.Default["InsertDelay"]))
            this.Current["ClipboardProtect"] := Integer(IniRead(filePath, "General", "ClipboardProtect", this.Default["ClipboardProtect"]))
            this.Current["AutoStart"] := Integer(IniRead(filePath, "General", "AutoStart", this.Default["AutoStart"]))
            configVersion := Integer(IniRead(filePath, "General", "ConfigVersion", 0))

            ; Advanced 部分
            this.Current["FocusRecovery"] := Integer(IniRead(filePath, "Advanced", "FocusRecovery", this.Default["FocusRecovery"]))
            this.Current["ShowTrayTip"] := Integer(IniRead(filePath, "Advanced", "ShowTrayTip", this.Default["ShowTrayTip"]))
            this.Current["ClipboardTimeout"] := Integer(IniRead(filePath, "Advanced", "ClipboardTimeout", this.Default["ClipboardTimeout"]))

            if configVersion < this.Version {
                this.MigrateDefaults(configVersion)
                this.Save()
            }

            return true
        } catch as e {
            return false
        }
    }

    ; 只迁移旧版默认值，保留用户自定义热键
    static MigrateDefaults(configVersion) {
        if configVersion < 2 {
            if this.Current["AutoSendKey"] = "LCtrl & LWin"
                this.Current["AutoSendKey"] := this.Default["AutoSendKey"]
            if this.Current["CancelKey"] = "z"
                this.Current["CancelKey"] := this.Default["CancelKey"]
            if this.Current["DouBaoHotkey"] = "^d"
                this.Current["DouBaoHotkey"] := this.Default["DouBaoHotkey"]
        }
        if configVersion < 3 {
            if this.Current["FreeToTalkKey"] = "XButton1"
                this.Current["FreeToTalkKey"] := this.Default["FreeToTalkKey"]
            if this.Current["AutoSendKey"] = "F9"
                this.Current["AutoSendKey"] := this.Default["AutoSendKey"]
            if this.Current["CancelKey"] = "F12"
                this.Current["CancelKey"] := this.Default["CancelKey"]
            if this.Current["DouBaoHotkey"] = "^!+d"
                this.Current["DouBaoHotkey"] := this.Default["DouBaoHotkey"]
        }
    }

    ; 保存配置到INI文件
    static Save() {
        try {
            filePath := this.GetFilePath()
            ; General 部分
            IniWrite(this.Current["HoldToTalkKey"], filePath, "General", "HoldToTalkKey")
            IniWrite(this.Current["FreeToTalkKey"], filePath, "General", "FreeToTalkKey")
            IniWrite(this.Current["AutoSendKey"], filePath, "General", "AutoSendKey")
            IniWrite(this.Current["CancelKey"], filePath, "General", "CancelKey")
            IniWrite(this.Current["AutoSendDelay"], filePath, "General", "AutoSendDelay")
            IniWrite(this.Current["DouBaoHotkey"], filePath, "General", "DouBaoHotkey")
            IniWrite(this.Current["InsertDelay"], filePath, "General", "InsertDelay")
            IniWrite(this.Current["ClipboardProtect"], filePath, "General", "ClipboardProtect")
            IniWrite(this.Current["AutoStart"], filePath, "General", "AutoStart")
            IniWrite(this.Version, filePath, "General", "ConfigVersion")

            ; Advanced 部分
            IniWrite(this.Current["FocusRecovery"], filePath, "Advanced", "FocusRecovery")
            IniWrite(this.Current["ShowTrayTip"], filePath, "Advanced", "ShowTrayTip")
            IniWrite(this.Current["ClipboardTimeout"], filePath, "Advanced", "ClipboardTimeout")

            return true
        } catch as e {
            return false
        }
    }

    ; 获取配置值
    static Get(key) {
        return this.Current.Has(key) ? this.Current[key] : ""
    }

    ; 设置配置值
    static Set(key, value) {
        this.Current[key] := value
    }

    ; 设置开机自启动
    static SetAutoStart(enable) {
        startupPath := A_Startup . "\豆包语音助手.lnk"

        if enable {
            try {
                FileCreateShortcut(A_ScriptFullPath, startupPath, A_ScriptDir, "--hidden")
                return true
            } catch {
                return false
            }
        } else {
            try {
                if FileExist(startupPath)
                    FileDelete(startupPath)
                return true
            } catch {
                return false
            }
        }
    }

    ; 检查是否已设置开机自启动
    static IsAutoStartEnabled() {
        return FileExist(A_Startup . "\豆包语音助手.lnk") ? true : false
    }

    static RefreshAutoStartShortcut() {
        if this.IsAutoStartEnabled()
            return this.SetAutoStart(true)
        return true
    }
}
