import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from qfluentwidgets import (
    ScrollArea,
    SubtitleLabel,
    CaptionLabel,
    CardWidget,
    PrimaryPushButton,
    IconWidget,
    FluentIcon as FIF,
    isDarkTheme
)

from core.utils import resource_path

class HomeActionCard(CardWidget):
    """Interactive Fluent Action Card linking to a feature module."""
    def __init__(self, icon, title, description, button_text, on_click, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("home_action_card")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Row (Icon + Title)
        hdr_row = QHBoxLayout()
        icon_w = IconWidget(icon, self)
        icon_w.setFixedSize(32, 32)
        title_lbl = SubtitleLabel(title, self)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")

        hdr_row.addWidget(icon_w)
        hdr_row.addSpacing(10)
        hdr_row.addWidget(title_lbl)
        hdr_row.addStretch(1)
        layout.addLayout(hdr_row)

        # Description Label
        desc_lbl = CaptionLabel(description, self)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 12px; color: #888888; min-height: 38px;")
        layout.addWidget(desc_lbl)

        # Action Button
        btn = PrimaryPushButton(button_text, self)
        btn.clicked.connect(on_click)
        layout.addWidget(btn, 0, Qt.AlignRight)

class HomeTab(ScrollArea):
    """Welcoming Home Landing Tab UI with horizontal hero banner and interactive action cards."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("home_tab")
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.container = QWidget(self)
        self.container.setObjectName("home_container")
        self.container.setStyleSheet("QWidget#home_container { background: transparent; }")
        self.setWidget(self.container)

        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(28, 24, 28, 28)
        main_layout.setSpacing(24)

        # Welcome Header Hero Banner (Horizontal Layout)
        banner_card = CardWidget(self.container)
        banner_layout = QHBoxLayout(banner_card)
        banner_layout.setContentsMargins(28, 24, 28, 24)
        banner_layout.setSpacing(20)

        # Left Text Container
        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)
        welcome_title = SubtitleLabel("Welcome to Thafreeg Suite", banner_card)
        welcome_title.setStyleSheet("font-size: 22px; font-weight: bold;")
        welcome_sub = CaptionLabel(
            "Unified AI Multimedia Transcription, Groq Vision OCR & Telegram Harvester", banner_card
        )
        welcome_sub.setStyleSheet("font-size: 13px; color: #888888;")
        text_layout.addWidget(welcome_title)
        text_layout.addWidget(welcome_sub)
        banner_layout.addLayout(text_layout, 1)

        # Right Hero Branding Logo Graphic
        self.hero_logo = QLabel(banner_card)
        self.hero_logo.setFixedSize(72, 72)
        self.update_hero_logo()
        banner_layout.addWidget(self.hero_logo)

        main_layout.addWidget(banner_card)

        # Module Cards Grid (2x2)
        grid_layout = QGridLayout()
        grid_layout.setSpacing(16)

        # Card 1: YouTube Harvest
        card_yt = HomeActionCard(
            FIF.VIDEO,
            "YouTube Harvest",
            "Extract & transcribe single videos or complete playlists from YouTube automatically.",
            "Open YouTube Harvest",
            self._nav_to_youtube,
            self.container
        )
        grid_layout.addWidget(card_yt, 0, 0)

        # Card 2: Local Audio Batch
        card_audio = HomeActionCard(
            FIF.MUSIC,
            "Local Audio Batch",
            "Transcribe batches of local audio files (MP3, M4A, WAV) using Groq Whisper API.",
            "Open Audio Batch",
            self._nav_to_audio,
            self.container
        )
        grid_layout.addWidget(card_audio, 0, 1)

        # Card 3: Telegram Harvester
        card_tg = HomeActionCard(
            FIF.CHAT,
            "Telegram Harvester",
            "Harvest and transcribe audio/video posts directly from Telegram channels.",
            "Open Telegram Harvester",
            self._nav_to_telegram,
            self.container
        )
        grid_layout.addWidget(card_tg, 1, 0)

        # Card 4: Vision OCR Scan
        card_ocr = HomeActionCard(
            FIF.VIEW,
            "Vision OCR Scan",
            "Scan manuscript images and multi-page PDFs into structured text using Groq Vision API.",
            "Open Vision OCR",
            self._nav_to_vision,
            self.container
        )
        grid_layout.addWidget(card_ocr, 1, 1)

        main_layout.addLayout(grid_layout)
        main_layout.addStretch(1)

    def update_hero_logo(self):
        logo_file = "assets/logo_dark.png" if isDarkTheme() else "assets/logo_light.png"
        path = resource_path(logo_file)
        if not os.path.exists(path):
            path = resource_path("assets/icon.png")
        if os.path.exists(path):
            pix = QPixmap(path).scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.hero_logo.setPixmap(pix)

    def _nav_to_youtube(self):
        main_win = self.window()
        if hasattr(main_win, 'switchTo') and hasattr(main_win, 'youtube_tab'):
            main_win.switchTo(main_win.youtube_tab)

    def _nav_to_audio(self):
        main_win = self.window()
        if hasattr(main_win, 'switchTo') and hasattr(main_win, 'audio_tab'):
            main_win.switchTo(main_win.audio_tab)

    def _nav_to_telegram(self):
        main_win = self.window()
        if hasattr(main_win, 'switchTo') and hasattr(main_win, 'telegram_tab'):
            main_win.switchTo(main_win.telegram_tab)

    def _nav_to_vision(self):
        main_win = self.window()
        if hasattr(main_win, 'switchTo') and hasattr(main_win, 'vision_tab'):
            main_win.switchTo(main_win.vision_tab)
