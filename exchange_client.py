"""
Тонкая обёртка над ccxt для работы со спотовым рынком OKX,
с поддержкой демо-торговли (Demo Trading).
"""
import ccxt
import pandas as pd

import config


def create_exchange() -> ccxt.okx:
    exchange = ccxt.okx({
        "apiKey": config.OKX_API_KEY,
        "secret": config.OKX_SECRET,
        "password": config.OKX_PASSPHRASE,
        "enableRateLimit": True,
    })

    if config.DEMO_MODE:
        # OKX требует этот заголовок на ВСЕХ запросах в режиме демо-торговли.
        # Ключи для демо-режима создаются отдельно, в разделе
        # "Demo Trading" личного кабинета OKX — обычные ключи не подойдут.
        exchange.headers = exchange.headers or {}
        exchange.headers["x-simulated-trading"] = "1"

    return exchange


def fetch_ohlcv_df(exchange: ccxt.okx, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def fetch_last_price(exchange: ccxt.okx, symbol: str) -> float:
    ticker = exchange.fetch_ticker(symbol)
    return float(ticker["last"])


def fetch_free_quote_balance(exchange: ccxt.okx, quote_ccy: str) -> float:
    balance = exchange.fetch_balance()
    return float(balance.get(quote_ccy, {}).get("free", 0) or 0)


def fetch_free_base_balance(exchange: ccxt.okx, base_ccy: str) -> float:
    balance = exchange.fetch_balance()
    return float(balance.get(base_ccy, {}).get("free", 0) or 0)


def market_buy_quote(exchange: ccxt.okx, symbol: str, quote_amount: float):
    """Покупка на рынке на сумму quote_amount в котируемой валюте (например, USDT)."""
    # OKX спот позволяет создавать маркет-ордер на покупку, указывая сумму в quote-валюте
    return exchange.create_order(
        symbol=symbol,
        type="market",
        side="buy",
        amount=quote_amount,
        params={"tgtCcy": "quote_ccy"},
    )


def market_sell_base(exchange: ccxt.okx, symbol: str, base_amount: float):
    """Продажа всего доступного объёма базовой валюты (например, BTC) по рынку."""
    return exchange.create_order(
        symbol=symbol,
        type="market",
        side="sell",
        amount=base_amount,
    )
