from flask import Flask, render_template, request, jsonify
from datetime import date, datetime, timedelta
import os

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, Date,
    ForeignKey, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

app = Flask(__name__)

# ---------------- DB 설정 ---------------- #

# PythonAnywhere에서는 별도 DATABASE_URL이 없으니 sqlite 사용
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///sul_calendar.db"

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, index=True)

    entries = relationship("Entry", back_populates="user", cascade="all, delete-orphan")
    drink_amounts = relationship("DrinkAmount", back_populates="user", cascade="all, delete-orphan")


class Entry(Base):
    """
    하루에 한 줄 (커피/술 여부만)
    """
    __tablename__ = "entries"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    date = Column(Date, index=True)
    coffee = Column(Boolean, default=False)
    alcohol = Column(Boolean, default=False)

    user = relationship("User", back_populates="entries")


class DrinkAmount(Base):
    """
    술 종류별 양 (소주/맥주/양주/와인)
    """
    __tablename__ = "drink_amounts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    date = Column(Date, index=True)

    soju_bottle = Column(Integer, default=0)   # 병
    beer_glass = Column(Integer, default=0)    # 잔
    whisky_glass = Column(Integer, default=0)  # 잔
    wine_glass = Column(Integer, default=0)    # 잔

    user = relationship("User", back_populates="drink_amounts")


# 테이블 생성 (기존 테이블은 유지, 새로운 테이블만 추가됨)
Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()


# ---------------- 유틸 ---------------- #

def get_or_create_user(session, name: str) -> User:
    user = session.query(User).filter_by(name=name).first()
    if not user:
        user = User(name=name)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def calc_streak_from_entries(entries, key: str) -> int:
    """
    Entry 리스트 기준, 오늘부터 연속으로 안 마신 일수 계산.
    entries는 해당 유저의 모든 기록.
    """
    entry_map = {e.date: e for e in entries}
    today = date.today()
    d = today
    cnt = 0

    while True:
        e = entry_map.get(d)
        drank = False
        if e:
            if key == "coffee" and e.coffee:
                drank = True
            if key == "alcohol" and e.alcohol:
                drank = True
        if drank:
            break
        cnt += 1
        d -= timedelta(days=1)
        if cnt > 365:  # 안전장치
            break
    return cnt


def count_in_month_from_entries(entries, year: int, month: int, key: str) -> int:
    cnt = 0
    for e in entries:
        if e.date.year == year and e.date.month == month:
            if key == "coffee" and e.coffee:
                cnt += 1
            if key == "alcohol" and e.alcohol:
                cnt += 1
    return cnt


def calc_rankings(session, year: int, month: int):
    """전체 사용자 기준, 이번 달 커피/술 많이 마신 '날 수' 순위."""
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)

    # 커피 순위
    coffee_query = (
        session.query(User.name, func.count(Entry.id).label("cnt"))
        .join(Entry, Entry.user_id == User.id)
        .filter(Entry.date >= first, Entry.date <= last, Entry.coffee.is_(True))
        .group_by(User.name)
        .order_by(func.count(Entry.id).desc())
    )
    coffee_rank = [(row.name, row.cnt) for row in coffee_query.limit(10)]

    # 술 순위
    alcohol_query = (
        session.query(User.name, func.count(Entry.id).label("cnt"))
        .join(Entry, Entry.user_id == User.id)
        .filter(Entry.date >= first, Entry.date <= last, Entry.alcohol.is_(True))
        .group_by(User.name)
        .order_by(func.count(Entry.id).desc())
    )
    alcohol_rank = [(row.name, row.cnt) for row in alcohol_query.limit(10)]

    return coffee_rank, alcohol_rank


# ---------------- 라우트 ---------------- #

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/month")
def api_month():
    """
    /api/month?user=홍길동&year=2025&month=11
    """
    username = (request.args.get("user") or "").strip() or "default"
    try:
        year = int(request.args.get("year"))
        month = int(request.args.get("month"))
    except (TypeError, ValueError):
        return jsonify({"error": "year/month 파라미터가 잘못되었습니다."}), 400

    session = get_session()
    try:
        user = get_or_create_user(session, username)

        # 이 유저의 모든 Entry
        user_entries = (
            session.query(Entry)
            .filter(Entry.user_id == user.id)
            .all()
        )

        # 이 유저의 이번 달 술 양
        first = date(year, month, 1)
        if month == 12:
            last = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last = date(year, month + 1, 1) - timedelta(days=1)

        drink_entries = (
            session.query(DrinkAmount)
            .filter(
                DrinkAmount.user_id == user.id,
                DrinkAmount.date >= first,
                DrinkAmount.date <= last,
            )
            .all()
        )
        drink_map = {e.date: e for e in drink_entries}

        # days 딕셔너리 구성 (하루씩 돌면서 Entry + DrinkAmount 합치기)
        days_dict = {}
        d = first
        while d.month == month:
            ds = d.isoformat()
            day_data = {}

            entry = next((e for e in user_entries if e.date == d), None)
            if entry:
                if entry.coffee:
                    day_data["coffee"] = "마셨다"
                if entry.alcohol:
                    day_data["alcohol"] = "마셨다"

            drink = drink_map.get(d)
            if drink:
                if drink.soju_bottle:
                    day_data["soju"] = drink.soju_bottle
                if drink.beer_glass:
                    day_data["beer"] = drink.beer_glass
                if drink.whisky_glass:
                    day_data["whisky"] = drink.whisky_glass
                if drink.wine_glass:
                    day_data["wine"] = drink.wine_glass

            if day_data:
                days_dict[ds] = day_data

            d += timedelta(days=1)

        # 개인 통계
        coffee_streak = calc_streak_from_entries(user_entries, "coffee")
        alcohol_streak = calc_streak_from_entries(user_entries, "alcohol")
        coffee_month = count_in_month_from_entries(user_entries, year, month, "coffee")
        alcohol_month = count_in_month_from_entries(user_entries, year, month, "alcohol")

        # 전체 사용자 순위
        coffee_rank, alcohol_rank = calc_rankings(session, year, month)

        # 술 종류별 이번 달 합계
        soju_total = sum(e.soju_bottle or 0 for e in drink_entries)
        beer_total = sum(e.beer_glass or 0 for e in drink_entries)
        whisky_total = sum(e.whisky_glass or 0 for e in drink_entries)
        wine_total = sum(e.wine_glass or 0 for e in drink_entries)

        stats = {
            "coffee_streak": coffee_streak,
            "alcohol_streak": alcohol_streak,
            "coffee_month": coffee_month,
            "alcohol_month": alcohol_month,
            "coffee_rank": coffee_rank,
            "alcohol_rank": alcohol_rank,
            "soju_total": soju_total,
            "beer_total": beer_total,
            "whisky_total": whisky_total,
            "wine_total": wine_total,
        }

        return jsonify({"days": days_dict, "stats": stats})
    finally:
        session.close()


@app.route("/api/update", methods=["POST"])
def api_update():
    """
    { 
      "user": "홍길동",
      "date": "2025-11-28",
      "coffee": true/false (옵션),
      "alcohol": true/false (옵션),
      "soju": 1,
      "beer": 2,
      "whisky": 0,
      "wine": 0
    }
    """
    body = request.get_json() or {}
    username = (body.get("user") or "").strip() or "default"
    date_str = body.get("date")
    if not date_str:
        return jsonify({"error": "date가 없습니다."}), 400

    try:
        d = datetime.fromisoformat(date_str).date()
    except Exception:
        return jsonify({"error": "date 형식이 잘못되었습니다."}), 400

    coffee_on = body.get("coffee")  # True/False/None
    alcohol_on = body.get("alcohol")

    soju = body.get("soju")
    beer = body.get("beer")
    whisky = body.get("whisky")
    wine = body.get("wine")

    session = get_session()
    try:
        user = get_or_create_user(session, username)

        # ----- Entry(커피/술 여부) 처리 -----
        entry = (
            session.query(Entry)
            .filter(Entry.user_id == user.id, Entry.date == d)
            .first()
        )
        if not entry:
            entry = Entry(user_id=user.id, date=d, coffee=False, alcohol=False)
            session.add(entry)

        if coffee_on is True:
            entry.coffee = True
        elif coffee_on is False:
            entry.coffee = False

        # 술 여부는 두 가지 경로 중 하나로 정해짐:
        # 1) alcohol 필드가 직접 전달된 경우
        # 2) 술 양(soju/beer/whisky/wine) 합계로 자동 판단
        amounts_given = any(v is not None for v in [soju, beer, whisky, wine])

        # 먼저 양을 숫자로 정리
        def _to_int(x):
            try:
                return int(x)
            except (TypeError, ValueError):
                return 0

        soju_i = _to_int(soju) if soju is not None else None
        beer_i = _to_int(beer) if beer is not None else None
        whisky_i = _to_int(whisky) if whisky is not None else None
        wine_i = _to_int(wine) if wine is not None else None

        # ----- DrinkAmount 처리 -----
        drink = (
            session.query(DrinkAmount)
            .filter(DrinkAmount.user_id == user.id, DrinkAmount.date == d)
            .first()
        )

        if amounts_given:
            if not drink:
                drink = DrinkAmount(
                    user_id=user.id,
                    date=d,
                    soju_bottle=0,
                    beer_glass=0,
                    whisky_glass=0,
                    wine_glass=0,
                )
                session.add(drink)

            if soju_i is not None:
                drink.soju_bottle = max(0, soju_i)
            if beer_i is not None:
                drink.beer_glass = max(0, beer_i)
            if whisky_i is not None:
                drink.whisky_glass = max(0, whisky_i)
            if wine_i is not None:
                drink.wine_glass = max(0, wine_i)

            total_amount = (
                (drink.soju_bottle or 0)
                + (drink.beer_glass or 0)
                + (drink.whisky_glass or 0)
                + (drink.wine_glass or 0)
            )

            # 양 합계가 0이면 DrinkAmount 삭제
            if total_amount == 0:
                session.delete(drink)
                drink = None

            # alcohol_on이 명시되지 않았다면, 양 합계 기준으로 자동 설정
            if alcohol_on is None:
                alcohol_on = total_amount > 0

        # alcohol 필드 최종 반영
        if alcohol_on is True:
            entry.alcohol = True
        elif alcohol_on is False:
            entry.alcohol = False

        # 커피/술 둘 다 False이고 술 양도 없으면 Entry 삭제
        has_drink = False
        if drink:
            if (drink.soju_bottle or 0) or (drink.beer_glass or 0) \
               or (drink.whisky_glass or 0) or (drink.wine_glass or 0):
                has_drink = True

        if not entry.coffee and not entry.alcohol and not has_drink:
            session.delete(entry)

        session.commit()
        return jsonify({"ok": True})
    finally:
        session.close()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
