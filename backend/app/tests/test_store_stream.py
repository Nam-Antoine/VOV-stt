"""store_stream: a failed upload leaves nothing behind in AUDIO_DIR."""

from __future__ import annotations

import io

import pytest

from app.ingest import store_stream


class _DiskFull(io.BytesIO):
    """Serves one chunk, then fails the way a full disk does mid-upload."""

    def __init__(self) -> None:
        super().__init__(b"x" * 10)
        self.calls = 0

    def read(self, size: int = -1) -> bytes:
        self.calls += 1
        if self.calls > 1:
            raise OSError(28, "No space left on device")
        return super().read(size)


def test_success_writes_dest_and_no_part(tmp_path):
    dest = tmp_path / "a.mp3"
    store_stream(io.BytesIO(b"abc"), dest)
    assert dest.read_bytes() == b"abc"
    assert list(tmp_path.iterdir()) == [dest]


def test_failure_removes_part_file(tmp_path):
    with pytest.raises(OSError):
        store_stream(_DiskFull(), tmp_path / "a.mp3")
    assert list(tmp_path.iterdir()) == []
