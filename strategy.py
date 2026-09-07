"""
Стратегия: пересечение EMA(fast) / EMA(slow) на 5-минутных свечах,
отфильтрованное по RSI, чтобы не покупать в перекупленности
и не пытаться "ловить нож" в глубокой перепроданности.

Так как это СПОТ (шортов нет), логика однонаправленная:
  BUY  — EMA fast пересекает EMA slow снизу вверх, и RSI не в зоне перекупленности
  SELL — EMA fast пересекает EMA slow сверху вниз (закрытие лонга)
  HOLD — во всех остальных случаях

Стоп-лосс и тейк-профит обрабатываются отдельно в main.py по текущей цене,
чтобы реагировать быстрее, чем раз в 5 минут.
"""
import pandas as pd

import config


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-12)
    return 100 - (100 / (1 + rs))


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema_fast"] = _ema(df["close"], config.EMA_FAST)
    df["ema_slow"] = _ema(df["close"], config.EMA_SLOW)
    df["rsi"] = _rsi(df["close"], config.RSI_PERIOD)
    return df


def generate_signal(df: pd.DataFrame, in_position: bool) -> str:
    """
    Ожидает df с колонками close/ema_fast/ema_slow/rsi, где ПОСЛЕДНЯЯ строка —
    последняя ЗАКРЫТАЯ свеча (main.py уже должен это гарантировать).
    Возвращает: "buy" | "sell" | "hold"
    """
    if len(df) < max(config.EMA_SLOW, config.RSI_PERIOD) + 2:
        return "hold"  # недостаточно данных для точного расчёта индикаторов

    prev = df.iloc[-2]
    last = df.iloc[-1]

    crossed_up = prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]
    crossed_down = prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]

    if not in_position:
        if crossed_up and last["rsi"] < config.RSI_OVERBOUGHT:
            return "buy"
        return "hold"
    else:
        if crossed_down:
            return "sell"
        return "hold"
