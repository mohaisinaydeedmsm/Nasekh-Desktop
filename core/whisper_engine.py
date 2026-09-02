import os
import glob
import time
import subprocess
import requests

from core.config_manager import load_config
from core.utils import (
    generate_subtitles, get_media_duration_sec, build_ffmpeg_cmd, run_exporters,
    log_task, update_task_key_status, update_task_analytics
)

def transcribe_with_api(audio_path, task, chunk_idx=0, output_dir=".", master_file="Thafreeg"):
    config = task.data.get("config") or load_config()
    audio_engine = config.get("audio_engine", {})

    base_url = audio_engine.get("base_url", "https://api.groq.com/openai/v1").rstrip("/")
    audio_model = audio_engine.get("model", "whisper-large-v3")
    engine_key = audio_engine.get("api_key", "").strip()

    api_keys = task.data.get("api_keys", [])
    if not api_keys and engine_key:
        api_keys = [engine_key]

    is_local = any(host in base_url.lower() for host in ["localhost", "127.0.0.1", "0.0.0.0"])
    if is_local and not api_keys:
        api_keys = ["local"]

    if not api_keys:
        api_keys = [""]

    key_state = task.data.get("key_state", {"index": 0})
    dyn_vocab = task.data.get("vocab", "")

    url = f"{base_url}/audio/transcriptions"
    consecutive_429s = 0

    while True:
        task.check_state()
        current_key = api_keys[key_state["index"] % len(api_keys)]
        headers = {}
        if current_key and current_key != "local":
            headers["Authorization"] = f"Bearer {current_key}"
        elif is_local:
            headers["Authorization"] = "Bearer local"

        try:
            with open(audio_path, 'rb') as f:
                files = {'file': (os.path.basename(audio_path), f)}
                data = {'model': audio_model, 'prompt': dyn_vocab, 'response_format': 'verbose_json'}

                key_desc = "Local Endpoint" if is_local else f"Key #{key_state['index'] + 1}"
                log_task(task, f"    -> Transcribing {os.path.basename(audio_path)} via API ({key_desc})...")
                update_task_key_status(task, f"Active ({key_desc})", "green")

                response = requests.post(url, headers=headers, files=files, data=data, timeout=300)

                if response.status_code == 200:
                    try:
                        res_json = response.json()
                        generate_subtitles(res_json.get('segments', []), master_file, output_dir, chunk_idx)
                        return res_json.get('text', '').strip()
                    except Exception:
                        return response.text.strip()
                elif response.status_code == 429:
                    if is_local:
                        time.sleep(5)
                        continue
                    consecutive_429s += 1
                    update_task_key_status(task, "Rate Limit 429 (Cooldown)", "yellow")
                    if len(api_keys) > 1 and consecutive_429s < len(api_keys):
                        key_state["index"] = (key_state["index"] + 1) % len(api_keys)
                        log_task(task, f"    [WAIT] Rate limit. Switching to Key #{key_state['index'] + 1}...")
                        continue
                    else:
                        log_task(task, "    [WAIT] All keys exhausted! Sleeping for 10 minutes...")
                        for _ in range(600):
                            task.check_state()
                            time.sleep(1)
                        consecutive_429s = 0
                        continue
                elif response.status_code == 401:
                    if is_local:
                        update_task_key_status(task, "Local Endpoint Auth Error", "red")
                        raise Exception("Local server returned 401 Unauthorized.")
                    if len(api_keys) > 1:
                        key_state["index"] = (key_state["index"] + 1) % len(api_keys)
                        continue
                    else:
                        update_task_key_status(task, "Invalid Key Error", "red")
                        raise Exception("Fatal API Error: Your API key is invalid.")
                else:
                    update_task_key_status(task, f"Error {response.status_code}", "red")
                    return ""
        except Exception as e:
            if "Cancelled" in str(e):
                raise e
            log_task(task, f"    [WAIT] Network error ({e}). Retrying in 60s...")
            update_task_key_status(task, "Network Retry", "yellow")
            time.sleep(60)

def run_local_pipeline(task):
    file_paths = task.data['entries']
    full_output_path = task.data['output_path']
    append_mode = task.data['append']
    config = task.data['config']

    total_files = len(file_paths)
    mode = 'a' if append_mode else 'w'
    task.data["key_state"] = {"index": 0}
    out_dir = os.path.dirname(full_output_path)

    try:
        with open(full_output_path, mode, encoding='utf-8') as master:
            for index, filepath in enumerate(file_paths, start=1):
                task.check_state()
                filename = os.path.basename(filepath)
                log_task(task, f"[{index}/{total_files}] Processing: {filename}")
                master.write(f"\n\n--- {filename} ---\n\n")

                duration_sec = get_media_duration_sec(filepath)
                base_progress = (index - 1) / total_files
                subprocess.run(build_ffmpeg_cmd(filepath, config), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000 if os.name == 'nt' else 0)
                task.update_progress(base_progress + (0.10 / total_files))

                chunks = sorted(glob.glob("chunk_*.mp3"))
                full_transcription = []
                for c_idx, chunk in enumerate(chunks):
                    task.check_state()
                    text = transcribe_with_api(chunk, task, c_idx, out_dir, full_output_path)
                    if text:
                        full_transcription.append(text)
                    os.remove(chunk)
                    chunk_prog = ((c_idx + 1) / len(chunks)) * 0.90
                    task.update_progress(base_progress + ((0.10 + chunk_prog) / total_files))

                res_text = " ".join(full_transcription)
                master.write(res_text + "\n")
                words = len(res_text.split())
                update_task_analytics(task, local_count=1, local_sec=duration_sec, words=words)
                task.update_progress(index / total_files)

        log_task(task, "\n[SUCCESS] Local processing complete!")
        run_exporters(full_output_path, config.get('export_docx', False), config.get('export_md', False), lambda msg: log_task(task, msg))
    except Exception as e:
        if "Cancelled" in str(e):
            raise e
        raise e
