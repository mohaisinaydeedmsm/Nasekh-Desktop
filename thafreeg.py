import os
import sys
import json
import time
import threading
import subprocess
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES
from PIL import Image, ImageDraw
import pystray

from core import (
    load_config,
    save_config,
    resource_path,
    get_cookie_opts,
    get_media_duration_sec,
    format_duration,
    run_exporters,
    clean_vtt,
    generate_subtitles,
    build_ffmpeg_cmd,
    TaskStatus,
    Task,
    transcribe_with_api,
    run_local_pipeline,
    process_vision_api,
    run_vision_pipeline,
    fetch_yt_playlist_info,
    run_youtube_pipeline,
    run_telegram_pipeline,
    process_telegram_async
)

# =========================================================
# HELPER: WINDOWS TASKBAR PROGRESS (CTYPES COM INTERFACE)
# =========================================================
class WindowsTaskbarProgress:
    TBPF_NOPROGRESS    = 0x00
    TBPF_INDETERMINATE = 0x01
    TBPF_NORMAL        = 0x02
    TBPF_ERROR         = 0x04
    TBPF_PAUSED        = 0x08

    def __init__(self, hwnd=None):
        self.hwnd = hwnd
        self.taskbar = None
        if os.name == 'nt':
            try:
                import ctypes
                import comtypes.client
                CLSID_TaskbarList = comtypes.GUID("{56FDF344-FD6D-11d0-958A-006097C9A090}")
                IID_ITaskbarList3 = comtypes.GUID("{EA1E3220-7080-4E2E-A69A-E27299386378}")
                class ITaskbarList3(ctypes.c_void_p): pass
                self.taskbar = comtypes.client.CreateObject(CLSID_TaskbarList, interface=ITaskbarList3)
            except Exception:
                self.taskbar = None

    def set_progress(self, hwnd, completed, total):
        if self.taskbar and hwnd:
            try:
                self.taskbar.SetProgressValue(int(hwnd), int(completed), int(total))
                self.taskbar.SetProgressState(int(hwnd), self.TBPF_NORMAL)
            except Exception: pass

    def set_state(self, hwnd, state_flag):
        if self.taskbar and hwnd:
            try: self.taskbar.SetProgressState(int(hwnd), state_flag)
            except Exception: pass

# =========================================================
# GLOBALS & CONSTANTS
# =========================================================
ctk.set_default_color_theme("green")
CONFIG_FILE = "config.json"
QUEUE_FILE = "queue.json"

LANGUAGES = {
    "Afrikaans": "af", "Albanian": "sq", "Amharic": "am", "Arabic": "ar", "English": "en",
    "French": "fr", "German": "de", "Hindi": "hi", "Indonesian": "id", "Italian": "it",
    "Japanese": "ja", "Korean": "ko", "Malayalam": "ml", "Portuguese": "pt", "Russian": "ru",
    "Spanish": "es", "Turkish": "tr", "Urdu": "ur"
}

# =========================================================
# MODERN UI & MAIN APP 
# =========================================================
class ThafreegApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        self.root = self
        self.title("Thafreeg Suite")
        self.geometry("1250x850")
        self.minsize(1250, 850)
        self.protocol("WM_DELETE_WINDOW", self.hide_window)
        
        self.taskbar = WindowsTaskbarProgress()
        try: self.iconbitmap(resource_path("icon.ico"))
        except Exception: pass

        # Global Config State
        self.api_keys, self.tg_api_id, self.tg_api_hash = [], "", ""
        self.output_dir, self.output_file = os.getcwd(), "Thafreeg_Transcription.txt"
        self.yt_vocab, self.local_vocab, self.tg_vocab, self.ocr_vocab = "", "", "", ""
        self.ocr_lang, self.ocr_dir = "Arabic", "RTL"
        self.noise_reduction, self.export_docx, self.export_md = False, False, False
        self.dark_mode = True
        
        # Granular Analytics Tracking
        self.stats_yt_count = 0
        self.stats_yt_sec = 0
        self.stats_local_count = 0
        self.stats_local_sec = 0
        self.stats_tg_count = 0
        self.stats_tg_sec = 0
        self.stats_ocr_pages = 0
        self.stats_total_words = 0

        # Current Input State
        self.local_files, self.vision_files = [], []

        # Global Job Queue (Threaded)
        self.global_queue = []
        self.is_queue_running = False
        self.active_task = None
        self.right_sidebar_visible = True

        self.load_config()
        ctk.set_appearance_mode("dark" if self.dark_mode else "light")

        # Color Palette
        self.bg_workspace = ("#F8FAFD", "#131314")
        self.bg_card = ("#FFFFFF", "#1e1f22")
        self.bg_card_hover = ("#EAEEEF", "#2b2c2f")
        self.nav_active_bg = ("#C2E7FF", "#004a77")
        self.nav_active_fg = ("#001D35", "#c2e7ff")
        self.nav_inactive_fg = ("#444746", "#e3e3e3")
        self.text_primary = ("#1F1F1F", "#e3e3e3")
        self.border_color = ("#D0D7DE", "#333333")
        self.accent_green = "#34a853"
        self.log_bg = ("#F0F4F9", "#141517")
        self.log_text_color = ("#006400", "#00ff00")
        
        self.configure(fg_color=self.bg_workspace)
        self.build_ui()
        self.load_queue_from_disk()

    # --- UI BUILDING ---
    def build_ui(self):
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=15, pady=15)

        # 1. LEFT SIDEBAR
        self.sidebar = ctk.CTkScrollableFrame(self.main_container, width=220, corner_radius=16, fg_color="transparent")
        self.sidebar.pack(side="left", fill="y", padx=(0, 10))

        try:
            logo_img = ctk.CTkImage(light_image=Image.open(resource_path("logo_light.png")), dark_image=Image.open(resource_path("logo_dark.png")), size=(180, 54))
            self.logo_label = ctk.CTkLabel(self.sidebar, text="", image=logo_img, pady=20)
        except Exception:
            self.logo_label = ctk.CTkLabel(self.sidebar, text="تفريغ\nTHAFREEG", font=("Segoe UI", 20, "bold"), text_color=self.accent_green, pady=20)
        self.logo_label.pack(side="top", fill="x")

        self.nav_btns = {}
        nav_items = [
            ("yt", "▶  YouTube"),
            ("local", "📁  Audio"),
            ("tg", "📥  Telegram"),
            ("ocr", "👁  Vision OCR"),
            ("settings", "⚙  Settings")
        ]
        for key, text in nav_items:
            btn = ctk.CTkButton(self.sidebar, text=text, font=("Segoe UI", 13, "bold"), fg_color="transparent", text_color=self.nav_inactive_fg, hover_color=self.bg_card_hover, corner_radius=20, height=40, anchor="w", command=lambda k=key: self.switch_tab(k))
            btn.pack(side="top", fill="x", pady=4, padx=12)
            self.nav_btns[key] = btn

        # BRAVE-INSPIRED EXPANDED STATS CARD
        self.stats_card = ctk.CTkFrame(self.sidebar, corner_radius=14, fg_color=self.bg_card, border_width=1, border_color=self.border_color)
        self.stats_card.pack(side="top", fill="x", padx=10, pady=(15, 10))
        ctk.CTkLabel(self.stats_card, text="SUITE STATS", font=("Segoe UI", 10, "bold"), text_color="gray").pack(anchor="w", padx=12, pady=(10, 8))
        
        # Stat 1: YouTube
        self.lbl_yt_val = ctk.CTkLabel(self.stats_card, text="0 (0m)", font=("Segoe UI", 16, "bold"), text_color="#FF4E4E")
        self.lbl_yt_val.pack(anchor="w", padx=12)
        ctk.CTkLabel(self.stats_card, text="YouTube Videos", font=("Segoe UI", 10), text_color=self.text_primary).pack(anchor="w", padx=12, pady=(0, 8))

        # Stat 2: Local Audio
        self.lbl_audio_val = ctk.CTkLabel(self.stats_card, text="0 (0m)", font=("Segoe UI", 16, "bold"), text_color="#34A853")
        self.lbl_audio_val.pack(anchor="w", padx=12)
        ctk.CTkLabel(self.stats_card, text="Audio Files", font=("Segoe UI", 10), text_color=self.text_primary).pack(anchor="w", padx=12, pady=(0, 8))

        # Stat 3: Telegram
        self.lbl_tg_val = ctk.CTkLabel(self.stats_card, text="0 (0m)", font=("Segoe UI", 16, "bold"), text_color="#1A73E8")
        self.lbl_tg_val.pack(anchor="w", padx=12)
        ctk.CTkLabel(self.stats_card, text="Telegram Files", font=("Segoe UI", 10), text_color=self.text_primary).pack(anchor="w", padx=12, pady=(0, 8))

        # Stat 4: Vision OCR
        self.lbl_ocr_val = ctk.CTkLabel(self.stats_card, text="0", font=("Segoe UI", 16, "bold"), text_color="#FF6B00")
        self.lbl_ocr_val.pack(anchor="w", padx=12)
        ctk.CTkLabel(self.stats_card, text="OCR Pages Scanned", font=("Segoe UI", 10), text_color=self.text_primary).pack(anchor="w", padx=12, pady=(0, 8))

        # Stat 5: Words Generated
        self.lbl_words_val = ctk.CTkLabel(self.stats_card, text="0", font=("Segoe UI", 16, "bold"), text_color="#A066FF")
        self.lbl_words_val.pack(anchor="w", padx=12)
        ctk.CTkLabel(self.stats_card, text="Total Words Output", font=("Segoe UI", 10), text_color=self.text_primary).pack(anchor="w", padx=12, pady=(0, 10))

        # 2. RIGHT SIDEBAR (COMMAND CENTER QUEUE MANAGER)
        self.right_sidebar = ctk.CTkFrame(self.main_container, width=280, corner_radius=16, fg_color=self.bg_card, border_width=1, border_color=self.border_color)
        self.right_sidebar.pack(side="right", fill="y", padx=(10, 0))
        self.right_sidebar.pack_propagate(False)

        right_hdr = ctk.CTkFrame(self.right_sidebar, fg_color="transparent")
        right_hdr.pack(fill="x", padx=10, pady=(15, 5))
        ctk.CTkLabel(right_hdr, text="Command Center", font=("Segoe UI", 13, "bold"), text_color=self.text_primary).pack(side="left")
        self.toggle_right_btn = ctk.CTkButton(right_hdr, text="»", width=28, height=24, fg_color="transparent", text_color=self.text_primary, hover_color=self.bg_card_hover, command=self.toggle_right_sidebar)
        self.toggle_right_btn.pack(side="right")
        
        self.open_out_btn = ctk.CTkButton(right_hdr, text="📁", width=28, height=24, fg_color="transparent", text_color=self.text_primary, hover_color=self.bg_card_hover, command=lambda: self.open_file_or_folder(self.output_dir))
        self.open_out_btn.pack(side="right", padx=(0, 5))

        q_hdr = ctk.CTkFrame(self.right_sidebar, fg_color="transparent")
        q_hdr.pack(fill="x", padx=15, pady=(10, 2))
        ctk.CTkLabel(q_hdr, text="Global Job Queue", font=("Segoe UI", 11, "bold"), text_color=self.accent_green).pack(side="left")
        ctk.CTkButton(q_hdr, text="Clear Queue", font=("Segoe UI", 10), width=65, height=20, fg_color="transparent", text_color="gray", hover_color=self.bg_card_hover, command=self.clear_global_queue).pack(side="right")
        
        # SCROLLABLE QUEUE UI
        self.queue_scroll = ctk.CTkScrollableFrame(self.right_sidebar, fg_color="transparent", corner_radius=0)
        self.queue_scroll.pack(fill="both", expand=True, padx=10, pady=5)

        self.dash_card = ctk.CTkFrame(self.right_sidebar, corner_radius=12, fg_color=self.bg_workspace, border_width=1, border_color=self.border_color)
        self.dash_card.pack(fill="x", padx=12, pady=15)
        ctk.CTkLabel(self.dash_card, text="Groq Keys Health:", font=("Segoe UI", 10, "bold"), text_color=self.text_primary).pack(anchor="w", padx=10, pady=(8, 2))
        self.lbl_key_status = ctk.CTkLabel(self.dash_card, text="Idle / Ready", font=("Segoe UI", 11), text_color="#34a853")
        self.lbl_key_status.pack(anchor="w", padx=10, pady=(0, 6))
        ctk.CTkLabel(self.dash_card, text="Telegram Anti-Ban:", font=("Segoe UI", 10, "bold"), text_color=self.text_primary).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkLabel(self.dash_card, text="Protected (FastTelethon)", font=("Segoe UI", 11), text_color="#34a853").pack(anchor="w", padx=10, pady=(0, 8))

        # 3. MAIN CENTER AREA
        self.content_area = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.content_area.pack(side="left", fill="both", expand=True)
        self.content_area.grid_rowconfigure(0, weight=1)
        self.content_area.grid_columnconfigure(0, weight=1)

        list_bg = "#141517" if self.dark_mode else "#F0F4F9"
        list_fg = "#e3e3e3" if self.dark_mode else "#1F1F1F"

        # TABS (YT, LOCAL, TG, OCR, SETTINGS)
        self.yt_tab = ctk.CTkFrame(self.content_area, corner_radius=16, fg_color=self.bg_card, border_width=1, border_color=self.border_color)
        self.yt_tab.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        ctk.CTkLabel(self.yt_tab, text="YouTube Link (Single or Playlist):", font=("Segoe UI", 13, "bold"), text_color=self.text_primary).pack(anchor="w", padx=20, pady=(20, 5))
        self.url_entry = ctk.CTkEntry(self.yt_tab, font=("Consolas", 12), height=35)
        self.url_entry.pack(fill="x", padx=20, pady=(0, 15))

        yt_ctrl = ctk.CTkFrame(self.yt_tab, fg_color="transparent")
        yt_ctrl.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(yt_ctrl, text="Custom Vocab:", text_color=self.text_primary).pack(side="left", padx=(0, 10))
        self.yt_vocab_entry = ctk.CTkEntry(yt_ctrl, font=("Consolas", 12), height=35)
        self.yt_vocab_entry.pack(side="left", fill="x", expand=True)
        self.yt_vocab_entry.insert(0, self.yt_vocab)
        ctk.CTkButton(self.yt_tab, text="Add to Queue", command=self.start_fetch_playlist, height=40, font=("Segoe UI", 13, "bold")).pack(pady=25)

        self.local_tab = ctk.CTkFrame(self.content_area, corner_radius=16, fg_color=self.bg_card, border_width=1, border_color=self.border_color)
        self.local_tab.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        btn_row = ctk.CTkFrame(self.local_tab, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkButton(btn_row, text="+ Add Audio", command=self.add_local_files, width=120).pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_row, text="Clear", command=lambda: self.clear_list(self.local_files, self.local_listbox), width=80, fg_color=("#E0E0E0", "#444444"), text_color=self.text_primary).pack(side="left")
        self.local_listbox = tk.Listbox(self.local_tab, height=5, font=("Consolas", 11), bg=list_bg, fg=list_fg, bd=0)
        self.local_listbox.pack(fill="both", expand=True, padx=20, pady=10)
        local_ctrl = ctk.CTkFrame(self.local_tab, fg_color="transparent")
        local_ctrl.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(local_ctrl, text="Custom Vocab:", text_color=self.text_primary).pack(side="left", padx=(20, 10))
        self.local_vocab_entry = ctk.CTkEntry(local_ctrl, font=("Consolas", 12), height=35)
        self.local_vocab_entry.pack(side="left", fill="x", expand=True)
        self.local_vocab_entry.insert(0, self.local_vocab)
        ctk.CTkButton(self.local_tab, text="Add Local Audio to Queue", command=self.pre_start_local_process, height=40, font=("Segoe UI", 13, "bold")).pack(pady=25)
        self.local_listbox.drop_target_register(DND_FILES)
        self.local_listbox.dnd_bind('<<Drop>>', lambda e: self.handle_drop(e, self.local_files, self.local_listbox, ['.mp3', '.m4a', '.wav']))

        self.tg_tab = ctk.CTkFrame(self.content_area, corner_radius=16, fg_color=self.bg_card, border_width=1, border_color=self.border_color)
        self.tg_tab.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        ctk.CTkLabel(self.tg_tab, text="Start Link (e.g. t.me/c/690):", font=("Segoe UI", 12, "bold"), text_color=self.text_primary).pack(anchor="w", padx=20, pady=(20, 2))
        self.tg_start_entry = ctk.CTkEntry(self.tg_tab, font=("Consolas", 12), height=35)
        self.tg_start_entry.pack(fill="x", padx=20, pady=(0, 15))
        ctk.CTkLabel(self.tg_tab, text="End Link (e.g. t.me/c/700):", font=("Segoe UI", 12, "bold"), text_color=self.text_primary).pack(anchor="w", padx=20, pady=(0, 2))
        self.tg_end_entry = ctk.CTkEntry(self.tg_tab, font=("Consolas", 12), height=35)
        self.tg_end_entry.pack(fill="x", padx=20, pady=(0, 15))
        tg_ctrl = ctk.CTkFrame(self.tg_tab, fg_color="transparent")
        tg_ctrl.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(tg_ctrl, text="Custom Vocab:", text_color=self.text_primary).pack(side="left", padx=(20, 10))
        self.tg_vocab_entry = ctk.CTkEntry(tg_ctrl, font=("Consolas", 12), height=35)
        self.tg_vocab_entry.pack(side="left", fill="x", expand=True)
        self.tg_vocab_entry.insert(0, self.tg_vocab)
        ctk.CTkButton(self.tg_tab, text="Add Telegram to Queue", command=self.pre_start_telegram_process, height=40, font=("Segoe UI", 13, "bold")).pack(pady=25)

        self.ocr_tab = ctk.CTkFrame(self.content_area, corner_radius=16, fg_color=self.bg_card, border_width=1, border_color=self.border_color)
        self.ocr_tab.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        ocr_btn_row = ctk.CTkFrame(self.ocr_tab, fg_color="transparent")
        ocr_btn_row.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkButton(ocr_btn_row, text="+ Add Images/PDF", command=self.add_vision_files, width=140).pack(side="left", padx=(0, 10))
        ctk.CTkButton(ocr_btn_row, text="Clear", command=lambda: self.clear_list(self.vision_files, self.ocr_listbox), width=80, fg_color=("#E0E0E0", "#444444"), text_color=self.text_primary).pack(side="left")
        self.ocr_listbox = tk.Listbox(self.ocr_tab, height=5, font=("Consolas", 11), bg=list_bg, fg=list_fg, bd=0)
        self.ocr_listbox.pack(fill="both", expand=True, padx=20, pady=10)
        ocr_ctrl = ctk.CTkFrame(self.ocr_tab, fg_color="transparent")
        ocr_ctrl.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(ocr_ctrl, text="Language:", text_color=self.text_primary).grid(row=0, column=0, sticky="w", padx=(0,10), pady=5)
        self.ocr_lang_var = ctk.StringVar(value=self.ocr_lang)
        ctk.CTkOptionMenu(ocr_ctrl, variable=self.ocr_lang_var, values=list(LANGUAGES.keys()), width=120).grid(row=0, column=1, sticky="w", pady=5)
        ctk.CTkLabel(ocr_ctrl, text="Direction:", text_color=self.text_primary).grid(row=0, column=2, sticky="w", padx=(20,10), pady=5)
        self.ocr_dir_var = ctk.StringVar(value=self.ocr_dir)
        ctk.CTkOptionMenu(ocr_ctrl, variable=self.ocr_dir_var, values=["RTL", "LTR"], width=100).grid(row=0, column=3, sticky="w", pady=5)
        ctk.CTkLabel(ocr_ctrl, text="Custom Prompt:", text_color=self.text_primary).grid(row=1, column=0, sticky="w", padx=(0,10), pady=(10, 5))
        self.vision_prompt_var = ctk.StringVar(value=self.ocr_vocab)
        self.vision_prompt_entry = ctk.CTkEntry(ocr_ctrl, textvariable=self.vision_prompt_var, font=("Consolas", 12), height=35)
        self.vision_prompt_entry.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(10, 5))
        ocr_ctrl.columnconfigure(3, weight=1)
        ctk.CTkButton(self.ocr_tab, text="Add Vision Scan to Queue", command=self.pre_start_vision_process, height=40, font=("Segoe UI", 13, "bold")).pack(pady=25)
        self.ocr_listbox.drop_target_register(DND_FILES)
        self.ocr_listbox.dnd_bind('<<Drop>>', lambda e: self.handle_drop(e, self.vision_files, self.ocr_listbox, ['.jpg', '.jpeg', '.png', '.pdf']))

        # INTEGRATED NATIVE SETTINGS TAB
        self.settings_tab = ctk.CTkScrollableFrame(self.content_area, corner_radius=16, fg_color=self.bg_card, border_width=1, border_color=self.border_color)
        self.settings_tab.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.theme_var = ctk.BooleanVar(value=self.dark_mode)
        theme_switch = ctk.CTkSwitch(self.settings_tab, text="Enable Dark Mode", variable=self.theme_var, command=self.toggle_theme, text_color=self.text_primary, font=("Segoe UI", 12, "bold"))
        theme_switch.pack(anchor="e", padx=20, pady=(20, 0))

        ctk.CTkLabel(self.settings_tab, text="Groq API Keys (Paste 1 per line):", font=("Segoe UI", 12, "bold"), text_color=self.text_primary).pack(anchor="w", padx=20, pady=(10, 5))
        self.keys_text = ctk.CTkTextbox(self.settings_tab, height=80, font=("Consolas", 11), border_width=1, fg_color=self.bg_workspace, text_color=self.text_primary, border_color=self.border_color)
        self.keys_text.pack(fill="x", padx=20)
        
        placeholder_text = "gsk_12345abcdefg###\ngsk_67890hijklmn###"
        if self.api_keys:
            self.keys_text.insert("1.0", "\n".join(self.api_keys))
        else:
            self.keys_text.insert("1.0", placeholder_text)
            self.keys_text.configure(text_color="gray")

        def on_focus_in(e):
            if self.keys_text.get("1.0", tk.END).strip() == placeholder_text:
                self.keys_text.delete("1.0", tk.END)
                self.keys_text.configure(text_color=self.text_primary)
                
        def on_focus_out(e):
            if not self.keys_text.get("1.0", tk.END).strip():
                self.keys_text.insert("1.0", placeholder_text)
                self.keys_text.configure(text_color="gray")

        self.keys_text.bind("<FocusIn>", on_focus_in)
        self.keys_text.bind("<FocusOut>", on_focus_out)

        ctk.CTkLabel(self.settings_tab, text="Telegram API ID:", font=("Segoe UI", 12, "bold"), text_color=self.text_primary).pack(anchor="w", padx=20, pady=(20, 5))
        self.tg_id_entry = ctk.CTkEntry(self.settings_tab, font=("Consolas", 12), height=35, border_width=1, border_color=self.border_color)
        self.tg_id_entry.insert(0, self.tg_api_id)
        self.tg_id_entry.pack(fill="x", padx=20)

        ctk.CTkLabel(self.settings_tab, text="Telegram API Hash:", font=("Segoe UI", 12, "bold"), text_color=self.text_primary).pack(anchor="w", padx=20, pady=(15, 5))
        self.tg_hash_entry = ctk.CTkEntry(self.settings_tab, font=("Consolas", 12), height=35, border_width=1, border_color=self.border_color)
        self.tg_hash_entry.insert(0, self.tg_api_hash)
        self.tg_hash_entry.pack(fill="x", padx=20)

        ctk.CTkLabel(self.settings_tab, text="Output Folder:", font=("Segoe UI", 12, "bold"), text_color=self.text_primary).pack(anchor="w", padx=20, pady=(20, 5))
        dir_frame = ctk.CTkFrame(self.settings_tab, fg_color="transparent")
        dir_frame.pack(fill="x", padx=20)
        self.dir_entry = ctk.CTkEntry(dir_frame, font=("Consolas", 12), height=35, border_width=1, border_color=self.border_color)
        self.dir_entry.insert(0, self.output_dir)
        self.dir_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(dir_frame, text="Browse", command=self.browse_folder, width=80).pack(side="right", padx=(10, 0))

        ctk.CTkLabel(self.settings_tab, text="Output File Name:", font=("Segoe UI", 12, "bold"), text_color=self.text_primary).pack(anchor="w", padx=20, pady=(15, 5))
        self.file_entry = ctk.CTkEntry(self.settings_tab, font=("Consolas", 12), height=35, border_width=1, border_color=self.border_color)
        self.file_entry.insert(0, self.output_file)
        self.file_entry.pack(fill="x", padx=20)

        ctk.CTkLabel(self.settings_tab, text="Advanced Modules:", font=("Segoe UI", 13, "bold"), text_color=self.text_primary).pack(anchor="w", padx=20, pady=(25, 10))
        self.noise_var = ctk.BooleanVar(value=self.noise_reduction)
        ctk.CTkCheckBox(self.settings_tab, text="Enable FFmpeg Noise Reduction (afftdn)", variable=self.noise_var, text_color=self.text_primary).pack(anchor="w", padx=30, pady=5)
        
        self.docx_var = ctk.BooleanVar(value=self.export_docx)
        ctk.CTkCheckBox(self.settings_tab, text="Auto-Export as Word Document (.docx)", variable=self.docx_var, text_color=self.text_primary).pack(anchor="w", padx=30, pady=5)
        
        self.md_var = ctk.BooleanVar(value=self.export_md)
        ctk.CTkCheckBox(self.settings_tab, text="Auto-Export as Markdown (.md)", variable=self.md_var, text_color=self.text_primary).pack(anchor="w", padx=30, pady=5)

        btn_frame = ctk.CTkFrame(self.settings_tab, fg_color="transparent")
        btn_frame.pack(pady=30)
        ctk.CTkButton(btn_frame, text="📥 Import Config", command=self.import_system_config, fg_color=("#E0E0E0", "#444444"), text_color=self.text_primary, hover_color=("#D0D0D0", "#555555")).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="💾 Save Settings", command=self.save_settings_from_tab, font=("Segoe UI", 12, "bold")).pack(side="left", padx=10)
        
        # BOTTOM MASTER PROGRESS & LOG
        progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        progress_frame.pack(fill="x", padx=30, pady=5)
        self.progress_label = ctk.CTkLabel(progress_frame, text="Idle", font=("Segoe UI", 12, "bold"), text_color=self.text_primary)
        self.progress_label.pack(side="top", pady=2)
        self.progress = ctk.CTkProgressBar(progress_frame, height=10)
        self.progress.set(0)
        self.progress.pack(side="top", fill="x")

        log_frame = ctk.CTkFrame(self, fg_color="transparent")
        log_frame.pack(fill="both", expand=True, padx=30, pady=(15, 30))
        ctk.CTkLabel(log_frame, text="Live Output Log", font=("Segoe UI", 12, "bold"), text_color=self.text_primary).pack(anchor="w", pady=(0, 5))
        self.log_text = ctk.CTkTextbox(log_frame, wrap="word", height=150, state='disabled', fg_color=self.log_bg, text_color=self.log_text_color, font=("Consolas", 11), border_width=1, border_color=self.border_color)
        self.log_text.pack(fill="both", expand=True)

        self.update_stats_ui()
        self.print_startup_instructions()
        self.switch_tab("yt")

    # --- QUEUE MANAGEMENT (THE NEW ENGINE) ---
    def add_task_to_queue(self, task_type, task_name, task_data):
        if not self.check_readiness(): return
        
        t_id = str(int(time.time() * 1000))
        task = Task(
            t_id, task_type, task_name, task_data,
            log_callback=self.log,
            status_callback=self.sync_task_ui,
            key_status_callback=self.update_key_status,
            analytics_callback=self.update_analytics
        )
        self.global_queue.append(task)
        
        # Build Task Card UI
        card = ctk.CTkFrame(self.queue_scroll, fg_color=self.bg_card, corner_radius=8, border_width=1, border_color=self.border_color)
        card.pack(fill="x", pady=4, padx=2)
        task.card_ui = card
        
        # Bind double-click event to open containing folder/file
        card.bind("<Double-1>", lambda e, p=task_data.get('output_path'): self.open_file_or_folder(p))
        
        # Top Row: Name & Move Controls
        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=8, pady=(8, 2))
        lbl_name = ctk.CTkLabel(top_row, text=task_name[:25]+"..." if len(task_name)>25 else task_name, font=("Segoe UI", 12, "bold"), text_color=self.text_primary)
        lbl_name.pack(side="left")
        
        top_row.bind("<Double-1>", lambda e, p=task_data.get('output_path'): self.open_file_or_folder(p))
        lbl_name.bind("<Double-1>", lambda e, p=task_data.get('output_path'): self.open_file_or_folder(p))
        
        btn_up = ctk.CTkButton(top_row, text="▲", width=20, height=20, fg_color="transparent", text_color=self.text_primary, hover_color=self.bg_card_hover, command=lambda t=task: self.move_task(t, -1))
        btn_up.pack(side="right")
        btn_dn = ctk.CTkButton(top_row, text="▼", width=20, height=20, fg_color="transparent", text_color=self.text_primary, hover_color=self.bg_card_hover, command=lambda t=task: self.move_task(t, 1))
        btn_dn.pack(side="right", padx=(0, 5))

        # Middle Row: Status & Actions
        mid_row = ctk.CTkFrame(card, fg_color="transparent")
        mid_row.pack(fill="x", padx=8, pady=(0, 4))
        task.lbl_status = ctk.CTkLabel(mid_row, text=TaskStatus.QUEUED, font=("Segoe UI", 10), text_color="gray")
        task.lbl_status.pack(side="left")
        
        # Action Buttons
        task.btn_pause = ctk.CTkButton(mid_row, text="⏸", width=24, height=24, fg_color="#fbbc05", text_color="black", hover_color="#e0a800", command=task.pause)
        task.btn_resume = ctk.CTkButton(mid_row, text="▶", width=24, height=24, fg_color="#34a853", text_color="white", hover_color="#2b8c46", command=task.resume)
        task.btn_cancel = ctk.CTkButton(mid_row, text="✖", width=24, height=24, fg_color="#ea4335", text_color="white", hover_color="#c9302c", command=task.cancel)
        task.btn_retry = ctk.CTkButton(mid_row, text="↻", width=24, height=24, fg_color="#1A73E8", text_color="white", hover_color="#1558b0", command=lambda t=task: self.retry_task(t))
        
        task.btn_cancel.pack(side="right")
        
        # Bottom Row: Progress
        task.card_progress = ctk.CTkProgressBar(card, height=6, progress_color="gray")
        task.card_progress.set(0)
        task.card_progress.pack(fill="x", padx=8, pady=(0, 10))
        
        self.save_queue_to_disk()
        
        if not self.is_queue_running:
            self.is_queue_running = True
            threading.Thread(target=self._process_queue_loop, daemon=True).start()

    def sync_task_ui(self, task):
        colors = {
            TaskStatus.QUEUED: ("gray", "gray"), TaskStatus.RUNNING: ("#fbbc05", "#fbbc05"),
            TaskStatus.PAUSED: ("#fbbc05", "gray"), TaskStatus.COMPLETED: ("#34a853", "#34a853"),
            TaskStatus.FAILED: ("#ea4335", "#ea4335"), TaskStatus.CANCELLED: ("gray", "gray")
        }
        text_color, bar_color = colors.get(task.status, ("gray", "gray"))
        
        def _update():
            try:
                task.lbl_status.configure(text=f"{task.status} | {task.eta_text}", text_color=text_color)
                task.card_progress.configure(progress_color=bar_color)
                task.card_progress.set(task.progress_fraction)
                
                for b in [task.btn_pause, task.btn_resume, task.btn_cancel, task.btn_retry]: b.pack_forget()
                
                if task.status == TaskStatus.RUNNING:
                    task.btn_cancel.pack(side="right")
                    task.btn_pause.pack(side="right", padx=(0, 5))
                elif task.status == TaskStatus.PAUSED:
                    task.btn_cancel.pack(side="right")
                    task.btn_resume.pack(side="right", padx=(0, 5))
                elif task.status == TaskStatus.QUEUED:
                    task.btn_cancel.pack(side="right")
                elif task.status in [TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    task.btn_cancel.pack(side="right")
                    task.btn_retry.pack(side="right", padx=(0, 5))
                else:
                    task.btn_cancel.configure(text="OK")
                    task.btn_cancel.pack(side="right")
                    
                if self.active_task and self.active_task.id == task.id:
                    self.progress.set(task.progress_fraction)
                    prog_percent = int(task.progress_fraction * 100)
                    self.progress_label.configure(text=f"Active: {task.name} ({prog_percent}%) | {task.eta_text}")
                    if self.taskbar and self.winfo_id():
                        if task.status == TaskStatus.PAUSED: self.taskbar.set_state(self.winfo_id(), WindowsTaskbarProgress.TBPF_PAUSED)
                        else: self.taskbar.set_progress(self.winfo_id(), prog_percent, 100)
            except Exception: pass
        self.after(0, _update)

    def _process_queue_loop(self):
        while True:
            self.active_task = None
            for t in self.global_queue:
                if t.status == TaskStatus.QUEUED:
                    self.active_task = t
                    break
                    
            if not self.active_task: break
                
            self.active_task.start_time = time.time()
            self.active_task._update_status(TaskStatus.RUNNING)
            
            try:
                if self.active_task.type == 'YT': run_youtube_pipeline(self.active_task)
                elif self.active_task.type == 'LOCAL': run_local_pipeline(self.active_task)
                elif self.active_task.type == 'VISION': run_vision_pipeline(self.active_task)
                elif self.active_task.type == 'TG': run_telegram_pipeline(self.active_task)
                
                if self.active_task.status != TaskStatus.CANCELLED:
                    self.active_task._update_status(TaskStatus.COMPLETED)
            except Exception as e:
                if "Cancelled" in str(e): self.active_task._update_status(TaskStatus.CANCELLED)
                else:
                    self.log(f"[!] Task Failed: {e}")
                    self.active_task._update_status(TaskStatus.FAILED)
                    
            self.save_queue_to_disk()
            
        self.is_queue_running = False
        self.active_task = None
        self.after(0, self.reset_gui)

    def move_task(self, task, direction):
        idx = self.global_queue.index(task)
        new_idx = idx + direction
        if 0 <= new_idx < len(self.global_queue):
            self.global_queue[idx], self.global_queue[new_idx] = self.global_queue[new_idx], self.global_queue[idx]
            self.after(0, self._redraw_queue)
            self.save_queue_to_disk()

    def retry_task(self, task):
        task.progress_fraction = 0
        task._cancel_flag = False
        task._pause_event.set()
        task._update_status(TaskStatus.QUEUED)
        if not self.is_queue_running:
            self.is_queue_running = True
            threading.Thread(target=self._process_queue_loop, daemon=True).start()

    def _redraw_queue(self):
        for widget in self.queue_scroll.winfo_children(): widget.pack_forget()
        for t in self.global_queue: t.card_ui.pack(fill="x", pady=4, padx=2)

    def clear_global_queue(self):
        to_remove = [t for t in self.global_queue if t.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED]]
        for t in to_remove:
            if hasattr(t, 'card_ui') and t.card_ui:
                t.card_ui.destroy()
            self.global_queue.remove(t)
        self.save_queue_to_disk()

    # --- ADD TO QUEUE TRIGGERS ---
    def start_fetch_playlist(self):
        url = self.url_entry.get().strip()
        if not url: return
        self.yt_vocab = self.yt_vocab_entry.get().strip(); self.save_config()
        
        self.url_entry.delete(0, tk.END)
        self.log("\nAnalyzing YouTube link...")
        threading.Thread(target=self._fetch_and_queue_yt, args=(url,), daemon=True).start()

    def _fetch_and_queue_yt(self, url):
        try:
            title, entries = fetch_yt_playlist_info(url)
            data = {'entries': entries, 'output_path': self.get_full_output_path("YT"), 'append': False, 'config': self.get_current_config(), 'api_keys': self.api_keys, 'vocab': self.yt_vocab}
            self.after(0, lambda: self.add_task_to_queue("YT", title, data))
        except Exception as e: self.log(f"[!] YT Fetch Error: {e}")

    def pre_start_local_process(self):
        if not self.local_files: return
        self.local_vocab = self.local_vocab_entry.get().strip(); self.save_config()
        
        files_to_process = list(self.local_files)
        self.clear_list(self.local_files, self.local_listbox)
        data = {'entries': files_to_process, 'output_path': self.get_full_output_path("LOCAL"), 'append': False, 'config': self.get_current_config(), 'api_keys': self.api_keys, 'vocab': self.local_vocab}
        self.add_task_to_queue("LOCAL", f"Local Audio ({len(files_to_process)} files)", data)

    def pre_start_telegram_process(self):
        sl, el = self.tg_start_entry.get().strip(), self.tg_end_entry.get().strip()
        if not sl or not el or not self.tg_api_id: return
        self.tg_vocab = self.tg_vocab_entry.get().strip(); self.save_config()
        
        self.tg_start_entry.delete(0, tk.END); self.tg_end_entry.delete(0, tk.END)
        data = {'start': sl, 'end': el, 'tg_id': self.tg_api_id, 'tg_hash': self.tg_api_hash, 'output_path': self.get_full_output_path("TG"), 'append': False, 'config': self.get_current_config(), 'api_keys': self.api_keys, 'vocab': self.tg_vocab}
        self.add_task_to_queue("TG", f"Telegram Harvest", data)

    def pre_start_vision_process(self):
        if not self.vision_files: return
        self.ocr_lang = self.ocr_lang_var.get(); self.ocr_dir = self.ocr_dir_var.get(); self.ocr_vocab = self.vision_prompt_var.get().strip()[:200]; self.save_config()
        
        files_to_process = list(self.vision_files)
        self.clear_list(self.vision_files, self.ocr_listbox)
        data = {'entries': files_to_process, 'output_path': self.get_full_output_path("VISION"), 'append': False, 'config': self.get_current_config(), 'api_keys': self.api_keys, 'vocab': self.ocr_vocab, 'ocr_lang': self.ocr_lang, 'ocr_dir': self.ocr_dir}
        self.add_task_to_queue("VISION", f"Vision Scan ({len(files_to_process)} items)", data)

    # --- SETTINGS & HELPERS ---
    def clear_list(self, arr, listbox):
        arr.clear(); listbox.delete(0, tk.END)
    
    def handle_drop(self, event, target_list, listbox, allowed_exts):
        for f in self.tk.splitlist(event.data):
            if os.path.splitext(f)[1].lower() in allowed_exts and f not in target_list: target_list.append(f); listbox.insert(tk.END, os.path.basename(f))

    def get_full_output_path(self, task_type):
        folders = {"YT": "YouTube", "LOCAL": "Audio", "TG": "Telegram", "VISION": "OCR"}
        subfolder = os.path.join(self.output_dir, folders.get(task_type, "Misc"))
        os.makedirs(subfolder, exist_ok=True)
        
        name, ext = os.path.splitext(self.output_file)
        base_path = os.path.join(subfolder, f"{name}{ext}")
        
        if not os.path.exists(base_path): 
            return base_path
            
        c = 1
        while os.path.exists(os.path.join(subfolder, f"{name}_{c}{ext}")): 
            c += 1
        return os.path.join(subfolder, f"{name}_{c}{ext}")

    def open_file_or_folder(self, path):
        if not path: return
        try:
            if os.path.exists(path):
                if os.name == 'nt': subprocess.run(['explorer', '/select,', os.path.normpath(path)])
                else: os.startfile(os.path.dirname(path))
            elif os.path.exists(os.path.dirname(path)):
                os.startfile(os.path.dirname(path))
        except Exception as e:
            self.log(f"[!] Unable to open path: {e}")

    def check_readiness(self):
        if not self.api_keys: messagebox.showwarning("Missing Info", "Add Groq Keys in Settings."); return False
        return True

    def get_current_config(self): return {'noise_reduction': self.noise_reduction, 'export_docx': self.export_docx, 'export_md': self.export_md}

    def reset_gui(self):
        self.update_key_status("Idle / Ready", "green")
        self.progress.set(0)
        self.progress_label.configure(text="Idle")
        if self.taskbar and self.winfo_id(): self.taskbar.set_state(self.winfo_id(), WindowsTaskbarProgress.TBPF_NOPROGRESS)

    def load_config(self):
        c = load_config(CONFIG_FILE)
        self.api_keys = c.get("api_keys", [])
        self.tg_api_id = c.get("tg_api_id", "")
        self.tg_api_hash = c.get("tg_api_hash", "")
        self.output_dir = c.get("output_dir", os.getcwd())
        self.output_file = c.get("output_file", "Thafreeg_Transcription.txt")
        self.yt_vocab = c.get("yt_vocab", "")
        self.local_vocab = c.get("local_vocab", "")
        self.tg_vocab = c.get("tg_vocab", "")
        self.ocr_vocab = c.get("custom_vision_prompt", "")
        self.ocr_lang = c.get("ocr_lang", "Arabic")
        self.ocr_dir = c.get("ocr_dir", "RTL")
        self.noise_reduction = c.get("noise_reduction", False)
        self.export_docx = c.get("export_docx", False)
        self.export_md = c.get("export_md", False)
        self.dark_mode = c.get("dark_mode", True)
        
        self.stats_yt_count = c.get("stats_yt_count", 0)
        self.stats_yt_sec = c.get("stats_yt_sec", 0)
        self.stats_local_count = c.get("stats_local_count", 0)
        self.stats_local_sec = c.get("stats_local_sec", 0)
        self.stats_tg_count = c.get("stats_tg_count", 0)
        self.stats_tg_sec = c.get("stats_tg_sec", 0)
        self.stats_ocr_pages = c.get("stats_ocr_pages", 0)
        self.stats_total_words = c.get("stats_total_words", 0)

    def save_config(self):
        config_data = {
            "api_keys": self.api_keys, "tg_api_id": self.tg_api_id, "tg_api_hash": self.tg_api_hash,
            "output_dir": self.output_dir, "output_file": self.output_file, "yt_vocab": self.yt_vocab,
            "local_vocab": self.local_vocab, "tg_vocab": self.tg_vocab, "custom_vision_prompt": self.ocr_vocab,
            "ocr_lang": self.ocr_lang, "ocr_dir": self.ocr_dir, "noise_reduction": self.noise_reduction,
            "export_docx": self.export_docx, "export_md": self.export_md, "dark_mode": self.dark_mode,
            "stats_yt_count": self.stats_yt_count, "stats_yt_sec": self.stats_yt_sec,
            "stats_local_count": self.stats_local_count, "stats_local_sec": self.stats_local_sec,
            "stats_tg_count": self.stats_tg_count, "stats_tg_sec": self.stats_tg_sec,
            "stats_ocr_pages": self.stats_ocr_pages, "stats_total_words": self.stats_total_words
        }
        save_config(config_data, CONFIG_FILE)

    def save_queue_to_disk(self):
        q_data = []
        for t in self.global_queue:
            if t.status in [TaskStatus.QUEUED, TaskStatus.PAUSED, TaskStatus.RUNNING]:
                q_data.append({"type": t.type, "name": t.name, "data": t.data})
        try: json.dump(q_data, open(QUEUE_FILE, 'w'), indent=4)
        except Exception: pass

    def load_queue_from_disk(self):
        if os.path.exists(QUEUE_FILE):
            try:
                q_data = json.load(open(QUEUE_FILE, 'r'))
                for task in q_data: self.add_task_to_queue(task["type"], task["name"], task["data"])
            except Exception: pass

    # --- MISC UTILS (Tray, Log, UI toggles) ---
    def switch_tab(self, tab_key):
        for btn in self.nav_btns.values(): 
            btn.configure(fg_color="transparent", text_color=self.nav_inactive_fg)
            
        # Hide all tabs (This bypasses the CustomTkinter overlap bug)
        for tab in [self.yt_tab, self.local_tab, self.tg_tab, self.ocr_tab, self.settings_tab]:
            tab.grid_remove()
            
        # Reveal only the requested tab
        if tab_key == "yt": self.yt_tab.grid()
        elif tab_key == "local": self.local_tab.grid()
        elif tab_key == "tg": self.tg_tab.grid()
        elif tab_key == "ocr": self.ocr_tab.grid()
        elif tab_key == "settings": self.settings_tab.grid()
        
        self.nav_btns[tab_key].configure(fg_color=self.nav_active_bg, text_color=self.nav_active_fg)

    def toggle_right_sidebar(self):
        if self.right_sidebar_visible:
            self.right_sidebar.pack_forget(); self.toggle_right_btn.configure(text="«"); self.right_sidebar_visible = False
        else:
            self.right_sidebar.pack(side="right", fill="y", padx=(10, 0)); self.toggle_right_btn.configure(text="»"); self.right_sidebar_visible = True

    def toggle_theme(self):
        self.dark_mode = self.theme_var.get()
        mode = "dark" if self.dark_mode else "light"
        ctk.set_appearance_mode(mode)
        
        list_bg = "#141517" if self.dark_mode else "#F0F4F9"
        list_fg = "#e3e3e3" if self.dark_mode else "#1F1F1F"
        try:
            self.local_listbox.config(bg=list_bg, fg=list_fg)
            self.ocr_listbox.config(bg=list_bg, fg=list_fg)
        except Exception: pass

    def import_system_config(self):
        file_path = filedialog.askopenfilename(title="Select config.json", filetypes=[("JSON Files", "*.json")])
        if file_path:
            try:
                with open(file_path, 'r') as src, open(CONFIG_FILE, 'w') as dst: dst.write(src.read())
                self.load_config()
                messagebox.showinfo("Success", "System configuration imported successfully!")
            except Exception as e: messagebox.showerror("Error", f"Failed to import config: {e}")

    def browse_folder(self):
        f = filedialog.askdirectory(title="Select Output Folder")
        if f: self.dir_entry.delete(0, tk.END); self.dir_entry.insert(0, f)

    def save_settings_from_tab(self):
        raw_keys = self.keys_text.get("1.0", tk.END).strip()
        if raw_keys and "gsk_" in raw_keys: self.api_keys = [k.strip() for k in raw_keys.split('\n') if k.strip()]
        else: self.api_keys = []
            
        self.tg_api_id = self.tg_id_entry.get().strip()
        self.tg_api_hash = self.tg_hash_entry.get().strip()
        self.output_dir = self.dir_entry.get().strip()
        self.output_file = self.file_entry.get().strip()
                
        self.noise_reduction = self.noise_var.get()
        self.export_docx = self.docx_var.get()
        self.export_md = self.md_var.get()
        
        self.save_config()
        self.log("⚙️ Settings updated successfully.")

    def update_analytics(self, yt_count=0, yt_sec=0, local_count=0, local_sec=0, tg_count=0, tg_sec=0, ocr_pages=0, words=0):
        self.stats_yt_count += yt_count
        self.stats_yt_sec += yt_sec
        self.stats_local_count += local_count
        self.stats_local_sec += local_sec
        self.stats_tg_count += tg_count
        self.stats_tg_sec += tg_sec
        self.stats_ocr_pages += ocr_pages
        self.stats_total_words += words
        self.save_config()
        self.after(0, self.update_stats_ui)

    def update_stats_ui(self):
        yt_dur = format_duration(self.stats_yt_sec)
        local_dur = format_duration(self.stats_local_sec)
        tg_dur = format_duration(self.stats_tg_sec)
        
        self.lbl_yt_val.configure(text=f"{self.stats_yt_count} {yt_dur}")
        self.lbl_audio_val.configure(text=f"{self.stats_local_count} {local_dur}")
        self.lbl_tg_val.configure(text=f"{self.stats_tg_count} {tg_dur}")
        self.lbl_ocr_val.configure(text=f"{self.stats_ocr_pages}")
        self.lbl_words_val.configure(text=f"{self.stats_total_words:,}")

    def update_key_status(self, text, color_code):
        colors = {"green": "#34a853", "yellow": "#fbbc05", "red": "#ea4335"}
        self.after(0, lambda: self.lbl_key_status.configure(text=text, text_color=colors.get(color_code, "#34a853")))

    def hide_window(self):
        self.withdraw()
        try: tray_image = Image.open(resource_path("icon.png"))
        except Exception: tray_image = Image.new('RGB', (64, 64), color=(43, 43, 43)); ImageDraw.Draw(tray_image).rectangle((16, 16, 48, 48), fill=(0, 255, 0))
        self.tray_icon = pystray.Icon("Thafreeg", tray_image, "Thafreeg", pystray.Menu(pystray.MenuItem('Show App', self.show_window, default=True), pystray.MenuItem('Exit', self.quit_window)))
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self, icon, item): self.tray_icon.stop(); self.after(0, self.deiconify)
    def quit_window(self, icon, item): self.tray_icon.stop(); self.destroy(); os._exit(0)
    
    def log(self, message):
        def _log():
            self.log_text.configure(state='normal')
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state='disabled')
        self.after(0, _log)

    def add_local_files(self):
        for f in filedialog.askopenfilenames(filetypes=(("Audio", "*.mp3 *.m4a *.wav"), ("All", "*.*"))):
            if f not in self.local_files: self.local_files.append(f); self.local_listbox.insert(tk.END, os.path.basename(f))
            
    def add_vision_files(self):
        for f in filedialog.askopenfilenames(filetypes=(("Images & PDFs", "*.jpg *.png *.jpeg *.pdf"), ("All", "*.*"))):
            if f not in self.vision_files: self.vision_files.append(f); self.ocr_listbox.insert(tk.END, os.path.basename(f))

    def print_startup_instructions(self):
        self.log("===============================================================\n"
                 "                 THAFREEG - ASYNC QUEUE EDITION\n"
                 "===============================================================\n"
                 "► NEW: Dynamic Queue Task Cards with Pause/Resume/Cancel.\n"
                 "► NEW: Integrated Settings Workspace Tab.\n"
                 "► NEW: Granular Brave-Style Lifetime Analytics Dashboard.\n"
                 "► NEW: Accurately Probed Audio Durations & Word Counts.\n"
                 "===============================================================\n")

if __name__ == "__main__":
    app = ThafreegApp()
    app.mainloop()