"""
Точка входа. Запускается на Railway как worker-процесс (см. Procfile).

Цикл работы:
  1. Раз в PRICE_CHECK_INTERVAL_SEC секунд проверяем текущую цену:
     если в позиции и сработал стоп-лосс/тейк-профит — закрываем сразу.
  2. Раз в закрытие 5-минутной свечи пересчитываем индикаторы и,
     если сигнал "buy"/"sell" — исполняем ордер по рынку.

Состояние (в позиции или нет, цена входа) сохраняется в STATE_FILE,
чтобы переживать перезапуск процесса (но не пересоздание контейнера
без подключённого volume на Railway — это нормальное ограничение
для простого бота).
"""
import json
import logging
import os
import time

import ccxt

import config
import exchange_client
import strategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("okx-bot")

BASE_CCY, QUOTE_CCY = config.SYMBOL.split("/")

TIMEFRAME_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900,
    "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
}.get(config.TIMEFRAME, 300)


def load_state() -> dict:
    if os.path.exists(config.STATE_FILE):
        try:
            with open(config.STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            log.warning("Не удалось прочитать файл состояния, начинаю заново")
    return {"in_position": False, "entry_price": None, "base_amount": None}


def save_state(state: dict) -> None:
    with open(config.STATE_FILE, "w") as f:
        json.dump(state, f)


def seconds_until_next_candle_close() -> float:
    now = time.time()
    return TIMEFRAME_SECONDS - (now % TIMEFRAME_SECONDS) + 2  # +2с запас, чтобы свеча точно закрылась


def check_stop_loss_take_profit(exchange, state: dict) -> bool:
    """Возвращает True, если позиция была закрыта."""
    if not state["in_position"]:
        return False

    price = exchange_client.fetch_last_price(exchange, config.SYMBOL)
    entry = state["entry_price"]
    change_pct = (price - entry) / entry * 100

    if change_pct <= -config.STOP_LOSS_PCT:
        log.info(f"СТОП-ЛОСС: цена {price:.4f}, вход {entry:.4f} ({change_pct:.2f}%)")
        close_position(exchange, state, reason="stop_loss")
        return True

    if change_pct >= config.TAKE_PROFIT_PCT:
        log.info(f"ТЕЙК-ПРОФИТ: цена {price:.4f}, вход {entry:.4f} ({change_pct:.2f}%)")
        close_position(exchange, state, reason="take_profit")
        return True

    return False


def open_position(exchange, state: dict) -> None:
    free_quote = exchange_client.fetch_free_quote_balance(exchange, QUOTE_CCY)
    trade_amount = free_quote * config.TRADE_SIZE_FRACTION

    if trade_amount <= 0:
        log.warning(f"Недостаточно свободного {QUOTE_CCY} для покупки, сигнал пропущен")
        return

    price = exchange_client.fetch_last_price(exchange, config.SYMBOL)
    log.info(f"BUY сигнал: покупаю на {trade_amount:.2f} {QUOTE_CCY} по цене ~{price:.4f}")

    order = exchange_client.market_buy_quote(exchange, config.SYMBOL, trade_amount)
    time.sleep(1.5)  # даём бирже время исполнить и обновить баланс
    base_amount = exchange_client.fetch_free_base_balance(exchange, BASE_CCY)

    state.update({
        "in_position": True,
        "entry_price": price,
        "base_amount": base_amount,
    })
    save_state(state)
    log.info(f"Позиция открыта: {base_amount:.6f} {BASE_CCY} по {price:.4f}. Order id: {order.get('id')}")


def close_position(exchange, state: dict, reason: str) -> None:
    base_amount = exchange_client.fetch_free_base_balance(exchange, BASE_CCY)
    if base_amount <= 0:
        log.warning(f"Нет {BASE_CCY} на балансе для продажи, сбрасываю состояние")
        state.update({"in_position": False, "entry_price": None, "base_amount": None})
        save_state(state)
        return

    order = exchange_client.market_sell_base(exchange, config.SYMBOL, base_amount)
    log.info(f"Позиция закрыта ({reason}): продано {base_amount:.6f} {BASE_CCY}. Order id: {order.get('id')}")

    state.update({"in_position": False, "entry_price": None, "base_amount": None})
    save_state(state)


def run_strategy_check(exchange, state: dict) -> None:
    df = exchange_client.fetch_ohlcv_df(exchange, config.SYMBOL, config.TIMEFRAME, limit=200)
    df = df.iloc[:-1]  # отбрасываем текущую незакрытую свечу
    df = strategy.add_indicators(df)

    signal = strategy.generate_signal(df, state["in_position"])
    last = df.iloc[-1]
    log.info(
        f"[{config.TIMEFRAME}] close={last['close']:.4f} "
        f"EMA{config.EMA_FAST}={last['ema_fast']:.4f} EMA{config.EMA_SLOW}={last['ema_slow']:.4f} "
        f"RSI={last['rsi']:.1f} -> сигнал: {signal}"
    )

    if signal == "buy" and not state["in_position"]:
        open_position(exchange, state)
    elif signal == "sell" and state["in_position"]:
        close_position(exchange, state, reason="signal")


def main() -> None:
    mode = "ДЕМО-СЧЁТ" if config.DEMO_MODE else "⚠️ РЕАЛЬНАЯ ТОРГОВЛЯ"
    log.info(f"Запуск бота OKX | Режим: {mode} | Пара: {config.SYMBOL} | ТФ: {config.TIMEFRAME}")

    if not config.OKX_API_KEY or not config.OKX_SECRET or not config.OKX_PASSPHRASE:
        log.error("Не заданы OKX_API_KEY / OKX_SECRET / OKX_PASSPHRASE. Задайте переменные окружения и перезапустите.")
        return

    exchange = exchange_client.create_exchange()
    state = load_state()

    log.info(f"Начальное состояние: {state}")

    # Синхронизируемся с закрытием ближайшей свечи, чтобы не считать по неполным данным
    next_strategy_check = time.time() + seconds_until_next_candle_close()

    while True:
        try:
            check_stop_loss_take_profit(exchange, state)

            if time.time() >= next_strategy_check:
                run_strategy_check(exchange, state)
                next_strategy_check = time.time() + TIMEFRAME_SECONDS

        except ccxt.BaseError as e:
            log.error(f"Ошибка биржи: {e}")
        except Exception as e:
            log.exception(f"Непредвиденная ошибка: {e}")

        time.sleep(config.PRICE_CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
