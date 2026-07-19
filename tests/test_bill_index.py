"""Tests for bill_index CSV encode/decode round-trip (issue #61).

The write and read paths are asymmetric and worth testing together rather than
separately: writing goes through the hand-rolled ``_format_csv_cell``, while reading
goes through ``csv.DictReader`` (which already removes CSV quoting) and *then*
``_decode_value``. A cell therefore passes two unquoting stages, and only the
round-trip shows what the second one does to text the first one quoted.

Cases here are constructed from the declared domain rather than sampled from the
corpus. The index stores free text from bill XML (``title``, ``status``,
``policyArea``) alongside genuinely numeric counts, and the current corpus happens to
contain no title that would exercise the quote-decoding edges -- so corpus-derived
cases would bound only the observed input space, not the space the code accepts.

The known-latent decode defects are recorded as ``xfail(strict=True)``: they assert
the behavior the round-trip *should* have, so they neither pin the current mangling as
correct nor go silently stale. When the decode is fixed they xpass, and strict mode
turns that into a failure that prompts removing the marker. Tracked in #256.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bill_index.bill_index import BillIndex, _decode_value, _format_csv_cell


def round_trip(tmp_path: Path, value: object, column: str = "title") -> object:
    """Persist one field value through save() and read it back through load()."""
    csv_path = tmp_path / "bills.csv"
    index = BillIndex(csv_path)
    index.add_bills([{"id": "119-hr-1", column: value}], save=True)

    reloaded = BillIndex(csv_path)
    reloaded.load()
    return reloaded.get("119-hr-1")[column]


class TestFreeTextRoundTrip:
    """Free-text columns (title, status, policyArea) must survive unchanged.

    These carry bill titles and latest-action text straight from BILLSTATUS XML, so
    CSV-significant characters are ordinary content here, not edge cases.
    """

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("Consolidated Appropriations Act", id="plain"),
            pytest.param(
                "Making appropriations for the Departments of Commerce and Justice, "
                "Science, and Related Agencies, and for other purposes.",
                id="commas",
            ),
            pytest.param("Referred to the Committee on Appropriations.", id="sentence"),
            pytest.param('An Act to amend the "Clean Air Act" provisions', id="inner-quotes"),
            pytest.param("line one\nline two", id="embedded-newline"),
            pytest.param("line one\r\nline two", id="embedded-crlf"),
            # A lone CR needs its own case: the CRLF above is already quoted by the
            # "\n" clause, so it cannot tell whether the "\r" clause works. Without
            # that clause an unquoted CR makes csv.DictReader split one record into
            # two -- silent record inflation plus a truncated title.
            pytest.param("line one\rline two", id="embedded-lone-cr"),
            pytest.param("café — em dash, naïve", id="unicode"),
            pytest.param("“Scholarships for Opportunity Act”", id="curly-quoted-short-title"),
            pytest.param(r"path\to\thing", id="backslashes"),
            pytest.param('a","b', id="quote-comma-combo"),
            pytest.param("2025-01-01", id="iso-date"),
            pytest.param("1.5", id="float-like-stays-text"),
            pytest.param("True", id="bool-like-stays-text"),
            pytest.param("119-hr-1234", id="bill-id-shape"),
            pytest.param("", id="empty"),
        ],
    )
    def test_value_survives_the_round_trip_unchanged(self, tmp_path, value):
        assert round_trip(tmp_path, value) == value

    def test_curly_quoted_title_is_not_decoded(self, tmp_path):
        # Legislative short titles are typeset with curly quotes, so they do not hit
        # the straight-quote decode branch. Pinning this keeps a future "normalize
        # smart quotes" change from silently routing real titles into that branch.
        value = "“Scholarships for Opportunity and Results Reauthorization Act”"
        assert round_trip(tmp_path, value) == value


class TestNumericColumns:
    """Count columns are stored as ints and must come back as ints.

    ``historySize``, ``actionCount``, ``versionCount`` and friends are produced by
    ``len()`` / ``stat()``, and getting them back as ints is what keeps a reloaded
    index sortable and comparable without callers re-parsing every cell.

    Note this is the *motivation* for the int coercion, not its implementation.
    ``_decode_value`` takes a ``column`` argument and never reads it
    (``bill_index.py:280``), so the coercion is applied to every column including the
    free-text ones -- which is why a digits-only title does not survive the round
    trip. That case is recorded in ``TestKnownLatentDecodeDefects``.
    """

    @pytest.mark.parametrize("value", [0, 1, 42, 1000, 12345678901234567890])
    def test_int_round_trips_as_int(self, tmp_path, value):
        result = round_trip(tmp_path, value, column="actionCount")
        assert result == value
        assert isinstance(result, int)

    def test_negative_int_round_trips(self, tmp_path):
        # daysActive is a date subtraction and can legitimately be negative.
        result = round_trip(tmp_path, -3, column="daysActive")
        assert result == -3
        assert isinstance(result, int)

    def test_zero_is_not_confused_with_empty(self, tmp_path):
        # 0 and "" are different facts: no actions recorded vs field absent. The
        # empty-string short-circuit in _decode_value runs before the int parse, so
        # this pins that 0 does not fall into it.
        assert round_trip(tmp_path, 0, column="actionCount") == 0
        assert round_trip(tmp_path, "", column="actionCount") == ""


class TestDecodeValueUnit:
    """Direct unit coverage of _decode_value, below the CSV layer."""

    @pytest.mark.parametrize("value", [None, ""])
    def test_missing_values_decode_to_empty_string(self, value):
        assert _decode_value("title", value) == ""

    def test_digits_decode_to_int(self):
        assert _decode_value("actionCount", "42") == 42

    def test_non_numeric_text_is_returned_as_is(self):
        assert _decode_value("title", "An Act") == "An Act"

    def test_iso_date_is_not_coerced(self):
        assert _decode_value("introducedDate", "2025-01-01") == "2025-01-01"

    def test_unbalanced_quote_is_left_alone(self):
        # The decode branch requires a quote at *both* ends, so these bypass it.
        assert _decode_value("title", '"unterminated') == '"unterminated'
        assert _decode_value("title", 'trailing"') == 'trailing"'


class TestFormatCsvCell:
    def test_quotes_commas_and_newlines_are_escaped(self):
        assert _format_csv_cell("a,b") == '"a,b"'
        assert _format_csv_cell('say "hi"') == '"say ""hi"""'
        assert _format_csv_cell("a\nb") == '"a\nb"'

    def test_plain_text_is_not_quoted(self):
        assert _format_csv_cell("plain") == "plain"

    def test_none_becomes_empty(self):
        assert _format_csv_cell(None) == ""


class TestKnownLatentDecodeDefects:
    """Values that do not survive the round-trip today (#256).

    The quote cases below reach ``_decode_value`` with a string that starts and ends
    with a straight double quote -- which happens whenever the stored text itself
    begins and ends with one, because ``csv.DictReader`` has already removed the
    CSV-level quoting by then. The decode cannot distinguish "CSV quoting" from "the
    text contains quotes", and strips them either way. The remaining cases come from
    ``int()`` being used as a type sniffer, which accepts Python literal syntax.

    Not currently reachable from real data: no title in the committed corpus starts
    with a straight quote, and legislative short titles use curly quotes. These are
    latent (#256), which is why they are xfail rather than a fix inside a test-coverage
    change -- altering decode semantics would also change how existing bills.csv
    files are read.
    """

    @pytest.mark.xfail(
        strict=True,
        reason="#256: json.loads succeeds on the quoted text and silently unwraps it",
    )
    def test_text_wrapped_in_straight_quotes_keeps_its_quotes(self, tmp_path):
        # '"hello"' -> written as '"""hello"""' -> DictReader -> '"hello"' ->
        # json.loads('"hello"') -> 'hello'. The quotes are content, not syntax.
        value = '"hello"'
        assert round_trip(tmp_path, value) == value

    @pytest.mark.xfail(
        strict=True,
        reason="#256: JSONDecodeError fallback strips the outer quotes and unescapes",
    )
    def test_quote_wrapped_text_that_is_not_valid_json_keeps_its_quotes(self, tmp_path):
        # The fallback at bill_index.py:291-293. '"a"b"' -> DictReader -> '"a"b"' ->
        # not valid JSON -> value[1:-1].replace('""', '"') -> 'a"b'.
        value = '"a"b"'
        assert round_trip(tmp_path, value) == value

    @pytest.mark.xfail(
        strict=True,
        reason="#256: json.loads also interprets backslash escapes inside the quotes",
    )
    @pytest.mark.parametrize(
        "value",
        [
            pytest.param('"a\\nb"', id="literal-backslash-n-becomes-a-newline"),
            pytest.param('"\\u00e9"', id="unicode-escape-becomes-a-character"),
        ],
    )
    def test_escape_sequences_inside_quotes_are_not_interpreted(self, tmp_path, value):
        # A second, distinct corruption mode: where the quoted text happens to parse
        # as JSON, the decode does not merely unwrap it, it also resolves any escape
        # sequence inside. '"a\\nb"' comes back holding a real newline rather than the
        # two literal characters that were stored. This is the branch the
        # JSONDecodeError fallback does *not* share -- the fallback leaves escapes
        # alone -- so the two paths disagree on the same input shape.
        assert round_trip(tmp_path, value) == value

    @pytest.mark.xfail(
        strict=True,
        reason="#256: _decode_value ignores its column arg, so digits-only text becomes int",
    )
    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("2024", id="year-like-title"),
            pytest.param("117", id="congress-like-title"),
            pytest.param("0", id="zero-as-text"),
        ],
    )
    def test_digits_only_text_stays_text(self, tmp_path, value):
        # The reachable member of this family, and the reason it is listed here
        # rather than among the round-trip cases above: the coercion is column-blind,
        # so a *title* that happens to be all digits comes back as an int. Unlike the
        # quote and underscore cases, this needs no exotic input at all -- any
        # free-text field holding a bare year or number trips it.
        result = round_trip(tmp_path, value)
        assert result == value
        assert isinstance(result, str)

    @pytest.mark.xfail(
        strict=True,
        reason="#256: int() accepts underscore separators, so '1_000' becomes 1000",
    )
    def test_underscore_separated_digits_stay_text(self, tmp_path):
        # int('1_000') == 1000 is Python literal syntax leaking into a data decoder.
        assert round_trip(tmp_path, "1_000") == "1_000"

    @pytest.mark.xfail(
        strict=True,
        reason="#256: int() drops leading zeros, sign prefixes and surrounding space",
    )
    @pytest.mark.parametrize("value", ["007", "+5", " 12 "])
    def test_numeric_looking_text_keeps_its_exact_form(self, tmp_path, value):
        assert round_trip(tmp_path, value) == value
