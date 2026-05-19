"""Unit tests for the matching engine — covers the 4 design-doc scenarios."""
import pytest

from services.matching import (
    normalize_tags, exact_match_score, similarity_score, rank,
    TAG_GROUPS,
)


def test_normalize_tags():
    assert normalize_tags(["Rust", " 系统编程 ", "", "  "]) == {"rust", "系统编程"}


def test_exact_match_scenario_1_perfect():
    """Asker tags {rust, 系统编程} vs Agent {rust, 系统编程, 编译器} → perfect Ochiai."""
    q = {"rust", "系统编程"}
    a = {"rust", "系统编程", "编译器"}
    s = exact_match_score(q, a)
    # |∩|=2, max(2,3)=3 → 0.667
    assert 0.66 <= s <= 0.67


def test_exact_match_scenario_2_partial():
    q = {"rust"}
    a = {"rust", "系统编程", "编译器"}
    s = exact_match_score(q, a)
    # |∩|=1, max(1,3)=3 → 0.333
    assert 0.33 <= s <= 0.34


def test_exact_match_scenario_3_no_overlap():
    q = {"rust"}
    a = {"法律"}
    assert exact_match_score(q, a) == 0.0


def test_similarity_scenario_4_fallback():
    """Asker 'WASM' vs Agent has 'rust' — both fall into 系统底层 group."""
    q = normalize_tags(["WASM"])
    a = normalize_tags(["rust", "性能优化"])
    s = similarity_score(q, a)
    assert s > 0  # both in 系统底层 group


def test_tag_groups_cover_design_doc():
    """The 9 predefined tag groups must each contain at least 1 tag."""
    assert len(TAG_GROUPS) == 9
    for name, members in TAG_GROUPS.items():
        assert len(members) > 0, f"group {name} is empty"


def test_rank_balances_repute_and_match():
    """rank = 0.6 * (repute/5) + 0.4 * match_score — sanity check the weights."""
    # Perfect repute, no match
    assert rank(5.0, 0.0) == pytest.approx(0.6)
    # No repute, perfect match
    assert rank(0.0, 1.0) == pytest.approx(0.4)
    # Both perfect
    assert rank(5.0, 1.0) == pytest.approx(1.0)
