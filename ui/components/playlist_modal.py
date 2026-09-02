import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QCheckBox
)
from PySide6.QtCore import Qt
from qfluentwidgets import (
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    PushButton,
    PrimaryPushButton,
    CardWidget
)

from core.utils import format_duration

class PlaylistSelectionModal(QDialog):
    """Fluent Dialog for selecting/curating YouTube playlist videos before queueing."""
    def __init__(self, playlist_title, entries, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle("YouTube Playlist Curation")
        self.setMinimumSize(560, 480)
        self.resize(600, 520)

        self.entries = entries
        self.selected_entries = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        title_lbl = SubtitleLabel(f"Playlist: {playlist_title}", self)
        subtitle_lbl = CaptionLabel(f"Select videos to queue ({len(entries)} items found):", self)
        layout.addWidget(title_lbl)
        layout.addWidget(subtitle_lbl)

        # Selection Control Buttons Bar
        ctrl_bar = QHBoxLayout()
        self.select_all_btn = PushButton("Select All", self)
        self.select_all_btn.clicked.connect(self.select_all)

        self.deselect_all_btn = PushButton("Deselect All", self)
        self.deselect_all_btn.clicked.connect(self.deselect_all)

        ctrl_bar.addWidget(self.select_all_btn)
        ctrl_bar.addWidget(self.deselect_all_btn)
        ctrl_bar.addStretch(1)
        layout.addLayout(ctrl_bar)

        # Video Checklist ListWidget
        self.list_widget = QListWidget(self)
        self.list_widget.setStyleSheet(
            "QListWidget { border: 1px solid #E5E5E5; border-radius: 8px; background: transparent; padding: 4px; }"
            "QListWidget::item { padding: 6px; border-bottom: 1px solid #F0F0F0; }"
        )

        for entry in self.entries:
            title = entry.get("title", "Untitled Video")
            dur = entry.get("duration", 0)
            dur_str = format_duration(dur) if dur else ""
            display_text = f"{title} {dur_str}".strip()

            item = QListWidgetItem(display_text, self.list_widget)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, entry)

        layout.addWidget(self.list_widget, 1)

        # Action Button Row
        btn_row = QHBoxLayout()
        self.queue_btn = PrimaryPushButton("Queue Selected", self)
        self.queue_btn.clicked.connect(self.on_accept)

        self.cancel_btn = PushButton("Cancel", self)
        self.cancel_btn.clicked.connect(self.reject)

        btn_row.addStretch(1)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.queue_btn)
        layout.addLayout(btn_row)

    def select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Checked)

    def deselect_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Unchecked)

    def on_accept(self):
        self.selected_entries = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                entry = item.data(Qt.UserRole)
                if entry:
                    self.selected_entries.append(entry)
        self.accept()

    def get_selected_entries(self):
        return self.selected_entries
