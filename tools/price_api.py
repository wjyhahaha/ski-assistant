#!/usr/bin/env python3
"""
flyai CLI 桥接工具
用法:
  python tools/price_api.py search-flight '<json>'
  python tools/price_api.py search-hotel '<json>'
  python tools/price_api.py search-poi '<json>'
  python tools/price_api.py check

仅负责调用 flyai CLI 并返回原始 JSON 结果，所有格式化和降级逻辑由 Agent 完成。
"""

import json
import subprocess
import sys


def flyai_available() -> bool:
    """检测 flyai CLI 是否已安装"""
    try:
        r = subprocess.run(["flyai", "--help"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def run_flyai(args: list, timeout: int = 20) -> dict:
    """运行 flyai 命令并返回解析后的 JSON"""
    try:
        r = subprocess.run(["flyai"] + args, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return {"error": f"flyai 返回错误码 {r.returncode}", "stderr": r.stderr[:500]}
        data = json.loads(r.stdout)
        if data.get("status") == 0:
            return data
        return {"error": f"flyai 返回状态异常: {data.get('status')}", "raw": r.stdout[:500]}
    except subprocess.TimeoutExpired:
        return {"error": f"flyai 执行超时（{timeout}s）"}
    except json.JSONDecodeError:
        return {"error": "flyai 输出非 JSON 格式", "raw": r.stdout[:500]}
    except FileNotFoundError:
        return {"error": "flyai 未安装，请先安装 flyai CLI"}
    except Exception as e:
        return {"error": str(e)}


def search_flight(params: dict) -> dict:
    """搜索机票"""
    args = ["search-flight",
            "--origin", params.get("from_city", ""),
            "--destination", params.get("to_city", ""),
            "--dep-date", params.get("date", ""),
            "--sort-type", "3"]
    return run_flyai(args)


def search_hotel(params: dict) -> dict:
    """搜索酒店"""
    args = ["search-hotel",
            "--dest-name", params.get("destination", ""),
            "--check-in-date", params.get("check_in", ""),
            "--check-out-date", params.get("check_out", ""),
            "--sort", params.get("sort", "price_asc")]
    if params.get("poi_name"):
        args += ["--poi-name", params["poi_name"]]
    if params.get("max_price"):
        args += ["--max-price", str(params["max_price"])]
    return run_flyai(args)


def search_poi(params: dict) -> dict:
    """搜索景点/门票"""
    args = ["search-poi",
            "--city-name", params.get("city", "")]
    if params.get("category"):
        args += ["--category", params["category"]]
    if params.get("keyword"):
        args += ["--keyword", params["keyword"]]
    return run_flyai(args)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "check":
        available = flyai_available()
        print(json.dumps({"available": available}))
    elif cmd in ("search-flight", "search-hotel", "search-poi"):
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
        funcs = {
            "search-flight": search_flight,
            "search-hotel": search_hotel,
            "search-poi": search_poi,
        }
        result = funcs[cmd](params)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)
