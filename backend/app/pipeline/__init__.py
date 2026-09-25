"""The transcription pipeline (PLAN §3).

    audio → vad → asr → utterances → raw JSON

Stage modules are importable without the native runtime: ``sherpa_onnx`` is imported
inside the functions that need it, so the pure-python parts (``asr.tokens_to_words``,
``merge``) and their tests run anywhere.
"""
