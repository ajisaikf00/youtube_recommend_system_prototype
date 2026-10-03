"""
基盤層 - 外部レコメンドAPI（フック用スタブ）
================================================
実サービスでは、自社のスコアリングに加えて外部のレコメンドMLサービス
（マネージドAPI等）へ候補生成の一部を委譲することがある。

このデモには外部APIを用意していない（＝ネットワーク呼び出しを一切行わない）ため、
常に None を返し、呼び出し側（recommender.py）は完全にローカルロジックへ
フォールバックする。将来、実際の外部APIをつなぐ場合はこの関数の中身だけを
差し替えればよい、という「差し替え可能な境界」を示すためのファイル。
"""

from typing import Optional


def fetch_external_recommendations(user_id: int, k: int = 5) -> Optional[list]:
    """
    本番なら:
        response = requests.post(EXTERNAL_RECO_ENDPOINT, json={...})
        return response.json()["items"]
    のようにHTTPで問い合わせる想定の関数。

    このローカルデモでは外部APIを持たないため常に None を返す。
    """
    return None
