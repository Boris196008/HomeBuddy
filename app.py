from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
from flask_limiter import Limiter
from openai import OpenAI
import os
import json

# ─── Инициализация ──────────────────────────────
app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)
#CORS(
#    app,

#origins=[
#        "https://lazy-gpt.webflow.io",
#        "https://lazygptcom.wpcomstaging.com"
#    ],
#    supports_credentials=True
)
limiter = Limiter(key_func=lambda: get_session_id(), app=app)

# OpenAI client (укажи свой API-ключ через .env или напрямую)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─── Константы и хранилище ──────────────────────
SESSION_USAGE = {}
FREE_LIMIT = 3
ALLOWED_REFERER = "https://lazy-gpt.webflow.io"

# ─── Вспомогательные функции ────────────────────
def get_session_id():
    return (
        request.headers.get("X-Session-Id") or
        request.cookies.get("session_id") or
        "no-session"
    )

def is_pro_user(session_id):
    return session_id.startswith("pro_")

# ─── Защита: js_token + honeypot + referer + UA ─
@app.before_request
def validate_request():
    if request.path not in ["/ask", "/analyze-image"] or request.method != "POST":
        return

    # Защита по Referer
    referer = request.headers.get("Referer", "")
    if not referer.startswith(ALLOWED_REFERER):
        return jsonify({"error": "Invalid referer"}), 403

    # Блокировка подозрительных User-Agent
    ua = request.headers.get("User-Agent", "").lower()
    bad_signatures = ["curl", "python", "aiohttp", "wget", "httpclient", "go-http", "scrapy", "headless"]
    if any(sig in ua for sig in bad_signatures):
        print(f"🚩 Подозрительный User-Agent: {ua}")
        return jsonify({"error": "Bot detected — invalid user-agent"}), 403

    try:
        data = request.get_json(force=True)
    except:
        return jsonify({"error": "Malformed request"}), 403

    if data.get("js_token") != "genuine-human":
        print("🚩 js_token отсутствует или неверный")
        return jsonify({"error": "Bot detected — invalid token"}), 403

    if data.get("phone"):
        print("🚩 Honeypot поле заполнено")
        return jsonify({"error": "Bot detected — honeypot filled"}), 403

# ─── Основной маршрут /ask ──────────────────────
@app.route("/ask", methods=["POST", "OPTIONS"])
@cross_origin(origins=["https://lazy-gpt.webflow.io"], supports_credentials=True)
@limiter.limit(lambda: "30 per minute" if is_pro_user(get_session_id()) else "5 per minute")
def ask():
    session_id = get_session_id()
    is_pro = is_pro_user(session_id)
    print("📥 /ask от", session_id)

    try:
        data = request.get_json(force=True)

        if not is_pro:
            SESSION_USAGE[session_id] = SESSION_USAGE.get(session_id, 0) + 1
            if SESSION_USAGE[session_id] > FREE_LIMIT:
                return jsonify({
                    "error": "Free limit reached",
                    "pro": False,
                    "session_id": session_id
                }), 403

        data["pro"] = is_pro  # <--- обязательно!
        return handle_request(data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── Chat handler logic ─────────────────────────
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

# ─── Сброс лимита ───────────────────────────────
@app.route("/reset", methods=["POST"])
def reset_session_usage():
    session_id = get_session_id()
    if session_id in SESSION_USAGE:
        del SESSION_USAGE[session_id]
        print(f"✅ Сброшен лимит для: {session_id}")
    return jsonify({"message": "Session usage reset", "session_id": session_id})

# ─── Статистика ─────────────────────────────────
@app.route("/stats", methods=["GET"])
def stats():
    total = len(SESSION_USAGE)
    anon = len([sid for sid in SESSION_USAGE if sid.startswith("anon_")])
    pro = len([sid for sid in SESSION_USAGE if sid.startswith("pro_")])
    total_requests = sum(SESSION_USAGE.values())
    return jsonify({
        "active_sessions": total,
        "anon_sessions": anon,
        "pro_sessions": pro,
        "total_requests": total_requests
    })

# ─── Заглушка ───────────────────────────────────
@app.route("/")
def index():
    return jsonify({"status": "HomeBuddy is running clean."})

# ─── Запуск ─────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
