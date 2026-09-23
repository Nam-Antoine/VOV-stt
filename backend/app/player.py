"""Player derivatives: waveform peaks and a compressed listening copy.

The browser used to download the whole 16 kHz WAV (~27 MB for 14 minutes) and decode
it before it could draw a waveform or play a sample. Both jobs move here:

* **Peaks** — a few thousand max-amplitude points computed once from the WAV. With
  peaks and a duration in hand, wavesurfer draws immediately and streams the audio
  through a plain ``<audio>`` element instead of decoding it.
* **Proxy** — mono AAC in an ``.m4a`` (~5 MB). Encoded from the 16 kHz WAV, not the
  original upload, so its timeline is the one the word timestamps were measured
  against (PLAN §13). The ``.m4a`` carries an edit list that strips the encoder
  priming, so a seek lands on the same sample as in the WAV.

Everything here is a disposable cache under ``DATA_DIR/cache/player``: it is derived,
regenerable, and never touches ``/data/raw`` (PLAN §0.2). Delete the folder and it is
rebuilt on demand.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import settings

log = logging.getLogger("player")

#: Points in the waveform. ~4 per pixel on a wide screen, ~30 KB of JSON.
PEAK_COUNT = 4000
PROXY_BITRATE = "48k"

_building: set[Path] = set()
_lock = threading.Lock()


def cache_dir() -> Path:
    return settings.data_dir / "cache" / "player"


def _key(wav: Path) -> str:
    """Cache key that changes whenever the WAV does."""
    st = wav.stat()
    return f"{wav.stem}-{st.st_size}-{int(st.st_mtime)}"


def compute_peaks(wav: Path, count: int = PEAK_COUNT) -> dict:
    """Max absolute amplitude per bin, scaled to 0..1, plus the exact duration."""
    data, rate = sf.read(str(wav), dtype="int16", always_2d=True)
    mono = np.abs(data[:, 0].astype(np.int32))
    duration = len(mono) / rate
    if len(mono) == 0:
        return {"duration": 0.0, "peaks": []}
    bins = min(count, len(mono))
    edges = np.linspace(0, len(mono), bins + 1, dtype=np.int64)
    peaks = np.maximum.reduceat(mono, edges[:-1]) / 32768.0
    return {"duration": duration, "peaks": [round(float(p), 3) for p in peaks]}


def peaks_for(wav: Path) -> dict:
    """Cached :func:`compute_peaks`."""
    path = cache_dir() / f"{_key(wav)}.peaks.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = compute_peaks(wav)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps(result), encoding="utf-8")
    tmp.replace(path)
    return result


def proxy_path(wav: Path) -> Path:
    return cache_dir() / f"{_key(wav)}.m4a"


def build_proxy(wav: Path) -> Path:
    """Encode the listening copy. Blocking; ~3 s per 14 minutes on this box."""
    dest = proxy_path(wav)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", str(wav),
            "-ac", "1", "-c:a", "aac", "-b:a", PROXY_BITRATE,
            # moov atom first: the browser can start playing before the file ends.
            "-movflags", "+faststart", "-f", "mp4", str(tmp),
        ],
        check=True, capture_output=True, text=True,
    )
    tmp.replace(dest)
    return dest


def proxy_or_schedule(wav: Path) -> Path | None:
    """The proxy if it exists; otherwise start building it and return ``None``.

    The first listener gets the WAV (still range-streamed) rather than waiting on the
    encode; everyone after gets the proxy.
    """
    dest = proxy_path(wav)
    if dest.exists():
        return dest
    with _lock:
        if wav in _building:
            return None
        _building.add(wav)

    def run() -> None:
        try:
            build_proxy(wav)
            log.info("player proxy ready: %s", dest.name)
        except Exception:  # noqa: BLE001 — the WAV keeps working; log and move on
            log.exception("player proxy failed for %s", wav)
        finally:
            with _lock:
                _building.discard(wav)

    threading.Thread(target=run, name="player-proxy", daemon=True).start()
    return None
