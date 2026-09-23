"""Rewrite the seeded hotwords in the form the ASR model can actually match.

The model's BPE vocabulary is UPPERCASE and spoken-form. A mixed-case term such as
``Thanh Huyền`` encodes to ``▁T <unk> ▁H <unk>`` and biases nothing, so every 0001 seed
term except ``VOV2`` was inert. ``Đàn bà 30+`` also needs its spoken form: the model
hears and emits ``BA MƯƠI CỘNG``, never ``30+``.

These are bias *inputs*, not transcript text — the transcript is still exactly what the
engine emitted (CLAUDE.md rule 1).

Only a row still carrying the untouched 0001 spelling is rewritten, and only when the
new spelling is not already present, so an operator's own edits survive.

Revision ID: 0002_hotwords_model_form
Revises: 0001_initial
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_hotwords_model_form"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

#: 0001 spelling → model spelling.
RENAMES: list[tuple[str, str]] = [
    ("Đàn bà 30+", "ĐÀN BÀ BA MƯƠI CỘNG"),
    ("Thanh Huyền", "THANH HUYỀN"),
    ("Di Li", "DI LI"),
    ("Hoàng Anh Tú", "HOÀNG ANH TÚ"),
    ("Đỗ Anh Vũ", "ĐỖ ANH VŨ"),
    ("quản chồng", "QUẢN CHỒNG"),
    ("giữ chồng", "GIỮ CHỒNG"),
    ("giữ lửa", "GIỮ LỬA"),
    ("ngoại tình", "NGOẠI TÌNH"),
    ("tâm sự", "TÂM SỰ"),
    ("hôn nhân", "HÔN NHÂN"),
    ("chung thủy", "CHUNG THỦY"),
    ("ly hôn", "LY HÔN"),
    ("gia đình", "GIA ĐÌNH"),
]

_RENAME = sa.text(
    "UPDATE hotwords SET term = :new WHERE term = :old "
    "AND NOT EXISTS (SELECT 1 FROM hotwords WHERE term = :new)"
)


def upgrade() -> None:
    for old, new in RENAMES:
        op.execute(_RENAME.bindparams(old=old, new=new))


def downgrade() -> None:
    for old, new in RENAMES:
        op.execute(_RENAME.bindparams(old=new, new=old))
