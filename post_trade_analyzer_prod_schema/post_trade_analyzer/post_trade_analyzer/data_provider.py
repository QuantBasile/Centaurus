from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd

from .utils.schema import build_empty_trade_df, flag_cols, SchemaConfig

class TradeDataProvider(Protocol):
    def load_trades(self, from_date: date, to_date: date) -> pd.DataFrame:
        ...

@dataclass(frozen=True)
class FakeDataConfig:
    n_rows: int = 200_000
    seed: int = 42
    schema: SchemaConfig = SchemaConfig()

class FakeTradeDataProvider:
    """Deterministic fake data generator matching the production schema."""

    def __init__(self, config: FakeDataConfig = FakeDataConfig()):
        self.config = config

    def load_trades(self, from_date: date, to_date: date) -> pd.DataFrame:
        if to_date < from_date:
            raise ValueError("to_date must be >= from_date")

        rng = pd.date_range(
            start=pd.Timestamp(from_date),
            end=pd.Timestamp(to_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1),
            freq="S",
        )
        if len(rng) == 0:
            return build_empty_trade_df(cfg=self.config.schema)

        n = self.config.n_rows
        rs = pd.Series(range(n), dtype="int64")

        idx = (rs * 1103515245 + self.config.seed) % len(rng)
        trade_time = rng.take(idx.astype("int64"))

        instruments = ["DAX_CALL", "DAX_PUT", "SPX_CALL", "SPX_PUT", "SX5E_CALL", "SX5E_PUT"]
        underlyings = ["DAX", "SPX", "SX5E", "NDX", "AAPL", "MSFT"]
        counterparties = ["CP_A", "CP_B", "CP_C", "CP_D", "CP_E", "CP_F", "CP_G"]
        portfolios = ["MM_CORE", "MM_FLOW", "MM_HEDGE", "MM_PROP"]

        inst_idx = (rs * 2654435761 + 7) % len(instruments)
        ul_idx = (rs * 2246822519 + 19) % len(underlyings)
        cp_idx = (rs * 1597334677 + 13) % len(counterparties)
        pf_idx = (rs * 3266489917 + 3) % len(portfolios)

        df = build_empty_trade_df(n_rows=n, cfg=self.config.schema)

        df["tradeNr"] = pd.Series(range(1, n + 1), dtype="int64")
        df["tradeTime"] = pd.to_datetime(trade_time)
        df["instrument"] = pd.Series([instruments[int(i)] for i in inst_idx.tolist()], dtype="string")
        df["underlying"] = pd.Series([underlyings[int(i)] for i in ul_idx.tolist()], dtype="string")
        df["counterparty"] = pd.Series([counterparties[int(i)] for i in cp_idx.tolist()], dtype="string")
        df["portfolio"] = pd.Series([portfolios[int(i)] for i in pf_idx.tolist()], dtype="string")

        base_map = {"DAX": 18000.0, "SPX": 5200.0, "SX5E": 4800.0, "NDX": 18000.0, "AAPL": 190.0, "MSFT": 420.0}
        noise = ((rs * 104729 + 97) % 20001 - 10000) / 10.0  # [-1000, +1000]
        df["tradeUnderlyingSpotRef"] = [base_map.get(underlyings[int(ul_idx.iloc[i])], 1000.0) + float(noise.iloc[i]) for i in range(n)]

        d_step = ((rs * 8191 + 23) % 2001 - 1000) / 5000.0  # ~[-0.2, 0.2]
        pnl_step = ((rs * 104729 + 97) % 2_000_001 - 1_000_000) / 100.0  # [-10000, +10000]
        w_stock = ((rs * 37 + 11) % 1000) / 1000.0
        w_cert = 1.0 - w_stock

        day_key = df["tradeTime"].dt.date.astype("string")
        key = df["instrument"].astype("string") + " | " + day_key
        df["_key"] = key
        df.sort_values(["_key", "tradeTime"], inplace=True, kind="mergesort")

        df["CumDelta_stock"] = pd.Series((d_step * w_stock).values, index=df.index).groupby(df["_key"]).cumsum()
        df["CumDelta_our_scheine"] = pd.Series((d_step * w_cert * 0.55).values, index=df.index).groupby(df["_key"]).cumsum()
        df["CumDelta_external_scheine"] = pd.Series((d_step * w_cert * 0.45).values, index=df.index).groupby(df["_key"]).cumsum()

        df["CumDelta_certificates_abandon"] = pd.Series((d_step * w_cert * 0.30).values, index=df.index).groupby(df["_key"]).cumsum()
        df["CumDelta_our_abandon"] = pd.Series((d_step * w_cert * 0.40).values, index=df.index).groupby(df["_key"]).cumsum()
        df["CumDelta_external_abandon"] = pd.Series((d_step * w_cert * 0.30).values, index=df.index).groupby(df["_key"]).cumsum()

        df["CumDelta"] = df["CumDelta_stock"] + df["CumDelta_our_scheine"] + df["CumDelta_external_scheine"]

        df["PremiaCum"] = pd.Series((pnl_step * 0.60).values, index=df.index).groupby(df["_key"]).cumsum()
        df["SpreadsCapture"] = pd.Series((pnl_step * 0.08).values, index=df.index).groupby(df["_key"]).cumsum()
        df["FullSpreadCapture"] = pd.Series((pnl_step * 0.05).values, index=df.index).groupby(df["_key"]).cumsum()
        df["PnlVonDeltaCum"] = pd.Series((pnl_step * 0.22).values, index=df.index).groupby(df["_key"]).cumsum()
        df["feesCum"] = pd.Series((-abs(pnl_step) * 0.01).values, index=df.index).groupby(df["_key"]).cumsum()
        df["AufgeldCum"] = pd.Series((pnl_step * 0.03).values, index=df.index).groupby(df["_key"]).cumsum()

        df["Total"] = (
            df["PremiaCum"]
            + df["SpreadsCapture"]
            + df["FullSpreadCapture"]
            + df["PnlVonDeltaCum"]
            + df["feesCum"]
            + df["AufgeldCum"]
        )

        for j, col in enumerate(flag_cols(self.config.schema)):
            df[col] = ((rs + j) % (7 + (j % 9))) == 0

        df.drop(columns=["_key"], inplace=True)
        df.sort_values(["tradeTime"], inplace=True, kind="mergesort")
        df.reset_index(drop=True, inplace=True)

        return df
