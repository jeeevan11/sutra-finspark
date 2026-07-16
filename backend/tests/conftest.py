import pytest

from sutra.generator.world import World, build_world


@pytest.fixture(scope="session")
def world() -> World:
    return build_world(42)


@pytest.fixture(scope="session")
def ml(world):
    """Session-scoped: trained once on the benign day (~10s)."""
    from sutra.ml.model import train_or_load
    scorer = train_or_load(world, 42, None)
    assert scorer.ready, "ML must train for the test suite"
    return scorer
