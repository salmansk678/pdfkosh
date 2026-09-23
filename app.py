import io
import os
import re
import zipfile
from datetime import datetime, timezone
from flask import Flask, render_template, request, send_file, jsonify, flash, redirect, url_for, Response
from werkzeug.utils import secure_filename
import img2pdf
from PIL import Image
import pypdf
import pypdfium2 as pdfium
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Maximum upload size: 50 MB
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
ALLOWED_PDF_EXTENSIONS = {'pdf'}

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

def prepare_image_for_pdf(image_stream):
    """
    Ensures image format and color space are compatible with img2pdf.
    Flattens any alpha transparency onto a clean white background.
    """
    with Image.open(image_stream) as img:
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            
            output = io.BytesIO()
            background.save(output, format="JPEG", quality=95)
            output.seek(0)
            return output.getvalue()
        
        elif img.mode not in ("RGB", "L", "1", "CMYK"):
            output = io.BytesIO()
            img.convert("RGB").save(output, format="JPEG", quality=95)
            output.seek(0)
            return output.getvalue()
        
        image_stream.seek(0)
        return image_stream.read()

def parse_page_ranges(range_str, total_pages):
    """
    Parses a page range string (e.g. '1-3, 5, 7-9') into a list of 0-based page indices.
    """
    if not range_str or not range_str.strip():
        raise ValueError("Page range cannot be empty.")

    selected_pages = []
    parts = [p.strip() for p in range_str.split(',') if p.strip()]

    for part in parts:
        if '-' in part:
            bounds = part.split('-')
            if len(bounds) != 2:
                raise ValueError(f"Invalid range syntax: '{part}'")
            start_str, end_str = bounds[0].strip(), bounds[1].strip()
            if not start_str.isdigit() or not end_str.isdigit():
                raise ValueError(f"Invalid page numbers in range: '{part}'")
            start, end = int(start_str), int(end_str)
            if start > end:
                raise ValueError(f"Start page ({start}) cannot be greater than end page ({end}).")
            if start < 1 or end > total_pages:
                raise ValueError(f"Range {start}-{end} out of bounds (document has {total_pages} pages).")
            for p in range(start, end + 1):
                if (p - 1) not in selected_pages:
                    selected_pages.append(p - 1)
        else:
            if not part.isdigit():
                raise ValueError(f"Invalid page number: '{part}'")
            p = int(part)
            if p < 1 or p > total_pages:
                raise ValueError(f"Page {p} out of bounds (document has {total_pages} pages).")
            if (p - 1) not in selected_pages:
                selected_pages.append(p - 1)

    if not selected_pages:
        raise ValueError("No valid pages selected.")

    return selected_pages

# ==========================================
# Routes
# ==========================================

@app.route('/', methods=['GET'])
def index():
    """PDFKosh Dashboard with 9 tool cards."""
    return render_template('index.html')

# --- 1. Image to PDF ---

@app.route('/image-to-pdf', methods=['GET'])
def image_to_pdf_page():
    return render_template('image_to_pdf.html')

@app.route('/image-to-pdf', methods=['POST'])
@app.route('/convert', methods=['POST'])
def convert_image():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    if 'image' not in request.files:
        error_msg = "No file part in the request."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('image_to_pdf_page'))

    file = request.files['image']

    if file.filename == '':
        error_msg = "No image selected. Please choose a file."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('image_to_pdf_page'))

    if not allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
        error_msg = f"Invalid file type. Allowed formats: {', '.join(ALLOWED_IMAGE_EXTENSIONS).upper()}."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('image_to_pdf_page'))

    try:
        original_filename = secure_filename(file.filename)
        base_name = os.path.splitext(original_filename)[0] or "converted"
        pdf_filename = f"{base_name}.pdf"

        file_bytes = io.BytesIO(file.read())
        processed_bytes = prepare_image_for_pdf(file_bytes)
        pdf_bytes = img2pdf.convert(processed_bytes)

        response = send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=pdf_filename
        )
        response.headers['X-Suggested-Filename'] = pdf_filename
        return response

    except Exception as e:
        error_msg = f"Image conversion failed: {str(e)}"
        if is_ajax:
            return jsonify({'error': error_msg}), 500
        flash(error_msg, "error")
        return redirect(url_for('image_to_pdf_page'))

# --- 2. Merge PDF ---

@app.route('/merge-pdf', methods=['GET'])
def merge_pdf_page():
    return render_template('merge_pdf.html')

@app.route('/merge-pdf', methods=['POST'])
def merge_pdf():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    files = request.files.getlist('pdf_files')

    valid_files = [f for f in files if f.filename and allowed_file(f.filename, ALLOWED_PDF_EXTENSIONS)]

    if len(valid_files) < 2:
        error_msg = "Please select at least 2 valid PDF files to merge."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('merge_pdf_page'))

    try:
        writer = pypdf.PdfWriter()
        for pdf_file in valid_files:
            file_stream = io.BytesIO(pdf_file.read())
            writer.append(file_stream)

        output_pdf = io.BytesIO()
        writer.write(output_pdf)
        writer.close()
        output_pdf.seek(0)

        download_name = "pdfkosh_merged.pdf"
        response = send_file(
            output_pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=download_name
        )
        response.headers['X-Suggested-Filename'] = download_name
        return response

    except Exception as e:
        error_msg = f"Failed to merge PDFs: {str(e)}"
        if is_ajax:
            return jsonify({'error': error_msg}), 500
        flash(error_msg, "error")
        return redirect(url_for('merge_pdf_page'))

# --- 3. Split PDF ---

@app.route('/split-pdf', methods=['GET'])
def split_pdf_page():
    return render_template('split_pdf.html')

@app.route('/api/pdf-info', methods=['POST'])
def pdf_info():
    """Helper API endpoint to quickly get total pages and metadata of an uploaded PDF."""
    if 'pdf_file' not in request.files:
        return jsonify({'error': 'No file uploaded.'}), 400

    file = request.files['pdf_file']
    if not file.filename or not allowed_file(file.filename, ALLOWED_PDF_EXTENSIONS):
        return jsonify({'error': 'Please select a valid PDF file.'}), 400

    try:
        file_bytes = io.BytesIO(file.read())
        reader = pypdf.PdfReader(file_bytes)
        is_encrypted = reader.is_encrypted
        total_pages = len(reader.pages) if not is_encrypted else 0
        return jsonify({
            'filename': secure_filename(file.filename),
            'total_pages': total_pages,
            'is_encrypted': is_encrypted
        })
    except Exception as e:
        return jsonify({'error': f"Failed to inspect PDF: {str(e)}"}), 400

@app.route('/split-pdf', methods=['POST'])
def split_pdf():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    if 'pdf_file' not in request.files:
        error_msg = "No PDF file uploaded."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('split_pdf_page'))

    file = request.files['pdf_file']
    if not file.filename or not allowed_file(file.filename, ALLOWED_PDF_EXTENSIONS):
        error_msg = "Please upload a valid PDF file."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('split_pdf_page'))

    split_mode = request.form.get('split_mode', 'range')
    page_range = request.form.get('page_range', '').strip()

    try:
        file_bytes = io.BytesIO(file.read())
        reader = pypdf.PdfReader(file_bytes)
        total_pages = len(reader.pages)

        if total_pages == 0:
            raise ValueError("The provided PDF has 0 pages.")

        original_filename = secure_filename(file.filename)
        base_name = os.path.splitext(original_filename)[0] or "document"

        # Mode A: Split into individual pages packaged as a ZIP
        if split_mode == 'all':
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for idx, page in enumerate(reader.pages):
                    writer = pypdf.PdfWriter()
                    writer.add_page(page)
                    page_buffer = io.BytesIO()
                    writer.write(page_buffer)
                    page_buffer.seek(0)
                    zip_file.writestr(f"{base_name}_page_{idx + 1}.pdf", page_buffer.getvalue())

            zip_buffer.seek(0)
            zip_filename = f"{base_name}_split_pages.zip"
            response = send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=zip_filename
            )
            response.headers['X-Suggested-Filename'] = zip_filename
            return response

        # Mode B: Extract specific page range
        else:
            if not page_range:
                raise ValueError("Please specify the page range to extract (e.g. 1-3, 5).")

            indices = parse_page_ranges(page_range, total_pages)
            writer = pypdf.PdfWriter()
            for idx in indices:
                writer.add_page(reader.pages[idx])

            output_pdf = io.BytesIO()
            writer.write(output_pdf)
            output_pdf.seek(0)

            download_name = f"{base_name}_extracted.pdf"
            response = send_file(
                output_pdf,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=download_name
            )
            response.headers['X-Suggested-Filename'] = download_name
            return response

    except ValueError as ve:
        error_msg = str(ve)
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('split_pdf_page'))
    except Exception as e:
        error_msg = f"Failed to split PDF: {str(e)}"
        if is_ajax:
            return jsonify({'error': error_msg}), 500
        flash(error_msg, "error")
        return redirect(url_for('split_pdf_page'))

# --- 4. Compress PDF ---

@app.route('/compress-pdf', methods=['GET'])
def compress_pdf_page():
    return render_template('compress_pdf.html')

@app.route('/compress-pdf', methods=['POST'])
def compress_pdf():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    if 'pdf_file' not in request.files:
        error_msg = "No PDF file uploaded."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('compress_pdf_page'))

    file = request.files['pdf_file']
    if not file.filename or not allowed_file(file.filename, ALLOWED_PDF_EXTENSIONS):
        error_msg = "Please upload a valid PDF document."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('compress_pdf_page'))

    compression_level = request.form.get('compression_level', 'recommended')

    try:
        raw_bytes = file.read()
        original_size = len(raw_bytes)
        if original_size == 0:
            raise ValueError("The uploaded PDF is empty.")

        original_filename = secure_filename(file.filename)
        base_name = os.path.splitext(original_filename)[0] or "document"
        download_name = f"{base_name}_compressed.pdf"

        compressed_bytes = None

        if compression_level == 'strong':
            doc = pdfium.PdfDocument(io.BytesIO(raw_bytes))
            image_list = []
            for page in doc:
                pil_img = page.render(scale=1.4).to_pil()
                img_buf = io.BytesIO()
                pil_img.save(img_buf, format="JPEG", quality=72, optimize=True)
                image_list.append(img_buf.getvalue())
            compressed_bytes = img2pdf.convert(image_list)
        else:
            reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
            writer = pypdf.PdfWriter()
            for p in reader.pages:
                new_page = writer.add_page(p)
                try:
                    new_page.compress_content_streams()
                except Exception:
                    pass
            try:
                writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
            except Exception:
                pass

            out = io.BytesIO()
            writer.write(out)
            writer.close()
            compressed_bytes = out.getvalue()

        compressed_size = len(compressed_bytes)

        if compressed_size > original_size and compression_level != 'strong':
            compressed_bytes = raw_bytes
            compressed_size = original_size

        saved_bytes = max(0, original_size - compressed_size)
        saved_percent = round((saved_bytes / original_size) * 100, 1) if original_size > 0 else 0

        response = send_file(
            io.BytesIO(compressed_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=download_name
        )
        response.headers['X-Suggested-Filename'] = download_name
        response.headers['X-Original-Size'] = str(original_size)
        response.headers['X-Compressed-Size'] = str(compressed_size)
        response.headers['X-Saved-Percent'] = str(saved_percent)
        return response

    except Exception as e:
        error_msg = f"Compression failed: {str(e)}"
        if is_ajax:
            return jsonify({'error': error_msg}), 500
        flash(error_msg, "error")
        return redirect(url_for('compress_pdf_page'))

# --- 5. PDF to Image ---

@app.route('/pdf-to-image', methods=['GET'])
def pdf_to_image_page():
    return render_template('pdf_to_image.html')

@app.route('/pdf-to-image', methods=['POST'])
def pdf_to_image():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    if 'pdf_file' not in request.files:
        error_msg = "No PDF file uploaded."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('pdf_to_image_page'))

    file = request.files['pdf_file']
    if not file.filename or not allowed_file(file.filename, ALLOWED_PDF_EXTENSIONS):
        error_msg = "Please upload a valid PDF document."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('pdf_to_image_page'))

    image_format = request.form.get('image_format', 'jpg').lower()
    if image_format not in ('jpg', 'jpeg', 'png'):
        image_format = 'jpg'

    resolution = request.form.get('resolution', 'standard')
    scale = 2.5 if resolution == 'high' else 1.5

    try:
        raw_bytes = file.read()
        doc = pdfium.PdfDocument(io.BytesIO(raw_bytes))
        total_pages = len(doc)
        if total_pages == 0:
            raise ValueError("The PDF has 0 pages.")

        original_filename = secure_filename(file.filename)
        base_name = os.path.splitext(original_filename)[0] or "document"

        zip_buffer = io.BytesIO()
        ext = 'jpg' if image_format in ('jpg', 'jpeg') else 'png'
        pil_format = 'JPEG' if ext == 'jpg' else 'PNG'

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for idx, page in enumerate(doc):
                pil_img = page.render(scale=scale).to_pil()
                img_io = io.BytesIO()
                if pil_format == 'JPEG':
                    if pil_img.mode != 'RGB':
                        pil_img = pil_img.convert('RGB')
                    pil_img.save(img_io, format='JPEG', quality=90, optimize=True)
                else:
                    pil_img.save(img_io, format='PNG', optimize=True)
                img_io.seek(0)
                zip_file.writestr(f"{base_name}_page_{idx + 1}.{ext}", img_io.getvalue())

        zip_buffer.seek(0)
        zip_filename = f"{base_name}_images.zip"

        response = send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        response.headers['X-Suggested-Filename'] = zip_filename
        response.headers['X-Total-Pages'] = str(total_pages)
        return response

    except Exception as e:
        error_msg = f"PDF to Image conversion failed: {str(e)}"
        if is_ajax:
            return jsonify({'error': error_msg}), 500
        flash(error_msg, "error")
        return redirect(url_for('pdf_to_image_page'))

# --- 6. Rotate PDF ---

@app.route('/rotate-pdf', methods=['GET'])
def rotate_pdf_page():
    return render_template('rotate_pdf.html')

@app.route('/rotate-pdf', methods=['POST'])
def rotate_pdf():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    if 'pdf_file' not in request.files:
        error_msg = "No PDF file uploaded."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('rotate_pdf_page'))

    file = request.files['pdf_file']
    if not file.filename or not allowed_file(file.filename, ALLOWED_PDF_EXTENSIONS):
        error_msg = "Please upload a valid PDF document."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('rotate_pdf_page'))

    try:
        angle = int(request.form.get('angle', 90))
        if angle not in (90, 180, 270):
            angle = 90

        file_bytes = io.BytesIO(file.read())
        reader = pypdf.PdfReader(file_bytes)
        writer = pypdf.PdfWriter()

        for page in reader.pages:
            page.rotate(angle)
            writer.add_page(page)

        output_pdf = io.BytesIO()
        writer.write(output_pdf)
        writer.close()
        output_pdf.seek(0)

        original_filename = secure_filename(file.filename)
        base_name = os.path.splitext(original_filename)[0] or "document"
        download_name = f"{base_name}_rotated_{angle}.pdf"

        response = send_file(
            output_pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=download_name
        )
        response.headers['X-Suggested-Filename'] = download_name
        return response

    except Exception as e:
        error_msg = f"Failed to rotate PDF: {str(e)}"
        if is_ajax:
            return jsonify({'error': error_msg}), 500
        flash(error_msg, "error")
        return redirect(url_for('rotate_pdf_page'))

# --- 7. Protect PDF ---

@app.route('/protect-pdf', methods=['GET'])
def protect_pdf_page():
    return render_template('protect_pdf.html')

@app.route('/protect-pdf', methods=['POST'])
def protect_pdf():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    if 'pdf_file' not in request.files:
        error_msg = "No PDF file uploaded."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('protect_pdf_page'))

    file = request.files['pdf_file']
    if not file.filename or not allowed_file(file.filename, ALLOWED_PDF_EXTENSIONS):
        error_msg = "Please upload a valid PDF document."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('protect_pdf_page'))

    password = request.form.get('password', '').strip()
    if not password:
        error_msg = "Password cannot be empty."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('protect_pdf_page'))

    try:
        file_bytes = io.BytesIO(file.read())
        reader = pypdf.PdfReader(file_bytes)

        if reader.is_encrypted:
            error_msg = "This PDF is already encrypted. Unlock it before re-encrypting."
            if is_ajax:
                return jsonify({'error': error_msg}), 400
            flash(error_msg, "error")
            return redirect(url_for('protect_pdf_page'))

        writer = pypdf.PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        writer.encrypt(user_password=password)

        output_pdf = io.BytesIO()
        writer.write(output_pdf)
        writer.close()
        output_pdf.seek(0)

        original_filename = secure_filename(file.filename)
        base_name = os.path.splitext(original_filename)[0] or "document"
        download_name = f"{base_name}_protected.pdf"

        response = send_file(
            output_pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=download_name
        )
        response.headers['X-Suggested-Filename'] = download_name
        return response

    except Exception as e:
        error_msg = f"Failed to protect PDF: {str(e)}"
        if is_ajax:
            return jsonify({'error': error_msg}), 500
        flash(error_msg, "error")
        return redirect(url_for('protect_pdf_page'))

# --- 8. Unlock PDF ---

@app.route('/unlock-pdf', methods=['GET'])
def unlock_pdf_page():
    return render_template('unlock_pdf.html')

@app.route('/unlock-pdf', methods=['POST'])
def unlock_pdf():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    if 'pdf_file' not in request.files:
        error_msg = "No PDF file uploaded."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('unlock_pdf_page'))

    file = request.files['pdf_file']
    if not file.filename or not allowed_file(file.filename, ALLOWED_PDF_EXTENSIONS):
        error_msg = "Please upload a valid PDF document."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('unlock_pdf_page'))

    password = request.form.get('password', '').strip()

    try:
        file_bytes = io.BytesIO(file.read())
        reader = pypdf.PdfReader(file_bytes)

        if not reader.is_encrypted:
            error_msg = "The uploaded PDF is not password-protected."
            if is_ajax:
                return jsonify({'error': error_msg}), 400
            flash(error_msg, "error")
            return redirect(url_for('unlock_pdf_page'))

        if not password:
            error_msg = "Please enter the password to unlock this document."
            if is_ajax:
                return jsonify({'error': error_msg}), 400
            flash(error_msg, "error")
            return redirect(url_for('unlock_pdf_page'))

        decrypt_status = reader.decrypt(password)
        if decrypt_status == 0:
            error_msg = "Incorrect password. Could not unlock the PDF."
            if is_ajax:
                return jsonify({'error': error_msg}), 400
            flash(error_msg, "error")
            return redirect(url_for('unlock_pdf_page'))

        writer = pypdf.PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        output_pdf = io.BytesIO()
        writer.write(output_pdf)
        writer.close()
        output_pdf.seek(0)

        original_filename = secure_filename(file.filename)
        base_name = os.path.splitext(original_filename)[0] or "document"
        download_name = f"{base_name}_unlocked.pdf"

        response = send_file(
            output_pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=download_name
        )
        response.headers['X-Suggested-Filename'] = download_name
        return response

    except Exception as e:
        error_msg = f"Failed to unlock PDF: {str(e)}"
        if is_ajax:
            return jsonify({'error': error_msg}), 500
        flash(error_msg, "error")
        return redirect(url_for('unlock_pdf_page'))

# --- 9. Page Numbers ---

@app.route('/page-numbers', methods=['GET'])
def page_numbers_page():
    return render_template('page_numbers.html')

@app.route('/page-numbers', methods=['POST'])
def page_numbers():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    if 'pdf_file' not in request.files:
        error_msg = "No PDF file uploaded."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('page_numbers_page'))

    file = request.files['pdf_file']
    if not file.filename or not allowed_file(file.filename, ALLOWED_PDF_EXTENSIONS):
        error_msg = "Please upload a valid PDF document."
        if is_ajax:
            return jsonify({'error': error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('page_numbers_page'))

    position = request.form.get('position', 'bottom-center')
    num_format = request.form.get('format', 'page_x_of_y')
    try:
        start_number = int(request.form.get('start_number', 1))
    except ValueError:
        start_number = 1

    try:
        file_bytes = io.BytesIO(file.read())
        reader = pypdf.PdfReader(file_bytes)
        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ValueError("The provided PDF has 0 pages.")

        writer = pypdf.PdfWriter()

        for idx, page in enumerate(reader.pages):
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)

            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(width, height))
            can.setFont("Helvetica", 10)
            can.setFillColorRGB(0.2, 0.2, 0.2)

            curr_num = idx + start_number
            text = f"Page {curr_num} of {total_pages}" if num_format == 'page_x_of_y' else str(curr_num)

            if position == 'bottom-right':
                can.drawRightString(width - 40, 25, text)
            elif position == 'bottom-left':
                can.drawString(40, 25, text)
            else:
                can.drawCentredString(width / 2.0, 25, text)

            can.save()
            packet.seek(0)

            overlay = pypdf.PdfReader(packet)
            page.merge_page(overlay.pages[0])
            writer.add_page(page)

        output_pdf = io.BytesIO()
        writer.write(output_pdf)
        writer.close()
        output_pdf.seek(0)

        original_filename = secure_filename(file.filename)
        base_name = os.path.splitext(original_filename)[0] or "document"
        download_name = f"{base_name}_numbered.pdf"

        response = send_file(
            output_pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=download_name
        )
        response.headers['X-Suggested-Filename'] = download_name
        return response

    except Exception as e:
        error_msg = f"Failed to add page numbers: {str(e)}"
        if is_ajax:
            return jsonify({'error': error_msg}), 500
        flash(error_msg, "error")
        return redirect(url_for('page_numbers_page'))

# --- Legal & Company Pages ---

@app.route('/privacy-policy', methods=['GET'])
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/terms', methods=['GET'])
def terms():
    return render_template('terms.html')

@app.route('/about', methods=['GET'])
def about():
    return render_template('about.html')

# --- SEO: Dynamic Sitemap & Robots.txt ---

@app.route('/sitemap.xml', methods=['GET'])
def sitemap():
    base_url = "https://pdfkosh.onrender.com"
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    pages = [
        # Homepage
        {"loc": "/", "priority": "1.0", "changefreq": "daily"},
        # 9 Tools
        {"loc": "/image-to-pdf", "priority": "0.9", "changefreq": "weekly"},
        {"loc": "/merge-pdf", "priority": "0.9", "changefreq": "weekly"},
        {"loc": "/split-pdf", "priority": "0.9", "changefreq": "weekly"},
        {"loc": "/compress-pdf", "priority": "0.9", "changefreq": "weekly"},
        {"loc": "/pdf-to-image", "priority": "0.9", "changefreq": "weekly"},
        {"loc": "/rotate-pdf", "priority": "0.8", "changefreq": "weekly"},
        {"loc": "/protect-pdf", "priority": "0.8", "changefreq": "weekly"},
        {"loc": "/unlock-pdf", "priority": "0.8", "changefreq": "weekly"},
        {"loc": "/page-numbers", "priority": "0.8", "changefreq": "weekly"},
        # Legal & Info Pages
        {"loc": "/about", "priority": "0.6", "changefreq": "monthly"},
        {"loc": "/privacy-policy", "priority": "0.5", "changefreq": "monthly"},
        {"loc": "/terms", "priority": "0.5", "changefreq": "monthly"},
    ]

    xml_elements = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_elements.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for page in pages:
        xml_elements.append("  <url>")
        xml_elements.append(f"    <loc>{base_url}{page['loc']}</loc>")
        xml_elements.append(f"    <lastmod>{today}</lastmod>")
        xml_elements.append(f"    <changefreq>{page['changefreq']}</changefreq>")
        xml_elements.append(f"    <priority>{page['priority']}</priority>")
        xml_elements.append("  </url>")
    xml_elements.append("</urlset>")

    return Response("\n".join(xml_elements), mimetype='application/xml')

@app.route('/robots.txt', methods=['GET'])
def robots():
    content = "User-agent: *\nAllow: /\n\nSitemap: https://pdfkosh.onrender.com/sitemap.xml\n"
    return Response(content, mimetype='text/plain')

@app.errorhandler(413)
def request_entity_too_large(error):
    error_msg = "Uploaded file exceeds the maximum allowed size (50 MB)."
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({'error': error_msg}), 413
    flash(error_msg, "error")
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
