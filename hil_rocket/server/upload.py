import shutil
import logging
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = Path("uploads/stl")
ENG_DIR    = Path("uploads/eng")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ENG_DIR.mkdir(parents=True, exist_ok=True)


# ── STL upload (single assembly file) ────────────────────────────────────────

@router.post("/upload/stl/assembly")
async def upload_assembly_stl(file: UploadFile = File(...)):
    """
    Accepts the full rocket assembly STL.
    Saved as uploads/stl/assembly.stl — overwrites any previous upload.
    """
    if not file.filename.lower().endswith(".stl"):
        raise HTTPException(status_code=400, detail="Only .stl files are accepted")

    dest = UPLOAD_DIR / "assembly.stl"
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        logger.error(f"STL save failed: {e}")
        raise HTTPException(status_code=500, detail="File save failed")

    logger.info(f"Assembly STL saved: {dest}  ({dest.stat().st_size // 1024} KB)")
    return JSONResponse({"status": "ok", "path": str(dest)})


# ── .eng motor file upload ────────────────────────────────────────────────────

@router.post("/upload/eng")
async def upload_eng(file: UploadFile = File(...)):
    """
    Accepts a RASP .eng motor file, parses it, and returns motor parameters.
    """
    if not file.filename.lower().endswith(".eng"):
        raise HTTPException(status_code=400, detail="Only .eng files are accepted")

    dest = ENG_DIR / "custom.eng"
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save failed: {e}")

    try:
        from simulator.motors import parse_eng_file
        motor = parse_eng_file(str(dest))
        return JSONResponse(motor.summary())
    except Exception as e:
        logger.error(f".eng parse failed: {e}")
        raise HTTPException(status_code=400, detail=f"Could not parse .eng file: {e}")


# ── Serve assembly STL to the frontend viewer ─────────────────────────────────

from fastapi.responses import FileResponse as _FileResponse

@router.get("/upload/stl/assembly/file")
async def get_assembly_stl():
    """Serve the uploaded assembly STL so the flight viewer can load it."""
    path = UPLOAD_DIR / "assembly.stl"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No assembly STL uploaded yet")
    return _FileResponse(str(path), media_type="application/octet-stream")
