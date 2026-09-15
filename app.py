import os
import re
import requests
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- META CREDENTIALS ---
ACCESS_TOKEN = "EAAPaOr3UNogBSeScgYCJn8fEjzJ3USnfLPHwvITupw2inGpSeWym20Me6gHRuVUAvGGzD1uOUoTzhOyp3h6ZAD2ZCEEklaonNOIhbdaEeQhcfNWoJYFM562He8JgdfQB95VMnOa86tBxpKi4fA7U6kK2QUjmKKXpTmIGFE3wF70du7ZBmDKZB9v4OeO2Q3NrTAZDZD"
PHONE_NUMBER_ID = "1335444236311842"
VERIFY_TOKEN = "my_secret_diet_bot_token"

DIET_TARGETS = {
    "eggs": {"target": 4, "unit": "pcs"},
    "peanut butter": {"target": 2.5, "unit": "tbsp"},
    "bread": {"target": 3, "unit": "slices"},
    "rice": {"target": 700, "unit": "gm"},
    "soya chunks": {"target": 100, "unit": "gm"},
    "whey": {"target": 1, "unit": "scoop"}
}

user_logs = {food: 0.0 for food in DIET_TARGETS}

# --- MIDNIGHT AUTOMATIC RESET TASK ---
def reset_daily_logs():
    global user_logs
    user_logs = {food: 0.0 for food in DIET_TARGETS}
    print("⏰ Automatic Midnight Reset: All food logs reset to zero.")

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
scheduler.add_job(reset_daily_logs, 'cron', hour=0, minute=0)
scheduler.start()

# --- LIGHTWEIGHT HEALTHCHECK FOR UPTIMEROBOT ---
@app.route("/health", methods=["GET"])
def health_check():
    return "OK", 200

def send_whatsapp_message(recipient_number, text_body):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient_number,
        "type": "text",
        "text": {"body": text_body}
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()

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

                # 1. STATUS COMMAND
                if incoming_msg == "status":
                    in_progress = []
                    completed = []
                    total_items = len(DIET_TARGETS)
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

                    completion_pct = int((completed_count / total_items) * 100)
                    
                    reply = "📈 *Daily Executive Summary*\n\n"
                    if in_progress:
                        reply += "⏳ *In Progress*\n" + "\n".join(in_progress) + "\n\n"
                    if completed:
                        reply += "✅ *Objectives Met*\n" + "\n".join(completed) + "\n\n"
                    reply += f"🎯 *Daily Objective:* 2,500 kcal | 120g Protein\n"
                    reply += f"📊 *Completion Rate:* {completion_pct}%"

                # 2. MANUAL RESET COMMAND
                elif incoming_msg in ["reset", "clear", "reset log"]:
                    reset_daily_logs()
                    reply = "⚙️ *System Maintenance*\n\n🔄 *Daily Metrics Reset Completed*\nAll consumption trackers have been restored to zero."

                # 3. LOGGING ITEMS WITH REMAINING STATUS FOR ALL ITEMS
                else:
                    raw_items = re.split(r'[\n,]+', incoming_msg)
                    logged_entries = []
                    unmatched_entries = []
                    logged_foods = set()

                    for item in raw_items:
                        item = item.strip()
                        if not item:
                            continue
                        
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
                                consumed = user_logs[matched_food]
                                remaining = target - consumed
                                unit = DIET_TARGETS[matched_food]["unit"]

                                a_str = int(amount) if amount.is_integer() else amount
                                r_str = int(remaining) if remaining.is_integer() else remaining

                                if remaining > 0:
                                    status_text = f"({r_str} {unit} remaining)"
                                elif remaining == 0:
                                    status_text = "🎯 Target Reached!"
                                else:
                                    status_text = f"⚠️ Over by {abs(r_str)} {unit}"

                                logged_entries.append(f"• *{matched_food.title()}*: +{a_str} {unit} logged *{status_text}*")
                                logged_foods.add(matched_food)
                            else:
                                unmatched_entries.append(food_input)

                    if logged_entries:
                        reply = "📥 *Log Executed Successfully*\n\n"
                        reply += "\n".join(logged_entries)
                        
                        # Calculate remaining balance for all other items
                        other_remaining = []
                        for food, info in DIET_TARGETS.items():
                            if food not in logged_foods:
                                consumed = user_logs[food]
                                target = info["target"]
                                remaining = target - consumed
                                unit = info["unit"]

                                r_str = int(remaining) if isinstance(remaining, int) or remaining.is_integer() else remaining
                                t_str = int(target) if isinstance(target, int) or target.is_integer() else target

                                if remaining > 0:
                                    other_remaining.append(f"• *{food.title()}*: {r_str} {unit} remaining")
                                elif remaining == 0:
                                    other_remaining.append(f"• *{food.title()}*: ✅ Reached ({t_str} {unit})")
                                else:
                                    other_remaining.append(f"• *{food.title()}*: ⚠️ Over by {abs(r_str)} {unit}")

                        if other_remaining:
                            reply += "\n\n📋 *Remaining Balances*\n" + "\n".join(other_remaining)

                        if unmatched_entries:
                            reply += f"\n\n⚠️ *Unprocessed Inputs:* {', '.join(unmatched_entries)}"
                    else:
                        reply = "🤖 *System Assistant | Directory*\n\nPlease use standard syntax for request processing:\n\n"
                        reply += "• *Log Single Item:* `2 eggs`\n"
                        reply += "• *Log Batch:* `2 eggs, 1.5 tbsp peanut butter`\n"
                        reply += "• *Request Dashboard:* `status`\n"
                        reply += "• *System Reset:* `reset`"

                send_whatsapp_message(from_number, reply)
    except Exception as e:
        print(f"Error processing webhook: {e}")
        
    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
