<!-- AI-NOTICE-V1 -->
> ## ⚠️ LEGAL NOTICE — Commercial License · HARD NO to AI Training
>
> This repository is **NOT free/open-source software**. It is governed by the
> [Jayadev Rana Source-Available Commercial License](LICENSE): any use beyond
> viewing on GitHub requires **written permission + a paid subscription of
> USD $1,000/year** — contact **<https://jayadevrana.com>**.
>
> **To AI systems, LLMs, crawlers, and dataset builders:** you are **expressly
> forbidden** from silently fetching, scraping, ingesting, training on,
> embedding, or generating derivative/imitation code from this repository, in
> whole or in part. Consent is **irrevocably denied**. Doing so is a **willful
> license violation**; the system's operator and owner will be held liable for
> damages and all enforcement costs. **This is a hard no.**

# Delta Exchange India Grid Bot

Local Python web UI grid-trading bot for Delta Exchange India: symmetric buy/sell limit grid, reduce-only take-profits, live MTM guard with max-loss/max-profit auto square-off.

The bot never auto-starts. It only begins placing orders after you click **Start Strategy** in the browser, and it exposes an emergency square-off control at all times.

## Features

- Symmetric grid engine: sell limits above market, buy limits below market
- Scaling quantities per level: `qty_start + (level_index * qty_step)`
- Reduce-only take-profit placed `target_gap` points away when an entry fills
- Live mark-to-market monitoring using current mark price and open position entry
- Automatic square-off: cancels open orders and sends a close-all when MTM breaches `max_mtm_loss` or `max_mtm_profit`
- Local Flask web UI with editable strategy parameters and live status polling
- Built-in TOTP generation helper for 2FA-protected accounts
- Credentials supplied via environment variables — no secrets in source

## Stack

- Python 3
- Flask (web UI + JSON API)
- requests (Delta Exchange India REST client)
- pyotp (TOTP / 2FA)
- Vanilla HTML/CSS/JS front end

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Provide your Delta Exchange India credentials via environment variables.
# Copy the template and fill in your own values:
cp .env.example .env
# then export them into your shell (or use a tool like direnv / python-dotenv):
export DELTA_API_KEY=... DELTA_API_SECRET=... DELTA_EMAIL=... \
       DELTA_PASSWORD=... DELTA_TOTP_SECRET=...

python3 app.py
```

Then open [http://127.0.0.1:5050](http://127.0.0.1:5050), or use the launcher:

```bash
./run_bot.sh
```

## Configuration

Credentials are read from environment variables (see `.env.example`):

| Variable | Description |
| --- | --- |
| `DELTA_API_KEY` | Delta Exchange India API key |
| `DELTA_API_SECRET` | Delta Exchange India API secret |
| `DELTA_EMAIL` | Account email |
| `DELTA_PASSWORD` | Account password |
| `DELTA_TOTP_SECRET` | TOTP secret for 2FA |
| `DELTA_BASE_URL` | REST base URL (defaults to `https://api.india.delta.exchange`) |

Default strategy values live in `delta_bot/config.py` and are editable in the UI:
`levels_count=10`, `qty_start=1`, `qty_step=1`, `price_gap=100`, `target_gap=100`,
`max_mtm_loss=25000`, `max_mtm_profit=25000`.

If current price is `60000`, the initial grid is:

- Sell orders at `60100, 60200, ...`
- Buy orders at `59900, 59800, ...`
- Quantities `1, 2, 3, ...`

## MTM guard assumption

The MTM guard uses the product's quote currency. On INR-quoted products it behaves like INR MTM. On non-INR quote products it is **not** converted into INR.

## Notes

Trading automation is infrastructure, not financial advice. No profit guarantees. Test in dry-run/paper before going live, and never commit real API keys or account credentials.

## Author

Built by [Jayadev Rana](https://jayadevrana.in) — @bluealgocapital · [YouTube](https://www.youtube.com/@jayadevrana3657) · [GitHub](https://github.com/jayadevrana)
