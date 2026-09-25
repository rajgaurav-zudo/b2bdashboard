"""Which region each team belongs to.

Every dashboard files its work under a team -- the SRM team on the introducers
master, the managing team on the log. The business groups those teams into
regions, and the dashboards filter on both: Region picks a set of teams, Team
narrows it further. The mapping lives here, once, so the three dashboards cannot
disagree about where a team sits.

A team the mapping has never heard of -- a new team, an old one, a blank --
lands in Other rather than vanishing: a filter that silently drops rows is worse
than one with an untidy bucket.
"""

from __future__ import annotations

OTHER = "Other"

_BY_REGION: dict[str, tuple[str, ...]] = {
    "Africa": (
        "Africa B2B AMT", "Africa B2B SRMs", "East Africa B2B AMT", "East Africa B2B SRMs",
        "West Africa B2B AMT 1", "West Africa B2B AMT2",
        "West Africa B2B SRMs 1", "West Africa B2B SRMs 2",
    ),
    "Bangladesh": ("Bangladesh B2B SRMs",),
    "India & South Asia": (
        "Bhutan B2B SRM", "Chennai B2B", "Chennai B2C", "India B2B SRMs", "Myanmar B2B SRM",
        "Nepal B2B AMT", "Nepal B2B SRMs", "North India B2B SRMs", "Philippines B2B SRM",
        "South India B2B SRMs", "South India Region", "SouthAsia B2B SRMs",
        "SriLanka B2B SRMs", "Vietnam B2B SRMs", "West India B2B SRMs",
    ),
    "China": ("China B2B SRMs", "China UK B2C"),
    # North Africa is run by the MENA team, so it sits here, not under Africa
    "MENA & CIS": ("CIS B2B SRMs", "MENA B2B SRMs", "North Africa B2B SRMs"),
    "NR": ("DevTesting AMT",),
    "RoW & Pakistan": ("LATAM B2B SRMs", "Pak B2B SRMs", "RoW B2B SRMs", "UK B2B SRMs"),
    "Thailand": ("Thai B2B SRMs",),
}

REGIONS: dict[str, str] = {team: region for region, teams in _BY_REGION.items() for team in teams}

# the order the menu lists them in; Other always last
ORDER: list[str] = [*_BY_REGION, OTHER]


def region_of(team: str) -> str:
    return REGIONS.get(team, OTHER)


def split(raw: str | None) -> list[str]:
    """A `|`-joined URL value as a list. Pipes, because team names hold commas."""
    return [part.strip() for part in (raw or "").split("|") if part.strip()]


def narrow(teams: list[str], regions: list[str], known: list[str]) -> list[str] | None:
    """The teams the page should keep, or None for every team.

    `known` is every team the data holds. With only teams picked, those are the
    answer; with regions picked, it is the picked teams (or all known ones) that
    sit in those regions. The result can be empty -- a team picked in one region
    and a different region picked -- and an empty list must match nothing, not
    everything, which is why it is not collapsed to None.
    """
    if not regions:
        return list(teams) or None
    wanted = set(regions)
    return [t for t in (teams or known) if region_of(t) in wanted]


def options(team_counts: list[dict], key: str = "team") -> tuple[list[dict], list[dict]]:
    """The team menu tagged with regions, and the region menu with totals.

    Only regions that hold some team in the data are offered, so a region can
    never be picked into an empty page.
    """
    teams = [{**row, "region": region_of(row[key])} for row in team_counts]
    totals: dict[str, int] = {}
    for row in teams:
        totals[row["region"]] = totals.get(row["region"], 0) + int(row["n"] or 0)
    regions = [{"region": r, "n": totals[r]} for r in ORDER if r in totals]
    return teams, regions
