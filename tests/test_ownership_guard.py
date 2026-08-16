import pytest

from src.tradelens.services.ownership import require_user_id


def test_accepts_a_positive_integer():
    assert require_user_id(7) == 7


@pytest.mark.parametrize("bad", [None, 0, -1, "3", 3.0, True, False, [], {}])
def test_refuses_everything_that_is_not_a_positive_int(bad):
    """`True` is the subtle one: in Python `isinstance(True, int)` is True and
    `True > 0`, so a bare int check would accept it and scope a query to user 1."""
    with pytest.raises(ValueError):
        require_user_id(bad)
