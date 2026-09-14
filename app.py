import os
import re
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- PASTE YOUR META CREDENTIALS HERE ---
ACCESS_TOKEN = "EAAPaOr3UNogBSSBmmaG5gmew1ZAdHFT2QOumaX4lAKlY39ZBdgZBHq1r8kRPOajfg1LCL0ZASv6XyNMYkUj3WiVV3844ZCR7XwdB0VP0GfCOxGKuYdJyNNjZB3HhZBry1cAQliBFvCLzFEMt0L8vPZCIFQRreySWn39awGBrFEB45G05i40Qz2PPS4aAqbhDjhwdmRcdeQRDAnDNHlVvyIKvo7wZBBy9HkK9f0l9CcJLxsBKgJbSfnZBVPwrP9my2zS3ZC3g3COQefeeu1ty2101IBSBSX0YwZDZD"
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

def send_whatsapp_message(recipient_number, text_body):
    url = f"https://facebook.com{PHONE_NUMBER_ID}/messages"
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
        message = data['entry']['changes']['value']['messages']
        from_number = message['from']
        
        if message['type'] == 'text':
            incoming_msg = message['text']['body'].lower().strip()
            reply = ""

            if incoming_msg == "status":
                reply = "📋 *Your Daily Intake Status:*\n\n"
                for food, info in DIET_TARGETS.items():
                    consumed = user_logs[food]
                    c_str = int(consumed) if consumed.is_integer() else consumed
                    t_str = int(info['target']) if isinstance(info['target'], int) or info['target'].is_integer() else info['target']
                    reply += f"• *{food.title()}*: {c_str}/{t_str} {info['unit']}\n"
                reply += "\n🔥 Total Target: 2500 Cal | 120g Protein"

            elif incoming_msg == "reset":
                user_logs = {food: 0.0 for food in DIET_TARGETS}
                reply = "🔄 Daily logs have been reset to 0!"

            else:
                match = re.match(r"^([0-9\.]+)\s+(.+)$", incoming_msg)
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
                            reply = f"✅ {a_str} {matched_food} logged. {r_str} {unit} more to go!"
                        elif remaining == 0:
                            reply = f"🎉 Goal reached for {matched_food}!"
                        else:
                            reply = f"⚠️ Over Limit! Exceeded {matched_food} by {abs(r_str)} {unit}."
                    else:
                        reply = "❌ Food item not found."
                else:
                    reply = "❌ Invalid format. Use:\n• `2 eggs`\n• `status`"

            send_whatsapp_message(from_number, reply)
    except Exception as e:
        pass
    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
