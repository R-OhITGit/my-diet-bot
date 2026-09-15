import os
import re
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- META CREDENTIALS ---
ACCESS_TOKEN = "EAAPaOr3UNogBSeScgYCJn8fEjzJ3USnfLPHwvITupw2inGpSeWym20Me6gHRuVUAvGGzD1uOUoTzhOyp3h6ZAD2ZCEEklaonNOIhbdaEeQhcfNWoJYFM562He8JgdfQB95VMnOa86tBxpKi4fA7U6kK2QUjmKKXpTmIGFE3wF70du7ZBmDKZB9v4OeO2Q3NrTAZDZD"
PHONE_NUMBER_ID = "1335444236311842"
VERIFY_TOKEN = "my_secret_diet_bot_token"

# --- SUPABASE CREDENTIALS ---
SUPABASE_URL = "https://supabase.com"
SUPABASE_KEY = "sb_publishable_9E3HxGiqRjjGnvTqSkIySg_Yr9PoFKr"

DIET_TARGETS = {
    "eggs": {"target": 4, "unit": "pcs"},
    "peanut butter": {"target": 2.5, "unit": "tbsp"},
    "bread": {"target": 3, "unit": "slices"},
    "rice": {"target": 700, "unit": "gm"},
    "soya chunks": {"target": 100, "unit": "gm"},
    "whey": {"target": 1, "unit": "scoop"}
}

user_logs = {food: 0.0 for food in DIET_TARGETS}

def get_db_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def sync_from_database():
    """Fetches today's logs from the database or creates a new entry for today"""
    global user_logs
    today_str = datetime.now().strftime("%Y-%m-%d")
    url = f"{SUPABASE_URL}/rest/v1/daily_history?log_date=eq.{today_str}"
    
    try:
        response = requests.get(url, headers=get_db_headers())
        data = response.json()
        
        if data:
            row = data[0]
            user_logs["eggs"] = float(row.get("eggs", 0.0))
            user_logs["peanut butter"] = float(row.get("peanut_butter", 0.0))
            user_logs["bread"] = float(row.get("bread", 0.0))
            user_logs["rice"] = float(row.get("rice", 0.0))
            user_logs["soya chunks"] = float(row.get("soya_chunks", 0.0))
            user_logs["whey"] = float(row.get("whey", 0.0))
        else:
            insert_url = f"{SUPABASE_URL}/rest/v1/daily_history"
            payload = {"log_date": today_str}
            requests.post(insert_url, headers=get_db_headers(), json=payload)
            user_logs = {food: 0.0 for food in DIET_TARGETS}
    except Exception as e:
        print(f"Database sync error: {e}")

def update_database():
    """Saves current live data directly into the database row"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    url = f"{SUPABASE_URL}/rest/v1/daily_history?log_date=eq.{today_str}"
    payload = {
        "eggs": user_logs["eggs"],
        "peanut_butter": user_logs["peanut butter"],
        "bread": user_logs["bread"],
        "rice": user_logs["rice"],
        "soya_chunks": user_logs["soya chunks"],
        "whey": user_logs["whey"]
    }
    try:
        requests.patch(url, headers=get_db_headers(), json=payload)
    except Exception as e:
        print(f"Database update error: {e}")

# Initialize baseline on bootup
sync_from_database()

def reset_daily_logs():
    sync_from_database()
    print("⏰ Automatic Midnight Reset and History Save Completed.")

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
scheduler.add_job(reset_daily_logs, 'cron', hour=0, minute=0)
scheduler.start()

@app.route("/health", methods=["GET"])
def health_check():
    return "OK", 200

def send_whatsapp_message(recipient_number, text_body):
    url = f"https://facebook.com{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": recipient_number, "type": "text", "text": {"body": text_body}}
    requests.post(url, headers=headers, json=data)

@app.route("/webhook", methods=["GET"])
def webhook_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def webhook_receive():
    global user_logs
    data = request.get_json()
    try:
        entry = data['entry'][0]
        changes = entry['changes'][0]
        value = changes['value']

        if 'messages' in value:
            message = value['messages'][0]
            from_number = message['from']
            
            if message['type'] == 'text':
                incoming_msg = message['text']['body'].lower().strip()
                reply = ""

                sync_from_database()

                # 1. STATUS COMMAND
                if incoming_msg == "status":
                    in_progress, completed = [], []
                    completed_count = 0

                    for food, info in DIET_TARGETS.items():
                        consumed = user_logs[food]
                        c_str = int(consumed) if consumed.is_integer() else consumed
                        t_str = int(info['target']) if isinstance(info['target'], int) or info['target'].is_integer() else info['target']
                        line = f"• *{food.title()}*: {c_str} / {t_str} {info['unit']}"
                        if consumed >= info['target']:
                            completed.append(line)
                            completed_count += 1
                        else:
                            in_progress.append(line)

                    completion_pct = int((completed_count / len(DIET_TARGETS)) * 100)
                    reply = "📈 *Daily Executive Summary*\n\n"
                    if in_progress: reply += "⏳ *In Progress*\n" + "\n".join(in_progress) + "\n\n"
                    if completed: reply += "✅ *Objectives Met*\n" + "\n".join(completed) + "\n\n"
                    reply += f"🎯 *Daily Objective:* 2,500 kcal | 120g Protein\n📊 *Completion Rate:* {completion_pct}%"

                # 2. DYNAMIC CUSTOM HISTORY COMMAND (e.g., "history 10", "history 30", or "history")
                elif incoming_msg.startswith("history"):
                    # Check if a custom number of days was provided
                    history_match = re.match(r"^history\s+(\d+)$", incoming_msg)
                    if history_match:
                        days = int(history_match.group(1))
                    else:
                        days = 7  # Default view if you just text "history"

                    url = f"{SUPABASE_URL}/rest/v1/daily_history?order=log_date.desc&limit={days}"
                    res = requests.get(url, headers=get_db_headers()).json()
                    
                    if res and isinstance(res, list):
                        reply = f"🗓️ *Your Intake History (Last {len(res)} Days)*\n\n"
                        for row in res:
                            reply += f"📅 *{row['log_date']}*\n"
                            reply += f"🥚 Eggs: {row['eggs']} | 🥜 PB: {row['peanut_butter']} | 🍞 Bread: {row['bread']}\n"
                            reply += f"🍚 Rice: {row['rice']}g | 🧆 Soya: {row['soya_chunks']}g | 🥛 Whey: {row['whey']}\n\n"
                    else:
                        reply = "📭 No historical logs found in your database yet."

                # 3. MANUAL RESET
                elif incoming_msg in ["reset", "clear"]:
                    user_logs = {food: 0.0 for food in DIET_TARGETS}
                    update_database()
                    reply = "🔄 *Daily Trackers Cleared to Zero.*"

                # 4. ENTRY LOGGING LOGIC
                else:
                    raw_items = re.split(r'[\n,]+', incoming_msg)
                    logged_entries = []

                    for item in raw_items:
                        item = item.strip()
                        if not item: continue
                        match = re.match(r"^([0-9\.]+)\s*(.+)$", item)
                        if match:
                            amount = float(match.group(1))
                            food_input = match.group(2).strip()
                            matched_food = None

                            for food in DIET_TARGETS:
                                if food in food_input or food_input in food:
                                    matched_food = food
                                    break

                            if matched_food:
                                user_logs[matched_food] += amount
                                target = DIET_TARGETS[matched_food]["target"]
                                remaining = target - user_logs[matched_food]
                                unit = DIET_TARGETS[matched_food]["unit"]

                                r_str = int(remaining) if remaining.is_integer() else remaining
                                status_text = f"({r_str} {unit} left)" if remaining > 0 else "🎯 Target Reached!"
                                logged_entries.append(f"• *{matched_food.title()}*: +{amount} {unit} logged {status_text}")

                    if logged_entries:
                        update_database()
                        reply = "📥 *Log Executed Successfully*\n\n" + "\n".join(logged_entries)
                    else:
                        reply = "❌ Invalid syntax. Use format like: `2 eggs` or type `status`, `history 10`"

                send_whatsapp_message(from_number, reply)
    except Exception as e:
        print(f"Error handling request: {e}")
    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
