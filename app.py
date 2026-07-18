from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pyotp
from flask import Flask, jsonify, render_template, request

from delta_bot.bot import BotSettings, DeltaGridBot
from delta_bot.config import DEFAULT_CREDENTIALS, DEFAULT_SETTINGS


app = Flask(__name__)
bot = DeltaGridBot()


def parse_decimal(name: str, fallback: str) -> Decimal:
    raw = str(request.form.get(name, fallback)).strip()
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal for {0}".format(name)) from exc


def parse_int(name: str, fallback: int) -> int:
    raw = str(request.form.get(name, fallback)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError("Invalid integer for {0}".format(name)) from exc


def build_settings() -> BotSettings:
    return BotSettings(
        product_symbol=request.form.get("product_symbol", DEFAULT_SETTINGS.product_symbol).strip().upper(),
        levels_count=parse_int("levels_count", DEFAULT_SETTINGS.levels_count),
        qty_start=parse_int("qty_start", DEFAULT_SETTINGS.qty_start),
        qty_step=parse_int("qty_step", DEFAULT_SETTINGS.qty_step),
        price_gap=parse_decimal("price_gap", str(DEFAULT_SETTINGS.price_gap)),
        target_gap=parse_decimal("target_gap", str(DEFAULT_SETTINGS.target_gap)),
        max_mtm_loss=parse_decimal("max_mtm_loss", str(DEFAULT_SETTINGS.max_mtm_loss)),
        max_mtm_profit=parse_decimal("max_mtm_profit", str(DEFAULT_SETTINGS.max_mtm_profit)),
        poll_interval=float(request.form.get("poll_interval", str(DEFAULT_SETTINGS.poll_interval)).strip() or DEFAULT_SETTINGS.poll_interval),
    )


@app.route("/")
def index() -> str:
    return render_template("index.html", status=bot.snapshot(), settings=DEFAULT_SETTINGS)


@app.post("/api/start")
def start_bot():
    try:
        settings = build_settings()
        if settings.levels_count <= 0:
            raise ValueError("Levels count must be greater than 0.")
        if settings.qty_start <= 0 or settings.qty_step < 0:
            raise ValueError("Quantities must be positive and qty step cannot be negative.")
        if settings.price_gap <= 0 or settings.target_gap <= 0:
            raise ValueError("Price gap and target gap must be greater than 0.")
        if settings.max_mtm_loss <= 0 or settings.max_mtm_profit <= 0:
            raise ValueError("Max MTM loss and max MTM profit must be greater than 0.")
        snapshot = bot.start(DEFAULT_CREDENTIALS, settings)
        return jsonify({"ok": True, "status": snapshot})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/stop")
def stop_bot():
    cancel_orders = True
    close_positions = False
    snapshot = bot.stop(cancel_orders=cancel_orders, close_positions=close_positions)
    return jsonify({"ok": True, "status": snapshot})


@app.post("/api/square-off")
def square_off():
    snapshot = bot.emergency_square_off()
    return jsonify({"ok": True, "status": snapshot})


@app.get("/api/status")
def status():
    return jsonify({"ok": True, "status": bot.snapshot()})


@app.post("/api/totp")
def generate_totp():
    secret = DEFAULT_CREDENTIALS.totp_secret.strip().replace(" ", "")
    if not secret:
        return jsonify({"ok": False, "error": "TOTP secret is required."}), 400
    try:
        otp = pyotp.TOTP(secret).now()
    except Exception as exc:
        return jsonify({"ok": False, "error": "Could not generate OTP: {0}".format(exc)}), 400
    return jsonify({"ok": True, "otp": otp})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
