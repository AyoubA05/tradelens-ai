import pytest

from src.tradelens.services import corrections


def test_scope_sets_and_restores(two_users):
    a, _ = two_users
    with corrections.corrections_scope(a):
        assert corrections.count_corrections() == 0
    with pytest.raises(LookupError):
        corrections.count_corrections()


def test_scope_resets_even_when_the_body_raises(two_users):
    """A handler that raises must not leave its owner visible to the next
    request on the same worker thread."""
    a, _ = two_users
    with pytest.raises(RuntimeError):
        with corrections.corrections_scope(a):
            raise RuntimeError("handler exploded")
    with pytest.raises(LookupError):
        corrections.count_corrections()


def test_nested_scopes_restore_the_outer_owner(two_users):
    a, b = two_users
    with corrections.corrections_scope(a):
        with corrections.corrections_scope(b):
            assert corrections._resolve_user(corrections._UNSET) == b
        assert corrections._resolve_user(corrections._UNSET) == a


def test_unset_context_refuses_rather_than_using_the_legacy_tenant():
    with pytest.raises(LookupError):
        corrections._resolve_user(corrections._UNSET)


def test_an_explicit_owner_does_not_need_a_scope(two_users):
    a, _ = two_users
    assert corrections.count_corrections(user_id=a) == 0


def test_scope_refuses_an_invalid_owner():
    with pytest.raises(ValueError):
        with corrections.corrections_scope(None):
            pass
