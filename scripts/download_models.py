#!/usr/bin/env python3
"""Download every model file the pipeline needs into ``models/``.

PLAN §11 T0. Idempotent: re-running verifies sha256s and re-downloads only what is
missing or corrupt.

Sources
-------
ASR        ``hynt/Zipformer-30M-RNNT-6000h``   (CC BY-NC-ND 4.0 — see LICENSE-NOTICE.md)
VAD        ``csukuangfj/vad``                  (silero_vad.onnx)
Diarization segmentation
           ``csukuangfj/sherpa-onnx-pyannote-segmentation-3-0``
Diarization embedding
           ``csukuangfj/speaker-embedding-models``

Two things about the ASR repo that trip people up (PLAN §2, §13):

* ``config.json`` **is not JSON**. It is the tokens file. We save it as ``tokens.txt``
  and assert the first line is ``<blk> 0``.
* ``jit_script.pt`` is deliberately **not** downloaded — HF flags it as a suspicious
  pickle and we only use the ONNX graphs.

Usage
-----
    python scripts/download_models.py --dest models
    python scripts/download_models.py --dest models --verify-only
    python scripts/download_models.py --dest models --fp32        # also pull fp32 ONNX
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "MANIFEST.json"
MANIFEST_VERSION = 1

ASR_REPO = "hynt/Zipformer-30M-RNNT-6000h"
ASR_DIR = "zipformer-30m-rnnt-6000h"
VAD_REPO = "csukuangfj/vad"
SEG_REPO = "csukuangfj/sherpa-onnx-pyannote-segmentation-3-0"
EMB_REPO = "csukuangfj/speaker-embedding-models"
PUNCT_REPO = "welcomyou/vibert-capu-onnx"

#: PLAN §3 recommends 3D-Speaker or WeSpeaker. The zh_en advanced CAM++ is the
#: general-purpose default; override with --embedding.
DEFAULT_EMBEDDING = "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"


@dataclass(frozen=True)
class Item:
    """One file to fetch: ``repo``/``remote`` → ``<dest>/<local>``."""

    repo: str
    remote: str
    local: str
    role: str
    note: str = ""
    #: Set for config.json → tokens.txt, which must start with "<blk> 0".
    expect_first_line: str | None = None


@dataclass
class Report:
    downloaded: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def plan_items(*, int8: bool, fp32: bool, embedding: str) -> list[Item]:
    """Build the download list. ``int8`` and ``fp32`` are not exclusive."""
    items: list[Item] = []

    suffixes: list[str] = []
    if int8:
        suffixes.append(".int8.onnx")
    if fp32:
        suffixes.append(".onnx")
    for part in ("encoder", "decoder", "joiner"):
        for sfx in suffixes:
            name = f"{part}-epoch-20-avg-10{sfx}"
            items.append(Item(ASR_REPO, name, f"{ASR_DIR}/{name}", role=f"asr-{part}"))

    items.append(
        Item(ASR_REPO, "bpe.model", f"{ASR_DIR}/bpe.model", role="asr-bpe",
             note="sentencepiece vocab; needed for bpe hotwords (PLAN §2)")
    )
    # PLAN §2 / §13: the repo's config.json IS tokens.txt.
    items.append(
        Item(ASR_REPO, "config.json", f"{ASR_DIR}/tokens.txt", role="asr-tokens",
             note="HF calls this config.json; it is the tokens file, not JSON",
             expect_first_line="<blk> 0")
    )

    items.append(
        Item(VAD_REPO, "silero_vad.onnx", "vad/silero_vad.onnx", role="vad",
             note="Silero VAD v4, MIT")
    )
    items.append(
        Item(SEG_REPO, "model.onnx",
             "diarization/sherpa-onnx-pyannote-segmentation-3-0/model.onnx",
             role="diarization-segmentation", note="pyannote/segmentation-3.0 ONNX export")
    )
    items.append(
        Item(EMB_REPO, embedding, f"diarization/speaker-embedding/{embedding}",
             role="diarization-embedding", note="speaker embedding extractor")
    )
    # Readable layer (app/readable.py): punctuation + capitals, CC BY-SA 4.0.
    for remote, role in (("vibert-capu.onnx", "punctuation-model"),
                         ("vocab.txt", "punctuation-vocab"),
                         ("vocabulary/labels.txt", "punctuation-labels")):
        items.append(
            Item(PUNCT_REPO, remote, f"punctuation/vibert-capu/{remote}", role=role,
                 note="ViBERT-capu ONNX; readable layer only, never corpus text")
        )
    return items


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def load_manifest(dest: Path) -> dict:
    path = dest / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"  ! {path} is not valid JSON; it will be rewritten", file=sys.stderr)
        return {}


def check_tokens_file(path: Path, expected: str) -> None:
    """Fail loudly if tokens.txt does not look like a tokens file (PLAN §13)."""
    with path.open("r", encoding="utf-8") as fh:
        first = fh.readline().strip()
    if first != expected:
        raise RuntimeError(
            f"{path} first line is {first!r}, expected {expected!r}. "
            "Did the upstream repo change, or did something rewrite the file?"
        )


def fetch(item: Item, dest: Path, *, token: str | None) -> Path:
    """Download one file via huggingface_hub and place it at its local path."""
    from huggingface_hub import hf_hub_download  # imported late: optional dependency

    target = dest / item.local
    target.parent.mkdir(parents=True, exist_ok=True)
    cached = hf_hub_download(repo_id=item.repo, filename=item.remote, token=token)
    # Copy rather than symlink: /data/models is bind-mounted read-only into the
    # containers and must not depend on the host's HF cache surviving.
    shutil.copyfile(cached, target)
    return target


def run(dest: Path, *, int8: bool, fp32: bool, embedding: str, verify_only: bool,
        force: bool, token: str | None) -> int:
    items = plan_items(int8=int8, fp32=fp32, embedding=embedding)
    dest.mkdir(parents=True, exist_ok=True)
    old = load_manifest(dest)
    old_files = {f["path"]: f for f in old.get("files", [])}

    report = Report()
    entries: list[dict] = []

    for item in items:
        target = dest / item.local
        known = old_files.get(item.local, {})
        have = target.exists()
        digest: str | None = None

        if have and not force:
            digest = sha256_file(target)
            if known.get("sha256") and known["sha256"] != digest:
                print(f"  ! {item.local}: sha256 changed since the manifest was written")
                have = False if not verify_only else have

        if verify_only:
            status = "ok" if have else "MISSING"
            print(f"  {status:<8} {item.local}")
            if not have:
                report.failed.append((item.local, "missing"))
            else:
                report.reused.append(item.local)
        elif have and not force:
            print(f"  reuse    {item.local}")
            report.reused.append(item.local)
        else:
            print(f"  fetch    {item.repo}/{item.remote} -> {item.local}")
            try:
                target = fetch(item, dest, token=token)
                digest = sha256_file(target)
                report.downloaded.append(item.local)
            except Exception as exc:  # noqa: BLE001 — report and keep going
                print(f"  ! failed: {exc}", file=sys.stderr)
                report.failed.append((item.local, str(exc)))
                continue

        if item.expect_first_line and target.exists():
            check_tokens_file(target, item.expect_first_line)

        if target.exists():
            entries.append(
                {
                    "path": item.local,
                    "role": item.role,
                    "repo": item.repo,
                    "remote": item.remote,
                    "bytes": target.stat().st_size,
                    "sha256": digest or sha256_file(target),
                    "note": item.note,
                }
            )

    if not verify_only:
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "asr": {
                "name": "zipformer-30m-rnnt-6000h",
                "hf_repo": ASR_REPO,
                "licence": "CC BY-NC-ND 4.0 — non-commercial; see LICENSE-NOTICE.md",
                "dir": ASR_DIR,
            },
            "files": sorted(entries, key=lambda e: e["path"]),
        }
        path = dest / MANIFEST_NAME
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {path} ({len(entries)} files)")

    print(
        f"\ndownloaded={len(report.downloaded)} reused={len(report.reused)} "
        f"failed={len(report.failed)}"
    )
    if report.failed:
        for name, why in report.failed:
            print(f"  FAILED {name}: {why}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", type=Path, default=Path("models"),
                    help="destination directory (default: models)")
    ap.add_argument("--no-int8", dest="int8", action="store_false",
                    help="skip the int8 ONNX graphs")
    ap.add_argument("--fp32", action="store_true",
                    help="also download the fp32 ONNX graphs (for the §4.3 int8-vs-fp32 sweep)")
    ap.add_argument("--embedding", default=DEFAULT_EMBEDDING,
                    help=f"speaker-embedding file in {EMB_REPO} (default: %(default)s)")
    ap.add_argument("--verify-only", action="store_true",
                    help="check what is present and its sha256; download nothing")
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    ap.add_argument("--token", default=None, help="Hugging Face token (for rate limits)")
    args = ap.parse_args(argv)

    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        print("huggingface_hub is required: pip install huggingface_hub", file=sys.stderr)
        return 2

    print(f"models -> {args.dest.resolve()}")
    print("ASR model licence: CC BY-NC-ND 4.0 (non-commercial). See LICENSE-NOTICE.md.\n")
    return run(args.dest, int8=args.int8, fp32=args.fp32, embedding=args.embedding,
               verify_only=args.verify_only, force=args.force, token=args.token)


if __name__ == "__main__":
    raise SystemExit(main())
