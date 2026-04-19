"""
Vantage Daily Briefing — GitHub Actions script
Personalised briefing using your actual portfolio positions from the web app.

Setup:
1. Run Portfolio Advisor + Stock Scanner in the web app
2. Click "Export for GitHub Actions" in Daily Briefing
3. Save the file as portfolio_context.json in this repo root
4. Briefings will use your actual positions automatically
"""

import os
import json
import re
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT = os.environ["TELEGRAM_CHAT_ID"]

SGT = timezone(timedelta(hours=8))
now = datetime.now(SGT)
today = now.strftime("%A, %d %B %Y")
weekday = now.weekday()  # 0=Mon, 6=Sun

# Sunday = no briefing
if weekday == 6:
    print("Sunday — no briefing. Exiting.")
    exit(0)

day_label = (
    "Monday Weekly Review" if weekday == 0 else
    "Weekend Portfolio Check" if weekday == 5 else
    "Daily Briefing"
)

# ── Load portfolio context if available ──
context_file = Path("portfolio_context.json")
portfolio_block = ""
watchlist_block = ""
context_age_note = ""

if context_file.exists():
    try:
        ctx = json.loads(context_file.read_text())
        port = ctx.get("portfolio", {})
        watch = ctx.get("watchlist", {})
        exported = ctx.get("exported", "")

        if exported:
            age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(exported.replace("Z", "+00:00"))).days
            if age_days > 7:
                context_age_note = f"\nNote: portfolio context is {age_days} days old — advice may be stale."

        positions = port.get("positions", [])
        if positions:
            high_pri = [p for p in positions if (p.get("priority") or "").lower() == "high"]
            trim_exit = [p for p in positions if (p.get("action") or "").upper() in ["TRIM", "EXIT", "SELL", "REDUCE"]]
            all_tickers = [p["ticker"] for p in positions]

            portfolio_block = f"""
CURRENT PORTFOLIO ({len(positions)} positions, context from {port.get('updated', 'unknown')[:10]}):
Summary: {port.get('summary', 'N/A')}
HIGH PRIORITY actions pending:
{chr(10).join(f"- {p['ticker']}: {p['action']} | Exit: {p.get('exit_target') or 'N/S'} | Stop: {p.get('stop') or 'N/S'} | {p.get('reasoning','')[:100]}" for p in high_pri) or "- None flagged high priority"}
TRIM/EXIT candidates:
{chr(10).join(f"- {p['ticker']}: {p['action']} | Target: {p.get('exit_target') or 'N/S'} | Stop: {p.get('stop') or 'N/S'}" for p in trim_exit) or "- None"}
All positions: {', '.join(f"{p['ticker']}({p.get('action','?')})" for p in positions)}"""

        stocks = watch.get("stocks", [])
        if stocks:
            tier1 = [s for s in stocks if "1" in (s.get("conviction") or "") or "high" in (s.get("conviction") or "").lower()]
            watchlist_block = f"""
WATCHLIST ({len(stocks)} stocks from last scanner run):
Macro context: {watch.get('macro', 'N/A')}
Tier 1 / highest conviction: {', '.join(f"{s['ticker']} entry:{s.get('entry','?')} tgt:{s.get('target','?')}" for s in tier1) or 'None'}
Full watchlist: {' | '.join(f"{s['ticker']}[{s.get('sleeve','LT')}]" for s in stocks)}"""

        print(f"Loaded context: {len(positions)} positions, {len(stocks)} watchlist stocks")
    except Exception as e:
        print(f"Could not load portfolio_context.json: {e}")
else:
    print("No portfolio_context.json found — running generic briefing")
    print("Tip: use 'Export for GitHub Actions' in the web app to personalise these briefings")

# ── Prompts ──
SHARED_PROFILE = f"""Investor profile: value investing, US NYSE/NASDAQ and SGX/SEA markets, dual horizon — long-term 2–5 years and short-term under 3 months.
{portfolio_block}
{watchlist_block}
{context_age_note}"""

PROMPTS = {
    "Daily Briefing": f"""You are a personal investment advisor generating a {day_label} for {today}.

{SHARED_PROFILE}

Generate a personalised briefing. If portfolio data is available above, reference specific tickers and their exact exit targets or stops. Use plain text only — no markdown headers, no asterisks, no dashes as dividers.

Format exactly:

📊 Vantage {day_label} — {today}

🔴 Urgent actions
[Time-sensitive actions: positions near stops, high-priority trims/exits. Reference specific tickers and price levels. If none: "None today."]

📋 This week's positions
[For each TRIM or EXIT candidate: restate the action and exact price target. One line per ticker.]

📡 Market signal
[One macro signal relevant to your specific holdings. One sentence.]

✅ Today's actions
[Numbered list, max 6. Format: "1. TICKER — action at price/condition". Reference actual positions where possible.]

Under 300 words. Direct, no preamble, no sign-off.""",

    "Monday Weekly Review": f"""You are a personal investment advisor generating a Monday weekly review for {today}.

{SHARED_PROFILE}

Use plain text only — no markdown headers, no asterisks, no dashes as dividers.

Format exactly:

📊 Vantage Weekly Review — {today}

📈 Last week recap
[Key moves relevant to your holdings. Reference specific tickers where relevant. 2 sentences.]

🗓 This week's calendar
[Top 2–3 events this week — earnings for held stocks, Fed/MAS, economic data. Be specific.]

🔭 Watchlist entries
[For each watchlist stock: is it at or near entry zone? One line each.]

✅ This week's priorities
[Numbered list, max 5. Format: "1. TICKER — action — reason in one sentence".]

Under 320 words.""",

    "Weekend Portfolio Check": f"""You are a personal investment advisor generating a Saturday portfolio check for {today}.

{SHARED_PROFILE}

Use plain text only — no markdown headers, no asterisks, no dashes as dividers.

Format exactly:

📊 Vantage Weekend Check — {today}

📈 Week in review
[US and SGX performance this week, relevant to your holdings. 2 sentences.]

⚠ Stop check
[For each high-priority or trim/exit position: is the stop level still valid? Any at risk of triggering next week?]

📋 Weekend prep
[One concrete research task to do before Monday open, based on your actual positions or watchlist.]

Under 220 words."""
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
            "max_tokens": 700,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]

def clean_text(text):
    text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def send_telegram(text):
    text = clean_text(text)
    if len(text) > 4000:
        text = text[:3990] + "\n\n[truncated]"
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT, "text": text},
        timeout=15
    )
    resp.raise_for_status()
    return resp.json()

def main():
    print(f"Running {day_label} for {today}")
    briefing = call_anthropic(PROMPTS[day_label])
    print(f"Got {len(briefing)} chars")
    result = send_telegram(briefing)
    if result.get("ok"):
        print("Telegram sent OK")
    else:
        raise Exception(f"Telegram failed: {result}")

if __name__ == "__main__":
    main()
