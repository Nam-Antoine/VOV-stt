"""Score punctuation/case restoration against the client's hand-punctuated reference.

Gold: resource/docs/TÂM SỰ CHIẾN THUẬT QUẢN TRỊ CHỒNG.docx, split into speaker blocks.
Input to a system: each block's words, lower-cased, marks stripped.
Scores (per word position, mark after word i):
  END   = sentence end (. or ?)      COMMA = ,      Q = ?      COLON = :
  ALL   = micro-F1 over every mark with the exact mark required
  CAP   = F1 over words whose first letter is upper case in the gold
Split: first half of blocks by word count = TUNE, rest = TEST (only for final report).
"""
from __future__ import annotations

import difflib
import html
import json
import re
import zipfile

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = str(ROOT / 'resource/docs/TÂM SỰ CHIẾN THUẬT QUẢN TRỊ CHỒNG.docx')
SPEAKERS = {'MC Thanh Huyền:', 'Nhà văn Di Li:', 'Nhân vật chia sẻ:', 'Ý kiến 1:', 'Ý kiến 2:',
            'Ý kiến 3:', 'Ý kiến 4:', 'Ý kiến nam giới:', 'Ý kiến nữ giới:'}
MARKS = ',.:?'
GOLD_MAP = {';': ',', '!': '.', '…': '.'}


def core(tok: str) -> str:
    junk = MARKS + ';!…"“”–-()'
    return tok.strip(junk).lower()


def mark_of(tok: str) -> str:
    t = tok.rstrip('"“”)')
    if t and t[-1] in GOLD_MAP:
        return GOLD_MAP[t[-1]]
    return t[-1] if t and t[-1] in MARKS else ''


def is_cap(tok: str) -> bool:
    t = tok.lstrip('"“(–-')
    return bool(t) and t[0].isupper()


def load_blocks():
    x = zipfile.ZipFile(REF).read('word/document.xml').decode()
    paras = [html.unescape(''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', p, re.S))).strip()
             for p in re.findall(r'<w:p[ >].*?</w:p>', x, re.S)]
    blocks, cur = [], None
    for p in paras[1:]:  # skip title
        if p in SPEAKERS:
            cur = []
            blocks.append(cur)
            continue
        if not p or cur is None:
            continue
        toks = [t for t in p.split() if core(t)]
        cur.extend(toks)
    blocks = [b for b in blocks if b]
    gold = [[{'w': core(t), 'mark': mark_of(t), 'cap': is_cap(t)} for t in b] for b in blocks]
    total = sum(len(b) for b in gold)
    acc, split = 0, len(gold)
    for k, b in enumerate(gold):
        if acc >= total / 2:
            split = k
            break
        acc += len(b)
    return gold[:split], gold[split:]


def align(gold_block, out_tokens):
    """Map system tokens to gold words; tolerate rewritten words (e.g. numbers)."""
    g = [x['w'] for x in gold_block]
    o = [core(t) for t in out_tokens]
    pred = [{'mark': '', 'cap': False, 'aligned': False} for _ in g]
    sm = difflib.SequenceMatcher(None, g, o, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for a, b in zip(range(i1, i2), range(j1, j2)):
                pred[a] = {'mark': mark_of(out_tokens[b]), 'cap': is_cap(out_tokens[b]),
                           'aligned': True}
        elif tag == 'replace':
            # rewritten span: first word's case, last word's mark
            pred[i1]['cap'] = is_cap(out_tokens[j1])
            pred[i2 - 1]['mark'] = mark_of(out_tokens[j2 - 1])
    return pred


def f1(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def score(gold_blocks, outputs):
    c = {k: [0, 0, 0] for k in ('END', 'COMMA', 'Q', 'COLON', 'ALL', 'CAP')}
    aligned = total = 0
    for gb, out in zip(gold_blocks, outputs):
        for g, p in zip(gb, align(gb, out)):
            total += 1
            aligned += p['aligned']
            gm, pm = g['mark'], p['mark']
            for key, test in (('END', lambda m: m in '.?' and m != ''), ('COMMA', lambda m: m == ','),
                              ('Q', lambda m: m == '?'), ('COLON', lambda m: m == ':')):
                gt, pt = test(gm), test(pm)
                c[key][0] += gt and pt
                c[key][1] += pt and not gt
                c[key][2] += gt and not pt
            c['ALL'][0] += bool(gm) and gm == pm
            c['ALL'][1] += bool(pm) and gm != pm
            c['ALL'][2] += bool(gm) and gm != pm
            c['CAP'][0] += g['cap'] and p['cap']
            c['CAP'][1] += p['cap'] and not g['cap']
            c['CAP'][2] += g['cap'] and not p['cap']
    res = {k: round(100 * f1(*v), 1) for k, v in c.items()}
    for k in ('END', 'COMMA'):
        tp, fp, fn = c[k]
        res[k + '_P'] = round(100 * tp / (tp + fp), 1) if tp + fp else 0.0
        res[k + '_R'] = round(100 * tp / (tp + fn), 1) if tp + fn else 0.0
    res['word_match'] = round(100 * aligned / total, 1)
    return res


def inputs(gold_blocks):
    return [[x['w'] for x in b] for b in gold_blocks]


def main() -> None:
    """Score the readable layer's punctuator on the reference.

        python scripts/punct_eval.py --split tune --keep-bias 0.5 --stop-bias 1.0

    Tune only on tune. Look at test once, for the final number.
    """
    import argparse
    import sys

    sys.path.insert(0, str(ROOT / 'backend'))
    from app.pipeline import punctuate as P

    ap = argparse.ArgumentParser()
    ap.add_argument('--split', choices=['tune', 'test'], default='tune')
    ap.add_argument('--models', default=str(ROOT / 'models/punctuation'))
    ap.add_argument('--keep-bias', type=float, default=0.0)
    ap.add_argument('--stop-bias', type=float, default=1.0)
    ap.add_argument('--with-xlmr', action='store_true', help='average with xlmr-capu')
    a = ap.parse_args()
    m = Path(a.models)
    models = [P.ModelSpec(m / 'vibert-capu', 'vibert-capu.onnx', 'wordpiece')]
    if a.with_xlmr:
        models.append(P.ModelSpec(m / 'xlmr-capu', 'xlmr-capu.onnx', 'sentencepiece'))
    p = P.Punctuator.load(P.PunctParams(models=tuple(models), keep_bias=a.keep_bias,
                                        stop_bias=a.stop_bias))
    tune, test = load_blocks()
    data = tune if a.split == 'tune' else test
    outs = [P.readable_turn(p, [' '.join(ws)])[0].split() for ws in inputs(data)]
    print(json.dumps({'split': a.split, **score(data, outs)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
