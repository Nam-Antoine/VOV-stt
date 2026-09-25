"""``python -m app.exports --episode <slug>`` — regenerate every export for one episode.

Backs ``make export EP=<slug>``. Writes into ``EXPORTS_DIR/<slug>/`` (PLAN §6), always
regenerated from the raw JSON plus the verified layer — never from a previous export
(PLAN §0.2).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import TIER_ASR, TIER_VERIFIED, csv, docx, eaf, json_verified, srt, txt

log = logging.getLogger("exports")

#: extension -> (renderer, tier). ``tier=None`` means the renderer decides.
RENDERERS = {
    "txt": (txt.render, TIER_ASR),
    "verified.txt": (txt.render, TIER_VERIFIED),
    "csv": (csv.render, None),
    "srt": (srt.render, TIER_ASR),
    "eaf": (eaf.render, TIER_ASR),
    "verified.json": (json_verified.render, None),
}

#: Binary formats, written with write_bytes instead of write_text.
BINARY_RENDERERS = {
    "docx": (docx.render_bytes, TIER_VERIFIED),
}


def render_all(doc: dict, out_dir: Path, slug: str,
               overrides: dict | None = None,
               title: str | None = None) -> list[Path]:
    """Write every format for one document. Returns the paths written.

    ``overrides`` is the verified layer keyed by utterance index. When it is supplied
    the verified-tier renderers see the human text; the ASR-tier ones never do, which is
    the whole point of keeping both tiers on disk (PLAN §0.2).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # Layer the overrides onto a copy once, so each renderer downstream sees one
    # consistent document instead of every renderer knowing about the override dict.
    verified_doc = (
        json_verified.build(doc, overrides=overrides)
        if overrides else doc
    )

    for ext, (render, tier) in RENDERERS.items():
        path = out_dir / f"{slug}.{ext}"
        if render is json_verified.render:
            body = render(doc, overrides=overrides)
        else:
            kwargs: dict = {}
            if tier is not None:
                kwargs["tier"] = tier
            body = render(verified_doc if tier == TIER_VERIFIED else doc, **kwargs)
        path.write_text(body, encoding="utf-8")
        written.append(path)

    for ext, (render, tier) in BINARY_RENDERERS.items():
        source = verified_doc if tier == TIER_VERIFIED else doc
        path = out_dir / f"{slug}.{ext}"
        path.write_bytes(
            render(source, tier=tier, title=title or slug)
        )
        written.append(path)

    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--episode", help="episode slug (loads the current transcript)")
    group.add_argument("--raw-json", type=Path,
                       help="render straight from a raw JSON file, no DB")
    ap.add_argument("--out", type=Path, default=None,
                    help="output directory (default: EXPORTS_DIR/<slug>)")
    args = ap.parse_args(argv)
    logging.basicConfig(level="INFO", format="%(levelname)-7s %(message)s")

    if args.raw_json:
        import json

        doc = json.loads(args.raw_json.read_text(encoding="utf-8"))
        slug = args.raw_json.stem
        out_dir = args.out or args.raw_json.parent / "exports"
        for path in render_all(doc, out_dir, slug):
            log.info("wrote %s", path)
        return 0

    # TODO(T3): load the episode, its current transcript's raw JSON, the utterances
    # overrides, then call render_all.
    print(
        "error: --episode needs the DB layer, which lands in T3 (PLAN §11). "
        "Use --raw-json to render from a raw JSON file today.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
