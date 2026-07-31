# Do Tennis Players Need Time to Adapt to a New Surface?

**I set out to measure surface adaptation in professional tennis. The effect I found disappeared once I controlled for which tournament each match was played at.**

![The effect dissolving](figures/1_etkinin_erimesi.png)

When a player moves from the clay season to the grass season, do they return worse in their first few grass matches than they do later in the same swing? The first analysis said yes: −0.14 SD, p = 0.002. After adding tournament identity to the model, the effect shrank to a third of its size and lost significance: −0.06 SD, p = 0.24.

The reason is simple but easy to miss. **The grass season starts at Stuttgart and Halle and ends at Wimbledon.** These courts do not play at the same speed. What looked like "the player hasn't adjusted yet" was largely "the early matches happened on faster courts."

---

## The question

Is there a measurable *adaptation window* after a surface change? And if so, does it vary between players?

This is a different question from the usual "surface adaptation index" approach, which measures how much a player's average performance varies across the three surfaces. That is a measure of *level*, not of *adjustment*. Here adaptation is defined temporally: the gap between a player's first matches on a new surface and the rest of that same surface swing.

| Hypothesis | Claim | Verdict |
|---|---|---|
| **H1** | Performance drops in the first matches on a new surface | **Rejected** — a weak effect exists in the opposite direction |
| **H2** | The size of the effect depends on the direction of the switch | Partly — but it is not surface-specific |
| **H3** | Adaptation speed is a stable player trait | **Rejected** — r = 0.07, indistinguishable from zero |

---

## Data

**Source:** [Tennismylife/TML-Database](https://github.com/Tennismylife/TML-Database) · CC BY-NC-SA
**Origin:** Jeff Sackmann / [Tennis Abstract](https://github.com/JeffSackmann)
**Period:** 2021–2025 (5 full seasons) · **Retrieved:** 31 July 2026

> This project was originally built on Jeff Sackmann's `tennis_atp` repository. During the work the repository became unavailable (404). I switched to the TML-Database mirror, which uses an identical column schema, so no code changes were required. TML-Database additionally carries an `indoor` flag, which made it possible to treat indoor hard courts as a separate surface in a robustness check.

### Cleaning

| Filter | Rows dropped | Share |
|---|---:|---:|
| Team/exhibition events + Davis Cup + Olympics | 1,547 | 10.5% |
| Missing surface | 0 | 0.0% |
| Retirements, walkovers, defaults | 475 | 3.2% |
| Missing serve statistics | 6 | 0.0% |
| Implausibly short matches (< 20 service points) | 1 | 0.0% |
| **Retained** | **12,639** | **86.2%** |

Team and exhibition events (United Cup, ATP Cup, Laver Cup, Davis Cup, the Olympics) were removed deliberately: they sit in the middle of the calendar as isolated one-off matches and corrupt the block-detection logic.

---

## Method

### 1. Long format

Each match becomes two rows, one per player's perspective. 12,639 matches → **25,278 rows**.

The core metric is **return points won (RPW)**: the share of the opponent's service points that the player won.

```
RPW = (opp_svpt − opp_1stWon − opp_2ndWon) / opp_svpt
```

An identity check runs on every execution: `RPW + SPW = 1.0000`, because every return point won is a service point lost by someone.

| Surface | Mean RPW | SD | Matches |
|---|---:|---:|---:|
| Clay | 0.3804 | 0.0853 | 7,786 |
| Hard | 0.3545 | 0.0858 | 14,456 |
| Grass | 0.3387 | 0.0796 | 3,036 |

### 2. Residualisation

Raw return percentage reflects three things: the player's skill, **the opponent's serve**, and context. An additive ridge model separates them:

```
RPW ~ player + opponent + surface + round  (+ tournament)
```

The residual is observed minus predicted, then standardised within surface.

**This step is a precondition for validity, not an optional refinement.** The first matches of a block are almost always early rounds, i.e. against weaker opponents. In raw data, return percentage falls from 36.4% in R128 to 34.9% in finals. After residualisation that gradient vanishes entirely (≈ 0.00 across all rounds).

Model R² = 0.297 (0.327 with tournament fixed effects). Only about 30% of the variation in a single match's return percentage is structural; the rest is match-to-match noise. This foreshadows why H3 turns out to be untestable in practice.

### 3. Surface blocks

Each player's matches are ordered chronologically. **Consecutive matches on the same surface form a block.** A new block starts when the surface changes or after a gap of more than 60 days.

Validity criteria: at least 5 matches, and the preceding block must be on a different surface. Result: **1,441 blocks · 16,008 matches · 232 players.**

The algorithm reconstructs the tennis calendar without being told anything about it. Alcaraz, 2024:

```
Hard  |  4 matches | Australian Open
Clay  |  3 matches | Buenos Aires
Hard  | 10 matches | Indian Wells, Miami
Clay  | 11 matches | Madrid, Roland Garros
Grass |  9 matches | Queen's Club, Wimbledon
Hard  | 17 matches | Cincinnati, US Open, Beijing, Shanghai
```

### 4. Transition penalty

```
TP = mean(first 2 matches of block) − mean(remaining matches)
```

Negative means degradation on arrival. Because the comparison happens *within* a block, the player's general skill level on that surface cancels out structurally — strong and weak players cannot be confounded by construction.

### 5. Modelling

`statsmodels` MixedLM was attempted. The player-level variance was estimated at the boundary of the parameter space (zero), the Hessian became singular, and standard errors exploded (SE ≈ 3.4 million). A variance component pinned at zero is itself the answer to H3.

The analysis therefore uses **block-level OLS with standard errors clustered by player** — it accounts for the same dependence and is numerically stable.

---

## Findings

### H1 — No adaptation penalty; a weak "fresh start" effect instead

| Model | Coefficient | SE | p |
|---|---:|---:|---:|
| Return | +0.0806 | 0.0216 | 0.0002 |
| Return + tournament control | +0.0441 | 0.0219 | 0.0447 |
| Serve (placebo) | +0.0449 | 0.0221 | 0.0420 |
| **Serve + tournament control** | **+0.0837** | 0.0213 | **0.0001** |

The coefficients are **positive**: players perform slightly *above* their own baseline in the first matches of a new surface. The opposite of the hypothesis.

The last row is the decisive one. After tournament controls, the residual effect is roughly **twice as large on serve as on return** (+0.084 vs +0.044). If this were surface adaptation, the ordering would be reversed — serving is far less sensitive to surface than returning. When both move in the same direction and serve moves more, what is being measured is not surface-specific. It is general freshness after a rest period.

**Practical magnitude:** 0.10 SD ≈ 0.85 percentage points ≈ 0.7 return points per match. The residual +0.044 effect works out to about **one third of a point per match**. Statistically distinguishable from zero, practically negligible.

### H2 — The clay-to-grass finding was a tournament composition artefact

![Tournament composition](figures/2_turnuva_kompozisyonu.png)

| Transition | Base model | + tournament control | p |
|---|---:|---:|---:|
| Clay → Grass | −0.1443 | −0.0586 | 0.236 |
| Clay → Hard | +0.2227 | +0.1349 | 0.006 * |
| Hard → Clay | +0.1579 | +0.0787 | 0.027 * |
| Grass → Hard | +0.0045 | −0.0275 | 0.616 |
| Grass → Clay | +0.1065 | +0.1098 | 0.196 |

The mechanism is visible directly in the data:

| Tournament | Share of first 2 block matches | Share of match 3 onward | Mean return % |
|---|---:|---:|---:|
| Stuttgart | 28.2% | 2.9% | 31.8 |
| Halle | 17.4% | 10.7% | 32.9 |
| 's-Hertogenbosch | 21.4% | 2.6% | 34.1 |
| Queen's Club | 15.6% | 9.1% | 34.4 |
| **Wimbledon** | **5.4%** | **47.4%** | **36.1** |

The opening matches of the grass swing are played on the fastest, hardest-to-return courts on tour; nearly half of the later matches are at Wimbledon. That 4.3-point court gap is the source of the apparent "adaptation penalty."

The two surviving transitions (clay→hard, hard→clay) are both positive and both coincide with the start of a season block — freshness again.

### H3 — Adaptation speed is not a stable player trait

| Measure | n | r | p |
|---|---:|---:|---:|
| Return | 53 players | +0.021 | 0.882 |
| Return + tournament | 53 players | +0.069 | 0.622 |
| Serve | 53 players | +0.113 | 0.422 |

A player's transition penalty in 2021–23 carries **no predictive information** about their transition penalty in 2023–25. Test-retest reliability is zero.

This means that any "top 10 fastest adapters" ranking built from this kind of measure is noise. Such a list can be produced, and it will look convincing — but it will be entirely different next year.

![Within-block trajectory](figures/3_blok_ici_seyir.png)

---

## Robustness

Each row re-runs the full pipeline.

| Variant | Blocks | Overall | p | Clay→Grass | p |
|---|---:|---:|---:|---:|---:|
| **Baseline (K=2, min=5, 60d)** | 1,441 | +0.048 | 0.031 | −0.059 | 0.236 |
| Adaptation window K=1 | 1,441 | +0.064 | 0.030 | −0.013 | 0.843 |
| Adaptation window K=3 | 1,441 | +0.090 | 0.000 | +0.041 | 0.373 |
| Min block size = 4 | 1,676 | +0.076 | 0.001 | +0.009 | 0.855 |
| Min block size = 6 | 1,218 | +0.029 | 0.202 | −0.074 | 0.185 |
| Min block size = 8 | 894 | +0.002 | 0.953 | −0.128 | 0.099 |
| Gap threshold 45 days | 1,409 | +0.040 | 0.076 | −0.059 | 0.236 |
| Gap threshold 90 days | 1,465 | +0.049 | 0.026 | −0.059 | 0.236 |
| Ridge alpha = 1 | 1,441 | +0.048 | 0.031 | −0.058 | 0.237 |
| Ridge alpha = 20 | 1,441 | +0.048 | 0.028 | −0.059 | 0.231 |
| Slams + Masters only | 638 | +0.046 | 0.186 | +0.126 | 0.113 |
| Indoor treated as separate surface | 1,942 | +0.077 | 0.000 | −0.059 | 0.236 |
| Serve (placebo) | 1,441 | +0.085 | 0.000 | +0.088 | 0.136 |

**The clay-to-grass effect is not significant in any of the 13 variants** (p ranges from 0.099 to 0.855, and the sign flips in several).

**The surviving overall effect is fragile.** Raising the minimum block size from 4 to 8 drives the coefficient from +0.076 to +0.002. The "fresh start bonus" is therefore driven mainly by short blocks — in a 5-match block, the first two matches are 40% of the block and the comparison window is only three matches. This is the fingerprint of the survivorship bias described below.

The ridge regularisation parameter has no effect on the result.

---

## Limitations

1. **Survivorship bias.** A block only has a comparison window if the player kept winning. Players who lose early drop out of the sample. The robustness table makes this bias visible but does not remove it.

2. **The tournament control may over-adjust.** If genuine adaptation systematically coincides with particular tournaments, a tournament fixed effect will absorb it. This analysis answers the narrower but more defensible question: is there adaptation *holding the venue constant*?

3. **Return percentage is one dimension of adaptation.** Movement, sliding technique and tactical adjustment are not in this data.

4. **Sample.** Top-level ATP only (250 and above), 5 seasons, 232 players, 1,441 blocks. Clay→grass has 259 blocks; hard→grass has only 10 and is excluded.

5. **Measurement noise.** Only ~30% of single-match return percentage is structural, so statistical power to detect small individual differences is low. The "no" on H3 should be read as "not separable with this data" rather than "definitively absent."

6. **The 60-day block-splitting threshold** is a practical rather than theoretical choice; 45-day and 90-day variants were tested and the result did not change.

---

## Reproduction

```bash
git clone <repo>
cd surface-transition-analysis
pip install -r requirements.txt

python app.py      # pipeline + models  (~5 min, downloads on first run)
python viz.py      # figures → figures/
```

Setting `ROBUSTLUK_KOS = False` in `app.py` skips the robustness section and cuts runtime to about a minute.

Data files are gitignored; `app.py` fetches them from source on first run.

```
app.py       Sections 1-7, 9, 10 — pipeline, tests, robustness
viz.py       Section 8 — three figures
data/        intermediate outputs (parquet)
figures/     PNG outputs
```

Code comments and console output are in Turkish.

---

## Attribution and licence

Data: [Tennismylife/TML-Database](https://github.com/Tennismylife/TML-Database), CC BY-NC-SA.
Origin: Jeff Sackmann, [Tennis Abstract](https://github.com/JeffSackmann) — maintained as personal work; commercial use is contrary to the licence terms.

Code is MIT licensed. Data files are not redistributed in this repository.
