import os
from decimal import Decimal

from .bot import BotCredentials, BotSettings


# Credentials are read from environment variables. Never hardcode live secrets.
# See .env.example for the required variable names.
DEFAULT_CREDENTIALS = BotCredentials(
    api_key=os.environ.get("DELTA_API_KEY", "YOUR_API_KEY"),
    api_secret=os.environ.get("DELTA_API_SECRET", "YOUR_API_SECRET"),
    email=os.environ.get("DELTA_EMAIL", "you@example.com"),
    password=os.environ.get("DELTA_PASSWORD", "YOUR_PASSWORD"),
    totp_secret=os.environ.get("DELTA_TOTP_SECRET", "YOUR_TOTP_SECRET"),
    base_url=os.environ.get("DELTA_BASE_URL", "https://api.india.delta.exchange"),
)


DEFAULT_SETTINGS = BotSettings(
    product_symbol="BTCUSD",
    levels_count=10,
    qty_start=1,
    qty_step=1,
    price_gap=Decimal("100"),
    target_gap=Decimal("100"),
    max_mtm_loss=Decimal("25000"),
    max_mtm_profit=Decimal("25000"),
    poll_interval=2.0,
)
