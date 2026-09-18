APP_QSS = """
QMainWindow, QDialog, QWidget {
    background: #1b1d23;
    color: #e8eaed;
}
QLabel {
    color: #e8eaed;
}
QListWidget {
    background: #16181d;
    border: none;
    padding: 8px;
    outline: none;
}
QListWidget::item {
    padding: 10px 12px;
    margin-bottom: 4px;
    border-radius: 8px;
    color: #cfd3dc;
}
QListWidget::item:selected {
    background: #2a3142;
    color: #ffffff;
}
QListWidget::item:hover {
    background: #232833;
}
QPlainTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox {
    background: #22252c;
    border: 1px solid #2e323c;
    border-radius: 8px;
    padding: 8px 10px;
    color: #e8eaed;
    selection-background-color: #3d5aa8;
}
QPlainTextEdit:focus, QLineEdit:focus {
    border: 1px solid #5b8cff;
}
QPushButton {
    background: #2a3142;
    color: #e8eaed;
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    min-height: 20px;
}
QPushButton:hover {
    background: #35405a;
}
QPushButton:pressed {
    background: #243056;
}
QPushButton:disabled {
    background: #2a2c33;
    color: #6b707a;
}
QPushButton#primary {
    background: #3d6dff;
    color: #ffffff;
}
QPushButton#primary:hover {
    background: #5b8cff;
}
QPushButton#danger {
    background: #5a2a32;
}
QPushButton#danger:hover {
    background: #7a3540;
}
QScrollArea {
    border: none;
    background: #1b1d23;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px;
}
QScrollBar::handle:vertical {
    background: #3a3f4a;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QCheckBox {
    color: #cfd3dc;
    spacing: 8px;
}
QFrame#sidebar {
    background: #16181d;
}
QFrame#header {
    background: #1b1d23;
    border-bottom: 1px solid #2e323c;
}
QFrame#inputBar {
    background: #1b1d23;
    border-top: 1px solid #2e323c;
}
QFrame#userBubble {
    background: #2f6fed;
    border-radius: 14px;
}
QFrame#assistantBubble {
    background: #252830;
    border-radius: 14px;
    border: 1px solid #323640;
}
QFrame#errorBubble {
    background: #3a2428;
    border-radius: 14px;
    border: 1px solid #6a3942;
}
QTextBrowser {
    background: transparent;
    border: none;
    color: #e8eaed;
}
QStatusBar {
    background: #16181d;
    color: #8b909a;
    border-top: 1px solid #2e323c;
}
"""
