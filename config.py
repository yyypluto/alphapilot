PAGE_CONFIG = {
    "page_title": "AlphaPilot - 工程师的个人美股投资驾驶舱",
    "page_icon": "🚀",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

TARGET_ETFS = ["VOO", "QQQ", "QLD", "TQQQ", "SMH", "TLT"]
MACRO_TICKERS = ["^VIX", "^TNX"]
TIME_RANGES = ["1y", "2y", "5y"]

ETF_INFO = {
    "VOO": {
        "name": "Vanguard S&P 500 ETF",
        "desc": "🇺🇸 **美国国运基石**。追踪标普 500 指数，包含美国最大的 500 家上市公司。它是你投资组合的压舱石。",
        "relation": "基准指数。所有其他资产都应参考与 VOO 的相关性。",
        "strategy": "核心仓位 (40-50%)"
    },
    "QQQ": {
        "name": "Invesco QQQ Trust",
        "desc": "💻 **科技成长引擎**。追踪纳斯达克 100 指数，重仓 Apple, Microsoft, Nvidia 等科技巨头。",
        "relation": "高贝塔 (High Beta) 资产。通常在牛市中跑赢 VOO，熊市中跌幅更大。",
        "strategy": "进攻仓位 (30-40%)"
    },
    "QLD": {
        "name": "ProShares Ultra QQQ (2x)",
        "desc": "🚀 **2倍做多纳指**。追求纳斯达克指数单日表现的 2 倍回报。",
        "relation": "杠杆资产。波动极大，适合在明确的牛市趋势中使用。注意损耗！",
        "strategy": "波段交易 (0-10%)。不建议长期“死拿”，除非在强劲牛市中。"
    },
    "TQQQ": {
        "name": "ProShares UltraPro QQQ (3x)",
        "desc": "🎰 **3倍做多纳指**。风险极高，收益也极高。俗称“纳指三倍做多”。",
        "relation": "极高风险。巨大的波动率损耗（Volatility Decay）。市场震荡时会亏损。",
        "strategy": "短线博弈 (<5%)。仅在极度恐慌反弹或主升浪时持有，严设止损。"
    },
    "SMH": {
        "name": "VanEck Semiconductor ETF",
        "desc": "⚡️ **算力时代的石油**。追踪半导体指数，重仓 Nvidia, TSMC, AMD。AI 时代的核心受益者。",
        "relation": "极高波动性。与 QQQ 高度相关，但爆发力更强。",
        "strategy": "卫星仓位 (10-20%)"
    },
    "TLT": {
        "name": "iShares 20+ Year Treasury Bond ETF",
        "desc": "🛡️ **长期国债防守**。追踪美国 20 年期以上国债。通常在经济衰退或股市暴跌时上涨（避险属性）。",
        "relation": "负相关资产。理想情况下与股票走势相反，用于对冲风险。",
        "strategy": "对冲仓位 (0-10%)"
    }
}

INDICATOR_INFO = {
    "MA20 (黄线)": "短期趋势线。价格在上方代表短期强势。若价格跌破 MA20，可能是短线回调信号。",
    "MA200 (蓝线)": "牛熊分界线。价格在上方代表长期牛市。价格回踩 MA200 且不跌破，通常是绝佳买点（黄金坑）。",
    "RSI (相对强弱)": "衡量超买超卖。\n• >70: 超买（可能回调，分批止盈）\n• <30: 超卖（可能反弹，分批买入）",
    "MACD (趋势)": "由快线(蓝)、慢线(橙)和柱状图组成。\n• 金叉（蓝线上穿橙线）：买入信号\n• 死叉（蓝线下穿橙线）：卖出信号\n• 柱状图翻红：上涨动能增强",
    "Bollinger Bands (布林带)": "由中轨(MA20)和上下两条标准差线组成。\n• 价格触及上轨：压力位，可能回调\n• 价格触及下轨：支撑位，可能反弹\n• 开口收窄：变盘前兆"
}

# Networking defaults
YAHOO_USER_AGENT = "Mozilla/5.0"
REQUEST_TIMEOUT = 15
