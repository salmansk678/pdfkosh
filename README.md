# PDFKosh 🛠️📄

> **Your Free & Secure PDF Toolkit** — Fast, 100% in-memory PDF utility web application built with Python Flask and Tailwind CSS.

---

## ✨ Features (9-in-1 Toolkit)

1. **Image to PDF**: Convert JPG, JPEG, PNG, and WebP pictures into clean, standard PDF documents with lossless fidelity.
2. **Merge PDF**: Combine two or more PDF files into a single consolidated document in your preferred sequence.
3. **Split PDF**: Extract specific page ranges (e.g. `1-3, 5`) or split every page into separate PDFs bundled in a `.zip` archive.
4. **Compress PDF**: Optimize content streams and deduplicate objects or resample heavy graphics to reduce file size.
5. **PDF to Image**: Render and extract PDF pages into high-resolution JPG or PNG pictures.
6. **Rotate PDF**: Reorient document pages 90°, 180°, or 270° clockwise with permanent orientation saving.
7. **Protect PDF**: Safeguard confidential PDF files with secure password encryption.
8. **Unlock PDF**: Remove password security restrictions from authorized PDF files.
9. **Page Numbers**: Insert dynamic, vector-sharp page numbers (`Page X of Y` or `1, 2, 3...`) in bottom-center or bottom-right margins.

---

## 🔒 Security & Privacy

- **100% In-Memory Processing**: Uploaded documents are processed entirely in RAM streams via Python's `io.BytesIO`.
- **Zero Disk Writes**: No files or temporary copies are ever written to the server's hard drive.
- **Privacy by Design**: Documents disappear from memory as soon as the response stream completes.

---

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/salmansk678/pdfkosh.git
cd pdfkosh
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Application
```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

---

## 📦 Tech Stack

- **Backend**: Python 3, [Flask](https://flask.palletsprojects.com/)
- **PDF Engines**: [pypdf](https://pypdf.readthedocs.io/), [pypdfium2](https://pypdfium2.readthedocs.io/), [img2pdf](https://gitlab.mister-muffin.de/josch/img2pdf), [reportlab](https://www.reportlab.com/), [Pillow](https://pillow.readthedocs.io/)
- **Frontend**: HTML5, [Tailwind CSS](https://tailwindcss.com/) (CDN), Google Fonts (Inter & Outfit)

---

## 📄 License

MIT License. Free for personal and commercial use.
