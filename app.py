from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
from openai import OpenAI
import sys
from flask_limiter import Limiter
import json

sys.stdout.reconfigure(line_buffering=True)
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app = Flask(__name__)

# Разрешаем запросы только с твоего фронта
CORS(app, origins=["https://lazy-gpt-api.onrender.com"])

# Ограничение по session_id из cookie
def get_session_id():
    try:
        return request.cookies.get("session_id") or "no-session"
    except:
        return "no-session"

limiter = Limiter(key_func=get_session_id, app=app)

@app.before_request
def reject_invalid_token():
    if request.path == "/ask" and request.method == "POST":
        try:
            data = request.get_json()
            if data.get("js_token") != "genuine-human":
                print("🚩 Bot without js_token — rejected", flush=True)
                return jsonify({"error": "Bot detected — invalid token"}), 403
        except:
            return jsonify({"error": "Malformed request"}), 403

@app.after_request
def log_request(response):
    print(f"📡 IP: {request.remote_addr}, UA: {request.user_agent}, Session: {get_session_id()}, Status: {response.status_code}", flush=True)
    return response

@app.route('/')
def index():
    return "HomeBuddy API is running. Use POST /ask."

@app.route('/ask', methods=['POST'])
@limiter.limit("3 per minute")
def ask():
    try:
        data = request.get_json()
        data["from"] = "webflow"
        return handle_request(data)
    except:
        return jsonify({"error": "Invalid JSON"}), 400

def handle_request(data):
    user_input = data.get("message") or ""
    is_webflow = data.get("from") == "webflow"

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    system_prompt = (
        "You are HomeBuddy — a friendly, minimal AI assistant for home tasks. "
        "Answer simply, clearly and in helpful tone. Avoid questions. No explanations. "
        "Just deliver a final result that’s practical and easy to understand for a homemaker."
    ) if is_webflow else (
        "Ты — гениальный помощник. Пользователь пишет всего одну фразу — ты сразу выдаёшь готовый, завершённый, красиво оформленный ответ. "
        "⚠️ Никогда не задавай уточняющих вопросов. Ответ должен быть кратким, лаконичным и финальным."
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
        return jsonify({"response": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)