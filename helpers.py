import json
import logging
import time
import requests
from datetime import datetime
import re
from bs4 import BeautifulSoup

def load_config():
    try:
        with open('Config.json', 'r') as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading config: {e}")
        return None

def load_analyzed_item(list_analyzed_items):
    try:
        with open("vinted_items.txt", "r", errors="ignore") as f:
            for line in f:
                if line:
                    list_analyzed_items.append(line.rstrip())
    except IOError as e:
        logging.error(e, exc_info=True)
        raise

def save_analyzed_item(hash):
    try:
        with open("vinted_items.txt", "a") as f:
            f.write(str(hash) + "\n")
    except IOError as e:
        logging.error(e, exc_info=True)
        raise

def get_ebay_average_price(search_text):
    url = f"https://www.ebay.ie/sch/i.html?_nkw={search_text.replace(' ', '+')}&_sacat=0&_from=R40&rt=nc&LH_Sold=1&LH_Complete=1&rt=nc&LH_PrefLoc=3"
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

    retries = 3
    for _ in range(retries):
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise an exception for bad status codes
            soup = BeautifulSoup(response.text, "html.parser")

            print("Response fetched successfully. Checking for price elements...")

            # Find all elements containing the price
            price_elements = soup.find_all("span", class_="POSITIVE ITALIC")

            if not price_elements:
                print("No price elements found in the eBay response.")
            else:
                print(f"Found {len(price_elements)} price elements.")

            prices = []
            for price_element in price_elements:
                price_str = price_element.get_text().strip()

                match = re.search(r"EUR ([0-9,]+(?:\.\d{1,2})?)", price_str)
                if match:
                    price = match.group(1).replace(',', '')  # Remove commas if present
                    prices.append(float(price))

            if prices:
                avg_price = sum(prices) / len(prices)
                return round(avg_price, 2)
            else:
                return None

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503:
                print("503 Service Unavailable, retrying...")
                time.sleep(5)  # Wait for 5 seconds before retrying
                continue
            else:
                print(f"HTTP error: {e}")
                break
        except Exception as e:
            print(f"Error fetching eBay data: {e}")
            break
    return None
    
def calculate_overall_score(positive_feedback, negative_feedback, max_stars=5):
    # Total feedback (positive + negative)
    total_feedback = positive_feedback + negative_feedback
    if total_feedback == 0:
        return 0  # If no feedback, return a 0 score

    # Calculate the ratio of positive feedback
    score = positive_feedback / total_feedback

    # Normalize to a scale of 0 to max_stars (e.g., 5 stars)
    overall_score = score * max_stars
    return overall_score

def display_stars(score, max_stars=5):
    # Normalize score to the range of stars (0 to max_stars)
    filled_stars = int(round(score))
    empty_stars = max_stars - filled_stars
    star_display = "★" * filled_stars + "☆" * empty_stars
    return star_display

def send_discord_message(item_title, item_name, item_price, item_url, item_image, user_id, feedback, webhook_url, 
                         item_size, item_condition, service_fee):
    overall_score = calculate_overall_score(feedback["positive_feedback"], feedback["negative_feedback"])
    star_rating = display_stars(overall_score)

    content = {
        "embeds": [
            {
                "title": f"📦 {item_title}",
                "url": item_url,
                "description": (
                    f"💶 Price: `{item_price}` (+ fee: `{service_fee}`)\n"
                    f"📏 Size: `{item_size}`\n"
                    f"🧼 Condition: `{item_condition}`\n"
                    f"🙋 User: `{user_id}`\n"
                    f"⭐ Feedback: {star_rating} ({overall_score:.2f}/5)"
                ),
                "fields": [
                    {
                        "name": "👍 Positive", 
                        "value": str(feedback["positive_feedback"]), 
                        "inline": True
                    },
                    {
                        "name": "👎 Negative", 
                        "value": str(feedback["negative_feedback"]), 
                        "inline": True
                    }
                ],
                "image": {
                    "url": item_image
                },
                "footer": {
                    "text": "🤖 Vinted Scanner Bot"
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        ]
    }

    headers = {
        "Content-Type": "application/json"
    }

    while True:
        response = requests.post(webhook_url, json=content, headers=headers)

        if response.status_code == 204:
            print("✅ Discord message sent successfully!")
            break
        elif response.status_code == 429:
            retry_after = response.json().get("retry_after", 1.5)
            print(f"⏳ Rate limited by Discord. Retrying after {retry_after} seconds...")
            time.sleep(float(retry_after))
        else:
            print(f"❌ Failed to send Discord message ({response.status_code}): {response.text}")
            break

def get_user_data(session, username):
    url = f"https://www.vinted.ie/api/v2/users/{username}"
    params = {
        "search_text": username,
        "page": 1
    }
    
    response = session.get(url, params=params)

    if response.status_code == 200:
        data = response.json()

        user_data = data.get("user", {})
        positive_feedback = user_data.get("positive_feedback_count", 0)
        neutral_feedback = user_data.get("neutral_feedback_count", 0)
        negative_feedback = user_data.get("negative_feedback_count", 0)
        
        return {
            "positive_feedback": positive_feedback,
            "neutral_feedback": neutral_feedback,
            "negative_feedback": negative_feedback
        }
    else:
        print(f"Failed to fetch user data. Status: {response.status_code}")
        return None
