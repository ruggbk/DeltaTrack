"""A33 -- region crop and the pixel/PDF coordinate transform. NOT a harness component.

Pure encodings of the A33 rulings, written executably so they can be tested before
`build_oracle.py` exists. Nothing here opens a PDF, scores anything, or decides an outcome.
`x20_oracle_crop_coordinates.py` is the test.

    A33.1  the region bbox is the MINIMAL union of COMMITTED neutral-line bboxes, zero padding
    A33.2  the committed frame is authoritative -- geometry is never re-derived from the PDF
    A33.3  the pixel<->PDF transform is the renderer's actual mapping, measured not assumed
    A33.4  a rotated page is refused unless a proven deterministic transform exists

WHY THE TRANSFORM IS NOT WHAT A30.3 SKETCHED. A30.3 described the inversion as a linear map
across the bbox:

    pdf_x = bbox_x0 + (start_x_px / image_width) * (bbox_x1 - bbox_x0)

`x20` measures that MuPDF does something different and simpler: the pixmap's device origin is
`floor(bbox_x0 * DPI/72)`, so image column 0 is NOT `bbox_x0`, and each pixel is exactly
`72/DPI` points -- never `(bbox_x1-bbox_x0)/image_width`, which differs because the integer
pixmap is the rounded-out bounding box of the transformed clip. Both errors are small per pixel
and both accumulate across a region-width image. The mapping below is the renderer's, and it
needs no metadata beyond `bbox_x0` and the frozen DPI.
"""

from __future__ import annotations

import math

# abort classes -- each refuses; none is representable in a rendered stimulus
MISSING_LINE_BBOX = "MISSING_LINE_BBOX"
NON_FINITE_LINE_BBOX = "NON_FINITE_LINE_BBOX"
NON_POSITIVE_REGION_BBOX = "NON_POSITIVE_REGION_BBOX"
REGION_HAS_NO_LINES = "REGION_HAS_NO_LINES"
NONZERO_PAGE_ROTATION = "NONZERO_PAGE_ROTATION"


class OracleGeometryError(Exception):
    """The committed geometry cannot be rendered as frozen. Deterministic, never a value."""

    def __init__(self, reason: str, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason} {detail!r}")


# ------------------------------------------------------------------- A33.1 / A33.2 bbox


def region_bbox(page_frame: dict, region_ordinal: int):
    """The MINIMAL axis-aligned union of the region's COMMITTED neutral-line bboxes.

    ZERO PADDING. A `NeutralLine` bbox is already the min/max over every eligible source-glyph
    box on that physical line, so padding would introduce a free parameter, could expose
    neighbouring content outside the frozen region, and would no longer be the unique
    least-expansive rectangle implementing "region bbox from neutral geometry".

    A33.2 -- this reads ONLY the committed frame. It never re-clusters, never re-reads the PDF,
    and never consults H text, X text, anchor content or adjudicated content. The PDF supplies
    pixels; the frame supplies which rectangle to render.
    """
    region = next((r for r in page_frame["regions"] if r["region_ordinal"] == region_ordinal), None)
    if region is None or not region["neutral_line_keys"]:
        raise OracleGeometryError(REGION_HAS_NO_LINES, {"region_ordinal": region_ordinal})

    wanted = {tuple(k) for k in region["neutral_line_keys"]}
    boxes = []
    for line in page_frame["neutral_lines"]:
        if tuple(line["key"]) in wanted:
            bbox = line.get("bbox")
            if bbox is None or len(bbox) != 4:
                raise OracleGeometryError(MISSING_LINE_BBOX, {"line": line.get("key")})
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in bbox):
                raise OracleGeometryError(NON_FINITE_LINE_BBOX, {"line": line.get("key"), "bbox": bbox})
            boxes.append(bbox)
    if len(boxes) != len(wanted):
        raise OracleGeometryError(MISSING_LINE_BBOX, {"expected": len(wanted), "found": len(boxes)})

    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    if not (x1 > x0 and y1 > y0):
        raise OracleGeometryError(NON_POSITIVE_REGION_BBOX, {"bbox": [x0, y0, x1, y1]})
    return (x0, y0, x1, y1)


# ------------------------------------------------------------------ A33.3 the transform


def scale(dpi: int) -> float:
    return dpi / 72.0


def device_origin_px(bbox_x0: float, dpi: int) -> int:
    """The device x of image column 0. MEASURED: MuPDF's pixmap is the rounded-OUT integer
    bounding box of the transformed clip, so its origin is the floor, not `bbox_x0 * s`."""
    return math.floor(bbox_x0 * scale(dpi))


def expected_image_width(bbox_x0: float, bbox_x1: float, dpi: int) -> int:
    """The width MuPDF returns for this clip: ceil(x1*s) - floor(x0*s).

    A VALIDATION helper only -- `pixel_to_pdf_x` does not use it, so nothing in the inversion
    depends on this function. The tiny snap below is a FLOAT GUARD, not a tolerance: when
    `x1 * s` is mathematically an integer, IEEE double arithmetic can land at 463.00000000000006
    and `ceil` then returns 464 where MuPDF, computing exactly, returns 463. Measured on the
    synthetic grid, the only disagreements were of exactly this form. It rounds a value that is
    already within 1e-9 of an integer to that integer; it admits no genuine sub-pixel slack and
    it never touches the resolver.
    """
    s = scale(dpi)
    hi = bbox_x1 * s
    if abs(hi - round(hi)) < 1e-9:
        hi = round(hi)
    return math.ceil(hi) - math.floor(bbox_x0 * s)


def pixel_to_pdf_x(start_x_px: int, bbox_x0: float, dpi: int) -> float:
    """A33.3 -- the frozen inversion. Needs only `bbox_x0` and the frozen DPI.

    Each pixel is exactly 72/DPI points; the origin is the pixmap's device origin. `image_width`
    is deliberately NOT an input: using it as a scale, as A30.3 sketched, spreads the
    rounded-out integer width across the region and drifts by a pixel or more at the far edge.
    """
    return (device_origin_px(bbox_x0, dpi) + start_x_px) / scale(dpi)


def pdf_x_to_pixel(pdf_x: float, bbox_x0: float, dpi: int) -> int:
    """The forward map an adjudicator's eye approximates: which integer column contains `pdf_x`."""
    return math.floor(pdf_x * scale(dpi)) - device_origin_px(bbox_x0, dpi)


# --------------------------------------------------------------------- A33.4 rotation


def check_rotation(rotation: int) -> None:
    """A33.4 -- refuse a rotated page rather than improvise a transform.

    `x20` proves the CLIP can be carried exactly onto a rotated page by `page.rotation_matrix`.
    That is not sufficient, and the reason is the part that matters: at 90 and 270 the image's
    horizontal axis is the PDF **y** axis, and at 180 it is the PDF x axis MIRRORED. So
    `start_x_px` -- a horizontal pixel offset the adjudicator marks -- stops corresponding to a
    neutral glyph's `x0`, which is the quantity A30.3's nearest-x resolver compares. Rendering
    the right pixels is not the same as preserving the coordinate semantics.

    Proposed for review, fail-closed, and NOT adopted unilaterally.
    """
    if rotation:
        raise OracleGeometryError(NONZERO_PAGE_ROTATION, {"rotation": rotation})
