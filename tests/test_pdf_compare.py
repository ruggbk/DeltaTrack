"""Tests for the web service's PDF compare wrap (server/).

Two layers:
  - Fast API-guard tests (no real diffing) — validate upload rejection paths
    via FastAPI's TestClient. Skipped if fastapi isn't installed.
  - A slow end-to-end test that runs the real engine on the committed HR4366
    sample PDFs and validates the result against the canonical JSON schema.
    Skipped if the sample PDFs aren't present (they're large / not in CI).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from corpus_paths import FIXTURES_DIR, fixture_path

ROOT = Path(__file__).resolve().parent.parent
BILL_DIR = FIXTURES_DIR / "118-hr-4366"
SCHEMA = ROOT / "schema" / "canonical-diff.schema.json"


# ---------- Fast API-guard tests -------------------------------------------


def _client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from server.app import app

    return TestClient(app)


def test_http_redirects_to_https_for_get():
    resp = _client().get(
        "/index.html",
        headers={"X-Forwarded-Proto": "http", "Host": "deltatrack.agoradmv.org"},
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["location"] == "https://deltatrack.agoradmv.org/index.html"


def test_http_redirects_to_https_when_forwarded_port_80():
    resp = _client().get(
        "/",
        headers={"X-Forwarded-Port": "80", "Host": "deltatrack.agoradmv.org"},
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["location"] == "https://deltatrack.agoradmv.org/"


def test_http_redirects_to_https_for_post():
    resp = _client().post(
        "/api/compare",
        headers={"X-Forwarded-Proto": "http", "Host": "deltatrack.agoradmv.org"},
        follow_redirects=False,
    )
    assert resp.status_code == 308
    assert resp.headers["location"] == "https://deltatrack.agoradmv.org/api/compare"


def test_no_redirect_without_forwarded_proto():
    resp = _client().get("/", follow_redirects=False)
    assert resp.status_code == 200


def test_security_headers_on_served_page():
    """Every response carries the baseline security headers (#64).

    `nosniff` stops a browser second-guessing a declared Content-Type, and
    `DENY` stops the site being framed. Nothing here is served for framing:
    the sample report and generated reports both open in a new tab
    (webapp/index.html, webapp/js/compare.js), so DENY costs nothing.
    """
    resp = _client().get("/", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_security_headers_on_rejected_upload():
    """The headers wrap the API too, not just the static mount.

    A rejection is the response most likely to render attacker-influenced
    content, so it is the one that most needs `nosniff`.
    """
    resp = _client().post(
        "/api/compare",
        files={
            "start_file": ("a.pdf", b"not a pdf at all", "application/pdf"),
            "end_file": ("b.pdf", b"%PDF-1.4 whatever", "application/pdf"),
        },
    )
    assert resp.status_code == 415
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_security_headers_survive_the_https_redirect():
    """The headers reach a response that short-circuits the chain (#64).

    The https redirect returns without calling the rest of the stack, so it
    only carries these headers if the header middleware wraps the redirect
    one. That depends on registration order, which is easy to change without
    noticing; this pins it.
    """
    resp = _client().get(
        "/",
        headers={"X-Forwarded-Proto": "http", "Host": "deltatrack.agoradmv.org"},
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_report_sized_html_is_gzipped():
    """Report-sized HTML compresses ~6x, and on an office connection the
    transfer is the dominant cost of using the tool (#354). The sample report
    is the largest committed page the static mount serves; it stands in for a
    generated report without running the engine.

    The security headers must survive compression: gzip wraps the header
    middleware, and a reordering that drops them would pass a body-only check.
    """
    resp = _client().get("/sample/example.html", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") == "gzip"
    assert resp.headers["x-frame-options"] == "DENY"
    # httpx decodes transparently; the document must round-trip intact.
    assert "</html>" in resp.text


def test_generated_report_response_is_gzipped(monkeypatch):
    """/api/compare's own HTML response is compressed, not just static files.

    A minimum_size threshold can exclude one path and not the other (#354), so
    the API route is checked separately, with the engine stubbed out to keep
    this in the fast group.
    """
    import server.app as app_module

    fake_html = "<!DOCTYPE html><html>" + ("report " * 20_000) + "</html>"
    monkeypatch.setitem(app_module._COMPARE, "pdf", (".pdf", lambda *a, **kw: fake_html, lambda *a, **kw: {}))
    resp = _client().post(
        "/api/compare",
        files={
            "start_file": ("v1.pdf", b"%PDF-1.4 start", "application/pdf"),
            "end_file": ("v2.pdf", b"%PDF-1.4 end", "application/pdf"),
        },
        headers={"Accept-Encoding": "gzip"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") == "gzip"
    assert resp.text == fake_html


def test_small_responses_are_not_compressed():
    """Tiny JSON rejections stay below minimum_size and skip compression —
    gzip overhead on a 50-byte body is pure waste (#354)."""
    resp = _client().post(
        "/api/compare",
        files={
            "start_file": ("a.pdf", b"not a pdf at all", "application/pdf"),
            "end_file": ("b.pdf", b"%PDF-1.4 whatever", "application/pdf"),
        },
        headers={"Accept-Encoding": "gzip"},
    )
    assert resp.status_code == 415
    assert "content-encoding" not in resp.headers


def test_compare_rejects_non_pdf():
    # start_file lacks the %PDF magic → 415 before any diffing happens.
    resp = _client().post(
        "/api/compare",
        files={
            "start_file": ("a.pdf", b"not a pdf at all", "application/pdf"),
            "end_file": ("b.pdf", b"%PDF-1.4 whatever", "application/pdf"),
        },
    )
    assert resp.status_code == 415


def test_compare_rejects_empty_file():
    resp = _client().post(
        "/api/compare",
        files={
            "start_file": ("a.pdf", b"", "application/pdf"),
            "end_file": ("b.pdf", b"%PDF-1.4 whatever", "application/pdf"),
        },
    )
    assert resp.status_code == 400


def test_compare_xml_rejects_non_xml():
    # format=xml but the bytes don't start with "<" → 415 before any diffing.
    resp = _client().post(
        "/api/compare?format=xml",
        files={
            "start_file": ("a.xml", b"not xml at all", "application/xml"),
            "end_file": ("b.xml", b"<?xml version='1.0'?><bill/>", "application/xml"),
        },
    )
    assert resp.status_code == 415


def test_compare_pdf_bytes_rejected_when_format_xml():
    # A PDF uploaded under the XML option is caught by the magic-byte check.
    resp = _client().post(
        "/api/compare?format=xml",
        files={
            "start_file": ("a.pdf", b"%PDF-1.4 whatever", "application/pdf"),
            "end_file": ("b.xml", b"<?xml version='1.0'?><bill/>", "application/xml"),
        },
    )
    assert resp.status_code == 415


# ---------- Enrolled-layout decline guard (#141) ---------------------------
#
# Enrolled prints carry no GPO margin line numbers, so every anchor path returns
# nothing and the diff silently degrades to one giant block instead of raising.
# The guard must decline; these tests pin both the refusal and the happy path.

ENROLLED_PDF = fixture_path("115-hr-5895", "5_enrolled-bill.pdf")
NUMBERED_PDF = fixture_path("118-hr-8752", "1_reported-in-house.pdf")


def _line(n):
    from parsers.pdf_text import Line

    return Line(n, "text")


def _pages(numbered: int, unnumbered: int, *, per_page: int = 50):
    """One synthetic doc with the given mix of numbered/unnumbered lines."""
    from parsers.pdf_text import Page

    lines = [_line(i + 1) for i in range(numbered)] + [_line(None) for _ in range(unnumbered)]
    return [
        Page(p + 1, tuple(lines[p * per_page : (p + 1) * per_page]))
        for p in range((len(lines) + per_page - 1) // per_page)
    ]


def test_unnumbered_layout_is_detected():
    # Enrolled shape: 14 stray numbered lines out of 3,808 (115-hr-5895 v5).
    from server.pdf_compare import _is_unnumbered_layout

    assert _is_unnumbered_layout(_pages(14, 3794)) is True


def test_numbered_layout_is_not_detected():
    # Lowest ratio among real numbered prints in the corpus is ~0.90.
    from server.pdf_compare import _is_unnumbered_layout

    assert _is_unnumbered_layout(_pages(900, 100)) is False


def test_short_document_is_not_declined():
    # Short amendment prints in the corpus run 0.18-0.43 numbered over 21-28
    # lines, so the ratio alone would decline them. The size floor is what keeps
    # the guard from rejecting them; this pins that.
    from server.pdf_compare import _is_unnumbered_layout

    assert _is_unnumbered_layout(_pages(4, 18)) is False


def test_miss_window_stays_narrow():
    # Everything under the floor is EXEMPT, so the floor IS the window in which
    # the silent wrong answer survives. A 4-page unnumbered slice of a real
    # enrolled bill diffs to one anchorless block with a 200 OK, so raising this
    # floor re-opens the bug the guard exists to close. Pinned so a future change
    # to _MIN_LINES_FOR_GUARD has to be deliberate.
    from server.pdf_compare import _MIN_LINES_FOR_GUARD, _is_unnumbered_layout

    assert _MIN_LINES_FOR_GUARD <= 50
    # An unnumbered document just above the floor must still be declined.
    assert _is_unnumbered_layout(_pages(0, _MIN_LINES_FOR_GUARD)) is True


@pytest.mark.slow
def test_enrolled_pdf_is_declined_not_silently_diffed():
    if not ENROLLED_PDF.exists():
        pytest.skip("enrolled sample PDF not present (tests/corpus/115-hr-5895/)")

    from server.pdf_compare import UnsupportedLayoutError, compare_pdfs

    with pytest.raises(UnsupportedLayoutError):
        compare_pdfs(ENROLLED_PDF.read_bytes(), ENROLLED_PDF.read_bytes())


@pytest.mark.slow
def test_enrolled_pdf_declined_when_only_one_side_is_enrolled():
    # The real staffer gesture: diff a numbered version against the enrolled one.
    if not ENROLLED_PDF.exists() or not NUMBERED_PDF.exists():
        pytest.skip("sample PDFs not present")

    from server.pdf_compare import UnsupportedLayoutError, compare_pdfs

    with pytest.raises(UnsupportedLayoutError):
        compare_pdfs(NUMBERED_PDF.read_bytes(), ENROLLED_PDF.read_bytes())


@pytest.mark.slow
def test_enrolled_upload_returns_specific_message_not_generic_422():
    if not ENROLLED_PDF.exists():
        pytest.skip("enrolled sample PDF not present (tests/corpus/115-hr-5895/)")

    pdf = ENROLLED_PDF.read_bytes()
    resp = _client().post(
        "/api/compare",
        files={
            "start_file": ("start.pdf", pdf, "application/pdf"),
            "end_file": ("end.pdf", pdf, "application/pdf"),
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "enrolled" in detail.lower()
    assert "XML" in detail
    # Must not fall through to the catch-all's generic wording.
    assert "Are both valid bill-text" not in detail


@pytest.mark.slow
def test_numbered_pdfs_still_diff_after_guard():
    # The guard must not fire on the happy path.
    if not NUMBERED_PDF.exists():
        pytest.skip("sample PDF not present (tests/corpus/118-hr-8752/)")

    end = fixture_path("118-hr-8752", "2_engrossed-in-house.pdf")
    if not end.exists():
        pytest.skip("sample PDF not present (tests/corpus/118-hr-8752/)")

    from server.pdf_compare import compare_pdfs

    canonical = compare_pdfs(NUMBERED_PDF.read_bytes(), end.read_bytes())
    assert canonical["changes"]


# ---------- Slow end-to-end engine test ------------------------------------


@pytest.mark.slow
def test_compare_pdfs_returns_valid_canonical():
    start = BILL_DIR / "1_reported-in-house.pdf"
    end = BILL_DIR / "2_engrossed-in-house.pdf"
    if not start.exists() or not end.exists():
        pytest.skip("sample bill PDFs not present (tests/corpus/118-hr-4366/)")

    from server.pdf_compare import compare_pdfs

    canonical = compare_pdfs(
        start.read_bytes(),
        end.read_bytes(),
        start_label="Reported in House",
        end_label="Engrossed in House",
    )

    assert canonical["schema_version"]
    assert canonical["versions"]["v1"]["label"] == "Reported in House"
    assert canonical["versions"]["v2"]["label"] == "Engrossed in House"
    assert canonical["versions"]["v1"]["source"] == "pdf"
    assert isinstance(canonical["changes"], list) and canonical["changes"]
    assert canonical["full_text"]["v1"] and canonical["full_text"]["v2"]

    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text())
    jsonschema.validate(canonical, schema)


@pytest.mark.slow
def test_compare_pdfs_html_returns_standalone_report():
    start = BILL_DIR / "1_reported-in-house.pdf"
    end = BILL_DIR / "2_engrossed-in-house.pdf"
    if not start.exists() or not end.exists():
        pytest.skip("sample bill PDFs not present (tests/corpus/118-hr-4366/)")

    from server.pdf_compare import compare_pdfs_html

    html = compare_pdfs_html(
        start.read_bytes(),
        end.read_bytes(),
        start_label="Reported in House",
        end_label="Engrossed in House",
    )

    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "change-card" in html
    assert "financial-table" in html
    assert "Reported in House" in html
    assert "Engrossed in House" in html


@pytest.mark.slow
def test_compare_api_returns_html():
    start = BILL_DIR / "1_reported-in-house.pdf"
    end = BILL_DIR / "2_engrossed-in-house.pdf"
    if not start.exists() or not end.exists():
        pytest.skip("sample bill PDFs not present (tests/corpus/118-hr-4366/)")

    resp = _client().post(
        "/api/compare?output=html",
        files={
            "start_file": ("start.pdf", start.read_bytes(), "application/pdf"),
            "end_file": ("end.pdf", end.read_bytes(), "application/pdf"),
        },
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "change-card" in resp.text


def test_derive_congress_from_cover():
    from parsers.pdf_text import Line, Page
    from server.pdf_compare import _derive_congress

    page = Page(1, (Line(None, "118TH CONGRESS"), Line(None, "1ST SESSION H. R. 4366")))
    assert _derive_congress([page]) == "118"
    # No cover match → empty (renderer then omits the "th Congress" suffix).
    assert _derive_congress([Page(1, (Line(None, "AN ACT"),))]) == ""
    assert _derive_congress([]) == ""
