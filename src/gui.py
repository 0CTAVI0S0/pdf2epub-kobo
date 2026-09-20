"""
Interfaz gráfica: arrastra PDFs, previsualiza capítulos y genera EPUB/KEPUB.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.converter import (
    AnalysisResult,
    ConversionCancelled,
    ConversionOptions,
    ConversionResult,
    analyze_pdf,
    convert_many,
    convert_pdf_to_epub,
    default_output_path,
    parse_manual_chapter_markers,
    read_pdf_metadata,
)

LANGUAGES = [
    ("es", "Español"),
    ("en", "English"),
    ("pt", "Português"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("ca", "Català"),
    ("gl", "Galego"),
]


class Worker(QThread):
    progress = Signal(str, int)
    failed = Signal(str)
    analysis_done = Signal(object)
    convert_done = Signal(object)
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self._mode = "convert"
        self.pdf_paths: list[Path] = []
        self.output_path: Path | None = None
        self.dest_dir: Path | None = None
        self.options = ConversionOptions()
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def _is_cancelled(self) -> bool:
        return self._cancel

    def configure_analysis(self, pdf: Path, options: ConversionOptions) -> None:
        self._mode = "analyze"
        self._cancel = False
        self.pdf_paths = [pdf]
        self.options = options
        self.options.is_cancelled = self._is_cancelled

    def configure_convert(
        self,
        pdfs: list[Path],
        options: ConversionOptions,
        output_path: Path | None = None,
        dest_dir: Path | None = None,
    ) -> None:
        self._mode = "convert"
        self._cancel = False
        self.pdf_paths = pdfs
        self.options = options
        self.options.is_cancelled = self._is_cancelled
        self.output_path = output_path
        self.dest_dir = dest_dir

    def run(self) -> None:
        try:
            if self._mode == "analyze":
                result = analyze_pdf(
                    self.pdf_paths[0],
                    self.options,
                    progress_cb=self.progress.emit,
                )
                self.analysis_done.emit(result)
                return

            if len(self.pdf_paths) == 1 and self.output_path is not None:
                result = convert_pdf_to_epub(
                    self.pdf_paths[0],
                    self.output_path,
                    self.options,
                    progress_cb=self.progress.emit,
                )
                self.convert_done.emit([result])
            else:
                dest = self.dest_dir or self.pdf_paths[0].parent
                results = convert_many(
                    self.pdf_paths, dest, self.options, progress_cb=self.progress.emit
                )
                self.convert_done.emit(results)
        except ConversionCancelled:
            self.cancelled.emit()
        except Exception:
            self.failed.emit(traceback.format_exc())


class DropZone(QFrame):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(120)
        self.setStyleSheet(
            """
            QFrame {
                border: 2px dashed #8a8a8a;
                border-radius: 10px;
                background-color: #fafafa;
            }
            QFrame:hover { border-color: #4a90d9; }
            """
        )
        layout = QVBoxLayout(self)
        self.label = QLabel("Arrastra uno o más PDFs aquí\no haz click para seleccionarlos")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("border: none; font-size: 14px; color: #555;")
        layout.addWidget(self.label)

    def mousePressEvent(self, event):
        paths, _ = QFileDialog.getOpenFileNames(self, "Selecciona PDFs", "", "PDF (*.pdf)")
        if paths:
            self.files_dropped.emit([Path(p) for p in paths])

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        pdfs = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() == ".pdf":
                pdfs.append(path)
        if pdfs:
            self.files_dropped.emit(pdfs)
        else:
            QMessageBox.warning(self, "Archivo inválido", "Suelta uno o más archivos .pdf")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF → EPUB para Kobo")
        self.setMinimumWidth(540)

        self.pdfs: list[Path] = []
        self.cover_image_path: Path | None = None
        self.analysis: AnalysisResult | None = None
        self.worker = Worker()
        self.worker.progress.connect(self.on_progress)
        self.worker.failed.connect(self.on_failure)
        self.worker.analysis_done.connect(self.on_analysis)
        self.worker.convert_done.connect(self.on_convert_done)
        self.worker.cancelled.connect(self.on_cancelled)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        central = QWidget()
        scroll.setWidget(central)
        self.setCentralWidget(scroll)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self.handle_files)
        layout.addWidget(self.drop_zone)

        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(90)
        layout.addWidget(self.file_list)

        form_row1 = QHBoxLayout()
        form_row1.addWidget(QLabel("Título:"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("(metadata del PDF o nombre de archivo)")
        form_row1.addWidget(self.title_input)
        layout.addLayout(form_row1)

        form_row2 = QHBoxLayout()
        form_row2.addWidget(QLabel("Autor:"))
        self.author_input = QLineEdit()
        self.author_input.setPlaceholderText("Desconocido")
        form_row2.addWidget(self.author_input)
        layout.addLayout(form_row2)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Idioma:"))
        self.language_combo = QComboBox()
        for code, label in LANGUAGES:
            self.language_combo.addItem(f"{label} ({code})", code)
        lang_row.addWidget(self.language_combo, stretch=1)
        layout.addLayout(lang_row)

        cover_row = QHBoxLayout()
        self.cover_button = QPushButton("Elegir portada…")
        self.cover_button.clicked.connect(self.choose_cover_image)
        cover_row.addWidget(self.cover_button)
        self.cover_label = QLabel("Portada: se extraerá de la 1.ª página")
        self.cover_label.setStyleSheet("color: #666;")
        cover_row.addWidget(self.cover_label, stretch=1)
        self.clear_cover_button = QPushButton("Quitar")
        self.clear_cover_button.setEnabled(False)
        self.clear_cover_button.clicked.connect(self.clear_cover_image)
        cover_row.addWidget(self.clear_cover_button)
        layout.addLayout(cover_row)

        self.extract_cover_checkbox = QCheckBox("Extraer portada del PDF si no eliges una imagen")
        self.extract_cover_checkbox.setChecked(True)
        layout.addWidget(self.extract_cover_checkbox)

        self.split_by_page_checkbox = QCheckBox(
            "Crear un capítulo por cada página del PDF (en vez de detectar títulos)"
        )
        self.split_by_page_checkbox.toggled.connect(self.mark_preview_stale)
        layout.addWidget(self.split_by_page_checkbox)

        self.strip_headers_checkbox = QCheckBox("Quitar cabeceras, pies y números de página")
        self.strip_headers_checkbox.setChecked(True)
        self.strip_headers_checkbox.toggled.connect(self.mark_preview_stale)
        layout.addWidget(self.strip_headers_checkbox)

        self.ocr_checkbox = QCheckBox("Usar OCR (Tesseract) si el PDF no tiene texto seleccionable")
        self.ocr_checkbox.toggled.connect(self.mark_preview_stale)
        layout.addWidget(self.ocr_checkbox)

        self.kepub_checkbox = QCheckBox("Generar KEPUB (.kepub.epub) con marcas de lectura Kobo")
        self.kepub_checkbox.toggled.connect(self.mark_preview_stale)
        layout.addWidget(self.kepub_checkbox)

        self.manual_chapters_checkbox = QCheckBox(
            "Definir capítulos manualmente (tiene prioridad sobre lo anterior)"
        )
        self.manual_chapters_checkbox.toggled.connect(self.toggle_manual_chapters)
        layout.addWidget(self.manual_chapters_checkbox)

        self.manual_chapters_help = QLabel(
            "Una línea por capítulo, formato:  Título :: primeras palabras exactas del capítulo"
        )
        self.manual_chapters_help.setStyleSheet("color: #666; font-size: 11px;")
        self.manual_chapters_help.setWordWrap(True)
        self.manual_chapters_help.setVisible(False)
        layout.addWidget(self.manual_chapters_help)

        self.manual_chapters_input = QPlainTextEdit()
        self.manual_chapters_input.setPlaceholderText(
            "Noche primera :: Era una noche maravillosa, una de esas noches\n"
            "Noche segunda :: Bueno, ¿y qué? ¿No ha dormido usted?"
        )
        self.manual_chapters_input.setFixedHeight(90)
        self.manual_chapters_input.setVisible(False)
        self.manual_chapters_input.textChanged.connect(self.mark_preview_stale)
        layout.addWidget(self.manual_chapters_input)

        preview_header = QHBoxLayout()
        preview_header.addWidget(QLabel("Capítulos detectados (doble click para renombrar):"))
        self.redetect_button = QPushButton("Volver a detectar")
        self.redetect_button.clicked.connect(self.start_analysis)
        preview_header.addWidget(self.redetect_button)
        layout.addLayout(preview_header)

        self.preview_list = QListWidget()
        self.preview_list.setMinimumHeight(120)
        self.preview_list.itemChanged.connect(self.on_chapter_renamed)
        layout.addWidget(self.preview_list)

        btn_row = QHBoxLayout()
        self.convert_button = QPushButton("Convertir a EPUB")
        self.convert_button.setEnabled(False)
        self.convert_button.setStyleSheet(
            """
            QPushButton {
                background-color: #4a90d9; color: white; padding: 10px;
                border-radius: 6px; font-size: 14px; font-weight: bold;
            }
            QPushButton:disabled { background-color: #b0c4d9; }
            QPushButton:hover:!disabled { background-color: #3a7cc0; }
            """
        )
        self.convert_button.clicked.connect(self.start_conversion)
        btn_row.addWidget(self.convert_button)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_work)
        btn_row.addWidget(self.cancel_button)
        layout.addLayout(btn_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def current_language(self) -> str:
        return self.language_combo.currentData() or "es"

    def set_language(self, code: str) -> None:
        code = (code or "es").split("-")[0].lower()
        for i in range(self.language_combo.count()):
            if self.language_combo.itemData(i) == code:
                self.language_combo.setCurrentIndex(i)
                return

    def handle_files(self, paths: list[Path]) -> None:
        self.pdfs = paths
        self.analysis = None
        self.preview_list.clear()
        self.file_list.clear()
        for path in paths:
            self.file_list.addItem(path.name)
        self.convert_button.setEnabled(True)
        self.status_label.setText("")
        self.progress_bar.setValue(0)

        if len(paths) == 1:
            meta = read_pdf_metadata(paths[0])
            self.title_input.setText(meta.title or paths[0].stem)
            if meta.author:
                self.author_input.setText(meta.author)
            if meta.language:
                self.set_language(meta.language)
            self.start_analysis()
        else:
            self.title_input.setText("")
            self.title_input.setPlaceholderText("Se toma de cada PDF (metadata o nombre)")
            self.status_label.setText(f"{len(paths)} PDFs listos para conversión por lote.")

    def toggle_manual_chapters(self, checked: bool) -> None:
        self.manual_chapters_help.setVisible(checked)
        self.manual_chapters_input.setVisible(checked)
        self.split_by_page_checkbox.setEnabled(not checked)
        self.mark_preview_stale()

    def mark_preview_stale(self, *_args) -> None:
        self.analysis = None
        if self.pdfs:
            self.status_label.setText("Opciones cambiadas: vuelve a detectar capítulos o convierte de nuevo.")

    def on_chapter_renamed(self, item: QListWidgetItem) -> None:
        if not self.analysis:
            return
        row = self.preview_list.row(item)
        chapters = list(self.analysis.chapters)
        if 0 <= row < len(chapters):
            _, html = chapters[row]
            chapters[row] = (item.text().strip() or f"Capítulo {row + 1}", html)
            self.analysis.chapters = chapters

    def choose_cover_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona una imagen de portada", "", "Imágenes (*.jpg *.jpeg *.png)"
        )
        if path:
            self.cover_image_path = Path(path)
            self.cover_label.setText(f"🖼 {self.cover_image_path.name}")
            self.clear_cover_button.setEnabled(True)

    def clear_cover_image(self) -> None:
        self.cover_image_path = None
        self.cover_label.setText("Portada: se extraerá de la 1.ª página")
        self.clear_cover_button.setEnabled(False)

    def build_options(self, *, include_preview_chapters: bool) -> ConversionOptions | None:
        manual_chapters = None
        if self.manual_chapters_checkbox.isChecked():
            try:
                manual_chapters = parse_manual_chapter_markers(
                    self.manual_chapters_input.toPlainText()
                )
            except ValueError as exc:
                QMessageBox.warning(self, "Formato de capítulos inválido", str(exc))
                return None

        chapters = None
        method = ""
        if include_preview_chapters and self.analysis and len(self.pdfs) == 1:
            chapters = list(self.analysis.chapters)
            method = self.analysis.detection_method

        return ConversionOptions(
            title=self.title_input.text().strip(),
            author=self.author_input.text().strip() or "Desconocido",
            language=self.current_language(),
            split_by_page=self.split_by_page_checkbox.isChecked(),
            manual_chapters=manual_chapters,
            cover_image_path=self.cover_image_path,
            extract_cover_from_pdf=self.extract_cover_checkbox.isChecked(),
            use_ocr=self.ocr_checkbox.isChecked(),
            strip_headers_footers=self.strip_headers_checkbox.isChecked(),
            kepub=self.kepub_checkbox.isChecked(),
            chapters=chapters,
            detection_method=method,
        )

    def set_busy(self, busy: bool) -> None:
        self.convert_button.setEnabled(not busy and bool(self.pdfs))
        self.redetect_button.setEnabled(not busy and len(self.pdfs) == 1)
        self.cancel_button.setEnabled(busy)
        self.drop_zone.setEnabled(not busy)

    def start_analysis(self) -> None:
        if len(self.pdfs) != 1:
            return
        options = self.build_options(include_preview_chapters=False)
        if options is None:
            return
        self.set_busy(True)
        self.status_label.setText("Analizando…")
        self.worker.configure_analysis(self.pdfs[0], options)
        self.worker.start()

    def start_conversion(self) -> None:
        if not self.pdfs:
            return
        options = self.build_options(include_preview_chapters=True)
        if options is None:
            return

        kepub = options.kepub
        if len(self.pdfs) == 1:
            default_name = default_output_path(
                self.pdfs[0], None, kepub=kepub
            ).name
            if options.title:
                default_name = options.title + (".kepub.epub" if kepub else ".epub")
            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar EPUB como",
                default_name,
                "KEPUB (*.kepub.epub);;EPUB (*.epub)" if kepub else "EPUB (*.epub)",
            )
            if not output_path:
                return
            dest_dir = None
            out = Path(output_path)
        else:
            dest = QFileDialog.getExistingDirectory(self, "Carpeta de salida para los EPUB")
            if not dest:
                return
            dest_dir = Path(dest)
            out = None

        self.set_busy(True)
        self.status_label.setText("Convirtiendo…")
        self.progress_bar.setValue(0)
        self.worker.configure_convert(self.pdfs, options, output_path=out, dest_dir=dest_dir)
        self.worker.start()

    def cancel_work(self) -> None:
        self.worker.request_cancel()
        self.status_label.setText("Cancelando…")

    def on_progress(self, msg: str, percent: int) -> None:
        self.status_label.setText(msg)
        self.progress_bar.setValue(percent)

    def on_analysis(self, result: AnalysisResult) -> None:
        self.set_busy(False)
        self.analysis = result
        self.preview_list.blockSignals(True)
        self.preview_list.clear()
        for title, _html in result.chapters:
            item = QListWidgetItem(title)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.preview_list.addItem(item)
        self.preview_list.blockSignals(False)

        if not self.title_input.text().strip() and result.metadata.title:
            self.title_input.setText(result.metadata.title)
        if (not self.author_input.text().strip() or self.author_input.text() == "Desconocido") and result.metadata.author:
            self.author_input.setText(result.metadata.author)

        msg = f"{len(result.chapters)} capítulo(s) — {result.detection_method}"
        if result.warnings:
            msg += " | " + "; ".join(result.warnings)
        self.status_label.setText(msg)
        self.progress_bar.setValue(100)

    def on_convert_done(self, results: list[ConversionResult]) -> None:
        self.set_busy(False)
        self.progress_bar.setValue(100)
        if len(results) == 1:
            result = results[0]
            msg = (
                f"EPUB creado con {result.chapter_count} capítulo(s) "
                f"(detectados por: {result.detection_method}): {result.output_path.name}"
            )
            self.status_label.setText(msg)
            extra = ""
            if result.warnings:
                extra = "\n\nAvisos:\n- " + "\n- ".join(result.warnings)
            QMessageBox.information(self, "Conversión completada", msg + extra)
        else:
            lines = [
                f"{r.output_path.name}: {r.chapter_count} cap. ({r.detection_method})"
                for r in results
            ]
            warnings = [w for r in results for w in r.warnings]
            msg = f"{len(results)} EPUB creados:\n" + "\n".join(lines)
            self.status_label.setText(f"{len(results)} EPUB creados.")
            if warnings:
                msg += "\n\nAvisos:\n- " + "\n- ".join(warnings)
            QMessageBox.information(self, "Lote completado", msg)

    def on_cancelled(self) -> None:
        self.set_busy(False)
        self.status_label.setText("Cancelado.")
        self.progress_bar.setValue(0)

    def on_failure(self, error_msg: str) -> None:
        self.set_busy(False)
        self.status_label.setText("Error en la conversión")
        QMessageBox.critical(self, "Error", f"No se pudo completar la operación:\n\n{error_msg}")


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(580, 760)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
