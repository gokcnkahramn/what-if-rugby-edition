"""Unit test for `season_match_pages.parse_season_matches` against a small,
hand-built fake season-page wikitext (same static-fixture convention as
this project's other Wikipedia parser tests) - the live-data coverage
(every real Six Nations 2000-2008 and Rugby Championship/Tri Nations
1996-2025 year) is exercised by `test_historical_six_nations.py`/
`test_historical_rugby_championship.py` instead."""

from rugby_sim.data.sources.season_match_pages import parse_season_matches

FAKE_SEASON_PAGE = """
==Table==
{| class="wikitable"
|-
|align=left|{{ru|ENG}}
|2||2||0||0||50||20||+30||1||'''9'''
|}

==Results==

===Round 1===
{{Rugbybox
|date = 1 February 2003
|home = {{Ru-rt|ENG}}
|score = 25–17
|away = {{Ru|FRA}}
|stadium = [[Twickenham Stadium|Twickenham]]
}}
{| style="width:100%"
|-
|style="vertical-align:top;width:50%"|
{| cellspacing="0" cellpadding="0"
|-
|FB ||'''15'''||[[Josh Lewsey]]
|-
|RW ||'''14'''||[[Jason Robinson]]
|-
|colspan="3"|'''Replacements:'''
|-
|HK ||'''16'''||[[Dorian West]]
|-
|colspan="3"|'''Coach:'''
|-
|colspan="3"|{{flagdeco|ENG}} [[Clive Woodward]]
|}
|style="vertical-align:top;width:50%"|
{| cellspacing="0" cellpadding="0"
|-
|FB ||'''15'''||[[Gerald Merceron|G. Merceron]]
|-
|RW ||'''14'''||[[Aurelien Rougerie]]
|}
"""


def test_parse_season_matches_extracts_a_real_match_with_two_lineups():
    matches = parse_season_matches(FAKE_SEASON_PAGE)
    assert len(matches) == 1
    m = matches[0]
    assert m.home_code == "ENG" and m.away_code == "FRA"
    assert m.home_score == 25 and m.away_score == 17
    assert {e.name for e in m.home_lineup} == {"Josh Lewsey", "Jason Robinson", "Dorian West"}
    # The real article title (full name) is kept over a display alias -
    # `[[Gerald Merceron|G. Merceron]]` resolves to "Gerald Merceron".
    assert {e.name for e in m.away_lineup} == {"Gerald Merceron", "Aurelien Rougerie"}
    starters = [e for e in m.home_lineup if e.is_starter]
    bench = [e for e in m.home_lineup if not e.is_starter]
    assert {e.name for e in starters} == {"Josh Lewsey", "Jason Robinson"}
    assert {e.name for e in bench} == {"Dorian West"}
    # "Replacements:"/"Coach:" marker rows never leak in as fake players.
    assert all(e.name not in ("Replacements", "Coach", "Clive Woodward") for e in m.home_lineup)


def test_parse_season_matches_returns_empty_list_for_no_matches():
    assert parse_season_matches("No rugbybox here at all.") == []
