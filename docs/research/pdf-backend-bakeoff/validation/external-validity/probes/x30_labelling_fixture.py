"""Synthetic scorer payload for x30's labelling controls. SYNTHETIC ONLY, no holdout.

Built from x27's own frame builders rather than a hand-written dict, so the payload has the
real shape `score()` produces. A hand-made fixture would encode a belief about the scorer's
output and could pass while the real payload had drifted away from it.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import score_metrics as SM  # noqa: E402
import x27_score_metrics as X27  # noqa: E402


def build_payload() -> dict:
    """A scored payload over synthetic frames, with one cross-engine FAILING document.

    A failing document is required: with every document passing, `qualification` is `None`
    everywhere and the labelling controls could not tell a carried status from an absent one.
    """
    frames = [X27.frame([X27.page_input(1)])]
    documents = [f["document"] for f in frames]
    cross_engine = X27.cross_engine_artifact(documents, failed={documents[0]})
    return SM.score(X27.inputs(frames, cross_engine=cross_engine))
