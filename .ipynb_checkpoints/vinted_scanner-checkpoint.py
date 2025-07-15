#!/usr/bin/env python3
import csv
import time
import sys
import time
import json
import smtplib
import logging
import requests
import email.utils
from helpers import load_config, load_analyzed_item, save_analyzed_item, get_ebay_average_price, calculate_overall_score, display_stars, send_discord_message, get_user_data
from datetime import datetime
from email.message import EmailMessage
from logging.handlers import RotatingFileHandler
import sqlite3

DB_FILE = "processed_items.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS processed_items (
            item_id TEXT PRIMARY KEY
        )
    """)
    conn.commit()
    return conn

def is_processed(conn, item_id):
    c = conn.cursor()
    c.execute("SELECT 1 FROM processed_items WHERE item_id = ?", (item_id,))
    return c.fetchone() is not None

def mark_processed(conn, item_id):
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO processed_items (item_id) VALUES (?)", (item_id,))
    conn.commit()

def load_config():
    try:
        with open('Config.json', 'r') as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading config: {e}")
        return None

config = load_config()

handler = RotatingFileHandler("vinted_scanner.log", maxBytes=5000000, backupCount=5)

logging.basicConfig(handlers=[handler], 
                    format="%(asctime)s - %(filename)s - %(funcName)10s():%(lineno)s - %(levelname)s - %(message)s", 
                    level=logging.INFO)

# Timeout configuration for the requests
timeoutconnection = 30

list_analyzed_items = []

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

import os

webhook_url = os.environ.get("WEBHOOK_URL")

def main():
    # Initialize SQLite DB connection
    conn = init_db()

    session = requests.Session()
    session.post(config["vinted_url"], headers=headers, timeout=timeoutconnection)
    cookies = session.cookies.get_dict()

    new_items_found = 0  # Counter for new items

    for params in config["search_queries"]:
        print("🔍 Running search with params:", params)
        response = requests.get("https://vinted.ie/api/v2/catalog/items", params=params, cookies=cookies, headers=headers)

        try:
            data = response.json()
        except json.JSONDecodeError:
            print("❌ Failed to decode response from Vinted API.")
            return

        if "items" in data:
            for item in data["items"]:
                item_id = str(item["id"])

                # Check if already processed
                if is_processed(conn, item_id):
                    continue  # Skip if already analyzed

                listing_id = item["id"]
                item_title = item["brand_title"]
                item_name = item["title"]
                item_url = item["url"]
                item_price = f'{item["price"]["amount"]} {item["price"]["currency_code"]}'
                service_fee = item["service_fee"]["amount"] 
                item_size = item["size_title"]
                item_condition = item["status"]
                item_image = item["photo"]["full_size_url"]
                user_id = item["user"]["login"]

                search_text = params.get("search_text", "")
                
                feedback = get_user_data(session, user_id)
                if not feedback:
                    continue  # Skip if failed to fetch user data

                if feedback and feedback["positive_feedback"] > 0:
                    send_discord_message(item_title, item_name, item_price, item_url, item_image, user_id, feedback,
                                         webhook_url, item_size, item_condition, service_fee)
                else:
                    print(f"⚠️ Skipping item {item_title} from user {user_id} due to insufficient positive feedback.")

                # Mark as processed in DB
                mark_processed(conn, item_id)
                new_items_found += 1
        else:
            print("⚠️ No 'items' key found in Vinted API response.")

    if new_items_found == 0:
        print("ℹ️ No new items found during this scan.")
    else:
        print(f"✅ {new_items_found} new item(s) found and processed.")

    conn.close()

if __name__ == "__main__":
    main()