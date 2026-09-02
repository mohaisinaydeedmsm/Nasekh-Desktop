import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QInputDialog
from PySide6.QtCore import Qt
from qfluentwidgets import (
    ScrollArea,
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    LineEdit,
    TextEdit,
    SwitchButton,
    PushButton,
    PrimaryPushButton,
    ComboBox,
    CardWidget,
    InfoBar,
    InfoBarPosition,
    setTheme,
    Theme
)

from core.config_manager import load_config, save_config
from core.telegram_engine import request_telegram_otp, complete_telegram_otp

class SettingsTab(ScrollArea):
    """Full-featured Settings Tab respecting Dark/Light mode, theme switching & Telegram OTP authentication."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("settings_tab")
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        # Container widget inside scroll area
        self.container = QWidget(self)
        self.container.setObjectName("settings_container")
        self.container.setStyleSheet("QWidget#settings_container { background: transparent; }")
        self.setWidget(self.container)

        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setContentsMargins(24, 20, 24, 24)
        self.main_layout.setSpacing(16)

        # Header Title
        title = SubtitleLabel("Settings & Configuration", self.container)
        self.main_layout.addWidget(title)

        self.build_ui()
        self.load_settings()

    def build_ui(self):
        # Card 1: Appearance & Theme
        card_theme = CardWidget(self.container)
        theme_layout = QHBoxLayout(card_theme)
        theme_layout.setContentsMargins(16, 14, 16, 14)
        lbl_theme = BodyLabel("Application Theme Preference", card_theme)
        
        self.theme_combo = ComboBox(card_theme)
        self.theme_combo.addItems(["Auto", "Light", "Dark"])
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)

        theme_layout.addWidget(lbl_theme)
        theme_layout.addStretch(1)
        theme_layout.addWidget(self.theme_combo)
        self.main_layout.addWidget(card_theme)

        # Card 2: Groq API Keys (Explicit layout constraints)
        card_keys = CardWidget(self.container)
        keys_layout = QVBoxLayout(card_keys)
        keys_layout.setContentsMargins(16, 16, 16, 16)
        keys_layout.setSpacing(10)
        
        lbl_keys = BodyLabel("Groq API Keys (Paste 1 per line):", card_keys)
        keys_layout.addWidget(lbl_keys)
        
        self.keys_text = TextEdit(card_keys)
        self.keys_text.setPlaceholderText("gsk_12345abcdefg...\ngsk_67890hijklmn...")
        self.keys_text.setMinimumHeight(140)
        keys_layout.addWidget(self.keys_text)
        self.main_layout.addWidget(card_keys)

        # Card 3: Telegram API Credentials & OTP Verification
        card_tg = CardWidget(self.container)
        tg_layout = QVBoxLayout(card_tg)
        tg_layout.setContentsMargins(16, 16, 16, 16)
        tg_layout.setSpacing(10)

        tg_title = BodyLabel("Telegram API Credentials & Sign-In", card_tg)
        tg_layout.addWidget(tg_title)

        lbl_tg_id = CaptionLabel("API ID:", card_tg)
        self.tg_id_entry = LineEdit(card_tg)
        self.tg_id_entry.setPlaceholderText("e.g. 12345678")
        tg_layout.addWidget(lbl_tg_id)
        tg_layout.addWidget(self.tg_id_entry)

        lbl_tg_hash = CaptionLabel("API Hash:", card_tg)
        self.tg_hash_entry = LineEdit(card_tg)
        self.tg_hash_entry.setPlaceholderText("e.g. 0123456789abcdef0123456789abcdef")
        tg_layout.addWidget(lbl_tg_hash)
        tg_layout.addWidget(self.tg_hash_entry)

        lbl_tg_phone = CaptionLabel("Phone Number:", card_tg)
        self.tg_phone_entry = LineEdit(card_tg)
        self.tg_phone_entry.setPlaceholderText("e.g. +966500000000")
        tg_layout.addWidget(lbl_tg_phone)
        tg_layout.addWidget(self.tg_phone_entry)

        self.otp_btn = PushButton("Send Telegram OTP & Authenticate", card_tg)
        self.otp_btn.clicked.connect(self.authenticate_telegram)
        tg_layout.addWidget(self.otp_btn)

        self.main_layout.addWidget(card_tg)

        # Card 4: Output File & Path
        card_out = CardWidget(self.container)
        out_layout = QVBoxLayout(card_out)
        out_layout.setContentsMargins(16, 16, 16, 16)
        out_layout.setSpacing(10)

        out_title = BodyLabel("Output Folder & File Name", card_out)
        out_layout.addWidget(out_title)

        lbl_folder = CaptionLabel("Output Directory:", card_out)
        out_layout.addWidget(lbl_folder)
        
        dir_row = QHBoxLayout()
        self.dir_entry = LineEdit(card_out)
        self.browse_btn = PushButton("Browse", card_out)
        self.browse_btn.clicked.connect(self.browse_folder)
        dir_row.addWidget(self.dir_entry, 1)
        dir_row.addWidget(self.browse_btn)
        out_layout.addLayout(dir_row)

        lbl_file = CaptionLabel("Default Master Output File Name:", card_out)
        self.file_entry = LineEdit(card_out)
        out_layout.addWidget(lbl_file)
        out_layout.addWidget(self.file_entry)
        self.main_layout.addWidget(card_out)

        # Card 5: Advanced Module Toggles
        card_adv = CardWidget(self.container)
        adv_layout = QVBoxLayout(card_adv)
        adv_layout.setContentsMargins(16, 16, 16, 16)
        adv_layout.setSpacing(12)

        adv_title = BodyLabel("Advanced Modules & Exports", card_adv)
        adv_layout.addWidget(adv_title)

        # Noise reduction toggle
        noise_row = QHBoxLayout()
        lbl_noise = CaptionLabel("Enable FFmpeg Noise Reduction (afftdn)", card_adv)
        self.noise_switch = SwitchButton(card_adv)
        noise_row.addWidget(lbl_noise)
        noise_row.addStretch(1)
        noise_row.addWidget(self.noise_switch)
        adv_layout.addLayout(noise_row)

        # Docx export toggle
        docx_row = QHBoxLayout()
        lbl_docx = CaptionLabel("Auto-Export as Word Document (.docx)", card_adv)
        self.docx_switch = SwitchButton(card_adv)
        docx_row.addWidget(lbl_docx)
        docx_row.addStretch(1)
        docx_row.addWidget(self.docx_switch)
        adv_layout.addLayout(docx_row)

        # Markdown export toggle
        md_row = QHBoxLayout()
        lbl_md = CaptionLabel("Auto-Export as Markdown (.md)", card_adv)
        self.md_switch = SwitchButton(card_adv)
        md_row.addWidget(lbl_md)
        md_row.addStretch(1)
        md_row.addWidget(self.md_switch)
        adv_layout.addLayout(md_row)

        self.main_layout.addWidget(card_adv)

        # Action Buttons Row
        btn_row = QHBoxLayout()
        self.import_btn = PushButton("Import Config", self.container)
        self.import_btn.clicked.connect(self.import_config)
        
        self.save_btn = PrimaryPushButton("Save Settings", self.container)
        self.save_btn.clicked.connect(self.save_settings)

        btn_row.addWidget(self.import_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.save_btn)
        self.main_layout.addLayout(btn_row)

    def load_settings(self):
        config = load_config()
        api_keys = config.get("api_keys", [])
        self.keys_text.setPlainText("\n".join(api_keys))
        
        self.tg_id_entry.setText(str(config.get("tg_api_id", "")))
        self.tg_hash_entry.setText(str(config.get("tg_api_hash", "")))
        self.tg_phone_entry.setText(str(config.get("tg_phone", "")))
        self.dir_entry.setText(config.get("output_dir", os.getcwd()))
        self.file_entry.setText(config.get("output_file", "Thafreeg_Transcription.txt"))
        
        self.noise_switch.setChecked(config.get("noise_reduction", False))
        self.docx_switch.setChecked(config.get("export_docx", False))
        self.md_switch.setChecked(config.get("export_md", False))
        
        saved_theme = config.get("theme", "Auto")
        self.theme_combo.setCurrentText(saved_theme)
        self.apply_theme(saved_theme)

    def save_settings(self):
        raw_keys = self.keys_text.toPlainText().strip()
        api_keys = [k.strip() for k in raw_keys.split("\n") if k.strip()] if raw_keys else []

        selected_theme = self.theme_combo.currentText()
        config_data = {
            "api_keys": api_keys,
            "tg_api_id": self.tg_id_entry.text().strip(),
            "tg_api_hash": self.tg_hash_entry.text().strip(),
            "tg_phone": self.tg_phone_entry.text().strip(),
            "output_dir": self.dir_entry.text().strip(),
            "output_file": self.file_entry.text().strip(),
            "noise_reduction": self.noise_switch.isChecked(),
            "export_docx": self.docx_switch.isChecked(),
            "export_md": self.md_switch.isChecked(),
            "theme": selected_theme,
            "dark_mode": selected_theme == "Dark"
        }

        success = save_config(config_data)
        if success:
            InfoBar.success(
                title="Settings Saved",
                content="System configuration updated successfully.",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self.container
            )

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.dir_entry.text())
        if folder:
            self.dir_entry.setText(folder)

    def import_config(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import config.json", "", "JSON Files (*.json)")
        if file_path:
            import json
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    save_config(data)
                    self.load_settings()
                    InfoBar.success(
                        title="Config Imported",
                        content="Configuration imported successfully.",
                        parent=self.container
                    )
            except Exception as e:
                InfoBar.error(
                    title="Import Failed",
                    content=f"Error importing config: {e}",
                    duration=-1,
                    parent=self.container
                )

    def on_theme_changed(self, theme_text):
        self.apply_theme(theme_text)

    def apply_theme(self, theme_text):
        if theme_text == "Dark":
            setTheme(Theme.DARK)
        elif theme_text == "Light":
            setTheme(Theme.LIGHT)
        else:
            setTheme(Theme.AUTO)

        main_win = self.window()
        if hasattr(main_win, 'update_theme_logos'):
            main_win.update_theme_logos()

    def authenticate_telegram(self):
        tg_id = self.tg_id_entry.text().strip()
        tg_hash = self.tg_hash_entry.text().strip()
        phone = self.tg_phone_entry.text().strip()

        if not tg_id or not tg_hash or not phone:
            InfoBar.warning(
                title="Missing Information",
                content="Please enter Telegram API ID, API Hash, and Phone Number.",
                duration=-1,
                parent=self.container
            )
            return

        try:
            InfoBar.info("Sending OTP", "Requesting login code from Telegram...", parent=self.container)
            phone_code_hash = request_telegram_otp(tg_id, tg_hash, phone)
            
            code, ok = QInputDialog.getText(
                self,
                "Telegram Verification Code",
                f"Enter the verification code sent to {phone}.\n\n"
                "(Note: Check your active Telegram app for a message from 'Telegram' – codes are usually sent in-app first, not via SMS):"
            )

            if ok and code.strip():
                user_id = complete_telegram_otp(tg_id, tg_hash, phone, phone_code_hash, code.strip())
                if user_id:
                    InfoBar.success(
                        title="Telegram Authenticated",
                        content=f"Successfully signed in to Telegram (User ID: {user_id}). Session file saved!",
                        parent=self.container
                    )
                    self.save_settings()
                else:
                    InfoBar.error("Authentication Failed", "Telegram sign in failed.", duration=-1, parent=self.container)
        except Exception as e:
            InfoBar.error(
                title="Telegram Authentication Error",
                content=str(e),
                duration=-1,
                parent=self.container
            )
