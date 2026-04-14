"""
LVAY Baseball/Softball API Server
====================================
Reads from shared lvay_v2.db (populated by lvay-scraper).
Serves schedule and rankings data for baseball and softball.
"""

from flask import Flask, jsonify, request
import sqlite3
import os
from datetime import datetime
from power_rating_engine import calculate_power_ratings, save_rankings

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "/data/lvay_v2.db")
SEASON  = os.environ.get("SEASON_YEAR", "2026")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return jsonify({
        "service": "LVAY Baseball/Softball API",
        "status": "ok",
        "season": SEASON,
        "endpoints": [
            "/api/schedules/baseball",
            "/api/schedules/softball",
            "/api/schedules/baseball?school=Barbe",
            "/api/rankings/baseball",
            "/api/rankings/softball",
            "/api/rankings/calculate",
            "/api/status",
        ]
    })


@app.route("/api/status")
def status():
    conn = get_db()
    c = conn.cursor()
    counts = {}
    for sport in ["baseball", "softball"]:
        c.execute("""
            SELECT COUNT(*) FROM games
            WHERE sport=? AND season=?
        """, (sport, SEASON))
        counts[sport] = c.fetchone()[0]
    conn.close()
    return jsonify({
        "status": "ok",
        "season": SEASON,
        "db": DB_PATH,
        "game_counts": counts,
        "timestamp": datetime.now().isoformat()
    })


# ── Schedules ─────────────────────────────────────────────────────────────────

def get_schedules(sport):
    """Return all schools with their game-by-game breakdown."""
    conn = get_db()
    c = conn.cursor()
    school_filter = request.args.get("school")

    if school_filter:
        c.execute("""
            SELECT DISTINCT school FROM games
            WHERE sport=? AND season=?
            AND LOWER(school) LIKE LOWER(?)
        """, (sport, SEASON, f"%{school_filter}%"))
    else:
        c.execute("""
            SELECT DISTINCT school FROM games
            WHERE sport=? AND season=?
            ORDER BY school ASC
        """, (sport, SEASON))

    school_rows = c.fetchall()
    schools = []

    for row in school_rows:
        school = row["school"]

        c.execute("""
            SELECT game_date, opponent, home_away, win_loss, score,
                   class_, district, opponent_class, out_of_state,
                   district_class
            FROM games
            WHERE school=? AND sport=? AND season=?
            ORDER BY game_date ASC
        """, (school, sport, SEASON))

        games = [dict(g) for g in c.fetchall()]
        wins    = sum(1 for g in games if (g["win_loss"] or "").upper() in ("W","WIN"))
        losses  = sum(1 for g in games if (g["win_loss"] or "").upper() in ("L","LOSS"))
        ties    = sum(1 for g in games if (g["win_loss"] or "").upper() in ("T","TIE"))

        schools.append({
            "school":  school,
            "sport":   sport,
            "season":  SEASON,
            "record":  f"{wins}-{losses}-{ties}" if ties else f"{wins}-{losses}",
            "wins":    wins,
            "losses":  losses,
            "ties":    ties,
            "games":   games,
        })

    conn.close()
    return jsonify({
        "sport":   sport,
        "season":  SEASON,
        "count":   len(schools),
        "schools": schools
    })


@app.route("/api/schedules/baseball")
def schedules_baseball():
    return get_schedules("baseball")


@app.route("/api/schedules/softball")
def schedules_softball():
    return get_schedules("softball")


# ── Rankings ──────────────────────────────────────────────────────────────────

def get_rankings(sport):
    """Return saved power rankings for a sport."""
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT school, class_, division, district,
               power_rating, wins, losses, ties,
               games_played, calculated_at
        FROM power_rankings
        WHERE sport=? AND season=?
        ORDER BY
            CASE division
                WHEN 'I'   THEN 1
                WHEN 'II'  THEN 2
                WHEN 'III' THEN 3
                WHEN 'IV'  THEN 4
                ELSE 5
            END,
            power_rating DESC
    """, (sport, SEASON))

    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    if not rows:
        return jsonify({
            "error": "No rankings found. Run /api/rankings/calculate first.",
            "sport": sport,
            "season": SEASON
        }), 404

    return jsonify({
        "sport":    sport,
        "season":   SEASON,
        "count":    len(rows),
        "rankings": rows
    })


@app.route("/api/rankings/baseball")
def rankings_baseball():
    return get_rankings("baseball")


@app.route("/api/rankings/softball")
def rankings_softball():
    return get_rankings("softball")


@app.route("/api/rankings/calculate")
def rankings_calculate():
    """Recalculate and save power rankings for baseball and/or softball."""
    sport_param = request.args.get("sport", "both")
    sports = ["baseball", "softball"] if sport_param == "both" else [sport_param]

    results = {}
    for sport in sports:
        print(f"\nCalculating {sport} rankings...")
        rankings = calculate_power_ratings(sport)
        saved = save_rankings(sport, rankings)
        results[sport] = {
            "schools_ranked": saved,
            "top_5": [
                {
                    "rank": i + 1,
                    "school": r["school"],
                    "rating": r["power_rating"],
                    "record": f"{r['wins']}-{r['losses']}-{r['ties']}",
                    "division": r["division"]
                }
                for i, r in enumerate(rankings[:5])
            ]
        }

    return jsonify({
        "status":    "ok",
        "season":    SEASON,
        "timestamp": datetime.now().isoformat(),
        "results":   results
    })


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\nLVAY Baseball/Softball API starting on port {port}")
    print(f"DB: {DB_PATH} | Season: {SEASON}")
    app.run(host="0.0.0.0", port=port, debug=False)
