import time
from PySide6.QtCore import QThread, Signal

from core.utils import Task, TaskStatus
from core.yt_engine import run_youtube_pipeline
from core.whisper_engine import run_local_pipeline
from core.vision_engine import run_vision_pipeline
from core.telegram_engine import run_telegram_pipeline

class TaskWorker(QThread):
    """Thread-safe background execution worker for Thafreeg backend tasks."""

    progress_changed = Signal(str, float, str)  # (task_id, progress_fraction, eta_text)
    log_added = Signal(str, str)               # (task_id, log_text)
    task_finished = Signal(str, dict)          # (task_id, stats_delta_dict)
    task_failed = Signal(str, str)             # (task_id, error_message)

    def __init__(self, task: Task, parent=None):
        super().__init__(parent=parent)
        self.task = task
        self.stats_delta = {
            "yt_count": 0, "yt_sec": 0,
            "local_count": 0, "local_sec": 0,
            "tg_count": 0, "tg_sec": 0,
            "ocr_pages": 0, "words": 0
        }

        # Wire pure-Python Task callbacks to QThread Signals
        self.task.log_callback = self._on_log
        self.task.status_callback = self._on_status_change
        self.task.analytics_callback = self._on_analytics

    def _on_log(self, text):
        self.log_added.emit(self.task.id, str(text))

    def _on_status_change(self, task):
        self.progress_changed.emit(task.id, task.progress_fraction, task.eta_text)

    def _on_analytics(self, **kwargs):
        for k, v in kwargs.items():
            if k in self.stats_delta:
                self.stats_delta[k] += v

    def run(self):
        self.task.start_time = self.task.start_time or time.time()
        self.task._update_status(TaskStatus.RUNNING)

        try:
            task_type = self.task.type.upper()
            if task_type == 'YT':
                run_youtube_pipeline(self.task)
            elif task_type == 'LOCAL':
                run_local_pipeline(self.task)
            elif task_type == 'VISION':
                run_vision_pipeline(self.task)
            elif task_type == 'TG':
                run_telegram_pipeline(self.task)
            else:
                raise ValueError(f"Unknown task type: {self.task.type}")

            if self.task.status != TaskStatus.CANCELLED:
                self.task._update_status(TaskStatus.COMPLETED)
                self.task_finished.emit(self.task.id, self.stats_delta)
        except Exception as e:
            err_msg = str(e)
            if "Cancelled" in err_msg:
                self.task._update_status(TaskStatus.CANCELLED)
                self.log_added.emit(self.task.id, "[!] Task Cancelled by user.")
            else:
                self.task.error_message = err_msg
                self.task._update_status(TaskStatus.FAILED)
                self.log_added.emit(self.task.id, f"[!] Task Exception: {err_msg}")
                self.task_failed.emit(self.task.id, err_msg)
