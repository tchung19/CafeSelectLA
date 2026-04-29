"""
One-time script to register the Telegram webhook URL.

Usage:
    python scripts/set_webhook.py https://your-railway-app.up.railway.app

Run this once after deploying to Railway and adding TELEGRAM_TOKEN to env vars.
"""

import sys
import httpx

sys.path.insert(0, ".")
from api.config import settings

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/set_webhook.py <base-url>")
        print("Example: python scripts/set_webhook.py https://cafeselect.up.railway.app")
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")
    webhook_url = f"{base_url}/bot/telegram"
    token = settings.telegram_token

    if not token:
        print("Error: TELEGRAM_TOKEN is not set in .env or environment.")
        sys.exit(1)

    res = httpx.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": webhook_url},
    )
    data = res.json()
    if data.get("ok"):
        print(f"✅ Webhook set: {webhook_url}")
    else:
        print(f"❌ Failed: {data}")

if __name__ == "__main__":
    main()
