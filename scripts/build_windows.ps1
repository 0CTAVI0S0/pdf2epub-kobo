# Build a Windows .exe (one-file) with PyInstaller.
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm pdf2epub.spec
Write-Host "Listo: dist/pdf2epub-kobo.exe"
