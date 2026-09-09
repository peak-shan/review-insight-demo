"""Exercise classification, CSV validation, and the complete sample upload."""

from pathlib import Path

import pytest
from httpx import Response
from fastapi.testclient import TestClient

from app.analytics import analyze_reviews
from app.main import MAX_BYTES, app

client = TestClient(app)


def upload(content: bytes) -> Response:
    """Send CSV bytes with an explicit HTTP timeout."""
    return client.post('/api/analyze', files={'file': ('reviews.csv', content, 'text/csv')}, timeout=10)


def test_analytics() -> None:
    """Check case folding, boundaries, stopwords, ties, and ratio denominator."""
    result = analyze_reviews(['舒服 SOFT soft the', 'uncomfortable', 'soft bad', 'blue', ' '])
    assert (result['positive'], result['negative'], result['neutral']) == (1, 1, 2)
    assert result['positive_ratio'] == result['negative_ratio'] == 0.25
    words = {item['word']: item['count'] for item in result['top_words']}
    assert words['soft'] == 3
    assert 'the' not in words
    assert analyze_reviews([])['positive_ratio'] == 0


def test_sample_and_page() -> None:
    """Check the static entry point and all thirty sample reviews."""
    page = client.get('/', timeout=10)
    assert page.status_code == 200
    assert 'echarts' in page.text
    response = upload(Path('sample_reviews.csv').read_bytes())
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 30
    assert (data['positive'], data['negative'], data['neutral']) == (15, 11, 4)
    assert len(data['top_words']) == 20


@pytest.mark.parametrize('content', [b'other\nhello', b'comment\n   ', b'comment\n\xff', b'comment\n"unfinished', b'comment\na,b', b'comment,comment\na,b'])
def test_invalid_csv(content: bytes) -> None:
    """Return actionable 400 errors for invalid CSV uploads."""
    assert upload(content).status_code == 400


def test_upload_limits_and_bom() -> None:
    """Accept UTF-8 BOM and quoted newlines; reject excessive upload size."""
    assert upload(b'x' * (MAX_BYTES + 1)).status_code == 413
    response = upload('\ufeffcomment\n"soft, good\ncomfortable"\n'.encode('utf-8'))
    assert response.status_code == 200
    assert response.json()['positive'] == 1
    assert upload(b'comment\n' + b'good\n' * 10001).status_code == 400
    assert client.post('/api/analyze', timeout=10).status_code == 422
