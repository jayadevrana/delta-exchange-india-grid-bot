from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests


class DeltaApiError(Exception):
    """Raised when Delta returns an API-level or transport-level failure."""


class DeltaIndiaClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://api.india.delta.exchange") -> None:
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.user_agent = "python-3.9-delta-local-grid-bot"

    def get_product(self, symbol: str) -> Dict[str, Any]:
        return self._request("GET", "/v2/products/{symbol}".format(symbol=symbol), auth=False)

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        return self._request("GET", "/v2/tickers/{symbol}".format(symbol=symbol), auth=False)

    def get_position(self, product_id: int) -> Dict[str, Any]:
        params = {"product_id": product_id}
        result = self._request("GET", "/v2/positions", params=params, auth=True)
        if isinstance(result, list):
            return result[0] if result else {}
        return result or {}

    def get_open_orders(self, product_id: int) -> List[Dict[str, Any]]:
        params = {"product_id": product_id, "state": "open"}
        result = self._request("GET", "/v2/orders", params=params, auth=True)
        return result if isinstance(result, list) else []

    def get_recent_fills(self, product_id: int, page_size: int = 50) -> List[Dict[str, Any]]:
        params = {"product_ids": str(product_id), "page_size": min(page_size, 50)}
        result = self._request("GET", "/v2/fills", params=params, auth=True)
        return result if isinstance(result, list) else []

    def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/v2/orders", json_body=payload, auth=True)

    def place_batch_orders(self, product_id: int, product_symbol: str, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        payload = {
            "product_id": product_id,
            "product_symbol": product_symbol,
            "orders": orders,
        }
        result = self._request("POST", "/v2/orders/batch", json_body=payload, auth=True)
        return result if isinstance(result, list) else []

    def cancel_all_orders(self, product_id: int) -> Dict[str, Any]:
        payload = {"product_id": product_id}
        return self._request("DELETE", "/v2/orders/all", json_body=payload, auth=True)

    def close_all_positions(self, product_id: int) -> Dict[str, Any]:
        payload = {"product_id": product_id}
        return self._request("POST", "/v2/positions/close_all", json_body=payload, auth=True)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        auth: bool = False,
    ) -> Any:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        query = self._encode_query(params)
        body_text = json.dumps(json_body, separators=(",", ":"), sort_keys=True) if json_body is not None else ""
        request_path = path if not query else "{path}?{query}".format(path=path, query=query)
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if auth:
            timestamp = str(int(time.time()))
            message = "{method}{timestamp}{request_path}{body}".format(
                method=method.upper(),
                timestamp=timestamp,
                request_path=request_path,
                body=body_text,
            )
            signature = hmac.new(
                self.api_secret.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers.update(
                {
                    "api-key": self.api_key,
                    "signature": signature,
                    "timestamp": timestamp,
                }
            )

        response = self.session.request(
            method=method.upper(),
            url="{base}{path}".format(base=self.base_url, path=path),
            params=params or None,
            data=body_text if json_body is not None else None,
            headers=headers,
            timeout=15,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise DeltaApiError("Delta returned a non-JSON response: {0}".format(response.text[:500])) from exc

        if response.status_code >= 400:
            raise DeltaApiError(self._extract_error(payload, response.status_code))
        if payload.get("success") is False:
            raise DeltaApiError(self._extract_error(payload, response.status_code))
        return payload.get("result")

    @staticmethod
    def _encode_query(params: Dict[str, Any]) -> str:
        if not params:
            return ""
        return urlencode(list(params.items()), doseq=True)

    @staticmethod
    def _extract_error(payload: Dict[str, Any], status_code: int) -> str:
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code") or "api_error"
            message = error.get("message") or json.dumps(error.get("context") or {})
            return "Delta API error {0} ({1}): {2}".format(status_code, code, message)
        if isinstance(error, str):
            return "Delta API error {0}: {1}".format(status_code, error)
        return "Delta API error {0}: {1}".format(status_code, payload)


def to_decimal(value: Any, fallback: str = "0") -> Decimal:
    raw = fallback if value in (None, "") else str(value)
    return Decimal(raw)
