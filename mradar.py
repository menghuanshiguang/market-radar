#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mradar — 大盘月线MACD雷达
检测各主要指数的月线MACD状态: 金叉健康/金叉垂死/刚死叉/死叉收敛/死叉扩大
用法:
  mradar                    # 扫描全部指数
  mradar sh000001           # 单指数详细(含近8月轨迹+信号历史)
  mradar --all              # 同默认
"""
import json, sys, urllib.request, datetime

# 指数列表: (代码, 市场, 名称, 对应ETF, 类型)
INDICES = [
    ("000001", "sh", "上证指数", "510050/510880", "a"),
    ("000016", "sh", "上证50",  "510050",        "a"),
    ("399001", "sz", "深证成指", "159903",        "a"),
    ("399006", "sz", "创业板指", "159915",        "a"),
    ("000300", "sh", "沪深300",  "510300",        "a"),
    ("000905", "sh", "中证500",  "510500",        "a"),
    ("000852", "sh", "中证1000", "512100",        "a"),
    ("000688", "sh", "科创50",   "588000",        "a"),
    ("HSI",    "h",  "恒生指数",  "513660",        "h"),
    ("HSTECH", "h",  "恒生科技",  "513180",        "h"),
    ("HSCEI",  "h",  "国企指数",  "510900",        "h"),
    ("IXIC",   "u",  "纳斯达克",  "513100(纳指QDII)", "u"),
    ("INX",    "u",  "标普500",  "513500(标普QDII)", "u"),
    ("DJI",    "u",  "道琼斯",   "无直接QDII",      "u"),
]

def get_monthly(code, mtype):
    merged = {}
    for s, e in [("2019-01-01", "2022-12-31"), ("2023-01-01", "2026-12-31")]:
        try:
            if mtype == "h":
                url = f"https://ifzq.gtimg.cn/appstock/app/hkfqkline/get?param=hk{code},month,{s},{e},640,qfq"
                key = f"hk{code}"
            elif mtype == "u":
                url = f"https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get?param=us{code},month,{s},{e},640,qfq"
                key = f"us{code}"
            else:
                url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={mtype}{code},month,{s},{e},640,"
                key = f"{mtype}{code}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            d = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
            node = d["data"][key]
            arr = node.get("month") or node.get("qfqmonth") or node.get("day") or node.get("qfqday")
            if not arr:
                continue
            for k in arr:
                merged[k[0]] = float(k[2])
        except Exception:
            pass
    return merged

def macd_all(closes):
    def ema(vals, n):
        k = 2 / (n + 1); e = vals[0]; out = [e]
        for v in vals[1:]:
            e = v * k + e * (1 - k); out.append(e)
        return out
    e12, e26 = ema(closes, 12), ema(closes, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = ema(dif, 9)
    return dif, dea

def classify(dif, dea, dates):
    """返回 (状态, 说明)"""
    d1, e1 = dif[-1], dea[-1]
    hist = [(dif[i] - dea[i]) * 2 for i in range(len(dif))]
    h3 = hist[-3:]  # 近3月柱
    if d1 > e1:
        # 金叉
        if h3[-1] > h3[-2]:
            return "金叉健康", f"柱{h3[-1]:+.0f}(回升)"
        if abs(h3[-1]) < 40:
            return "金叉垂死", f"柱{h3[-1]:+.0f}贴零轴(即将死叉)"
        return "金叉转弱", f"柱{h3[-1]:+.0f}连续收缩(3月:{h3[0]:+.0f}→{h3[-1]:+.0f})"
    else:
        # 死叉: 找死叉月份 + 柱趋势
        cross_m = None
        for i in range(len(dif) - 1, 0, -1):
            if dif[i - 1] >= dea[i - 1] and dif[i] < dea[i]:
                cross_m = dates[i][:7]
                break
        # 刚死叉: 死叉发生在最近2个月内
        if cross_m and cross_m >= dates[-2][:7]:
            return "刚死叉", f"{cross_m}死叉 柱{h3[-1]:+.0f}(第1-2月)"
        a = [abs(x) for x in h3]
        if a[2] < a[0]:
            return "死叉收敛", f"{cross_m}死叉 柱{h3[-1]:+.0f}(绿柱缩短,或修复)"
        return "死叉扩大", f"{cross_m}死叉 柱{h3[-1]:+.0f}(绿柱扩大,恶化)"

def analyze_one(code, mtype, name, etf):
    m = get_monthly(code, mtype)
    if len(m) < 35:
        return None
    dates = sorted(m)
    closes = [m[d] for d in dates]
    dif, dea = macd_all(closes)
    state, note = classify(dif, dea, dates)
    # 死叉后跌幅
    dd = None
    if state.startswith("死叉"):
        for i in range(len(dif) - 1, 0, -1):
            if dif[i - 1] >= dea[i - 1] and dif[i] < dea[i]:
                dd = (closes[-1] / closes[i] - 1) * 100
                break
    return {
        "name": name, "etf": etf, "state": state, "note": note,
        "dif": dif[-1], "dea": dea[-1], "price": closes[-1],
        "dd": dd, "hist3": [(dif[i] - dea[i]) * 2 for i in range(-3, 0)],
        "dates": dates, "closes": closes, "dif_all": dif, "dea_all": dea,
    }

def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return

    if args and args[0] in ("--all",):
        args = []

    if args:
        # 单指数详细
        code = args[0]
        mtype = None
        if code.startswith("sh"): mtype, code = "sh", code[2:]
        elif code.startswith("sz"): mtype, code = "sz", code[2:]
        elif code.startswith("hk"): mtype, code = "h", code[2:]
        elif code.startswith("us"): mtype, code = "u", code[2:]
        for c, mt, name, etf, t in INDICES:
            if c == code and (mtype is None or mt == mtype):
                r = analyze_one(c, mt, name, etf)
                if not r:
                    print(f"{name}: 数据不足"); return
                print(f"=== {name} ({c}) 月线MACD ===")
                print(f"状态: [{r['state']}] {r['note']}")
                print(f"DIF={r['dif']:+.1f} DEA={r['dea']:+.1f} 点位{r['price']:,.0f}")
                if r['dd'] is not None:
                    print(f"死叉以来: {r['dd']:+.1f}%")
                print(f"近8月轨迹:")
                for i in range(-8, 0):
                    hist = (r['dif_all'][i] - r['dea_all'][i]) * 2
                    print(f"  {r['dates'][i][:7]}: 收{r['closes'][i]:,.0f} 柱{hist:+.0f}")
                return
        print(f"未找到 {args[0]}")
        return

    # 全量扫描
    print(f"=== 大盘月线MACD雷达 {datetime.date.today()} ===")
    results = []
    for code, mtype, name, etf, t in INDICES:
        r = analyze_one(code, mtype, name, etf)
        if r:
            results.append(r)
    order = {"金叉健康": 0, "金叉转弱": 1, "金叉垂死": 2, "刚死叉": 3, "死叉收敛": 4, "死叉扩大": 5}
    results.sort(key=lambda x: (order.get(x["state"], 9), -x["hist3"][-1]))
    print(f"{'指数':8s} {'状态':>8s} {'月线柱':>8s} {'说明':>28s} {'对应ETF':>14s}")
    for r in results:
        mark = {"金叉健康": "🟢", "金叉转弱": "🟡", "金叉垂死": "🟡", "死叉收敛": "🟠", "刚死叉": "🔴", "死叉扩大": "🔴"}.get(r["state"], "")
        print(f"{r['name']:8s} {mark}{r['state']:>8s} {r['hist3'][-1]:>+8.0f} {r['note']:>28s} {r['etf']:>14s}")
    print("\n🟢金叉健康=柱扩大可做多  🟡金叉垂死=收敛将死叉   🟠死叉收敛=或修复")
    print("🔴死叉=按月线策略回避/清仓(上证死叉则全A股半导体策略空仓)")

if __name__ == "__main__":
    main()
