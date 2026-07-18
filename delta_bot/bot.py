from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Deque, Dict, List, Optional, Set

from .api import DeltaIndiaClient, to_decimal


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BotCredentials:
    api_key: str
    api_secret: str
    email: str = ""
    password: str = ""
    totp_secret: str = ""
    base_url: str = "https://api.india.delta.exchange"


@dataclass
class BotSettings:
    product_symbol: str = "BTCUSD"
    levels_count: int = 10
    qty_start: int = 1
    qty_step: int = 1
    price_gap: Decimal = Decimal("100")
    target_gap: Decimal = Decimal("100")
    max_mtm_loss: Decimal = Decimal("25000")
    max_mtm_profit: Decimal = Decimal("25000")
    poll_interval: float = 2.0


@dataclass
class BotSnapshot:
    running: bool = False
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    product_symbol: str = ""
    product_id: Optional[int] = None
    tick_size: str = "1"
    current_price: str = "0"
    approx_mtm: str = "0"
    position_size: int = 0
    position_entry_price: str = "0"
    last_error: str = ""
    last_action: str = "Idle"
    grid_orders_sent: int = 0
    target_orders_sent: int = 0
    public_note: str = ""


class DeltaGridBot:
    def __init__(self) -> None:
        self._state = BotSnapshot(
            public_note="Approx MTM uses quote currency. For INR-quoted contracts, this matches INR."
        )
        self._logs: Deque[str] = deque(maxlen=500)
        self._state_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._client: Optional[DeltaIndiaClient] = None
        self._credentials: Optional[BotCredentials] = None
        self._settings: Optional[BotSettings] = None
        self._product_id: Optional[int] = None
        self._tick_size = Decimal("1")
        self._handled_fill_ids: Set[str] = set()
        self._grid_order_ids: Set[int] = set()
        self._target_order_ids: Set[int] = set()
        self._grid_client_prefix = ""

    def start(self, credentials: BotCredentials, settings: BotSettings) -> Dict[str, Any]:
        if self.is_running:
            raise RuntimeError("Bot is already running.")

        self._credentials = credentials
        self._settings = settings
        self._client = DeltaIndiaClient(credentials.api_key, credentials.api_secret, credentials.base_url)
        self._stop_event.clear()
        self._product_id = None
        self._tick_size = Decimal("1")
        self._handled_fill_ids = set()
        self._grid_order_ids = set()
        self._target_order_ids = set()
        self._grid_client_prefix = str(int(time.time()))

        self._set_state(
            running=True,
            started_at=utc_now_iso(),
            stopped_at=None,
            product_symbol=settings.product_symbol.upper().strip(),
            product_id=None,
            last_error="",
            last_action="Preparing strategy",
            grid_orders_sent=0,
            target_orders_sent=0,
            current_price="0",
            approx_mtm="0",
            position_size=0,
            position_entry_price="0",
        )
        self._thread = threading.Thread(target=self._run, name="delta-grid-bot", daemon=True)
        self._thread.start()
        return self.snapshot()

    def stop(self, cancel_orders: bool = False, close_positions: bool = False, reason: str = "Manual stop requested") -> Dict[str, Any]:
        self._log(reason)
        self._stop_event.set()
        client = self._client
        product_id = self._product_id
        if client and product_id:
            if cancel_orders:
                try:
                    client.cancel_all_orders(product_id)
                    self._log("All open orders cancelled.")
                except Exception as exc:
                    self._log("Cancel-all failed: {0}".format(exc))
            if close_positions:
                try:
                    client.close_all_positions(product_id)
                    self._log("Close-all positions request sent.")
                except Exception as exc:
                    self._log("Close-all failed: {0}".format(exc))
        self._set_state(
            running=False,
            stopped_at=utc_now_iso(),
            last_action="Stopped",
        )
        return self.snapshot()

    def emergency_square_off(self) -> Dict[str, Any]:
        return self.stop(cancel_orders=True, close_positions=True, reason="Emergency square-off requested")

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive() and not self._stop_event.is_set())

    def snapshot(self) -> Dict[str, Any]:
        with self._state_lock:
            data = asdict(self._state)
        data["logs"] = list(self._logs)
        return data

    def _run(self) -> None:
        assert self._client is not None
        assert self._settings is not None
        try:
            symbol = self._settings.product_symbol.upper().strip()
            product = self._client.get_product(symbol)
            self._product_id = int(product["id"])
            self._tick_size = to_decimal(product.get("tick_size"), "1")
            self._set_state(product_id=self._product_id, tick_size=str(self._tick_size), last_action="Product loaded")

            current_price = self._get_current_price(symbol)
            self._set_state(current_price=str(current_price), last_action="Placing opening grid")
            self._place_opening_grid(current_price)
            self._log("Opening grid sent around price {0}".format(current_price))

            while not self._stop_event.is_set():
                latest_price = self._get_current_price(symbol)
                approx_mtm = self._compute_approx_mtm(latest_price)
                self._sync_new_fills()
                self._set_state(current_price=str(latest_price), approx_mtm=str(approx_mtm), last_action="Monitoring")
                self._log(
                    "Current MTM: {0} | exit at <= -{1} or >= {2}".format(
                        approx_mtm,
                        self._settings.max_mtm_loss,
                        self._settings.max_mtm_profit,
                    )
                )
                if approx_mtm <= -self._settings.max_mtm_loss:
                    self._log(
                        "Max MTM loss hit at {0}. Triggering cancel + close-all.".format(approx_mtm)
                    )
                    self.stop(
                        cancel_orders=True,
                        close_positions=True,
                        reason="Risk stop triggered by max MTM loss",
                    )
                    break
                if approx_mtm >= self._settings.max_mtm_profit:
                    self._log(
                        "Max MTM profit hit at {0}. Triggering cancel + close-all.".format(approx_mtm)
                    )
                    self.stop(
                        cancel_orders=True,
                        close_positions=True,
                        reason="Risk stop triggered by max MTM profit",
                    )
                    break
                time.sleep(self._settings.poll_interval)
        except Exception as exc:
            self._log("Bot stopped with error: {0}".format(exc))
            self._set_state(running=False, stopped_at=utc_now_iso(), last_error=str(exc), last_action="Errored")

    def _place_opening_grid(self, current_price: Decimal) -> None:
        assert self._client is not None
        assert self._settings is not None
        assert self._product_id is not None
        orders: List[Dict[str, Any]] = []
        for index in range(self._settings.levels_count):
            step_index = index + 1
            qty = self._settings.qty_start + (index * self._settings.qty_step)
            buy_price = self._round_to_tick(current_price - (self._settings.price_gap * step_index))
            sell_price = self._round_to_tick(current_price + (self._settings.price_gap * step_index))
            orders.append(
                {
                    "size": qty,
                    "side": "buy",
                    "order_type": "limit_order",
                    "limit_price": str(buy_price),
                    "client_order_id": self._client_order_id("gb", step_index),
                }
            )
            orders.append(
                {
                    "size": qty,
                    "side": "sell",
                    "order_type": "limit_order",
                    "limit_price": str(sell_price),
                    "client_order_id": self._client_order_id("gs", step_index),
                }
            )

        result = self._client.place_batch_orders(self._product_id, self._settings.product_symbol.upper(), orders)
        for order in result:
            order_id = order.get("id")
            if order_id is not None:
                self._grid_order_ids.add(int(order_id))

        self._set_state(
            grid_orders_sent=len(result),
            target_orders_sent=0,
            last_action="Opening grid live",
        )
        self._log(
            "Opening grid sent with {0} entry orders. Targets will be placed after fills.".format(
                len(result),
            )
        )

    def _sync_new_fills(self) -> None:
        assert self._client is not None
        assert self._product_id is not None

        fills = self._client.get_recent_fills(self._product_id)
        for fill in reversed(fills):
            fill_id = str(fill.get("id") or fill.get("fill_id") or fill.get("f") or "")
            if not fill_id or fill_id in self._handled_fill_ids:
                continue
            self._handled_fill_ids.add(fill_id)

            order_id = int(fill.get("order_id") or fill.get("o") or 0)
            if order_id in self._target_order_ids or order_id not in self._grid_order_ids:
                continue

            side = str(fill.get("side") or fill.get("S") or "").lower()
            size = int(fill.get("size") or fill.get("s") or 0)
            price = to_decimal(fill.get("price") or fill.get("p"))
            if size <= 0 or side not in {"buy", "sell"}:
                continue

            self._place_target_order(side=side, fill_price=price, fill_size=size, fill_id=fill_id)

    def _place_target_order(self, side: str, fill_price: Decimal, fill_size: int, fill_id: str) -> None:
        assert self._client is not None
        assert self._product_id is not None
        assert self._settings is not None
        target_side = "sell" if side == "buy" else "buy"
        target_price = fill_price + self._settings.target_gap if side == "buy" else fill_price - self._settings.target_gap
        target_price = self._round_to_tick(target_price)
        payload = {
            "product_id": self._product_id,
            "product_symbol": self._settings.product_symbol.upper(),
            "size": fill_size,
            "side": target_side,
            "order_type": "limit_order",
            "limit_price": str(target_price),
            "reduce_only": True,
            "client_order_id": self._fill_target_client_order_id(fill_id),
        }
        order = self._client.place_order(payload)
        if order.get("id") is not None:
            self._target_order_ids.add(int(order["id"]))
        self._set_state(
            target_orders_sent=self._state.target_orders_sent + 1,
            last_action="Profit target placed",
        )
        self._log(
            "Placed target {0} for fill {1}: qty {2} @ {3}".format(
                target_side,
                fill_id,
                fill_size,
                target_price,
            )
        )

    def _get_current_price(self, symbol: str) -> Decimal:
        assert self._client is not None
        ticker = self._client.get_ticker(symbol)
        mark = ticker.get("mark_price") or ticker.get("close") or ticker.get("spot_price")
        return self._round_to_tick(to_decimal(mark, "0"))

    def _compute_approx_mtm(self, latest_price: Decimal) -> Decimal:
        assert self._client is not None
        assert self._product_id is not None
        position = self._client.get_position(self._product_id)
        size = int(position.get("size") or 0)
        entry_price = to_decimal(position.get("entry_price"), "0")
        if size == 0:
            self._set_state(position_size=0, position_entry_price="0")
            return Decimal("0")

        signed_qty = Decimal(size)
        pnl = (latest_price - entry_price) * signed_qty
        pnl = pnl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self._set_state(position_size=size, position_entry_price=str(entry_price))
        return pnl

    def _round_to_tick(self, value: Decimal) -> Decimal:
        if self._tick_size <= 0:
            return value
        steps = (value / self._tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        rounded = steps * self._tick_size
        normalized = rounded.quantize(self._tick_size) if self._tick_size < 1 else rounded.quantize(Decimal("1"))
        return normalized

    def _client_order_id(self, prefix: str, step_index: int) -> str:
        return "{0}{1}{2}".format(prefix, self._grid_client_prefix[-8:], step_index)

    @staticmethod
    def _fill_target_client_order_id(fill_id: str) -> str:
        return "tp{0}".format(fill_id.replace("-", "")[-30:])

    def _set_state(self, **updates: Any) -> None:
        with self._state_lock:
            for key, value in updates.items():
                setattr(self._state, key, value)

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._logs.appendleft("[{0}] {1}".format(timestamp, message))
