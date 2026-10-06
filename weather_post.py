#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ارسال خودکار گزارش روزانه‌ی وضعیت آب‌وهوای ایران به کانال تلگرام.

منبع داده: Open-Meteo (رایگان، بدون نیاز به کلید). یک درخواست برای همه‌ی
شهرها ارسال می‌شود، سپس شهرها بر اساس «منطقه» گروه‌بندی و متن گزارش
به‌صورت خودکار ساخته می‌شود.
"""

import os
import random
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
USE_PERSIAN_DIGITS = True       # True = ۱۴ مهر ۱۴۰۵ ، False = 14 مهر 1405

# آستانه‌ها (قابل تنظیم)
RAIN_MM = 1.0           # بارش حداقل (میلی‌متر) برای «بارش»
GUST_STRONG = 65        # تندباد (km/h) برای «وزش باد شدید»
ORANGE_MM, ORANGE_GUST = 25, 90
YELLOW_MM, YELLOW_GUST = 10, 75

# استان ← (مرکز استان، عرض، طول)
PROVINCES = {
    "آذربایجان شرقی": ("تبریز", 38.08, 46.29), "آذربایجان غربی": ("ارومیه", 37.55, 45.07),
    "اردبیل": ("اردبیل", 38.25, 48.30), "زنجان": ("زنجان", 36.68, 48.48),
    "گیلان": ("رشت", 37.28, 49.58), "مازندران": ("ساری", 36.56, 53.06),
    "گلستان": ("گرگان", 36.84, 54.43),
    "کردستان": ("سنندج", 35.31, 47.00), "کرمانشاه": ("کرمانشاه", 34.31, 47.07),
    "همدان": ("همدان", 34.80, 48.51), "لرستان": ("خرم‌آباد", 33.49, 48.35),
    "ایلام": ("ایلام", 33.64, 46.42),
    "مرکزی": ("اراک", 34.09, 49.69), "قزوین": ("قزوین", 36.27, 50.00),
    "البرز": ("کرج", 35.84, 50.99), "تهران": ("تهران", 35.69, 51.39),
    "قم": ("قم", 34.64, 50.88), "سمنان": ("سمنان", 35.58, 53.39),
    "اصفهان": ("اصفهان", 32.65, 51.67), "یزد": ("یزد", 31.90, 54.37),
    "خراسان رضوی": ("مشهد", 36.30, 59.60), "خراسان شمالی": ("بجنورد", 37.47, 57.33),
    "خراسان جنوبی": ("بیرجند", 32.87, 59.22),
    "کرمان": ("کرمان", 30.28, 57.08), "سیستان و بلوچستان": ("زاهدان", 29.50, 60.86),
    "خوزستان": ("اهواز", 31.32, 48.67), "چهارمحال و بختیاری": ("شهرکرد", 32.33, 50.86),
    "کهگیلویه و بویراحمد": ("یاسوج", 30.67, 51.59),
    "فارس": ("شیراز", 29.59, 52.58), "بوشهر": ("بوشهر", 28.92, 50.84),
    "هرمزگان": ("بندرعباس", 27.18, 56.27),
}

# منطقه ← استان‌ها (اگر همه‌ی استان‌های یک منطقه درگیر باشند، فقط نام منطقه می‌آید)
MACROS = {
    "شمال غرب": ["آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "زنجان"],
    "سواحل خزر": ["گیلان", "مازندران", "گلستان"],
    "غرب": ["کردستان", "کرمانشاه", "همدان", "لرستان", "ایلام"],
    "مرکز کشور": ["مرکزی", "قزوین", "البرز", "تهران", "قم", "سمنان", "اصفهان", "یزد"],
    "شمال شرق": ["خراسان رضوی", "خراسان شمالی"],
    "شرق": ["خراسان جنوبی"],
    "جنوب شرق": ["کرمان", "سیستان و بلوچستان"],
    "جنوب غرب": ["خوزستان", "چهارمحال و بختیاری", "کهگیلویه و بویراحمد"],
    "جنوب": ["فارس", "بوشهر", "هرمزگان"],
}
# مناطق خشک که تندباد در آن‌ها معمولاً با گرد و خاک همراه است
DRY_MACROS = {"مرکز کشور", "شرق", "جنوب شرق", "جنوب غرب", "جنوب"}
MACRO_OF = {p: m for m, ps in MACROS.items() for p in ps}
DRY_PROVINCES = {p for p in PROVINCES if MACRO_OF[p] in DRY_MACROS}

THUNDER = {95, 96, 99}
SNOW = {71, 73, 75, 77, 85, 86}

WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]
MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
          "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]

FOOTER = (
    "صبارسانه\nصدای بی صدایان\nبازنشستگان و مالباختگان تامین اجتماعی\n----\n"
    "\u200e🆔 @saba_rasanehh\n\n\u200e🔗 https://t.me/saba_rasanehh"
)

# فهرست مسطح استان‌ها: (استان، مرکز، عرض، طول)
CITIES = [(p, c, la, lo) for p, (c, la, lo) in PROVINCES.items()]


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


def analyse_day(data: list, i: int) -> dict:
    """وضعیت هر استان در روز i (۰ = امروز) ← {استان: دیکشنری}."""
    out = {}
    for (prov, city, _, _), d in zip(CITIES, data):
        dd = d["daily"]
        mm = dd["precipitation_sum"][i] or 0
        gust = dd["wind_gusts_10m_max"][i] or 0
        code = dd["weather_code"][i]
        rain = mm >= RAIN_MM
        wind = gust >= GUST_STRONG
        out[prov] = {
            "city": city, "mm": mm, "gust": gust,
            "tmax": dd["temperature_2m_max"][i], "tmin": dd["temperature_2m_min"][i],
            "rain": rain,
            "snow": rain and code in SNOW,
            "storm": rain and (code in THUNDER or mm >= 10),   # رگبار / رعد و برق
            "wind": wind,
            "dust": wind and not rain and prov in DRY_PROVINCES,
            "orange": mm >= ORANGE_MM or gust >= ORANGE_GUST,
            "yellow": mm >= YELLOW_MM or gust >= YELLOW_GUST,
        }
    return out


def pick(day: dict, key: str) -> set:
    return {p for p, x in day.items() if x[key]}


def label(provs: set) -> str:
    """نام استان‌ها؛ اگر همه‌ی استان‌های یک منطقه باشند، نام منطقه می‌آید."""
    parts = []
    for macro, plist in MACROS.items():
        hit = [p for p in plist if p in provs]
        if len(plist) > 1 and len(hit) == len(plist):
            parts.append(macro)
        else:
            parts.extend(hit)
    return join_fa(parts)


def macro_label(provs: set) -> str:
    """فقط نام مناطقی که حداقل یک استانشان در مجموعه است (برای تیتر)."""
    return join_fa([m for m, plist in MACROS.items() if any(p in provs for p in plist)])


# ---------- ساخت متن گزارش ----------
# جمله‌های آغازین (هر بار یکی تصادفی از دسته‌ی مناسب انتخاب می‌شود)
OPENERS = {
    "alert": ["آسمان امروز کمی بی‌قرار است؛ با احتیاط و آمادگی پیش بروید.",
              "طبیعت امروز در بخش‌هایی از کشور تندخو شده؛ مراقب خودتان و عزیزانتان باشید.",
              "امروز آسمان حرف‌های زیادی برای گفتن دارد؛ کمی بیشتر مراقب باشید."],
    "rain": ["امروز آسمان بخش‌هایی از ایران بوی باران می‌دهد.",
             "ابرها امروز به دیدار بخش‌هایی از کشور می‌روند و باران هدیه می‌برند.",
             "باران امروز به خانه‌ی بخش‌هایی از ایران سر می‌زند."],
    "wind": ["امروز باد سرِ شوخی ندارد؛ هرچه سبک است محکم ببندید.",
             "امروز باد در بخش‌هایی از کشور بی‌تابی می‌کند."],
    "calm": ["آسمان امروز آرام است و هوا پایدار؛ روز خوبی برای قدم‌زدن.",
             "امروز هوا مهربان است و آسمان بی‌ادعا؛ از روزتان لذت ببرید."],
}


def build_report(data: list) -> str:
    now = datetime.now(TEHRAN)
    today = analyse_day(data, 0)

    # تاریخ شمسی + نام روز هفته
    jd = jalali(now.date())
    date_line = f"{WEEKDAYS[jd.weekday()]} {num(jd.day)} {MONTHS[jd.month - 1]} {num(jd.year)}"

    rain, snow, storm = pick(today, "rain"), pick(today, "snow"), pick(today, "storm")
    wind, dust = pick(today, "wind"), pick(today, "dust")
    orange, yellow = pick(today, "orange"), pick(today, "yellow")
    alert = orange or yellow
    level = "نارنجی" if orange else "زرد"

    # تیتر و جمله‌ی آغازین
    if alert:
        headline, mood = f"⚠️ ناپایداری جوی (سطح {level}) در {macro_label(alert)} کشور", "alert"
    elif rain:
        headline, mood = f"🌧 بارش در مناطقی از {macro_label(rain)} کشور", "rain"
    elif wind:
        headline, mood = f"💨 وزش باد شدید در {macro_label(wind)} کشور", "wind"
    else:
        headline, mood = "☀️ آسمان آرام و هوای پایدار در بیشتر مناطق کشور", "calm"
    opener = random.choice(OPENERS[mood])

    blocks = []

    # بارش امروز (رگبار و رعد و برق / باران / برف)
    heavy, light = storm - snow, rain - storm - snow
    if heavy:
        blocks.append(f"⛈ آسمان {label(heavy)} امروز ابری و ناآرام است؛ رگبار، رعد و برق و وزش باد مهمان این مناطق خواهد بود.")
    if light:
        blocks.append(f"🌧 در {label(light)} هم ابر و بارانِ ملایم‌تر در راه است." if heavy
                      else f"🌧 امروز در {label(light)} آسمان ابری است و باران می‌بارد.")
    if snow:
        blocks.append(f"❄️ در ارتفاعات {label(snow)} برف می‌نشیند.")
    if not rain:
        blocks.append("☀️ امروز در بیشتر مناطق کشور خبری از بارش قابل‌توجه نیست.")

    # باد و گرد و خاک
    if wind:
        top = num(round(max(today[p]["gust"] for p in wind)))
        blocks.append(f"💨 باد در {label(wind)} تند می‌وزد (تندباد تا حدود {top} کیلومتر بر ساعت).")
    if dust:
        blocks.append(f"🌫 در {label(dust)} احتمال خیزش گرد و خاک و کاهش کیفیت هوا وجود دارد؛ افراد حساس و بیماران تنفسی مراقب باشند.")

    # بیشترین بارش
    wet = sorted(rain, key=lambda p: -today[p]["mm"])[:3]
    if wet:
        items = "، ".join(f"{today[p]['city']} ({num(round(today[p]['mm']))} میلی‌متر)" for p in wet)
        blocks.append(f"💧 پربارش‌ترین شهرها: {items}")

    # هشدار
    if alert:
        blocks.append(f"⚠️ بر پایه‌ی شدت بارش و باد پیش‌بینی‌شده، برای {label(alert)} سطح هشدار {level} در نظر گرفته می‌شود؛ در تردد و فعالیت‌های فضای باز احتیاط کنید.")

    # روزهای آینده
    outlook = []
    for i in (1, 2, 3):
        day = analyse_day(data, i)
        r, w = pick(day, "rain"), pick(day, "wind")
        if not (r or w):
            continue
        name = WEEKDAYS[jalali(now.date() + timedelta(days=i)).weekday()]
        parts = ([f"🌧 بارش در {label(r)}"] if r else []) + ([f"💨 باد شدید در {label(w)}"] if w else [])
        outlook.append(f"🔹{'فردا (' + name + ')' if i == 1 else name}: " + "؛ ".join(parts))
    blocks.append("📅 نگاهی به روزهای پیش رو:\n" + "\n".join(outlook) if outlook
                  else "📅 در سه روز آینده نیز در بیشتر مناطق کشور هوا پایدار و آرام می‌ماند.")

    # دما
    hot = max(today.values(), key=lambda x: x["tmax"])
    cold = min(today.values(), key=lambda x: x["tmin"])
    t = today["تهران"]
    blocks.append(
        f"🌡 تهران: {num(round(t['tmin']))} تا {num(round(t['tmax']))} درجه\n"
        f"🔥 گرم‌ترین: {hot['city']} ({num(round(hot['tmax']))}°)   🥶 سردترین: {cold['city']} ({num(round(cold['tmin']))}°)"
    )

    # توصیه‌ی پایانی
    if alert:
        tip = "🧣 سالمندان و بیماران عزیز: تا حد امکان از تردد غیرضروری بپرهیزید و گرم بمانید."
    elif rain:
        tip = "☔ چتر فراموش نشود و هنگام رانندگی احتیاط کنید."
    elif wind:
        tip = "🚗 هنگام رانندگی و پارک خودرو مراقب باد باشید."
    elif hot["tmax"] >= 38:
        tip = "🥤 در ساعات گرم روز آب بنوشید و کمتر زیر آفتاب بمانید."
    else:
        tip = "🌿 روزتان آرام و دلنشین باد."

    body = "\n\n".join([opener] + blocks + [tip])
    return f"{headline}\n📆 {date_line}\n\n{body}\n\n\n{FOOTER}"


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
