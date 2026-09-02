import os
import time
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QDialog
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
from core.yt_engine import fetch_yt_playlist_info
from core.task_worker import TaskWorker
from ui.components.playlist_modal import PlaylistSelectionModal

class YouTubeTab(QWidget):
    """YouTube Harvest Tab UI with thread-safe TaskWorker execution."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("youtube_tab")
        self.worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # Header
        title = SubtitleLabel("YouTube Harvest", self)
        layout.addWidget(title)

        # Input Card
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        lbl_url = BodyLabel("YouTube Video or Playlist Link:", card)
        self.url_entry = LineEdit(card)
        self.url_entry.setPlaceholderText("https://www.youtube.com/watch?v=... or playlist link")
        card_layout.addWidget(lbl_url)
        card_layout.addWidget(self.url_entry)

        lbl_vocab = BodyLabel("Custom Vocabulary / Prompt:", card)
        self.vocab_entry = LineEdit(card)
        self.vocab_entry.setPlaceholderText("Optional e.g. names, terms, or domain vocab")
        card_layout.addWidget(lbl_vocab)
        card_layout.addWidget(self.vocab_entry)

        self.start_btn = PrimaryPushButton("Start YouTube Processing", card)
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
        url = self.url_entry.text().strip()
        vocab = self.vocab_entry.text().strip()

        if not url:
            InfoBar.warning("Missing URL", "Please enter a valid YouTube URL.", duration=-1, parent=self)
            return

        config = load_config()
        api_keys = config.get("api_keys", [])
        if not api_keys:
            InfoBar.error("Missing API Keys", "Please add at least one Groq API Key in Settings.", duration=-1, parent=self)
            return

        self.start_btn.setEnabled(False)
        self.log(f"\n[+] Analyzing YouTube link: {url}")
        self.status_lbl.setText("Status: Extracting YouTube metadata...")
        self.progress_bar.setVal(5)

        try:
            title, entries = fetch_yt_playlist_info(url)
        except Exception as e:
            self.log(f"[!] Metadata Extraction Failed: {e}")
            self.status_lbl.setText("Status: Error")
            self.start_btn.setEnabled(True)
            return

        if len(entries) > 1 or 'list=' in url:
            modal = PlaylistSelectionModal(title, entries, parent=self)
            if modal.exec() != QDialog.Accepted:
                self.log("[!] Playlist curation cancelled by user.")
                self.status_lbl.setText("Status: Cancelled")
                self.start_btn.setEnabled(True)
                return
            entries = modal.get_selected_entries()
            if not entries:
                InfoBar.warning("No Videos Selected", "Please select at least one video from the playlist.", duration=-1, parent=self)
                self.status_lbl.setText("Status: Cancelled")
                self.start_btn.setEnabled(True)
                return

        # Prepare task data
        subfolder = os.path.join(config.get("output_dir", os.getcwd()), "YouTube")
        os.makedirs(subfolder, exist_ok=True)
        output_file = config.get("output_file", "Thafreeg_Transcription.txt")
        name, ext = os.path.splitext(output_file)
        full_out_path = os.path.join(subfolder, f"{name}{ext}")

        task_data = {
            "entries": entries,
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

        t_id = None
        main_win = self.window()
        if hasattr(main_win, 'add_task_to_queue'):
            t_id = main_win.add_task_to_queue("youtube", {"title": title, "url": url})

        t_id = t_id or f"yt_{int(time.time() * 1000)}"
        task = Task(t_id, "YT", title, task_data)

        # Create worker thread
        self.worker = TaskWorker(task, self)
        self.worker.progress_changed.connect(self._on_progress_changed)
        self.worker.log_added.connect(self._on_log_added)
        self.worker.task_finished.connect(self._on_task_finished)
        self.worker.task_failed.connect(self._on_task_failed)

        self.status_lbl.setText(f"Status: Processing '{title}'...")
        self.worker.start()

    def _on_progress_changed(self, task_id, fraction, eta_text):
        percent = int(fraction * 100)
        self.progress_bar.setVal(percent)
        self.status_lbl.setText(f"Processing ({percent}%) | {eta_text}")
        main_win = self.window()
        if hasattr(main_win, 'update_global_progress'):
            main_win.update_global_progress("YouTube Harvest", fraction, eta_text)
        if hasattr(main_win, 'right_sidebar'):
            main_win.right_sidebar.update_card_progress(task_id, "processing", fraction)

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
        if hasattr(main_win, 'right_sidebar'):
            main_win.right_sidebar.update_card_progress(task_id, "completed", 1.0)

        # Update lifetime stats
        cfg = load_config()
        cfg["stats_yt_count"] = cfg.get("stats_yt_count", 0) + stats_delta.get("yt_count", 0)
        cfg["stats_yt_sec"] = cfg.get("stats_yt_sec", 0) + stats_delta.get("yt_sec", 0)
        cfg["stats_total_words"] = cfg.get("stats_total_words", 0) + stats_delta.get("words", 0)
        save_config(cfg)

        # Refresh sidebar stats
        if hasattr(main_win, 'refresh_stats'):
            main_win.refresh_stats()

        InfoBar.success("YouTube Task Complete", "YouTube processing finished successfully.", parent=self)

    def _on_task_failed(self, task_id, err_msg):
        self.status_lbl.setText("Status: Failed")
        self.start_btn.setEnabled(True)
        main_win = self.window()
        if hasattr(main_win, 'reset_global_task'):
            main_win.reset_global_task("Failed")
        if hasattr(main_win, 'right_sidebar'):
            main_win.right_sidebar.update_card_progress(task_id, "failed", 0.0)
        InfoBar.error("Task Failed", f"YouTube task error: {err_msg}", duration=-1, parent=self)
