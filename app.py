import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pypdf import PdfReader, PdfWriter
from starlette.background import BackgroundTask


app = FastAPI(
    title="ConvertGeine PDF Compressor",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://convertgeine.com",
        "https://www.convertgeine.com",
        "http://localhost:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Disposition",
        "X-Original-Size",
        "X-Final-Size",
        "X-Saved-Percent",
        "X-Compression-Applied",
    ],
)

MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_PROCESSING_SECONDS = 240

CompressionLevel = Literal["maximum", "balanced", "quality"]


def remove_directory(directory: str) -> None:
    shutil.rmtree(directory, ignore_errors=True)


def sanitize_filename(filename: str) -> str:
    stem = Path(filename).stem
    safe_stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", stem).strip("-")
    return safe_stem or "document"


def ghostscript_options(level: CompressionLevel) -> list[str]:
    options: dict[str, list[str]] = {
        "maximum": [
            "-dPDFSETTINGS=/screen",
            "-dDownsampleColorImages=true",
            "-dColorImageDownsampleType=/Bicubic",
            "-dColorImageResolution=96",
            "-dDownsampleGrayImages=true",
            "-dGrayImageDownsampleType=/Bicubic",
            "-dGrayImageResolution=96",
            "-dDownsampleMonoImages=true",
            "-dMonoImageDownsampleType=/Subsample",
            "-dMonoImageResolution=150",
            "-dJPEGQ=45",
        ],
        "balanced": [
            "-dPDFSETTINGS=/ebook",
            "-dDownsampleColorImages=true",
            "-dColorImageDownsampleType=/Bicubic",
            "-dColorImageResolution=150",
            "-dDownsampleGrayImages=true",
            "-dGrayImageDownsampleType=/Bicubic",
            "-dGrayImageResolution=150",
            "-dDownsampleMonoImages=true",
            "-dMonoImageDownsampleType=/Subsample",
            "-dMonoImageResolution=300",
            "-dJPEGQ=68",
        ],
        "quality": [
            "-dPDFSETTINGS=/printer",
            "-dDownsampleColorImages=true",
            "-dColorImageDownsampleType=/Bicubic",
            "-dColorImageResolution=220",
            "-dDownsampleGrayImages=true",
            "-dGrayImageDownsampleType=/Bicubic",
            "-dGrayImageResolution=220",
            "-dDownsampleMonoImages=true",
            "-dMonoImageDownsampleType=/Subsample",
            "-dMonoImageResolution=300",
            "-dJPEGQ=82",
        ],
    }

    return options[level]


def validate_pdf_header(path: Path) -> bool:
    try:
        with path.open("rb") as pdf_file:
            return pdf_file.read(5) == b"%PDF-"
    except OSError:
        return False


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "ConvertGeine PDF Compressor",
        "status": "running",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "ghostscript": shutil.which("gs") or "not-found",
    }


@app.post("/compress")
async def compress_pdf(
    file: UploadFile = File(...),
    level: CompressionLevel = Form("balanced"),
):
    original_filename = file.filename or "document.pdf"

    if not original_filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="The selected file must be a PDF.",
        )

    work_directory = tempfile.mkdtemp(prefix="convertgeine-")
    input_path = Path(work_directory) / "input.pdf"
    compressed_path = Path(work_directory) / "compressed.pdf"
    final_path = Path(work_directory) / "final.pdf"

    try:
        original_size = 0

        with input_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                original_size += len(chunk)

                if original_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="The PDF must be 25 MB or smaller.",
                    )

                destination.write(chunk)

        await file.close()

        if original_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded PDF is empty.",
            )

        if not validate_pdf_header(input_path):
            raise HTTPException(
                status_code=400,
                detail="The selected file is not a valid PDF.",
            )

        command = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.6",
            "-dNOPAUSE",
            "-dBATCH",
            "-dQUIET",
            "-dSAFER",
            "-dDetectDuplicateImages=true",
            "-dCompressFonts=true",
            "-dSubsetFonts=true",
            "-dAutoRotatePages=/None",
            "-dPreserveAnnots=true",
            "-dPreserveMarkedContent=true",
            *ghostscript_options(level),
            f"-sOutputFile={compressed_path}",
            str(input_path),
        ]

        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=MAX_PROCESSING_SECONDS,
            check=False,
        )

        if process.returncode != 0 or not compressed_path.exists():
            diagnostic = f"{process.stderr}\n{process.stdout}".lower()

            if "password" in diagnostic or "encrypted" in diagnostic:
                message = (
                    "Password-protected or encrypted PDFs "
                    "are not supported."
                )
            else:
                message = (
                    "The PDF could not be compressed. "
                    "It may be damaged or unsupported."
                )

            raise HTTPException(status_code=422, detail=message)

        compressed_size = compressed_path.stat().st_size

        compression_applied = (
            compressed_size > 0 and compressed_size < original_size
        )

        source_path = compressed_path if compression_applied else input_path
        shutil.copyfile(source_path, final_path)

        final_size = final_path.stat().st_size

        saved_percent = (
            max(0, round((1 - final_size / original_size) * 100))
            if compression_applied
            else 0
        )

        safe_name = sanitize_filename(original_filename)
        download_name = f"compressed-{safe_name}.pdf"

        return FileResponse(
            path=final_path,
            media_type="application/pdf",
            filename=download_name,
            headers={
                "Cache-Control": "no-store",
                "X-Original-Size": str(original_size),
                "X-Final-Size": str(final_size),
                "X-Saved-Percent": str(saved_percent),
                "X-Compression-Applied": (
                    "yes" if compression_applied else "no"
                ),
            },
            background=BackgroundTask(
                remove_directory,
                work_directory,
            ),
        )

    except HTTPException:
        remove_directory(work_directory)
        raise

    except subprocess.TimeoutExpired:
        remove_directory(work_directory)

        raise HTTPException(
            status_code=504,
            detail="Compression took too long. Try a smaller PDF.",
        )

    except Exception as error:
        remove_directory(work_directory)
        print("Unexpected compression error:", repr(error))

        raise HTTPException(
            status_code=500,
            detail="An unexpected compression error occurred.",
        )


@app.post("/merge")
async def merge_pdfs(
    files: list[UploadFile] = File(...),
):
    if len(files) < 2:
        raise HTTPException(
            status_code=400,
            detail="Please upload at least two PDF files.",
        )

    if len(files) > 20:
        raise HTTPException(
            status_code=400,
            detail="You can merge a maximum of 20 PDF files at once.",
        )

    work_directory = tempfile.mkdtemp(prefix="convertgeine-merge-")
    output_path = Path(work_directory) / "merged.pdf"

    writer = PdfWriter()
    total_size = 0
    input_paths: list[Path] = []

    try:
        for index, uploaded_file in enumerate(files):
            filename = uploaded_file.filename or f"document-{index + 1}.pdf"

            if not filename.lower().endswith(".pdf"):
                raise HTTPException(
                    status_code=400,
                    detail=f"{filename} is not a PDF file.",
                )

            input_path = Path(work_directory) / f"input-{index}.pdf"
            file_size = 0

            with input_path.open("wb") as destination:
                while True:
                    chunk = await uploaded_file.read(1024 * 1024)

                    if not chunk:
                        break

                    file_size += len(chunk)
                    total_size += len(chunk)

                    if file_size > MAX_FILE_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail=f"{filename} exceeds the 25 MB limit.",
                        )

                    if total_size > 100 * 1024 * 1024:
                        raise HTTPException(
                            status_code=413,
                            detail="The combined upload must be 100 MB or smaller.",
                        )

                    destination.write(chunk)

            await uploaded_file.close()

            if file_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"{filename} is empty.",
                )

            if not validate_pdf_header(input_path):
                raise HTTPException(
                    status_code=400,
                    detail=f"{filename} is not a valid PDF.",
                )

            input_paths.append(input_path)

        for input_path in input_paths:
            reader = PdfReader(str(input_path))

            if reader.is_encrypted:
                raise HTTPException(
                    status_code=422,
                    detail="Password-protected PDFs cannot be merged.",
                )

            writer.append(reader)

        with output_path.open("wb") as output_file:
            writer.write(output_file)

        writer.close()

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise HTTPException(
                status_code=500,
                detail="The merged PDF could not be created.",
            )

        return FileResponse(
            path=output_path,
            media_type="application/pdf",
            filename="merged.pdf",
            headers={
                "Cache-Control": "no-store",
                "X-File-Count": str(len(files)),
                "X-Final-Size": str(output_path.stat().st_size),
            },
            background=BackgroundTask(
                remove_directory,
                work_directory,
            ),
        )

    except HTTPException:
        try:
            writer.close()
        except Exception:
            pass

        remove_directory(work_directory)
        raise

    except Exception as error:
        try:
            writer.close()
        except Exception:
            pass

        remove_directory(work_directory)
        print("Unexpected merge error:", repr(error))

        raise HTTPException(
            status_code=500,
            detail="The PDF files could not be merged.",
        )


def parse_page_selection(value: str, total_pages: int) -> list[int]:
    selected: list[int] = []
    seen: set[int] = set()

    for item in value.split(","):
        item = item.strip()

        if not item:
            continue

        if "-" in item:
            parts = item.split("-", 1)

            if len(parts) != 2:
                raise ValueError("Invalid page range.")

            start_text, end_text = parts[0].strip(), parts[1].strip()

            if not start_text.isdigit() or not end_text.isdigit():
                raise ValueError("Page ranges must contain numbers.")

            start = int(start_text)
            end = int(end_text)

            if start > end:
                raise ValueError(
                    f"Invalid range {start}-{end}. "
                    "The first page must be smaller."
                )

            page_numbers = range(start, end + 1)
        else:
            if not item.isdigit():
                raise ValueError(
                    "Pages must look like 1-3,5,7."
                )

            page_numbers = [int(item)]

        for page_number in page_numbers:
            if page_number < 1 or page_number > total_pages:
                raise ValueError(
                    f"Page {page_number} is outside the PDF. "
                    f"This document has {total_pages} pages."
                )

            zero_based_index = page_number - 1

            if zero_based_index not in seen:
                seen.add(zero_based_index)
                selected.append(zero_based_index)

    if not selected:
        raise ValueError("Please enter at least one page.")

    return selected


@app.post("/split")
async def split_pdf(
    file: UploadFile = File(...),
    pages: str = Form(...),
):
    original_filename = file.filename or "document.pdf"

    if not original_filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="The selected file must be a PDF.",
        )

    work_directory = tempfile.mkdtemp(
        prefix="convertgeine-split-"
    )
    input_path = Path(work_directory) / "input.pdf"
    output_path = Path(work_directory) / "split-pages.pdf"

    writer = PdfWriter()

    try:
        file_size = 0

        with input_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                file_size += len(chunk)

                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="The PDF must be 25 MB or smaller.",
                    )

                destination.write(chunk)

        await file.close()

        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded PDF is empty.",
            )

        if not validate_pdf_header(input_path):
            raise HTTPException(
                status_code=400,
                detail="The selected file is not a valid PDF.",
            )

        reader = PdfReader(str(input_path))

        if reader.is_encrypted:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Password-protected PDFs cannot be split."
                ),
            )

        total_pages = len(reader.pages)

        try:
            selected_pages = parse_page_selection(
                pages,
                total_pages,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            ) from error

        for page_index in selected_pages:
            writer.add_page(reader.pages[page_index])

        with output_path.open("wb") as output_file:
            writer.write(output_file)

        writer.close()

        if (
            not output_path.exists()
            or output_path.stat().st_size == 0
        ):
            raise HTTPException(
                status_code=500,
                detail="The split PDF could not be created.",
            )

        safe_name = sanitize_filename(original_filename)

        return FileResponse(
            path=output_path,
            media_type="application/pdf",
            filename=f"split-{safe_name}.pdf",
            headers={
                "Cache-Control": "no-store",
                "X-Original-Pages": str(total_pages),
                "X-Selected-Pages": str(len(selected_pages)),
                "X-Final-Size": str(output_path.stat().st_size),
            },
            background=BackgroundTask(
                remove_directory,
                work_directory,
            ),
        )

    except HTTPException:
        try:
            writer.close()
        except Exception:
            pass

        remove_directory(work_directory)
        raise

    except Exception as error:
        try:
            writer.close()
        except Exception:
            pass

        remove_directory(work_directory)
        print("Unexpected split error:", repr(error))

        raise HTTPException(
            status_code=500,
            detail="The PDF could not be split.",
        )
