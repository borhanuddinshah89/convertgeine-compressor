from fastapi import APIRouter

router = APIRouter(prefix="/pdf-to-jpg", tags=["PDF"])

@router.post("")
async def pdf_to_jpg():
    return {
        "status": "ok",
        "message": "PDF to JPG endpoint is ready for implementation."
    }
