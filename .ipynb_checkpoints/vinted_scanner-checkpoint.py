#!/usr/bin/env python3
import json
import logging
import os
import requests
from datetime import datetime
from logging.handlers import RotatingFileHandler
from helpers import load_config, get_user_data, send_discord_message

PROCESSED_ITEMS_FILE = "vinted_items.txt"

def load_processed_items():
    if not os.path.exists(PROCESSED_ITEMS_FILE):
        return set()
    with open(PROCESSED_ITEMS_FILE, 'r') as f:
        return set(line.strip() for line in f if line.strip())

def save_processed_item(item_id):
    with open(PROCESSED_ITEMS_FILE, 'a') as f:
        f.write(f"{item_id}\n")

config = load_config()

handler = RotatingFileHandler("vinted_scanner.log", maxBytes=5000000, backupCount=5)

logging.basicConfig(
    handlers=[handler],
    format="%(asctime)s - %(filename)s - %(funcName)10s():%(lineno)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

timeoutconnection = 30

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.8,en-US;q=0.5,en;q=0.3",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-GPC": "1",
    "Priority": "u=0, i",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}

webhook_url = os.environ.get("WEBHOOK_URL")

def main():
    processed_items = load_processed_items()
    session = requests.Session()
    session.post(config["vinted_url"], headers=headers, timeout=timeoutconnection)
    cookies = session.cookies.get_dict()

    new_items_found = 0

    for params in config["search_queries"]:
        print("🔍 Running search with params:", params)
        try:
            response = requests.get("https://vinted.ie/api/v2/catalog/items", params=params, cookies=cookies, headers=headers)
            data = response.json()
        except Exception as e:
            print(f"❌ Failed to fetch or decode response: {e}")
            continue

        if "items" in data:
            for item in data["items"]:
                item_id = str(item["id"])

                if item_id in processed_items:
                    continue  # already processed

                item_title = item["brand_title"]
                item_name = item["title"]
                item_url = item["url"]
                item_price = f'{item["price"]["amount"]} {item["price"]["currency_code"]}'
                service_fee = item["service_fee"]["amount"]
                item_size = item["size_title"]
                item_condition = item["status"]
                item_image = item["photo"]["full_size_url"]
                user_id = item["user"]["login"]

                feedback = get_user_data(session, user_id)
                if not feedback:
                    continue

                if feedback["positive_feedback"] > 0:
                    send_discord_message(item_title, item_name, item_price, item_url, item_image, user_id, feedback,
                                         webhook_url, item_size, item_condition, service_fee)
                    print(f"✅ Sent new item: {item_title}")
                else:
                    print(f"⚠️ Skipped item from user {user_id} due to low feedback.")

                save_processed_item(item_id)
                processed_items.add(item_id)
                new_items_found += 1
        else:
            print("⚠️ No 'items' key found in API response.")

    if new_items_found == 0:
        print("ℹ️ No new items found during this scan.")
    else:
        print(f"✅ {new_items_found} new item(s) processed.")

if __name__ == "__main__":
    main()
