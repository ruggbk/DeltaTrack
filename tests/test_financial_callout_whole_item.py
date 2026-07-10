"""#86 — whole-item added/removed amounts reach the financial callout.

Headline case, asserted at the consumed output (the rendered callout, per the
issue): 119-hr-1 reported-in-house -> engrossed-in-house, Sec. 20004 (a). Ground
truth is one changed pair ($250M -> $500M) and one removed item ($250M). Before
#86 the callout reported a lone +$250M and was silent on the removal; it must now
surface the -$250M removal and net to $0.

The list renumbering also emits a net-zero +/-$350M shuffle pair (a position
shuffle the word-diff juxtaposes). Cleaning that noise is #87's scope, so this
test deliberately does NOT assert those rows away — only that the real removal is
surfaced and the net is honest.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bill_tree import normalize_bill
from diff_bill import bill_diff_to_dict, diff_bills
from formatters.canonical import view_from_canonical, xml_diff_to_canonical
from formatters.diff_html import _build_callout

BILLS_DIR = Path(__file__).parent.parent / "bills"
_V1 = BILLS_DIR / "119-hr-1" / "1_reported-in-house.xml"
_V2 = BILLS_DIR / "119-hr-1" / "2_engrossed-in-house.xml"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (_V1.exists() and _V2.exists()), reason="119-hr-1 XML corpus not present"),
]


def _sec_20004_a_callout() -> str:
    """Build the real diff and render the Sec. 20004 (a) Appropriations callout."""
    diff_dict = bill_diff_to_dict(diff_bills(normalize_bill(_V1), normalize_bill(_V2)), financial=True)
    view = view_from_canonical(xml_diff_to_canonical(diff_dict))
    # The (a) card is the one carrying the changed $250M -> $500M pair.
    cards = [c for c in view.changes if c.section_number == "Sec. 20004" and (250000000, 500000000) in c.amount_pairs]
    assert len(cards) == 1, f"expected exactly one Sec. 20004 (a) card, got {len(cards)}"
    return _build_callout(cards[0])


def test_sec_20004_callout_surfaces_removal():
    """The removed $250M appropriation shows as a removed row (previously silent)."""
    callout = _sec_20004_a_callout()
    assert "Removed:" in callout
    assert "$250,000,000" in callout


def test_sec_20004_callout_nets_to_zero():
    """Changed +$250M and removed -$250M cancel (as do the +/-$350M shuffle rows);
    the net is $0, not the old lone +$250M."""
    callout = _sec_20004_a_callout()
    assert "Net:" in callout
    assert ">$0</span>" in callout
