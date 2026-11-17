from src.services import sizes


def test_size_guide_lists_every_size_in_order():
    """
    Given the size guide
    When listing its sizes
    Then they are XS, S, M, L, each with a summary, a when and an example
    """
    assert list(sizes.SIZE_GUIDE) == ["XS", "S", "M", "L"]
    assert all(g.short and g.when and g.example for g in sizes.SIZE_GUIDE.values())
