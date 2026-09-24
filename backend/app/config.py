"""Settings — every knob comes from the environment (PLAN §6, .env.example).

Pipeline parameters live here rather than in code so the pilot (§4.3) can change them
without a rebuild, and so the values that produced a transcript can be recorded in
``transcripts.params``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- app ---------------------------------------------------------------
    secret_key: str = "dev-only-change-me"
    #: Off: no login, everyone is treated as an admin and edits are recorded as
    #: ``open_editor``. On: per-user accounts (app/api/auth.py, app/api/users.py).
    auth_enabled: bool = False
    open_editor: str = "verifier"
    session_cookie_name: str = "vnstt_session"
    session_max_age_s: int = 30 * 24 * 3600
    log_level: str = "INFO"

    # --- database ----------------------------------------------------------
    database_url: str = "postgresql+psycopg://vnstt:vnstt@db:5432/vnstt"

    # --- storage (PLAN §6) -------------------------------------------------
    data_dir: Path = Path("/data")
    models_dir: Path = Path("/data/models")
    audio_dir: Path = Path("/data/audio")
    raw_dir: Path = Path("/data/raw")
    exports_dir: Path = Path("/data/exports")
    #: Generated at run time, so it cannot live in models_dir — that is mounted
    #: read-only in compose so a bad deploy cannot corrupt the downloaded ONNX.
    hotwords_file: Path = Path("/data/hotwords.txt")

    # --- engine (PLAN §2) --------------------------------------------------
    asr_model_dir: Path = Path("/data/models/zipformer-30m-rnnt-6000h")
    asr_int8: bool = True
    asr_num_threads: int = 2
    asr_decoding_method: str = "modified_beam_search"
    asr_max_active_paths: int = 4
    asr_blank_penalty: float = 0.25
    hotwords_score: float = 1.5

    # --- vad (PLAN §3) -----------------------------------------------------
    vad_model: Path = Path("/data/models/vad/silero_vad.onnx")
    vad_threshold: float = 0.3
    vad_min_speech_s: float = 0.1
    vad_min_silence_s: float = 0.4
    vad_pad_s: float = 0.35
    vad_merge_gap_s: float = 0.3
    vad_max_segment_s: float = 25.0
    vad_min_speech_ratio: float = 0.70

    # --- diarization (PLAN §3) ---------------------------------------------
    diar_segmentation_model: Path = Path(
        "/data/models/diarization/sherpa-onnx-pyannote-segmentation-3-0/model.onnx"
    )
    diar_embedding_model: Path = Path(
        "/data/models/diarization/speaker-embedding/"
        "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
    )
    diar_threshold: float = 0.8
    diar_num_clusters: int = 0
    diar_min_duration_on: float = 0.3
    diar_min_duration_off: float = 0.5
    #: pyannote window step (fraction of 10 s). 0.2 halves diarization time; see DiarParams.
    diar_window_shift_ratio: float = 0.2
    diar_num_threads: int = 2

    # --- readable layer: punctuation + capitalisation (derived, never the corpus) ---
    #: ViBERT-capu ONNX (CC BY-SA 4.0). Missing model = readable layer off, nothing else.
    punct_model_dir: Path = Path("/data/models/punctuation/vibert-capu")
    punct_model_file: str = "vibert-capu.onnx"
    punct_num_threads: int = 2
    #: Tuned on the first half of the client's hand-punctuated reference, scored on the
    #: unseen second half (scripts/punct_eval.py). stop_bias fixes the model's habit of
    #: writing a comma where the reference ends the sentence.
    punct_keep_bias: float = 0.0
    punct_stop_bias: float = 1.0

    # --- worker ------------------------------------------------------------
    worker_poll_interval_s: float = 2.0
    worker_max_attempts: int = 3
    #: Diarization is the slow stage (~3-5x realtime vs ASR's ~7x) and it is what makes
    #: the box hot. On by default because the deliverable is speaker-labelled text, but
    #: a job can turn it off per run, and a loaded host can turn it off globally.
    diarize_by_default: bool = True
    #: Niceness applied to the worker process. The API and the reverse proxy must stay
    #: responsive while an episode transcribes; the worker has no latency requirement.
    worker_nice: int = 10

    # --- optional second engine (PLAN §11 T6) ------------------------------
    #: OFF by default. Turning this on sends audio abroad — see LICENSE-NOTICE.md.
    enable_scribe: bool = False
    elevenlabs_api_key: str = Field(default="", repr=False)

    # --- derived -----------------------------------------------------------
    def ensure_dirs(self) -> None:
        for d in (self.audio_dir, self.raw_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)

    def asr_params(self, hotwords_file: str | None = None):
        """An :class:`app.pipeline.asr.AsrParams` built from these settings."""
        from .pipeline.asr import AsrParams

        return AsrParams(
            model_dir=str(self.asr_model_dir),
            vocab_cache_dir=str(self.data_dir),
            int8=self.asr_int8,
            num_threads=self.asr_num_threads,
            blank_penalty=self.asr_blank_penalty,
            decoding_method=self.asr_decoding_method,
            max_active_paths=self.asr_max_active_paths,
            hotwords_file=hotwords_file,
            hotwords_score=self.hotwords_score,
        )

    def vad_params(self):
        from .pipeline.vad import VadParams

        return VadParams(
            model=str(self.vad_model),
            threshold=self.vad_threshold,
            min_speech_s=self.vad_min_speech_s,
            min_silence_s=self.vad_min_silence_s,
            pad_s=self.vad_pad_s,
            merge_gap_s=self.vad_merge_gap_s,
            max_segment_s=self.vad_max_segment_s,
            min_speech_ratio=self.vad_min_speech_ratio,
        )

    def diar_params(self):
        from .pipeline.diarize import DiarParams

        return DiarParams(
            segmentation_model=str(self.diar_segmentation_model),
            embedding_model=str(self.diar_embedding_model),
            threshold=self.diar_threshold,
            num_clusters=self.diar_num_clusters,
            min_duration_on=self.diar_min_duration_on,
            min_duration_off=self.diar_min_duration_off,
            window_shift_ratio=self.diar_window_shift_ratio,
            num_threads=self.diar_num_threads,
        )

    def punct_params(self):
        from .pipeline.punctuate import ModelSpec, PunctParams

        return PunctParams(
            models=(ModelSpec(self.punct_model_dir, self.punct_model_file, "wordpiece"),),
            num_threads=self.punct_num_threads,
            keep_bias=self.punct_keep_bias,
            stop_bias=self.punct_stop_bias,
        )

    def punct_available(self) -> bool:
        return (self.punct_model_dir / self.punct_model_file).exists()

    def models_present(self) -> dict[str, bool]:
        """Used by ``/api/health`` (PLAN §11 T5)."""
        return {
            "asr_tokens": (self.asr_model_dir / "tokens.txt").exists(),
            "asr_encoder": any(self.asr_model_dir.glob("encoder-*.onnx")),
            "asr_bpe": (self.asr_model_dir / "bpe.model").exists(),
            "vad": self.vad_model.exists(),
            "diar_segmentation": self.diar_segmentation_model.exists(),
            "diar_embedding": self.diar_embedding_model.exists(),
            "punctuation": self.punct_available(),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
