import os
import sys
import tempfile

def test_imports():
    print("=" * 60)
    print("THAFREEG SUITE - BACKEND CORE MODULE & REFACTOR TEST")
    print("=" * 60)
    
    print("\n[1/7] Testing Module Imports...")
    try:
        import core
        from core.config_manager import load_config, save_config
        from core.utils import (
            format_duration, clean_vtt, generate_subtitles, build_ffmpeg_cmd,
            get_media_duration_sec, run_exporters, log_task, update_task_key_status,
            update_task_analytics, Task, TaskStatus
        )
        print("  [OK] core.utils and core.config_manager imported successfully.")
    except Exception as e:
        print(f"  [FAIL] Failed to import core.utils / config_manager: {e}")
        return False

    try:
        from core.whisper_engine import transcribe_with_api, run_local_pipeline
        print("  [OK] core.whisper_engine imported successfully.")
    except Exception as e:
        print(f"  [FAIL] Failed to import core.whisper_engine: {e}")
        return False

    try:
        from core.vision_engine import process_vision_api, run_vision_pipeline
        print("  [OK] core.vision_engine imported successfully.")
    except Exception as e:
        print(f"  [FAIL] Failed to import core.vision_engine: {e}")
        return False

    try:
        from core.yt_engine import fetch_yt_playlist_info, run_youtube_pipeline
        print("  [OK] core.yt_engine imported successfully.")
    except Exception as e:
        print(f"  [FAIL] Failed to import core.yt_engine: {e}")
        return False

    try:
        from core.telegram_engine import run_telegram_pipeline, process_telegram_async
        print("  [OK] core.telegram_engine imported successfully.")
    except Exception as e:
        print(f"  [FAIL] Failed to import core.telegram_engine: {e}")
        return False

    print("\n[2/7] Testing Centralized Config Manager (config.json)...")
    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.json', encoding='utf-8') as f:
        f.write("{}")
        temp_cfg_path = f.name
    try:
        cfg = load_config(temp_cfg_path)
        assert isinstance(cfg, dict), "load_config didn't return a dict"
        assert "ocr_lang" in cfg and cfg["ocr_lang"] == "Arabic", "Default config missing key"
        
        save_success = save_config({"yt_vocab": "test_vocab_value"}, temp_cfg_path)
        assert save_success, "save_config returned False"
        
        updated_cfg = load_config(temp_cfg_path)
        assert updated_cfg["yt_vocab"] == "test_vocab_value", "Config save verification failed"
        print(f"  [OK] Central config load & save verified: yt_vocab='{updated_cfg['yt_vocab']}'")
    finally:
        if os.path.exists(temp_cfg_path):
            os.remove(temp_cfg_path)

    print("\n[3/7] Testing Duration Formatting Utilities...")
    assert format_duration(3660) == "(1h 01m)", f"Expected (1h 01m), got {format_duration(3660)}"
    assert format_duration(300) == "(5m)", f"Expected (5m), got {format_duration(300)}"
    print(f"  [OK] format_duration(3660) = {format_duration(3660)}")
    print(f"  [OK] format_duration(300)  = {format_duration(300)}")

    print("\n[4/7] Testing FFmpeg Command Builder...")
    cmd = build_ffmpeg_cmd("test_audio.mp3", {"noise_reduction": True})
    assert "-af" in cmd and "afftdn" in cmd, "Noise reduction filter missing from ffmpeg cmd"
    print(f"  [OK] FFmpeg Noise Filter Command: {' '.join(cmd)}")

    print("\n[5/7] Testing VTT Subtitle Cleaning...")
    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.vtt', encoding='utf-8') as f:
        f.write("WEBVTT\nKind: captions\nLanguage: ar\n\n00:00:01.000 --> 00:00:04.000\n<c>مرحبا</c> بكم\n\n00:00:04.000 --> 00:00:08.000\n<c>مرحبا</c> بكم\n")
        temp_vtt = f.name
    try:
        cleaned = clean_vtt(temp_vtt)
        assert "مرحبا بكم" in cleaned, "Clean VTT content error"
        print(f"  [OK] Clean VTT Result: '{cleaned}'")
    finally:
        if os.path.exists(temp_vtt):
            os.remove(temp_vtt)

    print("\n[6/7] Testing Subtitle Generation Logic...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        segments = [
            {"start": 0.0, "end": 2.5, "text": "Hello world"},
            {"start": 2.5, "end": 5.0, "text": "Testing subtitles"}
        ]
        generate_subtitles(segments, "sample_audio.mp3", tmp_dir, chunk_index=0)
        srt_file = os.path.join(tmp_dir, "sample_audio.srt")
        vtt_file = os.path.join(tmp_dir, "sample_audio.vtt")
        assert os.path.exists(srt_file), "SRT file was not created"
        assert os.path.exists(vtt_file), "VTT file was not created"
        print("  [OK] SRT and VTT files generated successfully.")

    print("\n[7/7] Testing Pure-Python Task Object & Unified Logging...")
    logged_messages = []
    status_updates = []
    
    def mock_log(msg):
        logged_messages.append(msg)

    def mock_status(t):
        status_updates.append(t.status)

    task_data = {"api_keys": ["gsk_dummy_key"], "entries": []}
    task = Task("1001", "LOCAL", "Test Task", task_data, log_callback=mock_log, status_callback=mock_status)
    
    # Verify no UI object fields
    assert not hasattr(task, 'app'), "Task should not hold app reference"
    assert not hasattr(task, 'card_ui'), "Task should not hold card_ui widget reference"
    
    log_task(task, "Test log message")
    assert len(logged_messages) == 1 and logged_messages[0] == "Test log message", "Unified logging failed"
    
    task.update_progress(0.75)
    assert task.progress_fraction == 0.75, "Progress fraction mismatch"
    assert len(status_updates) > 0, "Status update callback failed"
    
    print(f"  [OK] Pure-Python Task '{task.name}' status: {task.status}, Progress: {task.progress_fraction * 100}%")
    print(f"  [OK] Unified log captured: '{logged_messages[0]}'")

    print("\n" + "=" * 60)
    print("ALL 7 CORE BACKEND & REFACTOR TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
