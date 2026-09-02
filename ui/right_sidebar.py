from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel
)
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import (
    CardWidget,
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    TextEdit,
    ProgressBar,
    PushButton,
    TransparentToolButton,
    FluentIcon as FIF,
    SingleDirectionScrollArea
)

class StatusBadge(QLabel):
    """Custom styled status tag/pill badge."""
    def __init__(self, status="pending", parent=None):
        super().__init__(parent=parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_status(status)

    def set_status(self, status):
        status = str(status).lower()
        styles = {
            "pending": ("Pending", "background-color: #0078D4; color: white;"),
            "processing": ("Processing", "background-color: #107C41; color: white;"),
            "completed": ("Completed", "background-color: #6B69D6; color: white;"),
            "failed": ("Failed", "background-color: #D13438; color: white;"),
            "cancelled": ("Cancelled", "background-color: #797775; color: white;")
        }
        text, style = styles.get(status, (status.capitalize(), "background-color: #8A8886; color: white;"))
        self.setText(f" {text} ")
        self.setStyleSheet(f"border-radius: 10px; font-size: 10px; font-weight: bold; padding: 2px 8px; {style}")

class TaskCardWidget(CardWidget):
    """Interactive Card representing a single Task item in the queue."""
    cancel_requested = Signal(str)  # task_id

    def __init__(self, task_item, parent=None):
        super().__init__(parent=parent)
        self.task_id = task_item.task_id
        self.task_type = task_item.task_type
        self.payload = task_item.payload or {}
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Header Row: Icon + Title + Status + Action
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        icon_map = {
            "youtube": FIF.VIDEO,
            "yt": FIF.VIDEO,
            "audio": FIF.MUSIC,
            "local": FIF.MUSIC,
            "vision": FIF.VIEW,
            "telegram": FIF.CHAT,
            "tg": FIF.CHAT
        }
        icon_type = icon_map.get(self.task_type.lower(), FIF.APPLICATION)
        self.icon_btn = TransparentToolButton(icon_type, self)
        self.icon_btn.setFixedSize(24, 24)

        title_text = self.payload.get("title") or self.payload.get("name") or f"{self.task_type.upper()} Task"
        if len(title_text) > 20:
            title_text = title_text[:18] + "..."

        self.title_lbl = BodyLabel(title_text, self)
        self.title_lbl.setStyleSheet("font-weight: bold; font-size: 12px;")

        self.badge = StatusBadge(task_item.status, self)

        self.cancel_btn = TransparentToolButton(FIF.DELETE, self)
        self.cancel_btn.setToolTip("Cancel & Remove Task")
        self.cancel_btn.setFixedSize(24, 24)
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.task_id))

        hdr.addWidget(self.icon_btn)
        hdr.addWidget(self.title_lbl, 1)
        hdr.addWidget(self.badge)
        hdr.addWidget(self.cancel_btn)
        layout.addLayout(hdr)

        # Mini Progress Bar
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setVal(0)
        self.progress_bar.setFixedHeight(4)
        layout.addWidget(self.progress_bar)

    def update_state(self, status, progress_fraction=0.0):
        self.badge.set_status(status)
        val = int(progress_fraction * 100)
        self.progress_bar.setVal(val)


class RightSidebar(CardWidget):
    """Persistent Collapsible Right Sidebar Command Center."""
    clear_completed_requested = Signal()

    def __init__(self, on_toggle=None, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("right_sidebar")
        self.setMinimumWidth(280)

        # 40px Top margin to safely clear titleBar
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 40, 10, 10)
        layout.setSpacing(8)

        # Header Row (Collapse toggle button on LEFT, Title/Counter in middle, Clear button on RIGHT)
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        self.toggle_btn = TransparentToolButton(FIF.CHEVRON_RIGHT_MED, self)
        self.toggle_btn.setToolTip("Collapse Command Center")
        if on_toggle:
            self.toggle_btn.clicked.connect(on_toggle)

        self.queue_title = SubtitleLabel("Queue (0)", self)
        self.queue_title.setStyleSheet("font-size: 14px; font-weight: bold;")

        self.clear_btn = PushButton("Clear Completed", self)
        self.clear_btn.setStyleSheet("font-size: 11px;")
        self.clear_btn.clicked.connect(lambda: self.clear_completed_requested.emit())

        hdr.addWidget(self.toggle_btn)
        hdr.addWidget(self.queue_title, 1)
        hdr.addWidget(self.clear_btn)
        layout.addLayout(hdr)

        # Task Cards Scroll Area
        self.scroll_area = SingleDirectionScrollArea(self, orient=Qt.Vertical)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.card_container = QWidget()
        self.card_container.setStyleSheet("background: transparent;")
        self.card_layout = QVBoxLayout(self.card_container)
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(8)
        self.card_layout.addStretch(1)

        self.scroll_area.setWidget(self.card_container)
        layout.addWidget(self.scroll_area, 2)

        # Global Log Console
        log_hdr = CaptionLabel("GLOBAL LOG CONSOLE", self)
        log_hdr.setStyleSheet("font-weight: bold; color: #888888; font-size: 10px;")
        layout.addWidget(log_hdr)

        self.log_edit = TextEdit(self)
        self.log_edit.setReadOnly(True)
        layout.addWidget(self.log_edit, 1)

        self.cards_map = {}  # task_id -> TaskCardWidget

    def append_log(self, text):
        self.log_edit.append(str(text))
        sb = self.log_edit.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def clear_logs(self):
        self.log_edit.clear()

    def refresh_queue_ui(self, tasks, on_cancel_callback=None):
        self.queue_title.setText(f"Queue ({len(tasks)})")
        
        # Remove existing widgets from layout (except stretch)
        while self.card_layout.count() > 1:
            item = self.card_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        
        self.cards_map.clear()

        for t_item in tasks:
            card = TaskCardWidget(t_item, self.card_container)
            if on_cancel_callback:
                card.cancel_requested.connect(on_cancel_callback)
            self.cards_map[t_item.task_id] = card
            self.card_layout.insertWidget(self.card_layout.count() - 1, card)

    def update_card_progress(self, task_id, status, fraction):
        if task_id in self.cards_map:
            self.cards_map[task_id].update_state(status, fraction)

    def update_task_progress(self, task_name, fraction, eta_text):
        """Backward compatibility helper for progress signal updates."""
        val = int(fraction * 100)
        # Update active task card progress if present
        for card in self.cards_map.values():
            if card.badge.text().strip().lower() in ("processing", "pending"):
                card.update_state("processing", fraction)
                break

    def reset_task(self, status_msg="Idle"):
        """Backward compatibility helper for task reset."""
        pass
