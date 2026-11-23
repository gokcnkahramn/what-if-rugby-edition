"""Single source of truth for every union's cross-cutting configuration -
dataset team_id/raw team-name, display nation, and (where relevant) a
Wikipedia squad/crest page title. Before this module existed, this same
information was scattered across up to 4 dicts in `pool_builder.py`
(`TIER1_TEAM_IDS`/`TIER2_TEAM_IDS`/`TIER2_WIKI_ONLY_TEAM_IDS`/
`WIKI_ONLY_NATIONS`) plus `wikipedia_squad.py`'s `WIKI_UNION_PAGES` and
`team_logos.py`'s `TEAM_LOGO_PAGES` - so adding or editing one union meant
touching up to 3 files. Those modules now just derive their own
dicts (same names, same shapes, same contents) from `UNION_REGISTRY` below.

`tier` is mostly a human-readable grouping label (Tier 1 vs Tier 2 vs the
Rugby Europe Championship's wiki-only unions vs Hong Kong/Zimbabwe), but
two values DO drive real behavior, preserved exactly from the dicts this
module replaces:
- `dataset_team_id is None` (every "wiki_only*" tier below) routes straight
  to `build_wikipedia_pool`, bypassing rugbydata entirely
  (`pool_builder.build_union_pool`).
- `"wiki_only_nation"` (Hong Kong/Zimbabwe) is DELIBERATELY excluded from
  `ALL_TEAM_IDS` (unlike `"wiki_only"`, the Rugby Europe Championship
  group), because `ALL_TEAM_IDS` membership is used elsewhere as an
  "is this a real/known union" validity check (e.g. `tournament/season.py`,
  `webapp.py`) - the two codes were simply never wired into that check
  originally, and this migration preserves that exactly rather than
  silently changing it.

Not covered here: the Barbarians/British & Irish Lions/Pacific Islanders
invitational sides. They have no `team_id`/Wikipedia-squad-page concept in
the same shape as a real union (see `rugby_sim/data/national_teams/`'s
`barbarians.py`/`lions.py`/`pacific_islanders.py` and their own bespoke
squad sources) and are added to `pool_builder.NATION_DISPLAY`/
`NON_RANKED_CODES` directly, not through this registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class UnionEntry:
    code: str
    nation: str  # display name
    tier: str  # "tier1" | "tier2" | "wiki_only" | "wiki_only_nation"
    dataset_team_id: Optional[str] = None
    dataset_team_name: Optional[str] = None  # raw rugbydata spelling, if it differs (e.g. "Usa")
    # Every union here has a real "<nation> national rugby union team"
    # Wikipedia page (used for crest scraping - `TEAM_LOGO_PAGES`), but only
    # SOME of them are also used as a squad-building fallback
    # (`WIKI_UNION_PAGES`/`build_union_pool_2026`) - a Tier 1 union like
    # England always has full rugbydata coverage, so it never needs that
    # fallback even though its Wikipedia page obviously still exists.
    wiki_page_title: Optional[str] = None  # the page title itself, if any
    needs_wiki_squad_fallback: bool = False  # True -> included in `WIKI_UNION_PAGES`
    has_logo_page: bool = True  # False for unions `TEAM_LOGO_PAGES` doesn't cover today


UNION_REGISTRY: List[UnionEntry] = [
    # -- Tier 1 (team names/ids resolved by scanning rugbydata's 2026 fixture
    # list). Every one has a real Wikipedia page (so a logo can be scraped),
    # but none of them (except Fiji) ever needs the Wikipedia SQUAD fallback
    # - rugbydata's own 2026 coverage is always complete for these.
    UnionEntry("ENG", "England", "tier1", "f60f757d", "England", "England national rugby union team"),
    UnionEntry("FRA", "France", "tier1", "67d88578", "France", "France national rugby union team"),
    UnionEntry("IRE", "Ireland", "tier1", "165b36e5", "Ireland", "Ireland national rugby union team"),
    UnionEntry("SCO", "Scotland", "tier1", "4409215c", "Scotland", "Scotland national rugby union team"),
    UnionEntry("WAL", "Wales", "tier1", "094dae60", "Wales", "Wales national rugby union team"),
    UnionEntry("ITA", "Italy", "tier1", "d0cffe5e", "Italy", "Italy national rugby union team"),
    UnionEntry("NZL", "New Zealand", "tier1", "d75e45cc", "New Zealand", "New Zealand national rugby union team"),
    UnionEntry("AUS", "Australia", "tier1", "b904fef9", "Australia", "Australia national rugby union team"),
    UnionEntry("RSA", "South Africa", "tier1", "9b93d911", "South Africa", "South Africa national rugby union team"),
    UnionEntry("ARG", "Argentina", "tier1", "11392c0c", "Argentina", "Argentina national rugby union team"),
    UnionEntry("JPN", "Japan", "tier1", "f97333f3", "Japan", "Japan national rugby union team"),
    # Fiji is Tier 1 but ALSO gets a Wikipedia squad top-up (rugbydata lacks
    # 2026 player-level data for Fiji specifically) - see
    # `pool_builder.build_union_pool_2026` - the one Tier 1 exception.
    UnionEntry("FIJ", "Fiji", "tier1", "3a1983b3", "Fiji", "Fiji national rugby union team",
               needs_wiki_squad_fallback=True),
    # -- Tier 2 (relevant for the 2027 Rugby World Cup pools). Rugby Europe
    # sides (GEO/ROU/ESP/POR) have 2026 rugbydata rows already; the
    # Pacific/Americas sides don't yet (most recent recorded internationals
    # are 2024-2025) - every one of these DOES use the Wikipedia squad
    # fallback for season="2026" specifically (`build_union_pool_2026`).
    UnionEntry("GEO", "Georgia", "tier2", "9b13901b", "Georgia", "Georgia national rugby union team",
               needs_wiki_squad_fallback=True),
    UnionEntry("ROU", "Romania", "tier2", "931e1c23", "Romania", "Romania national rugby union team",
               needs_wiki_squad_fallback=True),
    UnionEntry("ESP", "Spain", "tier2", "219a6262", "Spain", "Spain national rugby union team",
               needs_wiki_squad_fallback=True),
    UnionEntry("POR", "Portugal", "tier2", "5149996e", "Portugal", "Portugal national rugby union team",
               needs_wiki_squad_fallback=True),
    UnionEntry("SAM", "Samoa", "tier2", "23778ceb", "Samoa", "Samoa national rugby union team",
               needs_wiki_squad_fallback=True),
    UnionEntry("TGA", "Tonga", "tier2", "be110f80", "Tonga", "Tonga national rugby union team",
               needs_wiki_squad_fallback=True),
    # Dataset's own team-name spelling is "Usa" (confirmed - see `real_fixtures.py`'s
    # `_canonical_name` fixup for this exact case).
    UnionEntry("USA", "USA", "tier2", "5865faf2", "Usa", "United States national rugby union team",
               needs_wiki_squad_fallback=True),
    UnionEntry("CAN", "Canada", "tier2", "1039f7c4", "Canada", "Canada national rugby union team",
               needs_wiki_squad_fallback=True),
    UnionEntry("URU", "Uruguay", "tier2", "95ba991c", "Uruguay", "Uruguay national rugby union team",
               needs_wiki_squad_fallback=True),
    UnionEntry("CHI", "Chile", "tier2", "53ea6ee8", "Chile", "Chile national rugby union team",
               needs_wiki_squad_fallback=True),
    UnionEntry("NAM", "Namibia", "tier2", "03b35a84", "Namibia", "Namibia national rugby union team",
               needs_wiki_squad_fallback=True),
    # -- Rugby Europe Championship coverage (added to unblock that
    # competition for Georgia/Romania/Spain/Portugal - see
    # `real_fixtures.py`'s "rugby_europe_championship" entry): these six
    # have NO usable rugbydata player-level data at all (`fetch_team_matches`
    # has their match logs, but every match's `players` id list is empty -
    # confirmed live across 2022-2026), but each DOES have a standard
    # `==Current squad==`/`{{nat rs player|...}}` section on their "...
    # national rugby union team" Wikipedia page (Poland's/Switzerland's
    # squad listing is dated to the 2021-22 Rugby Europe Trophy season,
    # Germany's to a November 2024 friendly - still real, named, sourced
    # squads, not invented rosters). `dataset_team_id=None` routes straight
    # to `build_wikipedia_pool`, same mechanism Hong Kong/Zimbabwe
    # ("wiki_only_nation" below) use - but UNLIKE Hong Kong/Zimbabwe, these
    # six are deliberately folded into `ALL_TEAM_IDS` (see `tier` docstring
    # above) so every `ALL_TEAM_IDS`-walking consumer (season blocks, squad
    # lookups, fixture name canonicalization) picks them up automatically.
    # `TEAM_LOGO_PAGES` doesn't cover these 6 today (`has_logo_page=False`
    # preserved exactly - unverified whether these specific pages even
    # expose a `Badge=` infobox field; not this migration's job to add).
    UnionEntry("SUI", "Switzerland", "wiki_only", None, "Switzerland",
               "Switzerland national rugby union team", needs_wiki_squad_fallback=True, has_logo_page=False),
    UnionEntry("GER", "Germany", "wiki_only", None, "Germany",
               "Germany national rugby union team", needs_wiki_squad_fallback=True, has_logo_page=False),
    UnionEntry("POL", "Poland", "wiki_only", None, "Poland",
               "Poland national rugby union team", needs_wiki_squad_fallback=True, has_logo_page=False),
    # Netherlands/Belgium DO appear as team names in rugbydata's fixture
    # index (Russia doesn't, even at match level) but none of the three has
    # a resolvable per-player box score any more than Switzerland/Germany/
    # Poland do, so they get the identical wiki-only treatment.
    UnionEntry("NED", "Netherlands", "wiki_only", None, "Netherlands",
               "Netherlands national rugby union team", needs_wiki_squad_fallback=True, has_logo_page=False),
    UnionEntry("BEL", "Belgium", "wiki_only", None, "Belgium",
               "Belgium national rugby union team", needs_wiki_squad_fallback=True, has_logo_page=False),
    UnionEntry("RUS", "Russia", "wiki_only", None, "Russia",
               "Russia national rugby union team", needs_wiki_squad_fallback=True, has_logo_page=False),
    # -- Unions with no rugbydata team_id at all (not found in the dataset
    # under any name) but needed for the 2027 Rugby World Cup draw -
    # display name only, since there's no team-level box score to pull
    # from; Wikipedia-only (see `build_union_pool_2026`'s fallback).
    # Deliberately excluded from `ALL_TEAM_IDS` - see `tier` docstring above.
    UnionEntry("HKG", "Hong Kong", "wiki_only_nation",
               wiki_page_title="Hong Kong national rugby union team", needs_wiki_squad_fallback=True),
    UnionEntry("ZIM", "Zimbabwe", "wiki_only_nation",
               wiki_page_title="Zimbabwe national rugby union team", needs_wiki_squad_fallback=True),
]
