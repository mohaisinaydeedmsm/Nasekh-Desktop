import os
import re
import time
import base64
import requests

from core.config_manager import load_config
from core.utils import run_exporters, log_task, update_task_key_status, update_task_analytics

def process_vision_api(image_path, task):
    config = task.data.get("config") or load_config()
    vision_engine = config.get("vision_engine", {})

    base_url = vision_engine.get("base_url", "https://api.groq.com/openai/v1").rstrip("/")
    vision_model = vision_engine.get("model", "qwen/qwen3.6-27b")
    engine_key = vision_engine.get("api_key", "").strip()

    api_keys = task.data.get("api_keys", [])
    if not api_keys and engine_key:
        api_keys = [engine_key]

    is_local = any(host in base_url.lower() for host in ["localhost", "127.0.0.1", "0.0.0.0"])
    if is_local and not api_keys:
        api_keys = ["local"]

    if not api_keys:
        api_keys = [""]

    key_state = task.data.get("key_state", {"index": 0})

    selected_lang = task.data.get("ocr_lang") or config.get("target_language") or config.get("ocr_lang", "Arabic")
    selected_dir = task.data.get("ocr_dir") or config.get("ocr_dir", "RTL")
    user_custom_prompt = task.data.get("vocab", "")
    direction_text = "Right-to-Left (RTL) reading flow." if selected_dir == "RTL" else "Left-to-Right (LTR) reading flow."
    final_vision_prompt = f"{direction_text} Target language: {selected_lang}. {user_custom_prompt}".strip()

    url = f"{base_url}/chat/completions"
    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception:
        return ""

    consecutive_429s = 0
    while True:
        task.check_state()
        current_key = api_keys[key_state["index"] % len(api_keys)]
        headers = {"Content-Type": "application/json"}
        if current_key and current_key != "local":
            headers["Authorization"] = f"Bearer {current_key}"
        elif is_local:
            headers["Authorization"] = "Bearer local"

        payload = {
            "model": vision_model,
            "messages": [
                {"role": "system", "content": "You are a strict, automated OCR extraction engine specialized in Classical and Modern Arabic manuscripts. Output raw, literal text only with zero conversational filler."},
                {"role": "user", "content": [{"type": "text", "text": final_vision_prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}
            ]
        }

        key_desc = "Local Endpoint" if is_local else f"Key #{key_state['index'] + 1}"
        log_task(task, f"    -> Scanning {os.path.basename(image_path)} via Vision API ({key_desc})...")
        update_task_key_status(task, f"Scanning ({key_desc})", "green")

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            if response.status_code == 200:
                raw_content = response.json()['choices'][0]['message']['content'].strip()
                return re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()
            elif response.status_code == 429:
                if is_local:
                    time.sleep(5)
                    continue
                consecutive_429s += 1
                update_task_key_status(task, "Rate Limit 429 (Cooldown)", "yellow")
                if len(api_keys) > 1 and consecutive_429s < len(api_keys):
                    key_state["index"] = (key_state["index"] + 1) % len(api_keys)
                    continue
                else:
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
            time.sleep(30)

def run_vision_pipeline(task):
    file_paths = task.data['entries']
    full_output_path = task.data['output_path']
    append_mode = task.data['append']
    config = task.data['config']

    total_files = len(file_paths)
    mode = 'a' if append_mode else 'w'
    task.data["key_state"] = {"index": 0}

    try:
        with open(full_output_path, mode, encoding='utf-8') as master:
            for index, filepath in enumerate(file_paths, start=1):
                task.check_state()
                filename = os.path.basename(filepath)
                ext = os.path.splitext(filename)[1].lower()
                master.write(f"\n\n--- {filename} ---\n\n")

                base_progress = (index - 1) / total_files

                if ext == '.pdf':
                    try:
                        import fitz
                        doc = fitz.open(filepath)
                        total_pages = len(doc)
                        for page_num in range(total_pages):
                            task.check_state()
                            page = doc.load_page(page_num)
                            pix = page.get_pixmap(dpi=120)
                            temp_img = f"temp_file_{index}_page_{page_num}.jpg"
                            pix.save(temp_img)

                            text = process_vision_api(temp_img, task)
                            if text:
                                master.write(f"--- Page {page_num + 1} ---\n{text}\n\n")
                                words = len(text.split())
                                update_task_analytics(task, ocr_pages=1, words=words)
                            if os.path.exists(temp_img):
                                os.remove(temp_img)

                            task.update_progress(base_progress + (((page_num + 1) / total_pages) / total_files))
                    except Exception as e:
                        log_task(task, f"    [!] PDF Error: {e}")
                else:
                    text = process_vision_api(filepath, task)
                    if text:
                        master.write(text + "\n")
                        words = len(text.split())
                        update_task_analytics(task, ocr_pages=1, words=words)
                    task.update_progress(index / total_files)

        run_exporters(full_output_path, config.get('export_docx', False), config.get('export_md', False), lambda msg: log_task(task, msg))
    except Exception as e:
        if "Cancelled" in str(e):
            raise e
        raise e
