# -*- coding: utf-8 -*-
"""FastAPI web UI wrapper around pipeline.py.

Usage (after installing requirements):

    uvicorn web_app:app --reload --port 8000

Then open http://localhost:8000 in your browser.
"""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"

# Ensure expected directories exist when the app starts
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Video auto analysis & chapter generation",
    description="Web UI wrapper for pipeline.py (Whisper + GPT).",
)

# Allow cross-origin requests for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files from ./static
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=FileResponse)
def index() -> FileResponse:
    """Serve the main frontend page."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=404,
            detail="index.html not found. Please make sure static/index.html exists.",
        )
    return FileResponse(str(index_path))


def _run_pipeline(video_path: Path, chunk_seconds: int, api_key: str = "", api_base_url: str = "") -> Dict[str, Any]:
    """Call the existing pipeline.py script for the given video and read its outputs.

    This function shells out to the CLI pipeline you already have, so the
    original behavior is reused without modifying pipeline.py.
    """
    if not video_path.exists():
        raise HTTPException(status_code=400, detail="Video file does not exist.")

    ts = int(time.time())
    out_dir = OUTPUT_DIR / f"web_{ts}_{uuid.uuid4().hex[:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(BASE_DIR / "pipeline.py"),
        "--video",
        str(video_path),
        "--outdir",
        str(out_dir),
        "--chunk-seconds",
        str(chunk_seconds),
    ]

    # Inherit current environment and optionally override API settings
    env = os.environ.copy()
    if api_key:
        env["OPENAI_API_KEY"] = api_key
    if api_base_url:
        env["OPENAI_BASE_URL"] = api_base_url

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to process video. Please check server logs.\n\n"
                f"Command: {' '.join(cmd)}\n\nSTDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}"
            ),
        )

    summary_md = out_dir / "summary.md"
    chapters_json = out_dir / "chapters.json"
    segments_json = out_dir / "segments.json"
    transcript_txt = out_dir / "transcript.txt"

    if not summary_md.exists() or not chapters_json.exists() or not segments_json.exists():
        raise HTTPException(
            status_code=500,
            detail="pipeline.py finished but expected output files are missing.",
        )

    summary_raw = summary_md.read_text(encoding="utf-8", errors="ignore")
    summary_lines = [line for line in summary_raw.splitlines() if line.strip()]
    # Drop the first '# Summary' header line if present
    if summary_lines and summary_lines[0].lstrip().startswith("#"):
        summary_body = "\n".join(summary_lines[1:]).strip()
    else:
        summary_body = summary_raw.strip()

    try:
        chapters_data = json.loads(chapters_json.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        chapters_data = {"chapters": []}

    try:
        segments_data = json.loads(segments_json.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        segments_data = {"segments": []}

    transcript_preview = ""
    if transcript_txt.exists():
        full = transcript_txt.read_text(encoding="utf-8", errors="ignore")
        max_chars = 2000
        if len(full) > max_chars:
            transcript_preview = full[:max_chars] + "\n...\n(truncated; full transcript is stored on server in the output directory)"
        else:
            transcript_preview = full

    return {
        "summary": summary_body,
        "chapters": chapters_data.get("chapters", []),
        "segments": segments_data.get("segments", []),
        "transcript_preview": transcript_preview,
        "output_dir": str(out_dir.relative_to(BASE_DIR)),
    }


@app.post("/api/process")
async def process_video(
    file: UploadFile = File(..., description="Video file to analyze"),
    chunk_seconds: int = Form(600),
    api_key: str = Form("", description="OpenAI-compatible API key"),
    api_base_url: str = Form("", description="OpenAI-compatible base URL"),
) -> Dict[str, Any]:
    """Upload a video, run the pipeline, and return structured results as JSON."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Please upload a video file.")

    suffix = Path(file.filename).suffix or ".mp4"
    vid_name = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{suffix}"
    save_path = UPLOAD_DIR / vid_name

    try:
        with save_path.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    data = _run_pipeline(
        save_path,
        chunk_seconds=chunk_seconds,
        api_key=api_key,
        api_base_url=api_base_url,
    )
    return data
