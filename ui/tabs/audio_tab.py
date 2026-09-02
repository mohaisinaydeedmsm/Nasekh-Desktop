import os
import time
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog
from PySide6.QtCore import Qt
from qfluentwidgets import (
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    LineEdit,
    TextEdit,
    ProgressBar,
    PushButton,
    PrimaryPushButton,
    CardWidget,
    InfoBar
)

from core.config_manager import load_config, save_config
from core.utils import Task
from core.task_worker import TaskWorker

class AudioTab(QWidget):
    """Local Audio Batch Tab UI with thread-safe TaskWorker execution and Drag & Drop."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("audio_tab")
        self.setAcceptDrops(True)
        self.worker = None
        self.selected_files = []

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        valid_exts = {'.mp3', '.m4a', '.wav', '.flac', '.ogg', '.aac', '.wma'}
        added_files = []
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath and os.path.exists(filepath):
                ext = os.path.splitext(filepath)[1].lower()
                if ext in valid_exts and filepath not in self.selected_files:
                    self.selected_files.append(filepath)
                    added_files.append(filepath)
        if added_files:
            self.update_files_display()
            InfoBar.success("Files Added", f"Added {len(added_files)} audio file(s) via Drag & Drop.", parent=self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # Header
        title = SubtitleLabel("Local Audio Batch", self)
        layout.addWidget(title)

        # Input Card
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        file_hdr = QHBoxLayout()
        lbl_files = BodyLabel("Selected Audio Files:", card)
        self.add_files_btn = PushButton("+ Add Audio Files", card)
        self.add_files_btn.clicked.connect(self.browse_audio_files)
        self.clear_files_btn = PushButton("Clear", card)
        self.clear_files_btn.clicked.connect(self.clear_files)

        file_hdr.addWidget(lbl_files)
        file_hdr.addStretch(1)
        file_hdr.addWidget(self.add_files_btn)
        file_hdr.addWidget(self.clear_files_btn)
        card_layout.addLayout(file_hdr)

        self.files_display = TextEdit(card)
        self.files_display.setReadOnly(True)
        self.files_display.setFixedHeight(75)
        self.files_display.setPlaceholderText("No audio files selected.")
        card_layout.addWidget(self.files_display)

        lbl_vocab = BodyLabel("Custom Vocabulary / Prompt:", card)
        self.vocab_entry = LineEdit(card)
        self.vocab_entry.setPlaceholderText("Optional e.g. names, terms, or domain vocab")
        card_layout.addWidget(lbl_vocab)
        card_layout.addWidget(self.vocab_entry)

        self.start_btn = PrimaryPushButton("Start Audio Processing", card)
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

    def browse_audio_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Audio Files", "", "Audio Files (*.mp3 *.m4a *.wav);;All Files (*.*)"
        )
        if files:
            for f in files:
                if f not in self.selected_files:
                    self.selected_files.append(f)
            self.update_files_display()

    def clear_files(self):
        self.selected_files.clear()
        self.update_files_display()

    def update_files_display(self):
        if self.selected_files:
            names = [os.path.basename(f) for f in self.selected_files]
            self.files_display.setPlainText("\n".join(names))
        else:
            self.files_display.setPlainText("")

    def start_processing(self):
        if not self.selected_files:
            InfoBar.warning("No Files Selected", "Please add at least one audio file.", duration=-1, parent=self)
            return

        config = load_config()
        api_keys = config.get("api_keys", [])
        if not api_keys:
            InfoBar.error("Missing API Keys", "Please add at least one Groq API Key in Settings.", duration=-1, parent=self)
            return

        vocab = self.vocab_entry.text().strip()
        files_to_process = list(self.selected_files)

        subfolder = os.path.join(config.get("output_dir", os.getcwd()), "Audio")
        os.makedirs(subfolder, exist_ok=True)
        output_file = config.get("output_file", "Thafreeg_Transcription.txt")
        name, ext = os.path.splitext(output_file)
        full_out_path = os.path.join(subfolder, f"{name}{ext}")

        task_data = {
            "entries": files_to_process,
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
        title = f"Local Audio ({len(files_to_process)} files)"
        if hasattr(main_win, 'add_task_to_queue'):
            t_id = main_win.add_task_to_queue("audio", {"title": title, "count": len(files_to_process)})

        t_id = t_id or f"local_{int(time.time() * 1000)}"
        task = Task(t_id, "LOCAL", title, task_data)

        self.start_btn.setEnabled(False)
        self.log(f"\n[+] Starting Local Audio Batch: {len(files_to_process)} file(s)...")

        self.worker = TaskWorker(task, self)
        self.worker.progress_changed.connect(self._on_progress_changed)
        self.worker.log_added.connect(self._on_log_added)
        self.worker.task_finished.connect(self._on_task_finished)
        self.worker.task_failed.connect(self._on_task_failed)

        self.status_lbl.setText("Status: Processing audio files...")
        self.worker.start()

    def _on_progress_changed(self, task_id, fraction, eta_text):
        percent = int(fraction * 100)
        self.progress_bar.setVal(percent)
        self.status_lbl.setText(f"Processing ({percent}%) | {eta_text}")
        main_win = self.window()
        if hasattr(main_win, 'update_global_progress'):
            main_win.update_global_progress("Local Audio Batch", fraction, eta_text)
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

        cfg = load_config()
        cfg["stats_local_count"] = cfg.get("stats_local_count", 0) + stats_delta.get("local_count", 0)
        cfg["stats_local_sec"] = cfg.get("stats_local_sec", 0) + stats_delta.get("local_sec", 0)
        cfg["stats_total_words"] = cfg.get("stats_total_words", 0) + stats_delta.get("words", 0)
        save_config(cfg)

        if hasattr(main_win, 'refresh_stats'):
            main_win.refresh_stats()

        InfoBar.success("Audio Processing Complete", "Audio batch completed successfully.", parent=self)

    def _on_task_failed(self, task_id, err_msg):
        self.status_lbl.setText("Status: Failed")
        self.start_btn.setEnabled(True)
        main_win = self.window()
        if hasattr(main_win, 'reset_global_task'):
            main_win.reset_global_task("Failed")
        if hasattr(main_win, 'right_sidebar'):
            main_win.right_sidebar.update_card_progress(task_id, "failed", 0.0)
        InfoBar.error("Task Failed", f"Audio task error: {err_msg}", duration=-1, parent=self)
