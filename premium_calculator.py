"""
ETF 溢价率计算器
使用 AkShare 获取 A股 ETF 实时价格和净值
使用 yfinance 获取纳指期货和汇率数据
"""
import datetime as dt
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

try:
    import akshare as ak
except ImportError:
    ak = None

try:
    import yfinance as yf
except ImportError:
    yf = None


# ETF/LOF 配置信息
# fund_type: "etf" 使用 fund_etf_spot_em, "lof" 使用 fund_lof_spot_em
ETF_CONFIG = {
    # 纳斯达克100指数 ETF
    "513100": {"name": "纳指ETF(国泰)", "index": "NASDAQ-100", "fund_type": "etf"},
    "159941": {"name": "纳指ETF(广发)", "index": "NASDAQ-100", "fund_type": "etf"},
    "159501": {"name": "纳指ETF(嘉实)", "index": "NASDAQ-100", "fund_type": "etf"},
    "159696": {"name": "纳指ETF(易方达)", "index": "NASDAQ-100", "fund_type": "etf"},
    "159513": {"name": "纳斯达克100指数ETF", "index": "NASDAQ-100", "fund_type": "etf"},
    "159632": {"name": "纳斯达克ETF(博时)", "index": "NASDAQ-100", "fund_type": "etf"},
    "513300": {"name": "纳斯达克ETF(华泰)", "index": "NASDAQ-100", "fund_type": "etf"},
    "513390": {"name": "纳指100ETF(南方)", "index": "NASDAQ-100", "fund_type": "etf"},
    "159659": {"name": "纳斯达克100ETF(景顺)", "index": "NASDAQ-100", "fund_type": "etf"},
    "513110": {"name": "纳斯达克100ETF(招商)", "index": "NASDAQ-100", "fund_type": "etf"},
    "513870": {"name": "纳指ETF(富国)", "index": "NASDAQ-100", "fund_type": "etf"},
    "159660": {"name": "纳指100ETF(工银)", "index": "NASDAQ-100", "fund_type": "etf"},
    # 纳斯达克科技/生物科技
    "159509": {"name": "纳指科技ETF", "index": "NASDAQ-TECH", "fund_type": "etf"},
    "513290": {"name": "纳指生物科技ETF", "index": "NASDAQ-BIO", "fund_type": "etf"},
    # 标普信息科技 LOF
    "161128": {"name": "标普信息科技LOF", "index": "S&P-INFO-TECH", "fund_type": "lof"},
}


@dataclass
class ETFPremiumData:
    """ETF 溢价率数据结构"""
    code: str
    name: str
    current_price: Optional[float]  # 当前价格
    yesterday_nav: Optional[float]  # 昨日净值
    estimated_nav: Optional[float]  # 估算净值
    premium_rate: Optional[float]   # 溢价率
    error: Optional[str] = None


@dataclass
class MarketContext:
    """市场环境数据"""
    future_change_pct: Optional[float]  # 期货涨跌幅 %
    forex_rate: Optional[float]         # 汇率
    forex_change_pct: Optional[float]   # 汇率涨跌幅 %
    future_price: Optional[float] = None
    forex_error: Optional[str] = None
    future_error: Optional[str] = None


def get_etf_realtime_price(etf_codes: List[str]) -> Dict[str, Optional[float]]:
    """
    使用 akshare 获取 ETF/LOF 实时价格
    Args:
        etf_codes: 基金代码列表，如 ["513100", "159941", "161128"]
    Returns:
        {etf_code: price} 字典
    """
    if ak is None:
        return {code: None for code in etf_codes}
    
    result = {code: None for code in etf_codes}
    
    # 分离 ETF 和 LOF 代码
    etf_list = [c for c in etf_codes if ETF_CONFIG.get(c, {}).get("fund_type", "etf") == "etf"]
    lof_list = [c for c in etf_codes if ETF_CONFIG.get(c, {}).get("fund_type") == "lof"]
    
    # 获取 ETF 实时行情
    if etf_list:
        try:
            df = ak.fund_etf_spot_em()
            if df is not None and not df.empty:
                code_col = "代码" if "代码" in df.columns else "基金代码"
                price_col = "最新价" if "最新价" in df.columns else "现价"
                
                for code in etf_list:
                    row = df[df[code_col] == code]
                    if not row.empty:
                        price = row.iloc[0][price_col]
                        result[code] = float(price) if pd.notna(price) else None
        except Exception as e:
            st.warning(f"获取 ETF 实时价格失败: {e}")
    
    # 获取 LOF 实时行情
    if lof_list:
        try:
            df = ak.fund_lof_spot_em()
            if df is not None and not df.empty:
                code_col = "代码" if "代码" in df.columns else "基金代码"
                price_col = "最新价" if "最新价" in df.columns else "现价"
                
                for code in lof_list:
                    row = df[df[code_col] == code]
                    if not row.empty:
                        price = row.iloc[0][price_col]
                        result[code] = float(price) if pd.notna(price) else None
        except Exception as e:
            st.warning(f"获取 LOF 实时价格失败: {e}")
    
    return result


def get_etf_nav(etf_code: str) -> Optional[float]:
    """
    使用 akshare 获取 ETF 最新净值
    Args:
        etf_code: ETF 代码
    Returns:
        最新单位净值
    """
    if ak is None:
        return None
    
    try:
        # 获取开放式基金净值
        df = ak.fund_open_fund_info_em(symbol=etf_code, indicator="单位净值走势")
        if df is not None and not df.empty:
            # 取最新的净值
            latest = df.iloc[-1]
            # 列名通常是 "单位净值" 或类似
            nav_col = "单位净值" if "单位净值" in df.columns else df.columns[1]
            return float(latest[nav_col])
    except Exception as e:
        st.warning(f"获取 {etf_code} 净值失败: {e}")
    
    return None

def get_nasdaq_future_change() -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    获取纳指期货/指数的涨跌幅
    优先使用 yfinance，失败时使用 AkShare 纳斯达克指数作为备选
    Returns:
        (涨跌幅百分比, 当前价格, 错误信息)
    """
    errors = []
    
    # 方法1: 尝试 yfinance
    if yf is not None:
        try:
            ticker = yf.Ticker("NQ=F")
            # 使用 fast_info 避免过多请求
            try:
                fast_info = ticker.fast_info
                current_price = getattr(fast_info, 'last_price', None)
                prev_close = getattr(fast_info, 'previous_close', None)
                if current_price and prev_close:
                    change_pct = ((current_price - prev_close) / prev_close) * 100
                    return change_pct, current_price, None
            except Exception:
                pass
            
            # 备选: 使用历史数据
            hist = ticker.history(period="5d", interval="1d")
            if hist is not None and len(hist) >= 2:
                prev_close = hist["Close"].iloc[-2]
                curr_close = hist["Close"].iloc[-1]
                change_pct = ((curr_close - prev_close) / prev_close) * 100
                return change_pct, curr_close, None
        except Exception as e:
            errors.append(f"yfinance: {str(e)[:50]}")
    
    # 方法2: 使用 AkShare 获取纳斯达克综合指数
    if ak is not None:
        try:
            # 使用新浪纳斯达克指数数据
            df = ak.index_us_stock_sina(symbol=".IXIC")
            if df is not None and not df.empty and len(df) >= 2:
                # 获取最近两天数据计算涨跌幅
                curr_close = float(df.iloc[-1]["close"])
                prev_close = float(df.iloc[-2]["close"])
                change_pct = ((curr_close - prev_close) / prev_close) * 100
                return change_pct, curr_close, None
        except Exception as e:
            errors.append(f"akshare纳指: {str(e)[:50]}")
    
    error_msg = "; ".join(errors) if errors else "无法获取期货/指数数据"
    return None, None, error_msg


def get_forex_usd_cny() -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    获取美元兑人民币汇率
    优先使用 yfinance，失败时使用 AkShare 作为备选
    Returns:
        (汇率, 涨跌幅百分比, 错误信息)
    """
    errors = []
    
    # 方法1: 尝试 yfinance
    if yf is not None:
        try:
            ticker = yf.Ticker("CNY=X")
            try:
                fast_info = ticker.fast_info
                rate = getattr(fast_info, 'last_price', None)
                prev_close = getattr(fast_info, 'previous_close', None)
                if rate and prev_close:
                    change_pct = ((rate - prev_close) / prev_close) * 100
                    return rate, change_pct, None
            except Exception:
                pass
            
            hist = ticker.history(period="5d", interval="1d")
            if hist is not None and len(hist) >= 1:
                rate = hist["Close"].iloc[-1]
                if len(hist) >= 2:
                    prev = hist["Close"].iloc[-2]
                    change_pct = ((rate - prev) / prev) * 100
                else:
                    change_pct = 0.0
                return rate, change_pct, None
        except Exception as e:
            errors.append(f"yfinance: {str(e)[:50]}")
    
    # 方法2: 使用 AkShare 获取汇率
    if ak is not None:
        try:
            # 使用外汇实时数据 - fx_spot_quote 返回的列是 ['货币对', '买报价', '卖报价']
            df = ak.fx_spot_quote()
            if df is not None and not df.empty:
                usd_cny = df[df["货币对"] == "USD/CNY"]
                if not usd_cny.empty:
                    # 使用买报价作为汇率
                    rate = float(usd_cny.iloc[0]["买报价"])
                    # fx_spot_quote 没有涨跌幅，设为0
                    return rate, 0.0, None
        except Exception as e:
            errors.append(f"akshare外汇: {str(e)[:50]}")
        
        try:
            # 备选: 使用中国银行汇率
            df = ak.currency_boc_sina()
            if df is not None and not df.empty:
                # 取最新一行（按日期排序后）
                latest = df.iloc[-1]
                rate = float(latest.get("中行汇买价", 0)) / 100  # 转换单位
                if rate > 0:
                    return rate, 0.0, None  # BOC 数据没有涨跌幅
        except Exception as e:
            errors.append(f"akshare中行: {str(e)[:50]}")
    
    error_msg = "; ".join(errors) if errors else "无法获取汇率数据"
    return None, None, error_msg


@st.cache_data(ttl=300)  # 缓存5分钟
def get_market_context_cached() -> Tuple[Optional[float], Optional[float], Optional[str], Optional[float], Optional[float], Optional[str]]:
    """获取市场环境数据（带缓存）"""
    future_change, future_price, future_err = get_nasdaq_future_change()
    forex_rate, forex_change, forex_err = get_forex_usd_cny()
    return future_change, future_price, future_err, forex_rate, forex_change, forex_err


def get_market_context() -> MarketContext:
    """获取市场环境数据（期货和汇率）"""
    future_change, future_price, future_err, forex_rate, forex_change, forex_err = get_market_context_cached()
    
    return MarketContext(
        future_change_pct=future_change,
        future_price=future_price,
        forex_rate=forex_rate,
        forex_change_pct=forex_change,
        future_error=future_err,
        forex_error=forex_err,
    )


def calc_premium(etf_codes: Optional[List[str]] = None) -> Tuple[List[ETFPremiumData], MarketContext]:
    """
    计算 ETF 溢价率
    
    核心公式：
    Estimated_NAV = Yesterday_NAV * (1 + Future_Percent_Change/100) * (1 + Forex_Change/100)
    Premium_Rate = (Current_ETF_Price - Estimated_NAV) / Estimated_NAV
    
    Args:
        etf_codes: ETF 代码列表，默认使用预设的 513100 和 159941
    
    Returns:
        (ETF溢价数据列表, 市场环境数据)
    """
    if etf_codes is None:
        etf_codes = list(ETF_CONFIG.keys())
    
    # 1. 获取市场环境数据
    context = get_market_context()
    
    # 2. 获取 ETF 实时价格
    prices = get_etf_realtime_price(etf_codes)
    
    # 3. 计算每个 ETF 的溢价率
    results = []
    
    for code in etf_codes:
        config = ETF_CONFIG.get(code, {"name": code, "index": "Unknown"})
        
        # 获取当前价格
        current_price = prices.get(code)
        
        # 获取昨日净值
        nav = get_etf_nav(code)
        
        # 计算估值和溢价率
        estimated_nav = None
        premium_rate = None
        error = None
        
        if current_price is None:
            error = "无法获取实时价格"
        elif nav is None:
            error = "无法获取净值"
        elif context.future_change_pct is None:
            error = "无法获取期货数据"
        else:
            # 核心计算
            future_factor = 1 + (context.future_change_pct / 100)
            forex_factor = 1 + ((context.forex_change_pct or 0) / 100)
            estimated_nav = nav * future_factor * forex_factor
            premium_rate = (current_price - estimated_nav) / estimated_nav
        
        results.append(ETFPremiumData(
            code=code,
            name=config["name"],
            current_price=current_price,
            yesterday_nav=nav,
            estimated_nav=estimated_nav,
            premium_rate=premium_rate,
            error=error,
        ))
    
    return results, context


def get_action_recommendation(premium_rate: Optional[float]) -> Tuple[str, str]:
    """
    根据溢价率给出操作建议
    Args:
        premium_rate: 溢价率 (小数形式，如 0.03 表示 3%)
    Returns:
        (操作建议, 颜色标识)
    """
    if premium_rate is None:
        return "数据不足", "⚪️"
    
    pct = premium_rate * 100  # 转换为百分比
    
    if pct > 3:
        return "卖出/轮动", "🔴"
    elif pct < 0:
        return "买入 (折价黄金坑)", "🟢"
    elif pct <= 2:
        return "持有 (正常)", "⚪️"
    else:  # 2-3%
        return "观望 (溢价偏高)", "🟠"


def format_premium_output(results: List[ETFPremiumData], context: MarketContext) -> str:
    """
    格式化输出溢价率计算结果
    """
    lines = []
    lines.append("=" * 60)
    lines.append("📊 A股跨境ETF溢价率实时监控")
    lines.append("=" * 60)
    
    # 市场环境信息
    lines.append("\n📈 市场环境:")
    if context.future_change_pct is not None:
        sign = "+" if context.future_change_pct >= 0 else ""
        lines.append(f"  纳指期货 (NQ=F): {sign}{context.future_change_pct:.2f}%")
    else:
        lines.append(f"  纳指期货: {context.future_error or '数据不可用'}")
    
    if context.forex_rate is not None:
        sign = "+" if (context.forex_change_pct or 0) >= 0 else ""
        lines.append(f"  美元/人民币: {context.forex_rate:.4f} ({sign}{context.forex_change_pct or 0:.2f}%)")
    else:
        lines.append(f"  美元/人民币: {context.forex_error or '数据不可用'}")
    
    lines.append("\n" + "-" * 60)
    lines.append("ETF 溢价率:")
    lines.append("-" * 60)
    
    for data in results:
        if data.error:
            lines.append(f"[{data.code}] {data.name}: ⚠️ {data.error}")
        else:
            premium_pct = data.premium_rate * 100 if data.premium_rate else 0
            sign = "+" if premium_pct >= 0 else ""
            emoji = "🔴" if premium_pct > 0 else "🟢"
            action, _ = get_action_recommendation(data.premium_rate)
            
            lines.append(
                f"[{data.code}] 现价: {data.current_price:.3f} | "
                f"估值: {data.estimated_nav:.3f} | "
                f"溢价率: {sign}{premium_pct:.2f}% {emoji}"
            )
    
    lines.append("=" * 60)
    return "\n".join(lines)


def render_premium_dashboard():
    """
    在 Streamlit 中渲染溢价率监控仪表盘
    """
    st.subheader("🌏 跨境搬砖 - A股纳指ETF溢价监控")
    
    # 顶部控制栏
    col_refresh, col_sort, col_time = st.columns([1, 2, 2])
    with col_refresh:
        if st.button("🔄 刷新数据", key="refresh_premium"):
            st.cache_data.clear()
            st.rerun()
    with col_sort:
        sort_option = st.selectbox(
            "排序方式",
            options=["默认顺序", "溢价率 ↑ 升序", "溢价率 ↓ 降序"],
            key="sort_premium",
            label_visibility="collapsed"
        )
    with col_time:
        st.caption(f"更新时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 获取数据
    with st.spinner("正在获取实时数据..."):
        results, context = calc_premium()
    
    # 市场环境卡片
    st.markdown("### 📈 市场环境")
    col1, col2 = st.columns(2)
    
    with col1:
        if context.future_change_pct is not None:
            delta_color = "normal" if context.future_change_pct >= 0 else "inverse"
            st.metric(
                "纳指期货 (NQ=F)",
                f"{context.future_price:,.0f}" if context.future_price else "N/A",
                f"{context.future_change_pct:+.2f}%",
                delta_color=delta_color
            )
        else:
            st.metric("纳指期货 (NQ=F)", "数据不可用", context.future_error or "")
    
    with col2:
        if context.forex_rate is not None:
            change_pct = context.forex_change_pct or 0
            delta_color = "inverse" if change_pct >= 0 else "normal"  # 人民币升值是好事
            st.metric(
                "美元/人民币 (CNY=X)",
                f"{context.forex_rate:.4f}",
                f"{change_pct:+.2f}%",
                delta_color=delta_color
            )
        else:
            st.metric("美元/人民币", "数据不可用", context.forex_error or "")
    
    st.divider()
    
    # ETF 溢价表格
    st.markdown(f"### 🏦 ETF 溢价率 ({len(results)} 只)")
    
    # 根据排序选项排序 results
    if sort_option == "溢价率 ↑ 升序":
        # 将有 error 的放最后，其他按溢价率升序
        results_sorted = sorted(results, key=lambda x: (x.error is not None, x.premium_rate or float('inf')))
    elif sort_option == "溢价率 ↓ 降序":
        # 将有 error 的放最后，其他按溢价率降序
        results_sorted = sorted(results, key=lambda x: (x.error is not None, -(x.premium_rate or float('-inf'))))
    else:
        results_sorted = results
    
    # 构建表格数据
    table_data = []
    for data in results_sorted:
        if data.error:
            row = {
                "ETF代码": data.code,
                "名称": data.name,
                "现价": "N/A",
                "昨日净值": "N/A",
                "估算净值": "N/A",
                "实时溢价率": "N/A",
                "溢价率值": float('inf'),  # 用于内部排序
                "建议操作": f"⚠️ {data.error}",
            }
        else:
            premium_pct = data.premium_rate * 100 if data.premium_rate else 0
            action, emoji = get_action_recommendation(data.premium_rate)
            
            row = {
                "ETF代码": data.code,
                "名称": data.name,
                "现价": f"{data.current_price:.3f}",
                "昨日净值": f"{data.yesterday_nav:.4f}" if data.yesterday_nav else "N/A",
                "估算净值": f"{data.estimated_nav:.4f}" if data.estimated_nav else "N/A",
                "实时溢价率": f"{premium_pct:+.2f}%",
                "溢价率值": premium_pct,  # 用于内部排序
                "建议操作": f"{emoji} {action}",
            }
        table_data.append(row)
    
    df = pd.DataFrame(table_data)
    # 移除内部排序列
    df_display = df.drop(columns=["溢价率值"])
    
    # 样式函数
    def highlight_premium(val):
        if isinstance(val, str) and "%" in val:
            try:
                pct = float(val.replace("%", "").replace("+", ""))
                if pct > 3:
                    return "background-color: rgba(255,0,0,0.2); color: #ff4444; font-weight: bold"
                elif pct < 0:
                    return "background-color: rgba(0,255,0,0.2); color: #00cc00; font-weight: bold"
            except ValueError:
                pass
        return ""
    
    def highlight_action(val):
        if "🔴" in str(val):
            return "background-color: rgba(255,0,0,0.15); color: #ff4444"
        elif "🟢" in str(val):
            return "background-color: rgba(0,255,0,0.15); color: #00cc00"
        elif "🟠" in str(val):
            return "background-color: rgba(255,165,0,0.15); color: #ffa500"
        return ""
    
    styled_df = df_display.style.map(highlight_premium, subset=["实时溢价率"]).map(
        highlight_action, subset=["建议操作"]
    )
    
    st.dataframe(styled_df, width="stretch", hide_index=True)
    
    # 图例说明
    with st.expander("📚 指标说明"):
        st.markdown("""
        **计算公式:**
        - `估算净值 = 昨日净值 × (1 + 期货涨跌幅) × (1 + 汇率涨跌幅)`
        - `溢价率 = (现价 - 估算净值) / 估算净值`
        
        **操作建议:**
        - 🔴 **溢价 > 3%**: 卖出/轮动 - 溢价过高，可考虑卖出套利或轮动到其他标的
        - 🟠 **溢价 2-3%**: 观望 - 溢价偏高，不建议追高
        - ⚪️ **溢价 0-2%**: 持有 - 正常范围
        - 🟢 **折价 < 0%**: 买入黄金坑 - 折价难得，可考虑买入
        
        **数据来源:**
        - ETF 实时价格: 东方财富 (via AkShare)
        - ETF 净值: 东方财富 (via AkShare)
        - 纳指期货: Yahoo Finance (NQ=F)
        - 汇率: Yahoo Finance (CNY=X)
        """)


# 命令行测试
if __name__ == "__main__":
    results, context = calc_premium()
    print(format_premium_output(results, context))
