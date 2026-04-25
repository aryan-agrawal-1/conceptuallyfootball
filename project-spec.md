# Premier League Analytics Platform — Project Overview

---

## What We're Building

A Premier League analytics platform with three core features:

1. **Stat Matrix** — browse, filter, and compare all players
2. **Player Profile** — deep dive into an individual player
3. **Galaxy** — visual similarity map to discover players by style

---

## 1. Stat Matrix (Home Page)

The main exploration tool. A large, sortable, filterable table of all Premier League players.

### Columns (grouped)

**Basic Info:** Name, Team, Position (FWD / MID / DEF), Minutes / 90s

**Attacking:** Goals, npxG, npxG/90, xA/90, xGChain/90, xGBuildup/90, xG/Shot, Goals−xG, and more

**Defensive:** Tackles/90, Interceptions/90, Clearances/90, Blocks/90, Duels Won %, and more

**Passing / Possession:** Key Passes/90, Pass Accuracy %, Crosses/90, Long Balls/90, and more

**Custom Metrics (computed):** Attack Score, Creation Score, Finishing Score, Ball Winning Score, Involvement Score, Efficiency — all normalized and percentile-coloured

### Filters

- Minimum minutes played
- Team
- Position
- Sort by any column

### Interactions

- Toggle Per 90 / Raw Totals
- Percentile heatmap colouring on cells
- Click any player row → opens their Profile page

---

## 2. Player Profile Page

### Header

- Player name
- Basic info: Club, Nation, Age, Position

### Key Stats Cards

Five headline cards displayed prominently: Goals, Assists, xG, xA, Minutes

### Stat Bars (main panel)

A full breakdown of every stat we hold, displayed as horizontal percentile bars — inspired by the Draftballr-style layout in the reference image. Grouped into sections: **Creative**, **Attacking**, **Defending**.

Each bar shows:

- The raw or per-90 value
- A coloured bar scaled to the percentile (red → amber → green)
- The percentile number on the right (e.g. 95, 43, 10)

**Percentiles are calculated against same-position players only** (FWDs vs FWDs etc.)

Toggle between **Per 90** and **Raw Totals** switches all values and recalculates accordingly.

### Pizza / Radar Chart

An interactive radar (pizza) chart the user can customise:

- User picks any stats from a dropdown to add as axes (up to ~8–10)
- Chart updates live to show the player's percentile on each chosen axis
- **Session only** — selections are not saved between visits
- Useful for quick comparisons or building role-specific profiles

### Similar Players

- Top 5 most similar players (sourced from the Galaxy similarity engine)
- Shows similarity score + key stat side-by-side comparison

### Match Log

A match-by-match table showing xG, xA, and Goals for every appearance this season.

---

## 3. Galaxy Page

A visual similarity map — the platform's standout differentiator.

### Scatter Plot

- Each dot = one player
- Position on the plot = similarity (not geography) — computed via UMAP dimensionality reduction
- Colour = archetype cluster (e.g. deep-lying creator, pressing forward, ball-winner)
- Size = minutes played or involvement score

### Sidebar Filters

- Position group
- Team
- Minimum minutes

### Interactions

- Hover → quick stat summary tooltip
- Click → opens full Player Profile
- Highlight nearest neighbours of a selected player

### How Similarity Is Computed

Each player is represented as a feature vector of key stats (xG/90, xA/90, xGChain/90, xGBuildup/90, xG/Shot, Goals−xG, Tackles/90, Interceptions/90, Duels Won %, Key Passes/90, Pass Accuracy %). These are z-score normalised, then:

- **Cosine distance** → similarity scores
- **UMAP** → 2D projection for the scatter plot
- **KMeans** → archetype clusters

---

## Database Design

### Core Tables

`**players`** — id, name, team, position, nationality, age, minutes

`**player_stats_understat**` — General + Attacking stats from Understat (xG, npxG, xA, xGChain, xGBuildup, shot-level data, per season)

`**player_stats_sofascore**` — Defence, Passing, and Goalkeeping stats from Sofascore (tackles, interceptions, clearances, blocks, duels, key passes, pass accuracy, crosses, long balls, per season)

`**player_stats_derived**` — Precomputed per-90 metrics, custom scores (Attack Score, Creation Score, etc.), and percentile rankings — stored so nothing is recomputed on request

`**player_embeddings**` — player_id, feature vector, cluster_id (archetype)

`**player_similarity**` — player_id, similar_player_id, similarity_score (top N pairs precomputed)

`**matches**` — match_id, teams, date

`**player_match_stats**` — player_id, match_id, xG, xA, goals (for match log)

---

## Tech Stack

**Backend:** Django + Django REST Framework, PostgreSQL, Celery (data jobs), Redis (cache + queue)

**Frontend:** React (Vite), Tailwind CSS, ShadCN components, Recharts (charts), D3 / react-force-graph (galaxy)

**Data Processing:** Python with pandas, numpy, scikit-learn (KMeans, cosine similarity), UMAP

---

## Data Providers & Ingestion

### Understat (via `soccerdata` Python package)

Provides general and attacking stats — xG, xA, xGChain, xGBuildup, shot-level data. Fetched via scheduled Celery jobs.

### Sofascore (custom ingestion)

Provides defensive, passing, and goalkeeping stats. Not an official public API — must be handled carefully:

- **Backend-only** — never called from the frontend
- **Batch jobs once per day** — data stored in DB, served from there
- **Rate limiting** — delays between requests, no rapid loops
- **Browser-mimicking headers** — User-Agent etc. to avoid blocking
- **Abstraction layer** — a `SofaScoreClient` class wraps all calls so a single fix covers any API change
- **Fallback** — if Sofascore is unavailable, app serves last stored data without breaking
- **Endpoints** - Of the form: [https://www.sofascore.com/api/v1/unique-tournament/17/season/76986/statistics?limit=20&order=-rating&offset=20&accumulation=total&group=summary](https://www.sofascore.com/api/v1/unique-tournament/17/season/76986/statistics?limit=20&order=-rating&offset=20&accumulation=total&group=summary)(max limit 100)
- **Output** - Formatted in json as follows:

```json
{
"results": [
{
"tackles": 96,
"interceptions": 24,
"clearances": 45,
"errorLeadToGoal": 0,
"outfielderBlocks": 10,
"rating": 7.01,
"player": {
"name": "João Palhinha",
"slug": "joao-palhinha",
"userCount": 16719,
"gender": "M",
"id": 364612,
"fieldTranslations": {
"nameTranslation": {
"ar": "جواو بالينيا",
"bn": "জোয়াও পালহিনহা",
"hi": "जोआओ पालहिन्हा"
},
"shortNameTranslation": {
"ar": "ج. بالينيا",
"bn": "জে. পলহিনহা",
"hi": "जे. पालहिन्हा"
}
}
},
"team": {
"name": "Tottenham Hotspur",
"slug": "tottenham-hotspur",
"sport": {
"name": "Football",
"slug": "football",
"id": 1
},
"userCount": 0,
"national": false,
"type": 0,
"id": 33,
"teamColors": {
"primary": "#374df5",
"secondary": "#374df5",
"text": "#ffffff"
},
"fieldTranslations": {
"nameTranslation": {
"ar": "توتنهام هوتسبير",
"hi": "टोटेनहैम हॉटस्पर ऍफ़सी",
"ru": "Тоттенхэм Хотспур"
},
"shortNameTranslation": {
"ar": "توتنهام",
"bn": "টটেনহ্যাম",
"hi": "टॉटनहैम"
}
}
}
},
{
"tackles": 93,
"interceptions": 50,
"clearances": 75,
"errorLeadToGoal": 0,
"outfielderBlocks": 8,
"rating": 7.27,
"player": {
"name": "James Garner",
"slug": "james-garner",
"userCount": 3498,
"gender": "M",
"id": 927361,
"fieldTranslations": {
"nameTranslation": {
"ar": "جيمس غارنر",
"bn": "জেমস গার্নার",
"hi": "जेम्स गार्नर"
},
"shortNameTranslation": {
"ar": "ج. غارنر",
"bn": "জে. গার্নার",
"hi": "जे. गार्नर"
}
}
},
"team": {
"name": "Everton",
"slug": "everton",
"sport": {
"name": "Football",
"slug": "football",
"id": 1
},
"userCount": 0,
"national": false,
"type": 0,
"id": 48,
"teamColors": {
"primary": "#374df5",
"secondary": "#374df5",
"text": "#ffffff"
},
"fieldTranslations": {
"nameTranslation": {
"ar": "إيفرتون",
"bn": "এভারটন",
"hi": "एवर्टन",
"ru": "Эвертон"
},
"shortNameTranslation": {}
}
}
},
{...},
{...}
],
"page": 1,
"pages": 131
}
```

### Matching Understat ↔ Sofascore

Player records between the two sources are matched using the **[reep](https://github.com/withqwerty/reep)** library, which resolves player identity across data providers.

---

## Phase 1 Summary


| Layer             | What it does                                    |
| ----------------- | ----------------------------------------------- |
| Stat Matrix       | Browse + compare every Premier League player    |
| Player Profile    | Understand an individual player in full         |
| Galaxy            | Discover stylistically similar players visually |
| Understat         | Attacking + xG data layer                       |
| Sofascore         | Defensive + passing data layer                  |
| reep              | Cross-source player identity matching           |
| Custom metrics    | Differentiated scoring + percentile system      |
| Similarity engine | Cosine distance + UMAP + KMeans archetypes      |


