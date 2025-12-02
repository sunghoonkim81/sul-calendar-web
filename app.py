from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import datetime

app = Flask(__name__)

# 기존 sqlite 파일 계속 사용 (서버/로컬 동일 경로)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///sul_calendar.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class DailyRecord(db.Model):
    """사용자 하루 기록 (커피/술 여부 + 양)"""
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(50), index=True)
    date = db.Column(db.String(20), index=True)  # "YYYY-MM-DD"

    coffee = db.Column(db.String(10), default="안마셨다")   # "마셨다"/"안마셨다"
    alcohol = db.Column(db.String(10), default="안마셨다")  # "마셨다"/"안마셨다"

    soju = db.Column(db.Integer, default=0)       # 병
    beer = db.Column(db.Integer, default=0)       # 잔
    whisky = db.Column(db.Integer, default=0)     # 잔
    wine = db.Column(db.Integer, default=0)       # 잔
    makgeolli = db.Column(db.Integer, default=0)  # 잔


with app.app_context():
    db.create_all()


@app.route("/")
def index():
    return render_template("index.html")


def get_streak(records, field: str) -> int:
    """
    직전 기록부터 거꾸로 보면서 연속으로 '안마셨다'인 일 수 계산
    records 는 날짜 오름차순 정렬된 리스트라고 가정
    """
    streak = 0
    for r in reversed(records):
        if getattr(r, field) == "안마셨다":
            streak += 1
        else:
            break
    return streak


@app.route("/api/month")
def api_month():
    user = request.args.get("user", "default")
    year = int(request.args.get("year"))
    month = int(request.args.get("month"))

    # 이번 달 범위
    start = datetime.date(year, month, 1)
    if month == 12:
        end = datetime.date(year + 1, 1, 1)
    else:
        end = datetime.date(year, month + 1, 1)

    # 해당 유저의 이번 달 기록
    records = DailyRecord.query.filter(
        DailyRecord.user == user,
        DailyRecord.date >= str(start),
        DailyRecord.date < str(end),
    ).all()

    days = {}
    for r in records:
        days[r.date] = {
            "coffee": r.coffee,
            "alcohol": r.alcohol,
            "soju": r.soju,
            "beer": r.beer,
            "whisky": r.whisky,
            "wine": r.wine,
            "makgeolli": r.makgeolli,
        }

    # ---- streak 계산 (오늘 기준) ----
    today = datetime.date.today()
    month_start = datetime.date(today.year, today.month, 1)
    month_records = (
        DailyRecord.query.filter(
            DailyRecord.user == user,
            DailyRecord.date >= str(month_start),
            DailyRecord.date <= str(today),
        )
        .order_by(DailyRecord.date)
        .all()
    )

    coffee_streak = get_streak(month_records, "coffee")
    alcohol_streak = get_streak(month_records, "alcohol")

    # ---- 이번 달 커피/술 마신 '날 수' ----
    coffee_month = DailyRecord.query.filter(
        DailyRecord.user == user,
        DailyRecord.date >= str(start),
        DailyRecord.date < str(end),
        DailyRecord.coffee == "마셨다",
    ).count()

    alcohol_month = DailyRecord.query.filter(
        DailyRecord.user == user,
        DailyRecord.date >= str(start),
        DailyRecord.date < str(end),
        DailyRecord.alcohol == "마셨다",
    ).count()

    # ---- 이번 달 전체 사용자 데이터 ----
    all_users_data = DailyRecord.query.filter(
        DailyRecord.date >= str(start),
        DailyRecord.date < str(end),
    ).all()

    user_totals: dict[str, dict] = {}

    for r in all_users_data:
        if r.user not in user_totals:
            user_totals[r.user] = {
                "coffee_days": 0,
                "alcohol_days": 0,
                "soju": 0,
                "beer": 0,
                "whisky": 0,
                "wine": 0,
                "makgeolli": 0,
            }

        if r.coffee == "마셨다":
            user_totals[r.user]["coffee_days"] += 1
        if r.alcohol == "마셨다":
            user_totals[r.user]["alcohol_days"] += 1

        user_totals[r.user]["soju"] += r.soju
        user_totals[r.user]["beer"] += r.beer
        user_totals[r.user]["whisky"] += r.whisky
        user_totals[r.user]["wine"] += r.wine
        user_totals[r.user]["makgeolli"] += r.makgeolli

    # ---- 순위 만들기 ----
    def make_rank(key: str, hide_zero: bool = True):
        arr = []
        for u, v in user_totals.items():
            # 1) default 유저는 순위에서 제외
            if u == "default":
                continue
            val = v[key]
            # 2) 0인 사용자는 숨기기 (원하면 False로 바꿀 수 있음)
            if hide_zero and val <= 0:
                continue
            arr.append((u, val))
        arr.sort(key=lambda x: x[1], reverse=True)
        return arr

    coffee_rank = make_rank("coffee_days")
    alcohol_rank = make_rank("alcohol_days")

    soju_rank = make_rank("soju")
    beer_rank = make_rank("beer")
    whisky_rank = make_rank("whisky")
    wine_rank = make_rank("wine")
    makgeolli_rank = make_rank("makgeolli")

    # 현재 사용자 이번 달 술 양 합계 (없으면 0)
    current_user_totals = user_totals.get(user, {
        "soju": 0,
        "beer": 0,
        "whisky": 0,
        "wine": 0,
        "makgeolli": 0,
    })

    stats = {
        "coffee_streak": coffee_streak,
        "alcohol_streak": alcohol_streak,
        "coffee_month": coffee_month,
        "alcohol_month": alcohol_month,

        # 현재 사용자 기준 합계
        "soju_total": current_user_totals["soju"],
        "beer_total": current_user_totals["beer"],
        "whisky_total": current_user_totals["whisky"],
        "wine_total": current_user_totals["wine"],
        "makgeolli_total": current_user_totals["makgeolli"],

        # 순위 리스트
        "coffee_rank": coffee_rank,
        "alcohol_rank": alcohol_rank,
        "soju_rank": soju_rank,
        "beer_rank": beer_rank,
        "whisky_rank": whisky_rank,
        "wine_rank": wine_rank,
        "makgeolli_rank": makgeolli_rank,
    }

    return jsonify({"days": days, "stats": stats})


@app.route("/api/update", methods=["POST"])
def api_update():
    data = request.json or {}
    user = data.get("user", "default")
    date = data.get("date")
    if not date:
        return jsonify({"error": "date가 없습니다."}), 400

    record = DailyRecord.query.filter_by(user=user, date=date).first()
    if not record:
        record = DailyRecord(user=user, date=date)
        db.session.add(record)

    # 커피/술 여부
    if "coffee" in data:
        record.coffee = "마셨다" if data["coffee"] else "안마셨다"

    if "alcohol" in data:
        record.alcohol = "마셨다" if data["alcohol"] else "안마셨다"

    # 음수/잘못된 값 방지용 함수
    def _to_int(x):
        try:
            v = int(x)
            return max(0, v)
        except (TypeError, ValueError):
            return 0

    if "soju" in data:
        record.soju = _to_int(data["soju"])
    if "beer" in data:
        record.beer = _to_int(data["beer"])
    if "whisky" in data:
        record.whisky = _to_int(data["whisky"])
    if "wine" in data:
        record.wine = _to_int(data["wine"])
    if "makgeolli" in data:
        record.makgeolli = _to_int(data["makgeolli"])

    # 만약 모든 값이 0이고, 커피/술도 안마셨다 → 기록 삭제해서 DB 정리
    if (
        record.coffee == "안마셨다"
        and record.alcohol == "안마셨다"
        and record.soju == 0
        and record.beer == 0
        and record.whisky == 0
        and record.wine == 0
        and record.makgeolli == 0
    ):
        db.session.delete(record)

    db.session.commit()
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=True)
