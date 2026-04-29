"""
Tests for the WebSocket stream consumers — exercises the message handlers
directly with synthetic Binance payloads. Does NOT open a real WebSocket.
"""
import json

import pytest

from app.engines import liquidation_engine as liq
from app.engines import orderflow_engine as of
from app.streams.aggtrade_stream import AggTradeStream, _build_combined_url
from app.streams.liquidation_stream import LiquidationStream


@pytest.fixture(autouse=True)
def _clear_buffers():
    of.reset_for_tests()
    liq._liquidation_events.clear()  # type: ignore[attr-defined]
    yield
    of.reset_for_tests()
    liq._liquidation_events.clear()  # type: ignore[attr-defined]


class TestLiquidationStreamHandler:
    @pytest.mark.asyncio
    async def test_long_liquidation_recorded(self):
        stream = LiquidationStream()
        payload = {
            "e": "forceOrder", "E": 1568014460893,
            "o": {
                "s": "BTCUSDT", "S": "SELL", "o": "LIMIT", "f": "IOC",
                "q": "0.014", "p": "9910", "ap": "9910",
                "X": "FILLED", "l": "0.014", "z": "0.014", "T": 1568014460893
            }
        }
        await stream._handle_message(json.dumps(payload))
        events = liq._liquidation_events.get("BTCUSDT", [])  # type: ignore[attr-defined]
        assert len(events) == 1
        assert events[0]["side"] == "SELL"
        assert events[0]["price"] == pytest.approx(9910)
        assert stream.events_received == 1

    @pytest.mark.asyncio
    async def test_malformed_payload_ignored(self):
        stream = LiquidationStream()
        await stream._handle_message("not json")
        await stream._handle_message(json.dumps({"unrelated": True}))
        await stream._handle_message(json.dumps({"o": {"s": "BTCUSDT"}}))  # missing fields
        assert stream.events_received == 0
        assert liq._liquidation_events == {}  # type: ignore[comparison-overlap]

    @pytest.mark.asyncio
    async def test_zero_qty_ignored(self):
        stream = LiquidationStream()
        payload = {"o": {"s": "BTCUSDT", "S": "BUY", "q": "0", "p": "0",
                          "z": "0", "ap": "0", "T": 1, "X": "FILLED"}}
        await stream._handle_message(json.dumps(payload))
        assert stream.events_received == 0


class TestAggTradeStreamHandler:
    @pytest.mark.asyncio
    async def test_aggressive_buy_recorded(self):
        stream = AggTradeStream()
        env = {"stream": "btcusdt@aggTrade",
               "data": {"e": "aggTrade", "E": 1, "s": "BTCUSDT",
                        "a": 1, "p": "100.0", "q": "1.0",
                        "f": 1, "l": 1, "T": 1_000, "m": False}}
        await stream._handle_message(json.dumps(env))
        snap = of.get_cvd_snapshot("BTCUSDT", now_ms=1_000)
        assert stream.ticks_received == 1
        assert snap["cvd_1m"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_buyer_maker_means_aggressive_sell(self):
        stream = AggTradeStream()
        env = {"data": {"s": "BTCUSDT", "p": "100.0", "q": "2.0", "T": 1_000, "m": True}}
        await stream._handle_message(json.dumps(env))
        snap = of.get_cvd_snapshot("BTCUSDT", now_ms=1_000)
        assert snap["cvd_1m"] == pytest.approx(-200.0)

    @pytest.mark.asyncio
    async def test_missing_data_envelope_ignored(self):
        stream = AggTradeStream()
        await stream._handle_message(json.dumps({"stream": "x@aggTrade"}))
        await stream._handle_message("not json")
        assert stream.ticks_received == 0


class TestCombinedUrlBuilder:
    def test_builds_lowercase_stream_list(self):
        url = _build_combined_url(["BTCUSDT", "ETHUSDT"])
        assert url.endswith("btcusdt@aggTrade/ethusdt@aggTrade")

    def test_handles_single_symbol(self):
        url = _build_combined_url(["BTCUSDT"])
        assert url.endswith("btcusdt@aggTrade")
