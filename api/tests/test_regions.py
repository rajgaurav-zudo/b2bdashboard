"""The team-to-region mapping every dashboard filters on."""
import sys

sys.path.insert(0, "/srv/api")

from app import regions  # noqa: E402


def test_every_team_sits_in_exactly_one_region():
    assert regions.region_of("West Africa B2B AMT2") == "Africa"
    assert regions.region_of("DevTesting AMT") == "NR"
    assert regions.region_of("China UK B2C") == "China"
    assert regions.region_of("Europe") == regions.OTHER
    assert regions.region_of("Unassigned") == regions.OTHER
    assert len(regions.REGIONS) == 35


def test_narrow():
    known = ["Thai B2B SRMs", "China B2B SRMs", "Europe"]
    assert regions.narrow([], [], known) is None
    assert regions.narrow(["Europe"], [], known) == ["Europe"]
    assert regions.narrow([], ["China", "Other"], known) == ["China B2B SRMs", "Europe"]
    assert regions.narrow(["Thai B2B SRMs"], ["China"], known) == []


def test_options_total_each_region_and_keep_the_order():
    teams, regs = regions.options([{"team": "Europe", "n": 2}, {"team": "Thai B2B SRMs", "n": 3},
                                   {"team": "Chennai B2B", "n": 1}])
    assert [r["region"] for r in regs] == ["India & South Asia", "Thailand", "Other"]
    assert teams[0] == {"team": "Europe", "n": 2, "region": "Other"}


def test_split_uses_pipes():
    assert regions.split(" a, b |c||") == ["a, b", "c"]
