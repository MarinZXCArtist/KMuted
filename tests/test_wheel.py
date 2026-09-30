import math

import pytest

from kmuted.ui.overlay_wheel import clamp_vector, sector_for_vector


@pytest.mark.parametrize(
    "dx,dy,expected",
    [
        (0, -100, 0),  # up
        (70, -70, 1),  # up-right
        (100, 0, 2),  # right
        (70, 70, 3),
        (0, 100, 4),  # down
        (-70, 70, 5),
        (-100, 0, 6),  # left
        (-70, -70, 7),
        (-10, -100, 0),  # slightly left of up is still up
    ],
)
def test_eight_directions(dx, dy, expected):
    assert sector_for_vector(dx, dy, 8, 40) == expected


def test_deadzone_and_counts():
    assert sector_for_vector(10, 10, 8, 40) == -1
    assert sector_for_vector(100, 0, 4, 40) == 1
    assert sector_for_vector(0, 100, 4, 40) == 2
    assert sector_for_vector(0, -100, 0, 40) == -1


def test_clamp_vector():
    x, y = clamp_vector(300, 400, 100)
    assert math.isclose(math.hypot(x, y), 100)
    assert clamp_vector(3, 4, 100) == (3, 4)
