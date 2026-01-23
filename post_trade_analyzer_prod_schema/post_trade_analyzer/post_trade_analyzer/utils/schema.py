from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

PROD_COLS = [
    "tradeNr",
    "instrument",
    "tradeTime",
    "tradeUnderlyingSpotRef",
    "portfolio",
    "counterparty",
    "underlying",
    "CumDelta",
    "CumDelta_stock",
    "CumDelta_certificates_abandon",
    "CumDelta_our_abandon",
    "CumDelta_external_abandon",
    "CumDelta_our_scheine",
    "CumDelta_external_scheine",
    "PremiaCum",
    "SpreadsCapture",
    "FullSpreadCapture",
    "Total",
    "PnlVonDeltaCum",
    "feesCum",
    "AufgeldCum",
]

@dataclass(frozen=True)
class SchemaConfig:
    total_columns: int = 64

def flag_cols(cfg: SchemaConfig = SchemaConfig()) -> list[str]:
    n_flags = cfg.total_columns - len(PROD_COLS)
    if n_flags < 0:
        raise ValueError("SchemaConfig.total_columns is smaller than number of production columns.")
    return [f"flag_{i:02d}" for i in range(n_flags)]

def build_empty_trade_df(n_rows: int = 0, cfg: SchemaConfig = SchemaConfig()) -> pd.DataFrame:
    bool_cols = flag_cols(cfg)
    columns = PROD_COLS + bool_cols
    if len(columns) != cfg.total_columns:
        raise AssertionError(f"Schema mismatch: {len(columns)} != {cfg.total_columns}")

    df = pd.DataFrame(index=range(n_rows), columns=columns)

    dtypes = {
        "tradeNr": "int64",
        "instrument": "string",
        "tradeTime": "datetime64[ns]",
        "tradeUnderlyingSpotRef": "float64",
        "portfolio": "string",
        "counterparty": "string",
        "underlying": "string",
        "CumDelta": "float64",
        "CumDelta_stock": "float64",
        "CumDelta_certificates_abandon": "float64",
        "CumDelta_our_abandon": "float64",
        "CumDelta_external_abandon": "float64",
        "CumDelta_our_scheine": "float64",
        "CumDelta_external_scheine": "float64",
        "PremiaCum": "float64",
        "SpreadsCapture": "float64",
        "FullSpreadCapture": "float64",
        "Total": "float64",
        "PnlVonDeltaCum": "float64",
        "feesCum": "float64",
        "AufgeldCum": "float64",
        **{c: "boolean" for c in bool_cols},
    }

    if n_rows == 0:
        return df.astype(dtypes)

    df["tradeNr"] = pd.Series(range(1, n_rows + 1), dtype="int64")
    df["instrument"] = pd.Series([""] * n_rows, dtype="string")
    df["tradeTime"] = pd.NaT
    df["tradeUnderlyingSpotRef"] = 0.0
    df["portfolio"] = pd.Series([""] * n_rows, dtype="string")
    df["counterparty"] = pd.Series([""] * n_rows, dtype="string")
    df["underlying"] = pd.Series([""] * n_rows, dtype="string")

    for c in PROD_COLS:
        if c in ("tradeNr", "instrument", "tradeTime", "tradeUnderlyingSpotRef", "portfolio", "counterparty", "underlying"):
            continue
        df[c] = 0.0

    for c in bool_cols:
        df[c] = pd.Series([False] * n_rows, dtype="boolean")

    return df.astype(dtypes)

def validate_trade_df(df: pd.DataFrame, cfg: SchemaConfig = SchemaConfig()) -> None:
    missing = set(PROD_COLS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required production columns: {sorted(missing)}")

    if df.shape[1] != cfg.total_columns:
        raise ValueError(f"Expected {cfg.total_columns} columns, got {df.shape[1]}.")

    if not pd.api.types.is_datetime64_any_dtype(df["tradeTime"]):
        raise ValueError("tradeTime must be datetime64 dtype (pandas datetime).")
