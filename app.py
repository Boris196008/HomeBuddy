from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
from openai import OpenAI
import sys
from flask_limiter import Limiter
import json
import base64

# Track number of total requests per session (in-memory)
SESSION_USAGE = {}
FREE_LIMIT = 3

# Enable live logs
sys.stdout.reconfigure(line_buffering=True)

# Load environment variables
load_dotenv()

# OpenAI client setup
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Flask app setup
app = Flask(__name__)
# Глобальный CORS (не обязателен, но пусть будет)
CORS(app,
     origins=["https://lazy-gpt.webflow.io"],
     supports_credentials=True,
     allow_headers=["Content-Type"])

@app.route("/ask", methods=["POST", "OPTIONS"])
@cross_origin(origins=["https://lazy-gpt.webflow.io"], supports_credentials=True)
def ask():
    session_id = request.cookies.get("session_id", "no-session")
    print("📡 Получен session_id:", session_id)
    return jsonify({
        "message": f"Session ID: {session_id}"
    })

# Get session ID from cookies
def get_session_id():
    try:
        return request.cookies.get("session_id") or "no-session"
    except:
        return "no-session"

def is_pro_user(session_id):
    return session_id.startswith("pro_")

# Request limiter per session
limiter = Limiter(key_func=get_session_id, app=app)

# Block bots without proper js_token
@app.before_request
def reject_invalid_token():
    if request.path in ["/ask", "/analyze-image"] and request.method == "POST":
        try:
            data = request.get_json() if request.is_json else {}
            if data.get("js_token") != "genuine-human":
                print("🚩 Bot without js_token — rejected", flush=True)
                return jsonify({"error": "Bot detected — invalid token"}), 403
        except:
            return jsonify({"error": "Malformed request"}), 403

# Request logging
@app.after_request
def log_request(response):
    print(f"📡 IP: {request.remote_addr}, UA: {request.user_agent}, Session: {get_session_id()}, Status: {response.status_code}", flush=True)
    return response

# Root route
@app.route('/')
def index():
    return "HomeBuddy API is running. Use POST /ask."

# Main chat route
@app.route('/ask', methods=['POST'])
@limiter.limit(lambda: "30 per minute" if is_pro_user(get_session_id()) else "3 per minute")
def ask():
    try:
        data = request.get_json()
        
        # 🧪 DEBUG
        print("🧪 DEBUG INFO")
        print("Cookies:", request.cookies)
        print("session_id:", get_session_id())
        print("js_token:", data.get("js_token"))
        print("Headers:", dict(request.headers))
        print("Body:", data)

        session_id = get_session_id()
        data["from"] = "webflow"
        data["pro"] = is_pro_user(session_id)


        print(f"🧭 session_id = {session_id}, count = {SESSION_USAGE.get(session_id)}, pro = {data['pro']}", flush=True)

        if not data["pro"]:
            SESSION_USAGE[session_id] = SESSION_USAGE.get(session_id, 0) + 1
            if SESSION_USAGE[session_id] > FREE_LIMIT:
                return jsonify({"error": "Free limit reached", "pro": False}), 403

        return handle_request(data)
    except:
        return jsonify({"error": "Invalid JSON"}), 400

# Chat handler logic
def handle_request(data):
    user_input = data.get("message") or ""
    language = data.get("lang", "en")
    is_pro = data.get("pro", False)

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    system_prompt = (
        "You are HomeBuddy — a friendly, minimal AI assistant for home tasks. "
        "Answer simply, clearly and in helpful tone. Avoid questions. No explanations. "
        "Just deliver a final result that’s practical and easy to understand for a homemaker."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )
        answer = response.choices[0].message.content

        followup_prompt = (
            f"You are HomeBuddy assistant. Based on the answer below, suggest 3 practical follow-up actions "
            f"that a homemaker might ask next.\n"
            f"Language: {language.upper()}\n"
            f"Respond with JSON only, format:\n"
            f"[{{\"label\": \"...\", \"action\": \"...\"}}]\n"
            f"No links, no explanation, no repetition of the answer. Keep it useful and short."
        )

        followup_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": followup_prompt},
                {"role": "user", "content": answer}
            ]
        )

        raw = followup_response.choices[0].message.content.strip()
        try:
            if "```" in raw:
                raw = raw.split("```")[1].strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
            suggestions = json.loads(raw)
        except:
            suggestions = []

        return jsonify({
            "response": answer,
            "suggestions": suggestions,
            "pro": is_pro
        })
    except Exception as e:
        return jsonify({"error": str(e), "pro": is_pro}), 500

# Analyze image route (Pro only)
@app.route('/analyze-image', methods=['POST'])
@limiter.limit(lambda: "30 per minute" if is_pro_user(get_session_id()) else "3 per minute")
def analyze_image():
    session_id = get_session_id()
    is_pro = is_pro_user(session_id)
    if not is_pro:
        return jsonify({"error": "Access restricted to paid users only.", "pro": False}), 403

    image_file = request.files.get("image")
    if not image_file:
        return jsonify({"error": "Image file is missing.", "pro": True}), 400

    image_bytes = image_file.read()
    image_b64 = base64.b64encode(image_bytes).decode()

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You're a home assistant. Help suggest what to cook based on the contents of a fridge in the photo."},
                {"role": "user", "content": [
                    {"type": "text", "text": "What can I cook using what's visible in the photo?"},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}"
                    }}
                ]}
            ],
            max_tokens=300
        )
        result = response.choices[0].message.content
        return jsonify({"recipe": result, "pro": True})
    except Exception as e:
        return jsonify({"error": str(e), "pro": True}), 500

@app.route("/reset", methods=["POST"])
def reset_session_usage():
    session_id = get_session_id()
    if session_id in SESSION_USAGE:
        del SESSION_USAGE[session_id]
        print(f"✅ Reset usage for {session_id}", flush=True)
    else:
        print(f"ℹ️ Nothing to reset for {session_id}", flush=True)
    return jsonify({"message": "Session usage reset", "session_id": session_id})

# Run app
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
