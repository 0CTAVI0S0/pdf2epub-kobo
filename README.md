# PDF → EPUB para Kobo

Aplicación de escritorio (y CLI) para convertir PDFs de **texto** a **EPUB** o
**KEPUB**, listos para un Kobo u otro lector.

## Características

- GUI: arrastra uno o varios PDFs, o selecciónalos con un click.
- CLI: `python -m src libro.pdf -o libro.epub`.
- Título, autor e idioma se leen del metadata del PDF (puedes editarlos).
- Vista previa de capítulos: renómbralos con doble click antes de convertir.
- Detección automática de capítulos, de más a menos confiable:
  1. Índice/marcadores embebidos en el PDF.
  2. Tamaño de letra (títulos más grandes que el cuerpo).
  3. Patrón de texto ("Capítulo X", líneas en mayúsculas).
- Capítulos a mano (`Título :: primeras palabras`) o un capítulo por página.
- Limpia cabeceras, pies de página y números de página repetidos.
- Portada: imagen tuya o captura de la primera página del PDF.
- OCR opcional con Tesseract si el PDF es un escaneo.
- KEPUB (`.kepub.epub`) con `koboSpan` para el progreso de lectura en Kobo.
- Conversión por lote y barra de progreso con cancelación.
- Empaquetado a `.exe` (Windows) o binario/AppImage (Linux) con PyInstaller.

## Requisitos

- Python 3.10 o superior
- pip
- Para OCR: [Tesseract](https://github.com/tesseract-ocr/tesseract) en el PATH

## Instalación

```bash
git clone https://github.com/TU_USUARIO/pdf2epub-kobo.git
cd pdf2epub-kobo
python3 -m venv .venv
source .venv/bin/activate      # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Opcional, como paquete:

```bash
pip install -e .
pdf2epub --help
pdf2epub-gui
```

## Uso (GUI)

```bash
python3 main.py
```

1. Arrastra uno o más PDFs (o haz click para elegirlos).
2. Revisa título, autor, idioma y la lista de capítulos.
3. Opciones: portada, OCR, KEPUB, cabeceras, capítulos manuales.
4. **Convertir a EPUB** y elige el archivo (o una carpeta, si hay varios PDFs).
5. Copia el resultado a la carpeta de libros del Kobo por USB.

## Uso (CLI)

```bash
python -m src libro.pdf -o libro.epub
python -m src a.pdf b.pdf -d ./epubs --kepub
python -m src escaneo.pdf --ocr --language es
```

| Opción | Descripción |
| --- | --- |
| `-o` / `--output` | Archivo EPUB de salida (un PDF) |
| `-d` / `--outdir` | Carpeta de salida |
| `--title` `--author` `--language` | Metadatos |
| `--split-by-page` | Un capítulo por página |
| `--chapters-file` | Marcadores `Título :: inicio` |
| `--cover` | Imagen de portada |
| `--no-extract-cover` | No usar la 1.ª página como portada |
| `--ocr` | Tesseract si no hay texto |
| `--keep-headers` | No quitar cabeceras/pies |
| `--kepub` | Generar `.kepub.epub` |

## Tests

```bash
pytest tests/ -v
```

## Empaquetar

Windows (genera `dist/pdf2epub-kobo.exe`):

```powershell
powershell -File scripts/build_windows.ps1
```

Linux (binario; AppImage si tienes `appimagetool`):

```bash
bash scripts/build_linux.sh
```

## Limitaciones

- Sin Tesseract, los PDFs escaneados no se pueden leer.
- La detección de capítulos es heurística; usa la vista previa o el modo manual
  si el resultado no encaja.
- El OCR depende de que Tesseract esté instalado en el sistema.

## Estructura

```
pdf2epub-kobo/
├── main.py                 # Lanza la GUI
├── src/
│   ├── gui.py              # Interfaz PySide6
│   ├── cli.py              # Interfaz de consola
│   ├── converter.py        # Orquestación PDF → EPUB
│   ├── detect.py           # Capítulos
│   ├── cleanup.py          # Cabeceras / pies
│   └── htmlutil.py         # HTML, CSS Kobo, KEPUB
├── tests/
├── pdf2epub.spec           # PyInstaller
└── pyproject.toml
```

## Licencia

MIT — ver [LICENSE](LICENSE).
