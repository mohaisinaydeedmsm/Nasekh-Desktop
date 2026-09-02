from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from qfluentwidgets import CardWidget, CaptionLabel, BodyLabel

from core.utils import format_duration
from core.config_manager import load_config

class StatsWidget(CardWidget):
    """Custom Suite Stats card widget displayed in the navigation sidebar."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("stats_widget")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)
        
        # Header Label
        hdr = CaptionLabel("SUITE STATS", self)
        hdr.setStyleSheet("font-weight: bold; color: #888888; font-size: 10px;")
        layout.addWidget(hdr)
        
        # Stat 1: YouTube
        self.lbl_yt = QLabel("0 (0m)", self)
        self.lbl_yt.setStyleSheet("font-size: 15px; font-weight: bold; color: #FF4E4E;")
        layout.addWidget(self.lbl_yt)
        lbl_yt_desc = CaptionLabel("YouTube Videos", self)
        lbl_yt_desc.setStyleSheet("font-size: 10px; color: #aaaaaa;")
        layout.addWidget(lbl_yt_desc)
        
        # Stat 2: Local Audio
        self.lbl_audio = QLabel("0 (0m)", self)
        self.lbl_audio.setStyleSheet("font-size: 15px; font-weight: bold; color: #34A853;")
        layout.addWidget(self.lbl_audio)
        lbl_audio_desc = CaptionLabel("Audio Files", self)
        lbl_audio_desc.setStyleSheet("font-size: 10px; color: #aaaaaa;")
        layout.addWidget(lbl_audio_desc)

        # Stat 3: Telegram
        self.lbl_tg = QLabel("0 (0m)", self)
        self.lbl_tg.setStyleSheet("font-size: 15px; font-weight: bold; color: #1A73E8;")
        layout.addWidget(self.lbl_tg)
        lbl_tg_desc = CaptionLabel("Telegram Files", self)
        lbl_tg_desc.setStyleSheet("font-size: 10px; color: #aaaaaa;")
        layout.addWidget(lbl_tg_desc)

        # Stat 4: Vision OCR
        self.lbl_ocr = QLabel("0", self)
        self.lbl_ocr.setStyleSheet("font-size: 15px; font-weight: bold; color: #FF6B00;")
        layout.addWidget(self.lbl_ocr)
        lbl_ocr_desc = CaptionLabel("OCR Pages Scanned", self)
        lbl_ocr_desc.setStyleSheet("font-size: 10px; color: #aaaaaa;")
        layout.addWidget(lbl_ocr_desc)

        # Stat 5: Words Output
        self.lbl_words = QLabel("0", self)
        self.lbl_words.setStyleSheet("font-size: 15px; font-weight: bold; color: #A066FF;")
        layout.addWidget(self.lbl_words)
        lbl_words_desc = CaptionLabel("Total Words Output", self)
        lbl_words_desc.setStyleSheet("font-size: 10px; color: #aaaaaa;")
        layout.addWidget(lbl_words_desc)

        self.refresh_stats()

    def refresh_stats(self, config=None):
        if config is None:
            config = load_config()

        yt_count = config.get("stats_yt_count", 0)
        yt_sec = config.get("stats_yt_sec", 0)
        audio_count = config.get("stats_local_count", 0)
        audio_sec = config.get("stats_local_sec", 0)
        tg_count = config.get("stats_tg_count", 0)
        tg_sec = config.get("stats_tg_sec", 0)
        ocr_pages = config.get("stats_ocr_pages", 0)
        total_words = config.get("stats_total_words", 0)

        self.lbl_yt.setText(f"{yt_count} {format_duration(yt_sec)}")
        self.lbl_audio.setText(f"{audio_count} {format_duration(audio_sec)}")
        self.lbl_tg.setText(f"{tg_count} {format_duration(tg_sec)}")
        self.lbl_ocr.setText(f"{ocr_pages}")
        self.lbl_words.setText(f"{total_words:,}")
