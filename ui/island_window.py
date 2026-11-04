# ui/island_window.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QFrame, QProgressBar
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QEvent
from PyQt6.QtGui import QFont

class DynamicIslandWindow(QWidget):
    def __init__(self, on_user_submit_callback=None):
        super().__init__()
        self.on_user_submit = on_user_submit_callback
        self.is_expanded = False
        
        self.init_window_flags()
        self.init_ui()
        self.setup_animations()

    def init_window_flags(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.idle_w, self.idle_h = 240, 42
        screen_geo = self.screen().geometry()
        self.setGeometry((screen_geo.width() - self.idle_w) // 2, 12, self.idle_w, self.idle_h)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Outer Pill Box container with strict border-radius enforcement
        self.container = QFrame(self)
        self.container.setStyleSheet("""
            QFrame#MainContainer {
                background-color: #0b0b0e;
                border-radius: 20px;
                border: 1px solid #2f2f3d;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        self.container.setObjectName("MainContainer")
        
        box = QVBoxLayout(self.container)
        box.setContentsMargins(14, 8, 14, 8)
        box.setSpacing(6)
        
        # --- Top Bar ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        
        self.status_dot = QFrame()
        self.status_dot.setFixedSize(8, 8)
        self.set_dot_status("loading")
        
        self.title_lbl = QLabel("Kugane")
        self.title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet("color: #ffffff;")
        
        self.status_text_lbl = QLabel("Loading model...")
        self.status_text_lbl.setFont(QFont("Segoe UI", 8))
        self.status_text_lbl.setStyleSheet("color: #ffb700;")
        
        top_bar.addWidget(self.status_dot)
        top_bar.addWidget(self.title_lbl)
        top_bar.addWidget(self.status_text_lbl)
        top_bar.addStretch()
        box.addLayout(top_bar)
        
        # --- Loading Bar ---
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setFixedHeight(3)
        self.loading_bar.setStyleSheet("""
            QProgressBar {
                background-color: #16161f;
                border: none;
                border-radius: 1px;
            }
            QProgressBar::chunk {
                background-color: #ffb700;
                border-radius: 1px;
            }
        """)
        box.addWidget(self.loading_bar)
        
        # Output / Transcript Area
        self.output_lbl = QLabel("")
        self.output_lbl.setFont(QFont("Segoe UI", 9))
        self.output_lbl.setStyleSheet("color: #ffffff; padding: 2px;")
        self.output_lbl.setWordWrap(True)
        self.output_lbl.hide()
        
        # Typing Input Field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type message...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #16161f;
                border: 1px solid #2f2f3d;
                border-radius: 8px;
                padding: 6px 10px;
                color: #ffffff;
                font-family: 'Segoe UI';
                font-size: 9pt;
            }
            QLineEdit:focus { border: 1px solid #00ff66; }
        """)
        self.input_field.returnPressed.connect(self.handle_typed_input)
        self.input_field.hide()
        
        box.addWidget(self.output_lbl)
        box.addWidget(self.input_field)
        main_layout.addWidget(self.container)

    def set_dot_status(self, state: str):
        if state == "loading":
            color = "#ffb700"
        elif state == "ready":
            color = "#00ff66"
        else:
            color = "#ff4444"
        self.status_dot.setStyleSheet(f"background-color: {color}; border-radius: 4px; border: none;")

    def update_status(self, message: str):
        self.status_text_lbl.setText(message)
        if "Listening" in message:
            self.set_dot_status("ready")
            self.status_text_lbl.setStyleSheet("color: #888899;")
            self.loading_bar.hide()
        elif "Error" in message or "Failed" in message:
            self.set_dot_status("error")
            self.status_text_lbl.setStyleSheet("color: #ff4444;")
            self.loading_bar.hide()
        else:
            self.set_dot_status("loading")
            self.status_text_lbl.setStyleSheet("color: #ffb700;")
            self.loading_bar.show()

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow() and self.is_expanded:
                self.collapse_island()
        super().changeEvent(event)

    def setup_animations(self):
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(220)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def mousePressEvent(self, event):
        if not self.is_expanded:
            self.expand_island(target_w=440, target_h=110)

    def expand_island(self, target_w, target_h):
        self.is_expanded = True
        self.output_lbl.show()
        self.input_field.show()
        
        current = self.geometry()
        screen_geo = self.screen().geometry()
        new_x = (screen_geo.width() - target_w) // 2
        
        self.anim.stop()
        self.anim.setStartValue(current)
        self.anim.setEndValue(QRect(new_x, current.y(), target_w, target_h))
        self.anim.start()

    def collapse_island(self):
        self.is_expanded = False
        self.output_lbl.hide()
        self.input_field.hide()
        
        current = self.geometry()
        screen_geo = self.screen().geometry()
        new_x = (screen_geo.width() - self.idle_w) // 2
        
        self.anim.stop()
        self.anim.setStartValue(current)
        self.anim.setEndValue(QRect(new_x, current.y(), self.idle_w, self.idle_h))
        self.anim.start()

    def display_transcription(self, text):
        # Force text assignment and ensure label visibility
        self.output_lbl.setText(f"🗣️ {text}")
        self.output_lbl.show()
        
        needed_height = max(100, min(250, 75 + len(text) // 3))
        self.expand_island(target_w=440, target_h=needed_height)
        
        if self.on_user_submit:
            self.on_user_submit(text)

    def handle_typed_input(self):
        text = self.input_field.text().strip()
        if text:
            self.output_lbl.setText(f"⌨️ {text}")
            self.output_lbl.show()
            self.input_field.clear()
            if self.on_user_submit:
                self.on_user_submit(text)