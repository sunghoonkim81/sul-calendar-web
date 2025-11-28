from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)

DATA_FILE = "sul_calendar_data_web.json"


# ---------------------------
# 데이터 파일 로드/저장
# ---------------------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------
# 연속 안 마신 날 계산
# ---------------------------
def calc_streak(user_days):
    today = datetime.now().date()
    streak_coffee = 0
    streak_alcohol = 0

    cur = today
    while True:
        date_str = cur.strftime("%Y-%m-%d")
        day = user_days.get(date_str, {})

        if day.get("coffee") == "마셨다":
            break
        streak_coffee += 1
        cur -= timedelta(days=1)

    cur = today
    while True:
        date_str = cur.strftime("%Y-%m-%d")
        day = user_days.get(date_str, {})
        if day.get("alcohol") == "마셨다":
            break
        streak_alcohol += 1
        cur -= timedelta(days=1)

    return streak_coffee, streak_alcohol


# ---------------------------
# 이번 달 카운트
# ---------------------------
def calc_month_counts(user_days, year, month):
    coffee_cnt = 0
    alcohol_cnt = 0
    for d in range(1, 32):
        try:
            dt = datetime(year, month, d)
        except:
            continue
        ds = dt.strftime("%Y-%m-%d")
        day = user_days.get(ds, {})
        if day.get("coffee") == "마셨다":
            coffee_cnt += 1
        if day.get("alcohol") == "마셨다":
            alcohol_cnt += 1
    return coffee_cnt, alcohol_cnt


# ---------------------------
# 새로운 기능: 전체 사용자 “순위”
# ---------------------------
def calc_rankings(data, year, month):
    users = data.get("users", {})

    coffee_rank = []
    alcohol_rank = []

    for username, user_days in users.items():
        c_cnt, a_cnt = calc_month_counts(user_days, year, month)
        coffee_rank.append((username, c_cnt))
        alcohol_rank.append((username, a_cnt))

    # 많이 마신 순으로 정렬
    coffee_rank.sort(key=lambda x: x[1], reverse=True)
    alcohol_rank.sort(key=lambda x: x[1], reverse=True)

    # TOP 10만
    return coffee_rank[:10], alcohol_rank[:10]


# ---------------------------
# ROUTES
# ---------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/month")
def api_month():
    user = request.args.get("user", "default")
    year = int(request.args.get("year"))
    month = int(request.args.get("month"))

    data = load_data()
    users = data.get("users", {})
    user_days = users.get(user, {})

    # streak
    streak_coffee, streak_alcohol = calc_streak(user_days)

    # month count
    coffee_cnt, alcohol_cnt = calc_month_counts(user_days, year, month)

    # 전체 사용자 순위 추가
    coffee_rank, alcohol_rank = calc_rankings(data, year, month)

    return jsonify({
        "days": user_days,
        "stats": {
            "coffee_streak": streak_coffee,
            "alcohol_streak": streak_alcohol,
            "coffee_month": coffee_cnt,
            "alcohol_month": alcohol_cnt,

            # ★ 추가된 부분
            "coffee_rank": coffee_rank,
            "alcohol_rank": alcohol_rank
        }
    })


@app.route("/api/update", methods=["POST"])
def api_update():
    body = request.get_json()
    user = body.get("user", "default")
    date_str = body.get("date")

    data = load_data()
    users = data.setdefault("users", {})
    user_days = users.setdefault(user, {})
    day = user_days.setdefault(date_str, {})

    if "coffee" in body:
        day["coffee"] = "마셨다" if body["coffee"] else "안 마셨다"
    if "alcohol" in body:
        day["alcohol"] = "마셨다" if body["alcohol"] else "안 마셨다"

    save_data(data)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
