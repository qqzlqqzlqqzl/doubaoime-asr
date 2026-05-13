from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import tempfile
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import miniaudio
import numpy as np

from doubaoime_asr import ASRConfig, ResponseType, transcribe_realtime, transcribe_stream
from doubaoime_asr.transcript import TranscriptAccumulator


SAMPLE_RATE = 16000
LONG_TEXT_SEGMENTS = [
    "今天的长文本测试从清晨的城市开始，路边早餐摊刚刚支起炉火，公交车在潮湿的路面上缓慢转弯，行人一边看手机，一边躲开施工围挡。",
    "第一段声音保持正常音量，然后突然放轻，好像说话的人退后了两步；几秒钟之后又靠近麦克风，语速略快，但每个词仍然清楚。",
    "会议室里有人打开投影，屏幕闪了一下，项目经理提醒大家记录关键数字：三十六台设备、十二个网关、七组备用电池，都要在下午复核。",
    "接着测试会故意停顿，像真实口述那样断断续续：先说库存表，再停一下；再说客户地址，又停一下；最后补充一句，所有信息都要核对两遍。",
    "中间部分音量降低，背景仿佛有空调和键盘声。说话人描述仓库、地铁、雨伞、纸箱、扫码枪和临时通行证，用来观察识别结果是否会漏掉短词。",
    "随后音量抬高，语气更像紧急通知：如果系统发现重复订单，请不要直接删除，要先保存日志、截图、时间戳和处理人姓名。",
    "为了模拟长句输入，下面连续说一串自然语言：我希望这个助手能在写邮件、整理会议纪要、填写工单、记录电话回访和总结测试结果时保持稳定。",
    "补充一段低声说明：如果长时间停顿之后继续说话，程序仍然应该把前后内容合并成完整记录，而不是只保留最后几个词，并且要保留上下文顺序完整。",
    "最后一段再次变轻，并加入较长空白。测试结束前，还要确认标点、停顿、数字和专有名词是否合理，例如豆包语音输入助手、离线帮助文档和安装器。",
]

VOLUME_PATTERN = [0.95, 0.52, 1.12, 0.70, 0.38, 1.15, 0.82, 0.46, 0.58]
SILENCE_PATTERN = [0.35, 0.90, 0.25, 1.15, 0.55, 0.80, 1.20, 0.75, 0.50]
KEYWORDS = ["清晨", "会议室", "备用电池", "库存表", "仓库", "重复订单", "会议纪要", "长时间停顿", "安装器"]


@dataclass
class SampleInfo:
    audio_path: str
    text_path: str
    manifest_path: str
    duration_seconds: float
    text_chars: int
    cjk_chars: int
    segments: int
    volume_pattern: list[float]
    silence_pattern: list[float]


def sample_text() -> str:
    return "".join(LONG_TEXT_SEGMENTS)


def cjk_char_count(text: str) -> int:
    return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")


def _write_sapi_chunks(chunk_dir: Path, voice: str | None = None) -> list[Path]:
    manifest = chunk_dir / "chunks.json"
    items = [{"index": index, "text": text} for index, text in enumerate(LONG_TEXT_SEGMENTS)]
    manifest.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    script = chunk_dir / "speak.ps1"
    script.write_text(
        r'''
param(
  [Parameter(Mandatory = $true)][string]$Manifest,
  [Parameter(Mandatory = $true)][string]$OutputDir,
  [string]$VoiceName = ""
)

Add-Type -AssemblyName System.Speech
$Synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($VoiceName -ne "") {
  $Synth.SelectVoice($VoiceName)
} else {
  $Voice = $Synth.GetInstalledVoices() |
    Where-Object { $_.VoiceInfo.Culture.Name -like "zh-*" } |
    Select-Object -First 1
  if ($Voice -ne $null) {
    $Synth.SelectVoice($Voice.VoiceInfo.Name)
  }
}
$Synth.Rate = 3
$Synth.Volume = 100
$Items = Get-Content -Raw -Encoding UTF8 $Manifest | ConvertFrom-Json
foreach ($Item in $Items) {
  $Out = Join-Path $OutputDir ("chunk-{0:D2}.wav" -f [int]$Item.index)
  $Synth.SetOutputToWaveFile($Out)
  $Synth.Speak([string]$Item.text)
  $Synth.SetOutputToNull()
}
'''.lstrip(),
        encoding="utf-8",
    )

    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Manifest",
        str(manifest),
        "-OutputDir",
        str(chunk_dir),
    ]
    if voice:
        command.extend(["-VoiceName", voice])
    subprocess.run(command, check=True)

    chunks = [chunk_dir / f"chunk-{index:02d}.wav" for index in range(len(LONG_TEXT_SEGMENTS))]
    missing = [path for path in chunks if not path.exists()]
    if missing:
        raise FileNotFoundError(f"SAPI did not produce chunk(s): {missing}")
    return chunks


def _decode_chunk(path: Path) -> np.ndarray:
    decoded = miniaudio.decode_file(
        str(path),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=SAMPLE_RATE,
    )
    return np.frombuffer(decoded.samples.tobytes(), dtype=np.int16).astype(np.float32)


def _shape_volume(samples: np.ndarray, gain: float) -> np.ndarray:
    if samples.size == 0:
        return samples.astype(np.int16)
    ramp_len = min(samples.size // 8, SAMPLE_RATE // 10)
    envelope = np.ones(samples.size, dtype=np.float32)
    if ramp_len > 0:
        ramp = np.linspace(0.15, 1.0, ramp_len, dtype=np.float32)
        envelope[:ramp_len] = ramp
        envelope[-ramp_len:] = ramp[::-1]
    shaped = np.clip(samples * envelope * gain, -32768, 32767)
    return shaped.astype(np.int16)


def generate_long_text_sample(output: str | Path, voice: str | None = None) -> SampleInfo:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text_path = output_path.with_suffix(".txt")
    manifest_path = output_path.with_suffix(".manifest.json")

    with tempfile.TemporaryDirectory(prefix="doubao-long-text-") as tmp:
        tmp_dir = Path(tmp)
        chunks = _write_sapi_chunks(tmp_dir, voice=voice)
        pieces: list[np.ndarray] = []
        for index, chunk in enumerate(chunks):
            samples = _decode_chunk(chunk)
            pieces.append(_shape_volume(samples, VOLUME_PATTERN[index]))
            silence = np.zeros(int(SAMPLE_RATE * SILENCE_PATTERN[index]), dtype=np.int16)
            pieces.append(silence)

        combined = np.concatenate(pieces) if pieces else np.array([], dtype=np.int16)

    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(combined.tobytes())

    text = sample_text()
    text_path.write_text(text, encoding="utf-8")
    info = SampleInfo(
        audio_path=str(output_path),
        text_path=str(text_path),
        manifest_path=str(manifest_path),
        duration_seconds=round(combined.size / SAMPLE_RATE, 3),
        text_chars=len(text),
        cjk_chars=cjk_char_count(text),
        segments=len(LONG_TEXT_SEGMENTS),
        volume_pattern=VOLUME_PATTERN,
        silence_pattern=SILENCE_PATTERN,
    )
    manifest_path.write_text(json.dumps(asdict(info), ensure_ascii=False, indent=2), encoding="utf-8")
    return info


async def _pcm_chunks_from_wav(audio_path: Path, sample_rate: int, frame_duration_ms: int):
    samples_per_frame = sample_rate * frame_duration_ms // 1000
    bytes_per_frame = samples_per_frame * 2
    with wave.open(str(audio_path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != sample_rate:
            raise ValueError(
                f"Expected 16 kHz mono int16 WAV, got channels={wav.getnchannels()}, "
                f"width={wav.getsampwidth()}, rate={wav.getframerate()}"
            )
        while True:
            chunk = wav.readframes(samples_per_frame)
            if not chunk:
                break
            if len(chunk) < bytes_per_frame:
                chunk += b"\x00" * (bytes_per_frame - len(chunk))
            yield chunk
            await asyncio.sleep(0)


async def run_asr(
    audio_path: Path,
    credential_path: Path,
    min_chars: int,
    min_keywords: int,
    mode: str = "realtime",
) -> dict:
    config = ASRConfig(credential_path=str(credential_path))
    finals: list[str] = []
    transcript = TranscriptAccumulator()
    events: list[dict] = []

    try:
        if mode == "file":
            responses = transcribe_stream(audio_path, config=config, realtime=False)
        else:
            responses = transcribe_realtime(
                _pcm_chunks_from_wav(audio_path, config.sample_rate, config.frame_duration_ms),
                config=config,
            )

        async for response in responses:
            events.append(
                {
                    "type": response.type.name,
                    "text": response.text,
                    "error_msg": response.error_msg,
                    "packet_number": response.packet_number,
                }
            )
            if response.type == ResponseType.FINAL_RESULT and response.text:
                finals.append(response.text)
            if response.type in {ResponseType.INTERIM_RESULT, ResponseType.FINAL_RESULT} and response.text:
                transcript.update(response.text, is_final=response.type == ResponseType.FINAL_RESULT)
            if response.type == ResponseType.ERROR:
                break
    except Exception as exc:
        events.append({"type": "EXCEPTION", "text": "", "error_msg": repr(exc), "packet_number": -1})

    recognized_text = transcript.text or "".join(finals)
    matched_keywords = [keyword for keyword in KEYWORDS if keyword in recognized_text]
    errors = [event for event in events if event["type"] in {"ERROR", "EXCEPTION"}]
    passed = not errors and len(recognized_text) >= min_chars and len(matched_keywords) >= min_keywords
    return {
        "passed": passed,
        "mode": mode,
        "recognized_text": recognized_text,
        "recognized_chars": len(recognized_text),
        "final_segments": finals,
        "matched_keywords": matched_keywords,
        "required_min_chars": min_chars,
        "required_min_keywords": min_keywords,
        "errors": errors,
        "events": events,
    }


def default_output_path() -> Path:
    return Path(".devtools") / "samples" / "long-text-volume-stress.wav"


def default_credential_path() -> Path:
    local = Path("credentials.json")
    if local.exists():
        return local
    appdata = Path.home() / "AppData/Roaming/DoubaoASRHelper/credentials.json"
    return appdata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and optionally transcribe a long Chinese stress-test sample.")
    parser.add_argument("--output", type=Path, default=default_output_path())
    parser.add_argument("--voice", help="Windows SAPI voice name. Defaults to the first zh-* voice.")
    parser.add_argument("--run-asr", action="store_true", help="Run Doubao ASR against the generated sample.")
    parser.add_argument("--mode", choices=["realtime", "file"], default="realtime")
    parser.add_argument("--credential-path", type=Path, default=default_credential_path())
    parser.add_argument("--report", type=Path, default=Path("release/test-reports/long-text-asr.json"))
    parser.add_argument("--min-recognized-chars", type=int, default=220)
    parser.add_argument("--min-keywords", type=int, default=3)
    args = parser.parse_args(argv)

    if shutil.which("powershell") is None:
        raise RuntimeError("Windows PowerShell is required to generate the SAPI voice sample.")

    info = generate_long_text_sample(args.output, voice=args.voice)
    report = {"sample": asdict(info), "source_text": sample_text()}

    if args.run_asr:
        report["asr"] = asyncio.run(
            run_asr(args.output, args.credential_path, args.min_recognized_chars, args.min_keywords, mode=args.mode)
        )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.run_asr and not report["asr"]["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
