import os
import json

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "api_keys": [],
    "audio_engine": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "whisper-large-v3",
        "api_key": ""
    },
    "vision_engine": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "qwen/qwen3.6-27b",
        "api_key": ""
    },
    "tg_api_id": "",
    "tg_api_hash": "",
    "tg_phone": "",
    "output_dir": os.getcwd(),
    "output_file": "Thafreeg_Transcription.txt",
    "yt_vocab": "",
    "local_vocab": "",
    "tg_vocab": "",
    "custom_vision_prompt": "",
    "target_language": "Arabic",
    "ocr_lang": "Arabic",
    "ocr_dir": "RTL",
    "noise_reduction": False,
    "export_docx": False,
    "export_md": False,
    "theme": "Auto",
    "dark_mode": False,
    "stats_yt_count": 0,
    "stats_yt_sec": 0,
    "stats_local_count": 0,
    "stats_local_sec": 0,
    "stats_tg_count": 0,
    "stats_tg_sec": 0,
    "stats_ocr_pages": 0,
    "stats_total_words": 0
}

def load_config(filepath=CONFIG_FILE):
    """Loads configuration from JSON file, populating defaults for missing keys."""
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict) and k in config and isinstance(config[k], dict):
                            config[k].update(v)
                        else:
                            config[k] = v
        except Exception as e:
            print(f"[!] Warning: Failed to read {filepath}: {e}")
    return config

def save_config(config_data, filepath=CONFIG_FILE):
    """Saves configuration dictionary to JSON file."""
    try:
        existing = load_config(filepath)
        existing.update(config_data)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=4)
        return True
    except Exception as e:
        print(f"[!] Error: Failed to save config to {filepath}: {e}")
        return False

