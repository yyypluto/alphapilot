"""
AlphaPilot V7.0 - Intelligent Option Engine
期权选筹模块：根据市场状态自动筛选最佳期权合约

State 0 (Attack): LEAPS Call Selector - 深实值长期看涨期权替代 QLD
State 2 (Escape): Cash-Secured Put Selector - 收租抄底策略
"""

import datetime as dt
from typing import Optional, Dict, Any, List
import pandas as pd

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

try:
    from polygon import RESTClient
    from polygon.rest.models import OptionsContract
    HAS_POLYGON = True
except ImportError:
    HAS_POLYGON = False


class OptionScanner:
    """
    期权扫描器：根据市场状态筛选最佳期权合约
    
    Usage:
        scanner = OptionScanner(ticker='QQQ')
        
        # State 0: 获取 LEAPS Call
        leaps = scanner.scan_leaps_call()
        
        # State 2: 获取 CSP
        csp = scanner.scan_cash_secured_put()
    """
    
    def __init__(self, ticker: str = 'QQQ'):
        """
        初始化期权扫描器
        
        Args:
            ticker: 标的代码，默认 'QQQ'
        """
        self.ticker = ticker.upper()
        self.client: Optional[RESTClient] = None
        self._init_client()
        
    def _init_client(self) -> None:
        """初始化 Polygon API 客户端"""
        if not HAS_POLYGON:
            return
            
        api_key = None
        
        # 1. 尝试从 Streamlit secrets 读取
        if HAS_STREAMLIT:
            try:
                api_key = st.secrets.get("POLYGON_API_KEY")
            except Exception:
                pass
        
        # 2. 尝试从环境变量读取
        if not api_key:
            import os
            api_key = os.environ.get("POLYGON_API_KEY")
        
        if api_key:
            try:
                self.client = RESTClient(api_key)
            except Exception as e:
                print(f"[OptionScanner] Failed to init Polygon client: {e}")
                self.client = None
    
    def is_available(self) -> bool:
        """检查 API 是否可用"""
        return self.client is not None and HAS_POLYGON
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def get_underlying_price(self) -> Optional[float]:
        """
        获取标的当前实时价格
        
        Returns:
            标的现价，失败返回 None
        """
        if not self.is_available():
            return self._get_mock_price()
        
        try:
            # 使用 Polygon 的 last trade 接口
            trade = self.client.get_last_trade(self.ticker)
            if trade and hasattr(trade, 'price'):
                return float(trade.price)
            
            # 备用：使用 previous close
            aggs = list(self.client.list_aggs(
                ticker=self.ticker,
                multiplier=1,
                timespan="day",
                from_=dt.date.today() - dt.timedelta(days=5),
                to=dt.date.today(),
                limit=1
            ))
            if aggs:
                return float(aggs[-1].close)
                
        except Exception as e:
            print(f"[OptionScanner] Error fetching price: {e}")
        
        return self._get_mock_price()
    
    def _get_mock_price(self) -> float:
        """返回模拟价格（用于测试/API 不可用时）"""
        mock_prices = {
            'QQQ': 520.0,
            'SPY': 590.0,
            'IWM': 220.0,
        }
        return mock_prices.get(self.ticker, 500.0)
    
    def fetch_option_chain(
        self,
        min_days: int,
        max_days: int,
        contract_type: str
    ) -> List[Dict[str, Any]]:
        """
        获取期权链并筛选合约
        
        Args:
            min_days: 最小到期天数
            max_days: 最大到期天数
            contract_type: 'call' 或 'put'
            
        Returns:
            筛选后的合约列表，包含 Greeks 和 Open Interest
        """
        if not self.is_available():
            return self._get_mock_option_chain(min_days, max_days, contract_type)
        
        today = dt.date.today()
        min_expiry = today + dt.timedelta(days=min_days)
        max_expiry = today + dt.timedelta(days=max_days)
        
        contracts = []
        
        try:
            # Step 1: 获取合约列表
            options_iter = self.client.list_options_contracts(
                underlying_ticker=self.ticker,
                contract_type=contract_type,
                expiration_date_gte=min_expiry.isoformat(),
                expiration_date_lte=max_expiry.isoformat(),
                limit=250
            )
            
            contract_tickers = []
            contract_info = {}
            
            for opt in options_iter:
                ticker = opt.ticker
                contract_tickers.append(ticker)
                contract_info[ticker] = {
                    'ticker': ticker,
                    'strike': float(opt.strike_price),
                    'expiration': opt.expiration_date,
                    'contract_type': opt.contract_type,
                }
            
            if not contract_tickers:
                return []
            
            # Step 2: 获取 Snapshot（包含 Greeks 和 Open Interest）
            # 分批处理，每批最多 50 个
            batch_size = 50
            for i in range(0, len(contract_tickers), batch_size):
                batch = contract_tickers[i:i + batch_size]
                
                try:
                    snapshots = self.client.get_snapshot_option(
                        underlying_asset=self.ticker,
                        option_contract=batch[0]  # 单个合约
                    )
                    
                    # 处理单个合约的 snapshot
                    if snapshots:
                        self._process_snapshot(snapshots, contract_info, contracts)
                        
                except Exception:
                    # 尝试获取所有期权的 snapshot
                    try:
                        all_snapshots = self.client.list_snapshot_options_chain(
                            underlying_asset=self.ticker,
                            expiration_date_gte=min_expiry.isoformat(),
                            expiration_date_lte=max_expiry.isoformat(),
                        )
                        for snap in all_snapshots:
                            self._process_snapshot(snap, contract_info, contracts)
                    except Exception as e2:
                        print(f"[OptionScanner] Snapshot batch error: {e2}")
                        # 使用基础信息
                        for ticker in batch:
                            if ticker in contract_info:
                                contracts.append(contract_info[ticker])
                        
        except Exception as e:
            print(f"[OptionScanner] Error fetching option chain: {e}")
            return self._get_mock_option_chain(min_days, max_days, contract_type)
        
        return contracts
    
    def _process_snapshot(
        self, 
        snapshot: Any, 
        contract_info: Dict, 
        contracts: List[Dict]
    ) -> None:
        """处理单个 snapshot 数据"""
        try:
            ticker = getattr(snapshot, 'details', {})
            if hasattr(ticker, 'ticker'):
                ticker = ticker.ticker
            elif hasattr(snapshot, 'ticker'):
                ticker = snapshot.ticker
            else:
                return
                
            if ticker not in contract_info:
                return
                
            info = contract_info[ticker].copy()
            
            # Greeks
            greeks = getattr(snapshot, 'greeks', None)
            if greeks:
                info['delta'] = getattr(greeks, 'delta', None)
                info['gamma'] = getattr(greeks, 'gamma', None)
                info['theta'] = getattr(greeks, 'theta', None)
                info['vega'] = getattr(greeks, 'vega', None)
            
            # Open Interest & Volume
            info['open_interest'] = getattr(snapshot, 'open_interest', 0) or 0
            
            # Day data
            day = getattr(snapshot, 'day', None)
            if day:
                info['last_price'] = getattr(day, 'close', None) or getattr(day, 'last', None)
                info['volume'] = getattr(day, 'volume', 0) or 0
            
            # Underlying Price
            underlying = getattr(snapshot, 'underlying_asset', None)
            if underlying:
                info['underlying_price'] = getattr(underlying, 'price', None)
            
            contracts.append(info)
            
        except Exception as e:
            print(f"[OptionScanner] Process snapshot error: {e}")
    
    def _get_mock_option_chain(
        self,
        min_days: int,
        max_days: int,
        contract_type: str
    ) -> List[Dict[str, Any]]:
        """生成模拟期权链数据"""
        underlying_price = self._get_mock_price()
        today = dt.date.today()
        
        # 根据合约类型生成不同的 mock 数据
        if contract_type == 'call':
            # LEAPS Call: 深实值
            strikes = [
                underlying_price * 0.70,  # 30% ITM
                underlying_price * 0.75,
                underlying_price * 0.80,
                underlying_price * 0.85,
                underlying_price * 0.90,
            ]
            deltas = [0.92, 0.88, 0.84, 0.78, 0.72]
            expiry_days = (min_days + max_days) // 2
        else:
            # Put: OTM
            strikes = [
                underlying_price * 0.85,
                underlying_price * 0.90,
                underlying_price * 0.92,
                underlying_price * 0.95,
                underlying_price * 0.97,
            ]
            deltas = [-0.35, -0.28, -0.25, -0.20, -0.15]
            expiry_days = (min_days + max_days) // 2
        
        contracts = []
        expiry_date = today + dt.timedelta(days=expiry_days)
        
        for i, (strike, delta) in enumerate(zip(strikes, deltas)):
            strike = round(strike)
            
            # 估算期权价格
            if contract_type == 'call':
                intrinsic = max(0, underlying_price - strike)
                time_value = underlying_price * 0.08 * (expiry_days / 365)
                price = intrinsic + time_value
            else:
                intrinsic = max(0, strike - underlying_price)
                time_value = underlying_price * 0.03 * (expiry_days / 365) ** 0.5
                price = intrinsic + time_value
            
            contracts.append({
                'ticker': f"O:{self.ticker}{expiry_date.strftime('%y%m%d')}{'C' if contract_type == 'call' else 'P'}{int(strike * 1000):08d}",
                'strike': float(strike),
                'expiration': expiry_date.isoformat(),
                'contract_type': contract_type,
                'delta': delta,
                'gamma': 0.01,
                'theta': -0.05 if contract_type == 'call' else -0.03,
                'vega': 0.15,
                'open_interest': 800 + i * 200,
                'last_price': round(price, 2),
                'volume': 500 + i * 100,
                'underlying_price': underlying_price,
                '_is_mock': True,
            })
        
        return contracts
    
    # =========================================================================
    # Core Logic 1: LEAPS Call Selector (State 0 进攻)
    # =========================================================================
    
    def scan_leaps_call(
        self,
        min_days: int = 365,
        max_days: int = 600,
        min_open_interest: int = 500,
        target_delta_min: float = 0.80,
        target_delta_max: float = 0.90
    ) -> Optional[Dict[str, Any]]:
        """
        扫描 LEAPS Call 期权（用于 State 0 进攻替代 QLD）
        
        目标：寻找替代 QLD 的深实值长期看涨期权
        
        Args:
            min_days: 最小到期天数（默认 365）
            max_days: 最大到期天数（默认 600）
            min_open_interest: 最小持仓量（流动性筛选）
            target_delta_min: 目标 Delta 下限
            target_delta_max: 目标 Delta 上限
            
        Returns:
            最佳合约详情，包含：
            - ticker: 合约代码
            - strike: 行权价
            - expiration: 到期日
            - delta: Delta 值
            - leverage: 理论杠杆率
            - premium_rate: 溢价率
            - days_to_expiry: 剩余天数
        """
        underlying_price = self.get_underlying_price()
        if underlying_price is None:
            return None
        
        # 获取期权链
        contracts = self.fetch_option_chain(min_days, max_days, 'call')
        
        if not contracts:
            return self._create_error_result("未找到符合条件的期权合约")
        
        # 筛选：流动性 + ITM
        filtered = []
        for c in contracts:
            oi = c.get('open_interest', 0) or 0
            strike = c.get('strike', 0)
            delta = c.get('delta')
            
            # 流动性筛选
            if oi < min_open_interest:
                continue
            
            # 实值筛选（Call: strike < underlying）
            if strike >= underlying_price:
                continue
            
            # Delta 筛选（如果有 delta 数据）
            if delta is not None:
                if not (target_delta_min <= delta <= target_delta_max):
                    continue
            
            filtered.append(c)
        
        if not filtered:
            # 没有符合严格条件的，返回最接近的
            return self._find_closest_delta(
                contracts, 
                target_delta=(target_delta_min + target_delta_max) / 2,
                underlying_price=underlying_price,
                contract_type='call',
                min_open_interest=min_open_interest
            )
        
        # 选择最接近目标 Delta 中点的合约
        target_delta = (target_delta_min + target_delta_max) / 2
        best = min(filtered, key=lambda x: abs((x.get('delta') or 0.85) - target_delta))
        
        return self._format_leaps_result(best, underlying_price)
    
    def _format_leaps_result(
        self, 
        contract: Dict[str, Any], 
        underlying_price: float
    ) -> Dict[str, Any]:
        """格式化 LEAPS Call 结果"""
        strike = contract.get('strike', 0)
        last_price = contract.get('last_price', 0) or 0
        delta = contract.get('delta', 0.85)
        expiration = contract.get('expiration', '')
        
        # 计算剩余天数
        try:
            if isinstance(expiration, str):
                exp_date = dt.datetime.strptime(expiration, '%Y-%m-%d').date()
            else:
                exp_date = expiration
            days_to_expiry = (exp_date - dt.date.today()).days
        except Exception:
            days_to_expiry = 400
        
        # 计算杠杆率：Underlying Price / Option Price
        leverage = underlying_price / last_price if last_price > 0 else 0
        
        # 计算溢价率：(Option Price - Intrinsic Value) / Intrinsic Value
        intrinsic = max(0, underlying_price - strike)
        time_value = last_price - intrinsic
        premium_rate = time_value / intrinsic if intrinsic > 0 else 0
        
        return {
            'ticker': contract.get('ticker', 'N/A'),
            'strike': strike,
            'expiration': expiration,
            'days_to_expiry': days_to_expiry,
            'delta': delta,
            'last_price': last_price,
            'leverage': round(leverage, 2),
            'premium_rate': round(premium_rate, 4),
            'underlying_price': underlying_price,
            'open_interest': contract.get('open_interest', 0),
            'is_mock': contract.get('_is_mock', False),
            'strategy': 'LEAPS_CALL',
            'recommendation': self._generate_leaps_recommendation(
                strike, last_price, leverage, premium_rate, days_to_expiry
            )
        }
    
    def _generate_leaps_recommendation(
        self,
        strike: float,
        price: float,
        leverage: float,
        premium_rate: float,
        days: int
    ) -> str:
        """生成 LEAPS Call 操作建议"""
        return (
            f"💡 操作建议：以 ${price:.2f} 买入 1 份合约（控制 100 股），"
            f"相当于以 ${strike:.0f} 的成本获得 {leverage:.1f}x 杠杆敞口。"
            f"时间价值溢价仅 {premium_rate:.1%}，距离到期还有 {days} 天。"
            f"适合替代 QLD 进行中长期多头配置。"
        )
    
    # =========================================================================
    # Core Logic 2: Cash-Secured Put Selector (State 2 抄底)
    # =========================================================================
    
    def scan_cash_secured_put(
        self,
        min_days: int = 30,
        max_days: int = 45,
        min_open_interest: int = 500,
        target_delta_min: float = -0.30,
        target_delta_max: float = -0.20
    ) -> Optional[Dict[str, Any]]:
        """
        扫描 Cash-Secured Put 期权（用于 State 2 收租抄底）
        
        目标：在下跌途中"收租"等待抄底的看跌期权
        
        Args:
            min_days: 最小到期天数（默认 30）
            max_days: 最大到期天数（默认 45，Theta 衰减最快）
            min_open_interest: 最小持仓量
            target_delta_min: 目标 Delta 下限（-0.30）
            target_delta_max: 目标 Delta 上限（-0.20）
            
        Returns:
            最佳合约详情，包含：
            - ticker: 合约代码
            - strike: 行权价
            - premium: 权利金金额
            - annualized_return: 年化回报率
            - prob_profit: 盈利概率
        """
        underlying_price = self.get_underlying_price()
        if underlying_price is None:
            return None
        
        # 获取期权链
        contracts = self.fetch_option_chain(min_days, max_days, 'put')
        
        if not contracts:
            return self._create_error_result("未找到符合条件的期权合约")
        
        # 筛选：流动性 + OTM
        filtered = []
        for c in contracts:
            oi = c.get('open_interest', 0) or 0
            strike = c.get('strike', 0)
            delta = c.get('delta')
            
            # 流动性筛选
            if oi < min_open_interest:
                continue
            
            # 虚值筛选（Put: strike < underlying）
            if strike >= underlying_price:
                continue
            
            # Delta 筛选
            if delta is not None:
                if not (target_delta_min <= delta <= target_delta_max):
                    continue
            
            filtered.append(c)
        
        if not filtered:
            return self._find_closest_delta(
                contracts,
                target_delta=(target_delta_min + target_delta_max) / 2,
                underlying_price=underlying_price,
                contract_type='put',
                min_open_interest=min_open_interest
            )
        
        # 选择最接近目标 Delta 中点的合约
        target_delta = (target_delta_min + target_delta_max) / 2
        best = min(filtered, key=lambda x: abs((x.get('delta') or -0.25) - target_delta))
        
        return self._format_csp_result(best, underlying_price)
    
    def _format_csp_result(
        self, 
        contract: Dict[str, Any], 
        underlying_price: float
    ) -> Dict[str, Any]:
        """格式化 CSP 结果"""
        strike = contract.get('strike', 0)
        last_price = contract.get('last_price', 0) or 0
        delta = contract.get('delta', -0.25)
        expiration = contract.get('expiration', '')
        
        # 计算剩余天数
        try:
            if isinstance(expiration, str):
                exp_date = dt.datetime.strptime(expiration, '%Y-%m-%d').date()
            else:
                exp_date = expiration
            days_to_expiry = (exp_date - dt.date.today()).days
        except Exception:
            days_to_expiry = 37
        
        # 权利金（每份合约 = 100 股）
        premium = last_price * 100
        
        # 年化回报率 = (Premium / Strike) * (365 / Days)
        if strike > 0 and days_to_expiry > 0:
            annualized_return = (last_price / strike) * (365 / days_to_expiry)
        else:
            annualized_return = 0
        
        # 盈利概率（基于 Delta）
        prob_profit = 1 - abs(delta) if delta else 0.75
        
        # 下跌保护距离
        downside_buffer = (underlying_price - strike) / underlying_price
        
        return {
            'ticker': contract.get('ticker', 'N/A'),
            'strike': strike,
            'expiration': expiration,
            'days_to_expiry': days_to_expiry,
            'delta': delta,
            'last_price': last_price,
            'premium': round(premium, 2),
            'annualized_return': round(annualized_return, 4),
            'prob_profit': round(prob_profit, 4),
            'downside_buffer': round(downside_buffer, 4),
            'underlying_price': underlying_price,
            'open_interest': contract.get('open_interest', 0),
            'is_mock': contract.get('_is_mock', False),
            'strategy': 'CASH_SECURED_PUT',
            'recommendation': self._generate_csp_recommendation(
                strike, last_price, premium, annualized_return, prob_profit, underlying_price
            )
        }
    
    def _generate_csp_recommendation(
        self,
        strike: float,
        price: float,
        premium: float,
        ann_return: float,
        prob: float,
        underlying: float
    ) -> str:
        """生成 CSP 操作建议"""
        buffer_pct = (underlying - strike) / underlying
        return (
            f"💡 操作建议：以 ${price:.2f} 的权利金卖出 1 份 Put（需预留 ${strike * 100:,.0f} 现金担保）。"
            f"如果 {self.ticker} 不跌破 ${strike:.0f}（当前下跌 {buffer_pct:.1%} 的空间），"
            f"则白赚 ${premium:.0f}，年化回报率 {ann_return:.1%}。"
            f"基于 Delta，约有 {prob:.0%} 的概率盈利。"
            f"如被行权则以 ${strike:.0f} 的成本接盘 100 股 {self.ticker}。"
        )
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def _find_closest_delta(
        self,
        contracts: List[Dict],
        target_delta: float,
        underlying_price: float,
        contract_type: str,
        min_open_interest: int
    ) -> Optional[Dict[str, Any]]:
        """找到最接近目标 Delta 的合约（当没有完全符合的）"""
        # 放宽流动性要求
        relaxed = [c for c in contracts if (c.get('open_interest', 0) or 0) >= min_open_interest // 2]
        
        if not relaxed:
            relaxed = contracts
        
        if not relaxed:
            return self._create_error_result("没有找到任何期权合约")
        
        # 根据合约类型筛选
        if contract_type == 'call':
            # ITM calls
            relaxed = [c for c in relaxed if c.get('strike', 0) < underlying_price]
        else:
            # OTM puts
            relaxed = [c for c in relaxed if c.get('strike', 0) < underlying_price]
        
        if not relaxed:
            return self._create_error_result("没有找到符合 ITM/OTM 条件的合约")
        
        # 找最接近的
        best = min(relaxed, key=lambda x: abs((x.get('delta') or target_delta) - target_delta))
        
        if contract_type == 'call':
            result = self._format_leaps_result(best, underlying_price)
        else:
            result = self._format_csp_result(best, underlying_price)
        
        result['warning'] = f"⚠️ Delta 偏差较大，未找到完全符合 {target_delta:.2f} 目标的合约"
        return result
    
    def _create_error_result(self, message: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            'error': True,
            'message': message,
            'ticker': self.ticker,
            'is_mock': True,
        }


# =============================================================================
# Standalone Testing
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("AlphaPilot Option Scanner - Test Mode")
    print("=" * 60)
    
    scanner = OptionScanner(ticker='QQQ')
    
    print(f"\n📊 Underlying: {scanner.ticker}")
    print(f"💰 Price: ${scanner.get_underlying_price():.2f}")
    print(f"🔌 API Available: {scanner.is_available()}")
    
    print("\n" + "-" * 60)
    print("🚀 LEAPS Call Scan (State 0 - Attack)")
    print("-" * 60)
    leaps = scanner.scan_leaps_call()
    if leaps:
        for k, v in leaps.items():
            if k != 'recommendation':
                print(f"  {k}: {v}")
        print(f"\n  {leaps.get('recommendation', '')}")
    
    print("\n" + "-" * 60)
    print("🛡️ CSP Scan (State 2 - Escape/Dip Buy)")
    print("-" * 60)
    csp = scanner.scan_cash_secured_put()
    if csp:
        for k, v in csp.items():
            if k != 'recommendation':
                print(f"  {k}: {v}")
        print(f"\n  {csp.get('recommendation', '')}")
