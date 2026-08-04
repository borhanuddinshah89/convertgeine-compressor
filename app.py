import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

CompressionLevel = Literal["maximum", "balanced", "quality"]


def cleanup_directory(directory: str) -> None:
    shutil.rmtree(directory, ignore_errors=True)


def compression_arguments(level: CompressionLevel) -> list[str]:
    presets: dict[str, list[str]] = {
        "maximum": [
            "-dPDFSETTINGS=/screen",
            "-dColorImageResolution=96",
            "-dGrayImageResolution=96",
            "-dMonoImageResolution=150",
            "-dJPEGQ=45",
        ],
        "balanced": [
            "-dPDFSETTINGS=/ebook",
            "-dColorImageResolution=150",
            "-dGrayImageResolution=150",
            "-dMonoImageResolution=300",
            "-dJPEGQ=68",
        ],
        "quality": [
            "-dPDFSETTINGS=/printer",
            "-dColorImageResolution=220",
            "-dGrayImageResolution=220",
            "-dMonoImageResolution=300",
            "-dJPEGQ=82",
        ],
    }

    return presets[level]


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "ConvertGeine PDF Compressor",
        "status": "running",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/compress")
async def compress_pdf(
    file: UploadFile = File(...),
    level: CompressionLevel = Form("balanced"),
):
    original_name = file.filename or "document.pdf"

    if not original_name.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="The selected file must be a PDF.",
        )

    work_directory = tempfile.mkdtemp(prefix="convertgeine-")
    input_path = Path(work_directory) / "input.pdf"
    compressed_path = Path(work_directory) / "compressed.pdf"
    final_path = Path(work_directory) / "final.pdf"

    try:
        total_size = 0

        with input_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="The PDF must be 25 MB or smaller.",
                    )

                destination.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded PDF is empty.",
            )

        command = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.6",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            "-dSAFER",
            "-dDetectDuplicateImages=true",
            "-dCompressFonts=true",
            "-dSubsetFonts=true",
            "-dAutoRotatePages=/None",
            *compression_arguments(level),
            f"-sOutputFile={compressed_path}",
            str(input_path),
        ]

        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

        if process.returncode != 0 or not compressed_path.exists():
            error_text = (process.stderr or process.stdout).lower()

            if "password" in error_text or "encrypted" in error_text:
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
            compressed_size > 0 and compressed_size < total_size
        )

        if compression_applied:
            shutil.copyfile(compressed_path, final_path)
        else:
            shutil.copyfile(input_path, final_path)

        final_size = final_path.stat().st_size

        saved_percent = (
            round((1 - final_size / total_size) * 100)
            if compression_applied
            else 0
        )

        safe_stem = "".join(
            character
            if character.isalnum() or character in "._-"
            else "-"
            for character in Path(original_name).stem
        ).strip("-") or "document"

        download_name = f"compressed-{safe_stem}.pdf"

        return FileResponse(
            path=final_path,
            media_type="application/pdf",
            filename=download_name,
            headers={
                "Cache-Control": "no-store",
                "X-Original-Size": str(total_size),
                "X-Final-Size": str(final_size),
                "X-Saved-Percent": str(saved_percent),
                "X-Compression-Applied": (
                    "yes" if compression_applied else "no"
                ),
            },
            background=BackgroundTask(
                cleanup_directory,
                work_directory,
            ),
        )

    except HTTPException:
        cleanup_directory(work_directory)
        raise

    except subprocess.TimeoutExpired:
        cleanup_directory(work_directory)
        raise HTTPException(
            status_code=504,
            detail="Compression took too long. Try a smaller PDF.",
        )

    except Exception as error:
        cleanup_directory(work_directory)
        print("Compression error:", repr(error))

        raise HTTPException(
            status_code=500,
            detail="An unexpected compression error occurred.",
        )
