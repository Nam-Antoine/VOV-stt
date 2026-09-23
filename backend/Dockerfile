# One image for api + worker (PLAN §6). CPU only — no CUDA anywhere.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # PLAN §3: 4 vCPU box, ASR gets 3 threads.
    OMP_NUM_THREADS=2

# ffmpeg is a hard dependency of app/pipeline/audio.py; libsndfile backs soundfile;
# DejaVu is the Vietnamese-capable font of the PDF export.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsndfile1 ca-certificates fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/backend

# Dependencies first so a code change does not re-resolve the wheel set.
COPY pyproject.toml ./
RUN python -m pip install --upgrade pip \
    && python -m pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" \
       "pydantic>=2.8" "pydantic-settings>=2.4" "sqlalchemy>=2.0.30" "alembic>=1.13" \
       "psycopg[binary]>=3.2" "python-multipart>=0.0.9" "itsdangerous>=2.2" \
       "sherpa-onnx>=1.12" "onnxruntime>=1.18" "numpy>=1.26" "soundfile>=0.12" "sentencepiece>=0.2" \
       "huggingface_hub>=0.24" "fpdf2>=2.7"

COPY . .
RUN python -m pip install --no-deps -e .

# /data is a bind mount: audio/, raw/, exports/ and (read-only) models/.
VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
