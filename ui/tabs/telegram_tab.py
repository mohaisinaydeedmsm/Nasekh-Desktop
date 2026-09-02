import os
import time
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt
from qfluentwidgets import (
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    LineEdit,
    TextEdit,
    ProgressBar,
    PrimaryPushButton,
    CardWidget,
    InfoBar
)

from core.config_manager import load_config, save_config
from core.utils import Task
from core.task_worker import TaskWorker

class TelegramTab(QWidget):
    """Telegram Harvester Tab UI with thread-safe TaskWorker execution."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("telegram_tab")
        self.worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # Header
        title = SubtitleLabel("Telegram Harvester", self)
        layout.addWidget(title)

        # Input Card
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        lbl_start = BodyLabel("Start Link (e.g. t.me/c/123/456):", card)
        self.start_entry = LineEdit(card)
        self.start_entry.setPlaceholderText("https://t.me/channel_name/100")
        card_layout.addWidget(lbl_start)
        card_layout.addWidget(self.start_entry)

        lbl_end = BodyLabel("End Link (e.g. t.me/c/123/460):", card)
        self.end_entry = LineEdit(card)
        self.end_entry.setPlaceholderText("https://t.me/channel_name/110")
        card_layout.addWidget(lbl_end)
        card_layout.addWidget(self.end_entry)

        lbl_vocab = BodyLabel("Custom Vocabulary / Prompt:", card)
        self.vocab_entry = LineEdit(card)
        self.vocab_entry.setPlaceholderText("Optional e.g. names, terms, or domain vocab")
        card_layout.addWidget(lbl_vocab)
        card_layout.addWidget(self.vocab_entry)

        self.start_btn = PrimaryPushButton("Start Telegram Harvest", card)
        self.start_btn.clicked.connect(self.start_processing)
        card_layout.addWidget(self.start_btn)

        layout.addWidget(card)

        # Progress Card
        prog_card = CardWidget(self)
        prog_layout = QVBoxLayout(prog_card)
        prog_layout.setContentsMargins(16, 14, 16, 14)
        prog_layout.setSpacing(8)

        self.status_lbl = CaptionLabel("Status: Idle", prog_card)
        self.progress_bar = ProgressBar(prog_card)
        self.progress_bar.setVal(0)

        prog_layout.addWidget(self.status_lbl)
        prog_layout.addWidget(self.progress_bar)
        layout.addWidget(prog_card)

        # Log Output Section
        log_hdr = BodyLabel("Live Output Log", self)
        layout.addWidget(log_hdr)

        self.log_edit = TextEdit(self)
        self.log_edit.setReadOnly(True)
        layout.addWidget(self.log_edit, 1)

    def log(self, text):
        self.log_edit.append(str(text))

    def start_processing(self):
        sl = self.start_entry.text().strip()
        el = self.end_entry.text().strip()
        vocab = self.vocab_entry.text().strip()

        if not sl or not el:
            InfoBar.warning("Missing Links", "Please enter both Start and End Telegram post links.", duration=-1, parent=self)
            return

        config = load_config()
        tg_id = config.get("tg_api_id", "")
        tg_hash = config.get("tg_api_hash", "")

        if not tg_id or not tg_hash:
            InfoBar.error("Missing Credentials", "Please set Telegram API ID and Hash in Settings.", duration=-1, parent=self)
            return

        api_keys = config.get("api_keys", [])
        if not api_keys:
            InfoBar.error("Missing API Keys", "Please add at least one Groq API Key in Settings.", duration=-1, parent=self)
            return

        subfolder = os.path.join(config.get("output_dir", os.getcwd()), "Telegram")
        os.makedirs(subfolder, exist_ok=True)
        output_file = config.get("output_file", "Thafreeg_Transcription.txt")
        name, ext = os.path.splitext(output_file)
        full_out_path = os.path.join(subfolder, f"{name}{ext}")

        task_data = {
            "start": sl,
            "end": el,
            "tg_id": tg_id,
            "tg_hash": tg_hash,
            "output_path": full_out_path,
            "append": False,
            "config": {
                "noise_reduction": config.get("noise_reduction", False),
                "export_docx": config.get("export_docx", False),
                "export_md": config.get("export_md", False)
            },
            "api_keys": api_keys,
            "vocab": vocab
        }

        t_id = f"tg_{int(time.time() * 1000)}"
        task = Task(t_id, "TG", "Telegram Harvest", task_data)

        self.start_btn.setEnabled(False)
        self.log(f"\n[+] Starting Telegram Harvest: {sl} -> {el}")

        self.worker = TaskWorker(task, self)
        self.worker.progress_changed.connect(self._on_progress_changed)
        self.worker.log_added.connect(self._on_log_added)
        self.worker.task_finished.connect(self._on_task_finished)
        self.worker.task_failed.connect(self._on_task_failed)

        self.status_lbl.setText("Status: Connecting to Telegram...")
        self.worker.start()

    def _on_progress_changed(self, task_id, fraction, eta_text):
        percent = int(fraction * 100)
        self.progress_bar.setVal(percent)
        self.status_lbl.setText(f"Processing ({percent}%) | {eta_text}")
        main_win = self.window()
        if hasattr(main_win, 'update_global_progress'):
            main_win.update_global_progress("Telegram Harvester", fraction, eta_text)

    def _on_log_added(self, task_id, text):
        self.log(text)
        main_win = self.window()
        if hasattr(main_win, 'log_global'):
            main_win.log_global(text)

    def _on_task_finished(self, task_id, stats_delta):
        self.progress_bar.setVal(100)
        self.status_lbl.setText("Status: Completed successfully!")
        self.start_btn.setEnabled(True)
        main_win = self.window()
        if hasattr(main_win, 'reset_global_task'):
            main_win.reset_global_task("Completed")

        cfg = load_config()
        cfg["stats_tg_count"] = cfg.get("stats_tg_count", 0) + stats_delta.get("tg_count", 0)
        cfg["stats_tg_sec"] = cfg.get("stats_tg_sec", 0) + stats_delta.get("tg_sec", 0)
        cfg["stats_total_words"] = cfg.get("stats_total_words", 0) + stats_delta.get("words", 0)
        save_config(cfg)

        if hasattr(main_win, 'refresh_stats'):
            main_win.refresh_stats()

        InfoBar.success("Telegram Harvest Complete", "Telegram posts processing finished.", parent=self)

    def _on_task_failed(self, task_id, err_msg):
        self.status_lbl.setText("Status: Failed")
        self.start_btn.setEnabled(True)
        main_win = self.window()
        if hasattr(main_win, 'reset_global_task'):
            main_win.reset_global_task("Failed")
        InfoBar.error("Task Failed", f"Telegram task error: {err_msg}", duration=-1, parent=self)
