from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
from flask_limiter import Limiter



app = Flask(__name__)
CORS(app, origins=["https://lazy-gpt.webflow.io"], supports_credentials=True)


SESSION_USAGE = {}
FREE_LIMIT = 3

def get_session_id():
    try:
        return request.cookies.get("session_id") or "no-session"
    except:
        return "no-session"

def is_pro_user(session_id):
    return session_id.startswith("pro_")

limiter = Limiter(
    key_func=get_session_id,
    app=app
)

@app.before_request

allowed_origin = "https://lazy-gpt.webflow.io"
referer = request.headers.get("Referer", "")
if not referer.startswith(allowed_origin):
    return jsonify({"error": "Invalid referer"}), 403

def reject_invalid_token():
    if request.path in ["/ask", "/analyze-image"] and request.method == "POST":
        try:
            data = request.get_json() if request.is_json else {}

            if data.get("js_token") != "genuine-human":
                print("🚩 Bot без js_token — отклонён", flush=True)
                return jsonify({"error": "Bot detected — invalid token"}), 403

            if data.get("phone"):  # honeypot поле заполнено
                print("🚩 Honeypot заполнен — бот!", flush=True)
                return jsonify({"error": "Bot detected — honeypot filled"}), 403

        except Exception as e:
            return jsonify({"error": "Malformed request"}), 403


@app.route("/ask", methods=["POST", "OPTIONS"])
@app.route("/reset", methods=["POST"])
def reset_session_usage():
    session_id = get_session_id()
    if session_id in SESSION_USAGE:
        del SESSION_USAGE[session_id]
        print(f"✅ Сброшен лимит для: {session_id}")
    else:
        print(f"ℹ️ Нет лимита для сброса: {session_id}")
    return jsonify({"message": "Session usage reset", "session_id": session_id})

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





@cross_origin(origins=["https://lazy-gpt.webflow.io"], supports_credentials=True)
@limiter.limit(lambda: "30 per minute" if is_pro_user(get_session_id()) else "5 per minute")
def ask():
    print("📥 Пришёл запрос на /ask")
    session_id = get_session_id()
    is_pro = is_pro_user(session_id)

    try:
        data = request.get_json(force=True)
        print("🔍 session:", session_id, "| pro:", is_pro)

        if not is_pro:
            SESSION_USAGE[session_id] = SESSION_USAGE.get(session_id, 0) + 1
            if SESSION_USAGE[session_id] > FREE_LIMIT:
                return jsonify({
                    "error": "Free limit reached",
                    "pro": False,
                    "session_id": session_id
                }), 403

        return jsonify({
            "response": f"✅ Принято. Это ваш {SESSION_USAGE.get(session_id, 1)} запрос.",
            "pro": is_pro,
            "session_id": session_id
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def index():
    return jsonify({"status": "HomeBuddy is running clean."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
