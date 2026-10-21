"""Bounded local processing. Document bytes are data, never instructions."""
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from io import BytesIO
from pathlib import Path
import os
import re
import shutil
import socket
import struct
import subprocess
import tempfile
from uuid import UUID
import zipfile
from xml.etree import ElementTree

from spesped.errors import DomainError

MAX_BYTES = 12 * 1024 * 1024
MAX_TEXT = 500_000
MAX_PAGES = 200
MEDIA = {".txt": "text/plain", ".eml": "message/rfc822", ".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class ProcessingUnavailable(Exception):
    pass


class UnsafeFile(Exception):
    pass


class LocalStorage:
    """Private object directory, never served as a static mount; UUID keys only."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)

    def path(self, key):
        return self.root / str(UUID(key))

    def put(self, key, content):
        path = self.path(key)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

    def read(self, key):
        with self.path(key).open("rb") as stream:
            content = stream.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise UnsafeFile()
        return content

    def delete(self, key):
        self.path(key).unlink(missing_ok=True)


@dataclass
class ClamdScanner:
    """Local clamd INSTREAM protocol; no shell, remote service or success fallback."""
    socket_path: str
    synthetic: bool = False

    def scan(self, content):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(15)
                connection.connect(self.socket_path)
                connection.sendall(b"zINSTREAM\0")
                for offset in range(0, len(content), 65536):
                    chunk = content[offset:offset + 65536]
                    connection.sendall(struct.pack("!I", len(chunk)) + chunk)
                connection.sendall(struct.pack("!I", 0))
                reply = b""
                while b"\0" not in reply and len(reply) < 4096:
                    chunk = connection.recv(1024)
                    if not chunk:
                        break
                    reply += chunk
                if reply.strip(b"\0\r\n") == b"stream: OK":
                    return "clean"
                if b" FOUND" in reply:
                    return "infected"
                raise ProcessingUnavailable("scanner_unavailable")
        except (OSError, TimeoutError):
            raise ProcessingUnavailable("scanner_unavailable") from None


@dataclass
class TesseractOCR:
    """Optional local executable adapter; explicit unavailable status when absent."""
    tesseract: str = "tesseract"
    pdftoppm: str = "pdftoppm"
    language: str = "nor+eng"
    tessdata_dir: str | None = None
    synthetic: bool = False

    def extract(self, content, extension, page_count=1):
        executable = shutil.which(self.tesseract)
        converter = shutil.which(self.pdftoppm)
        if not executable or (extension == ".pdf" and not converter):
            raise ProcessingUnavailable("ocr_unavailable")
        if page_count > 40:
            raise UnsafeFile("ocr_page_limit")
        with tempfile.TemporaryDirectory(prefix="spesped-ocr-") as directory:
            source = Path(directory) / ("source" + extension)
            source.write_bytes(content)
            try:
                if extension == ".pdf":
                    subprocess.run([converter, "-scale-to", "1600", "-png", str(source), str(Path(directory) / "page")], check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    images = sorted(Path(directory).glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
                else:
                    images = [source]
                pages = []
                for image in images:
                    arguments = [executable, str(image), "stdout", "-l", self.language]
                    if self.tessdata_dir:
                        arguments += ["--tessdata-dir", self.tessdata_dir]
                    result = subprocess.run(arguments, check=True, timeout=30, capture_output=True)
                    if len(result.stdout) > MAX_TEXT:
                        raise UnsafeFile("text_limit")
                    pages.append(result.stdout.decode("utf-8"))
                return pages
            except (subprocess.SubprocessError, OSError, UnicodeError):
                raise ProcessingUnavailable("ocr_failed") from None


def inspect_type(filename, content):
    if not content or len(content) > MAX_BYTES:
        raise DomainError("upload_size", "File must contain 1–12582912 bytes.", 413)
    extension = Path(filename).suffix.lower()
    if extension not in MEDIA:
        raise DomainError("file_type", "This file type is unsupported.", 422)
    valid = True
    if extension == ".pdf":
        valid = content.startswith(b"%PDF-")
    elif extension == ".docx":
        valid = content.startswith(b"PK\x03\x04")
    elif extension == ".png":
        valid = content.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension in {".jpg", ".jpeg"}:
        valid = content.startswith(b"\xff\xd8\xff")
    else:
        try:
            content.decode("utf-8-sig")
        except UnicodeError:
            valid = False
        valid = valid and b"\x00" not in content
        if extension == ".eml":
            valid = valid and bool(re.search(rb"(?im)^(from|subject|message-id):", content))
    if not valid:
        raise DomainError("file_signature", "File contents do not match its declared type.", 422)
    return extension, MEDIA[extension]


def extract(content, extension, scanner=None, ocr=None, depth=0):
    if extension == ".txt":
        pages = [content.decode("utf-8-sig")]
    elif extension == ".docx":
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(e.file_size for e in entries) > 32 * 1024 * 1024:
                raise UnsafeFile("archive_limit")
            for entry in entries:
                if entry.flag_bits & 1 or entry.file_size > 8 * 1024 * 1024 or (entry.file_size > max(entry.compress_size, 1) * 200) or ".." in Path(entry.filename).parts:
                    raise UnsafeFile("archive_limit")
                if entry.filename.endswith("vbaProject.bin") or entry.filename.startswith("word/embeddings/"):
                    raise UnsafeFile("embedded_content")
            if "word/document.xml" not in archive.namelist() or "[Content_Types].xml" not in archive.namelist():
                raise UnsafeFile("invalid_docx")
            xml = archive.read("word/document.xml")
            if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                raise UnsafeFile("xml_entities")
            tree = ElementTree.fromstring(xml)
            # DOCX has no stable physical pagination. These are explicitly logical pages
            # split only at actual page breaks; exact character spans remain authoritative.
            pages = [""]
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for node in tree.iter():
                if node.tag == ns + "t":
                    pages[-1] += node.text or ""
                elif node.tag == ns + "br" and node.attrib.get(ns + "type") == "page":
                    pages.append("")
                elif node.tag in {ns + "p", ns + "tab", ns + "br"}:
                    pages[-1] += "\n" if node.tag != ns + "tab" else "\t"
    elif extension == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted or len(reader.pages) > MAX_PAGES:
            raise UnsafeFile("pdf_limit_or_encryption")
        pages = [(page.extract_text() or "") for page in reader.pages]
        if any(not page.strip() for page in pages):
            if ocr is None:
                raise ProcessingUnavailable("ocr_unavailable")
            scanned = ocr.extract(content, extension, len(pages))
            if len(scanned) != len(pages):
                raise UnsafeFile("ocr_page_mismatch")
            pages = [text if text.strip() else scanned[i] for i, text in enumerate(pages)]
    elif extension in {".png", ".jpg", ".jpeg"}:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = 20_000_000
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > 20_000_000 or image.width > 12000 or image.height > 12000:
                raise UnsafeFile("image_pixel_limit")
            image.verify()
        if ocr is None:
            raise ProcessingUnavailable("ocr_unavailable")
        pages = ocr.extract(content, extension)
    elif extension == ".eml":
        if depth:
            raise UnsafeFile("nested_email")
        message = BytesParser(policy=policy.default).parsebytes(content)
        if message.defects:
            raise UnsafeFile("invalid_email")
        parts = list(message.walk())
        if len(parts) > 40:
            raise UnsafeFile("email_part_limit")
        pages = []
        for part in parts:
            if part.is_multipart():
                continue
            payload = part.get_payload(decode=True) or b""
            if len(payload) > MAX_BYTES:
                raise UnsafeFile("attachment_limit")
            filename = part.get_filename()
            if filename:
                attachment_ext, _ = inspect_type(filename, payload)
                if scanner is None or scanner.scan(payload) != "clean":
                    raise UnsafeFile("attachment_scan_failed")
                pages.extend(extract(payload, attachment_ext, scanner, ocr, depth + 1))
            elif part.get_content_type() == "text/plain":
                pages.append(payload.decode(part.get_content_charset() or "utf-8"))
        if not pages:
            raise ProcessingUnavailable("plain_text_email_required")
    else:
        raise UnsafeFile("unsupported_type")
    if len(pages) > MAX_PAGES or sum(len(page) for page in pages) > MAX_TEXT:
        raise UnsafeFile("text_limit")
    if not pages or not any(page.strip() for page in pages):
        raise ProcessingUnavailable("manual_transcription_required")
    return pages


def _extract_worker(connection, content, extension, scanner, ocr, temporary_root):
    # File/parser and OCR code run with process limits before decompression.
    try:
        import resource
        import sys
        import logging
        import warnings
        logging.disable(logging.CRITICAL)
        warnings.simplefilter("ignore")
        tempfile.tempdir = temporary_root
        os.setsid()
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
        if sys.platform != "darwin":
            resource.setrlimit(resource.RLIMIT_DATA, (768 * 1024 * 1024, 768 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024, 1536 * 1024 * 1024))
        pages = extract(content, extension, scanner, ocr)
        connection.send(("ready", pages))
    except ProcessingUnavailable as exc:
        connection.send(("unavailable", str(exc)))
    except BaseException:
        connection.send(("rejected", "unsafe_or_invalid_document"))
    finally:
        connection.close()


def bounded_extract(content, extension, scanner=None, ocr=None):
    import multiprocessing
    try:
        context = multiprocessing.get_context("spawn")
    except ValueError:
        raise ProcessingUnavailable("local_process_limits_unavailable") from None
    import time
    import signal
    import sys
    receive, send = context.Pipe(duplex=False)
    temporary = tempfile.TemporaryDirectory(prefix="spesped-extract-")
    process = context.Process(target=_extract_worker, args=(send, content, extension, scanner, ocr, temporary.name), daemon=True)
    try:
        process.start()
    except Exception:
        temporary.cleanup()
        receive.close()
        send.close()
        raise ProcessingUnavailable("processing_unavailable") from None
    send.close()
    try:
        deadline = time.monotonic() + 45
        while not receive.poll(0.025):
            if not process.is_alive() or time.monotonic() >= deadline:
                raise UnsafeFile("extraction_resource_limit")
            # Darwin rejects RLIMIT_AS/DATA/RSS. Monitor resident memory from
            # outside the parser; Linux also has strict kernel limits above.
            if sys.platform == "darwin":
                result = subprocess.run(["/bin/ps", "-o", "rss=", "-p", str(process.pid)], capture_output=True, timeout=2)
                if result.returncode == 0 and result.stdout.strip() and int(result.stdout.strip()) > 768 * 1024:
                    raise UnsafeFile("extraction_memory_limit")
        try:
            result, value = receive.recv()
        except EOFError:
            raise UnsafeFile("extraction_resource_limit") from None
        if result == "unavailable":
            raise ProcessingUnavailable(value)
        if result != "ready":
            raise UnsafeFile("unsafe_or_invalid_document")
        return value
    finally:
        receive.close()
        if process.is_alive():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                process.terminate()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join(timeout=2)
        temporary.cleanup()
