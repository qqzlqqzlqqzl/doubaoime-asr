# Upstream Diff Audit

Audit date: 2026-05-14

Current upstream references:

- `yangmoling/doubaoime-asr`: `267972f`
- `xiaohu31/doubao-voice-helper`: `12fb747`

This document explains every file-level behavioral diff from the two reference repositories. Generated runtime files such as `__pycache__`, `build`, `dist`, `release`, and local audit clones are not product source and are intentionally excluded.

Legend used below: `=` means intentionally identical to upstream, `M` means modified, and `A` means added by this repo. Line-ending-only differences are treated as `=` for behavior.

## Summary

The intended architecture is:

- Keep `yangmoling/doubaoime-asr` as the ASR protocol/API base.
- Keep `xiaohu31/doubao-voice-helper` as the AHK interaction/UI base.
- Add the smallest bridge needed so the AHK client calls the local Python ASR backend instead of driving the Doubao desktop app.

Three diffs did not explain cleanly and were fixed in this audit:

| Diff | Why it was a bug | Fix |
|---|---|---|
| AHK config still wrote to `%APPDATA%\DouBaoVoiceHelper` | Our product, installer, docs, credentials, and support path use `DoubaoASRHelper`; keeping the upstream app folder makes support and migration confusing | `ahk_client/src/config.ahk` now writes to `%APPDATA%\DoubaoASRHelper` and migrates old `DouBaoVoiceHelper\config.ini` if present |
| `DoubaoASR(config=None)` kept `self.config = None` | The public helper signatures allow `config=None`, but `AudioEncoder` then dereferences `None.sample_rate` | `doubaoime_asr/asr.py` now creates `ASRConfig()` when config is omitted |
| Source self-test required a manually prepared Opus DLL path | The repo already keeps Opus under `.devtools`, but direct `python -m doubaoime_asr.desktop_app --self-test` failed without global Opus installed | `doubaoime_asr/audio.py` now adds bundled/PyInstaller or local `.devtools\opus\bin` to the DLL search path before importing `opuslib` |

## Diff From `yangmoling/doubaoime-asr`

| File or group | Diff | Why |
|---|---|---|
| `.gitignore` | `M`: adds Windows build, release, credential, virtualenv, and generated-spec ignores | Required because this repo builds distributable Windows EXEs and stores local-only credentials/tools during testing |
| `.python-version`, `gen_proto.sh` | `=` | Toolchain pin/protobuf regeneration script can stay aligned with the ASR upstream |
| `doubaoime_asr/audio.py` | Adds local Opus runtime discovery before importing `opuslib`; PCM/Opus conversion behavior remains upstream-compatible | Required so source self-tests and development runs use the repo-local `.devtools\opus\bin` instead of depending on a global system install |
| `doubaoime_asr/asr.proto`, `asr_pb2.pyi` | No intentional behavior diff | These are protocol fundamentals; keeping them aligned reduces ASR risk |
| `doubaoime_asr/asr.py` | Adds websocket header compatibility helper, typed response structures, parsed `results/extra`, and the `config or ASRConfig()` fix | The local bridge and tests need stable structured interim/final metadata; websocket versions changed `additional_headers` vs `extra_headers`; `config=None` fix is a correctness repair |
| `doubaoime_asr/asr_pb2.py` | Generated protobuf version comment/runtime check differs | Generated code only; proto descriptor payload is unchanged, so protocol behavior is not intentionally changed |
| `doubaoime_asr/config.py` | Adds SAMI token handling, Wave session cache, JWT expiry helper | Required by added NER/Wave features; ASR credential path behavior remains compatible |
| `doubaoime_asr/constants.py` | Adds SAMI, handshake, NER constants | Required by added `sami.py`, `wave_client.py`, and `ner.py`; ASR constants are kept |
| `doubaoime_asr/device.py` | Adds `sami_token` and `wave_session` fields to cached credentials | Needed to persist added service tokens without another storage file; existing ASR credential fields remain compatible |
| `doubaoime_asr/__init__.py` | Exports typed ASR response models and NER API | Public API convenience for the added parsed-result and NER features |
| `doubaoime_asr/asr_bridge.py` | New local HTTP bridge for AHK | This is the central glue: AHK can start/stop/cancel/status ASR without embedding Python in AHK |
| `doubaoime_asr/transcript.py` | New interim/final transcript accumulator | Needed because real-time ASR sends revisions and segments; the bridge must avoid duplicating or truncating text |
| `doubaoime_asr/desktop_app.py`, `desktop_help.py` | Legacy Python desktop UI/help retained | Kept as test harness and fallback UI while the production client is AHK; default activation is disabled |
| `doubaoime_asr/activation.py`, `license-config.json`, `tools/license_*`, `tests/test_activation.py` | Activation-code support exists but defaults off | Retained for optional future distribution control. It does not block current no-login core flow because `require_activation=false` |
| `tests/conftest.py`, `tests/test_desktop_auto_insert.py` | Added pytest coverage for desktop and auto-insert behavior | Required because the bridge/client behavior is now part of product correctness, not present in the ASR-only upstream |
| `doubaoime_asr/ner.py`, `sami.py`, `wave_client.py` | Added non-ASR Doubao service helpers | These are not required for the AHK bridge, but explain the SAMI/Wave config additions and are isolated from the core ASR path |
| `doubaoime_asr/long_text_sample.py`, `test-long-text-asr.ps1` | Added long-text audio sample/test generator | Required by the requested 500+ character long-text, volume/pause ASR testing |
| `doubaoime_asr/assets/app.ico` | Added app icon | Required for desktop/tray/distribution polish |
| `examples/file_transcribe.py` | Final result prints segment timing when available | Demonstrates the added structured `results` field |
| `examples/mic_realtime.py` | `=` | Kept as upstream realtime microphone example; no reason to fork it |
| `examples/ner.py` | New NER example | Matches the added NER API |
| `pyproject.toml`, `uv.lock` | Version/dependency/script/package-data changes | Desktop bridge needs `sounddevice`, `pynput`, `sv-ttk`, `cryptography`, scripts, icon and license package data; lockfile follows dependencies |
| `.cargo/config.toml`, `enter-dev.ps1` | Added local dev environment helpers | Keeps Rust/native build caches and development activation isolated from the user's global environment |
| `README.md`, `TEST_PLAN.md`, `E2E_TEST_EVIDENCE.md`, `HANDOFF.md`, `REFERENCE_PARITY.md`, `WINDOWS_COMPATIBILITY.md`, `wave_protocol.md` | Product docs and test evidence added | Required for handoff, distribution, compatibility notes, and the user's requested closed-loop evidence |
| `build-desktop-exe.ps1`, `windows_installer.py`, `test-*.ps1` | Build, installer, smoke, compatibility, activation, and stress scripts added | Required to ship a Windows EXE/portable package and verify it on this machine |

Exact source inventory against `yangmoling/doubaoime-asr`:

| Status | Files |
|---|---|
| `=` | `.python-version`, `doubaoime_asr/asr.proto`, `examples/mic_realtime.py`, `gen_proto.sh` |
| `M` | `.gitignore`, `README.md`, `doubaoime_asr/__init__.py`, `doubaoime_asr/asr.py`, `doubaoime_asr/asr_pb2.py`, `doubaoime_asr/asr_pb2.pyi`, `doubaoime_asr/audio.py`, `doubaoime_asr/config.py`, `doubaoime_asr/constants.py`, `doubaoime_asr/device.py`, `examples/file_transcribe.py`, `pyproject.toml`, `uv.lock` |
| `A` | `.cargo/config.toml`, `E2E_TEST_EVIDENCE.md`, `HANDOFF.md`, `REFERENCE_PARITY.md`, `TEST_PLAN.md`, `WINDOWS_COMPATIBILITY.md`, `build-desktop-exe.ps1`, `doubaoime_asr/activation.py`, `doubaoime_asr/asr_bridge.py`, `doubaoime_asr/assets/app.ico`, `doubaoime_asr/desktop_app.py`, `doubaoime_asr/desktop_help.py`, `doubaoime_asr/license-config.json`, `doubaoime_asr/long_text_sample.py`, `doubaoime_asr/ner.py`, `doubaoime_asr/sami.py`, `doubaoime_asr/transcript.py`, `doubaoime_asr/wave_client.py`, `enter-dev.ps1`, `examples/ner.py`, `test-activation.ps1`, `test-desktop-exe.ps1`, `test-license-stress.ps1`, `test-long-text-asr.ps1`, `test-windows-compat.ps1`, `tests/conftest.py`, `tests/test_activation.py`, `tests/test_desktop_auto_insert.py`, `tools/license-codes.sample.json`, `tools/license_server.py`, `tools/license_stress_test.py`, `wave_protocol.md`, `windows_installer.py` |

## Diff From `xiaohu31/doubao-voice-helper`

| File or group | Diff | Why |
|---|---|---|
| `ahk_client/.gitignore` | Preserved from upstream | Keeps upstream AHK build output ignored inside the embedded client |
| `ahk_client/README.upstream.md` | Upstream README preserved under a renamed file | Keeps the reference UI/client documentation available without claiming it is the current product README |
| `ahk_client/assets/*`, `ahk_client/tools/compiler/Ahk2Exe.exe`, `ahk_client/tools/window-spy.ahk`, `window.ahk`, `doubao.ahk` | Intentionally kept aligned with upstream | Reuses proven UI assets, compiler, diagnostics, window helpers, and Doubao helper functions; `doubao.ahk` remains as compatibility utility even though bridge path does not use the Doubao desktop app |
| `ahk_client/src/bridge.ahk` | New local bridge client | Necessary glue from AHK hotkeys/UI to Python `asr_bridge.exe` |
| `ahk_client/src/float.ahk` | New local transcript float | Upstream relied on Doubao desktop floating UI; our backend has no Doubao window, so we need an equivalent non-focus-stealing float |
| `ahk_client/src/main.ahk` | Replaces Doubao hotkey/send-enter clipboard workflow with bridge `/start`, `/stop`, `/cancel`, `/status`; adds async finish polling | Required because we no longer depend on Doubao desktop UI. Async polling prevents UI freeze during ASR finalization |
| `ahk_client/src/config.ahk` | Product defaults, config versioning, migration, and app config directory changed | Defaults must avoid common shortcuts and mouse-only hardware; versioning migrates old defaults; app directory now matches `DoubaoASRHelper` |
| `ahk_client/src/hotkey.ahk` | Re-register now calls `UnregisterAll`; ampersand prefix dummy hotkeys are also disabled | Upstream assumed AHK replacement was enough; in practice old hotkeys can remain active after settings save, and prefix dummy keys can keep swallowing input |
| `ahk_client/src/gui.ahk` | Adds nicer display/roundtrip for `Space`, `Enter`, `Esc`, etc. | New keyboard-friendly defaults should display as user-facing keys, not uppercase internal tokens |
| `ahk_client/src/clipboard.ahk` | Adds `InsertText(text, protect)` | Upstream waits for Doubao to write recognition text into clipboard. Our bridge receives text over HTTP, so AHK must insert it directly while preserving clipboard |

Exact source inventory against `xiaohu31/doubao-voice-helper`:

| Status | Files |
|---|---|
| `=` | `README.md -> ahk_client/README.upstream.md`, `assets/demo.gif`, `assets/icon-disabled.ico`, `assets/icon.ico`, `src/doubao.ahk`, `src/window.ahk`, `tools/compiler/Ahk2Exe.exe`, `tools/window-spy.ahk` |
| `M` | `.gitignore -> ahk_client/.gitignore` line ending only, `src/clipboard.ahk`, `src/config.ahk`, `src/gui.ahk`, `src/hotkey.ahk`, `src/main.ahk` |
| `A` | `ahk_client/src/bridge.ahk`, `ahk_client/src/float.ahk` |

## Current Review Decisions

| Item | Decision |
|---|---|
| Replace Doubao desktop automation with local ASR bridge | Explained and required |
| Keep upstream AHK UI shape and tray behavior | Explained and required by user request |
| Keep dormant Python activation framework | Explained as optional distribution-control work; default disabled, not part of core AHK flow |
| Keep `doubao.ahk` even though bridge path avoids Doubao desktop | Explained as low-risk upstream compatibility; removing it would make future upstream sync harder |
| Change default hotkeys away from upstream mouse/Win combos | Explained: many users lack mouse side keys; Windows voice typing uses `Win+H`; AltGr/Win-prefix combos can swallow input |

## Verification Run For This Audit

- `python -m compileall doubaoime_asr\asr.py doubaoime_asr\desktop_app.py doubaoime_asr\desktop_help.py doubaoime_asr\asr_bridge.py`
- `python -m pytest -q`: `16 passed, 1 warning`
- `python -m doubaoime_asr.desktop_app --self-test --self-test-report release\test-reports\e2e-source-self-test.json`: passed; report shows `ok: true`
- `build-desktop-exe.ps1`: rebuilt `dist\DoubaoASRHelper.exe`, `dist\asr_bridge.exe`, installer, and release zips
- `test-desktop-exe.ps1`: passed; includes isolated AHK legacy config migration and old-default hotkey migration
- `git diff --check`: passed with CRLF normalization warnings only
