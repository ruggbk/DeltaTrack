"""
Classifier stress-test: parse all 7 bills, report unknowns and false-positive risks.

Run from DeltaTrack/:  uv run python notebooks/stress_test_analysis.py
"""

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bill_tree import normalize_bill
from notebooks.classify_bill import DOLLAR, classify_text

BILLS = [
    ("118", "hr", "4366", "MILCON/VA FY2024 approp"),
    ("119", "hr", "1", "Big Beautiful Bill (reconciliation)"),
    ("118", "s", "2226", "NDAA FY2024 (authorization)"),
    ("115", "hr", "2", "2018 Farm Bill (authorization)"),
    ("117", "hr", "3684", "IIJA (infrastructure auth)"),
    ("117", "hr", "5376", "IRA (reconciliation)"),
    ("118", "hr", "4368", "CJS FY2024 approp"),
]

BILLS_DIR = Path(__file__).parent.parent / "bills"

# Patterns that suggest a node is an authorization (should NOT be appropriation)
AUTH_HINTS = re.compile(
    r"authorized to be appropriated|is authorized|are authorized|"
    r"Authorization of Appropriations|authorization of appropriations",
    re.IGNORECASE,
)

# Common false-positive triggers in authorization bills
FP_PATTERNS = {
    "authorized_to_be_appropriated": re.compile(r"authorized to be appropriated", re.IGNORECASE),
    "fine_penalty": re.compile(r"\bfine\b.{0,30}\$|\bpenalty\b.{0,30}\$|\bpenalties\b.{0,30}\$", re.IGNORECASE),
    "income_threshold": re.compile(r"adjusted gross income|taxable income|earned income", re.IGNORECASE),
    "loan_amount": re.compile(r"\bloan\b.{0,50}\$|\bgrant\b.{0,50}\$", re.IGNORECASE),
    "contract_threshold": re.compile(r"\bcontract\b.{0,50}\$|\bthreshold\b.{0,50}\$", re.IGNORECASE),
    "pay_salary": re.compile(r"\bsalary\b|\bpay\b.{0,30}\$|\bcompensation\b.{0,30}\$", re.IGNORECASE),
    "benefit_amount": re.compile(r"\bbenefit\b.{0,50}\$|\bpayment\b.{0,50}\$", re.IGNORECASE),
}


def find_xml(congress, bill_type, number):
    pattern = BILLS_DIR / f"{congress}-{bill_type}-{number}"
    xmls = sorted(pattern.glob("*.xml"))
    return xmls[0] if xmls else None


def classify_node(node):
    """Classify a BillNode; return (label, first_clause_label, has_auth_hint)."""
    text = node.body_text or ""
    label = classify_text(text)
    has_auth_hint = bool(AUTH_HINTS.search(text))
    return label, has_auth_hint


def analyze_unknowns(rows):
    """Group unknown rows by leading text pattern for pattern mining."""
    groups = defaultdict(list)
    for r in rows:
        text = r["preview"]
        # First 6 words as cluster key
        key = " ".join(text.split()[:6]).lower()
        groups[key].append(r)
    return groups


def fp_flags(text):
    """Which false-positive hint patterns fire on this text."""
    return [name for name, pat in FP_PATTERNS.items() if pat.search(text)]


def run():
    all_unknowns = []
    all_fp_risks = []
    summary_rows = []

    for congress, btype, number, label in BILLS:
        xml_path = find_xml(congress, btype, number)
        if not xml_path:
            print(f"  ✗ {congress}-{btype}-{number}: XML not found")
            summary_rows.append(
                {
                    "bill": f"{congress}-{btype}-{number}",
                    "label": label,
                    "dollar_nodes": 0,
                    "unknowns": 0,
                    "fp_risks": 0,
                }
            )
            continue

        tree = normalize_bill(xml_path)
        dollar_nodes = [n for n in tree.nodes if DOLLAR.search(n.body_text or "")]
        labels = Counter()
        unknowns = []
        fp_risks = []

        for node in dollar_nodes:
            node_label, has_auth_hint = classify_node(node)
            labels[node_label] += 1
            text = node.body_text or ""
            preview = text[:200].replace("\n", " ")
            flags = fp_flags(text)

            if node_label == "unknown":
                unknowns.append(
                    {
                        "bill": f"{congress}-{btype}-{number}",
                        "preview": preview,
                        "has_auth_hint": has_auth_hint,
                        "fp_flags": flags,
                        "full_text": text,
                    }
                )

            # Check for false-positive risk: primary label on an auth hint
            if has_auth_hint and node_label in ("appropriation", "rescission", "transfer"):
                fp_risks.append(
                    {
                        "bill": f"{congress}-{btype}-{number}",
                        "label": node_label,
                        "preview": preview,
                        "full_text": text,
                    }
                )

        all_unknowns.extend(unknowns)
        all_fp_risks.extend(fp_risks)
        summary_rows.append(
            {
                "bill": f"{congress}-{btype}-{number}",
                "label": label,
                "dollar_nodes": len(dollar_nodes),
                "unknowns": len(unknowns),
                "fp_risks": len(fp_risks),
                "label_dist": dict(labels),
            }
        )

        print(f"\n{'=' * 70}")
        print(f"{congress}-{btype}-{number}  {label}")
        print(f"  {len(dollar_nodes)} dollar nodes | {len(unknowns)} unknown | {len(fp_risks)} fp-risk")
        print(f"  Label distribution: {dict(labels.most_common())}")

    # Unknown deep dive
    print(f"\n\n{'=' * 70}")
    print(f"UNKNOWN NODES — ALL BILLS ({len(all_unknowns)} total)")
    print("=" * 70)
    groups = analyze_unknowns(all_unknowns)
    sorted_groups = sorted(groups.items(), key=lambda x: -len(x[1]))
    for key, items in sorted_groups[:40]:
        print(f"\n[{len(items)}x] '{key}...'")
        for item in items[:3]:
            print(f"    [{item['bill']}] {item['preview'][:160]}")
            if item["fp_flags"]:
                print(f"    FP flags: {item['fp_flags']}")

    # False-positive risk
    print(f"\n\n{'=' * 70}")
    print(f"FALSE-POSITIVE RISKS ({len(all_fp_risks)} nodes labeled primary type but have auth hint)")
    print("=" * 70)
    for r in all_fp_risks[:30]:
        print(f"\n  [{r['bill']}] label={r['label']}")
        print(f"  {r['preview'][:200]}")

    # Auth-hint unknowns
    auth_unknowns = [r for r in all_unknowns if r["has_auth_hint"]]
    print(f"\n\n{'=' * 70}")
    print(f"UNKNOWN NODES WITH AUTH HINT ({len(auth_unknowns)} — likely authorizations, should stay unknown)")
    print("=" * 70)
    for r in auth_unknowns[:20]:
        print(f"  [{r['bill']}] {r['preview'][:180]}")

    # Summary table
    print(f"\n\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Bill':<22} {'Type':<38} {'$nodes':>7} {'unk':>6} {'fp?':>5}")
    print("-" * 70)
    for row in summary_rows:
        bill, lbl = row["bill"], row["label"]
        print(f"{bill:<22} {lbl:<38} {row['dollar_nodes']:>7} {row['unknowns']:>6} {row['fp_risks']:>5}")

    return all_unknowns, all_fp_risks, summary_rows


if __name__ == "__main__":
    unknowns, fp_risks, summary = run()
