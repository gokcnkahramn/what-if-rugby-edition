"""Curated REAL-data registry of rugby test-match stadiums used by the
"Classic Matches" catalog (`classic_matches.py` and its two Tier-B
modules). Same convention as `legends.py`/`rankings.py`'s `WR_RANKING_SEED`
- a small, hand-curated, committed-to-the-repo dict, not fetched live.

Every entry is a REAL, verifiable stadium (name, city, country and
approximate real-world coordinates, looked up rather than recalled from
memory where there was any doubt). Coordinates are accurate to ~4 decimal
places, which is more than enough precision for this project's purposes.

A few notes on historical naming, since several entries span 1995-2026 and
some stadiums were renamed or rebuilt during that window:

- Cardiff: the stadium now called "Principality Stadium" opened in 1999 as
  the "Millennium Stadium" and was renamed in 2016 under a new sponsorship
  deal. Same physical venue/coordinates either way - this registry keeps
  BOTH keys (`millennium_stadium` for matches before the 2016 rename,
  `principality_stadium` for matches from 2016 on) so each `ClassicMatch`
  can cite the name that was actually in use on its real date.
- Dublin: Ireland played at the old "Lansdowne Road" ground through 2007,
  moved to Croke Park (GAA's own stadium) for 2007-2009 while Lansdowne
  Road was demolished and rebuilt, then returned to the same site in 2010
  as the new "Aviva Stadium". Three keys (`lansdowne_road`, `croke_park`,
  `aviva_stadium`) cover that sequence; `lansdowne_road`/`aviva_stadium`
  share the same real-world coordinates (same site).
- Sydney: "Stadium Australia" (opened 1999) was known as "Telstra Stadium"
  (2002-2007), then "ANZ Stadium" (2008-2022), then "Accor Stadium"
  (2022-). One `stadium_australia` key covers all of these - same
  physical venue throughout, only the sponsor name changed.
- Twickenham: "Twickenham Stadium" was renamed "Allianz Stadium" under a
  2024 sponsorship deal. This registry keeps one `twickenham` key/name
  throughout (the matches referencing it even after 2024 still call it
  "Twickenham" in their own display names/blurbs), noted here for honesty
  rather than added as a second key.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Venue:
    name: str          # the real stadium name, e.g. "Twickenham Stadium"
    city: str
    country: str
    latitude: float
    longitude: float


VENUES: dict[str, Venue] = {
    # ---- England --------------------------------------------------------
    "twickenham": Venue("Twickenham Stadium", "London", "England", 51.4548, -0.3431),
    "wembley_stadium": Venue("Wembley Stadium", "London", "England", 51.5560, -0.2795),
    "brighton_community_stadium": Venue(
        "Brighton Community Stadium (Amex Stadium)", "Brighton", "England", 50.8616, -0.0836
    ),

    # ---- Wales (see module docstring re: 2016 rename) --------------------
    "millennium_stadium": Venue("Millennium Stadium", "Cardiff", "Wales", 51.4782, -3.1826),
    "principality_stadium": Venue("Principality Stadium", "Cardiff", "Wales", 51.4782, -3.1826),

    # ---- Scotland ---------------------------------------------------------
    "murrayfield": Venue("Murrayfield Stadium", "Edinburgh", "Scotland", 55.9422, -3.2399),

    # ---- Ireland (see module docstring re: Lansdowne Road -> Croke Park
    #      -> Aviva Stadium sequence) --------------------------------------
    "lansdowne_road": Venue("Lansdowne Road", "Dublin", "Ireland", 53.3351, -6.2286),
    "croke_park": Venue("Croke Park", "Dublin", "Ireland", 53.3607, -6.2512),
    "aviva_stadium": Venue("Aviva Stadium", "Dublin", "Ireland", 53.3351, -6.2286),

    # ---- France -----------------------------------------------------------
    "stade_de_france": Venue("Stade de France", "Saint-Denis", "France", 48.9244, 2.3601),
    "stade_de_la_beaujoire": Venue("Stade de la Beaujoire", "Nantes", "France", 47.2559, -1.5255),
    "stade_geoffroy_guichard": Venue("Stade Geoffroy-Guichard", "Saint-Étienne", "France", 45.4608, 4.3903),

    # ---- Italy --------------------------------------------------------------
    "stadio_olimpico": Venue("Stadio Olimpico", "Rome", "Italy", 41.9341, 12.4547),

    # ---- South Africa -------------------------------------------------------
    "ellis_park": Venue("Ellis Park Stadium", "Johannesburg", "South Africa", -26.1836, 28.0601),
    "fnb_stadium": Venue("FNB Stadium (Soccer City)", "Johannesburg", "South Africa", -26.2348, 27.9825),
    "kings_park": Venue("Kings Park Stadium", "Durban", "South Africa", -29.8273, 31.0233),
    "loftus_versfeld": Venue("Loftus Versfeld", "Pretoria", "South Africa", -25.7538, 28.2327),
    "newlands": Venue("Newlands Stadium", "Cape Town", "South Africa", -33.9752, 18.4712),
    "mbombela_stadium": Venue("Mbombela Stadium", "Mbombela", "South Africa", -25.4725, 30.9852),

    # ---- New Zealand ---------------------------------------------------------
    "eden_park": Venue("Eden Park", "Auckland", "New Zealand", -36.8749, 174.7444),
    "wellington_regional_stadium": Venue(
        "Wellington Regional Stadium", "Wellington", "New Zealand", -41.2730, 174.7859
    ),
    "carisbrook": Venue("Carisbrook", "Dunedin", "New Zealand", -45.8894, 170.5041),
    "waikato_stadium": Venue("Waikato Stadium", "Hamilton", "New Zealand", -37.7664, 175.2870),
    "orangetheory_stadium": Venue(
        "Orangetheory Stadium (Christchurch Stadium)", "Christchurch", "New Zealand", -43.5095, 172.7129
    ),

    # ---- Australia -------------------------------------------------------------
    "stadium_australia": Venue("Stadium Australia", "Sydney", "Australia", -33.8470, 151.0634),
    "bankwest_stadium": Venue("Bankwest Stadium (CommBank Stadium)", "Parramatta, Sydney", "Australia", -33.8169, 151.0626),
    "suncorp_stadium": Venue("Suncorp Stadium", "Brisbane", "Australia", -27.4650, 153.0095),
    "melbourne_cricket_ground": Venue("Melbourne Cricket Ground", "Melbourne", "Australia", -37.8199, 144.9834),
    "queensland_country_bank_stadium": Venue(
        "Queensland Country Bank Stadium", "Townsville", "Australia", -19.2847, 146.8142
    ),

    # ---- Japan (2019 Rugby World Cup) ---------------------------------------------
    "yokohama_stadium": Venue("International Stadium Yokohama", "Yokohama", "Japan", 35.5089, 139.6032),
    "shizuoka_stadium_ecopa": Venue("Shizuoka Stadium Ecopa", "Fukuroi", "Japan", 34.7897, 137.9268),

    # ---- Argentina ---------------------------------------------------------------
    "velez_sarsfield": Venue("Estadio José Amalfitani (Vélez Sarsfield)", "Buenos Aires", "Argentina", -34.6329, -58.5000),
    "estadio_malvinas_argentinas": Venue(
        "Estadio Malvinas Argentinas", "Mendoza", "Argentina", -32.8894, -68.8272
    ),
    "estadio_padre_martearena": Venue(
        "Estadio Padre Ernesto Martearena", "Salta", "Argentina", -24.7792, -65.4038
    ),
    "estadio_ciudad_de_la_plata": Venue(
        "Estadio Ciudad de La Plata", "La Plata", "Argentina", -34.9496, -57.9712
    ),
}
