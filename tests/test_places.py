"""Places: a typed city or zone name resolves to the zone and label the Desktop half gives too
(`tests/fixtures/places.json` is read by both halves)."""
import json

import pytest

from esb_fakes import ROOT, sub

FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "places.json").read_text(encoding="utf-8"))["resolve"]


@pytest.fixture
def places():
    return sub("engines.places")


@pytest.mark.parametrize("query,zone,label", FIXTURE, ids=[repr(row[0]) for row in FIXTURE])
def test_resolve_answers_like_the_fixture(places, query, zone, label):
    assert places.resolve(query) == (None if zone is None else {"zone": zone, "label": label})


def test_the_fixture_covers_both_outcomes():
    assert len(FIXTURE) >= 20
    assert any(row[1] is None for row in FIXTURE) and any(row[1] for row in FIXTURE)


def test_spelling_does_not_matter_but_only_whole_names_match(places):
    for typed in ("ZÜRICH", "zurich", "  Zurich  "):
        assert places.resolve(typed) == {"zone": "Europe/Zurich", "label": "Zurich"}
    assert places.resolve("Port-au-Prince") == places.resolve("port au prince")
    assert places.resolve("Zur") is None and places.resolve("Zurich Airport") is None


def test_a_city_in_the_list_wins_over_a_zone_of_the_same_name(places):
    # Kolkata is both a listed city and the zone's own name; Mumbai shares its zone
    assert places.resolve("Kolkata")["zone"] == places.resolve("Mumbai")["zone"] == "Asia/Kolkata"


def test_a_zone_name_is_labelled_by_its_city(places):
    assert places.resolve("America/Sao_Paulo") == {"zone": "America/Sao_Paulo", "label": "São Paulo"}
    assert places.resolve("Asia/Ho_Chi_Minh")["label"] == "Ho Chi Minh City"
    assert places.resolve("Pacific/Port_Moresby")["label"] == "Port Moresby"
    assert places.city_name("UTC") == "UTC"


@pytest.mark.parametrize("typed", [None, "   ", "/", "Europe/", "../../etc/hosts", "Europe/Atlantis", 7])
def test_what_is_not_a_place_is_none_and_never_raises(places, typed):
    assert places.resolve(typed) is None


def test_every_listed_place_is_a_zone_this_python_knows(places):
    data = json.loads((ROOT / "data" / "places.json").read_text(encoding="utf-8"))
    for city, zone, _country in data["cities"]:
        assert places.zone_loads(zone), (city, zone)
        assert places.resolve(city) is not None, city
