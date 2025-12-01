from flask import Flask, render_template, request, jsonify
from datetime import date, datetime, timedelta
import json
import os

app = Flask(__name__)

DATA_FILE = "sul_calendar_data_web.json"


# ---------------- 데이터 로드/저장 ---------------- #
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "users" not in data:
                data = {"users": {}}
            return data
    except Exception:
        return {"users": {}}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user_days(data, username: str):
    users = data.setdefault("users", {})
    return users.setdefault(username, {})


# ---------------- 통계 계산 ---------------- #
def calc_streak(user_days, key: str) -> int:
    """오늘 기준 연속으로 안 마신 일수."""
    today = date.today()
    d = today
    cnt = 0
    while True:
        ds = d.isoformat()
        day = user_days.get(ds)
        if day and day.get(key) == "마셨다":
            break
        cnt += 1
        d -= timedelta(days=1)
        if cnt > 365:
            break
    return cnt


def count_in_month(user_days, year: int, month: int, key: str) -> int:
    """해당 달에 '마신 날' 개수."""
    cnt = 0
    d = date(year, month, 1)
    while d.month == month:
        day = user_days.get(d.isoformat())
        if day and day.get(key) == "마셨다":
            cnt += 1
        d += timedelta(days=1)
    return cnt


def calc_rankings(data, year: int, month: int):
    """전체 사용자 기준, 이번 달 커피/술 많이 마신 순위."""
    users = data.get("users", {})
    coffee_rank = []
    alcohol_rank = []

    for username, user_days in users.items():
        c = count_in_month(user_days, year, month, "coffee")
        a = count_in_month(user_days, year, month, "alcohol")
        coffee_rank.append((username, c))
        alcohol_rank.append((username, a))

    coffee_rank.sort(key=lambda x: x[1], reverse=True)
    alcohol_rank.sort(key=lambda x: x[1], reverse=True)

    return coffee_rank[:10], alcohol_rank[:10]


# ---------------- 라우트 ---------------- #
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/month")
def api_month():
    """
    /api/month?user=이름&year=2025&month=11
    """
    username = request.args.get("user", "").strip() or "default"
    try:
        year = int(request.args.get("year"))
        month = int(request.args.get("month"))
    except (TypeError, ValueError):
        return jsonify({"error": "year/month 파라미터가 잘못되었습니다."}), 400

    data = load_data()
    user_days = get_user_days(data, username)

    # 이번 달 데이터만 days에 담기
    days = {}
    d = date(year, month, 1)
    while d.month == month:
        ds = d.isoformat()
        if ds in user_days:
            days[ds] = user_days[ds]
        d += timedelta(days=1)

    # 개인 통계
    coffee_streak = calc_streak(user_days, "coffee")
    alcohol_streak = calc_streak(user_days, "alcohol")
    coffee_month = count_in_month(user_days, year, month, "coffee")
    alcohol_month = count_in_month(user_days, year, month, "alcohol")

    # 전체 사용자 순위
    coffee_rank, alcohol_rank = calc_rankings(data, year, month)

    stats = {
        "coffee_streak": coffee_streak,
        "alcohol_streak": alcohol_streak,
        "coffee_month": coffee_month,
        "alcohol_month": alcohol_month,
        "coffee_rank": coffee_rank,
        "alcohol_rank": alcohol_rank,
    }

    return jsonify({"days": days, "stats": stats})


@app.route("/api/update", methods=["POST"])
def api_update():
    """
    { "user": "홍길동", "date": "2025-11-28", "coffee": true/false, "alcohol": true/false }
    """
    body = request.get_json() or {}
    username = (body.get("user") or "").strip() or "default"
    date_str = body.get("date")
    if not date_str:
        return jsonify({"error": "date가 없습니다."}), 400

    try:
        datetime.fromisoformat(date_str)
    except Exception:
        return jsonify({"error": "date 형식이 잘못되었습니다."}), 400

    coffee_on = body.get("coffee")
    alcohol_on = body.get("alcohol")

    data = load_data()
    user_days = get_user_days(data, username)
    day = user_days.get(date_str, {})

    if coffee_on is True:
        day["coffee"] = "마셨다"
    elif coffee_on is False:
        day.pop("coffee", None)

    if alcohol_on is True:
        day["alcohol"] = "마셨다"
    elif alcohol_on is False:
        day.pop("alcohol", None)

    if day:
        user_days[date_str] = day
    else:
        user_days.pop(date_str, None)

    save_data(data)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
