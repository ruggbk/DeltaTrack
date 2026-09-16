"""
Appropriations corpus classifier analysis — issue #115.

Reads data/appropriations_bills.csv for the bill roster, finds downloaded
bill XML in bills/, classifies the earliest version of each, and reports:

  - Per-bill summary (dollar nodes, unknown count, unknown %, fp-risk flags)
  - Aggregate unknown-node patterns for classifier gap mining
  - False-positive risk nodes (auth-hint language on a primary label)
  - Stats grouped by Congress and by bill type

Run from DeltaTrack/:
  uv run python docs/research/financial-semantics/approp_corpus_analysis.py

Download missing bills first:
  uv run python tools/fetch_bills.py download-all \\
    --file docs/research/financial-semantics/data/annual_approp_download_list.csv
"""

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO = next(p for p in [Path().resolve(), *Path().resolve().parents] if (p / "pyproject.toml").exists())
sys.path.insert(0, str(_HERE))

from classify_bill import DOLLAR, classify_text  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402

BILLS_CSV = _HERE / "data" / "annual_approp_bills.csv"
BILLS_DIR = _REPO / "bills"

AUTH_HINTS = re.compile(
    r"authorized to be appropriated|is authorized|are authorized|"
    r"Authorization of Appropriations|authorization of appropriations",
    re.IGNORECASE,
)

FP_PATTERNS = {
    "authorized_to_be_appropriated": re.compile(r"authorized to be appropriated", re.IGNORECASE),
    "fine_penalty": re.compile(r"\bfine\b.{0,30}\$|\bpenalty\b.{0,30}\$|\bpenalties\b.{0,30}\$", re.IGNORECASE),
    "income_threshold": re.compile(r"adjusted gross income|taxable income|earned income", re.IGNORECASE),
    "loan_amount": re.compile(r"\bloan\b.{0,50}\$|\bgrant\b.{0,50}\$", re.IGNORECASE),
    "contract_threshold": re.compile(r"\bcontract\b.{0,50}\$|\bthreshold\b.{0,50}\$", re.IGNORECASE),
    "pay_salary": re.compile(r"\bsalary\b|\bpay\b.{0,30}\$|\bcompensation\b.{0,30}\$", re.IGNORECASE),
    "benefit_amount": re.compile(r"\bbenefit\b.{0,50}\$|\bpayment\b.{0,50}\$", re.IGNORECASE),
}


def find_version1(bill_id: str) -> Path | None:
    """Return the lowest-indexed XML file in a bill directory (version 1)."""
    bill_dir = BILLS_DIR / bill_id
    if not bill_dir.exists():
        return None
    xmls = [p for p in bill_dir.glob("*.xml") if not p.stem.startswith("gap")]
    if not xmls:
        return None
    return min(xmls, key=lambda p: int(p.stem.split("_")[0]))


def fp_flags(text: str) -> list[str]:
    return [name for name, pat in FP_PATTERNS.items() if pat.search(text)]


def classify_bill_xml(bill_id: str, xml_path: Path) -> dict:
    """Parse and classify one XML version; returns a result dict."""
    try:
        tree = normalize_bill(xml_path)
    except Exception as exc:
        return {"bill": bill_id, "error": str(exc)}

    dollar_nodes = [n for n in tree.nodes if DOLLAR.search(n.body_text or "")]
    labels: Counter = Counter()
    unknown_rows: list[dict] = []
    fp_risk_rows: list[dict] = []

    for node in dollar_nodes:
        text = node.body_text or ""
        label = classify_text(text)
        has_auth_hint = bool(AUTH_HINTS.search(text))
        preview = text[:200].replace("\n", " ")
        flags = fp_flags(text)
        labels[label] += 1

        if label == "unknown":
            unknown_rows.append(
                {"bill": bill_id, "preview": preview, "has_auth_hint": has_auth_hint, "fp_flags": flags}
            )
        if has_auth_hint and label in ("appropriation", "rescission", "transfer"):
            fp_risk_rows.append({"bill": bill_id, "label": label, "preview": preview})

    return {
        "bill": bill_id,
        "dollar_nodes": len(dollar_nodes),
        "unknowns": len(unknown_rows),
        "fp_risks": len(fp_risk_rows),
        "label_dist": dict(labels),
        "unknown_rows": unknown_rows,
        "fp_risk_rows": fp_risk_rows,
        "error": None,
    }


def analyze_unknowns(rows: list[dict]) -> dict[str, list[dict]]:
    groups: defaultdict[str, list[dict]] = defaultdict(list)
    for r in rows:
        key = " ".join(r["preview"].split()[:6]).lower()
        groups[key].append(r)
    return dict(groups)


def run():
    df = pd.read_csv(BILLS_CSV)
    hr_s = df.copy()

    all_unknowns: list[dict] = []
    all_fp_risks: list[dict] = []
    summary_rows: list[dict] = []
    missing: list[str] = []
    errors: list[dict] = []

    print(f"Classifying up to {len(hr_s)} appropriations bills...")
    print(f"{'Bill':<22} {'$nodes':>7} {'unk':>5} {'unk%':>5} {'fp':>4}  version")

    for _, row in hr_s.sort_values("id").iterrows():
        bill_id = row["id"]
        xml_path = find_version1(bill_id)
        if xml_path is None:
            missing.append(bill_id)
            continue

        result = classify_bill_xml(bill_id, xml_path)
        if result.get("error"):
            errors.append({"bill": bill_id, "error": result["error"]})
            print(f"  {bill_id:<22} ERROR: {result['error'][:60]}")
            continue

        n = result["dollar_nodes"]
        u = result["unknowns"]
        unk_pct = u / max(n, 1) * 100

        all_unknowns.extend(result["unknown_rows"])
        all_fp_risks.extend(result["fp_risk_rows"])
        summary_rows.append(
            {
                "bill": bill_id,
                "congress": int(row["congress"]),
                "bill_type": row["bill_type"],
                "title": str(row["title"])[:70],
                "dollar_nodes": n,
                "unknowns": u,
                "unk_pct": unk_pct,
                "fp_risks": result["fp_risks"],
                "label_dist": result["label_dist"],
                "version1": xml_path.name,
            }
        )
        print(f"  {bill_id:<22} {n:>7} {u:>5} {unk_pct:>4.0f}% {result['fp_risks']:>4}  {xml_path.name}")

    # ── Corpus summary ────────────────────────────────────────────────────────
    total_dollar = sum(r["dollar_nodes"] for r in summary_rows)
    total_unknown = sum(r["unknowns"] for r in summary_rows)
    print(f"\n\n{'=' * 70}")
    print("CORPUS SUMMARY")
    print(f"  {len(summary_rows)} bills classified | {len(missing)} not downloaded | {len(errors)} errors")
    unk_pct = total_unknown / max(total_dollar, 1) * 100
    print(f"  {total_dollar} total dollar nodes | {total_unknown} unknown ({unk_pct:.1f}%)")
    print(f"  {sum(r['fp_risks'] for r in summary_rows)} total fp-risk flags")

    # ── By Congress ───────────────────────────────────────────────────────────
    if summary_rows:
        print(f"\n{'=' * 70}")
        print("BY CONGRESS")
        cdf = pd.DataFrame(summary_rows)
        grp = (
            cdf.groupby("congress")
            .agg(bills=("bill", "count"), dollar=("dollar_nodes", "sum"), unk=("unknowns", "sum"))
            .assign(unk_pct=lambda g: g["unk"] / g["dollar"].clip(lower=1) * 100)
        )
        print(grp.to_string())

        # ── Highest unknown-rate bills ─────────────────────────────────────────
        print(f"\n{'=' * 70}")
        print("HIGHEST UNKNOWN RATE (top 30, min 5 dollar nodes)")
        top = cdf[cdf["dollar_nodes"] >= 5].nlargest(30, "unk_pct")
        for _, r in top.iterrows():
            print(
                f"  {r['bill']:<22} {r['dollar_nodes']:>5}$ {r['unknowns']:>4}unk"
                f" {r['unk_pct']:>5.0f}%  {r['title'][:55]}"
            )

        # ── Lowest unknown-rate bills ──────────────────────────────────────────
        print(f"\n{'=' * 70}")
        print("LOWEST UNKNOWN RATE (top 30, min 5 dollar nodes)")
        bot = cdf[cdf["dollar_nodes"] >= 5].nsmallest(30, "unk_pct")
        for _, r in bot.iterrows():
            print(
                f"  {r['bill']:<22} {r['dollar_nodes']:>5}$ {r['unknowns']:>4}unk"
                f" {r['unk_pct']:>5.0f}%  {r['title'][:55]}"
            )

    # ── Unknown patterns ──────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"UNKNOWN NODE PATTERNS — ALL BILLS ({len(all_unknowns)} total)")
    groups = analyze_unknowns(all_unknowns)
    for key, items in sorted(groups.items(), key=lambda x: -len(x[1]))[:40]:
        print(f"\n[{len(items)}x] '{key}...'")
        for item in items[:2]:
            print(f"    [{item['bill']}] {item['preview'][:160]}")
            if item["fp_flags"]:
                print(f"    fp_flags: {item['fp_flags']}")

    # ── FP risks ─────────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"FP RISKS ({len(all_fp_risks)} total) — primary label with auth-adjacent language")
    for r in all_fp_risks[:30]:
        print(f"  [{r['bill']}] label={r['label']}")
        print(f"  {r['preview'][:200]}")

    # ── Auth-hint unknowns ────────────────────────────────────────────────────
    auth_unk = [r for r in all_unknowns if r["has_auth_hint"]]
    print(f"\n{'=' * 70}")
    print(f"UNKNOWN WITH AUTH-ADJACENT LANGUAGE ({len(auth_unk)}) — potential coverage gaps")
    for r in auth_unk[:20]:
        print(f"  [{r['bill']}] {r['preview'][:180]}")

    # ── Not downloaded ────────────────────────────────────────────────────────
    if missing:
        print(f"\n{'=' * 70}")
        print(f"NOT DOWNLOADED ({len(missing)} bills)")
        print("Run: uv run python tools/fetch_bills.py download-all \\")
        print("       --file docs/research/financial-semantics/data/approp_download_list.csv")
        for m in missing[:20]:
            print(f"  {m}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")

    return summary_rows, all_unknowns, all_fp_risks, missing


if __name__ == "__main__":
    run()
