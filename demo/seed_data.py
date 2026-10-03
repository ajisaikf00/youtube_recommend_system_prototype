"""
架空のユーザー・動画データを投入するスクリプト。
外部データソースは使わず、すべてローカルで生成する。
"""

import random

from db import get_connection, init_db, is_seeded

CATEGORIES = ["料理", "ゲーム実況", "音楽", "旅行Vlog", "ガジェット紹介"]

USER_NAMES = ["田中", "佐藤", "鈴木", "高橋", "伊藤"]


def seed():
    init_db()
    if is_seeded():
        print("既に投入済みです（demo.db を削除すれば再投入できます）")
        return

    conn = get_connection()

    # A/Bテスト: ユーザーを交互に control(A) / treatment(B) へ割り当てる
    for i, name in enumerate(USER_NAMES):
        variant = "A" if i % 2 == 0 else "B"
        conn.execute(
            "INSERT INTO users (id, name, ab_variant) VALUES (?, ?, ?)",
            (i + 1, name, variant),
        )
        for cat in CATEGORIES:
            conn.execute(
                "INSERT INTO user_prefs (user_id, category, weight) VALUES (?, ?, 0)",
                (i + 1, cat),
            )

    # 架空の動画を60本生成
    video_id = 1
    for cat in CATEGORIES:
        for n in range(12):
            title = f"{cat}#{n + 1} 「{random.choice(['神回', '初挑戦', '総集編', '検証', '雑談', '解説'])}」"
            duration = random.choice([30, 60, 90, 180, 300])
            conn.execute(
                "INSERT INTO videos (id, title, category, duration_sec) VALUES (?, ?, ?, ?)",
                (video_id, title, cat, duration),
            )
            video_id += 1

    conn.commit()
    conn.close()
    print(f"{len(USER_NAMES)}人のユーザーと{video_id - 1}本の動画を投入しました。")


if __name__ == "__main__":
    seed()
