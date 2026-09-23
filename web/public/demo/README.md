# Demo fixture — NOT client data

`episode.json` is genuine output from `python -m app.pipeline.run` (schema §5): real
word timestamps, real log-prob confidences, real diarization clusters.

`episode.mp3` is the audio it was produced from — Vietnamese ASR test clips from the
public `csukuangfj/sherpa-onnx-zipformer-vi-2025-04-20` repo, concatenated. It is **not**
VOV material and contains no client audio and no vox-pop speech (PLAN §0.3).

It exists so the Episode screen can be driven end-to-end before the T3 API handlers
land. Regenerate with `make demo`. Both files are gitignored.
