"""
Vantage Daily Briefing — GitHub Actions script
Calls Anthropic API and sends result to Telegram.
Runs daily at 8:30am SGT without any laptop or browser needed.
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta

# ── Config from GitHub Secrets ──
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT = os.environ["TELEGRAM_CHAT_ID"]

# ── SGT timestamp ──
SGT = timezone(timedelta(hours=8))
today = datetime.now(SGT).strftime("%A, %d %B %Y")
weekday = datetime.now(SGT).weekday()  # 0=Mon, 6=Sun

# ── Choose briefing type based on day ──
is_weekend = weekday >= 5
briefing_type = "weekly_review" if weekday == 0 else "daily" if not is_weekend else "weekend_watch"

# ── Prompt by type ──
PROMPTS = {
    "daily": f"""You are a personal investment advisor generating a daily morning briefing. Date: {today}.

Investor profile: Value investing, US (NYSE/NASDAQ) and SGX/SEA markets, dual horizon — long-term 2–5 years and short-term under 3 months.

Generate a concise daily briefing with these four sections:

🔴 URGENT (act today)
Any positions likely near stop levels or with imminent catalyst. If none, say so in one line.

📋 PORTFOLIO WATCH (act this week)
1–2 positions most likely to need action based on current macro conditions.

📡 MARKET SIGNAL
One macro signal relevant to US and SGX value stocks today. One sentence.

✅ TODAY'S 3 ACTIONS
Exactly 3 numbered, concrete actions. Format: "1. [TICKER or theme] — [what to do] at [price or condition]"

Keep total response under 300 words. Direct, no preamble.""",

    "weekly_review": f"""You are a personal investment advisor generating a Monday weekly review. Date: {today}.

Investor profile: Value investing, US (NYSE/NASDAQ) and SGX/SEA markets, dual horizon — long-term 2–5 years and short-term under 3 months.

Monday briefing format:

📊 LAST WEEK RECAP
Key market moves relevant to a US + SGX value investor. 2 sentences max.

🗓 THIS WEEK'S CALENDAR
Top 2–3 market events this week (earnings, Fed/MAS, economic data) that could move your positions.

🔭 WATCHLIST CHECK
For value investors: are current valuations in US tech / Singapore banks / REITs offering better or worse entry points vs 2 weeks ago?

✅ THIS WEEK'S 3 PRIORITIES
3 concrete actions for the week. Format: "1. [action] — [reasoning in one sentence]"

Under 350 words. Direct.""",

    "weekend_watch": f"""You are a personal investment advisor generating a Saturday portfolio check. Date: {today}.

Investor profile: Value investing, US (NYSE/NASDAQ) and SGX/SEA markets.

Weekend check format:

📈 WEEK IN REVIEW
US and SGX market performance this week. 2 sentences.

⚠ RISK RADAR
One risk that could affect value portfolios next week.

📋 STOP CHECK REMINDER
Reminder to review: are any short-term position stops at risk of being triggered next week?

✅ WEEKEND ACTION
One thing to review or research this weekend to be ready for Monday open.

Under 200 words."""
}

def call_anthropic(prompt):
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"]

def send_telegram(text):
    # Telegram has a 4096 char limit — truncate if needed
    if len(text) > 4000:
        text = text[:3990] + "\n\n…[truncated]"
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT,
            "text": f"📊 Vantage · {today}\n\n{text}",
            "parse_mode": "Markdown"
        },
        timeout=15
    )
    resp.raise_for_status()
    return resp.json()

def main():
    print(f"Running {briefing_type} briefing for {today}")

    # Generate briefing
    print("Calling Anthropic API...")
    briefing = call_anthropic(PROMPTS[briefing_type])
    print(f"Got {len(briefing)} chars")

    # Send to Telegram
    print("Sending to Telegram...")
    result = send_telegram(briefing)
    if result.get("ok"):
        print("✓ Telegram sent successfully")
    else:
        print(f"✗ Telegram error: {result}")
        raise Exception(f"Telegram failed: {result}")

    print("Done.")

if __name__ == "__main__":
    main()
