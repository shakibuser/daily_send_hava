#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ارسال خودکار گزارش روزانه‌ی وضعیت آب‌وهوای ایران به کانال تلگرام.

منبع داده: Open-Meteo (رایگان، بدون نیاز به کلید). یک درخواست برای همه‌ی
شهرها ارسال می‌شود، سپس شهرها بر اساس «منطقه» گروه‌بندی و متن گزارش
به‌صورت خودکار ساخته می‌شود.
"""

import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import jdatetime

# ---------- تنظیمات ----------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "@saba_rasanehh")
API_URL = "https://api.open-meteo.com/v1/forecast"
TEHRAN = ZoneInfo("Asia/Tehran")
USE_PERSIAN_DIGITS = False      # True = ۱۴ مهر ۱۴۰۵ ، False = 14 مهر 1405

# آستانه‌ها (قابل تنظیم)
RAIN_MM = 1.0           # بارش حداقل (میلی‌متر) برای «بارش»
GUST_STRONG = 65        # تندباد (km/h) برای «وزش باد شدید»
ORANGE_MM, ORANGE_GUST = 25, 90
YELLOW_MM, YELLOW_GUST = 10, 75

# منطقه ← {شهر: (عرض، طول)}
REGIONS = {
    "شمال غرب": {"تبریز": (38.08, 46.29), "ارومیه": (37.55, 45.07),
                 "اردبیل": (38.25, 48.30), "زنجان": (36.68, 48.48)},
    "سواحل خزر": {"رشت": (37.28, 49.58), "ساری": (36.56, 53.06),
                  "گرگان": (36.84, 54.43)},
    "غرب": {"کرمانشاه": (34.31, 47.07), "سنندج": (35.31, 47.00),
            "همدان": (34.80, 48.51), "خرم‌آباد": (33.49, 48.35),
            "ایلام": (33.64, 46.42)},
    "مرکز": {"تهران": (35.69, 51.39), "قزوین": (36.27, 50.00),
             "اراک": (34.09, 49.69), "قم": (34.64, 50.88),
             "اصفهان": (32.65, 51.67), "یزد": (31.90, 54.37),
             "سمنان": (35.58, 53.39)},
    "شمال شرق": {"مشهد": (36.30, 59.60), "بجنورد": (37.47, 57.33)},
    "شرق": {"بیرجند": (32.87, 59.22)},
    "جنوب شرق": {"کرمان": (30.28, 57.08), "زاهدان": (29.50, 60.86)},
    "جنوب غرب": {"اهواز": (31.32, 48.67), "یاسوج": (30.67, 51.59),
                 "شهرکرد": (32.33, 50.86)},
    "جنوب": {"شیراز": (29.59, 52.58), "بندرعباس": (27.18, 56.27),
             "بوشهر": (28.92, 50.84)},
}
# مناطق خشک که تندباد در آن‌ها معمولاً با گرد و خاک همراه است
DRY_REGIONS = {"مرکز", "شرق", "جنوب شرق", "جنوب غرب", "جنوب"}

THUNDER = {95, 96, 99}
SNOW = {71, 73, 75, 77, 85, 86}

WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]
MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
          "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]

FOOTER = (
    "صبارسانه\nصدای بی صدایان\nبازنشستگان و مالباختگان تامین اجتماعی\n----\n"
    "\u200e🆔 @saba_rasanehh\n\n\u200e🔗 https://t.me/saba_rasanehh"
)

# فهرست مسطح شهرها: (منطقه، شهر، عرض، طول)
CITIES = [(r, c, lat, lon) for r, cs in REGIONS.items() for c, (lat, lon) in cs.items()]


# ---------- ابزارهای کمکی ----------
def num(value) -> str:
    s = str(value)
    return s.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")) if USE_PERSIAN_DIGITS else s


def join_fa(items: list) -> str:
    """['الف','ب','ج'] ← «الف، ب و ج»"""
    if len(items) <= 1:
        return "".join(items)
    return "، ".join(items[:-1]) + " و " + items[-1]


def jalali(date_obj) -> jdatetime.date:
    return jdatetime.date.fromgregorian(date=date_obj)


def wait_until_8() -> None:
    """در اجرای زمان‌بندی‌شده، اگر زودتر از 8 صبح تهران هستیم تا 8 صبر می‌کند."""
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        return
    now = datetime.now(TEHRAN)
    delta = (now.replace(hour=8, minute=0, second=0, microsecond=0) - now).total_seconds()
    if 0 < delta <= 3000:
        print(f"انتظار {int(delta)} ثانیه تا ساعت 8 ...")
        time.sleep(delta)


# ---------- دریافت داده ----------
def fetch_forecast() -> list:
    params = {
        "latitude": ",".join(str(c[2]) for c in CITIES),
        "longitude": ",".join(str(c[3]) for c in CITIES),
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_sum,wind_gusts_10m_max",
        "forecast_days": 4,
        "timezone": "Asia/Tehran",
    }
    for attempt in range(1, 4):
        try:
            resp = requests.get(API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            data = data if isinstance(data, list) else [data]
            if len(data) == len(CITIES):
                return data
            raise ValueError("تعداد پاسخ‌ها با تعداد شهرها برابر نیست")
        except Exception as e:
            print(f"تلاش {attempt} ناموفق: {e}", file=sys.stderr)
            time.sleep(10 * attempt)
    sys.exit("دریافت پیش‌بینی ناموفق بود.")


def analyse_day(data: list, i: int) -> list:
    """وضعیت هر شهر در روز i (۰ = امروز) به‌صورت لیستی از دیکشنری."""
    rows = []
    for (region, city, _, _), d in zip(CITIES, data):
        dd = d["daily"]
        mm = dd["precipitation_sum"][i] or 0
        gust = dd["wind_gusts_10m_max"][i] or 0
        code = dd["weather_code"][i]
        rain = mm >= RAIN_MM
        wind = gust >= GUST_STRONG
        rows.append({
            "region": region, "city": city,
            "tmax": dd["temperature_2m_max"][i], "tmin": dd["temperature_2m_min"][i],
            "rain": rain,
            "snow": rain and code in SNOW,
            "thunder": code in THUNDER,
            "wind": wind,
            "dust": wind and not rain and region in DRY_REGIONS,
            "orange": mm >= ORANGE_MM or gust >= ORANGE_GUST,
            "yellow": mm >= YELLOW_MM or gust >= YELLOW_GUST,
        })
    return rows


def regions_of(rows: list, key: str) -> list:
    """نام مناطقی (به ترتیب تعریف) که حداقل یک شهرشان شرط key را دارد."""
    return [r for r in REGIONS if any(x[key] for x in rows if x["region"] == r)]


# ---------- ساخت متن گزارش ----------
def build_report(data: list) -> str:
    now = datetime.now(TEHRAN)
    today = analyse_day(data, 0)

    # تاریخ شمسی + نام روز هفته
    jd = jalali(now.date())
    date_line = f"{WEEKDAYS[jd.weekday()]} {num(jd.day)} {MONTHS[jd.month - 1]} {num(jd.year)}"

    rain_r, snow_r = regions_of(today, "rain"), regions_of(today, "snow")
    wind_r, dust_r = regions_of(today, "wind"), regions_of(today, "dust")
    orange_r, yellow_r = regions_of(today, "orange"), regions_of(today, "yellow")

    # تیتر
    if orange_r:
        headline = f"✅ شرایط جوی ناپایدار (سطح هشدار نارنجی) در {join_fa(orange_r)}"
    elif yellow_r:
        headline = f"✅ شرایط جوی ناپایدار (سطح هشدار زرد) در {join_fa(yellow_r)}"
    elif rain_r:
        headline = f"✅ بارش در مناطقی از {join_fa(rain_r)}"
    elif wind_r:
        headline = f"✅ وزش باد شدید در {join_fa(wind_r)}"
    else:
        headline = "✅ جوی آرام و پایدار در بیشتر مناطق کشور"

    bullets = []

    # امروز
    if rain_r:
        kind = "باران و برف" if snow_r else "باران"
        extra = "، گاهی رگبار و رعد و برق" if any(x["thunder"] for x in today) else ""
        bullets.append(f"🔸امروز در مناطقی از {join_fa(rain_r)} ابرناکی و بارش {kind}{extra} پیش‌بینی می‌شود.")
    else:
        bullets.append("🔸امروز در بیشتر مناطق کشور جوی آرام و پایدار پیش‌بینی می‌شود.")

    if wind_r:
        txt = f"🔸همچنین در {join_fa(wind_r)} وزش باد شدید"
        if dust_r:
            txt += f" و در {join_fa(dust_r)} احتمال خیزش گرد و خاک و کاهش کیفیت هوا"
        bullets.append(txt + " دور از انتظار نیست.")

    if orange_r or yellow_r:
        level = "نارنجی" if orange_r else "زرد"
        bullets.append(f"🔸با توجه به شدت پیش‌بینی‌شده، برای {join_fa(orange_r or yellow_r)} احتیاط‌های لازم توصیه می‌شود (سطح {level}).")

    # سه روز آینده
    outlook = []
    for i, label in ((1, "فردا"), (2, None), (3, None)):
        rows = analyse_day(data, i)
        r, w = regions_of(rows, "rain"), regions_of(rows, "wind")
        if not (r or w):
            continue
        day_name = WEEKDAYS[jalali(now.date() + timedelta(days=i)).weekday()]
        parts = []
        if r:
            parts.append(f"بارش در {join_fa(r)}")
        if w:
            parts.append(f"وزش باد شدید در {join_fa(w)}")
        outlook.append(f"🔸{label or day_name}{' (' + day_name + ')' if label else ''}: " + "؛ ".join(parts) + ".")
    bullets += outlook or ["🔸در سه روز آینده نیز در بیشتر مناطق کشور جوی پایدار پیش‌بینی می‌شود."]

    # دما
    hot = max(today, key=lambda x: x["tmax"])
    cold = min(today, key=lambda x: x["tmin"])
    tehran = next(x for x in today if x["city"] == "تهران")
    bullets.append(
        f"🔸دمای تهران: {num(round(tehran['tmin']))} تا {num(round(tehran['tmax']))} درجه | "
        f"گرم‌ترین: {hot['city']} ({num(round(hot['tmax']))}°) | "
        f"سردترین: {cold['city']} ({num(round(cold['tmin']))}°)"
    )

    return (f"{headline}\n{date_line}\n\nپیش‌بینی وضع هوا :\n\n"
            + "\n\n".join(bullets) + "\n\n\n" + FOOTER)


# ---------- ارسال ----------
def send_to_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True}
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, data=payload, timeout=30)
            if resp.ok and resp.json().get("ok"):
                print("گزارش با موفقیت ارسال شد.")
                return
            print(f"خطای تلگرام: {resp.text}", file=sys.stderr)
        except Exception as e:
            print(f"تلاش {attempt} ناموفق: {e}", file=sys.stderr)
        time.sleep(10 * attempt)
    sys.exit(1)


def main() -> None:
    if "--dry-run" in sys.argv:          # فقط نمایش متن، بدون ارسال
        print(build_report(fetch_forecast()))
        return
    if not TELEGRAM_BOT_TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN تنظیم نشده است.")
    wait_until_8()
    send_to_telegram(build_report(fetch_forecast()))


if __name__ == "__main__":
    main()
