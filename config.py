"""
Конфигурация бота. Все параметры берутся из переменных окружения
(на Railway задаются во вкладке Variables проекта).
"""
import os
from dotenv import load_dotenv

load_dotenv()  # для локального запуска из .env файла


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# --- Доступ к OKX ---
OKX_API_KEY = os.getenv("OKX_API_KEY", "")
OKX_SECRET = os.getenv("OKX_SECRET", "")
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE", "")

# Демо-торговля OKX (виртуальные деньги, реальные цены).
# ВАЖНО: для демо-режима нужны отдельные API-ключи,
# созданные в разделе Demo Trading на сайте OKX.
DEMO_MODE = _bool("DEMO_MODE", True)

# --- Торговые параметры ---
SYMBOL = os.getenv("SYMBOL", "BTC/USDT")          # торговая пара (спот)
TIMEFRAME = os.getenv("TIMEFRAME", "5m")          # таймфрейм свечей

EMA_FAST = int(os.getenv("EMA_FAST", "9"))
EMA_SLOW = int(os.getenv("EMA_SLOW", "21"))
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
RSI_OVERBOUGHT = float(os.getenv("RSI_OVERBOUGHT", "70"))
RSI_OVERSOLD = float(os.getenv("RSI_OVERSOLD", "30"))

# Доля свободного USDT, которая используется на одну сделку (0.1 = 10%)
TRADE_SIZE_FRACTION = float(os.getenv("TRADE_SIZE_FRACTION", "0.1"))

# Риск-менеджмент (в процентах от цены входа)
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "1.5"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "2.5"))

# Как часто проверять цену на предмет стоп-лосса/тейк-профита (сек)
PRICE_CHECK_INTERVAL_SEC = int(os.getenv("PRICE_CHECK_INTERVAL_SEC", "30"))

# Файл, в котором хранится состояние позиции (переживает рестарт процесса,
# но НЕ переживает пересоздание контейнера Railway без volume)
STATE_FILE = os.getenv("STATE_FILE", "state.json")
