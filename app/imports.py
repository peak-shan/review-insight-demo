"""Read CSV/Excel sheets and preserve provenance while building review corpora."""

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

import pandas as pd
from fastapi import HTTPException

from app.analytics import AnalysisResult, classify_review, summarize_corpora
from app.columns import COLUMN_RULES, ColumnRole, identify_column

MAX_ROWS = 10_000
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass
class SheetData:
    """A rectangular source table with original headers, including duplicate names."""

    name: str
    columns: list[str]
    rows: list[list[str]]


class ReviewRow(TypedDict):
    """One contributing source row; multiple cells may contribute to each corpus."""

    source_sheet: str
    source_row: int
    positive: list[str]
    negative: list[str]
    neutral: list[str]
    requirements: list[str]


class SheetReport(TypedDict):
    """Report every sheet, including skipped sheets and their original headers."""

    source_sheet: str
    columns: list[str]
    recognized_columns: dict[ColumnRole, list[str]]
    mode: Literal["dedicated", "general", "skipped"]
    read_rows: int
    valid_rows: int
    total: int
    positive: int
    negative: int
    neutral: int
    ignored_general: int
    skipped_reason: str | None


class ImportResult(AnalysisResult):
    """Analysis plus row provenance and per-sheet reconciliation totals."""

    valid_rows: int
    rows: list[ReviewRow]
    sheets: list[SheetReport]


def detect_format(filename: str | None, content_type: str | None) -> Literal["csv", "xlsx"]:
    """Prefer supported suffixes; fall back to MIME only if no suffix is supplied."""
    suffix = Path(filename or "").suffix.lower()
    if suffix in (".csv", ".xlsx"):
        return "xlsx" if suffix == ".xlsx" else "csv"
    if not suffix:
        mime = (content_type or "").split(";", 1)[0].strip().lower()
        if mime == XLSX_MIME:
            return "xlsx"
        if mime in ("text/csv", "application/csv"):
            return "csv"
    raise HTTPException(415, "仅支持 CSV / Excel（.csv / .xlsx）文件。")


def read_csv(raw: bytes) -> list[SheetData]:
    """Retain strict UTF-8 CSV parsing and validation from the original endpoint."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "请使用 UTF-8 编码的 CSV 文件。") from exc
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        columns = reader.fieldnames or []
        if len(columns) != len(set(columns)):
            raise HTTPException(400, "CSV 不能包含重复列名。")
        rows: list[list[str]] = []
        for row_number, row in enumerate(reader, start=1):
            if row_number > MAX_ROWS:
                raise HTTPException(400, "文件所有 sheet 合计最多支持 10000 行。")
            if None in row or any(value is None for value in row.values()):
                raise HTTPException(400, "CSV 行列数不一致，请检查引号和逗号。")
            rows.append([row[column].strip() for column in columns])
    except csv.Error as exc:
        raise HTTPException(400, "CSV 格式错误或单条评论过长。") from exc
    return [SheetData("CSV", columns, rows)]


def cell_text(value: object) -> str:
    """Keep textual cells only; blanks, numbers, dates and booleans are not reviews."""
    return value.strip() if isinstance(value, str) else ""


def read_xlsx(raw: bytes) -> list[SheetData]:
    """Read every sheet with pandas/openpyxl without mangling duplicate headers."""
    try:
        frames = pd.read_excel(
            io.BytesIO(raw), sheet_name=None, engine="openpyxl", header=None,
            dtype=object, keep_default_na=False, nrows=MAX_ROWS + 2,
        )
    except Exception as exc:
        # Parser failures for corrupt/encrypted/renamed workbooks are user input errors.
        raise HTTPException(400, "Excel 文件读取失败，请确认是未加密且未损坏的 .xlsx 文件。") from exc
    sheets: list[SheetData] = []
    row_count = 0
    for name, frame in frames.items():
        if frame.empty:
            sheets.append(SheetData(str(name), [], []))
            continue
        columns = [str(value).strip() for value in frame.iloc[0]]
        rows = [[cell_text(value) for value in row] for row in frame.iloc[1:].itertuples(index=False, name=None)]
        row_count += len(rows)
        if row_count > MAX_ROWS:
            raise HTTPException(400, "文件所有 sheet 合计最多支持 10000 行。")
        sheets.append(SheetData(str(name), columns, rows))
    return sheets


def analyze_sheets(sheets: list[SheetData]) -> ImportResult:
    """Combine per-sheet classified rows; dedicated columns override general sentiment."""
    merged: list[ReviewRow] = []
    reports: list[SheetReport] = []
    corpora: dict[str, list[str]] = {"positive": [], "negative": [], "neutral": []}
    any_review_column = False
    for sheet in sheets:
        positions: dict[ColumnRole, list[int]] = {role: [] for role in COLUMN_RULES}
        for index, column in enumerate(sheet.columns):
            if role := identify_column(column):
                positions[role].append(index)
        dedicated = bool(positions["positive"] or positions["negative"])
        has_reviews = dedicated or bool(positions["general"])
        any_review_column |= has_reviews
        report: SheetReport = {
            "source_sheet": sheet.name, "columns": sheet.columns,
            "recognized_columns": {role: [sheet.columns[i] for i in indices] for role, indices in positions.items()},
            "mode": "dedicated" if dedicated else "general" if has_reviews else "skipped",
            "read_rows": len(sheet.rows), "valid_rows": 0, "total": 0,
            "positive": 0, "negative": 0, "neutral": 0, "ignored_general": 0,
            "skipped_reason": None,
        }
        for source_row, cells in enumerate(sheet.rows, start=2):
            if not has_reviews:
                break
            row: ReviewRow = {
                "source_sheet": sheet.name, "source_row": source_row,
                "positive": [], "negative": [], "neutral": [],
                "requirements": [cells[i] for i in positions["requirement"] if cells[i]],
            }
            for role in ("positive", "negative"):
                row[role].extend(cells[i] for i in positions[role] if cells[i])
            for index in positions["general"]:
                if not (text := cells[index]):
                    continue
                sentiment = classify_review(text)
                if dedicated and sentiment != "neutral":
                    report["ignored_general"] += 1
                    continue
                row[sentiment].append(text)
            if any(row[role] for role in corpora):
                merged.append(row)
                report["valid_rows"] += 1
                for role in corpora:
                    corpora[role].extend(row[role])
                    report[role] += len(row[role])
                    report["total"] += len(row[role])
        if not report["total"]:
            report["skipped_reason"] = "未识别到评论类列" if not has_reviews else "没有可计入的非空评论文本"
        reports.append(report)
    if not any_review_column:
        details = "；".join(f"sheet「{sheet.name}」列名：{sheet.columns!r}" for sheet in sheets) or "工作簿无 sheet"
        raise HTTPException(400, f"未识别到任何评论类列，需要“好评/差评/评论”类列。实际读取：{details}")
    if not merged:
        raise HTTPException(400, "已识别到评论类列，但没有可计入的有效评论；请填写非空评论文本。")
    return {
        **summarize_corpora(corpora["positive"], corpora["negative"], corpora["neutral"]),
        "valid_rows": len(merged), "rows": merged, "sheets": reports,
    }
