"""Tests for the category mappings."""

from marktplaats_2dehands_mcp import categories


def test_l1_categories_present():
    assert categories.L1_CATEGORIES["fietsen en brommers"] == 445
    assert categories.L1_CATEGORIES["computers en software"] == 322
    assert len(categories.L1_CATEGORIES) >= 30


def test_l2_categories_have_id_and_parent():
    for name, info in categories.L2_CATEGORIES.items():
        assert "id" in info, f"{name} missing 'id'"
        assert "parent" in info, f"{name} missing 'parent'"
        assert isinstance(info["id"], int)
        assert isinstance(info["parent"], int)


def test_l2_parents_exist_in_l1():
    """Every L2 'parent' must reference an actual L1 id."""
    l1_ids = set(categories.L1_CATEGORIES.values())
    for name, info in categories.L2_CATEGORIES.items():
        assert info["parent"] in l1_ids, f"{name} has unknown parent {info['parent']}"


def test_known_subcategories_present():
    assert categories.L2_CATEGORIES["laptops"] == {"id": 339, "parent": 322}
    assert categories.L2_CATEGORIES["elektrische fietsen"] == {"id": 1901, "parent": 445}
