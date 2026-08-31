from __future__ import annotations

from ingestion.models import CompetitionType, PlayerDataMode

SEASON_LABELS = (
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
    "2025-26",
)


def _sort_order(label: str) -> int:
    # Domestic split-year seasons use the full ending year (``2026-27`` ->
    # 2027), while calendar competitions such as Allsvenskan use a plain year.
    parts = label.split("-")
    if len(parts) == 1:
        return int(parts[0])
    start = int(parts[0])
    ending = int(parts[-1])
    if len(parts[0]) == 4 and len(parts[-1]) == 2:
        ending += start - (start % 100)
        if ending <= start:
            ending += 100
    return ending


def _season_row(
    label: str,
    *,
    sofascore_unique_tournament_id: int | None,
    sofascore_season_id: int | None,
    understat_league: str | None = None,
    understat_season_year: str | None = None,
    whoscored_league: str | None = None,
    whoscored_season: str | None = None,
    whoscored_expected_match_count: int | None = None,
    is_active: bool = True,
    refresh_enabled: bool = False,
    legacy_label_alias: str | None = None,
    expected_team_count: int | None = None,
    min_merged_team_count: int | None = None,
    min_team_stats_coverage_count: int | None = None,
) -> dict:
    row = {
        "label": label,
        "sort_order": _sort_order(label),
        "sofascore_unique_tournament_id": sofascore_unique_tournament_id,
        "sofascore_season_id": sofascore_season_id,
        "understat_league": understat_league,
        "understat_season_year": understat_season_year,
        "is_active": is_active,
        "refresh_enabled": refresh_enabled,
    }
    if legacy_label_alias is not None:
        row["legacy_label_alias"] = legacy_label_alias
    if whoscored_league is not None:
        row.update(
            has_whoscored=True,
            whoscored_league=whoscored_league,
            whoscored_season=whoscored_season or label,
            whoscored_expected_match_count=whoscored_expected_match_count,
        )
    for key, value in (
        ("expected_team_count", expected_team_count),
        ("min_merged_team_count", min_merged_team_count),
        ("min_team_stats_coverage_count", min_team_stats_coverage_count),
    ):
        if value is not None:
            row[key] = value
    return row


COMPETITION_SEED_MANIFEST = [
    {
        "code": "ENG1",
        "aliases": ["EPL"],
        "name": "Premier League",
        "country": "England",
        "player_data_mode": PlayerDataMode.FULL_MERGE,
        "has_understat": True,
        "has_sofascore": True,
        "expected_team_count": 20,
        "min_merged_team_count": 18,
        "min_team_stats_coverage_count": 18,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=17, sofascore_season_id=37036, understat_league="EPL", understat_season_year="2021"),
            _season_row("2022-23", sofascore_unique_tournament_id=17, sofascore_season_id=41886, understat_league="EPL", understat_season_year="2022"),
            _season_row("2023-24", sofascore_unique_tournament_id=17, sofascore_season_id=52186, understat_league="EPL", understat_season_year="2023"),
            _season_row("2024-25", sofascore_unique_tournament_id=17, sofascore_season_id=61627, understat_league="EPL", understat_season_year="2024"),
            _season_row("2025-26", sofascore_unique_tournament_id=17, sofascore_season_id=76986, understat_league="EPL", understat_season_year="2025", refresh_enabled=True),
        ],
    },
    {
        "code": "ITA1",
        "name": "Serie A",
        "country": "Italy",
        "player_data_mode": PlayerDataMode.FULL_MERGE,
        "has_understat": True,
        "has_sofascore": True,
        "expected_team_count": 20,
        "min_merged_team_count": 18,
        "min_team_stats_coverage_count": 18,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=23, sofascore_season_id=37475, understat_league="Serie_A", understat_season_year="2021"),
            _season_row("2022-23", sofascore_unique_tournament_id=23, sofascore_season_id=42415, understat_league="Serie_A", understat_season_year="2022"),
            _season_row("2023-24", sofascore_unique_tournament_id=23, sofascore_season_id=52760, understat_league="Serie_A", understat_season_year="2023"),
            _season_row("2024-25", sofascore_unique_tournament_id=23, sofascore_season_id=63515, understat_league="Serie_A", understat_season_year="2024"),
            _season_row("2025-26", sofascore_unique_tournament_id=23, sofascore_season_id=76457, understat_league="Serie_A", understat_season_year="2025", refresh_enabled=True),
        ],
    },
    {
        "code": "SPA1",
        "name": "La Liga",
        "country": "Spain",
        "player_data_mode": PlayerDataMode.FULL_MERGE,
        "has_understat": True,
        "has_sofascore": True,
        "expected_team_count": 20,
        "min_merged_team_count": 18,
        "min_team_stats_coverage_count": 18,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=8, sofascore_season_id=37223, understat_league="La_liga", understat_season_year="2021"),
            _season_row("2022-23", sofascore_unique_tournament_id=8, sofascore_season_id=42409, understat_league="La_liga", understat_season_year="2022"),
            _season_row("2023-24", sofascore_unique_tournament_id=8, sofascore_season_id=52376, understat_league="La_liga", understat_season_year="2023"),
            _season_row("2024-25", sofascore_unique_tournament_id=8, sofascore_season_id=61643, understat_league="La_liga", understat_season_year="2024"),
            _season_row("2025-26", sofascore_unique_tournament_id=8, sofascore_season_id=77559, understat_league="La_liga", understat_season_year="2025", refresh_enabled=True),
        ],
    },
    {
        "code": "GER1",
        "name": "Bundesliga",
        "country": "Germany",
        "player_data_mode": PlayerDataMode.FULL_MERGE,
        "has_understat": True,
        "has_sofascore": True,
        "expected_team_count": 18,
        "min_merged_team_count": 16,
        "min_team_stats_coverage_count": 16,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=35, sofascore_season_id=37166, understat_league="Bundesliga", understat_season_year="2021"),
            _season_row("2022-23", sofascore_unique_tournament_id=35, sofascore_season_id=42268, understat_league="Bundesliga", understat_season_year="2022"),
            _season_row("2023-24", sofascore_unique_tournament_id=35, sofascore_season_id=52608, understat_league="Bundesliga", understat_season_year="2023"),
            _season_row("2024-25", sofascore_unique_tournament_id=35, sofascore_season_id=63516, understat_league="Bundesliga", understat_season_year="2024"),
            _season_row(
                "2025-26",
                sofascore_unique_tournament_id=35,
                sofascore_season_id=77333,
                understat_league="Bundesliga",
                understat_season_year="2025",
                whoscored_league="GER-Bundesliga",
                whoscored_season="2025-26",
                whoscored_expected_match_count=306,
                refresh_enabled=True,
            ),
        ],
    },
    {
        "code": "GER2",
        "name": "2. Bundesliga",
        "country": "Germany",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 18,
        "min_merged_team_count": 16,
        "min_team_stats_coverage_count": 0,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=44, sofascore_season_id=37168),
            _season_row("2022-23", sofascore_unique_tournament_id=44, sofascore_season_id=42269),
            _season_row("2023-24", sofascore_unique_tournament_id=44, sofascore_season_id=52607),
            _season_row("2024-25", sofascore_unique_tournament_id=44, sofascore_season_id=63514),
            _season_row("2025-26", sofascore_unique_tournament_id=44, sofascore_season_id=77354, refresh_enabled=True),
        ],
    },
    {
        "code": "GER3",
        "name": "3. Liga",
        "country": "Germany",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 20,
        "min_merged_team_count": 18,
        "min_team_stats_coverage_count": 0,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=491, sofascore_season_id=37235),
            _season_row("2022-23", sofascore_unique_tournament_id=491, sofascore_season_id=42444),
            _season_row("2023-24", sofascore_unique_tournament_id=491, sofascore_season_id=52815),
            _season_row("2024-25", sofascore_unique_tournament_id=491, sofascore_season_id=63786),
            _season_row("2025-26", sofascore_unique_tournament_id=491, sofascore_season_id=77744, refresh_enabled=True),
        ],
    },
    {
        "code": "FRA1",
        "name": "Ligue 1",
        "country": "France",
        "player_data_mode": PlayerDataMode.FULL_MERGE,
        "has_understat": True,
        "has_sofascore": True,
        "expected_team_count": 18,
        "min_merged_team_count": 16,
        "min_team_stats_coverage_count": 16,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=34, sofascore_season_id=37167, understat_league="Ligue_1", understat_season_year="2021"),
            _season_row("2022-23", sofascore_unique_tournament_id=34, sofascore_season_id=42273, understat_league="Ligue_1", understat_season_year="2022"),
            _season_row("2023-24", sofascore_unique_tournament_id=34, sofascore_season_id=52571, understat_league="Ligue_1", understat_season_year="2023"),
            _season_row("2024-25", sofascore_unique_tournament_id=34, sofascore_season_id=61736, understat_league="Ligue_1", understat_season_year="2024"),
            _season_row("2025-26", sofascore_unique_tournament_id=34, sofascore_season_id=77356, understat_league="Ligue_1", understat_season_year="2025", refresh_enabled=True),
        ],
    },
    {
        "code": "POR1",
        "name": "Liga Portugal",
        "country": "Portugal",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 18,
        "min_merged_team_count": 16,
        "min_team_stats_coverage_count": 16,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=238, sofascore_season_id=37358),
            _season_row("2022-23", sofascore_unique_tournament_id=238, sofascore_season_id=42655),
            _season_row("2023-24", sofascore_unique_tournament_id=238, sofascore_season_id=52769),
            _season_row("2024-25", sofascore_unique_tournament_id=238, sofascore_season_id=63670),
            _season_row("2025-26", sofascore_unique_tournament_id=238, sofascore_season_id=77806, refresh_enabled=True),
        ],
    },
    {
        "code": "NED1",
        "name": "Eredivisie",
        "country": "Netherlands",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 18,
        "min_merged_team_count": 16,
        "min_team_stats_coverage_count": 16,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=37, sofascore_season_id=36890),
            _season_row("2022-23", sofascore_unique_tournament_id=37, sofascore_season_id=42256),
            _season_row("2023-24", sofascore_unique_tournament_id=37, sofascore_season_id=52554),
            _season_row("2024-25", sofascore_unique_tournament_id=37, sofascore_season_id=61666),
            _season_row("2025-26", sofascore_unique_tournament_id=37, sofascore_season_id=77012, refresh_enabled=True),
        ],
    },
    {
        "code": "BEL1",
        "name": "Jupiler Pro League",
        "country": "Belgium",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 16,
        "min_merged_team_count": 14,
        "min_team_stats_coverage_count": 14,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=38, sofascore_season_id=36894),
            _season_row("2022-23", sofascore_unique_tournament_id=38, sofascore_season_id=42404),
            _season_row("2023-24", sofascore_unique_tournament_id=38, sofascore_season_id=52383),
            _season_row("2024-25", sofascore_unique_tournament_id=38, sofascore_season_id=61459),
            _season_row("2025-26", sofascore_unique_tournament_id=38, sofascore_season_id=77040, refresh_enabled=True),
        ],
    },
    {
        "code": "SCO1",
        "name": "Scottish Premiership",
        "country": "Scotland",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 12,
        "min_merged_team_count": 10,
        "min_team_stats_coverage_count": 10,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=36, sofascore_season_id=37029),
            _season_row("2022-23", sofascore_unique_tournament_id=36, sofascore_season_id=41957),
            _season_row("2023-24", sofascore_unique_tournament_id=36, sofascore_season_id=52588),
            _season_row("2024-25", sofascore_unique_tournament_id=36, sofascore_season_id=62408),
            _season_row("2025-26", sofascore_unique_tournament_id=36, sofascore_season_id=77128, refresh_enabled=True),
        ],
    },
    {
        "code": "ENG2",
        "name": "Championship",
        "country": "England",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 24,
        "min_merged_team_count": 22,
        "min_team_stats_coverage_count": 22,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=18, sofascore_season_id=37154),
            _season_row("2022-23", sofascore_unique_tournament_id=18, sofascore_season_id=42401),
            _season_row("2023-24", sofascore_unique_tournament_id=18, sofascore_season_id=52367),
            _season_row("2024-25", sofascore_unique_tournament_id=18, sofascore_season_id=61961),
            _season_row("2025-26", sofascore_unique_tournament_id=18, sofascore_season_id=77347, refresh_enabled=True),
        ],
    },
    {
        "code": "POL1",
        "name": "Ekstraklasa",
        "country": "Poland",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 18,
        "min_merged_team_count": 16,
        "min_team_stats_coverage_count": 0,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=202, sofascore_season_id=37062),
            _season_row("2022-23", sofascore_unique_tournament_id=202, sofascore_season_id=42004),
            _season_row("2023-24", sofascore_unique_tournament_id=202, sofascore_season_id=52176),
            _season_row("2024-25", sofascore_unique_tournament_id=202, sofascore_season_id=61236),
            _season_row("2025-26", sofascore_unique_tournament_id=202, sofascore_season_id=76477, refresh_enabled=True),
        ],
    },
    {
        "code": "CZE1",
        "name": "Czech First League",
        "country": "Czechia",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 18,
        "min_merged_team_count": 16,
        "min_team_stats_coverage_count": 0,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=172, sofascore_season_id=37051),
            _season_row("2022-23", sofascore_unique_tournament_id=172, sofascore_season_id=42398),
            _season_row("2023-24", sofascore_unique_tournament_id=172, sofascore_season_id=52364),
            _season_row("2024-25", sofascore_unique_tournament_id=172, sofascore_season_id=61716),
            _season_row("2025-26", sofascore_unique_tournament_id=172, sofascore_season_id=77019, refresh_enabled=True),
        ],
    },
    {
        "code": "DEN1",
        "name": "Superliga",
        "country": "Denmark",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 12,
        "min_merged_team_count": 10,
        "min_team_stats_coverage_count": 0,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=39, sofascore_season_id=36834),
            _season_row("2022-23", sofascore_unique_tournament_id=39, sofascore_season_id=41914),
            _season_row("2023-24", sofascore_unique_tournament_id=39, sofascore_season_id=52172),
            _season_row("2024-25", sofascore_unique_tournament_id=39, sofascore_season_id=61326),
            _season_row("2025-26", sofascore_unique_tournament_id=39, sofascore_season_id=76491, refresh_enabled=True),
        ],
    },
    {
        "code": "GRE1",
        "name": "Stoiximan Super League",
        "country": "Greece",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 14,
        "min_merged_team_count": 12,
        "min_team_stats_coverage_count": 0,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=185, sofascore_season_id=37707),
            _season_row("2022-23", sofascore_unique_tournament_id=185, sofascore_season_id=44513),
            _season_row("2023-24", sofascore_unique_tournament_id=185, sofascore_season_id=53223),
            _season_row("2024-25", sofascore_unique_tournament_id=185, sofascore_season_id=64052),
            _season_row("2025-26", sofascore_unique_tournament_id=185, sofascore_season_id=78175, refresh_enabled=True),
        ],
    },
    {
        "code": "CYP1",
        "name": "Cyprus League",
        "country": "Cyprus",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 12,
        "min_merged_team_count": 10,
        "min_team_stats_coverage_count": 0,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=171, sofascore_season_id=37481),
            _season_row("2022-23", sofascore_unique_tournament_id=171, sofascore_season_id=42725),
            _season_row("2023-24", sofascore_unique_tournament_id=171, sofascore_season_id=53242),
            _season_row("2024-25", sofascore_unique_tournament_id=171, sofascore_season_id=63498),
            _season_row("2025-26", sofascore_unique_tournament_id=171, sofascore_season_id=78640, refresh_enabled=True),
        ],
    },
    {
        "code": "TUR1",
        "name": "Super Lig",
        "country": "Turkey",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 18,
        "min_merged_team_count": 16,
        "min_team_stats_coverage_count": 0,
        "seasons": [
            _season_row("2021-22", sofascore_unique_tournament_id=52, sofascore_season_id=37466),
            _season_row("2022-23", sofascore_unique_tournament_id=52, sofascore_season_id=42632),
            _season_row("2023-24", sofascore_unique_tournament_id=52, sofascore_season_id=53190),
            _season_row("2024-25", sofascore_unique_tournament_id=52, sofascore_season_id=63814),
            _season_row("2025-26", sofascore_unique_tournament_id=52, sofascore_season_id=77805, refresh_enabled=True),
        ],
    },
    {
        "code": "EST1",
        "name": "Premium Liiga",
        "country": "Estonia",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 10,
        "min_merged_team_count": 8,
        "min_team_stats_coverage_count": 0,
        "seasons": [
            _season_row("2021", sofascore_unique_tournament_id=178, sofascore_season_id=35341, legacy_label_alias="2021-22"),
            _season_row("2022", sofascore_unique_tournament_id=178, sofascore_season_id=40593, legacy_label_alias="2022-23"),
            _season_row("2023", sofascore_unique_tournament_id=178, sofascore_season_id=48281, legacy_label_alias="2023-24"),
            _season_row("2024", sofascore_unique_tournament_id=178, sofascore_season_id=57905, legacy_label_alias="2024-25"),
            _season_row("2025", sofascore_unique_tournament_id=178, sofascore_season_id=71438, refresh_enabled=True, legacy_label_alias="2025-26"),
            _season_row("2026", sofascore_unique_tournament_id=178, sofascore_season_id=89137, expected_team_count=10, min_merged_team_count=8, min_team_stats_coverage_count=0, legacy_label_alias="2026-27"),
        ],
    },
    {
        "code": "NOR1",
        "name": "Eliteserien",
        "country": "Norway",
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 16,
        "min_merged_team_count": 14,
        "min_team_stats_coverage_count": 0,
        "seasons": [
            _season_row("2021", sofascore_unique_tournament_id=20, sofascore_season_id=35403, legacy_label_alias="2021-22"),
            _season_row("2022", sofascore_unique_tournament_id=20, sofascore_season_id=40405, legacy_label_alias="2022-23"),
            _season_row("2023", sofascore_unique_tournament_id=20, sofascore_season_id=47806, legacy_label_alias="2023-24"),
            _season_row("2024", sofascore_unique_tournament_id=20, sofascore_season_id=57322, legacy_label_alias="2024-25"),
            _season_row("2025", sofascore_unique_tournament_id=20, sofascore_season_id=70174, refresh_enabled=True, legacy_label_alias="2025-26"),
            _season_row("2026", sofascore_unique_tournament_id=20, sofascore_season_id=87809, expected_team_count=16, min_merged_team_count=14, min_team_stats_coverage_count=0, legacy_label_alias="2026-27"),
        ],
    },
]


# The current-season rows are kept together so their rollover policy is easy to
# audit without touching the historical rows above.  In particular, the
# 2026-27 rows are intentionally inactive only if a future operator changes
# this explicit flag; they are otherwise active, unpublished, and not selected
# for refresh until the safe cutover command is applied.
EXISTING_2026_27 = {
    "ENG1": (17, 96668, "EPL", "2026", 20, 18, 18),
    "ITA1": (23, 95836, "Serie_A", "2026", 20, 18, 18),
    "SPA1": (8, 97268, "La_liga", "2026", 20, 18, 18),
    "GER1": (35, 97464, "Bundesliga", "2026", 18, 16, 16),
    "GER2": (44, 97406, None, None, 18, 16, 0),
    "GER3": (491, 98012, None, None, 20, 18, 0),
    "FRA1": (34, 96127, "Ligue_1", "2026", 18, 16, 16),
    "POR1": (238, 97436, None, None, 18, 16, 16),
    "NED1": (37, 96143, None, None, 18, 16, 16),
    "BEL1": (38, 96616, None, None, 18, 16, 14),
    "SCO1": (36, 96658, None, None, 12, 10, 10),
    "ENG2": (18, 97037, None, None, 24, 22, 22),
    "POL1": (202, 96144, None, None, 18, 16, 0),
    "CZE1": (172, 96966, None, None, 16, 14, 0),
    "DEN1": (39, 95785, None, None, 12, 10, 0),
    "GRE1": (185, 98659, None, None, 14, 12, 0),
    "CYP1": (171, 99321, None, None, 14, 12, 0),
    "TUR1": (52, 98080, None, None, 18, 16, 0),
}

for competition_config in COMPETITION_SEED_MANIFEST:
    target = EXISTING_2026_27.get(competition_config["code"])
    if target is None:
        continue
    (
        tournament_id,
        season_id,
        understat_league,
        understat_year,
        expected_team_count,
        min_merged_team_count,
        min_team_stats_coverage_count,
    ) = target
    competition_config["seasons"].append(
        _season_row(
            "2026-27",
            sofascore_unique_tournament_id=tournament_id,
            sofascore_season_id=season_id,
            understat_league=understat_league,
            understat_season_year=understat_year,
            expected_team_count=expected_team_count,
            min_merged_team_count=min_merged_team_count,
            min_team_stats_coverage_count=min_team_stats_coverage_count,
        )
    )


def _cup_config(
    code: str,
    name: str,
    tournament_id: int,
    season_rows: list[tuple[str, int, int]],
) -> dict:
    return {
        "code": code,
        "name": name,
        "country": "Europe",
        "competition_type": CompetitionType.CONTINENTAL_CUP,
        "include_in_domestic_aggregates": False,
        "minimum_eligible_minutes": 270,
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": 36,
        "min_merged_team_count": 34,
        "min_team_stats_coverage_count": 0,
        "seasons": [
            _season_row(
                label,
                sofascore_unique_tournament_id=tournament_id,
                sofascore_season_id=season_id,
                expected_team_count=expected_count,
                min_merged_team_count=max(expected_count - 2, 1),
                min_team_stats_coverage_count=0,
            )
            for label, season_id, expected_count in season_rows
        ],
    }


COMPETITION_SEED_MANIFEST.extend(
    [
        _cup_config(
            "UCL",
            "UEFA Champions League",
            7,
            [
                ("2022-23", 41897, 32),
                ("2023-24", 52162, 32),
                ("2024-25", 61644, 36),
                ("2025-26", 76953, 36),
                ("2026-27", 96518, 36),
            ],
        ),
        _cup_config(
            "UEL",
            "UEFA Europa League",
            679,
            [
                ("2022-23", 44509, 40),
                ("2023-24", 53654, 40),
                ("2024-25", 61645, 36),
                ("2025-26", 76984, 36),
                ("2026-27", 96522, 36),
            ],
        ),
        _cup_config(
            "UECL",
            "UEFA Conference League",
            17015,
            [
                ("2022-23", 42224, 40),
                ("2023-24", 52327, 40),
                ("2024-25", 61648, 36),
                ("2025-26", 76960, 36),
                ("2026-27", 96529, 36),
            ],
        ),
    ]
)


def _domestic_config(
    code: str,
    name: str,
    country: str,
    tournament_id: int,
    season_rows: list[tuple[str, int, int]],
) -> dict:
    expected_team_count = max(expected for _, _, expected in season_rows)
    return {
        "code": code,
        "name": name,
        "country": country,
        "competition_type": CompetitionType.DOMESTIC_LEAGUE,
        "include_in_domestic_aggregates": True,
        "minimum_eligible_minutes": 450,
        "player_data_mode": PlayerDataMode.SOFASCORE_ONLY,
        "has_understat": False,
        "has_sofascore": True,
        "expected_team_count": expected_team_count,
        "min_merged_team_count": max(expected_team_count - 2, 1),
        "min_team_stats_coverage_count": 0,
        "seasons": [
            _season_row(
                label,
                sofascore_unique_tournament_id=tournament_id,
                sofascore_season_id=season_id,
                expected_team_count=expected_count,
                min_merged_team_count=max(expected_count - 2, 1),
                min_team_stats_coverage_count=0,
            )
            for label, season_id, expected_count in season_rows
        ],
    }


COMPETITION_SEED_MANIFEST.extend(
    [
        _domestic_config(
            "BEL2",
            "Challenger Pro League",
            "Belgium",
            9,
            [
                ("2023-24", 52384, 16),
                ("2024-25", 61412, 16),
                ("2025-26", 77849, 17),
                ("2026-27", 96912, 15),
            ],
        ),
        _domestic_config(
            "FRA2",
            "Ligue 2",
            "France",
            182,
            [
                ("2022-23", 42272, 20),
                ("2023-24", 52572, 21),
                ("2024-25", 61737, 20),
                ("2025-26", 77357, 20),
                ("2026-27", 96109, 18),
            ],
        ),
        _domestic_config(
            "FRA3",
            "Ligue 3",
            "France",
            183,
            [
                ("2024-25", 64124, 18),
                ("2025-26", 78599, 18),
                ("2026-27", 97457, 18),
            ],
        ),
        _domestic_config(
            "SCO2",
            "Scottish Championship",
            "Scotland",
            206,
            [
                ("2022-23", 41958, 13),
                ("2023-24", 52606, 13),
                ("2024-25", 62411, 13),
                ("2025-26", 77037, 13),
                ("2026-27", 96614, 10),
            ],
        ),
        _domestic_config(
            "SWE1",
            "Allsvenskan",
            "Sweden",
            40,
            [
                ("2022", 40406, 17),
                ("2023", 47730, 17),
                ("2024", 57284, 17),
                ("2025", 69956, 17),
                ("2026", 87925, 16),
            ],
        ),
    ]
)
