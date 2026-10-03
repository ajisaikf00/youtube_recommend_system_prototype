"""
基盤層 - モデル訓練（オフラインバッチ）
==========================================
events テーブルに溜まったログから「どの特徴がエンゲージメントに効いているか」を
ごく単純なロジスティック回帰（外部MLライブラリなし・純粋なPythonのループ）で
再学習し、model_weights テーブルを更新する。

実サービスなら Spark / SageMaker 等の学習基盤で日次バッチ実行するような処理を、
このデモでは `python model_training.py` を手動実行することで再現する。
"""

import math

from db import get_connection

LEARNING_RATE = 0.1
EPOCHS = 200


def _build_training_set():
    """
    events を "そのビデオの現在の集計値" を特徴量として、
    complete/like/purchase を正例(1)、skip を負例(0) としたデータセットに変換する。
    （簡略化のため、イベント発生"時点"ではなく"現在"の集計値を特徴として使う）
    """
    conn = get_connection()
    events = conn.execute(
        "SELECT video_id, type FROM events WHERE type IN ('complete','skip','like','purchase')"
    ).fetchall()
    videos = {
        row["id"]: row
        for row in conn.execute("SELECT * FROM videos").fetchall()
    }
    conn.close()

    X, y = [], []
    for e in events:
        video = videos.get(e["video_id"])
        if not video:
            continue
        impressions = max(video["impressions"], 1)
        elo_norm = max(-1.0, min(1.0, (video["elo"] - 1500) / 400))
        completion_rate = video["completes"] / impressions
        like_rate = video["likes"] / impressions
        label = 0.0 if e["type"] == "skip" else 1.0
        X.append([1.0, elo_norm, completion_rate, like_rate])  # [bias, elo, completion, like]
        y.append(label)
    return X, y


def _sigmoid(z):
    z = max(-30, min(30, z))  # オーバーフロー防止
    return 1 / (1 + math.exp(-z))


def _train_logistic_regression(X, y):
    n_features = len(X[0])
    w = [0.0] * n_features

    for _ in range(EPOCHS):
        grads = [0.0] * n_features
        for xi, yi in zip(X, y):
            pred = _sigmoid(sum(wj * xj for wj, xj in zip(w, xi)))
            error = pred - yi
            for j in range(n_features):
                grads[j] += error * xi[j]
        for j in range(n_features):
            w[j] -= LEARNING_RATE * grads[j] / len(X)
    return w  # [bias, w_elo, w_completion, w_like]


def recompute_weights():
    X, y = _build_training_set()
    if len(X) < 10:
        print(f"学習データが{len(X)}件しかありません（10件以上でモデルを更新します）。"
              " まずデモUIを操作してイベントを増やしてください。")
        return

    _, w_elo, w_completion, w_like = _train_logistic_regression(X, y)

    conn = get_connection()
    for key, value in [
        ("w_elo", abs(w_elo)),
        ("w_completion", abs(w_completion)),
        ("w_like", abs(w_like)),
    ]:
        conn.execute(
            "UPDATE model_weights SET value=? WHERE key=?", (round(value, 4), key)
        )
    conn.commit()
    conn.close()
    print(f"{len(X)}件のイベントから再学習しました: "
          f"w_elo={w_elo:.4f}, w_completion={w_completion:.4f}, w_like={w_like:.4f}")


if __name__ == "__main__":
    recompute_weights()
