"""
LVAY Baseball/Softball Power Rating Engine
============================================
Implements official LHSAA formula:
  Win  = 20 pts + opponent wins + class/division bonus
  Loss =  0 pts + opponent wins + class/division bonus
  Tie  =  5 pts + opponent wins
  Double Forfeit = 1 pt to winner + opponent wins

Final Rating = total power points / games played

Class order (lowest to highest): 1A, 2A, 3A, 4A, 5A
Division order (lowest to highest): IV, III, II, I
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "/data/lvay_v2.db")
SEASON   = os.environ.get("SEASON_YEAR", "2026")

CLASS_RANK = {"1A": 1, "2A": 2, "3A": 3, "4A": 4, "5A": 5}
DIV_RANK   = {"IV": 1, "III": 2, "II": 3, "I": 4}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def parse_class_div(class_str):
    """Parse '3-5A' into class='5A', division='III' (rank 3)."""
    if not class_str:
        return None, None
    parts = class_str.strip().split("-")
    if len(parts) == 2:
        div_num, cls = parts
        div_map = {"1": "I", "2": "II", "3": "III", "4": "IV",
                   "5": "V", "6": "VI", "7": "VII", "8": "VIII",
                   "9": "IX", "10": "X"}
        div = div_map.get(div_num, div_num)
        return cls.upper(), div.upper()
    return class_str.upper(), None


def get_class_bonus(school_class, school_div, opp_class, opp_div):
    """
    Calculate class/division bonus.
    +2 for each class level higher the opponent is.
    +2 for each division level higher (only if class is also higher or equal).
    OOS opponents: no bonus (handled by caller).
    """
    bonus = 0
    sc = CLASS_RANK.get(school_class, 0)
    oc = CLASS_RANK.get(opp_class, 0)
    sd = DIV_RANK.get(school_div, 0)
    od = DIV_RANK.get(opp_div, 0)

    if oc > sc:
        bonus += (oc - sc) * 2
        if od > sd:
            bonus += (od - sd) * 2
    elif oc == sc and od > sd:
        bonus += (od - sd) * 2

    return bonus


def get_opponent_wins(conn, opponent, sport, season):
    """Count wins for an opponent from the games table."""
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) FROM games
        WHERE school=? AND sport=? AND season=?
        AND UPPER(win_loss) IN ('W','WIN','L','LOSS','T','TIE')
        AND UPPER(win_loss) IN ('W','WIN')
    """, (opponent, sport, season))
    row = c.fetchone()
    return row[0] if row else 0


def calculate_power_ratings(sport):
    """
    Calculate power ratings for all schools in a sport.
    Returns list of dicts sorted by division then rating desc.
    """
    conn = get_db()
    c = conn.cursor()

    # Get all schools for this sport/season
    c.execute("""
        SELECT DISTINCT school, class_, district
        FROM games
        WHERE sport=? AND season=?
        AND UPPER(win_loss) NOT IN ('PPD','CANCELLED','','NONE')
    """, (sport, SEASON))
    schools = c.fetchall()

    results = []

    for row in schools:
        school     = row["school"]
        class_str  = row["class_"] or ""
        district   = row["district"] or ""

        school_class, school_div = parse_class_div(class_str)

        # Get all countable games
        c.execute("""
            SELECT * FROM games
            WHERE school=? AND sport=? AND season=?
            AND UPPER(win_loss) NOT IN ('PPD','CANCELLED','','NONE')
        """, (school, sport, SEASON))
        games = c.fetchall()

        total_pts   = 0
        games_played = 0
        wins = losses = ties = 0

        for g in games:
            wl       = (g["win_loss"] or "").upper().strip()
            opp      = g["opponent"] or ""
            opp_cls  = g["opponent_class"] or ""
            oos      = (g["out_of_state"] or "").upper() in ("Y", "YES", "1", "TRUE")

            opp_class, opp_div = parse_class_div(opp_cls)

            # Base points
            if wl in ("W", "WIN"):
                base = 20
                wins += 1
            elif wl in ("L", "LOSS"):
                base = 0
                losses += 1
            elif wl in ("T", "TIE"):
                base = 5
                ties += 1
            elif wl == "DOUBLE FORFEIT":
                base = 1
                wins += 1
            else:
                continue  # skip unknown

            games_played += 1

            # Opponent wins (always added)
            opp_wins = get_opponent_wins(conn, opp, sport, SEASON)

            # Class/division bonus (not for OOS)
            bonus = 0
            if not oos and opp_class and school_class:
                bonus = get_class_bonus(school_class, school_div,
                                        opp_class, opp_div)

            total_pts += base + opp_wins + bonus

        # Final rating = total / games played
        rating = round(total_pts / games_played, 2) if games_played > 0 else 0.0

        results.append({
            "school":      school,
            "sport":       sport,
            "season":      SEASON,
            "class_":      school_class or "",
            "division":    school_div or "",
            "district":    district,
            "power_rating": rating,
            "wins":        wins,
            "losses":      losses,
            "ties":        ties,
            "games_played": games_played,
            "total_pts":   total_pts,
        })

    conn.close()

    # Sort: Division I first, then by rating desc
    div_order = {"I": 1, "II": 2, "III": 3, "IV": 4, "": 5}
    results.sort(key=lambda x: (div_order.get(x["division"], 5),
                                 -x["power_rating"]))
    return results


def save_rankings(sport, rankings):
    """Save calculated rankings to power_rankings table."""
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS power_rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sport TEXT,
            season TEXT,
            school TEXT,
            class_ TEXT,
            division TEXT,
            track TEXT,
            district TEXT,
            power_rating REAL,
            wins INTEGER,
            losses INTEGER,
            ties INTEGER,
            games_played INTEGER,
            total_pts INTEGER,
            calculated_at TEXT,
            UNIQUE(sport, season, school)
        )
    """)

    now = datetime.now().isoformat()
    saved = 0

    for r in rankings:
        try:
            c.execute("""
                INSERT OR REPLACE INTO power_rankings
                (sport, season, school, class_, division, district,
                 power_rating, wins, losses, ties, games_played,
                 total_pts, calculated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                r["sport"], r["season"], r["school"],
                r["class_"], r["division"], r["district"],
                r["power_rating"], r["wins"], r["losses"],
                r["ties"], r["games_played"], r["total_pts"], now
            ))
            saved += 1
        except sqlite3.Error as e:
            print(f"  DB error saving {r['school']}: {e}")

    conn.commit()
    conn.close()
    print(f"  Saved {saved} {sport} rankings to DB")
    return saved


if __name__ == "__main__":
    for sport in ["baseball", "softball"]:
        print(f"\nCalculating {sport} power ratings...")
        rankings = calculate_power_ratings(sport)
        save_rankings(sport, rankings)
        print(f"  Top 5 {sport}:")
        for r in rankings[:5]:
            print(f"    {r['school']}: {r['power_rating']} "
                  f"({r['wins']}-{r['losses']}-{r['ties']}) Div {r['division']}")
