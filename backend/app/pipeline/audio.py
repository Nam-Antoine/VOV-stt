"""Audio ingest: decode to 16 kHz mono PCM, hash, measure (PLAN §3).

The 16 kHz WAV is **kept** — every timestamp in the corpus is measured against it, not
against the source mp3. PLAN §13: "always compute offsets from the 16 kHz WAV, not the
mp3", because a resample can shift duration by a frame or two.

Nothing here touches text, so there is no verbatim risk in this module.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

TARGET_SAMPLE_RATE = 16_000
TARGET_CHANNELS = 1


@dataclass(frozen=True)
class AudioInfo:
    """Everything the raw JSON's ``audio`` and ``source`` blocks need."""

    source_path: Path
    wav_path: Path
    source_sha256: str
    duration_s: float
    sample_rate: int
    channels: int

    def as_source_block(self, url: str | None = None) -> dict:
        return {
            "filename": self.source_path.name,
            "url": url,
            "sha256": self.source_sha256,
        }

    def as_audio_block(self) -> dict:
        return {
            "duration_s": self.duration_s,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
        }

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_path"] = str(self.source_path)
        d["wav_path"] = str(self.wav_path)
        return d


class FfmpegMissing(RuntimeError):
    """ffmpeg/ffprobe not on PATH."""


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise FfmpegMissing(
            f"{tool} not found on PATH. Install it (apt-get install ffmpeg); "
            "the container image already has it."
        )
    return path


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """sha256 of the file as it arrived — used for dedupe and provenance."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def probe_duration_s(path: Path) -> float:
    """Container duration in seconds, via ffprobe."""
    out = subprocess.run(
        [
            _require("ffprobe"), "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def to_wav16k(src: Path, dest: Path, *, overwrite: bool = False) -> Path:
    """Decode ``src`` to 16 kHz mono ``pcm_s16le`` WAV at ``dest``.

    PLAN §3: ``ffmpeg -i in -ac 1 -ar 16000 -f wav -acodec pcm_s16le``.
    No loudness normalisation, no denoise, no silence trimming — filters change what the
    ASR hears and the pilot's numbers would stop meaning anything.
    """
    src, dest = Path(src), Path(dest)
    if dest.exists() and not overwrite:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    subprocess.run(
        [
            _require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", str(src),
            "-ac", str(TARGET_CHANNELS), "-ar", str(TARGET_SAMPLE_RATE),
            "-acodec", "pcm_s16le", "-f", "wav", str(tmp),
        ],
        check=True, capture_output=True, text=True,
    )
    tmp.replace(dest)
    return dest


def read_wav_f32(path: Path) -> tuple[np.ndarray, int]:
    """Read a mono WAV as float32 in [-1, 1] — the shape sherpa-onnx wants.

    Uses the stdlib ``wave`` module so the pipeline has no hard ``soundfile``
    dependency for the one format we control.
    """
    import wave

    with wave.open(str(path), "rb") as wf:
        channels, width, rate = wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    if width != 2:
        raise ValueError(f"{path}: expected 16-bit PCM, got {width * 8}-bit")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return np.ascontiguousarray(samples), rate


def prepare(src: Path, wav_dir: Path, *, overwrite: bool = False) -> AudioInfo:
    """Full ingest for one episode: hash the source, decode, measure the WAV."""
    src = Path(src)
    wav_path = Path(wav_dir) / f"{src.stem}.16k.wav"
    to_wav16k(src, wav_path, overwrite=overwrite)
    samples, rate = read_wav_f32(wav_path)
    return AudioInfo(
        source_path=src,
        wav_path=wav_path,
        source_sha256=sha256_file(src),
        duration_s=len(samples) / rate,  # measured on the 16 kHz WAV, per PLAN §13
        sample_rate=rate,
        channels=TARGET_CHANNELS,
    )
