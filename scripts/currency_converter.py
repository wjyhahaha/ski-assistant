#!/usr/bin/env python3
"""
实时汇率换算工具
用法: python scripts/currency_converter.py <amount> <from> <to>
示例: python scripts/currency_converter.py 7800 JPY CNY

支持币种: CNY, JPY, KRW, CHF, EUR, CAD, USD, NZD, AUD, GBP
"""

import json
import os
import sys
import urllib.request

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from utils import track_usage

# 备用静态汇率（基于 2024-25 雪季参考值，当无法联网时使用）
FALLBACK_RATES_TO_CNY = {
    "CNY": 1.0,
    "JPY": 0.048,     # 1 JPY ≈ 0.048 CNY
    "KRW": 0.0053,    # 1 KRW ≈ 0.0053 CNY
    "CHF": 8.2,       # 1 CHF ≈ 8.2 CNY
    "EUR": 7.9,       # 1 EUR ≈ 7.9 CNY
    "CAD": 5.3,       # 1 CAD ≈ 5.3 CNY
    "USD": 7.25,      # 1 USD ≈ 7.25 CNY
    "NZD": 4.4,       # 1 NZD ≈ 4.4 CNY
    "AUD": 4.8,       # 1 AUD ≈ 4.8 CNY
    "GBP": 9.2,       # 1 GBP ≈ 9.2 CNY
}


def get_live_rate(from_currency: str, to_currency: str):
    """尝试获取实时汇率，返回 (rate, is_live)"""
    import time as _time
    url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ski-assistant/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                rates = data.get("rates", {})
                if to_currency in rates:
                    return rates[to_currency], True
        except Exception:
            if attempt < 2:
                _time.sleep(0.5 * (attempt + 1))
    return None, False


def convert(amount: float, from_cur: str, to_cur: str) -> dict:
    from_cur = from_cur.upper()
    to_cur = to_cur.upper()

    # Try live rate first
    rate, is_live = get_live_rate(from_cur, to_cur)

    if rate is None:
        # Fallback to static rates via CNY pivot
        from_rate = FALLBACK_RATES_TO_CNY.get(from_cur)
        to_rate = FALLBACK_RATES_TO_CNY.get(to_cur)
        if from_rate and to_rate:
            rate = from_rate / to_rate
            is_live = False
        else:
            return {"error": f"不支持的币种: {from_cur} 或 {to_cur}"}

    result_amount = amount * rate

    return {
        "from": {"amount": amount, "currency": from_cur},
        "to": {"amount": round(result_amount, 2), "currency": to_cur},
        "rate": round(rate, 6),
        "is_live": is_live,
        "note": "实时汇率" if is_live else "参考汇率（离线备用值，可能有偏差）",
    }


def format_result(result: dict) -> str:
    if "error" in result:
        return f"❌ {result['error']}"

    f = result["from"]
    t = result["to"]
    return (
        f"{f['currency']} {f['amount']:,.2f} = {t['currency']} {t['amount']:,.2f}\n"
        f"汇率: 1 {f['currency']} = {result['rate']} {t['currency']}\n"
        f"数据来源: {result['note']}"
    )


if __name__ == "__main__":
    if len(sys.argv) == 4:
        amount = float(sys.argv[1])
        from_cur = sys.argv[2]
        to_cur = sys.argv[3]
    elif len(sys.argv) == 2:
        params = json.loads(sys.argv[1])
        amount = params["amount"]
        from_cur = params["from"]
        to_cur = params["to"]
    else:
        print("用法: python currency_converter.py <amount> <from> <to>")
        print("示例: python currency_converter.py 7800 JPY CNY")
        sys.exit(1)

    result = convert(amount, from_cur, to_cur)
    track_usage("currency_converter.convert")
    print(format_result(result))
