import pytest

from determine.config import ModelRole, Settings


def test_independence_violation_detected():
    s = Settings(answerer=ModelRole(family="anthropic", name="a"),
                 verifier=ModelRole(family="anthropic", name="b"))
    with pytest.raises(RuntimeError, match="independence violation"):
        s.assert_independence()


def test_different_families_pass():
    s = Settings(answerer=ModelRole(family="anthropic", name="a"),
                 verifier=ModelRole(family="openai", name="b"))
    s.assert_independence()


def test_config_hash_stable():
    assert Settings().config_hash() == Settings().config_hash()
