import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLOAT_AHK = ROOT / "ahk_client" / "src" / "float.ahk"


def _control_rect(source: str, name: str) -> tuple[int, int, int, int]:
    match = re.search(rf"{name}\s*:=\s*this\.FloatGui\.Add\w+\(\"([^\"]+)\"", source)
    assert match, f"{name} declaration not found"
    options = match.group(1)
    coords = {}
    for key in ("x", "y", "w", "h"):
        coord_match = re.search(rf"(?<!\w){key}(-?\d+)", options)
        assert coord_match, f"{name} missing {key} in {options!r}"
        coords[key] = int(coord_match.group(1))
    return coords["x"], coords["y"], coords["w"], coords["h"]


def _bottom(rect: tuple[int, int, int, int]) -> int:
    return rect[1] + rect[3]


def test_float_result_text_does_not_overlap_action_buttons() -> None:
    source = FLOAT_AHK.read_text(encoding="utf-8")
    result_text = _control_rect(source, "this.ResultTextCtrl")

    for button in ("this.ClearBtn", "this.CopyBtn", "this.InsertBtn"):
        button_rect = _control_rect(source, button)
        assert _bottom(result_text) <= button_rect[1] - 6, button


def test_float_result_box_does_not_touch_window_bottom() -> None:
    source = FLOAT_AHK.read_text(encoding="utf-8")
    height_match = re.search(r"static Height := (\d+)", source)
    assert height_match, "VoiceFloat.Height not found"
    window_height = int(height_match.group(1))
    result_bg = _control_rect(source, "this.ResultBgCtrl")

    assert _bottom(result_bg) <= window_height - 6


def test_float_result_box_is_compact_but_taller() -> None:
    source = FLOAT_AHK.read_text(encoding="utf-8")
    result_text = _control_rect(source, "this.ResultTextCtrl")
    result_bg = _control_rect(source, "this.ResultBgCtrl")

    assert result_bg[1] <= 44
    assert result_text[3] >= 64
    assert 'static Height := 152' in source


def test_float_controls_keep_rounded_closed_outlines() -> None:
    source = FLOAT_AHK.read_text(encoding="utf-8")

    assert "this.TopPanelCtrl" in source
    assert "this.ResultBgCtrl := this.FloatGui.AddText(\"x18 y42 w420 h78 Border" in source
    assert "UiStyle.RoundControls([this.TopPanelCtrl, this.ResultBgCtrl], 7)" in source
    assert "UiStyle.RoundButtons([this.ClearBtn, this.CopyBtn, this.InsertBtn], 5)" in source


def test_float_result_mode_hides_wave_canvas() -> None:
    source = FLOAT_AHK.read_text(encoding="utf-8")

    assert "this.WaveCanvasCtrl.Visible := !visible" in source


def test_float_window_is_opaque_to_avoid_background_bleed() -> None:
    source = FLOAT_AHK.read_text(encoding="utf-8")

    assert "WinSetTransparent(255, this.FloatGui.Hwnd)" in source
