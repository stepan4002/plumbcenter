from PySide6.QtWidgets import QComboBox, QLineEdit

from plumbcenter.gui.mainwindow import MainWindow


def test_inputs_and_theme_toggle_have_accessible_names(qapp):
    win = MainWindow()
    try:
        assert win.theme_toggle_btn.accessibleName()
        inputs = win.findChildren(QLineEdit) + win.findChildren(QComboBox)
        # skip Qt-internal editors (e.g. a combo's embedded line edit)
        unnamed = [w for w in inputs
                   if not w.accessibleName() and not w.objectName().startswith("qt_")]
        assert unnamed == [], f"unnamed inputs: {len(unnamed)}"
    finally:
        win.close()
