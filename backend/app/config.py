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
    app_password: str = "change-me"
    secret_key: str = "dev-only-change-me"
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

    # --- engine (PLAN §2) --------------------------------------------------
    asr_model_dir: Path = Path("/data/models/zipformer-30m-rnnt-6000h")
    asr_int8: bool = True
    asr_num_threads: int = 3
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
    diar_threshold: float = 0.7
    diar_num_clusters: int = 0
    diar_min_duration_on: float = 0.3
    diar_min_duration_off: float = 0.5
    diar_num_threads: int = 3

    # --- worker ------------------------------------------------------------
    worker_poll_interval_s: float = 2.0
    worker_max_attempts: int = 3

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
            num_threads=self.diar_num_threads,
        )

    def models_present(self) -> dict[str, bool]:
        """Used by ``/api/health`` (PLAN §11 T5)."""
        return {
            "asr_tokens": (self.asr_model_dir / "tokens.txt").exists(),
            "asr_encoder": any(self.asr_model_dir.glob("encoder-*.onnx")),
            "asr_bpe": (self.asr_model_dir / "bpe.model").exists(),
            "vad": self.vad_model.exists(),
            "diar_segmentation": self.diar_segmentation_model.exists(),
            "diar_embedding": self.diar_embedding_model.exists(),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
