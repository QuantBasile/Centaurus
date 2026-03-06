from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import numpy as np
import pandas as pd


TRADES_COLS = [
    "traderNr",
    "instrument",
    "issuer",
    "strike",
    "tradeTime",
    "quantity",
    "tradePrice",
    "tradeUnderlyingSpotRef",
    "portfolio",
    "counterparty",
    "underlyingName",
    "isCall",
    "isStock",
    "fees",
    "buyOrSell",
    "Premia",
    "PremiaCum",
    "PnLVonDelta",
    "PnLVonDeltaCum",
    "delta",
    "deltaCum",
    "feesCum",
    "Total",
    "date",
]


class TradeDataProvider(Protocol):
    def load(self, from_date: date, to_date: date) -> pd.DataFrame:
        """
        Returns:
          - trades df guaranteed to contain TRADES_COLS
        """
        ...


@dataclass(frozen=True)
class FakeDataConfig:
    n_rows: int = 200_000
    seed: int = 42
    n_traders: int = 15
    issuers: tuple[str, ...] = ("ISSUER_A", "ISSUER_B", "ISSUER_C")
    portfolios: tuple[str, ...] = ("MM_CORE", "MM_FLOW", "MM_HEDGE", "MM_PROP")
    counterparties: tuple[str, ...] = ("CP_A", "CP_B", "CP_C", "CP_D", "CP_E")


class FakeTradeDataProvider:
    """
    Fast deterministic fake provider.

    Key guarantee:
      - returned trades df ALWAYS contains TRADES_COLS
      - app should only rely on those columns
    """

    def __init__(self, config: FakeDataConfig = FakeDataConfig()):
        self.config = config

    def load(self, from_date: date, to_date: date) -> pd.DataFrame:
        trades_raw = self._build_trades_raw(from_date, to_date)
        trades = normalize_trades_df(trades_raw)
        return trades

    def _build_trades_raw(self, from_date: date, to_date: date) -> pd.DataFrame:
        if to_date < from_date:
            raise ValueError("to_date must be >= from_date")

        rng = pd.date_range(
            start=pd.Timestamp(from_date),
            end=pd.Timestamp(to_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1),
            freq="s",
        )

        n = int(self.config.n_rows)
        if n <= 0 or len(rng) == 0:
            return pd.DataFrame(columns=TRADES_COLS)

        rs = np.arange(n, dtype=np.int64)
        seed = int(self.config.seed)

        idx = (rs * 1103515245 + seed) % len(rng)
        trade_time = rng.take(idx)

        instruments = np.array(
            ["DAX_CALL", "DAX_PUT", "SPX_CALL", "SPX_PUT", "SX5E_CALL", "SX5E_PUT"],
            dtype=object,
        )
        underlyings = np.array([f"UL_{i:03d}" for i in range(1, 101)], dtype=object)

        inst_idx = (rs * 2654435761 + 7) % len(instruments)
        ul_idx = (rs * 2246822519 + 19) % len(underlyings)

        instrument = instruments[inst_idx]
        underlying = underlyings[ul_idx]

        # base spots
        base_seed = ((ul_idx % 20) + 1) * 1000.0
        noise = ((rs * 104729 + 97) % 20001 - 10000) / 10.0
        spot = base_seed + noise

        strike = (np.round(spot / 50.0) * 50.0).astype(np.float64)
        quantity = ((rs * 37 + 11) % 200 + 1).astype(np.float64)
        trade_price = np.maximum(0.5, np.abs(spot - strike) / 100.0 + ((rs % 100) / 200.0)).astype(np.float64)

        trader_nr = ((rs * 17 + 3) % self.config.n_traders + 1).astype(np.int64)

        issuer = np.array(self.config.issuers, dtype=object)[(rs * 13 + 5) % len(self.config.issuers)]
        portfolio = np.array(self.config.portfolios, dtype=object)[(rs * 11 + 7) % len(self.config.portfolios)]
        counterparty = np.array(self.config.counterparties, dtype=object)[(rs * 19 + 9) % len(self.config.counterparties)]

        is_call = np.char.find(instrument.astype(str), "CALL") >= 0
        is_stock = np.zeros(n, dtype=bool)
        buy_or_sell = np.where(((rs + seed) % 2) == 0, "B", "S")

        tt = pd.to_datetime(trade_time)
        day_key = pd.Series(tt.date.astype(str))
        key = pd.Series(instrument.astype(str)) + " | " + day_key

        pnl_step = (((rs * 104729 + 97) % 2_000_001) - 1_000_000) / 100.0
        premia_step = (pnl_step * 0.60).astype(np.float64)
        delta_pnl_step = (pnl_step * 0.22).astype(np.float64)
        fees_step = (-np.abs(pnl_step) * 0.01).astype(np.float64)

        df = pd.DataFrame(
            {
                "traderNr": trader_nr,
                "instrument": instrument.astype(str),
                "issuer": pd.Series(issuer).astype(str),
                "strike": strike,
                "tradeTime": tt,
                "quantity": quantity,
                "tradePrice": trade_price,
                "tradeUnderlyingSpotRef": spot,
                "portfolio": pd.Series(portfolio).astype(str),
                "counterparty": pd.Series(counterparty).astype(str),
                "underlyingName": underlying.astype(str),
                "isCall": is_call,
                "isStock": is_stock,
                "buyOrSell": pd.Series(buy_or_sell).astype(str),
            }
        )

        df["_key"] = key.values
        df.sort_values(["_key", "tradeTime"], inplace=True, kind="mergesort")

        df["PremiaCum"] = pd.Series(premia_step, index=df.index).groupby(df["_key"]).cumsum()
        df["PnLVonDeltaCum"] = pd.Series(delta_pnl_step, index=df.index).groupby(df["_key"]).cumsum()
        df["feesCum"] = pd.Series(fees_step, index=df.index).groupby(df["_key"]).cumsum()

        df["Premia"] = df.groupby(df["_key"])["PremiaCum"].diff().fillna(df["PremiaCum"])
        df["PnLVonDelta"] = df.groupby(df["_key"])["PnLVonDeltaCum"].diff().fillna(df["PnLVonDeltaCum"])
        df["fees"] = df.groupby(df["_key"])["feesCum"].diff().fillna(df["feesCum"])

        # synthetic delta / deltaCum
        d_step = (((rs * 8191 + 23) % 2001) - 1000) / 5000.0
        df["deltaCum"] = pd.Series(d_step, index=df.index).groupby(df["_key"]).cumsum()
        df["delta"] = df.groupby(df["_key"])["deltaCum"].diff().fillna(df["deltaCum"])

        df["Total"] = df["PremiaCum"] + df["PnLVonDeltaCum"] + df["feesCum"]

        df.drop(columns=["_key"], inplace=True)
        df.sort_values(["tradeTime"], inplace=True, kind="mergesort")
        df.reset_index(drop=True, inplace=True)

        return df


def normalize_trades_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensures:
      - TRADES_COLS exist
      - date is derived from tradeTime
      - tolerant to alternate column names
    Keeps extra columns if present.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=TRADES_COLS)

    out = df.copy()

    rename_map = {
        "underlying": "underlyingName",
        "PnlVonDeltaCum": "PnLVonDeltaCum",
        "PnlVonDelta": "PnLVonDelta",
        "tradeNr": "traderNr",
        "Delta": "delta",
        "DeltaCum": "deltaCum"
    }
    for src, dst in rename_map.items():
        if src in out.columns and dst not in out.columns:
            out = out.rename(columns={src: dst})

    if "tradeTime" in out.columns:
        out["tradeTime"] = pd.to_datetime(out["tradeTime"], errors="coerce")
        out["date"] = out["tradeTime"].dt.date
    else:
        out["tradeTime"] = pd.NaT
        out["date"] = pd.NaT

    defaults = {
        "traderNr": 0,
        "instrument": "",
        "issuer": "",
        "strike": np.nan,
        "quantity": 0.0,
        "tradePrice": np.nan,
        "tradeUnderlyingSpotRef": np.nan,
        "portfolio": "",
        "counterparty": "",
        "underlyingName": "",
        "isCall": False,
        "isStock": False,
        "fees": 0.0,
        "buyOrSell": "",
        "Premia": 0.0,
        "PremiaCum": 0.0,
        "PnLVonDelta": 0.0,
        "PnLVonDeltaCum": 0.0,
        "delta": 0.0,
        "deltaCum": 0.0,
        "feesCum": 0.0,
        "Total": 0.0,
    }

    for c in TRADES_COLS:
        if c not in out.columns:
            out[c] = defaults.get(c, np.nan)

    if "PremiaCum" in out.columns and "Premia" in out.columns:
        if out["Premia"].isna().all() or (pd.to_numeric(out["Premia"], errors="coerce").fillna(0).abs().sum() == 0):
            out["Premia"] = out.groupby(["instrument", "date"])["PremiaCum"].diff().fillna(out["PremiaCum"])

    if "PnLVonDeltaCum" in out.columns and "PnLVonDelta" in out.columns:
        if out["PnLVonDelta"].isna().all() or (pd.to_numeric(out["PnLVonDelta"], errors="coerce").fillna(0).abs().sum() == 0):
            out["PnLVonDelta"] = out.groupby(["instrument", "date"])["PnLVonDeltaCum"].diff().fillna(out["PnLVonDeltaCum"])

    if "feesCum" in out.columns and "fees" in out.columns:
        if out["fees"].isna().all() or (pd.to_numeric(out["fees"], errors="coerce").fillna(0).abs().sum() == 0):
            out["fees"] = out.groupby(["instrument", "date"])["feesCum"].diff().fillna(out["feesCum"])

    if "deltaCum" in out.columns and "delta" in out.columns:
        if out["delta"].isna().all() or (pd.to_numeric(out["delta"], errors="coerce").fillna(0).abs().sum() == 0):
            out["delta"] = out.groupby(["instrument", "date"])["deltaCum"].diff().fillna(out["deltaCum"])

    extras = [c for c in out.columns if c not in TRADES_COLS]
    out = out.loc[:, TRADES_COLS + extras]

    return out