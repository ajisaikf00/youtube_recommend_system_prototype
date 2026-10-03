"""
UI層のホスト & APIエントリポイント
======================================
Flaskで最小限のサーバーを立て、
  - / ... UI層（自動再生・無限スクロール・進捗バー・ログイン表示）を返す
  - /api/feed ... 推薦・最適化層を呼び出してフィードを返す
  - /api/event ... 計測層へイベントを流し込む
をローカルだけで完結させる。外部サービスへの通信は一切行わない。
"""

from flask import Flask, jsonify, render_template, request, session

import events
import recommender
from db import get_connection, init_db, is_seeded
from seed_data import seed

app = Flask(__name__)
app.secret_key = "local-demo-only-not-for-production"


@app.before_request
def _ensure_db():
    init_db()
    if not is_seeded():
        seed()


@app.route("/")
def index():
    conn = get_connection()
    users = conn.execute("SELECT id, name, ab_variant FROM users").fetchall()
    conn.close()
    return render_template("index.html", users=[dict(u) for u in users])


@app.route("/api/login", methods=["POST"])
def login():
    user_id = int(request.json["user_id"])
    session["user_id"] = user_id
    variant = recommender.get_variant(user_id)
    return jsonify({"ok": True, "user_id": user_id, "variant": variant})


@app.route("/api/feed")
def feed():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "not logged in"}), 401
    page = int(request.args.get("page", 0))
    result = recommender.get_feed(user_id, page)
    return jsonify(result)


@app.route("/api/event", methods=["POST"])
def event():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "not logged in"}), 401
    data = request.json
    events.ingest_event(
        user_id=user_id,
        video_id=data["video_id"],
        type_=data["type"],
        value=data.get("value"),
    )
    return jsonify({"ok": True})


@app.route("/api/battle", methods=["POST"])
def battle():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "not logged in"}), 401
    data = request.json
    events.ingest_battle_result(
        user_id=user_id, winner_id=data["winner_id"], loser_id=data["loser_id"]
    )
    return jsonify({"ok": True})


@app.route("/api/debug/user/<int:user_id>")
def debug_user(user_id):
    """自分の嗜好ベクトルやA/B群を確認できる、分析用エンドポイント。"""
    prefs = recommender.get_user_prefs(user_id)
    variant = recommender.get_variant(user_id)
    weights = recommender.get_model_weights()
    return jsonify({"variant": variant, "prefs": prefs, "model_weights": weights})


if __name__ == "__main__":
    init_db()
    if not is_seeded():
        seed()
    app.run(debug=True, port=5000)
