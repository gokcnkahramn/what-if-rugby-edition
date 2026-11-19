# Attribute mapping: real stats -> `Attributes` (1-100)

This is the full reference for `attribute_mapping.py`: for every field in
`rugby_sim.models.attributes.Attributes`, which real rugbydata box-score
stat(s) feed it, the actual transformation applied, and how much real
statistical support backs it. It exists because the project's own audit
(Phase 4.1) asked for an inspectable map of player data -> individual
attributes -> position-specific calculations -> overall rating -> match
engine impact, and because "trust the comment in the code" isn't good
enough when the comment and the code can drift apart (see the Discrepancies
section below - one did).

This document describes the **real-data path** (`map_stats_to_attributes`,
used when `data_source == "rugbydata"`). Wikipedia-sourced and purely
manual/archetype players go through different code and are out of scope
here, except where noted.

## How to read "support level"

- **Well-supported**: 2+ independent real stats feed the attribute, each
  capturing a genuinely different facet of the skill (not just two columns
  that are arithmetically close to the same thing).
- **Single-proxy**: exactly one real stat stands in for a broader skill.
  The formula may have several *steps* (per-cap normalization, clamping,
  percentile scaling) but all of those steps still only see one underlying
  signal - that doesn't make it well-supported, it just makes the proxy
  more carefully packaged.
- **Archetype-only / hardcoded**: no real stat feeds it at all for this
  data path; it's a fixed constant regardless of the player.

All `scaled(...)` values go through `_scale` (fixed breakpoints mapped onto
`[out_lo, out_hi]`, default 30-95) unless `peer_proxies` has >=
`MIN_PEER_SAMPLE` (5) same-position players supplied, in which case
`_percentile_scale` is used instead (rank among peers mapped onto the same
output range). Either way, every attribute computed from a proxy sits in
roughly a 30-95 band before rounding and clamping to `Attributes.clamp()`'s
[1, 100]; a handful of attributes bypass `_scale` entirely (flat constants,
or bespoke if/else branches for goal-kicking) - those are called out
individually.

---

## Physical

| Attribute | Real stat(s) used | Formula | Support level |
|---|---|---|---|
| `pace` | `line_breaks`, `clean_breaks` (per cap) | `pace_proxy = line_breaks/caps + clean_breaks/caps`, then `_scale(proxy, 0.0, 1.5)` | Single-proxy. Two columns are summed, but both measure the same underlying event (broke the line), not two different skills - there is no running-speed or acceleration stat in the dataset at all. |
| `acceleration` | same as `pace` | `acceleration = pace` (literally the same rounded value, no separate computation) | Single-proxy (and not even independently derived - it's a duplicate of `pace`). Now an explicitly commented intentional proxy-share in the source, not a silent one. |
| `strength` | `metres_carried`, `carries` (per cap) | `strength_proxy = (metres_carried/caps) / max(carries/caps, 1.0)` (metres per carry), then `_scale(proxy, 2.0, 7.0)` | Single-proxy. Metres-per-carry is a reasonable physicality signal but conflates strength with footwork/pace/opposition quality; there's no actual contact/dominance stat independent of what's already used for `tackle_technique`. |
| `fitness` | none | Hardcoded `60` for every player, every position, every union. | Archetype-only / hardcoded. No stamina, minutes-per-90, or late-game-dropoff stat exists in the dataset. |
| `agility` | `pace` and `footwork` proxies (derived attributes, not raw stats) | `agility = round((pace + footwork) / 2)` | Single-proxy at the root (both pace and footwork ultimately trace back to line-break/defenders-beaten events - "beat someone and got through"), just averaged over two already-derived attributes rather than two independent raw stats. |

## Contact / defense

| Attribute | Real stat(s) used | Formula | Support level |
|---|---|---|---|
| `tackling` | `tackles_made`, `tackles_missed` | `tackle_success = tackles_made / (tackles_made + tackles_missed)` (default 0.85 if no attempts), then `_scale(success, 0.70, 0.95)` | Well-supported. Both inputs are direct, specific defensive stats and together form a real completion rate, not a proxy stand-in. |
| `tackle_technique` | `dominant_tackles` (per cap) and `turnovers_won` (per cap) | `dominant_score = scaled(dominant_tackles, 0.0, 3.0)`; `turnover_score = scaled(turnover_threat, 0.0, 1.2)`; `tackle_technique = round((dominant_score + turnover_score) / 2)` | Well-supported. Two genuinely distinct real signals (winning the collision vs. winning the ball back afterward), each capturing a different sub-skill a player can have without the other, per the code's own comment. |
| `aerial` | `lineout_jumping`, `strength`, `pace` (derived attributes, blended) | `aerial = round((lineout_jumping + strength + pace) / 3)` | Single-proxy-equivalent, honestly flagged in the source code comment (same convention as `scrummaging` below): the dataset has no restart/high-ball contest stat at all, so a blend of the closest available real-data signals - lineout-jumping athleticism, physical strength in the air, and pace to cover ground for a restart - stands in. Not a well-supported attribute (all three inputs ultimately trace back to proxies for other skills), but no longer a silent exact duplicate of `lineout_jumping`. |

## Set piece

| Attribute | Real stat(s) used | Formula | Support level |
|---|---|---|---|
| `scrummaging` | `rucks_won` (per cap) | `scaled(rucks_won, 0.0, 8.0)` | Single-proxy, explicitly and honestly flagged in the source code's own comment: the dataset has no scrum-contest stat at all, so general breakdown involvement (`rucks_won`) stands in. The code deliberately keeps this proxy out of every other attribute's formula and `position.py` leans on `strength` more than `scrummaging` for front row/locks specifically because of this weakness. |
| `lineout_jumping` | `lineouts_won` (per cap) | `scaled(lineouts_won, 0.0, 3.0)` | Single-proxy. One real stat (raw lineout wins, not a success rate against `total_lineouts`, which is used instead for throwing - see discrepancy note below). |
| `lineout_throwing` | `lineouts_won` / `total_lineouts` (raw hit rate, not per-cap) | `lineout_throw_rate = lineouts_won/total_lineouts` (default `0.75` if `total_lineouts` is 0, mirroring the `tackle_success` fallback), then `scaled(lineout_throw_rate, 0.5, 0.95)` | Single-proxy, but now consistent with `lineout_jumping`'s use of a success signal rather than attempt volume. Still a single real stat, and in practice the dataset attributes `lineouts_won` to the jumper rather than the hooker who threw it, so a hooker's own rate can read as 0 even on a well-thrown ball the jumper dropped - a known data-attribution limitation, not a formula bug. |

## Skill

| Attribute | Real stat(s) used | Formula | Support level |
|---|---|---|---|
| `handling` | `passes`, `turnovers_lost` (both per cap) | `handling_proxy = passes/caps - (turnovers_lost/caps) * 3`, then `scaled(proxy, 2.0, 25.0)` | Well-supported. Volume of passing plus a penalty for turnovers lost are two distinct signals (doing the skill a lot, and not messing it up), combined with a deliberate weighting rather than just picked from one column. |
| `passing` | same as `handling` | `passing = handling` (literal duplicate, no separate computation) | Well-supported inputs, but note it is not independently derived - `passing` and `handling` are always identical for every real-data player. Now an explicitly commented intentional proxy-share in the source, not a silent one. |
| `offload` | `offloads` (per cap) | `scaled(offloads, 0.0, 2.0)` | Single-proxy. One column, directly named for the skill it measures, so at least it's a precise single proxy rather than a stretch. |
| `footwork` | `defenders_beaten` (per cap) | `scaled(defenders_beaten, 0.0, 2.5)` | Single-proxy, but again a precise, directly-named one. |
| `kicking_game` | `kicks_from_hand` (per cap) | `scaled(kicks_from_hand, 0.0, 6.0)` | Single-proxy, and a volume-only one: raw kick count, not territory gained, hang time, or kicks-that-led-to-pressure. A high-volume poor kicker and a low-volume excellent one would be hard to distinguish. |
| `goal_kicking` | `kick_percent_success`, `penalty_goals`, `conversion_goals` | Bespoke branch, not `_scale`: `is_kicker = (penalty_goals + conversion_goals) > 0`; if `is_kicker` and `kick_percent_success` is not NaN, `_scale(kick_percent_success, 0.55, 0.95, out_lo=55, out_hi=96)`; elif `is_kicker` but success % missing, flat `70.0`; else (never attempted a kick) flat `35.0` | Well-supported for players who actually kick (a real success-rate stat, specifically gated on having attempted kicks) - but degrades to archetype-only guesses (flat 70 or flat 35) whenever `kick_percent_success` is missing or the player has never attempted a kick, which is the large majority of outfield players. |
| `place_kicking_range` | same as `goal_kicking` | `place_kicking_range = goal_kicking` (literal duplicate) | Same support level as `goal_kicking` above - not independently computed. Now an explicitly commented intentional proxy-share in the source, not a silent one. |

## Mental

| Attribute | Real stat(s) used | Formula | Support level |
|---|---|---|---|
| `game_intelligence` | `tackling` and `handling` (derived attributes) | `round((tackling + handling) / 2)` | Built from two well-supported derived attributes, but "game intelligence" as a concept (reading the game, decision-making) is not actually measured by either input - this is a plausible-sounding average of two unrelated skills, not a genuine intelligence proxy. Classified single-proxy-equivalent: there is no real stat that measures rugby IQ in this dataset, so the two numbers borrowed here are a stand-in, not independent evidence of intelligence. |
| `positioning` | same as `game_intelligence` | `positioning = game_intelligence` (literal duplicate) | Same caveat as above; also not independently computed. Now an explicitly commented intentional proxy-share in the source, not a silent one. |
| `leadership` | none | Hardcoded `50` for every player. | Archetype-only / hardcoded. No captaincy, experience, or influence stat exists in the dataset. |
| `discipline` | `penalties_conceded`, `yellow_cards`, `red_cards` (all per cap) | `discipline_raw = 2.0 - penalties_conceded/caps - (yellow_cards/caps + red_cards/caps * 2) * 20`, then `discipline = max(5.0, scaled(discipline_raw, 0.0, 2.0))` | Well-supported. Three distinct, specific disciplinary stats (penalties, yellows, reds, with reds weighted more heavily) feed one formula - a real multi-signal composite, not a single proxy dressed up. |
| `composure` | `discipline` and `goal_kicking` (derived attributes) | `round((discipline + goal_kicking) / 2)` | Same pattern as `game_intelligence`/`positioning`: a plausible-sounding average of two existing derived attributes standing in for a mental trait ("composure under pressure") that has no dedicated real stat. Treated as single-proxy-equivalent for the same reason. |

## Versatility

| Attribute | Real stat(s) used | Formula | Support level |
|---|---|---|---|
| `versatility` | none | Hardcoded `40` for every real-data player. | Archetype-only / hardcoded. No multi-position-appearance stat is consumed here, even though the dataset likely records which position(s) a player appeared at; nothing in `map_stats_to_attributes` reads it. Also the one attribute explicitly exempted from `scale_to_union_strength`'s compression toward 50, on the stated reasoning that versatility is a personal trait, not a reflection of union strength - a reasonable design choice, just worth noting it's exempted from a step that itself only moves already-hardcoded-or-derived numbers. |

---

## Union-strength pass (applies to every attribute above except `versatility`)

After the per-attribute computation, `scale_to_union_strength` pulls every
non-exempt attribute toward 50 in proportion to `(1 - UNION_STRENGTH[union])`:
`value' = 50 + (value - 50) * strength`. This runs on every player regardless
of data source (real stats, Wikipedia, or archetype fallback) and is **not**
derived from any per-player stat - it's a flat, hand-set table of
competitiveness multipliers per union (`UNION_STRENGTH`, e.g. `ENG/NZL/RSA
= 1.0`, `ROU = 0.4`, `HKG = 0.12`). This is an explicit, intentional
calibration layer on top of the per-attribute mapping, not a hidden one -
but it means even a "well-supported" attribute like `tackling` for a lower-
tier-union player is ultimately shrunk toward 50 by a number with no
statistical backing of its own, just an editorial judgment call documented
in the module's own comment block.

---

## Summary counts (real-data path, 23 attributes total)

- **Well-supported** (2+ independent real signals): `tackling`,
  `tackle_technique`, `handling` (and its duplicate `passing`),
  `discipline`, `goal_kicking` (and its duplicate `place_kicking_range`) -
  **conditionally**, only for players who have actually attempted kicks.
  That's 5 distinct computations (8 attributes counting duplicates).
- **Single-proxy** (one real stat, however it's packaged): `pace` (and
  `acceleration`), `strength`, `agility`, `scrummaging`,
  `lineout_jumping`, `lineout_throwing`, `offload`, `footwork`,
  `kicking_game`. That's 9 distinct computations (10 attributes counting
  the `acceleration` duplicate). `aerial` has moved to the composite
  category below (it blends three already-derived proxies rather than
  reading one raw stat directly).
- **Single-proxy-equivalent composites of derived attributes, no dedicated
  real stat of their own**: `game_intelligence` (and duplicate
  `positioning`), `composure`, `aerial`.
- **Archetype-only / hardcoded**: `fitness` (60), `leadership` (50),
  `versatility` (40), and `goal_kicking` degrades to this (flat 70 or 35)
  for the majority of players who have never attempted a kick.

Roughly a third of the 23 attributes are backed by genuinely independent
multi-signal real data; another third lean on exactly one real column
(sometimes a precise, well-named one like `offloads`, sometimes a stretch
like `rucks_won` for scrummaging or `total_lineouts` for throwing); and the
rest are either flat constants or unlabeled duplicates of other derived
values.

---

## Discrepancies found while writing this doc (status: fixed in a follow-up
pass, approved by the project owner - see each item)

1. **FIXED: `lineout_throwing` was named for accuracy but measured volume.**
   `_compute_proxies` now computes a raw hit rate,
   `lineout_throw_rate = lineouts_won / total_lineouts` (default `0.75`
   when `total_lineouts` is 0, mirroring the `tackle_success` fallback
   convention), and `map_stats_to_attributes` scales `lineout_throwing`
   from that rate (`scaled(lineout_throw_rate, 0.5, 0.95)`) instead of raw
   attempt volume. This changes real players' computed `lineout_throwing`
   values. Known limitation carried over from the underlying data: the
   dataset credits `lineouts_won` to the jumper, not the throwing hooker,
   so a hooker with real throw volume but 0 recorded `lineouts_won` now
   reads as a low (not flat-volume-inflated) rate - more honest than the
   old volume proxy, but still not a direct "throw accuracy" stat.

2. **FIXED: `aerial` is no longer a silent copy of `lineout_jumping`/flat
   50.** It's now a blended proxy, `aerial = round((lineout_jumping +
   strength + pace) / 3)`, with a source comment explaining the blend and
   explicitly flagging it as a weak proxy (same honesty convention as
   `scrummaging`) since the dataset has no restart/high-ball stat. This
   changes real players' computed `aerial` values and decouples them from
   `lineout_jumping`.

3. **FIXED: `passing`, `place_kicking_range`, `positioning`, and
   `acceleration` are now documented duplicates.** Each duplication site in
   `map_stats_to_attributes` has an explicit one-line comment stating it's
   an intentional proxy-share (no distinct real signal exists to tell the
   pair apart in this dataset). Their *values* are unchanged - this item
   was comment-only, no formula change.

No other attribute's formula was touched in this pass - see the module's
own comment headers at each changed site for the exact reasoning.
