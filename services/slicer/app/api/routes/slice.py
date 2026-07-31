from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import PurePath, PureWindowsPath

from fastapi import APIRouter, File, Form, UploadFile

from app.schemas.slice import SliceResponse
from app.services.slicer import slice_model

router = APIRouter(tags=["slicing"])


@router.post("/slice", response_model=SliceResponse)
async def slice_endpoint(
    model_file: UploadFile = File(...),
    profile_name: str | None = Form(None),
    center: str | None = Form("128,128"),
    preserve_orientation: bool | None = Form(None),
    slicer_options: str | None = Form(None),
):
    options = json.loads(slicer_options) if slicer_options else None

    tmp_dir = tempfile.mkdtemp()
    uploaded_name = model_file.filename or "model.stl"
    filename = PurePath(PureWindowsPath(uploaded_name).name).name or "model.stl"
    model_path = os.path.join(tmp_dir, filename)

    try:
        with open(model_path, "wb") as f:
            content = await model_file.read()
            f.write(content)

        result = slice_model(
            model_path=model_path,
            profile_name=profile_name,
            center=center,
            slicer_options=options,
            preserve_orientation=preserve_orientation,
        )
        return result
    except Exception as exc:
        return SliceResponse(
            success=False,
            error=f"Slicing failed: {exc}",
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
