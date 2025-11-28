from flask import Flask, render_template, request, jsonify
import calendar
import json
import os
from datetime import date, datetime, timedelta

app = Flask(__name__)

DATA_FILE = "sul_calendar_data_web.json"

# 전역 데이터 (메모리 + 파일 저장)
DATA = {"users": {}}


def load_data():
    global DATA
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                DATA = json.load(f)
                # 안전 장치
                if "users" not in DATA:
                    DATA = {"users": {}}
        except Exception:
            DATA = {"users": {}}
    else:
        DATA = {"users": {}}


def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(DATA, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("데이터 저장 오류:", e)


def get_user_data(username: str):
    users = DATA.setdefault("users", {})
    return users.setdefault(username, {})


def calc_streak(username: str, key: str) -> int:
    """
    오늘 기준으로 '연속으로 안 마신 일수' 계산.
    - 그날에 key가 '마셨다' 로 기록되어 있으면 streak 끊김
    - 기록이 없거나, '마셨다'가 아니면 '안 마신 날'로 간주
    """
    user_data = get_user_data(username)
    today = date.today()
    d = today
    count = 0

    while True:
        ds = d.isoformat()
        data = user_data.get(ds)
        if data and data.get(key) == "마셨다":
            break
        count += 1
        d -= timedelta(days=1)
        if count > 365:
            break
    return count


def count_in_month(username: str, year: int, month: int, key: str) -> int:
    """해당 달에 '마신 날' 개수"""
    user_data = get_user_data(username)
    cnt = 0
    d = date(year, month, 1)
    while d.month == month:
        data = user_data.get(d.isoformat())
        if data and data.get(key) == "마셨다":
            cnt += 1
        d += timedelta(days=1)
    return cnt


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/month")
def api_month():
    """
    /api/month?user=홍길동&year=2025&month=11
    해당 유저의 해당 달 데이터 + 통계 반환
    """
    username = request.args.get("user", "").strip()
    if not username:
        username = "default"

    try:
        year = int(request.args.get("year"))
        month = int(request.args.get("month"))
    except (TypeError, ValueError):
        return jsonify({"error": "year/month 파라미터가 잘못되었습니다."}), 400

    user_data = get_user_data(username)

    # 해당 달의 날짜들만 모아서 반환
    days = {}
    cal = calendar.Calendar(firstweekday=0)
    for week in cal.monthdatescalendar(year, month):
        for d in week:
            if d.month == month:
                ds = d.isoformat()
                if ds in user_data:
                    days[ds] = user_data[ds]

    # 통계
    coffee_streak = calc_streak(username, "coffee")
    alcohol_streak = calc_streak(username, "alcohol")
    coffee_month = count_in_month(username, year, month, "coffee")
    alcohol_month = count_in_month(username, year, month, "alcohol")

    stats = {
        "coffee_streak": coffee_streak,
        "alcohol_streak": alcohol_streak,
        "coffee_month": coffee_month,
        "alcohol_month": alcohol_month,
    }

    return jsonify({"days": days, "stats": stats})


@app.route("/api/update", methods=["POST"])
def api_update():
    """
    { "user": "홍길동", "date": "2025-11-28", "coffee": true/false, "alcohol": true/false }
    """
    body = request.get_json() or {}
    username = (body.get("user") or "").strip()
    if not username:
        username = "default"

    date_str = body.get("date")
    if not date_str:
        return jsonify({"error": "date가 없습니다."}), 400

    try:
        datetime.fromisoformat(date_str)
    except Exception:
        return jsonify({"error": "date 형식이 잘못되었습니다. YYYY-MM-DD"}), 400

    coffee_on = body.get("coffee")
    alcohol_on = body.get("alcohol")

    user_data = get_user_data(username)
    day_data = user_data.get(date_str, {})

    # bool 값에 따라 저장
    if coffee_on is True:
        day_data["coffee"] = "마셨다"
    elif coffee_on is False:
        if "coffee" in day_data:
            del day_data["coffee"]

    if alcohol_on is True:
        day_data["alcohol"] = "마셨다"
    elif alcohol_on is False:
        if "alcohol" in day_data:
            del day_data["alcohol"]

    # 둘 다 없으면 날짜도 삭제
    if not day_data:
        if date_str in user_data:
            del user_data[date_str]
    else:
        user_data[date_str] = day_data

    save_data()

    return jsonify({"ok": True})


if __name__ == "__main__":
    load_data()
    # host="0.0.0.0" 으로 하면 같은 와이파이의 다른 기기에서도 접속 가능
    app.run(debug=True, host="0.0.0.0", port=5000)
