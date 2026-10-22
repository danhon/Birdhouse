"""Tests for the birds-only filter (taxonomy.csv, with a denylist fallback)."""

from pathlib import Path

import pytest

from birdhouse.app import is_bird, load_bird_names


@pytest.fixture
def taxonomy_path(tmp_path) -> Path:
    # Same header shape as BirdNET-Go's config/models/shared/taxonomy.csv
    # (trimmed: the real file has many more common_name_* columns).
    path = tmp_path / "taxonomy.csv"
    path.write_text(
        "idx,sci_name,com_name,species_code,class_name,common_name_de\n"
        "0,Corvus brachyrhynchos,American Crow,amecro,aves,Amerikanerkrähe\n"
        "1,Canis latrans,Coyote,coyote,mammalia,Kojote\n"
        "2,Lithobates clamitans,Green Frog,grefro,amphibia,Grünfrosch\n"
        '3,"Haemorhous mexicanus",House Finch,houfin,aves,"Hausgimpel, mexikanisch"\n'
    )
    return path


class TestLoadBirdNames:
    def test_keeps_only_aves(self, taxonomy_path):
        assert load_bird_names(taxonomy_path) == {"Corvus brachyrhynchos", "Haemorhous mexicanus"}

    def test_missing_file_returns_none(self, tmp_path):
        assert load_bird_names(tmp_path / "nope.csv") is None

    def test_none_path_returns_none(self):
        assert load_bird_names(None) is None


class TestIsBird:
    @pytest.fixture
    def birds(self, taxonomy_path):
        return load_bird_names(taxonomy_path)

    def test_normal_bird(self, birds):
        assert is_bird("Corvus brachyrhynchos", birds)

    @pytest.mark.parametrize("name", ["Engine", "Dog", "Power tools", "Human vocal"])
    def test_birdnet_sound_classes_rejected(self, birds, name):
        assert not is_bird(name, birds)

    @pytest.mark.parametrize("name", ["Canis latrans", "Lithobates clamitans"])
    def test_non_bird_animals_rejected(self, birds, name):
        assert not is_bird(name, birds)

    def test_fallback_without_taxonomy_rejects_sound_classes(self):
        for name in ["Engine", "Dog", "Power tools", "Human vocal"]:
            assert not is_bird(name, None)

    def test_fallback_without_taxonomy_keeps_birds(self):
        assert is_bird("Corvus brachyrhynchos", None)
