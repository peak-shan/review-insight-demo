"""Serve the dashboard and analyze uploaded CSV or Excel workbooks."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.imports import MAX_ROWS, ImportResult, analyze_sheets, detect_format, read_csv, read_xlsx

app = FastAPI(title="亚马逊评论关键词看板")
PAGE = Path(__file__).parent / "static" / "index.html"
MAX_BYTES = 2 * 1024 * 1024


@app.get("/", response_class=FileResponse)
def index() -> FileResponse:
    """Return the static dashboard page."""
    return FileResponse(PAGE)


@app.post("/api/analyze")
def analyze(file: UploadFile) -> ImportResult:
    """Detect the format and combine all sheets using normalized column roles."""
    try:
        raw = file.file.read(MAX_BYTES + 1)
    finally:
        file.file.close()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "文件不能超过 2 MB。")
    file_format = detect_format(file.filename, file.content_type)
    sheets = read_xlsx(raw) if file_format == "xlsx" else read_csv(raw)
    return analyze_sheets(sheets)
