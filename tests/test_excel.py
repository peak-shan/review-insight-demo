"""Verify multi-sheet imports, column aliases, provenance and input failures."""

from pathlib import Path

import pandas as pd
import pytest
from httpx import Response

from app.columns import identify_column, normalize_column
from app.imports import XLSX_MIME
from tests.test_app import client, upload


def workbook_file(tmp_path: Path, sheets: dict[str, pd.DataFrame]) -> Path:
    """Write test-only workbooks under pytest's temporary directory."""
    path = tmp_path / "reviews.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return path


def upload_excel(path: Path, filename: str = "reviews.xlsx", mime: str = XLSX_MIME) -> Response:
    """Upload a temporary workbook with an explicit timeout."""
    return client.post("/api/analyze", files={"file": (filename, path.read_bytes(), mime)}, timeout=10)


def test_multi_sheet_aliases_and_frequencies(tmp_path: Path) -> None:
    """Both alias styles contribute to independent positive and negative frequencies."""
    path = workbook_file(tmp_path, {
        "sheet1": pd.DataFrame({"好评点分析": ["柔软 soft", "柔软"], "差评点分析": ["缩水 bad", ""]}),
        "sheet2": pd.DataFrame({"好评": ["柔软 soft"], "差评": ["缩水 bad"]}),
        "空白": pd.DataFrame(),
        "说明": pd.DataFrame({"产品编号": ["A1"]}),
        "无文本": pd.DataFrame({"评论": ["   "]}),
    })
    response = upload_excel(path)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["total"], data["positive"], data["negative"], data["neutral"]) == (5, 3, 2, 0)
    assert data["positive_ratio"] == 3 / 5
    assert {item["word"]: item["count"] for item in data["positive_top_words"]} == {"柔软": 3, "soft": 2}
    assert {item["word"]: item["count"] for item in data["negative_top_words"]} == {"缩水": 2, "bad": 2}
    sheets = {sheet["source_sheet"]: sheet for sheet in data["sheets"]}
    assert (sheets["sheet1"]["total"], sheets["sheet2"]["total"]) == (3, 2)
    assert sheets["sheet1"]["recognized_columns"]["positive"] == ["好评点分析"]
    assert sheets["sheet2"]["recognized_columns"]["negative"] == ["差评"]
    assert all(sheets[name]["skipped_reason"] for name in ("空白", "说明", "无文本"))
    assert data["valid_rows"] == 3
    assert [(row["source_sheet"], row["source_row"]) for row in data["rows"]] == [("sheet1", 2), ("sheet1", 3), ("sheet2", 2)]
    assert sum(sheet["total"] for sheet in data["sheets"]) == data["total"]


def test_general_only_excel(tmp_path: Path) -> None:
    """General comment aliases use keyword sentiment and include ties as neutral."""
    path = workbook_file(tmp_path, {"用户评论": pd.DataFrame({"评论内容": ["soft", "bad", "soft bad", "blue", " ", None]})})
    data = upload_excel(path).json()
    assert (data["positive"], data["negative"], data["neutral"], data["total"]) == (1, 1, 2, 4)
    assert data["positive_ratio"] == data["negative_ratio"] == 0.25
    assert data["sheets"][0]["mode"] == "general"
    assert data["positive_top_words"] == [{"word": "soft", "count": 1}]
    assert data["negative_top_words"] == [{"word": "bad", "count": 1}]


def test_multiple_columns_and_mixed_modes(tmp_path: Path) -> None:
    """Dedicated cells count individually; general text only supplements neutral."""
    path = workbook_file(tmp_path, {
        "专用": pd.DataFrame({
            "好评": ["bad", ""], "好评点分析（正面）": ["soft", " "],
            "差评点分析": ["good", ""], "Review_Content": ["soft bad", "great"],
            "买家留言": ["blue", ""], "需求建议": ["expect pockets", ""],
        }),
        "通用": pd.DataFrame({"Feedback": ["good"]}),
    })
    data = upload_excel(path).json()
    assert (data["positive"], data["negative"], data["neutral"]) == (3, 1, 2)
    assert data["total"] == 6
    assert data["valid_rows"] == 2
    assert data["sheets"][0]["ignored_general"] == 1
    assert data["sheets"][0]["recognized_columns"]["positive"] == ["好评", "好评点分析（正面）"]
    assert data["rows"][0]["requirements"] == ["expect pockets"]
    assert "expect" not in {word["word"] for word in data["top_words"]}
    assert data["rows"][0]["positive"] == ["bad", "soft"]
    assert data["rows"][0]["negative"] == ["good"]


@pytest.mark.parametrize("column, role", [
    ("好评点分析（正面）", "positive"), ("Good Review", "positive"),
    (" POSITIVE_feedback ", "positive"), ("差评点分析", "negative"),
    ("好评/负面", "negative"), ("好评/差评", "negative"),
    ("Negative_Review", "negative"), ("BAD comments", "negative"),
    ("买家 留言", "general"), ("评论内容", "general"), ("评价", "general"),
    ("Content", "general"), ("Feedback", "general"),
    ("expectations", "requirement"), ("评论建议", "requirement"),
    ("产品编号", None),
])
def test_column_rules(column: str, role: str | None) -> None:
    """Normalize headers and resolve role collisions deterministically."""
    assert normalize_column("好评点分析（正面）") == "好评点分析正面"
    assert identify_column(column) == role


def test_no_review_columns_error(tmp_path: Path) -> None:
    """Missing-review errors list all sheet names and actual headers."""
    path = workbook_file(tmp_path, {
        "库存表": pd.DataFrame({"商品编号": ["A1"], "库存": [10]}),
        "需求表": pd.DataFrame({"建议": ["more colors"]}),
        "空表": pd.DataFrame(),
    })
    response = upload_excel(path)
    assert response.status_code == 400
    detail = response.json()["detail"]
    for text in ("好评/差评/评论", "库存表", "商品编号", "库存", "需求表", "建议", "空表"):
        assert text in detail
    csv_response = upload("编号,颜色\na,blue\n".encode())
    assert csv_response.status_code == 400
    assert "CSV" in csv_response.json()["detail"]
    assert "颜色" in csv_response.json()["detail"]


def test_excel_text_and_duplicate_headers(tmp_path: Path) -> None:
    """Keep text such as NA and repeated columns; ignore numeric and blank cells."""
    path = workbook_file(tmp_path, {"数据": pd.DataFrame(
        [["soft", "good", "NA"], [123, True, "N/A"], [None, " ", ""]],
        columns=["好评", "好评", "评论"],
    )})
    data = upload_excel(path).json()
    assert data["positive"] == 2
    assert data["neutral"] == 2
    assert data["sheets"][0]["recognized_columns"]["positive"] == ["好评", "好评"]


def test_format_detection_and_corruption(tmp_path: Path) -> None:
    """Filename takes priority, MIME handles missing suffix, malformed Excel is 400."""
    path = workbook_file(tmp_path, {"评价": pd.DataFrame({"评论": ["soft"]})})
    assert upload_excel(path, "BOOK.XLSX", "application/octet-stream").status_code == 200
    assert upload_excel(path, "upload", XLSX_MIME).status_code == 200
    assert upload_excel(path, "book.xls", XLSX_MIME).status_code == 415
    response = client.post("/api/analyze", files={"file": ("upload", b"comment\ngood", "text/csv; charset=utf-8")}, timeout=10)
    assert response.status_code == 200
    response = client.post("/api/analyze", files={"file": ("broken.xlsx", b"not a workbook", XLSX_MIME)}, timeout=10)
    assert response.status_code == 400
    assert "Excel" in response.json()["detail"]


def test_csv_smart_columns() -> None:
    """CSV also supports multiple dedicated columns and provenance."""
    response = upload("好评,好评点分析,差评\nsoft,good,bad\n".encode())
    assert response.status_code == 200
    data = response.json()
    assert (data["positive"], data["negative"], data["valid_rows"]) == (2, 1, 1)
    assert data["rows"][0]["source_sheet"] == "CSV"


def test_excel_aggregate_row_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Apply the row ceiling across worksheets, not independently to each sheet."""
    monkeypatch.setattr("app.imports.MAX_ROWS", 3)
    path = workbook_file(tmp_path, {name: pd.DataFrame({"评论": ["good", "bad"]}) for name in ("a", "b")})
    assert upload_excel(path).status_code == 400
