from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import ttk

import numpy as np
import pandas as pd

from ..utils.table_utils import build_display_cache


# ============================================================
# Smart autocomplete combobox
#   - display: "UnderlyingName | inst1, inst2 ..."
#   - real value returned: underlyingName
#   - ranking: exact prefix > token match > contains
#   - bounded result count for performance
# ============================================================
class SmartFilterCombobox(ttk.Combobox):
    SEP = " | "

    def __init__(self, master, *, max_results: int = 25, **kwargs):
        super().__init__(master, **kwargs)
        self._max_results = max_results
        self._pairs: List[Tuple[str, str]] = []
        self._display_to_real: Dict[str, str] = {}
        self._all_displays: List[str] = []
        self._is_updating = False

        self.bind("<KeyRelease>", self._on_keyrelease)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<<ComboboxSelected>>", self._on_selected)
        self.bind("<Button-1>", self._on_click)

    def set_pairs(self, pairs: Sequence[Tuple[str, str]]) -> None:
        clean_pairs: List[Tuple[str, str]] = []
        seen_display = set()

        for display, real in pairs:
            d = str(display).strip()
            r = str(real).strip()
            if not d or not r or d in seen_display:
                continue
            clean_pairs.append((d, r))
            seen_display.add(d)

        self._pairs = clean_pairs
        self._display_to_real = {d: r for d, r in clean_pairs}
        self._all_displays = [d for d, _ in clean_pairs]
        self["values"] = self._all_displays[: self._max_results]

    def get_real_value(self) -> str:
        raw = self.get().strip()
        if not raw:
            return ""
        if raw in self._display_to_real:
            return self._display_to_real[raw]
        if self.SEP in raw:
            return raw.split(self.SEP, 1)[0].strip()
        return raw

    def _filtered_displays(self, text: str) -> List[str]:
        t = (text or "").strip().lower()
        if not t:
            return self._all_displays[: self._max_results]

        starts = []
        contains = []

        for d in self._all_displays:
            dl = d.lower()
            if dl.startswith(t):
                starts.append(d)
            elif t in dl:
                contains.append(d)

        out = starts + contains
        return out[: self._max_results] if out else self._all_displays[: self._max_results]

    def _on_keyrelease(self, event) -> None:
        if self._is_updating:
            return

        if event.keysym in ("Up", "Down", "Left", "Right", "Return", "Escape", "Tab"):
            return

        current_text = self.get()
        cursor_pos = self.index(tk.INSERT)
        vals = self._filtered_displays(current_text)

        self._is_updating = True
        try:
            self["values"] = vals
            self.delete(0, tk.END)
            self.insert(0, current_text)
            try:
                self.icursor(cursor_pos)
            except Exception:
                pass
        finally:
            self._is_updating = False

    def _on_focus_out(self, event) -> None:
        self["values"] = self._all_displays[: self._max_results]

    def _on_selected(self, event) -> None:
        self["values"] = self._all_displays[: self._max_results]

    def _on_click(self, event) -> None:
        self["values"] = self._filtered_displays(self.get())

# ============================================================
# EndOfDay Sheet
# ============================================================
@dataclass(frozen=True)
class EODSelection:
    underlying: str = ""


class EndOfDaySheet(ttk.Frame):
    sheet_id = "eod"
    sheet_title = "EndOfDay"

    HIST_METRICS = ["feesCum", "PnLVonDeltaCum", "PremiaCum", "Total"]

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._trades: Optional[pd.DataFrame] = None
        self._eod: Optional[pd.DataFrame] = None
        self._sel = EODSelection()

        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(14, 10))
        ttk.Label(top, text="EndOfDay", style="Title.TLabel").pack(side="left")

        search = ttk.Frame(self)
        search.pack(fill="x", padx=14, pady=(0, 10))

        ttk.Label(search, text="UnderlyingName", style="Muted.TLabel").grid(row=0, column=0, sticky="w")

        self.underlying_var = tk.StringVar()
        self.underlying_cb = SmartFilterCombobox(
            search,
            textvariable=self.underlying_var,
            state="normal",
            width=42,
            max_results=30,
        )
        self.underlying_cb.grid(row=1, column=0, sticky="w")

        ttk.Button(search, text="Apply", style="Accent.TButton", command=self._apply_selection).grid(
            row=1, column=1, padx=(14, 0)
        )
        ttk.Button(search, text="Clear", command=self._clear_selection).grid(
            row=1, column=2, padx=(8, 0)
        )

        self.sel_info = tk.StringVar(value="Selected: UnderlyingName=(all) | Instrument=-")
        ttk.Label(search, textvariable=self.sel_info, style="Muted.TLabel").grid(
            row=1, column=3, sticky="w", padx=(14, 0)
        )

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        self.nb = ttk.Notebook(inner)
        self.nb.pack(fill="both", expand=True)

        self.tab_data = EODDataTab(self.nb)
        self.tab_plot = EODPlotTab(self.nb, hist_metrics=self.HIST_METRICS)

        self.nb.add(self.tab_data, text="Data")
        self.nb.add(self.tab_plot, text="Plot")

    # -------------------------
    # API called by app
    # -------------------------
    def on_df_loaded(self, trades: pd.DataFrame) -> None:
        self._trades = trades
        self._rebuild_eod_if_possible()

    # -------------------------
    # Build EOD core df
    # -------------------------
    def _rebuild_eod_if_possible(self) -> None:
        if self._trades is None:
            return

        self._eod = self._build_eod_last_trade_per_day_underlying(self._trades)

        if self._eod is not None and not self._eod.empty:
            pairs = self._build_underlying_pairs(self._eod)
        else:
            pairs = []

        self.underlying_cb.set_pairs(pairs)
        self._push_filtered()

    @staticmethod
    def _build_eod_last_trade_per_day_underlying(df: pd.DataFrame) -> pd.DataFrame:
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

    @staticmethod
    def _summarize_instruments(inst_values: Sequence[str], max_items: int = 2) -> str:
        vals = [str(v).strip() for v in inst_values if str(v).strip()]
        vals = sorted(dict.fromkeys(vals))
        if not vals:
            return "-"
        if len(vals) <= max_items:
            return ", ".join(vals)
        return ", ".join(vals[:max_items]) + f" ... (+{len(vals) - max_items})"

    def _build_underlying_pairs(self, df: pd.DataFrame) -> List[Tuple[str, str]]:
        if df is None or df.empty or "underlyingName" not in df.columns:
            return []

        out: List[Tuple[str, str]] = []
        if "instrument" in df.columns:
            grouped = (
                df.groupby("underlyingName", sort=True)["instrument"]
                .agg(lambda s: self._summarize_instruments(s.tolist()))
            )
            for u, inst_txt in grouped.items():
                u_txt = str(u).strip()
                if u_txt:
                    out.append((f"{u_txt} | {inst_txt}", u_txt))
        else:
            vals = sorted(df["underlyingName"].dropna().astype(str).unique().tolist())
            out = [(u, u) for u in vals if u]

        return out

    def _instrument_info(self, df: pd.DataFrame) -> str:
        if df is None or df.empty or "instrument" not in df.columns:
            return "-"
        return self._summarize_instruments(df["instrument"].dropna().astype(str).tolist(), max_items=3)

    # -------------------------
    # Selection / filtering
    # -------------------------
    def _apply_selection(self) -> None:
        u = self.underlying_cb.get_real_value()
        self._sel = EODSelection(underlying=u)
        self._push_filtered()

    def _clear_selection(self) -> None:
        self.underlying_var.set("")
        self._sel = EODSelection()
        self._push_filtered()

    def _push_filtered(self) -> None:
        eod = self._eod
        if eod is None or eod.empty:
            self.sel_info.set("Selected: UnderlyingName=(all) | Instrument=- — no data")
            self.tab_data.set_df(pd.DataFrame())
            self.tab_plot.set_data(pd.DataFrame())
            return

        df = eod
        if self._sel.underlying:
            df = df[df["underlyingName"].astype(str) == self._sel.underlying]

        df = df.reset_index(drop=True)

        inst_txt = self._instrument_info(df)
        if self._sel.underlying:
            self.sel_info.set(f"Selected: UnderlyingName={self._sel.underlying} | Instrument={inst_txt}")
        else:
            self.sel_info.set(f"Selected: UnderlyingName=(all) | Instrument={inst_txt}")

        self.tab_data.set_df(df)
        self.tab_plot.set_data(df)


# ============================================================
# Data tab
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
# Plot tab
#   - top: true EOD cumulative levels aggregated by date
#   - bottom: daily differences of those EOD cumulative levels
# ============================================================
class EODPlotTab(ttk.Frame):
    COLOR_MAP = {
        "PremiaCum": "#4A6CF7",
        "PnLVonDeltaCum": "#111827",
        "feesCum": "#F97316",
        "Total": "#7C3AED",
    }

    def __init__(self, master: tk.Misc, hist_metrics: List[str]) -> None:
        super().__init__(master)

        self._eod: pd.DataFrame = pd.DataFrame()

        self._vars = [v for v in ["feesCum", "PnLVonDeltaCum", "PremiaCum", "Total"] if v in hist_metrics]
        if not self._vars:
            self._vars = hist_metrics[:]

        self._var_enabled: Dict[str, tk.BooleanVar] = {v: tk.BooleanVar(value=True) for v in self._vars}
        self._daily: pd.DataFrame = pd.DataFrame()

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

    def set_data(self, eod_filtered: pd.DataFrame) -> None:
        self._eod = eod_filtered if eod_filtered is not None else pd.DataFrame()
        self._daily = self._build_daily_frame()
        self.redraw()

    def _enabled_vars(self) -> List[str]:
        out = [v for v in self._vars if self._var_enabled[v].get()]
        return out if out else ([self._vars[0]] if self._vars else [])

    def _build_daily_frame(self) -> pd.DataFrame:
        eod = self._eod
        if eod is None or eod.empty:
            return pd.DataFrame()

        need = ["date"] + [v for v in self._vars if v in eod.columns]
        if "date" not in eod.columns or len(need) <= 1:
            return pd.DataFrame()

        work = eod[need].copy()
        for v in self._vars:
            if v in work.columns:
                work[v] = pd.to_numeric(work[v], errors="coerce").fillna(0.0)

        # If several underlyings are present, aggregate by date.
        out = work.groupby("date", sort=True, as_index=False).sum(numeric_only=True)
        out = out.sort_values("date", kind="mergesort").reset_index(drop=True)

        for v in self._vars:
            if v not in out.columns:
                out[v] = 0.0
            out[f"{v}Daily"] = out[v].diff().fillna(out[v])

        return out

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
        if not enabled:
            self.info_var.set("No metric selected.")
            return

        max_days = 240
        if len(df) > max_days:
            pick = np.linspace(0, len(df) - 1, num=max_days, dtype=int)
            pick = pd.unique(pick).tolist()
            df = df.iloc[pick].reset_index(drop=True)

        days = df["date"].astype(str).tolist()
        n = len(days)

        level_vals: Dict[str, List[float]] = {}
        daily_vals: Dict[str, List[float]] = {}
        for v in enabled:
            level_vals[v] = pd.to_numeric(df.get(v, 0.0), errors="coerce").fillna(0.0).astype(float).tolist()
            daily_vals[v] = pd.to_numeric(df.get(f"{v}Daily", 0.0), errors="coerce").fillna(0.0).astype(float).tolist()

        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())

        all_levels = [x for k in enabled for x in level_vals[k]]
        all_daily = [x for k in enabled for x in daily_vals[k]]

        vmax = max(1e-9, max(abs(v) for v in all_levels)) if all_levels else 1.0
        vmaxb = max(1e-9, max(abs(v) for v in all_daily)) if all_daily else 1.0

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

        def nice_step(v: float) -> float:
            if v <= 0:
                return 1.0
            exp = math.floor(math.log10(v))
            f = v / (10 ** exp)
            if f <= 1:
                nf = 1
            elif f <= 2:
                nf = 2
            elif f <= 5:
                nf = 5
            else:
                nf = 10
            return nf * (10 ** exp)

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
                    x_axis - 8, y, text=f"{t:,.0f}", anchor="e", fill="#6B7280", font=("TkDefaultFont", 8)
                )

        draw_y_axis(x0, y0_top, y1_top, vmax, y_top)
        draw_y_axis(x0, y0_bot, y1_bot, vmaxb, y_bot)

        c.create_line(x0, mid_top, x1, mid_top, fill="#CBD5E1", width=2)
        c.create_line(x0, mid_bot, x1, mid_bot, fill="#CBD5E1", width=2)

        # Top cumulative levels
        for v in enabled:
            pts: List[float] = []
            series = level_vals[v]
            for i in range(n):
                pts.extend([x_at(i), y_top(series[i])])
            if len(pts) >= 4:
                c.create_line(*pts, fill=self.COLOR_MAP.get(v, "#111827"), width=2)

        # Right-side final values
        y_text = y0_top + 10
        c.create_text(x1 - 6, y0_top - 2, text="Final (EOD)", anchor="ne", fill="#6B7280", font=("TkDefaultFont", 9))
        for v in enabled:
            final = level_vals[v][-1] if level_vals[v] else 0.0
            c.create_text(
                x1 - 6,
                y_text,
                text=f"{v}: {final:,.2f}",
                anchor="ne",
                fill=self.COLOR_MAP.get(v, "#111827"),
                font=("TkDefaultFont", 9, "bold"),
            )
            y_text += 16

        # Bottom daily bars
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
                        "level": float(level_vals[v][i]),
                    }
                )

        step = max(1, n // 8)
        for i in range(0, n, step):
            c.create_text(x_at(i), h - pad_b + 8, text=days[i], fill="#6B7280", font=("TkDefaultFont", 8), anchor="n")

        c.create_text(
            x0, y0_top - 2, text="EOD cumulative levels", anchor="nw",
            fill="#111827", font=("TkDefaultFont", 10, "bold")
        )
        c.create_text(
            x0, y0_bot - 2, text="Daily changes from EOD levels", anchor="nw",
            fill="#111827", font=("TkDefaultFont", 10, "bold")
        )

        self.info_var.set(f"{len(days)} days | vars: {', '.join(enabled)}")

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
        level = float(hit["level"])

        txt = f"{date_s}\n{var} daily: {val:,.2f}\n{var} EOD: {level:,.2f}"
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