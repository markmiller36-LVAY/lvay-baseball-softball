# LVAY Baseball/Softball

Power rating engine and API for Louisiana high school baseball and softball.
Part of the LVAY (Louisiana Vs All Y'all) platform at louisianavsallyall.com.

## Architecture

```
lvay-scraper  →  /data/lvay_v2.db  →  lvay-baseball-softball (this repo)
```

Raw game data is collected by `lvay-scraper` and stored in the shared SQLite DB.
This repo reads that data, calculates LHSAA power ratings, and serves the API.

## LHSAA Formula

| Result | Base Points | Bonus |
|--------|-------------|-------|
| Win | 20 | + opponent wins + class/div bonus |
| Loss | 0 | + opponent wins + class/div bonus |
| Tie | 5 | + opponent wins |
| Double Forfeit | 1 (winner) | + opponent wins |

**Final Rating = Total Points / Games Played**

Class/division bonus: +2 per level higher than your school (in-state only).

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `/api/schedules/baseball` | All baseball schedules |
| `/api/schedules/softball` | All softball schedules |
| `/api/schedules/baseball?school=Barbe` | Single school lookup |
| `/api/rankings/baseball` | Baseball power rankings |
| `/api/rankings/softball` | Softball power rankings |
| `/api/rankings/calculate` | Recalculate all rankings |
| `/api/rankings/calculate?sport=baseball` | Recalculate one sport |
| `/api/status` | DB status and game counts |

## Validation Targets (2025-2026 Season)

### Baseball
- Barbe (Non-Select D1 #1): 40.38
- Calvary Baptist (Select D3 #3): 33.35

### Softball
- Calvary Baptist (Select D3 #1): 39.77
- Walker (Non-Select D1 #1): 36.26

## Environment Variables

| Variable | Value |
|----------|-------|
| `DB_PATH` | `/data/lvay_v2.db` |
| `SEASON_YEAR` | `2026` |
| `TZ` | `America/Chicago` |

## Partners
Mark Miller, Jerit Roser, Jacob Coltson
