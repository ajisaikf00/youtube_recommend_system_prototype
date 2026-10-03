"""
推薦・最適化層
==================
- スコア計算 (compute_score)
- 並べ替え (rank_candidates)
- 探索 / Exploration (apply_exploration) … 変動報酬っぽい"ばらつき"をわざと混ぜる
- ユーザー情報更新 (update_user_prefs) … 反応のたびに嗜好ベクトルを更新
- A/Bテスト (get_variant, apply_exploration が variant で挙動を変える)

※ 概念説明用の架空・簡略化された実装です。
"""

import math
import random
import time

from db import get_connection
from external_api_stub import fetch_external_recommendations

PAGE_SIZE = 6

# A: 素直にスコア順（対照群）
# B: 素直な順位に加えて"当たり/普通/微妙"をあえて混ぜる（施策群）
EXPLORATION_EPSILON = {"A": 0.0, "B": 0.35}


# ---------- ユーザー情報 ----------

def get_variant(user_id: int) -> str:
    conn = get_connection()
    row = conn.execute("SELECT ab_variant FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return row["ab_variant"] if row else "A"


def get_user_prefs(user_id: int) -> dict:
    conn = get_connection()
    rows = conn.execute(
        "SELECT category, weight FROM user_prefs WHERE user_id=?", (user_id,)
    ).fetchall()
    conn.close()
    return {r["category"]: r["weight"] for r in rows}


def update_user_prefs(user_id: int, category: str, delta: float):
    """反応（視聴完了/スキップ/いいね等）のたびに、カテゴリ嗜好を微調整する。
    これが「4. ユーザー情報更新」にあたる、ごく単純なオンライン学習。"""
    conn = get_connection()
    conn.execute(
        """INSERT INTO user_prefs (user_id, category, weight) VALUES (?, ?, ?)
           ON CONFLICT(user_id, category) DO UPDATE SET weight = weight + excluded.weight""",
        (user_id, category, delta),
    )
    conn.commit()
    conn.close()


# ---------- スコア計算 ----------

def get_model_weights() -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM model_weights").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def _normalized_elo(elo: float) -> float:
    # 1500を中心に -1〜1程度に正規化
    return max(-1.0, min(1.0, (elo - 1500) / 400))


def compute_score(video: dict, prefs: dict, weights: dict) -> float:
    impressions = max(video["impressions"], 1)
    completion_rate = video["completes"] / impressions
    like_rate = video["likes"] / impressions
    pref_match = prefs.get(video["category"], 0.0)

    score = (
        weights["w_pref"] * pref_match
        + weights["w_elo"] * _normalized_elo(video["elo"])
        + weights["w_completion"] * completion_rate
        + weights["w_like"] * like_rate
    )
    return score


def rank_candidates(user_id: int, candidates: list) -> list:
    prefs = get_user_prefs(user_id)
    weights = get_model_weights()
    scored = [
        {**dict(v), "score": compute_score(v, prefs, weights)} for v in candidates
    ]
    scored.sort(key=lambda v: v["score"], reverse=True)
    return scored


# ---------- 探索 (Exploration) ----------

def apply_exploration(ranked: list, variant: str) -> list:
    """
    Bグループでは「確実に良い物」だけを連発せず、あえてスコアの低い候補を
    一定確率で上位に混ぜる。これにより結果の予測しづらさ（可変報酬）を作る。
    A/Bで比較できるようにするための、意図的な仕掛け。
    """
    epsilon = EXPLORATION_EPSILON.get(variant, 0.0)
    if epsilon <= 0 or len(ranked) < 2:
        return ranked

    result = []
    pool = ranked[:]
    while pool:
        if random.random() < epsilon and len(pool) > 1:
            # 上位に固執せず、ランダムな順位の動画を"混ぜる"
            idx = random.randrange(len(pool))
        else:
            idx = 0  # 最もスコアが高いもの
        result.append(pool.pop(idx))
    return result


# ---------- Elo (勝敗) ----------

def update_elo(winner_id: int, loser_id: int, k: float = 16.0):
    conn = get_connection()
    w = conn.execute("SELECT elo FROM videos WHERE id=?", (winner_id,)).fetchone()
    l = conn.execute("SELECT elo FROM videos WHERE id=?", (loser_id,)).fetchone()
    if not w or not l:
        conn.close()
        return
    expected_w = 1 / (1 + 10 ** ((l["elo"] - w["elo"]) / 400))
    expected_l = 1 - expected_w
    new_w = w["elo"] + k * (1 - expected_w)
    new_l = l["elo"] + k * (0 - expected_l)
    conn.execute("UPDATE videos SET elo=? WHERE id=?", (new_w, winner_id))
    conn.execute("UPDATE videos SET elo=? WHERE id=?", (new_l, loser_id))
    conn.commit()
    conn.close()


# ---------- フィード生成（UI層から呼ばれるエントリポイント） ----------

def get_feed(user_id: int, page: int = 0):
    variant = get_variant(user_id)

    conn = get_connection()
    all_videos = conn.execute("SELECT * FROM videos").fetchall()
    conn.close()

    # 外部レコメンドAPIがあればそちらを優先、なければローカルにフォールバック
    external = fetch_external_recommendations(user_id, k=PAGE_SIZE)
    if external is not None:
        candidates = external
    else:
        # 無限スクロール用に、毎回ランダムな母集団からサンプリング
        # （実サービスでは "まだ見せていない動画" を優先するのが普通）
        sample_size = min(len(all_videos), PAGE_SIZE * 4)
        candidates = random.sample(all_videos, sample_size)

    ranked = rank_candidates(user_id, candidates)
    ordered = apply_exploration(ranked, variant)
    page_items = ordered[:PAGE_SIZE]

    # インプレッションを記録（表示された = impressions++）
    conn = get_connection()
    for item in page_items:
        conn.execute(
            "UPDATE videos SET impressions = impressions + 1 WHERE id=?",
            (item["id"],),
        )
    conn.commit()
    conn.close()

    # たまに「どちらが気になる？」のバトルUIを差し込む（勝敗イベントの入口）
    battle_pair = None
    if len(page_items) >= 2 and random.random() < 0.4:
        a, b = random.sample(page_items, 2)
        battle_pair = {"a": a, "b": b}

    return {
        "variant": variant,
        "items": page_items,
        "battle": battle_pair,
        "generated_at": time.time(),
    }
