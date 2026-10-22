"""Spaced repetition for saved words: a small Leitner ladder.

Every word sits in a box 0..6. A correct review moves it up and pushes its next
due date out (1, 2, 4, 8, 16, 32 days); a miss drops it back to box 0 and
brings it up again in ten minutes. Grades: 0 again, 1 hard, 2 good, 3 easy.
Words never reviewed have due = 0 and therefore sort first.
"""
from __future__ import annotations

DAY = 86400.0
INTERVALS = [10 * 60.0, 1 * DAY, 2 * DAY, 4 * DAY, 8 * DAY, 16 * DAY, 32 * DAY]
MAX_BOX = len(INTERVALS) - 1


def next_state(box: int, grade: int, now: float) -> tuple[int, float]:
    """(new box, next due timestamp) after reviewing a card in `box` with `grade`."""
    box = max(0, min(MAX_BOX, int(box or 0)))
    grade = max(0, min(3, int(grade)))
    if grade == 0:
        new = 0
    elif grade == 1:
        new = box                      # hard: same box, but not sooner than a day
    elif grade == 2:
        new = min(MAX_BOX, box + 1)
    else:
        new = min(MAX_BOX, box + 2)
    wait = INTERVALS[new]
    if grade == 1:
        wait = max(wait, DAY)
    return new, now + wait
