"""Cross-platform batch OCR engine with built-in RapidOCR fallback and system tool integration."""

import glob
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import fitz  # PyMuPDF

try:
    from rapidocr_onnxruntime import RapidOCR  # type: ignore
except ImportError:
    RapidOCR = None

try:
    import ocrmypdf as ocrmypdf_pkg  # type: ignore
except ImportError:
    ocrmypdf_pkg = None


ENGINE_MODES = {
    "auto": "Auto (Recommended: System OCRmyPDF -> Tesseract -> Built-in RapidOCR)",
    "builtin": "Built-in Offline OCR (RapidOCR + PyMuPDF, Zero External Deps)",
    "tesseract_only": "PyMuPDF 300 DPI + Tesseract CLI (No Ghostscript Needed)",
    "gs_ocrmypdf": "Full Ghostscript + OCRmyPDF Pipeline (Best Archival Compression)",
}

_THREAD_LOCAL = threading.local()


def get_augmented_env() -> dict:
    """Return a copy of os.environ with common macOS Homebrew and Windows tool paths appended."""
    env = os.environ.copy()
    env.setdefault("MAX_IMAGE_PIXELS", "1000000000")
    system = platform.system()
    extra_dirs = []

    if system == "Darwin":
        extra_dirs.extend(["/opt/homebrew/bin", "/usr/local/bin"])
    elif system == "Windows":
        tess_dir = r"C:\Program Files\Tesseract-OCR"
        if os.path.isdir(tess_dir):
            extra_dirs.append(tess_dir)
        for gs_bin in sorted(glob.glob(r"C:\Program Files\gs\gs*\bin"), reverse=True):
            if os.path.isdir(gs_bin):
                extra_dirs.append(gs_bin)

    current_path = env.get("PATH", "")
    path_parts = [p for p in current_path.split(os.pathsep) if p]
    for d in extra_dirs:
        if d not in path_parts:
            path_parts.append(d)
    env["PATH"] = os.pathsep.join(path_parts)
    return env


def find_binary(names, env=None):
    """Find the first matching executable across augmented PATH or known install locations."""
    if isinstance(names, str):
        names = [names]
    if env is None:
        env = get_augmented_env()
    search_path = env.get("PATH", "")

    for name in names:
        found = shutil.which(name, path=search_path)
        if found:
            return found

    if platform.system() == "Darwin":
        for d in ("/opt/homebrew/bin", "/usr/local/bin"):
            for name in names:
                candidate = os.path.join(d, name)
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    return candidate
    elif platform.system() == "Windows":
        for name in names:
            for base in (r"C:\Program Files\Tesseract-OCR", *sorted(glob.glob(r"C:\Program Files\gs\gs*\bin"), reverse=True)):
                for ext in ("", ".exe"):
                    candidate = os.path.join(base, f"{name}{ext}")
                    if os.path.isfile(candidate):
                        return candidate
    return None


def check_system_deps() -> dict:
    """Inspect available built-in and external OCR dependencies."""
    env = get_augmented_env()
    gs_path = find_binary(["gswin64c", "gswin32c", "gs"], env=env)
    tess_path = find_binary(["tesseract"], env=env)
    ocr_cli_path = find_binary(["ocrmypdf"], env=env)
    brew_path = find_binary(["brew"], env=env) if platform.system() == "Darwin" else None
    winget_path = find_binary(["winget"], env=env) if platform.system() == "Windows" else None

    return {
        "rapidocr": RapidOCR is not None,
        "tesseract": tess_path,
        "ghostscript": gs_path,
        "ocrmypdf_cli": ocr_cli_path,
        "ocrmypdf_pkg": ocrmypdf_pkg is not None,
        "ocrmypdf": bool(ocr_cli_path or ocrmypdf_pkg is not None),
        "brew": brew_path,
        "winget": winget_path,
        "system": platform.system(),
    }


def _stream_process(cmd, env, log_callback):
    """Run a subprocess and stream combined stdout/stderr lines to log_callback."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if proc.stdout is not None:
        for line in proc.stdout:
            line = line.rstrip()
            if line and log_callback:
                log_callback(line)
    return proc.wait()


def install_system_deps(log_callback=None) -> bool:
    """Attempt unattended or assisted installation of system OCR dependencies."""
    def log(msg):
        if log_callback:
            log_callback(msg)

    env = get_augmented_env()
    system = platform.system()

    if system == "Windows":
        winget = find_binary(["winget"], env=env)
        if not winget:
            log("[ERROR] 'winget' was not found. You can still use Built-in Offline OCR without external installs.")
            return False

        ok = True
        for pkg_id, label in (
            ("UB-Mannheim.TesseractOCR", "Tesseract OCR"),
            ("ArtifexSoftware.Ghostscript", "Ghostscript"),
        ):
            log(f"[*] Installing {label} via winget (auto-accepting agreements)...")
            rc = _stream_process(
                [
                    winget,
                    "install",
                    "--id",
                    pkg_id,
                    "-e",
                    "--silent",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ],
                env,
                log,
            )
            if rc != 0:
                log(f"[WARNING] winget returned code {rc} for {label}.")
                ok = False

        if not getattr(sys, "frozen", False) and ocrmypdf_pkg is None:
            log("[*] Installing ocrmypdf Python package via pip...")
            rc = _stream_process([sys.executable, "-m", "pip", "install", "ocrmypdf"], env, log)
            if rc != 0:
                log(f"[WARNING] pip install ocrmypdf returned code {rc}.")
                ok = False
        return ok

    if system == "Darwin":
        brew = find_binary(["brew"], env=env)
        if brew:
            log(f"[*] Found Homebrew at {brew}. Installing ghostscript, tesseract, ocrmypdf (NONINTERACTIVE=1)...")
            brew_env = env.copy()
            brew_env["NONINTERACTIVE"] = "1"
            rc = _stream_process([brew, "install", "ghostscript", "tesseract", "ocrmypdf"], brew_env, log)
            if rc == 0:
                log("[OK] Homebrew OCR tools installed successfully.")
                return True
            log(f"[WARNING] brew install exited with code {rc}.")
            return False

        log("[INFO] Homebrew is not installed on this Mac.")
        log("[INFO] Installing Homebrew requires macOS administrator (sudo) password and Xcode Command Line Tools.")
        log("[INFO] Opening Terminal.app to run the official Homebrew + OCRmyPDF installer...")
        log("[TIP] If you prefer not to install Homebrew, select 'Built-in Offline OCR' — it works immediately with zero dependencies.")
        install_cmd = (
            'NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" '
            '&& eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null)" '
            '&& NONINTERACTIVE=1 brew install ghostscript tesseract ocrmypdf'
        )
        osa_script = f'tell application "Terminal"\nactivate\ndo script "{install_cmd.replace(chr(34), chr(92) + chr(34))}"\nend tell'
        try:
            subprocess.Popen(["osascript", "-e", osa_script])
            return True
        except Exception as ex:
            log(f"[ERROR] Failed to open Terminal.app: {ex}")
            return False

    log(f"[INFO] Automated install is only configured for Windows/macOS (current OS: {system}).")
    return False


def _get_rapidocr_instance():
    """Return a thread-local RapidOCR instance."""
    if RapidOCR is None:
        raise RuntimeError("rapidocr-onnxruntime is not installed in this environment.")
    if not hasattr(_THREAD_LOCAL, "rapidocr"):
        _THREAD_LOCAL.rapidocr = RapidOCR()
    return _THREAD_LOCAL.rapidocr


def _run_builtin_rapidocr(src_path: str, dst_path: str, dpi: int = 200) -> None:
    """Overlay an invisible searchable text layer onto PDF pages using RapidOCR + PyMuPDF."""
    ocr = _get_rapidocr_instance()
    scale = 72.0 / float(dpi)
    dst_dir = os.path.dirname(dst_path) or "."
    os.makedirs(dst_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", dir=dst_dir) as tmp_out:
        tmp_out_path = tmp_out.name

    try:
        doc = fitz.open(src_path)
        for page in doc:
            if page.get_text("text").strip():
                continue
            pix = page.get_pixmap(dpi=dpi)
            result, _ = ocr(pix.tobytes("png"))
            if not result:
                continue
            for item in result:
                if not item or len(item) < 2:
                    continue
                bbox, text = item[0], item[1]
                if not text or not str(text).strip():
                    continue
                xs = [pt[0] for pt in bbox]
                ys = [pt[1] for pt in bbox]
                x0 = min(xs) * scale
                y1 = max(ys) * scale
                box_h = max((max(ys) - min(ys)) * scale, 6.0)
                fontsize = max(4.0, min(box_h * 0.85, 72.0))
                page.insert_text(
                    fitz.Point(x0, y1),
                    str(text),
                    fontsize=fontsize,
                    render_mode=3,
                )
        doc.save(tmp_out_path, deflate=True, garbage=3)
        doc.close()
        os.replace(tmp_out_path, dst_path)
    finally:
        if os.path.exists(tmp_out_path):
            os.remove(tmp_out_path)


def _run_tesseract_only(src_path: str, dst_path: str, env: dict, dpi: int = 300) -> None:
    """Render PDF pages at 300 DPI via PyMuPDF and pipe PNGs into tesseract CLI for PDF output."""
    tess_bin = find_binary(["tesseract"], env=env)
    if not tess_bin:
        raise RuntimeError("Tesseract executable not found.")

    dst_dir = os.path.dirname(dst_path) or "."
    os.makedirs(dst_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", dir=dst_dir) as tmp_out:
        tmp_out_path = tmp_out.name

    src_doc = fitz.open(src_path)
    merged_doc = fitz.open()
    try:
        for page in src_doc:
            pix = page.get_pixmap(dpi=dpi)
            proc = subprocess.run(
                [tess_bin, "stdin", "stdout", "--dpi", str(dpi), "pdf"],
                input=pix.tobytes("png"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            if proc.returncode != 0 or not proc.stdout:
                err = proc.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"Tesseract failed (code {proc.returncode}): {err}")
            page_pdf = fitz.open("pdf", proc.stdout)
            merged_doc.insert_pdf(page_pdf)
            page_pdf.close()

        merged_doc.save(tmp_out_path, deflate=True, garbage=3)
        os.replace(tmp_out_path, dst_path)
    finally:
        src_doc.close()
        merged_doc.close()
        if os.path.exists(tmp_out_path):
            os.remove(tmp_out_path)


def _run_gs_ocrmypdf(src_path: str, dst_path: str, env: dict) -> None:
    """Standardize PDF at 300 DPI via Ghostscript, then run OCRmyPDF --force-ocr --clean."""
    gs_bin = find_binary(["gswin64c", "gswin32c", "gs"], env=env)
    tess_bin = find_binary(["tesseract"], env=env)
    ocr_cli = find_binary(["ocrmypdf"], env=env)
    if not gs_bin or not tess_bin or (not ocr_cli and ocrmypdf_pkg is None):
        raise RuntimeError("Ghostscript, Tesseract, and OCRmyPDF are all required for gs_ocrmypdf mode.")

    dst_dir = os.path.dirname(dst_path) or "."
    os.makedirs(dst_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", dir=dst_dir) as tmp_gs:
        tmp_gs_path = tmp_gs.name
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", dir=dst_dir) as tmp_out:
        tmp_out_path = tmp_out.name

    try:
        gs_cmd = [
            gs_bin,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/printer",
            "-dColorImageResolution=300",
            "-dGrayImageResolution=300",
            "-dMonoImageResolution=300",
            "-dNOPAUSE",
            "-dBATCH",
            f"-sOutputFile={tmp_gs_path}",
            src_path,
        ]
        gs_res = subprocess.run(gs_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        if gs_res.returncode != 0:
            err = gs_res.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Ghostscript failed (code {gs_res.returncode}): {err}")

        if ocr_cli:
            ocr_res = subprocess.run(
                [ocr_cli, "--force-ocr", "--clean", tmp_gs_path, tmp_out_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            if ocr_res.returncode != 0:
                err = ocr_res.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"OCRmyPDF failed (code {ocr_res.returncode}): {err}")
        else:
            ocrmypdf_pkg.ocr(tmp_gs_path, tmp_out_path, force_ocr=True, clean=True)

        os.replace(tmp_out_path, dst_path)
    finally:
        for p in (tmp_gs_path, tmp_out_path):
            if os.path.exists(p):
                os.remove(p)


def resolve_auto_mode(deps: dict) -> str:
    """Choose the best available OCR backend based on installed dependencies."""
    if deps.get("ghostscript") and deps.get("tesseract") and deps.get("ocrmypdf"):
        return "gs_ocrmypdf"
    if deps.get("tesseract"):
        return "tesseract_only"
    if deps.get("rapidocr"):
        return "builtin"
    raise RuntimeError("No OCR backend is available. Install rapidocr-onnxruntime or system Tesseract/OCRmyPDF.")


def ocr_single_pdf(src_path: str, dst_path: str, mode: str = "auto", env: dict = None) -> str:
    """Process one PDF from src_path to dst_path using the chosen or auto-resolved backend."""
    if env is None:
        env = get_augmented_env()

    resolved_mode = mode
    if mode == "auto":
        resolved_mode = resolve_auto_mode(check_system_deps())

    if resolved_mode == "gs_ocrmypdf":
        _run_gs_ocrmypdf(src_path, dst_path, env)
    elif resolved_mode == "tesseract_only":
        _run_tesseract_only(src_path, dst_path, env)
    elif resolved_mode == "builtin":
        _run_builtin_rapidocr(src_path, dst_path)
    else:
        raise ValueError(f"Unknown OCR engine mode: {mode}")

    return resolved_mode
