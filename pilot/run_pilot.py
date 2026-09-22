#!/usr/bin/env python3
"""Pilot sweep — the T2 gate (PLAN §4).

    python pilot/run_pilot.py --clip pilot/clip_2min.wav --reference pilot/reference.txt

Sweeps the §4.3 knobs over a 2-minute clip that contains **both** studio dialogue and a
vox-pop segment, scores each run, and writes ``pilot/RESULTS.md`` with sample output
pasted in.

Scoring (PLAN §4.2), and the order matters:

1. **Filler recall** — ``fillers_in_hyp / fillers_in_ref`` over
   {à, ừ, ờ, ừm, thì, là, ấy, nhé, đấy}. Target ≥ 0.85. This is the primary number.
2. **WER**, computed with **no normalisation** beyond lowercasing the reference and
   stripping its punctuation — because the model emits neither. Never normalise the
   hypothesis (PLAN §13: "WER looks great, corpus is wrong").
3. Diarization: MC, guest and ≥ 2 distinct vox-pop voices on separate cluster IDs.

Pick the configuration by **filler-recall-at-acceptable-WER, not by WER alone** (§4.3).

If verbatim fails on every setting: **stop and escalate.** Do not proceed to the web app
on this engine (PLAN §4.3).

T2 status: this script is written but has not been run — it needs the docx episode's
audio, which is not in the repo. Running it is the T2 task and needs owner sign-off.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

#: PLAN §4.2 filler set.
FILLERS = ("à", "ừ", "ờ", "ừm", "thì", "là", "ấy", "nhé", "đấy")

#: PLAN §4.2 named terms that hotwords are supposed to rescue.
KEY_TERMS = ("Thanh Huyền", "Di Li", "quản chồng", "giữ lửa")

#: PLAN §4.3 sweep.
SWEEP = {
    "blank_penalty": [0.0, 0.25, 0.5, 0.75],
    "decoding_method": ["greedy_search", "modified_beam_search"],
    "int8": [True, False],
    "diar_threshold": [0.5, 0.6, 0.7, 0.8, 0.9],
    "vad_threshold": [0.2, 0.3, 0.5],
}


@dataclass
class Reference:
    """``pilot/reference.txt``: one utterance per line, ``SPEAKER<TAB>text``."""

    lines: list[tuple[str, str]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Reference":
        rows = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            speaker, _, text = line.partition("\t")
            rows.append((speaker.strip(), text))
        return cls(rows)

    @property
    def text(self) -> str:
        return " ".join(text for _, text in self.lines)

    @property
    def speakers(self) -> set[str]:
        return {s for s, _ in self.lines}


def normalise_reference_only(text: str) -> str:
    """Lowercase and strip punctuation **from the reference only** (PLAN §4.2).

    The hypothesis is scored raw. Touching it is the bug in PLAN §13's last row.
    """
    return re.sub(r"[^\w\s]", " ", text.lower())


def tokens(text: str) -> list[str]:
    return text.split()


def filler_recall(hyp: str, ref: str) -> tuple[float, dict[str, tuple[int, int]]]:
    """Per-filler ``(hyp_count, ref_count)`` and the pooled recall."""
    hyp_toks, ref_toks = tokens(hyp.lower()), tokens(ref)
    per: dict[str, tuple[int, int]] = {}
    hyp_total = ref_total = 0
    for filler in FILLERS:
        h, r = hyp_toks.count(filler), ref_toks.count(filler)
        per[filler] = (h, r)
        # Recall is capped per filler: 50 spurious "thì" must not mask a missing "ừ".
        hyp_total += min(h, r)
        ref_total += r
    return (hyp_total / ref_total if ref_total else float("nan")), per


def word_error_rate(hyp: str, ref: str) -> float:
    """WER via ``jiwer`` when installed, else a plain Levenshtein fallback."""
    try:
        import jiwer

        return float(jiwer.wer(ref, hyp))
    except ImportError:
        pass
    r, h = tokens(ref), tokens(hyp)
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return prev[-1] / len(r) if r else float("nan")


def key_term_hits(hyp: str) -> dict[str, bool]:
    low = hyp.lower()
    return {term: term.lower() in low for term in KEY_TERMS}


def diarization_report(doc: dict) -> dict:
    segments = (doc.get("diarization") or {}).get("segments", [])
    clusters = {s["speaker"] for s in segments}
    return {"n_clusters": len(clusters), "n_segments": len(segments)}


def configurations(sweep: dict, *, full: bool) -> list[dict]:
    """The grid, or a one-at-a-time sweep around the PLAN §2/§3 defaults.

    The full grid is 4x2x2x5x3 = 240 runs of a 2-minute clip — hours on the box. The
    default walks one axis at a time from the baseline, which is what §4.3 actually
    needs to pick a setting.
    """
    baseline = {k: v[1] if k == "decoding_method" else v[0] for k, v in sweep.items()}
    baseline["blank_penalty"] = 0.25
    baseline["int8"] = True
    baseline["diar_threshold"] = 0.7
    baseline["vad_threshold"] = 0.3

    if full:
        keys = list(sweep)
        return [dict(zip(keys, combo)) for combo in itertools.product(*sweep.values())]

    configs = [dict(baseline)]
    for key, values in sweep.items():
        for value in values:
            if value == baseline[key]:
                continue
            cfg = dict(baseline)
            cfg[key] = value
            configs.append(cfg)
    return configs


def run_one(clip: Path, models: Path, cfg: dict, out_dir: Path,
            hotwords: Path | None) -> dict:
    """Run the pipeline once with ``cfg`` and return the raw JSON document."""
    from app.pipeline.asr import AsrParams
    from app.pipeline.diarize import DiarParams
    from app.pipeline.run import transcribe
    from app.pipeline.vad import VadParams

    # Hotwords need modified_beam_search; a greedy run in the sweep simply has none.
    use_hotwords = hotwords if cfg["decoding_method"] == "modified_beam_search" else None
    asr = AsrParams(
        model_dir=str(models / "zipformer-30m-rnnt-6000h"),
        int8=cfg["int8"],
        blank_penalty=cfg["blank_penalty"],
        decoding_method=cfg["decoding_method"],
        hotwords_file=str(use_hotwords) if use_hotwords else None,
    )
    vad = VadParams(model=str(models / "vad" / "silero_vad.onnx"),
                    threshold=cfg["vad_threshold"])
    embeddings = sorted((models / "diarization" / "speaker-embedding").glob("*.onnx"))
    diar = DiarParams(
        segmentation_model=str(
            models / "diarization" / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
        ),
        embedding_model=str(embeddings[0]),
        threshold=cfg["diar_threshold"],
    )
    return transcribe(clip, work_dir=out_dir, asr_params=asr, vad_params=vad,
                      diar_params=diar)


def score(doc: dict, reference: Reference) -> dict:
    hyp = " ".join(u["text"] for u in doc["utterances"])
    ref = normalise_reference_only(reference.text)
    recall, per_filler = filler_recall(hyp, ref)
    return {
        "hyp": hyp,
        "filler_recall": recall,
        "per_filler": per_filler,
        "wer": word_error_rate(hyp.lower(), ref),
        "key_terms": key_term_hits(hyp),
        "diarization": diarization_report(doc),
        "rtf": doc["timing"]["realtime_factor"],
        "peak_rss_mb": doc["timing"]["peak_rss_mb"],
    }


def write_results(rows: list[dict], out: Path, clip: Path, reference: Reference) -> None:
    """Write ``pilot/RESULTS.md`` — the artefact the T2 sign-off reads."""
    best = max(
        (r for r in rows if r["scores"]["filler_recall"] == r["scores"]["filler_recall"]),
        key=lambda r: (r["scores"]["filler_recall"], -r["scores"]["wer"]),
        default=None,
    )
    lines = [
        "# Pilot results (PLAN §4)",
        "",
        f"Clip: `{clip}` · reference: {len(reference.lines)} utterances, "
        f"{len(tokens(reference.text))} words",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S%z')}",
        "",
        "**Gate (PLAN §4.2): filler recall ≥ 0.85, MC + guest + ≥2 vox-pop on separate "
        "clusters, key terms present with hotwords, timestamps within ~200 ms.**",
        "",
        "Pick by filler-recall-at-acceptable-WER, **not** by WER alone (§4.3).",
        "",
        "| blank_pen | decoding | int8 | vad_th | diar_th | filler recall | WER | "
        "clusters | RTF |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        c, s = row["config"], row["scores"]
        lines.append(
            f"| {c['blank_penalty']} | {c['decoding_method'].replace('_search','')} | "
            f"{c['int8']} | {c['vad_threshold']} | {c['diar_threshold']} | "
            f"{s['filler_recall']:.3f} | {s['wer']:.3f} | "
            f"{s['diarization']['n_clusters']} | {s['rtf']} |"
        )
    if best:
        lines += [
            "", "## Best by filler recall", "",
            "```json", json.dumps(best["config"], ensure_ascii=False, indent=2), "```",
            "", "### Per-filler counts (hyp / ref)", "",
            "| filler | hyp | ref |", "|---|---|---|",
        ]
        for filler, (h, r) in best["scores"]["per_filler"].items():
            lines.append(f"| {filler} | {h} | {r} |")
        lines += [
            "", "### Sample output (verbatim, unedited)", "",
            "```", best["scores"]["hyp"][:4000], "```",
            "", "### Reference (first 20 lines)", "",
            "```",
            *[f"{s}\t{t}" for s, t in reference.lines[:20]],
            "```",
        ]
    lines += [
        "", "## Decision", "",
        "- [ ] 30M vs 150M: ",
        "- [ ] Chosen knobs written to the `settings` table: ",
        "- [ ] **Owner sign-off on verbatim:** ",
        "",
        "If verbatim failed on every setting: stop and escalate (PLAN §4.3). Do not "
        "start T3.",
        "",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clip", type=Path, default=Path("pilot/clip_2min.wav"))
    ap.add_argument("--reference", type=Path, default=Path("pilot/reference.txt"))
    ap.add_argument("--models", type=Path, default=Path("models"))
    ap.add_argument("--hotwords", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("pilot/RESULTS.md"))
    ap.add_argument("--work-dir", type=Path, default=Path("pilot/out"))
    ap.add_argument("--full-grid", action="store_true",
                    help="all 240 combinations instead of one axis at a time")
    args = ap.parse_args(argv)

    if not args.clip.exists():
        print(f"error: {args.clip} not found — cut the 2-minute clip first (PLAN §4.1)",
              file=sys.stderr)
        return 1
    if not args.reference.exists():
        print(f"error: {args.reference} not found — build it from the docx (PLAN §4.1)",
              file=sys.stderr)
        return 1

    reference = Reference.load(args.reference)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    configs = configurations(SWEEP, full=args.full_grid)
    print(f"{len(configs)} configurations over {args.clip}")
    for n, cfg in enumerate(configs, 1):
        print(f"[{n}/{len(configs)}] {cfg}")
        try:
            doc = run_one(args.clip, args.models, cfg, args.work_dir, args.hotwords)
        except Exception as exc:  # noqa: BLE001 — one bad config must not end the sweep
            print(f"  failed: {exc}", file=sys.stderr)
            continue
        scores = score(doc, reference)
        print(f"  filler recall {scores['filler_recall']:.3f}  WER {scores['wer']:.3f}  "
              f"clusters {scores['diarization']['n_clusters']}")
        rows.append({"config": cfg, "scores": scores})

    if not rows:
        print("every configuration failed — nothing to write", file=sys.stderr)
        return 1

    write_results(rows, args.out, args.clip, reference)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
