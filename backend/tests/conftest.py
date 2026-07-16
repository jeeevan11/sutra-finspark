import pytest

from sutra.generator.world import World, build_world


@pytest.fixture(scope="session")
def world() -> World:
    return build_world(42)
