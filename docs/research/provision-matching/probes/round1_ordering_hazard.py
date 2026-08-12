"""Is the cross-division list's parser-ordinal monotonicity structural, or corpus-contingent?

Within-division sublists are ordinal-ascending BY CONSTRUCTION (they are filtered from a
parser-ordered list). The CROSS-division list is a concatenation across divisions in
first-appearance order, so it is ascending only if each division's leftovers happen not to
interleave. This builds a case where they do.
"""

from __future__ import annotations

from deltatrack import diff_bill as db
from deltatrack.bill_tree import BillNode

MP = ("sec-1",)


def node(eid, body, div):
    return BillNode(
        match_path=MP,
        display_path=MP,
        tag="section",
        element_id=eid,
        header_text="",
        body_text=body,
        section_number="1",
        division_label=div,
        division_key=div,
    )


# Old parser order: X1(0), Y1(1), X2(2)  -- divisions X, Y, X interleave.
#   division X: 2 old, 1 new -> within-division assignment leaves X2 (ordinal 2) over
#   division Y: 1 old, 0 new -> structurally unmatched, Y1 (ordinal 1)
# all_divs first-appearance order is [X, Y], so unmatched_old == [X2, Y1] -> ordinals [2, 1].
old_nodes = [
    node("X1", "alpha alpha alpha shared opening text here", "X"),
    node("Y1", "yankee yankee yankee division y only text", "Y"),
    node("X2", "xray xray xray leftover from division x", "X"),
]
# New side: division X has one node (pairs with X1), division Z exists only on the new side
# so that the cross-division fallback has a non-empty new population.
new_nodes = [
    node("nX1", "alpha alpha alpha shared opening text here", "X"),
    node("nZ1", "xray xray xray leftover from division x", "Z"),
]

ordinals = {}
for i, n in enumerate(old_nodes):
    ordinals[id(n)] = i
for i, n in enumerate(new_nodes):
    ordinals[id(n)] = i

calls = []
real_sp = db._similarity_pair


def spy(o, n):
    r = real_sp(o, n)
    calls.append(
        {
            "old_ids": [x.element_id for x in o],
            "old_ordinals": [ordinals[id(x)] for x in o],
            "new_ids": [x.element_id for x in n],
            "new_ordinals": [ordinals[id(x)] for x in n],
            "out": [(a.element_id if a else None, b.element_id if b else None) for a, b in r],
        }
    )
    return r


db._similarity_pair = spy
result = db._match_collision_group(old_nodes, new_nodes)
db._similarity_pair = real_sp

for i, c in enumerate(calls):
    print(f"call {i}: old={c['old_ids']} ordinals={c['old_ordinals']}")
    print(f"         new={c['new_ids']} ordinals={c['new_ordinals']}")
    print(f"         -> {c['out']}")

cross = calls[-1]
asc = cross["old_ordinals"] == sorted(cross["old_ordinals"])
print()
print(f"cross-division OLD list ordinals: {cross['old_ordinals']}")
print(f"ascending parser-ordinal order?   {asc}")
print()
if not asc:
    print("RESULT: monotonicity is CORPUS-CONTINGENT, not structural.")
    print("  A cross-division assignment keyed on parser ordinals would sort this list")
    print("  differently from one keyed on local positions. The corpus never exhibits it")
    print("  (0/30 cross invocations), so no corpus gate can detect the substitution.")
else:
    print("RESULT: could not break monotonicity with this construction.")
print()
print("group result:", [(a.element_id if a else None, b.element_id if b else None) for a, b in result])
