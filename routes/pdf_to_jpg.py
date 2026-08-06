import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask


router = APIRouter(prefix="/pdf-to-jpg", tags=["PDF"])

MAX_FILE_SIZE = 25 * 1024 * 1024
PROCESSING_TIMEOUT = 240


def cleanup(directory: str) -> None:
    shutil.rmtree(directory, ignore_errors=True)


@router.post("")
async def pdf_to_jpg(file: UploadFile = File(...)):
    filename = file.filename or "document.pdf"

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Please choose a valid PDF file.",
        )

    work_directory = tempfile.mkdtemp(
        prefix="convertgeine-pdf-to-jpg-"
    )

    input_path = Path(work_directory) / "input.pdf"
    output_prefix = Path(work_directory) / "page"

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

        with input_path.open("rb") as pdf_file:
            if pdf_file.read(5) != b"%PDF-":
                raise HTTPException(
                    status_code=400,
                    detail="The selected file is not a valid PDF.",
                )

        process = subprocess.run(
            [
                "pdftoppm",
                "-jpeg",
                "-jpegopt",
                "quality=90",
                "-r",
                "150",
                str(input_path),
                str(output_prefix),
            ],
            capture_output=True,
            text=True,
            timeout=PROCESSING_TIMEOUT,
            check=False,
        )

        image_paths = sorted(
            Path(work_directory).glob("page-*.jpg")
        )

        if process.returncode != 0 or not image_paths:
            diagnostic = (
                f"{process.stdout}\n{process.stderr}"
            ).lower()

            if "password" in diagnostic or "encrypted" in diagnostic:
                message = (
                    "Password-protected PDFs are not supported."
                )
            else:
                message = (
                    "The PDF could not be converted. "
                    "It may be damaged or unsupported."
                )

            raise HTTPException(
                status_code=422,
                detail=message,
            )

        if len(image_paths) == 1:
            return FileResponse(
                path=image_paths[0],
                media_type="image/jpeg",
                filename="page-001.jpg",
                headers={
                    "Cache-Control": "no-store",
                    "X-Page-Count": "1",
                },
                background=BackgroundTask(
                    cleanup,
                    work_directory,
                ),
            )

        zip_path = Path(work_directory) / "pdf-images.zip"

        with zipfile.ZipFile(
            zip_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for index, image_path in enumerate(
                image_paths,
                start=1,
            ):
                archive.write(
                    image_path,
                    arcname=f"page-{index:03d}.jpg",
                )

        if not zip_path.exists() or zip_path.stat().st_size == 0:
            raise HTTPException(
                status_code=500,
                detail="The JPG archive could not be created.",
            )

        return FileResponse(
            path=zip_path,
            media_type="application/zip",
            filename="pdf-images.zip",
            headers={
                "Cache-Control": "no-store",
                "X-Page-Count": str(len(image_paths)),
                "X-Final-Size": str(zip_path.stat().st_size),
            },
            background=BackgroundTask(
                cleanup,
                work_directory,
            ),
        )

    except HTTPException:
        cleanup(work_directory)
        raise

    except subprocess.TimeoutExpired:
        cleanup(work_directory)
        raise HTTPException(
            status_code=504,
            detail="Conversion took too long. Try a smaller PDF.",
        )

    except Exception as error:
        cleanup(work_directory)
        print("PDF to JPG error:", repr(error))

        raise HTTPException(
            status_code=500,
            detail="The PDF could not be converted to JPG.",
        )
