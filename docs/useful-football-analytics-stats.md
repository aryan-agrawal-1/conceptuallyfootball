# Useful football analytics stats (and where to get them)

This document is a **product and engineering reference** for choosing metrics that are **interpretable**, **as independent as possible**, and **aligned with how analysts use them**. It complements `backend/ingestion/derived_definitions.py` and the Stat Matrix: it is not a full data-vendor comparison or licensing guide.

---

## How to use this doc

1. **Decide the question first** (finishing vs shot threat vs progression vs defending), then pick metrics that answer *that* question—not several correlated proxies for the same thing.
2. **Prefer rates** (per 90, per touch, per possession) over raw totals when comparing players with different minutes.
3. **Check provider definitions** before merging sources: “key pass,” “big chance,” and “tackle” are not identical across vendors.
4. **Label composite scores honestly**: if inputs are mostly volume or mostly xG-model outputs, the score should say so.

---

## Finishing and shot outcomes

| Stat | What it tends to measure | Caveats | Where it usually comes from |
|------|-------------------------|---------|----------------------------|
| **Non-penalty goals − NPxG (or G − xG)** | Outcome vs pre-shot model expectation; the usual public “finishing delta” | Very **noisy** over a season; driven by **sample size** and **luck**; not stable without shrinkage | **Understat** (already in stack), **Opta**-based feeds, **StatsBomb** match xG |
| **Post-shot xG (PSxG) − xG** (or goals vs PSxG) | **Shot placement / goalkeeper-independent** finishing vs where the shot was from | Requires **shot trajectory / goalmouth** data; still needs shrinkage for low shots | **Opta** (e.g. PSxG in professional datasets), **StatsBomb** shot-stopper / shot metrics in their data products |
| **Goals per shot on target** (or similar) | Simple conversion | Confounded by **shot distance/type**; use only with context | Derived from shot logs in any detailed feed |
| **NPxG per shot** | **Average chance quality** of attempts (shot selection / positions) | **Not** “finishing skill” by itself; highly **role- and team-dependent** | **Understat** player aggregates; same construct from **StatsBomb**/**Opta** shot-level xG |

**Analyst takeaway:** Public writing often separates **situation (xG)** from **execution (outcomes vs model or PSxG layer)**. For a “finishing” product signal with minimal data, **G−NPxG** is the standard—but it should be **caveated** or **shrunk**. **NPxG/90**, **shots/90**, and **NPxG/shot** belong in a **threat / shot profile** bucket, not the same label as finishing.

**Sources (high level):**

- **[Understat](https://understat.com/)** – Aggregated player xG/xA/chain stats (no full event API; scraping or third-party wrappers; terms of use apply).
- **[StatsBomb](https://statsbomb.com/)** / **[Hudl StatsBomb](https://www.hudl.com/products/statsbomb)** – Match and player event data, xG models, defensive pressures, pass heights, etc. (commercial).
- **[Opta](https://www.statsperform.com/opta/)** (Stats Perform) – Industry-standard event data; xG, PSxG, passes into box, etc. (commercial; also surfaces via broadcast and media partners).
- **[FBref](https://fbref.com/)** – Tables for many competitions; underlying match data for advanced sections is often **StatsBomb** (check site footers per competition). Good for **exploration** and **validation**, not always for **automated redistribution**.

---

## Chance creation and passing threat

| Stat | What it tends to measure | Caveats | Where it usually comes from |
|------|-------------------------|---------|----------------------------|
| **xA (expected assists)** | **Value of shots** taken after a player’s key creative action | Depends on **what the shooter does** after the pass; correlates with **key-pass volume** | **Understat**; **Opta** xA; **StatsBomb** pass-to-shot value |
| **Key passes / shot-creating actions** | **Volume** of passes that immediately precede shots | Does not encode **danger** without xA or similar | Most event providers; **Sofascore** (already in stack) |
| **Passes into penalty area / box entries** | **Territorial threat** into the box | Definition varies; not the same as xG | **Opta**, **StatsBomb**, **Wyscout** |
| **Through balls, progressive passes, pass into danger** | **Line-breaking** and **progression** | Definitions differ; often **possession- or zone-based** | **StatsBomb**, **Opta**, **Wyscout** |
| **Open-play sequence involvement** (e.g. xG assisted, shot creation chains) | **Role in moves** that end in chances | Can **overlap** with xA and chain metrics | **StatsBomb**-style OBV/chain products; **Opta** sequence addons |

**Analyst takeaway:** Strong dashboards usually combine **one value metric** (xA or equivalent) with **one volume or territory metric** (key passes, box passes, progressions)—not three metrics that are **algebraically or causally tied**.

**Sources:**

- Same as above; **Wyscout** ([glossary](https://dataglossary.wyscout.com/)) is useful for **naming** and **definitions** even if you license data elsewhere.

---

## Possession value and territory (including xT-style ideas)

| Stat | What it tends to measure | Caveats | Where it usually comes from |
|------|-------------------------|---------|----------------------------|
| **Expected threat (xT)** or **VAEP / OBV** | **Value added** per action or grid cell as the ball moves up the pitch | **Model-dependent**; not comparable across vendors without recalibration | **Research implementations** (open papers/code); **StatsBomb** OBV; some **analytics consultancies** publish methodologies |
| **Carries / progressive carries / dribble distance** | **Ball progression** with feet | Tracking or rich event data helps | **StatsBomb**, **Opta** carrying metrics where available, **SkillCorner**-class tracking |

**Analyst takeaway:** These metrics are widely cited for **replacing raw counts** with **field position and risk**. They are a good **next step** after xG/xA when you want **midfield progression** without double-counting shots.

**Sources:**

- **StatsBomb** OBV documentation and data products.
- **Wyscout** / **Impect** (commercial progression models—verify naming with vendor docs).

---

## Build-up and chain involvement

| Stat | What it tends to measure | Caveats | Where it usually comes from |
|------|-------------------------|---------|----------------------------|
| **xGChain / xGBuildup** | **Involvement** in possessions that end in shots; buildup excludes final actions in common definitions | **Same possession credited to many players**; **high correlation** between chain and buildup | **Understat** (already in stack); same concepts in **Opta**/**StatsBomb** chain metrics under different names |
| **Buildup share** (e.g. buildup ÷ chain) | **Style**: early-phase vs final-third share of chain credit | **Not a new data source**—ratio of two existing totals | Derived |

**Analyst takeaway:** Pick **either** a **rate** (buildup/90, chain/90) **or** a **style ratio**, or combine **carefully** to avoid one dominant factor in a composite.

---

## Defending and ball winning

| Stat | What it tends to measure | Caveats | Where it usually comes from |
|------|-------------------------|---------|----------------------------|
| **Tackles, interceptions, blocks, clearances** (per 90) | **Defensive activity** | **Not possession-adjusted**; **team style** and **opponent volume** dominate interpretation | **Sofascore** (already in stack); **Opta**; **StatsBomb** |
| **Possession-adjusted (PAdj) tackles / interceptions** | Activity **scaled by how much the opponent has the ball** | Needs **reliable possession time** (or agreed proxy) | **StatsBomb** publishes PAdj-style metrics; **Wyscout** glossary includes PAdj; derived if you compute possession yourself |
| **Pressures / pressure regains** | **Active defending** without a “won tackle” | Definition and coverage vary | **StatsBomb**; some **Opta** datasets |
| **Aerial duels won %** (or volume) | **Contest** strength in the air | Sample size for defenders varies | **Opta**, **StatsBomb**, **Wyscout**, **Sofascore** (where exposed) |

**Analyst takeaway:** Public articles (e.g. **StatsBomb** on [possession-adjusted stats](https://blogarchive.statsbomb.com/articles/soccer/introducing-possession-adjusted-player-stats/)) argue raw counts **understate** high-possession team defenders. Without PAdj or pressures, prefer labels like **“defensive activity”** rather than **“defending quality.”**

---

## Goalkeeping (for completeness)

| Stat | What it tends to measure | Caveats | Where it usually comes from |
|------|-------------------------|---------|----------------------------|
| **PSxG − goals conceded** (or similar) | Shot-stopping vs **placement-adjusted** expectation | Needs **PSxG**; small samples per keeper | **Opta**, **StatsBomb**, **FBref** tables where provided |

---

## Physical and tracking layer (optional upgrade path)

| Stat | What it tends to measure | Caveats | Where it usually comes from |
|------|-------------------------|---------|----------------------------|
| **Distance, sprints, high-speed running** | **Load** and **athletic output** | Not “technical quality”; **positional** differences | **Second Spectrum** / league tracking APIs, **SkillCorner**, **Catapult**-class providers (league-specific) |

---

## Suggested priority for Statballer-style composites

Rough **order of impact** if you extend ingestion beyond **Understat + Sofascore**:

1. **Possession or opponent-possession proxy** – unlocks **PAdj**-style defending and fairer comparisons.
2. **Progressive / line-breaking pass and carry metrics** – separates **build-up** from **shot volume** better than xGChain alone.
3. **Post-shot xG layer** – only if you want a **credible “finishing”** story beyond **G−xG**.
4. **Unified event feed** (one vendor per competition) – reduces **definition drift** when merging providers.

---

## Further reading (methodology, not vendors)

- [StatsBomb blog archive](https://blogarchive.statsbomb.com/) – xG, shot quality, PAdj, pressures.
- [Get Goalside](https://www.getgoalsideanalytics.com/) – Intuitive essays on adjustment and interpretation.
- Academic and semi-academic work on **expected goals**, **VAEP**, and **hierarchical models** for finishing (search: *hierarchical Bayesian finishing football xG*) for **shrinkage** when you build scores.

---

## Disclaimer

Vendor names, metric names, and API availability **change**. Before building production pipelines, confirm **licensing**, **coverage by competition**, and **field definitions** in the contract or schema for that provider and season.
