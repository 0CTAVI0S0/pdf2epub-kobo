import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.gui import MainWindow


def test_gui_fills_title_from_filename(sample_pdf):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.start_analysis = lambda: None  # type: ignore[method-assign]
    window.handle_files([sample_pdf])
    assert window.title_input.text() == sample_pdf.stem
    assert window.convert_button.isEnabled()
    app.processEvents()
