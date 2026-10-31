"""Fixtures shared by more than one test module."""
import pytest

from animation_fixtures import write_recipe


@pytest.fixture
def recipe(tmp_path):
    return write_recipe(tmp_path)
