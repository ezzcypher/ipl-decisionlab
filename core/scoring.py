"""IPL DecisionLab fantasy scoring — version v1 (verified against the original Phase 3 output, all 26,759 rows).

No fielding points. Milestone bonuses STACK (a century earns 4 + 8 + 16 = 28 bonus points).
"""

VERSION = "v1 (original rules) · v1.1 identity fixes"
CREDITED_WICKETS = ("caught", "bowled", "lbw", "stumped", "caught and bowled", "hit wicket")
NOT_CREDITED = ("run out", "retired hurt", "retired out", "obstructing the field")

RULES = [
    # component, rule, points, condition
    ("Batting", "Run scored off the bat", 1, "per run (extras never count)"),
    ("Batting", "Boundary bonus — four", 1, "per ball where runs off bat = 4"),
    ("Batting", "Boundary bonus — six", 2, "per ball where runs off bat = 6"),
    ("Batting", "Milestone — 30 runs", 4, "runs ≥ 30"),
    ("Batting", "Milestone — 50 runs", 8, "runs ≥ 50 (stacks with 30)"),
    ("Batting", "Milestone — 100 runs", 16, "runs ≥ 100 (stacks with 30 and 50)"),
    ("Batting", "Duck penalty", -2, "faced ≥ 1 delivery as striker, 0 runs, and recorded as dismissed (any mode)"),
    ("Bowling", "Credited wicket", 25, "dismissal type in: " + ", ".join(CREDITED_WICKETS)),
    ("Dot ball", "Dot ball bowled", 0.5, "not a wide, 0 runs off bat and 0 extras"),
]


def batting_points(runs, fours, sixes, batted, dismissed):
    if not batted:
        return 0.0
    bonus = 4 * (runs >= 30) + 8 * (runs >= 50) + 16 * (runs >= 100)
    duck = -2 if (runs == 0 and dismissed) else 0
    return float(runs + fours + 2 * sixes + bonus + duck)


def score(runs=0, fours=0, sixes=0, batted=False, dismissed=False, wickets=0, dots=0):
    b = batting_points(int(runs), int(fours), int(sixes), bool(batted), bool(dismissed))
    w = 25.0 * int(wickets)
    d = 0.5 * int(dots)
    return {"batting": b, "bowling": w, "dot": d, "total": b + w + d}


if __name__ == "__main__":
    assert score(158, 10, 13, True, False)["total"] == 222          # BB McCullum, 2008-04-18
    assert score(0, 0, 0, True, True)["total"] == -2                 # duck
    assert score(0, 0, 0, False, True)["total"] == 0                 # run out without facing: no duck
    assert score(wickets=3, dots=11)["total"] == 80.5
    print("scoring self-check ok")
