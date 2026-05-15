from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_ahk_main_repairs_hotkeys_before_registration_and_defers_full_doctor() -> None:
    source = _read("ahk_client/src/main.ahk")

    assert "#Include startup_doctor.ahk" in source
    assert "StartupDoctor.RepairHotkeyConfig()" in source
    assert "StartupDoctor.Run(Config.Get(\"AutoStart\"), false)" in source
    assert "SetTimer(() => this.SetupTray(), -600)" in source
    assert "SetTimer(() => this.EnsureHotkeysInitialized(), -800)" in source
    assert "SetTimer(() => BridgeClient.Warmup(), -1600)" in source
    assert source.index("StartupDoctor.RepairHotkeyConfig()") < source.index("this.InitHotkeys()")
    assert source.index("GuiManager.Show()") < source.index("this.EnsureHotkeysInitialized()")
    assert source.index("GuiManager.Show()") < source.index("StartupDoctor.Run(Config.Get(\"AutoStart\"), false)")
    assert source.index("GuiManager.Show()") < source.index("BridgeClient.Warmup()")


def test_startup_doctor_cleans_legacy_startup_entries_and_repairs_hotkeys() -> None:
    source = _read("ahk_client/src/startup_doctor.ahk")

    assert "doubaoime-asr.bat" in source
    assert "Doubao ASR Helper.lnk" in source
    assert "Config.RepairHotkeyConfig()" in source
    assert "DirExist(reportPath)" in source
    assert "startup_doctor_report_delete_failed" in source
    assert "--startup-doctor-report" in _read("ahk_client/src/main.ahk")


def test_ahk_hotkey_registration_rolls_back_partial_failures() -> None:
    source = _read("ahk_client/src/hotkey.ahk")

    assert "static SafeHotkeyOff(name)" in source
    assert source.count("SafeHotkeyOff") >= 12


def test_settings_save_blocks_internal_hotkey_conflicts() -> None:
    source = _read("ahk_client/src/gui.ahk")

    assert "FindInternalHotkeyConflict()" in source
    assert source.index("FindInternalHotkeyConflict()") < source.index("this.SaveConfigFromGui()")


def test_hotkey_auto_repair_restores_runtime_registration_when_candidates_fail() -> None:
    source = _read("ahk_client/src/main.ahk")

    assert "attempted := false" in source
    assert "Config.Set(field, original)" in source
    restore_block = source[source.index("Config.Set(field, original)"):]
    assert "if attempted" in restore_block
    assert "HotkeyManager.Init(" in restore_block


def test_uninstaller_removes_current_ahk_startup_shortcut() -> None:
    source = _read("windows_installer.py")

    assert "[char]35910" in source
    assert "[char]25163" in source
    assert "Remove-Item -LiteralPath (Join-Path $startup $name)" in source
