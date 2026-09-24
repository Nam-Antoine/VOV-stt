"""Default role labels: host by turn count, guest by talk time — inside one episode only."""

from app.roles import GUEST, HOST, guess_roles


def turns(*spec):
    """(speaker, n_turns, seconds_each, first_start) -> flat list of turns."""
    out = []
    for speaker, n, each, first in spec:
        out += [(speaker, first + k * 60.0, first + k * 60.0 + each) for k in range(n)]
    return out


def test_host_takes_most_turns_and_guest_talks_longest():
    got = guess_roles(turns(
        (0, 1, 3.0, 0.0),      # jingle
        (1, 15, 22.0, 3.0),    # host: many short links
        (2, 10, 45.0, 18.0),   # guest: fewer, longer answers
        (7, 1, 45.0, 146.0),   # vox pop
    ))
    assert got == {1: HOST, 2: GUEST}


def test_a_chatty_but_brief_voice_is_not_the_host():
    # 15 tiny turns (45 s in all) must not beat the real host's 13 turns.
    got = guess_roles(turns((2, 15, 3.0, 36.0), (1, 13, 12.0, 13.0), (4, 8, 63.0, 42.0)))
    assert got == {1: HOST, 4: GUEST}


def test_callers_and_vox_pops_stay_unnamed():
    got = guess_roles(turns((1, 12, 20.0, 3.0), (2, 8, 50.0, 18.0), (9, 1, 20.0, 300.0)))
    assert 9 not in got


def test_nothing_while_speakers_are_pending():
    assert guess_roles([(-1, 0.0, 5.0), (-1, 5.0, 9.0)]) == {}
    assert guess_roles([]) == {}


def test_single_voice_gets_host_only():
    assert guess_roles(turns((3, 5, 30.0, 0.0))) == {3: HOST}
