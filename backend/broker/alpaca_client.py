import os
from datetime import datetime, timedelta, time
import pytz
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus, OrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv

load_dotenv()

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# Always paper trading — never real money
trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

ET = pytz.timezone("America/New_York")


def is_market_open() -> bool:
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:
        return False
    return time(9, 30) <= now_et.time() <= time(16, 0)


def get_portfolio() -> dict:
    account = trading_client.get_account()
    positions = trading_client.get_all_positions()
    return {
        "total_value": float(account.portfolio_value),
        "cash": float(account.cash),
        "buying_power": float(account.buying_power),
        "positions": [
            {
                "ticker": p.symbol,
                "qty": float(p.qty),
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
            }
            for p in positions
        ],
    }


def place_order(ticker: str, side: str, position_size_pct: float) -> dict:
    if not is_market_open():
        raise ValueError("Market is closed — orders only accepted 9:30am–4:00pm ET")

    account = trading_client.get_account()
    portfolio_value = float(account.portfolio_value)
    notional = round(portfolio_value * (position_size_pct / 100), 2)

    order_data = MarketOrderRequest(
        symbol=ticker,
        notional=notional,
        side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )
    order = trading_client.submit_order(order_data)
    return {
        "alpaca_order_id": str(order.id),
        "ticker": ticker,
        "side": side,
        "notional": notional,
        "status": str(order.status),
    }


def get_closed_orders(limit: int = 500) -> list:
    """Returns filled closed orders — used for win-rate calculation."""
    try:
        orders = trading_client.get_orders(
            filter=GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=limit)
        )
        return [
            {
                "symbol": str(o.symbol),
                "side": o.side.value,
                "filled_qty": float(o.filled_qty) if o.filled_qty else 0.0,
                "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else 0.0,
                "filled_at": str(o.filled_at) if o.filled_at else None,
            }
            for o in orders
            if o.status == OrderStatus.FILLED and o.filled_avg_price
        ]
    except Exception:
        return []


def get_historical_bars(ticker: str, days: int = 30) -> list:
    end = datetime.now(ET)
    start = end - timedelta(days=days)
    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
    )
    bars = data_client.get_stock_bars(request)
    df = bars.df
    if df.empty:
        return []
    return df.reset_index().to_dict("records")
