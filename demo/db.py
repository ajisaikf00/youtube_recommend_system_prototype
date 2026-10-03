"""
基盤層 - データベース
========================
本デモでは SQLite 1ファイル（demo.db）を「基盤層のDB」として扱う。
実サービスなら分散DB・KVS・データウェアハウスなどに分かれる部分を、
学習用に単一ファイルへ単純化している。

※ このディレクトリのコードは全て概念説明用の架空・簡略化された実装であり、
   特定企業の実装を示すものではありません。
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "demo.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    ab_variant TEXT NOT NULL DEFAULT 'A'
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    duration_sec INTEGER NOT NULL,
    elo REAL NOT NULL DEFAULT 1500,
    impressions INTEGER NOT NULL DEFAULT 0,
    completes INTEGER NOT NULL DEFAULT 0,
    skips INTEGER NOT NULL DEFAULT 0,
    likes INTEGER NOT NULL DEFAULT 0,
    purchases INTEGER NOT NULL DEFAULT 0
);

-- 計測層のイベントは全てここに生ログとして流れ込む
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    video_id INTEGER,
    type TEXT NOT NULL,      -- play / complete / skip / like / purchase / win / lose
    value REAL,
    ts REAL NOT NULL
);

-- ユーザーごとのカテゴリ嗜好ベクトル（推薦・最適化層が更新する）
CREATE TABLE IF NOT EXISTS user_prefs (
    user_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, category)
);

-- モデル訓練層が書き込むグローバル重み
CREATE TABLE IF NOT EXISTS model_weights (
    key TEXT PRIMARY KEY,
    value REAL NOT NULL
);
"""

DEFAULT_WEIGHTS = {
    "w_pref": 1.0,
    "w_elo": 0.6,
    "w_completion": 0.8,
    "w_like": 0.5,
    "w_recency": 0.3,
}


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    for key, value in DEFAULT_WEIGHTS.items():
        conn.execute(
            "INSERT OR IGNORE INTO model_weights (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.commit()
    conn.close()


def is_seeded() -> bool:
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) AS c FROM videos").fetchone()
    conn.close()
    return row["c"] > 0
