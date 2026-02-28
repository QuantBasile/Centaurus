from __future__ import annotations

from dataclasses import dataclass
from datetime import date as DateType
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk

import pandas as pd

from ..utils.table_utils import build_display_cache


# ============================================================
# Simple autocomplete combobox (fast + robust)
# ============================================================
class AutocompleteCombobox(ttk.Combobox):
    """
    Simple autocomplete combobox:
    - keeps a master list of values
    - filters on KeyRelease
    - supports empty selection
    """

    def __init__(self, master, *, values: List[str], **kwargs):
        super().__init__(master, values=values, **kwargs)
        self._all_values = list(values)
        self.bind("<KeyRelease>", self._on_keyrelease)

    def set_values(self, values: List[str]) -> None:
        self._all_values = list(values)
        self["values"] = self._all_values

    def _on_keyrelease(self, event) -> None:
        if event.keysym in ("Up", "Down", "Left", "Right", "Return", "Escape", "Tab"):
            return
        text = self.get().strip().lower()
        if not text:
            self["values"] = self._all_values
            return
        filtered = [v for v in self._all_values if text in v.lower()]
        self["values"] = filtered if filtered else self._all_values


# ============================================================
# EndOfDay Sheet (Underlying-only selection)
# ============================================================
@dataclass(frozen=True)
class EODSelection:
    underlying: str = ""


class EndOfDaySheet(ttk.Frame):
    sheet_id = "eod"
    sheet_title = "EndOfDay"

    HIST_METRICS = ["feesCum", "PnLVonDeltaCum", "PremiaCum", "Total", "Anpassung"]

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._trades: Optional[pd.DataFrame] = None
        self._adj: Optional[pd.DataFrame] = None

        self._eod: Optional[pd.DataFrame] = None  # last trade per (underlyingName, date)
        self._sel = EODSelection()

        self._build()

    def _build(self) -> None:
        # Top title
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(14, 10))
        ttk.Label(top, text="EndOfDay", style="Title.TLabel").pack(side="left")

        # Search panel (Underlying-only)
        search = ttk.Frame(self)
        search.pack(fill="x", padx=14, pady=(0, 10))

        ttk.Label(search, text="Underlying", style="Muted.TLabel").grid(row=0, column=0, sticky="w")

        self.underlying_var = tk.StringVar()
        self.underlying_cb = AutocompleteCombobox(
            search, values=[], textvariable=self.underlying_var, state="normal", width=28
        )
        self.underlying_cb.grid(row=1, column=0, sticky="w")

        ttk.Button(search, text="Apply",style="Accent.TButton", command=self._apply_selection).grid(row=1, column=1, padx=(14, 0))
        ttk.Button(search, text="Clear", command=self._clear_selection).grid(row=1, column=2, padx=(8, 0))

        self.sel_info = tk.StringVar(value="Selected: Underlying=(all)")
        ttk.Label(search, textvariable=self.sel_info, style="Muted.TLabel").grid(
            row=1, column=3, sticky="w", padx=(14, 0)
        )

        # Main notebook
        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        self.nb = ttk.Notebook(inner)
        self.nb.pack(fill="both", expand=True)

        self.tab_data = EODDataTab(self.nb)
        self.tab_adj = EODAdjustmentsTab(self.nb)
        self.tab_plot = EODPlotTab(self.nb, hist_metrics=self.HIST_METRICS)

        self.nb.add(self.tab_data, text="Data")
        self.nb.add(self.tab_adj, text="Data II (Anpassung)")
        self.nb.add(self.tab_plot, text="Plot")

    # -------------------------
    # API called by app
    # -------------------------
    def on_df_loaded(self, trades: pd.DataFrame) -> None:
        self._trades = trades
        self._rebuild_eod_if_possible()

    def on_adjustment_loaded(self, adj: pd.DataFrame) -> None:
        self._adj = adj
        self._rebuild_eod_if_possible()

    # -------------------------
    # Build EOD core df
    # -------------------------
    def _rebuild_eod_if_possible(self) -> None:
        if self._trades is None:
            return

        self._eod = self._build_eod_last_trade_per_day_underlying(self._trades)

        # Update underlying list
        if self._eod is not None and not self._eod.empty:
            underlyings = sorted(self._eod["underlyingName"].astype(str).dropna().unique().tolist())
        else:
            underlyings = []

        self.underlying_cb.set_values(underlyings)

        # Push initial (unfiltered) view
        self._push_filtered()

    @staticmethod
    def _build_eod_last_trade_per_day_underlying(df: pd.DataFrame) -> pd.DataFrame:
        """
        Last row per (underlyingName, date) using idxmax(tradeTime).
        Assumes df has columns: underlyingName, date, tradeTime (date derived already).
        """
        if df is None or df.empty:
            return pd.DataFrame()
        if "underlyingName" not in df.columns or "date" not in df.columns or "tradeTime" not in df.columns:
            return pd.DataFrame()

        tt = pd.to_datetime(df["tradeTime"], errors="coerce")
        helper = pd.DataFrame(
            {"underlyingName": df["underlyingName"], "date": df["date"], "_tt": tt}
        ).dropna(subset=["underlyingName", "date", "_tt"])

        if helper.empty:
            return pd.DataFrame()

        idx = helper.groupby(["underlyingName", "date"], sort=False)["_tt"].idxmax()
        out = df.loc[idx].copy()
        out.reset_index(drop=True, inplace=True)
        return out

    # -------------------------
    # Selection / filtering
    # -------------------------
    def _apply_selection(self) -> None:
        u = self.underlying_var.get().strip()
        self._sel = EODSelection(underlying=u)
        self._push_filtered()

    def _clear_selection(self) -> None:
        self.underlying_var.set("")
        self._sel = EODSelection()
        self._push_filtered()

    def _push_filtered(self) -> None:
        eod = self._eod
        if eod is None or eod.empty:
            self.sel_info.set("Selected: Underlying=(all) — no data")
            self.tab_data.set_df(pd.DataFrame())
            self.tab_adj.set_df(pd.DataFrame())
            self.tab_plot.set_data(pd.DataFrame(), pd.DataFrame())
            return

        df = eod
        if self._sel.underlying:
            df = df[df["underlyingName"].astype(str) == self._sel.underlying]

        df = df.reset_index(drop=True)

        # Selected label
        if self._sel.underlying:
            self.sel_info.set(f"Selected: Underlying={self._sel.underlying}")
        else:
            self.sel_info.set("Selected: Underlying=(all)")

        # Data tab
        self.tab_data.set_df(df)

        # Adjustments tab (filtered by underlying + matching dates)
        adj_view = self._filter_adjustments_for_selection(df)
        self.tab_adj.set_df(adj_view)

        # Plot tab gets both
        self.tab_plot.set_data(df, adj_view)

    def _filter_adjustments_for_selection(self, df_eod_filtered: pd.DataFrame) -> pd.DataFrame:
        adj = self._adj
        if adj is None or adj.empty:
            return pd.DataFrame(columns=["underlyingName", "date", "Anpassung"])

        out = adj.copy()
        if "underlyingName" not in out.columns and "underlying" in out.columns:
            out = out.rename(columns={"underlying": "underlyingName"})

        if self._sel.underlying:
            out = out[out["underlyingName"].astype(str) == self._sel.underlying]

        if df_eod_filtered is not None and not df_eod_filtered.empty and "date" in df_eod_filtered.columns:
            dates = set(df_eod_filtered["date"].dropna().tolist())
            out = out[out["date"].isin(dates)]

        sort_cols = [c for c in ["date", "underlyingName"] if c in out.columns]
        if sort_cols:
            out = out.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)
        return out


# ============================================================
# Data tab (sortable table, fast)
# ============================================================
class EODDataTab(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._df: pd.DataFrame = pd.DataFrame()
        self._df_view: pd.DataFrame = pd.DataFrame()

        self._cache: Dict[str, List[str]] = {}
        self._cache_len: int = 0

        self._sort_col: Optional[str] = None
        self._sort_asc: bool = True

        self.info_var = tk.StringVar(value="No rows.")
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(10, 8))
        ttk.Label(top, textvariable=self.info_var, style="Muted.TLabel").pack(side="right")

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(inner, style="Futur.Treeview", show="headings")
        self.vsb = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        self.hsb = ttk.Scrollbar(inner, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")
        inner.rowconfigure(0, weight=1)
        inner.columnconfigure(0, weight=1)

        self.tree.tag_configure("odd", background="#FFFFFF")
        self.tree.tag_configure("even", background="#F8FAFF")

        # PERF: no resize bindings, no autofit, stretch=False

    def set_df(self, df: pd.DataFrame) -> None:
        self._df = df if df is not None else pd.DataFrame()
        self._df_view = self._df
        self._sort_col = None
        self._sort_asc = True

        n = len(self._df_view)
        self.info_var.set(f"{n:,} rows (EOD last trade per day & underlying)")

        self._cache, self._cache_len = build_display_cache(self._df_view)
        self._render()

    def _render(self) -> None:
        self.tree.delete(*self.tree.get_children())
        df = self._df_view
        if df is None or df.empty:
            self.tree["columns"] = []
            return

        cols = list(df.columns)
        self.tree["columns"] = cols

        for c in cols:
            self.tree.heading(c, text=c, command=lambda col=c: self._sort_by(col))
            self.tree.column(c, width=110, minwidth=80, anchor="c", stretch=False)

        cache = self._cache
        for i in range(self._cache_len):
            values = [cache[c][i] for c in cols]
            tag = "even" if (i % 2 == 0) else "odd"
            self.tree.insert("", "end", values=values, tags=(tag,))

    def _sort_by(self, col: str) -> None:
        df = self._df
        if df is None or df.empty:
            return

        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        try:
            view = df.sort_values(by=col, ascending=self._sort_asc, kind="mergesort")
        except Exception:
            view = (
                df.assign(_tmp=df[col].astype(str))
                .sort_values(by="_tmp", ascending=self._sort_asc, kind="mergesort")
                .drop(columns="_tmp")
            )

        self._df_view = view.reset_index(drop=True)
        self._cache, self._cache_len = build_display_cache(self._df_view)
        self._render()


# ============================================================
# Adjustments tab (sortable table, simple)
# ============================================================
class EODAdjustmentsTab(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._df: pd.DataFrame = pd.DataFrame()
        self._df_view: pd.DataFrame = pd.DataFrame()

        self._cache: Dict[str, List[str]] = {}
        self._cache_len: int = 0

        self._sort_col: Optional[str] = None
        self._sort_asc: bool = True

        self.info_var = tk.StringVar(value="No rows.")
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(10, 8))
        ttk.Label(top, textvariable=self.info_var, style="Muted.TLabel").pack(side="right")

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(inner, style="Futur.Treeview", show="headings")
        self.vsb = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        self.hsb = ttk.Scrollbar(inner, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")
        inner.rowconfigure(0, weight=1)
        inner.columnconfigure(0, weight=1)

        self.tree.tag_configure("odd", background="#FFFFFF")
        self.tree.tag_configure("even", background="#F8FAFF")

    def set_df(self, df: pd.DataFrame) -> None:
        self._df = df if df is not None else pd.DataFrame()
        self._df_view = self._df
        self._sort_col = None
        self._sort_asc = True

        n = len(self._df_view)
        self.info_var.set(f"{n:,} rows (Anpassung)")

        self._cache, self._cache_len = build_display_cache(self._df_view)
        self._render()

    def _render(self) -> None:
        self.tree.delete(*self.tree.get_children())
        df = self._df_view
        if df is None or df.empty:
            self.tree["columns"] = []
            return

        cols = list(df.columns)
        self.tree["columns"] = cols

        for c in cols:
            self.tree.heading(c, text=c, command=lambda col=c: self._sort_by(col))
            self.tree.column(c, width=140 if c != "Anpassung" else 120, minwidth=80, anchor="c", stretch=False)

        cache = self._cache
        for i in range(self._cache_len):
            values = [cache[c][i] for c in cols]
            tag = "even" if (i % 2 == 0) else "odd"
            self.tree.insert("", "end", values=values, tags=(tag,))

    def _sort_by(self, col: str) -> None:
        df = self._df
        if df is None or df.empty:
            return

        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        try:
            view = df.sort_values(by=col, ascending=self._sort_asc, kind="mergesort")
        except Exception:
            view = (
                df.assign(_tmp=df[col].astype(str))
                .sort_values(by="_tmp", ascending=self._sort_asc, kind="mergesort")
                .drop(columns="_tmp")
            )

        self._df_view = view.reset_index(drop=True)
        self._cache, self._cache_len = build_display_cache(self._df_view)
        self._render()


# ============================================================
# Plot tab — CEO single canvas (cumulative lines + daily bars)
#   - Y axes with ticks
#   - highlighted zero line
#   - dynamic left padding so big labels don't clip
#   - variable toggles + redraw
#   - hover tooltip on bars
# ============================================================
class EODPlotTab(ttk.Frame):
    PNL_NAME = "PnL (Anpassung+Total)"

    def __init__(self, master: tk.Misc, hist_metrics: List[str]) -> None:
        super().__init__(master)

        self._eod: pd.DataFrame = pd.DataFrame()
        self._adj: pd.DataFrame = pd.DataFrame()

        base = [v for v in ["feesCum", "PnLVonDeltaCum", "PremiaCum", "Total", "Anpassung"] if v in hist_metrics]
        if not base:
            base = hist_metrics[:]

        # ensure derived PnL present
        self._vars = base + [self.PNL_NAME]

        self._var_enabled: Dict[str, tk.BooleanVar] = {v: tk.BooleanVar(value=True) for v in self._vars}

        self._daily: pd.DataFrame = pd.DataFrame()

        # Hover geometry caches
        self._bar_hits: List[Dict[str, object]] = []
        self._tooltip: Optional[tk.Toplevel] = None

        self._build()

    def _build(self) -> None:
        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=10, pady=10)

        top = ttk.Frame(card, style="Card.TFrame")
        top.pack(fill="x", padx=10, pady=(10, 6))

        ttk.Button(top, text="Redraw", command=self.redraw).pack(side="left")

        chk = ttk.Frame(top)
        chk.pack(side="left", padx=(12, 0))
        for v in self._vars:
            ttk.Checkbutton(chk, text=v, variable=self._var_enabled[v], command=self.redraw).pack(
                side="left", padx=(0, 10)
            )

        self.info_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.info_var, style="Muted.TLabel").pack(side="right")

        self.canvas = tk.Canvas(card, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda e: self._hide_tooltip())

        # PERF: no redraw-on-resize bindings

    # API
    def set_data(self, eod_filtered: pd.DataFrame, adj_filtered: pd.DataFrame) -> None:
        self._eod = eod_filtered if eod_filtered is not None else pd.DataFrame()
        self._adj = adj_filtered if adj_filtered is not None else pd.DataFrame()
        self._daily = self._build_daily_frame()
        self.redraw()

    def _enabled_vars(self) -> List[str]:
        out = [v for v in self._vars if self._var_enabled[v].get()]
        return out if out else [self._vars[0]]

    # Data prep: aggregate per date + merge adjustments
    def _build_daily_frame(self) -> pd.DataFrame:
        eod = self._eod
        if eod is None or eod.empty:
            return pd.DataFrame()

        need = ["date", "PremiaCum", "PnLVonDeltaCum", "feesCum", "Total"]
        for c in need:
            if c not in eod.columns:
                return pd.DataFrame()

        tmp = pd.DataFrame(
            {
                "date": eod["date"],
                "PremiaCum": pd.to_numeric(eod["PremiaCum"], errors="coerce").fillna(0.0),
                "PnLVonDeltaCum": pd.to_numeric(eod["PnLVonDeltaCum"], errors="coerce").fillna(0.0),
                "feesCum": pd.to_numeric(eod["feesCum"], errors="coerce").fillna(0.0),
                "Total": pd.to_numeric(eod["Total"], errors="coerce").fillna(0.0),
            }
        ).dropna(subset=["date"])

        day = (
            tmp.groupby("date", sort=False, as_index=False)[["PremiaCum", "PnLVonDeltaCum", "feesCum", "Total"]].sum()
        )
        day = day.sort_values("date", kind="mergesort").reset_index(drop=True)

        # Merge adjustments by date (already filtered by underlying upstream)
        adj = self._adj
        if adj is not None and not adj.empty and "date" in adj.columns and "Anpassung" in adj.columns:
            a = adj.copy()
            a["Anpassung"] = pd.to_numeric(a["Anpassung"], errors="coerce").fillna(0.0)
            a_day = a.groupby("date", sort=False, as_index=False)[["Anpassung"]].sum()
            out = day.merge(a_day, on="date", how="left")
            out["Anpassung"] = out["Anpassung"].fillna(0.0)
        else:
            out = day.copy()
            out["Anpassung"] = 0.0

        # Derived PnL
        out[self.PNL_NAME] = out["Total"] + out["Anpassung"]
        return out

    # Drawing
    def redraw(self) -> None:
        import math

        c = self.canvas
        c.delete("all")
        self._bar_hits = []

        df = self._daily
        if df is None or df.empty:
            self.info_var.set("No data.")
            return

        enabled = self._enabled_vars()

        # Downsample days to keep canvas fast
        max_days = 240
        if len(df) > max_days:
            idx = pd.Series(range(len(df)))
            pick = (idx * (len(df) - 1) // (max_days - 1)).drop_duplicates().astype(int).tolist()
            df = df.iloc[pick].reset_index(drop=True)

        # Working frame with derived PnL guaranteed
        df_work = df.copy()
        if self.PNL_NAME not in df_work.columns:
            if "Total" in df_work.columns and "Anpassung" in df_work.columns:
                df_work[self.PNL_NAME] = (
                    pd.to_numeric(df_work["Total"], errors="coerce").fillna(0.0)
                    + pd.to_numeric(df_work["Anpassung"], errors="coerce").fillna(0.0)
                )
            else:
                df_work[self.PNL_NAME] = 0.0

        days = df_work["date"].astype(str).tolist()
        n = len(days)

        # Build daily series and cumulatives
        daily_vals: Dict[str, List[float]] = {}
        cum_vals: Dict[str, List[float]] = {}

        for v in enabled:
            if v not in df_work.columns:
                daily_vals[v] = [0.0] * len(df_work)
            else:
                daily_vals[v] = pd.to_numeric(df_work[v], errors="coerce").fillna(0.0).astype(float).tolist()

            s = 0.0
            cv = []
            for x in daily_vals[v]:
                s += float(x)
                cv.append(s)
            cum_vals[v] = cv

        # Canvas size
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())

        # Determine scales
        all_cum = [v for k in enabled for v in cum_vals[k]]
        all_daily = [v for k in enabled for v in daily_vals[k]]
        vmax = max(1e-9, max(abs(v) for v in all_cum)) if all_cum else 1.0
        vmaxb = max(1e-9, max(abs(v) for v in all_daily)) if all_daily else 1.0

        # Dynamic left padding for big Y labels (prevents clipping)
        max_label = max(vmax, vmaxb)
        digits = int(math.log10(max_label)) + 1 if max_label >= 1 else 1
        pad_l = max(54, 18 + digits * 9)

        pad_r = 16
        pad_t = 16
        pad_b = 28

        split = 0.60
        y_split = int(pad_t + (h - pad_t - pad_b) * split)

        x0, x1 = pad_l, w - pad_r
        y0_top, y1_top = pad_t, y_split - 10
        y0_bot, y1_bot = y_split + 10, h - pad_b

        if x1 <= x0 + 50 or y1_bot <= y0_top + 50:
            self.info_var.set("Canvas too small.")
            return

        # Frames
        c.create_rectangle(x0, y0_top, x1, y1_top, outline="#DDE3F0")
        c.create_rectangle(x0, y0_bot, x1, y1_bot, outline="#DDE3F0")

        slot = (x1 - x0) / max(1, n)

        def x_at(i: int) -> float:
            return x0 + slot * (i + 0.5)

        mid_top = (y0_top + y1_top) / 2
        mid_bot = (y0_bot + y1_bot) / 2

        def y_top(v: float) -> float:
            return mid_top - (v / vmax) * (y1_top - y0_top) * 0.45

        def y_bot(v: float) -> float:
            return mid_bot - (v / vmaxb) * (y1_bot - y0_bot) * 0.45

        # Helpers: nice ticks + y axis
        def nice_step(v: float) -> float:
            if v <= 0:
                return 1.0
            exp = math.floor(math.log10(v))
            f = v / (10**exp)
            if f <= 1:
                nf = 1
            elif f <= 2:
                nf = 2
            elif f <= 5:
                nf = 5
            else:
                nf = 10
            return nf * (10**exp)

        def draw_y_axis(x_axis: float, y_top_px: float, y_bot_px: float, vmax_abs: float, map_y):
            c.create_line(x_axis, y_top_px, x_axis, y_bot_px, fill="#E5E7EB")
            vmax_abs = max(1e-9, float(vmax_abs))
            step = nice_step(vmax_abs / 4.0)
            k = int(vmax_abs // step) + 1
            k = min(k, 6)
            ticks = [i * step for i in range(-k, k + 1)]
            for t in ticks:
                if abs(t) > vmax_abs * 1.001:
                    continue
                y = map_y(t)
                c.create_line(x_axis - 5, y, x_axis, y, fill="#E5E7EB")
                c.create_text(
                    x_axis - 8,
                    y,
                    text=f"{t:,.0f}",
                    anchor="e",
                    fill="#6B7280",
                    font=("TkDefaultFont", 8),
                )

        draw_y_axis(x0, y0_top, y1_top, vmax, y_top)
        draw_y_axis(x0, y0_bot, y1_bot, vmaxb, y_bot)

        # Zero lines (highlighted)
        c.create_line(x0, mid_top, x1, mid_top, fill="#CBD5E1", width=2)
        c.create_line(x0, mid_bot, x1, mid_bot, fill="#CBD5E1", width=2)

        # Colors (CEO style)
        color_map = {
            "PremiaCum": "#4A6CF7",         # blue
            "PnLVonDeltaCum": "#111827",    # near black
            "feesCum": "#F97316",           # orange
            "Total": "#7C3AED",             # purple
            "Anpassung": "#10B981",         # green
            self.PNL_NAME: "#0EA5E9",       # cyan
        }

        # TOP: cumulative lines
        for v in enabled:
            pts: List[float] = []
            series = cum_vals[v]
            for i in range(n):
                pts.extend([x_at(i), y_top(series[i])])
            if len(pts) >= 4:
                c.create_line(*pts, fill=color_map.get(v, "#111827"), width=2)

        # Right-side final values
        y_text = y0_top + 10
        c.create_text(
            x1 - 6, y0_top - 2, text="Final (cum)", anchor="ne", fill="#6B7280", font=("TkDefaultFont", 9)
        )
        for v in enabled:
            final = cum_vals[v][-1] if cum_vals[v] else 0.0
            c.create_text(
                x1 - 6,
                y_text,
                text=f"{v}: {final:,.2f}",
                anchor="ne",
                fill=color_map.get(v, "#111827"),
                font=("TkDefaultFont", 9, "bold"),
            )
            y_text += 16

        # BOTTOM: per-day grouped bars (green/red by sign)
        group_w = slot * 0.80
        k = len(enabled)
        bar_w = max(1.0, group_w / (k + 1.0))

        for i in range(n):
            cx = x_at(i)
            start = cx - group_w / 2
            for j, v in enumerate(enabled):
                val = daily_vals[v][i]
                bx0 = start + j * bar_w
                bx1 = bx0 + bar_w * 0.90

                yv = y_bot(val)
                if val >= 0:
                    y_top_bar, y_bot_bar = yv, mid_bot
                    fill = "#10B981"
                else:
                    y_top_bar, y_bot_bar = mid_bot, yv
                    fill = "#EF4444"

                c.create_rectangle(bx0, y_top_bar, bx1, y_bot_bar, outline="", fill=fill)

                self._bar_hits.append(
                    {
                        "x0": float(bx0),
                        "x1": float(bx1),
                        "y0": float(min(y_top_bar, y_bot_bar)),
                        "y1": float(max(y_top_bar, y_bot_bar)),
                        "date": days[i],
                        "var": v,
                        "value": float(val),
                        "cum": float(cum_vals[v][i]),
                    }
                )

        # X ticks
        step = max(1, n // 8)
        for i in range(0, n, step):
            c.create_text(
                x_at(i), h - pad_b + 8, text=days[i], fill="#6B7280", font=("TkDefaultFont", 8), anchor="n"
            )

        # Titles
        c.create_text(
            x0, y0_top - 2, text="Cumulative lines (daily cumsum)", anchor="nw",
            fill="#111827", font=("TkDefaultFont", 10, "bold")
        )
        c.create_text(
            x0, y0_bot - 2, text="Daily bars (green pos / red neg)", anchor="nw",
            fill="#111827", font=("TkDefaultFont", 10, "bold")
        )

        self.info_var.set(f"{len(days)} days | vars: {', '.join(enabled)}")

    # Hover tooltip
    def _on_motion(self, event) -> None:
        x, y = event.x, event.y
        hit = None
        for item in reversed(self._bar_hits):
            if item["x0"] <= x <= item["x1"] and item["y0"] <= y <= item["y1"]:
                hit = item
                break

        if hit is None:
            self._hide_tooltip()
            return

        date_s = str(hit["date"])
        var = str(hit["var"])
        val = float(hit["value"])
        cum = float(hit["cum"])

        txt = f"{date_s}\n{var}: {val:,.2f}\n{var} (cum): {cum:,.2f}"
        self._show_tooltip(event.x_root + 12, event.y_root + 12, txt)

    def _show_tooltip(self, x: int, y: int, text: str) -> None:
        self._hide_tooltip()
        tw = tk.Toplevel(self)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(tw, text=text, style="Tooltip.TLabel")
        label.pack(ipadx=8, ipady=6)
        self._tooltip = tw

    def _hide_tooltip(self) -> None:
        if self._tooltip is not None:
            try:
                self._tooltip.destroy()
            except Exception:
                pass
            self._tooltip = None