#!/usr/bin/env python3
"""yfinance MCP server.

Provides access to Yahoo Finance market data via the yfinance Python
library: historical OHLCV price data, ticker/company info, multi-ticker
downloads, and dividend/split history.

Documentation: https://ranaroussi.github.io/yfinance/
GitHub: https://github.com/ranaroussi/yfinance

IMPORTANT: yfinance is NOT an official Yahoo Finance API. It scrapes
Yahoo Finance's unofficial endpoints, so it can change or be rate-limited
without notice. No API key required. Not intended for commercial
redistribution or high-frequency production use - fine for ad hoc lookups.

Ticker format: Oslo Børs tickers use a ".OL" suffix (e.g. "EQNR.OL" for
Equinor, "DNB.OL" for DNB). US tickers are bare (e.g. "AAPL"). Indices use
a "^" prefix (e.g. "^GSPC" for S&P 500, "^OSEBX" for Oslo Børs Benchmark
Index).
"""
from __future__ import annotations

import json
from typing import Any

import yfinance as yf
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("yfinance-mcp")


def _df_to_records(df) -> list[dict[str, Any]]:
    """Convert a pandas DataFrame with a DatetimeIndex to a JSON-safe list
    of records, with the index turned into an ISO-date 'date' field."""
    reset = df.reset_index()
    reset.columns = [str(c) for c in reset.columns]
    date_col = reset.columns[0]
    reset[date_col] = reset[date_col].astype(str)
    return json.loads(reset.to_json(orient="records", date_format="iso"))


@mcp.tool()
def yfinance_history(ticker: str, period: str = "1y", interval: str = "1d") -> str:
    """Get historical OHLCV (open/high/low/close/volume) price data for a
    single ticker. 'period' is one of 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
    (default 1y). 'interval' is one of 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,
    1wk,1mo,3mo (default 1d; intraday intervals only available for recent
    periods, per Yahoo Finance limits). Norwegian tickers use a ".OL"
    suffix (e.g. "EQNR.OL"); indices use a "^" prefix (e.g. "^OSEBX")."""
    t = yf.Ticker(ticker)
    hist = t.history(period=period, interval=interval)
    if hist.empty:
        return json.dumps({"ticker": ticker, "error": "no data returned - check ticker symbol and period/interval combination"}, ensure_ascii=False)
    return json.dumps({"ticker": ticker, "period": period, "interval": interval, "rows": _df_to_records(hist)}, ensure_ascii=False, indent=2)


@mcp.tool()
def yfinance_info(ticker: str) -> str:
    """Get company/ticker metadata and the latest snapshot: name, sector,
    industry, currency, current/regular market price, market cap, P/E,
    dividend yield, 52-week range, business summary, etc. Returns the
    fields most likely to be useful (not the full raw dict, which can have
    100+ keys and is inconsistent across ticker types)."""
    t = yf.Ticker(ticker)
    info = t.info
    keys = [
        "shortName", "longName", "symbol", "currency", "exchange",
        "quoteType", "sector", "industry", "country",
        "currentPrice", "regularMarketPrice", "previousClose",
        "open", "dayLow", "dayHigh",
        "fiftyTwoWeekLow", "fiftyTwoWeekHigh",
        "marketCap", "trailingPE", "forwardPE", "dividendYield",
        "trailingAnnualDividendYield", "beta",
        "averageVolume", "volume",
        "longBusinessSummary",
    ]
    result = {k: info.get(k) for k in keys if k in info}
    result["_note"] = "Subset of available fields - ask for a specific field if something else is needed, since the full info dict varies a lot by ticker type."
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def yfinance_download(tickers: list[str], period: str = "1y", interval: str = "1d") -> str:
    """Download and compare historical OHLCV data for multiple tickers at
    once, adjusted for splits/dividends. Same 'period'/'interval' options as
    yfinance_history. Returns data grouped by ticker (one list of daily
    records per ticker) rather than yfinance's raw wide MultiIndex format,
    which is easier to reason about with several tickers."""
    data = yf.download(tickers, period=period, interval=interval, auto_adjust=True, progress=False, group_by="ticker")
    result: dict[str, Any] = {}
    if len(tickers) == 1:
        result[tickers[0]] = _df_to_records(data)
    else:
        for tk in tickers:
            try:
                sub = data[tk].dropna(how="all")
                result[tk] = _df_to_records(sub)
            except KeyError:
                result[tk] = {"error": "no data returned for this ticker"}
    return json.dumps({"tickers": tickers, "period": period, "interval": interval, "data": result}, ensure_ascii=False, indent=2)


@mcp.tool()
def yfinance_dividends_splits(ticker: str) -> str:
    """Get the full dividend payment history and stock split history for a
    ticker."""
    t = yf.Ticker(ticker)
    divs = t.dividends
    splits = t.splits
    return json.dumps({
        "ticker": ticker,
        "dividends": _df_to_records(divs.to_frame(name="dividend")) if not divs.empty else [],
        "splits": _df_to_records(splits.to_frame(name="ratio")) if not splits.empty else [],
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
