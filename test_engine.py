"""Run:  python3 test_engine.py"""
import random
import time

import bgengine as bg


def blot_position(d):
    """My lone blot is d pips in front of a single opponent checker."""
    p = bg.Position()
    p.board[0] = -1          # opponent checker (moves toward higher index)
    p.board[d] = 1           # my blot
    if d != 23:
        p.board[23] = 2      # my other checkers, out of the way
    return p


def test_shot_table():
    # Classic open-board direct+indirect shot counts (out of 36)
    expected = {1: 11, 2: 12, 3: 14, 4: 15, 5: 15, 6: 17, 7: 6, 8: 6, 9: 5,
                10: 3, 11: 2, 12: 3, 13: 0, 14: 0, 15: 1, 16: 1, 17: 0,
                18: 1, 19: 0, 20: 1, 21: 0}
    for d, n in expected.items():
        got = bg.hit_stats(blot_position(d))[0]
        assert got == n, "distance %d: expected %d got %d" % (d, n, got)
    print("shot table OK (distances 1-21)")


def test_forced_rules():
    # bar entry blocked -> no moves
    p = bg.Position()
    p.bar_me = 1
    p.board[24 - 3] = -2
    assert bg.generate_plays(p, 3, 3) == []
    # only one die playable and both individually playable -> larger die
    p = bg.Position()
    p.board[10] = 1
    p.board[3] = -2
    plays = bg.generate_plays(p, 3, 4)
    assert len(plays) == 1 and plays[0].steps[0][:2] == (10, 6), plays[0].steps
    # bear off with oversize die uses highest checker
    p = bg.Position()
    p.board[2] = 2
    p.board[1] = 1
    plays = bg.generate_plays(p, 6, 5)
    assert all(pl.pos.off_me == 2 for pl in plays)
    # cannot bear off while a checker is outside home
    p = bg.Position()
    p.board[2] = 2
    p.board[8] = 1
    for pl in bg.generate_plays(p, 2, 1):      # cannot get home with 2-1
        assert pl.pos.off_me == 0
    # 6-5: bearing off is legal only after the 6 brings the checker home
    for pl in bg.generate_plays(p, 6, 5):
        if pl.pos.off_me:
            assert pl.steps[0][:2] == (8, 2), pl.steps
    print("forced-move rules OK")


def test_opening_roll_count():
    # 3-1 from the start has 15 distinct legal plays? just check sane range
    n = len(bg.generate_plays(bg.opening_position(), 3, 1))
    assert 10 <= n <= 30, n
    print("opening 3-1 distinct plays:", n)


def random_position(rng):
    pts = list(range(24))
    rng.shuffle(pts)
    mine = pts[:rng.randint(4, 8)]
    theirs = pts[8:8 + rng.randint(4, 8)]
    p = bg.Position()
    p.bar_me = rng.choice([0, 0, 0, 1, 2])
    p.bar_opp = rng.choice([0, 0, 0, 1])
    for side, pts_, bar in ((1, mine, p.bar_me), (-1, theirs, p.bar_opp)):
        left = 15 - bar
        for i in pts_:
            p.board[i] = side
            left -= 1
        while left > 0:
            p.board[rng.choice(pts_)] += side
            left -= 1
    return p


def exact_hits(pos):
    f = pos.flipped()
    n = 0
    for a, c, w in bg.ROLLS:
        plays = bg.generate_plays(f, a, c)
        if any(pl.pos.bar_opp > f.bar_opp for pl in plays):
            n += w
    return n


def test_fast_vs_bruteforce():
    rng = random.Random(7)
    bad = 0
    total = 400
    worst = 0
    for _ in range(total):
        p = random_position(rng)
        fast = bg.hit_stats(p)[0]
        slow = exact_hits(p)
        if fast != slow:
            bad += 1
            worst = max(worst, abs(fast - slow))
    print("fast shot counter vs brute force: %d/%d positions differ "
          "(max gap %d/36)" % (bad, total, worst))
    assert bad <= total * 0.03


OPENING_BOOK = {
    (3, 1): "8/5 6/5",
    (4, 2): "8/4 6/4",
    (6, 1): "13/7 8/7",
    (5, 3): "8/3 6/3",
    (6, 5): "24/13",
    (5, 5): "13/3(2)",
    (6, 6): "24/18(2) 13/7(2)",
    (4, 4): "24/20(2) 13/9(2)",
    (3, 3): "8/5(2) 6/3(2)",
    (2, 2): "13/11(2) 6/4(2)",
    (1, 1): "8/7(2) 6/5(2)",
}


def test_opening_book(depth):
    pos = bg.opening_position()
    wrong = []
    t0 = time.time()
    for (a, b), want in OPENING_BOOK.items():
        c = bg.analyze(pos, a, b, depth=depth)
        got = c[0].notation
        if got != want:
            wrong.append(((a, b), want, got))
    dt = time.time() - t0
    print("opening book, depth %d: %d/%d match (%.1fs)" %
          (depth, len(OPENING_BOOK) - len(wrong), len(OPENING_BOOK), dt))
    for w in wrong:
        print("   roll %s: book %s, engine %s" % w)
    return wrong


if __name__ == "__main__":
    test_shot_table()
    test_forced_rules()
    test_opening_roll_count()
    test_fast_vs_bruteforce()
    test_opening_book(1)
    test_opening_book(2)


def test_editing():
    p = bg.Position()
    assert bg.edit_point(p, 5, "L", 1) and p.board[5] == 1
    assert not bg.edit_point(p, 5, "R", 1)          # cannot stack on enemy
    assert bg.edit_point(p, 6, "R", 1) and p.board[6] == -1
    assert bg.edit_point(p, 6, "R", -1) and p.board[6] == 0
    for _ in range(14):
        assert bg.edit_point(p, 0, "L", 1)
    assert not bg.edit_point(p, 1, "L", 1)          # 15 cap
    assert not bg.edit_bar(p, "L", 1) and not bg.edit_off(p, "L", 1)
    assert bg.edit_bar(p, "R", 1) and p.bar_opp == 1
    assert bg.edit_off(p, "R", 1) and p.off_opp == 1
    assert bg.count_side(p, "L") == 15
    print("editing helpers OK")


def test_smoke_midgame():
    rng = random.Random(3)
    t0 = time.time()
    for _ in range(25):
        p = random_position(rng)
        a, b = rng.randint(1, 6), rng.randint(1, 6)
        c = bg.analyze(p, a, b, depth=2)
        for cand in c:
            assert not bg.validate(cand.pos), cand.notation
    print("25 random positions analysed at 2-ply, checker counts conserved"
          " (%.1fs, %.2fs each)" % (time.time() - t0, (time.time() - t0) / 25))


if __name__ == "__main__" :
    test_editing()
    test_smoke_midgame()
