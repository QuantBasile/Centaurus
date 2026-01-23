from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import pandas as pd

def build_display_cache(df: pd.DataFrame) -> Tuple[Dict[str, List[str]], int]:
    """Column-wise cache of formatted strings for fast table rendering."""
    cache: Dict[str, List[str]] = {}
    if df is None or df.empty:
        return cache, 0

    n = len(df)
    for c in df.columns:
        s = df[c]
        if c == "tradeTime":
            cache[c] = [
                "" if pd.isna(v) else pd.Timestamp(v).strftime("%Y-%m-%d %H:%M:%S")
                for v in s
            ]
        elif c == "tradeNr":
            cache[c] = [
                "" if pd.isna(v) else str(int(v))
                for v in s
            ]
        elif c.startswith("flag_"):
            cache[c] = [
                "" if pd.isna(v) else ("✔" if bool(v) else "X")
                for v in s
            ]
        else:
            if pd.api.types.is_numeric_dtype(s):
                cache[c] = [
                    "" if pd.isna(v) else f"{float(v):.4f}"
                    for v in s
                ]
            else:
                cache[c] = [
                    "" if pd.isna(v) else str(v)
                    for v in s
                ]
    return cache, n

def sanitize_visible_cols(all_cols: List[str], visible_cols: Optional[List[str]]) -> List[str]:
    if not visible_cols:
        return all_cols[:]
    s = set(all_cols)
    return [c for c in visible_cols if c in s]
