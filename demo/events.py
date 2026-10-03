"""
計測層 + 基盤層のイベント処理
================================
UI層から飛んでくる生イベント（再生・完了・スキップ・いいね・購入・勝敗）を受け取り、
1) events テーブルへ生ログとして保存
2) videos / user_prefs の集計値をその場で更新（簡易ストリーム処理）
という2段構えにしている。

実サービスでは 1) はKafka等のイベントバスへ、2) は別のストリーム処理基盤
（Flink等）で非同期に行うことが多いが、本デモでは同期処理に単純化している。
"""

import time

from db import get_connection
from recommender import update_user_prefs, update_elo

# 反応の種類ごとに、ユーザーの「そのカテゴリへの嗜好」をどれだけ動かすか
PREF_DELTA = {
    "complete": +0.05,
    "skip": -0.03,
    "like": +0.15,
    "purchase": +0.4,
    "play": 0.0,
}


def _log_raw_event(user_id: int, video_id, type_: str, value: float = None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO events (user_id, video_id, type, value, ts) VALUES (?, ?, ?, ?, ?)",
        (user_id, video_id, type_, value, time.time()),
    )
    conn.commit()
    conn.close()


def ingest_event(user_id: int, video_id: int, type_: str, value: float = None):
    """UI層からの単発イベント（play/complete/skip/like/purchase）を処理する。"""
    _log_raw_event(user_id, video_id, type_, value)

    conn = get_connection()
    video = conn.execute("SELECT category FROM videos WHERE id=?", (video_id,)).fetchone()

    column_map = {
        "complete": "completes",
        "skip": "skips",
        "like": "likes",
        "purchase": "purchases",
    }
    col = column_map.get(type_)
    if col:
        conn.execute(f"UPDATE videos SET {col} = {col} + 1 WHERE id=?", (video_id,))
    conn.commit()
    conn.close()

    if video and type_ in PREF_DELTA and PREF_DELTA[type_] != 0.0:
        update_user_prefs(user_id, video["category"], PREF_DELTA[type_])


def ingest_battle_result(user_id: int, winner_id: int, loser_id: int):
    """「どちらが気になる？」で選ばれた方を勝ち、選ばれなかった方を負けとして記録する。"""
    _log_raw_event(user_id, winner_id, "win")
    _log_raw_event(user_id, loser_id, "lose")
    update_elo(winner_id, loser_id)
