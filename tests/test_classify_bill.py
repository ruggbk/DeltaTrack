"""Unit tests for notebooks/classify_bill.py — classify_text() behavior.

Covers every label outcome and the ordering/edge cases that matter:
- subsection prefix variants (RESTRICT, APPROP) — fixed in #115
- APPROP + RESCISSION interaction
- AUTHORIZATION ordering (fires after APPROP_ALT so hybrid nodes stay appropriation)
- RESTRICT_NOTWITHSTANDING
- unknown fallthrough
"""

from notebooks.classify_bill import classify_text


class TestRestriction:
    def test_plain_none_of_funds(self):
        text = "None of the funds made available in this Act may be used to pay"
        assert classify_text(text) == "restriction"

    def test_subsection_prefix(self):
        # Fixed in #115: was \s+ (required space), now \s* (allows no space)
        text = "(b)None of the funds made available under this heading"
        assert classify_text(text) == "restriction"

    def test_subsection_prefix_with_space(self):
        text = "(a) None of the funds appropriated under this section"
        assert classify_text(text) == "restriction"

    def test_notwithstanding_variant(self):
        text = (
            "Notwithstanding any other provision of law, none of the funds made available in this Act may be obligated"
        )
        assert classify_text(text) == "restriction"

    def test_notwithstanding_long_preamble(self):
        # Preamble up to 200 chars before "none of the funds"
        preamble = "Notwithstanding section 1234 of title 10, United States Code, "
        text = preamble + "none of the funds made available herein shall be used"
        assert classify_text(text) == "restriction"


class TestTransfer:
    def test_of_amounts(self):
        text = "Of amounts made available to the Department, $5,000,000 shall be transferred"
        assert classify_text(text) == "transfer"

    def test_of_the_amounts(self):
        text = "Of the amounts appropriated under this heading, $10,000,000 may be transferred"
        assert classify_text(text) == "transfer"


class TestAppropriation:
    def test_plain_for(self):
        text = "For necessary expenses of the Department of Defense, $1,000,000,000"
        assert classify_text(text) == "appropriation"

    def test_subsection_prefix(self):
        # Fixed in #115: was \s+ (required space after paren), now \s*
        text = "(a)For necessary expenses, $500,000,000"
        assert classify_text(text) == "appropriation"

    def test_subsection_prefix_with_space(self):
        text = "(b) For the construction of facilities, $200,000,000"
        assert classify_text(text) == "appropriation"

    def test_approp_alt(self):
        text = (
            "There is hereby appropriated, out of any money in the Treasury not otherwise appropriated, $2,000,000,000"
        )
        assert classify_text(text) == "appropriation"

    def test_approp_alt_plural(self):
        text = "There are hereby appropriated such sums as may be necessary, not to exceed $500,000,000"
        assert classify_text(text) == "appropriation"

    def test_approp_alt_without_hereby(self):
        text = "There is appropriated to the Secretary $100,000,000 for fiscal year 2024"
        assert classify_text(text) == "appropriation"

    def test_delayed_approp(self):
        text = "$1,500,000,000 shall become available on October 1, 2025"
        assert classify_text(text) == "appropriation"


class TestRescission:
    def test_approp_with_rescission(self):
        text = "For military construction, $500,000,000, of which $200,000,000 is hereby rescinded"
        assert classify_text(text) == "rescission"

    def test_approp_alt_with_rescission(self):
        text = "There is hereby appropriated $100,000,000, of which $50,000,000 are hereby rescinded"
        assert classify_text(text) == "rescission"

    def test_standalone_rescission(self):
        # No "For" or "There is appropriated" — just rescission language
        text = "The unobligated balances of $200,000,000 are hereby rescinded"
        assert classify_text(text) == "rescission"

    def test_plural_are_hereby_rescinded(self):
        text = "Amounts previously appropriated, $75,000,000, are hereby rescinded"
        assert classify_text(text) == "rescission"


class TestAuthorization:
    def test_authorized_to_be_appropriated(self):
        text = "There is authorized to be appropriated $500,000,000 for fiscal year 2024"
        assert classify_text(text) == "authorization"

    def test_authorization_ordering(self):
        # APPROP_ALT must fire before AUTHORIZATION so a hybrid node that contains
        # both "there is hereby appropriated" and "authorized to be appropriated"
        # stays as appropriation (an actual spending bill), not authorization.
        text = (
            "There is hereby appropriated $1,000,000,000; in addition, there is "
            "authorized to be appropriated such sums as may be necessary"
        )
        assert classify_text(text) == "appropriation"


class TestDirective:
    def test_the_secretary_shall(self):
        text = "The Secretary shall transfer $50,000,000 to the reserve fund"
        assert classify_text(text) == "directive"

    def test_the_agency_may_not(self):
        text = "The Agency may not obligate more than $10,000,000 for this purpose"
        assert classify_text(text) == "directive"


class TestCap:
    def test_reprogram(self):
        text = "No project may be increased or decreased by more than $10,000,000"
        assert classify_text(text) == "cap"

    def test_not_more_than(self):
        # Fallback CAP pattern (not an anchor-line pattern)
        text = "Expenses shall not exceed an amount not more than $5,000,000 per year"
        assert classify_text(text) == "cap"

    def test_not_to_exceed(self):
        text = "Administrative costs, not to exceed $2,000,000, may be paid from this appropriation"
        assert classify_text(text) == "cap"


class TestFee:
    def test_fee_in_the_amount_of(self):
        text = "Each applicant shall pay a fee in the amount of $500"
        assert classify_text(text) == "fee"

    def test_impose_a_fee(self):
        text = "The Administrator may impose a fee of $1,000 per application"
        assert classify_text(text) == "fee"

    def test_a_fee_of(self):
        # "The [entity] shall pay..." triggers DIRECTIVE first, so use a clause form
        text = "Each applicant pays a fee of $250 upon filing"
        assert classify_text(text) == "fee"


class TestEarmark:
    def test_earmark(self):
        text = (
            "Of the amount provided under this heading, amounts specified in the table "
            "shall be for the projects and activities identified in that table"
        )
        assert classify_text(text) == "earmark"


class TestAvailability:
    def test_availability_of_the_amount(self):
        text = "Of the amount appropriated herein, $500,000,000 shall remain available until expended"
        assert classify_text(text) == "availability"

    def test_of_which_shall_remain_available(self):
        text = "of which $200,000,000 shall remain available until September 30, 2026"
        assert classify_text(text) == "availability"


class TestSubAllocation:
    def test_dollar_shall_be_for(self):
        text = "$50,000,000 shall be for research and development"
        assert classify_text(text) == "sub_allocation"

    def test_dollar_shall_be_available(self):
        text = ", $30,000,000 shall be available for grants to States"
        assert classify_text(text) == "sub_allocation"

    def test_of_which(self):
        text = "of which $100,000,000 is for construction projects in rural areas"
        assert classify_text(text) == "sub_allocation"


class TestUnknown:
    def test_empty_string(self):
        assert classify_text("") is None

    def test_none_input(self):
        assert classify_text(None) is None

    def test_no_matching_pattern(self):
        # A dollar-bearing node that matches nothing — should fall through to unknown
        text = "Beginning in fiscal year 2025, $1,000,000 is available for these purposes"
        assert classify_text(text) == "unknown"
