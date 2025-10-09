STYLE_SHEET = """
QWidget {
    background-color: #1c1c1c;
    color: #dcdcdc;
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
}

QMainWindow {
    background-color: #262626;
}

QTreeWidget, QTableWidget, QListWidget {
    background-color: #2c2c2c;
    border: 1px solid #444444;
    font-size: 14px;
}

QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {
    background-color: #d85c27; /* Rekordbox Orange */
    color: #ffffff;
}

QPushButton {
    background-color: #3a3a3a;
    border: 1px solid #555555;
    font-size: 14px;
    border-radius: 4px;
}

QPushButton:hover {
    background-color: #4a4a4a;
}

QPushButton:pressed {
    background-color: #d85c27;
    /* Adjust padding for the "push down" visual effect on click */
}

/* --- THE REAL FINAL FIX --- */
/*
This rule targets the specific combination of an ENABLED button that
also has FOCUS or is the DEFAULT. This is a more specific selector
than just `:focus`, allowing it to override the problematic qdarkstyle
rule that only applies in this exact scenario.
*/
QPushButton:enabled:focus, QPushButton:enabled:default {
    border: 1px solid #d85c27; /* Provide focus feedback via border color */
    outline: none;             /* CRITICAL: Disable the focus rectangle */
}


QLineEdit, QComboBox {
    background-color: #2c2c2c;
    border: 1px solid #444444;
    border-radius: 3px;
}

QProgressBar {
    border: 1px solid #444444;
    border-radius: 3px;
    text-align: center;
    background-color: #2c2c2c;
}

QProgressBar::chunk {
    background-color: #d85c27;
}

QLabel {
    font-size: 14px;
}

QDialog {
    background-color: #262626;
}
"""