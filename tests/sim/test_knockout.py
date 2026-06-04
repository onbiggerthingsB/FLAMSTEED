import numpy as np
from wcmodel.sim.knockout import resolve_tie


def test_regulation_winner_advances_no_et():
    seq = iter([(2, 0)])
    winner = resolve_tie("X", "Y", sample=lambda phase, rng: next(seq),
                         rng=np.random.default_rng(0), et_scale=0.333, pen_home_prob=0.5)
    assert winner == "X"


def test_draw_goes_to_extra_time_then_penalties():
    scores = iter([(1, 1), (0, 0)])              # regulation draw, ET draw -> penalties
    winner = resolve_tie("X", "Y", sample=lambda phase, rng: next(scores),
                         rng=np.random.default_rng(0), et_scale=0.333, pen_home_prob=0.5)
    assert winner in ("X", "Y")
    s2 = iter([(1, 1), (0, 0)])
    w2 = resolve_tie("X", "Y", sample=lambda phase, rng: next(s2),
                    rng=np.random.default_rng(0), et_scale=0.333, pen_home_prob=0.5)
    assert winner == w2                          # penalty seeded -> reproducible


def test_et_decisive_no_penalties():
    scores = iter([(0, 0), (1, 0)])              # reg draw, ET decisive
    winner = resolve_tie("X", "Y", sample=lambda phase, rng: next(scores),
                         rng=np.random.default_rng(0), et_scale=0.333, pen_home_prob=0.5)
    assert winner == "X"


def test_phases_requested_in_order():
    seen = []
    scores = iter([(0, 0), (1, 0)])
    resolve_tie("X", "Y",
                sample=lambda phase, rng: (seen.append(phase), next(scores))[1],
                rng=np.random.default_rng(0), et_scale=0.333, pen_home_prob=0.5)
    assert seen == ["regulation", "extra_time"]  # ET only requested after a reg draw


def test_penalty_prob_respected():
    # With pen_home_prob=1.0, a drawn tie always goes to home; 0.0 -> away.
    scores = lambda phase, rng: (0, 0)
    assert resolve_tie("X", "Y", sample=scores, rng=np.random.default_rng(0),
                       et_scale=0.333, pen_home_prob=1.0) == "X"
    assert resolve_tie("X", "Y", sample=scores, rng=np.random.default_rng(0),
                       et_scale=0.333, pen_home_prob=0.0) == "Y"
