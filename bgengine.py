"""bgengine.py -- pure-Python backgammon move engine (no dependencies).

Conventions
-----------
The side to move is always "me" and is written with POSITIVE numbers.

    board[i]   i = 0..23  ->  point number i+1 from my side.
               I move from high index to low index; bearing off happens
               "below" index 0 (my home board is indices 0..5).
               Positive = my checkers, negative = opponent's checkers.
    bar_me, bar_opp, off_me, off_opp : checkers on the bar / borne off.

The opponent is handled by flipping the whole position (flipped()), so the
same move generator and evaluator serve both sides.

What is exact and what is an estimate
-------------------------------------
* Legal-move generation (forced-move rules, bar entry, bearing off): exact.
* Shot odds ("x/36 rolls hit a blot"): exact enumeration of the 21 dice
  outcomes, including combination shots and blocked intermediate points.
* Win % / equity: an ESTIMATE from a hand-built evaluator (pip count, race
  formula, points, primes, anchors, blot exposure) searched 1 or 2 plies.
  It is not a neural network, so very close decisions may differ from
  GNU Backgammon or XG.
"""
import math

# (die1, die2, weight out of 36)
ROLLS = [(a, b, 1 if a == b else 2) for a in range(1, 7) for b in range(a, 7)]


# --------------------------------------------------------------------------
# Position
# --------------------------------------------------------------------------
class Position:
    __slots__ = ("board", "bar_me", "bar_opp", "off_me", "off_opp")

    def __init__(self, board=None, bar_me=0, bar_opp=0, off_me=0, off_opp=0):
        self.board = list(board) if board is not None else [0] * 24
        self.bar_me = bar_me
        self.bar_opp = bar_opp
        self.off_me = off_me
        self.off_opp = off_opp

    def copy(self):
        return Position(self.board, self.bar_me, self.bar_opp,
                        self.off_me, self.off_opp)

    def flipped(self):
        """Same position seen from the other side of the board."""
        return Position([-x for x in reversed(self.board)],
                        self.bar_opp, self.bar_me, self.off_opp, self.off_me)

    def key(self):
        return (tuple(self.board), self.bar_me, self.bar_opp,
                self.off_me, self.off_opp)


def opening_position():
    p = Position()
    p.board[23] = 2
    p.board[12] = 5
    p.board[7] = 3
    p.board[5] = 5
    p.board[0] = -2
    p.board[11] = -5
    p.board[16] = -3
    p.board[18] = -5
    return p


def validate(pos):
    """Return a list of human-readable problems (empty list = looks fine)."""
    problems = []
    me = sum(x for x in pos.board if x > 0) + pos.bar_me + pos.off_me
    opp = -sum(x for x in pos.board if x < 0) + pos.bar_opp + pos.off_opp
    if me != 15:
        problems.append("Light has %d checkers (should be 15)" % me)
    if opp != 15:
        problems.append("Red has %d checkers (should be 15)" % opp)
    return problems


def pip_counts(pos):
    """(my pips, opponent pips)."""
    b = pos.board
    me = 25 * pos.bar_me
    opp = 25 * pos.bar_opp
    for i in range(24):
        v = b[i]
        if v > 0:
            me += (i + 1) * v
        elif v < 0:
            opp += (24 - i) * (-v)
    return me, opp


# --------------------------------------------------------------------------
# Move generation
# --------------------------------------------------------------------------
def _all_home(pos):
    if pos.bar_me:
        return False
    b = pos.board
    for i in range(6, 24):
        if b[i] > 0:
            return False
    return True


def _single_moves(pos, die):
    """Legal single-die moves as (src, dst). src 24 = bar, dst -1 = off."""
    b = pos.board
    out = []
    if pos.bar_me:
        dst = 24 - die
        if b[dst] >= -1:
            out.append((24, dst))
        return out
    home = _all_home(pos)
    hi = -1
    for i in range(23, -1, -1):
        if b[i] > 0:
            hi = i
            break
    for src in range(hi, -1, -1):
        if b[src] <= 0:
            continue
        dst = src - die
        if dst >= 0:
            if b[dst] >= -1:
                out.append((src, dst))
        elif home and (dst == -1 or src == hi):
            out.append((src, -1))
    return out


def _apply(pos, mv):
    src, dst = mv
    n = pos.copy()
    nb = n.board
    hit = False
    if src == 24:
        n.bar_me -= 1
    else:
        nb[src] -= 1
    if dst == -1:
        n.off_me += 1
    else:
        if nb[dst] == -1:
            nb[dst] = 1
            n.bar_opp += 1
            hit = True
        else:
            nb[dst] += 1
    return n, hit


def _pt(p):
    if p == 24:
        return "bar"
    if p == -1:
        return "off"
    return str(p + 1)


def _notation(steps):
    chains = []  # each: [points, hit flags]
    for src, dst, hit in steps:
        for ch in chains:
            if ch[0][-1] == src and src != -1:
                ch[0].append(dst)
                ch[1].append(hit)
                break
        else:
            chains.append([[src, dst], [False, hit]])
    parts = []
    for pts, hits in chains:
        s = _pt(pts[0])
        for k in range(1, len(pts)):
            last = (k == len(pts) - 1)
            if last or hits[k]:
                s += "/" + _pt(pts[k]) + ("*" if hits[k] else "")
        parts.append((-pts[0], s))
    count = {}
    order = []
    for _, s in sorted(parts):
        if s in count:
            count[s] += 1
        else:
            count[s] = 1
            order.append(s)
    return " ".join(s if count[s] == 1 else "%s(%d)" % (s, count[s])
                    for s in order)


class Play:
    __slots__ = ("steps", "pos", "notation")

    def __init__(self, steps, pos):
        self.steps = steps
        self.pos = pos
        self.notation = _notation(steps)


def generate_plays(pos, d1, d2):
    """All distinct legal plays (resulting positions) for the roll d1-d2.

    Implements the forced-move rules: use as many dice as possible, and if
    only one die can be played, it must be the larger one when possible.
    """
    if d1 == d2:
        orders = [[d1] * 4]
    else:
        orders = [[d1, d2], [d2, d1]]
    runs = []
    best = 0
    for order in orders:
        level = {pos.key(): (pos, [])}
        depth = 0
        for die in order:
            nxt = {}
            for p, steps in level.values():
                for mv in _single_moves(p, die):
                    np_, hit = _apply(p, mv)
                    k = np_.key()
                    if k not in nxt:
                        nxt[k] = (np_, steps + [(mv[0], mv[1], hit)])
            if not nxt:
                break
            level = nxt
            depth += 1
        runs.append((depth, level, order))
        best = max(best, depth)
    if best == 0:
        return []
    runs = [r for r in runs if r[0] == best]
    if best == 1 and d1 != d2:
        big = max(d1, d2)
        if any(r[2][0] == big for r in runs):
            runs = [r for r in runs if r[2][0] == big]
    merged = {}
    for _, level, _ in runs:
        for k, (p, steps) in level.items():
            if k not in merged:
                merged[k] = Play(steps, p)
    return list(merged.values())


# --------------------------------------------------------------------------
# Exact shot odds
# --------------------------------------------------------------------------
def _open(b, idx):
    return b[idx] >= -1


def _clear(b, s, t, x):
    """Every intermediate landing spot from s down to t (step x) is open."""
    p = s - x
    while p > t:
        if b[p] <= -2:
            return False
        p -= x
    return True


def _best_hit(b, bar, blots, srcs, a, c):
    """Largest pip loss the roller can inflict with roll a-c (0 = no hit).

    b is the board from the ROLLER's side (positive = roller). blots are
    indices of the other side's single checkers; loss = index + 1 pips.
    """
    best = 0
    if a == c:
        x = a
        if bar:
            if b[24 - x] <= -2:
                return 0
            kbar, koth = 5 - bar, 4 - bar
        else:
            kbar, koth = 0, 4
        for t in blots:
            loss = t + 1
            if loss <= best:
                continue
            if kbar > 0:
                d = 24 - t
                if d % x == 0 and d // x <= kbar and _clear(b, 24, t, x):
                    best = loss
                    continue
            if koth > 0:
                for s in srcs:
                    d = s - t
                    if (d > 0 and d % x == 0 and d // x <= koth
                            and _clear(b, s, t, x)):
                        best = loss
                        break
        return best

    if bar >= 2:
        for t in blots:
            loss = t + 1
            if loss > best and (t == 24 - a or t == 24 - c):
                best = loss
        return best
    if bar == 1:
        for e, r in ((a, c), (c, a)):
            ent = 24 - e
            if not _open(b, ent):
                continue
            starts = srcs + [ent]
            for t in blots:
                loss = t + 1
                if loss <= best:
                    continue
                if t == ent:
                    best = loss
                    continue
                for s in starts:
                    if s - t == r:
                        best = loss
                        break
        return best

    for t in blots:
        loss = t + 1
        if loss <= best:
            continue
        for s in srcs:
            d = s - t
            if d <= 0:
                continue
            if d == a or d == c:
                best = loss
                break
            if d == a + c and (_open(b, s - a) or _open(b, s - c)):
                best = loss
                break
    return best


def hit_stats(pos):
    """The opponent is on roll and shoots at my blots.

    Returns (rolls_that_hit out of 36, expected pips lost, number of blots).
    """
    f = pos.flipped()
    b = f.board
    bar = f.bar_me  # opponent checkers on the bar
    blots = [t for t in range(24) if b[t] == -1]
    if not blots:
        return 0, 0.0, 0
    srcs = [s for s in range(24) if b[s] > 0]
    nhit = 0
    loss_sum = 0
    for a, c, w in ROLLS:
        best = _best_hit(b, bar, blots, srcs, a, c)
        if best:
            nhit += w
            loss_sum += w * best
    return nhit, loss_sum / 36.0, len(blots)


# --------------------------------------------------------------------------
# Evaluation (estimate)
# --------------------------------------------------------------------------
HOME_PT = [0.5, 1.5, 2.0, 3.0, 4.0, 3.0]          # made point, idx 0..5
OUTER_PT = {6: 2.5, 7: 2.0, 8: 1.0, 9: 0.5}       # bar, 8, 9, 10 points
ANCHOR = {18: 3.0, 19: 5.0, 20: 4.0, 21: 2.5, 22: 1.0, 23: 0.5}
PRIME = [0, 0, 0, 2.0, 5.0, 9.0, 14.0]


def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _has_contact(pos):
    b = pos.board
    max_me = -1
    if pos.bar_me:
        max_me = 24
    else:
        for i in range(23, -1, -1):
            if b[i] > 0:
                max_me = i
                break
    min_opp = 99
    if pos.bar_opp:
        min_opp = -1
    else:
        for i in range(24):
            if b[i] < 0:
                min_opp = i
                break
    return max_me > min_opp


def _race_waste(pos):
    """Keith-style wastage adjustment, bear-off phase only."""
    if not _all_home(pos):
        return 0
    m = [max(0, x) for x in pos.board[:6]]
    w = 2 * max(0, m[0] - 1) + max(0, m[1] - 1) + max(0, m[2] - 2)
    for i in (3, 4, 5):
        if m[i] == 0:
            w += 1
    return w


def _structure(pos):
    b = pos.board
    s = 0.0
    run = best = 0
    for i in range(12):
        if b[i] >= 2:
            if i < 6:
                s += HOME_PT[i]
            else:
                s += OUTER_PT.get(i, 0.0)
            run += 1
            best = max(best, run)
        else:
            run = 0
    s += PRIME[min(best, 6)]
    for i in range(18, 24):
        if b[i] >= 2:
            s += ANCHOR[i]
    for i in range(24):
        if b[i] > 3:
            s -= 0.8 * (b[i] - 3)
    s -= 4.0 * pos.bar_me
    return s


def evaluate(pos, me_on_roll):
    """Estimated cubeless equity for me in [-1, 1] (about 2*P(win) - 1)."""
    if pos.off_me >= 15:
        return 1.0
    if pos.off_opp >= 15:
        return -1.0
    me_p, opp_p = pip_counts(pos)
    if not _has_contact(pos):
        a_me = me_p + _race_waste(pos)
        a_op = opp_p + _race_waste(pos.flipped())
        d = a_op - a_me + (4.0 if me_on_roll else -4.0)
        sigma = 2.13 * math.sqrt(max(10.0, (a_me + a_op) / 2.0))
        return 2.0 * _phi(d / sigma) - 1.0

    f = pos.flipped()
    score = (opp_p - me_p) + (4.0 if me_on_roll else -4.0)
    score += _structure(pos) - _structure(f)
    _, l_me, _ = hit_stats(pos)   # opponent shooting at my blots
    _, l_op, _ = hit_stats(f)     # me shooting at his blots
    b = pos.board
    my_board = sum(1 for i in range(6) if b[i] >= 2)
    opp_board = sum(1 for i in range(18, 24) if b[i] <= -2)
    f_me = 1.2 + 0.12 * opp_board   # being hit hurts more vs a strong board
    f_op = 1.2 + 0.12 * my_board
    if me_on_roll:
        score += f_op * l_op - 0.25 * f_me * l_me
    else:
        score += -f_me * l_me + 0.25 * f_op * l_op
    return 2.0 * _phi(score / 22.0) - 1.0


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------
class Candidate:
    __slots__ = ("notation", "pos", "steps", "equity", "ply",
                 "shot_rolls", "blots", "pips")

    def __init__(self, play):
        self.notation = play.notation
        self.pos = play.pos
        self.steps = play.steps
        self.equity = 0.0
        self.ply = 1
        self.shot_rolls = 0
        self.blots = 0
        self.pips = 0

    @property
    def win_pct(self):
        return (self.equity + 1.0) * 50.0


def _two_ply(cpos):
    """Average over the opponent's 21 rolls of his best reply (by my eval)."""
    f = cpos.flipped()
    total = 0.0
    for a, c, w in ROLLS:
        plays = generate_plays(f, a, c)
        if not plays:
            v = evaluate(cpos, True)
        else:
            v = 2.0
            for pl in plays:
                e = evaluate(pl.pos.flipped(), True)
                if e < v:
                    v = e
        total += w * v
    return total / 36.0


def analyze(pos, d1, d2, depth=2, top_n=8, progress=None):
    """Rank every legal play for roll d1-d2.

    depth 1: static evaluation after the move (instant).
    depth 2: the best `top_n` plays are re-scored by averaging over all 21
             opponent rolls and his best reply.
    Returns a list of Candidate, best first. Plays scored at 2 ply come
    first (ply == 2); the remainder are ordered by 1-ply score.
    """
    cands = []
    for pl in generate_plays(pos, d1, d2):
        c = Candidate(pl)
        c.equity = evaluate(pl.pos, False)
        c.shot_rolls, _, c.blots = hit_stats(pl.pos)
        c.pips = pip_counts(pl.pos)[0]
        cands.append(c)
    cands.sort(key=lambda c: -c.equity)
    if depth >= 2 and cands:
        k = min(top_n, len(cands))
        for i in range(k):
            cands[i].equity = _two_ply(cands[i].pos)
            cands[i].ply = 2
            if progress:
                progress(i + 1, k)
        head = sorted(cands[:k], key=lambda c: -c.equity)
        cands = head + cands[k:]
    return cands


# --------------------------------------------------------------------------
# Board editing helpers used by the touch UI (pure functions, unit-tested)
# --------------------------------------------------------------------------
def count_side(pos, side):
    """Total checkers for side 'L' (me, positive) or 'R' (opponent)."""
    if side == "L":
        return sum(x for x in pos.board if x > 0) + pos.bar_me + pos.off_me
    return -sum(x for x in pos.board if x < 0) + pos.bar_opp + pos.off_opp


def edit_point(pos, idx, side, delta):
    """Add (+1) or remove (-1) one checker of `side` on point index idx.
    Returns True if the position changed."""
    sign = 1 if side == "L" else -1
    v = pos.board[idx]
    if delta > 0:
        if v * sign < 0 or count_side(pos, side) >= 15:
            return False
        pos.board[idx] += sign
        return True
    if v * sign > 0:
        pos.board[idx] -= sign
        return True
    return False


def edit_bar(pos, side, delta):
    if side == "L":
        if delta > 0 and count_side(pos, "L") < 15:
            pos.bar_me += 1
            return True
        if delta < 0 and pos.bar_me > 0:
            pos.bar_me -= 1
            return True
    else:
        if delta > 0 and count_side(pos, "R") < 15:
            pos.bar_opp += 1
            return True
        if delta < 0 and pos.bar_opp > 0:
            pos.bar_opp -= 1
            return True
    return False


def edit_off(pos, side, delta):
    if side == "L":
        if delta > 0 and count_side(pos, "L") < 15:
            pos.off_me += 1
            return True
        if delta < 0 and pos.off_me > 0:
            pos.off_me -= 1
            return True
    else:
        if delta > 0 and count_side(pos, "R") < 15:
            pos.off_opp += 1
            return True
        if delta < 0 and pos.off_opp > 0:
            pos.off_opp -= 1
            return True
    return False
