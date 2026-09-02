import os
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSplitter, QSystemTrayIcon, QMenu, QApplication
from PySide6.QtCore import Qt, Slot
from qfluentwidgets import (
    FluentWindow,
    NavigationItemPosition,
    NavigationDisplayMode,
    TransparentToolButton,
    FluentIcon as FIF,
    setTheme,
    Theme,
    isDarkTheme,
    InfoBar,
    InfoBarPosition
)

from core.utils import resource_path
from core.config_manager import load_config, save_config
from core.task_manager import TaskManager
from core.windows_taskbar import WindowsTaskbar, TBPF_NORMAL, TBPF_NOPROGRESS
from ui.stats_widget import StatsWidget
from ui.right_sidebar import RightSidebar
from ui.tabs import (
    HomeTab,
    YouTubeTab,
    AudioTab,
    TelegramTab,
    VisionTab,
    SettingsTab
)

class NavigationHeader(QWidget):
    """Proportional sidebar header displaying the branding logo graphic cleanly."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setFixedHeight(65)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(0)

        # Single QLabel dedicated solely to displaying the logo image
        self.logo_lbl = QLabel(self)
        self.logo_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.logo_lbl)

        self.update_logo(is_expanded=True)

    def update_logo(self, is_expanded=True):
        logo_file = "assets/logo_dark.png" if isDarkTheme() else "assets/logo_light.png"
        path = resource_path(logo_file)
        if not os.path.exists(path):
            path = resource_path("assets/icon.png")
        if os.path.exists(path):
            w = 210 if is_expanded else 36
            h = 55 if is_expanded else 36
            pix = QPixmap(path).scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_lbl.setPixmap(pix)

    def set_title_visible(self, visible):
        self.update_logo(is_expanded=visible)

class MainWindow(FluentWindow):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        # Clear default window title text to prevent double-text overlap in titleBar
        self.setWindowTitle("")
        self.resize(1360, 880)
        self.setMinimumSize(1050, 720)

        # Apply configured theme
        config = load_config()
        theme_setting = config.get("theme", "Auto")
        self.apply_initial_theme(theme_setting)

        # Set Window Icon using assets/icon.png (fallback logo_light.png)
        icon_path = resource_path("assets/icon.png")
        if not os.path.exists(icon_path):
            icon_path = resource_path("assets/logo_light.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Create sub-interface route widgets
        self.home_tab = HomeTab(self)
        self.youtube_tab = YouTubeTab(self)
        self.audio_tab = AudioTab(self)
        self.telegram_tab = TelegramTab(self)
        self.vision_tab = VisionTab(self)
        self.settings_tab = SettingsTab(self)

        self.init_navigation()

        # Initialize global task manager and load queue state
        self.task_manager = TaskManager()
        self.task_manager.load_queue()

        # Wire up RightSidebar Clear Completed signal
        self.right_sidebar.clear_completed_requested.connect(self.clear_completed_tasks)
        self.refresh_queue_ui()

        # Initialize Windows Taskbar progress integration
        self._force_quit = False
        self.windows_taskbar = WindowsTaskbar()

        # Setup System Tray Integration
        self.setup_system_tray()

        # Silver Bullet: Force TitleBar to absolute top of Z-index stack
        self.titleBar.raise_()

    def refresh_queue_ui(self):
        """Refreshes the right sidebar interactive task cards."""
        if hasattr(self, 'right_sidebar') and hasattr(self, 'task_manager'):
            self.right_sidebar.refresh_queue_ui(self.task_manager.tasks, self.remove_task_from_queue)

    def add_task_to_queue(self, task_type, payload):
        """Adds a task to TaskManager and updates the UI card queue."""
        task_id = self.task_manager.add_task(task_type, payload)
        self.task_manager.save_queue()
        self.refresh_queue_ui()
        return task_id

    def remove_task_from_queue(self, task_id):
        """Removes a task from TaskManager and updates the UI card queue."""
        self.task_manager.remove_task(task_id)
        self.task_manager.save_queue()
        self.refresh_queue_ui()

    def clear_completed_tasks(self):
        """Clears completed, failed, and cancelled tasks from queue."""
        if hasattr(self, 'task_manager'):
            self.task_manager.tasks = [
                t for t in self.task_manager.tasks
                if t.status in ("pending", "processing")
            ]
            self.task_manager.save_queue()
            self.refresh_queue_ui()

    def apply_initial_theme(self, theme_setting):
        if theme_setting == "Dark":
            setTheme(Theme.DARK)
        elif theme_setting == "Light":
            setTheme(Theme.LIGHT)
        else:
            setTheme(Theme.AUTO)

    def init_navigation(self):
        # Insert Proportional Branding Header Widget at top of left sidebar
        self.nav_header = NavigationHeader(self)
        self.navigationInterface.panel.layout().insertWidget(0, self.nav_header)

        # Home Landing Page (Default Route)
        self.addSubInterface(
            self.home_tab,
            FIF.HOME,
            'Home'
        )

        # Sidebar navigation items
        self.addSubInterface(
            self.youtube_tab,
            FIF.VIDEO,
            'YouTube Harvest'
        )
        self.addSubInterface(
            self.audio_tab,
            FIF.MUSIC,
            'Local Audio Batch'
        )
        self.addSubInterface(
            self.telegram_tab,
            FIF.CHAT,
            'Telegram Harvester'
        )
        self.addSubInterface(
            self.vision_tab,
            FIF.VIEW,
            'Vision OCR'
        )

        # Dedicated "Toggle Console" Navigation Item at bottom (above Settings)
        self.navigationInterface.addItem(
            routeKey='toggle_console_item',
            icon=FIF.FEEDBACK,
            text='Toggle Console',
            onClick=self.toggle_right_sidebar,
            selectable=False,
            position=NavigationItemPosition.BOTTOM
        )

        # Settings tab anchored to bottom navigation position
        self.addSubInterface(
            self.settings_tab,
            FIF.SETTING,
            'Settings',
            position=NavigationItemPosition.BOTTOM
        )

        # Inject StatsWidget into bottom of left navigation panel
        self.stats_widget = StatsWidget(self)
        self.navigationInterface.panel.layout().insertWidget(3, self.stats_widget)

        # 2. Correct QSplitter Integration into self.hBoxLayout
        self.right_sidebar = RightSidebar(on_toggle=self.toggle_right_sidebar, parent=self)
        
        self.main_splitter = QSplitter(Qt.Horizontal, self)
        self.main_splitter.setHandleWidth(1)

        # Move stackedWidget into left side of splitter, and right_sidebar into right side
        self.hBoxLayout.removeWidget(self.stackedWidget)
        self.main_splitter.addWidget(self.stackedWidget)
        self.main_splitter.addWidget(self.right_sidebar)

        # Set 75% / 25% stretch factors
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([920, 320])

        self.hBoxLayout.addWidget(self.main_splitter, 1)

        # Load saved sidebar visibility preference
        config = load_config()
        show_right = config.get("show_right_sidebar", True)
        self.right_sidebar.setVisible(show_right)

        # Handle display mode changes (collapse/expand header & stats widget)
        self.navigationInterface.displayModeChanged.connect(self._on_display_mode_changed)

    def _on_display_mode_changed(self, mode):
        is_expanded = mode in (NavigationDisplayMode.EXPAND, NavigationDisplayMode.MENU)
        self.nav_header.set_title_visible(is_expanded)
        self.stats_widget.setVisible(is_expanded)

    def toggle_right_sidebar(self):
        """Toggles visibility of the right log panel and persists state to config.json."""
        is_visible = not self.right_sidebar.isVisible()
        self.right_sidebar.setVisible(is_visible)
        cfg = load_config()
        cfg["show_right_sidebar"] = is_visible
        save_config(cfg)

    def log_global(self, text):
        """Streams log messages to the persistent right sidebar."""
        self.right_sidebar.append_log(text)

    def update_global_progress(self, task_name, fraction, eta_text):
        """Updates active task progress on the right sidebar and taskbar icon."""
        self.right_sidebar.update_task_progress(task_name, fraction, eta_text)
        if hasattr(self, 'windows_taskbar'):
            current = int(fraction * 100)
            hwnd = int(self.winId())
            if 0 < current < 100:
                self.windows_taskbar.set_progress_state(hwnd, TBPF_NORMAL)
                self.windows_taskbar.set_progress_value(hwnd, current, 100)
            elif current >= 100:
                self.windows_taskbar.set_progress_state(hwnd, TBPF_NOPROGRESS)

    def reset_global_task(self, status_msg="Idle"):
        """Resets right sidebar active task status and taskbar progress."""
        self.right_sidebar.reset_task(status_msg)
        if hasattr(self, 'windows_taskbar'):
            self.windows_taskbar.set_progress_state(int(self.winId()), TBPF_NOPROGRESS)

    def refresh_stats(self):
        """Refreshes the sidebar suite stats card."""
        if hasattr(self, 'stats_widget'):
            self.stats_widget.refresh_stats()

    def update_theme_logos(self):
        """Refreshes dynamic theme logos across window."""
        if hasattr(self, 'nav_header'):
            is_expanded = self.navigationInterface.isExpanded if hasattr(self.navigationInterface, 'isExpanded') else True
            self.nav_header.update_logo(is_expanded=is_expanded)
        if hasattr(self, 'home_tab') and hasattr(self.home_tab, 'update_hero_logo'):
            self.home_tab.update_hero_logo()

    @Slot(str, str)
    def show_unhandled_error(self, summary, details):
        """Displays a persistent fluent InfoBar.error toast (duration=-1 for manual dismissal)."""
        InfoBar.error(
            title="Unhandled Application Exception",
            content=summary,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=-1,
            parent=self
        )

    def setup_system_tray(self):
        """Initializes native system tray icon and context menu."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon_path = resource_path("assets/icon.png")
        if not os.path.exists(icon_path):
            icon_path = resource_path("assets/logo_light.png")

        self.tray_icon = QSystemTrayIcon(self)
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))

        tray_menu = QMenu(self)
        restore_action = tray_menu.addAction("Restore App")
        restore_action.triggered.connect(self.restore_from_tray)

        tray_menu.addSeparator()

        quit_action = tray_menu.addAction("Quit Thafreeg Suite")
        quit_action.triggered.connect(self.force_quit_app)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)
        self.tray_icon.show()

    def restore_from_tray(self):
        self.showNormal()
        self.activateWindow()

    def force_quit_app(self):
        self._force_quit = True
        if hasattr(self, 'task_manager'):
            self.task_manager.save_queue()
        QApplication.quit()

    def _on_tray_icon_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.restore_from_tray()

    def closeEvent(self, event):
        """Minimize to System Tray on window close unless explicitly quitting."""
        if getattr(self, '_force_quit', False):
            if hasattr(self, 'task_manager'):
                self.task_manager.save_queue()
            event.accept()
        else:
            event.ignore()
            self.hide()
            if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    "Thafreeg Suite",
                    "Thafreeg Suite is still running in the background.",
                    QSystemTrayIcon.Information,
                    2000
                )

