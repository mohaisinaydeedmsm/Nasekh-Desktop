import os
import sys
import re
import time
import asyncio
import threading
import subprocess
import docx

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_path, relative_path)

def get_cookie_opts():
    return {'cookiefile': 'cookies.txt'} if os.path.exists("cookies.txt") else {'cookiesfrombrowser': ('chrome', )}

def get_media_duration_sec(filepath):
    """Accurately probes media duration using ffprobe."""
    if not os.path.exists(filepath):
        return 0
    try:
        cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', filepath
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             creationflags=0x08000000 if os.name == 'nt' else 0)
        return float(res.stdout.strip())
    except Exception:
        return 0

def format_duration(seconds):
    """Formats seconds into readable string e.g. (2h 15m) or (45m)."""
    seconds = int(seconds)
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    if hrs > 0:
        return f"({hrs}h {mins:02d}m)"
    return f"({mins}m)"

def run_exporters(txt_path, do_docx, do_md, log_func=None):
    if not os.path.exists(txt_path):
        return
    with open(txt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    base = os.path.splitext(txt_path)[0]
    if do_md:
        try:
            with open(base + ".md", 'w', encoding='utf-8') as f:
                f.write(content)
            if log_func:
                log_func("    -> Exported: Markdown (.md)")
        except Exception:
            pass
    if do_docx:
        try:
            doc = docx.Document()
            doc.add_paragraph(content)
            doc.save(base + ".docx")
            if log_func:
                log_func("    -> Exported: Word (.docx)")
        except Exception as e:
            if log_func:
                log_func(f"    [!] Docx export failed: {e}")

def clean_vtt(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    content = re.sub(r'WEBVTT.*?\n', '', content)
    content = re.sub(r'Kind:.*?\n', '', content)
    content = re.sub(r'Language:.*?\n', '', content)
    content = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*\n', '', content)
    content = re.sub(r'<[^>]+>', '', content)
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    clean_lines = []
    for line in lines:
        if not clean_lines or clean_lines[-1] != line:
            clean_lines.append(line)
    return " ".join(clean_lines)

def generate_subtitles(segments, base_filename, output_dir, chunk_index):
    if not segments:
        return
    name_only = os.path.splitext(os.path.basename(base_filename))[0]
    srt_path = os.path.join(output_dir, f"{name_only}.srt")
    vtt_path = os.path.join(output_dir, f"{name_only}.vtt")

    def format_time(seconds, vtt=False):
        hrs, mins, secs = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
        msecs, sep = int((seconds - int(seconds)) * 1000), "." if vtt else ","
        return f"{hrs:02}:{mins:02}:{secs:02}{sep}{msecs:03}"

    offset = chunk_index * 3600
    with open(srt_path, 'a', encoding='utf-8') as f_srt, open(vtt_path, 'a', encoding='utf-8') as f_vtt:
        if chunk_index == 0 and (not os.path.exists(vtt_path) or os.path.getsize(vtt_path) == 0):
            f_vtt.write("WEBVTT\n\n")
        line_count = sum(1 for line in open(srt_path, 'r', encoding='utf-8') if '-->' in line) if os.path.exists(srt_path) else 0

        for i, seg in enumerate(segments, start=line_count + 1):
            start, end = format_time(seg.get('start', 0) + offset), format_time(seg.get('end', 0) + offset)
            start_vtt, end_vtt = format_time(seg.get('start', 0) + offset, True), format_time(seg.get('end', 0) + offset, True)
            text = seg.get('text', '').strip()
            f_srt.write(f"{i}\n{start} --> {end}\n{text}\n\n")
            f_vtt.write(f"{start_vtt} --> {end_vtt}\n{text}\n\n")

def build_ffmpeg_cmd(input_file, config):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-f', 'segment', '-segment_time', '3600', '-c:a', 'libmp3lame', '-b:a', '32k', '-ac', '1', '-ar', '16000']
    if config.get('noise_reduction', False):
        cmd.extend(['-af', 'afftdn'])
    cmd.extend(['-vn', 'chunk_%03d.mp3'])
    return cmd

# =========================================================
# LOGGING & BACKEND STATE HELPERS
# =========================================================
def log_task(task, text):
    """Unified backend task logging helper."""
    if task and hasattr(task, 'log_callback') and callable(task.log_callback):
        try:
            task.log_callback(text)
            return
        except Exception:
            pass
    print(text)

def update_task_key_status(task, text, color_code="green"):
    """Notifies key status callback if provided on task."""
    if task and hasattr(task, 'key_status_callback') and callable(task.key_status_callback):
        try:
            task.key_status_callback(text, color_code)
        except Exception:
            pass

def update_task_analytics(task, **kwargs):
    """Notifies analytics callback if provided on task."""
    if task and hasattr(task, 'analytics_callback') and callable(task.analytics_callback):
        try:
            task.analytics_callback(**kwargs)
        except Exception:
            pass

# =========================================================
# PURE-PYTHON TASK ABSTRACTIONS
# =========================================================
class TaskStatus:
    QUEUED = "Queued"
    RUNNING = "Processing..."
    PAUSED = "Paused"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"

class Task:
    """Strictly pure-Python data model representing a background processing task."""
    def __init__(self, t_id, t_type, t_name, data, log_callback=None, status_callback=None, key_status_callback=None, analytics_callback=None):
        self.id = str(t_id)
        self.type = str(t_type)
        self.name = str(t_name)
        self.data = data if isinstance(data, dict) else {}

        self.status = TaskStatus.QUEUED
        self.progress_fraction = 0.0
        self.eta_text = "ETA: --:--"
        self.start_time = None
        self.error_message = None

        self.log_callback = log_callback
        self.status_callback = status_callback
        self.key_status_callback = key_status_callback
        self.analytics_callback = analytics_callback

        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancel_flag = False

    def check_state(self):
        """ Blocking check for paused/cancelled states """
        if self._cancel_flag:
            raise Exception("Task Cancelled by User")
        if not self._pause_event.is_set():
            log_task(self, f"⏸ Task Paused: {self.name}")
            self._update_status(TaskStatus.PAUSED)
            self._pause_event.wait()
            if self._cancel_flag:
                raise Exception("Task Cancelled by User")
            log_task(self, f"▶ Task Resumed: {self.name}")
            self._update_status(TaskStatus.RUNNING)
            self.start_time = time.time() - (self.progress_fraction * 100)

    async def async_check_state(self):
        while not self._pause_event.is_set():
            if self._cancel_flag:
                raise Exception("Task Cancelled by User")
            await asyncio.sleep(0.5)
        if self._cancel_flag:
            raise Exception("Task Cancelled by User")

    def update_progress(self, fraction):
        self.progress_fraction = min(1.0, max(0.0, float(fraction)))
        if self.progress_fraction > 0 and self.start_time:
            elapsed = time.time() - self.start_time
            total_est = elapsed / self.progress_fraction
            eta_seconds = int(total_est - elapsed)
            mins, secs = divmod(max(0, eta_seconds), 60)
            self.eta_text = f"ETA: {mins}m {secs}s" if self.progress_fraction < 1.0 else "Done"

        if callable(self.status_callback):
            try:
                self.status_callback(self)
            except Exception:
                pass

    def _update_status(self, new_status):
        self.status = new_status
        if callable(self.status_callback):
            try:
                self.status_callback(self)
            except Exception:
                pass

    def log(self, msg):
        log_task(self, msg)

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def cancel(self):
        self._cancel_flag = True
        self._pause_event.set()
        self._update_status(TaskStatus.CANCELLED)
