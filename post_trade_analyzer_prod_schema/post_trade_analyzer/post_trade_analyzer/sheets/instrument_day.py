from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import ttk

import pandas as pd

from ..utils.table_utils import build_display_cache
from ..utils.time_utils import parse_iso_date, us_open_berlin


# ============================================================
# Smart autocomplete combobox
#   - display: "UnderlyingName | inst1, inst2 ..."
#   - real value returned: underlyingName
#   - ranking: exact prefix > token match > contains
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


class BaseSheet(ttk.Frame):
    sheet_id: str = "base"
    sheet_title: str = "Base"

    def on_df_loaded(self, df: pd.DataFrame) -> None:
        pass


class InstrumentDaySheet(BaseSheet):
    """
    Clean version:
      - filter by UnderlyingName + date
      - no instrument filter
      - instrument shown as context next to underlying
      - Data tab simple + fast
      - Plot tab lightweight, no zoom drag
    """

    sheet_id = "instday"
    sheet_title = "DayZoom"

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._df_all: Optional[pd.DataFrame] = None
        self._df_base: Optional[pd.DataFrame] = None

        self.underlying_var = tk.StringVar()
        self.date_var = tk.StringVar()

        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(14, 10))
        ttk.Label(top, text="DayZoom", style="Title.TLabel").pack(side="left")

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=14, pady=(0, 10))

        ttk.Label(controls, text="UnderlyingName", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self.underlying_cb = SmartFilterCombobox(
            controls,
            textvariable=self.underlying_var,
            state="normal",
            width=42,
            max_results=30,
        )
        self.underlying_cb.grid(row=1, column=0, sticky="w", padx=(0, 14))

        ttk.Label(controls, text="Date (YYYY-MM-DD)", style="Muted.TLabel").grid(
            row=0, column=1, sticky="w", padx=(0, 8)
        )
        self.date_entry = ttk.Entry(controls, textvariable=self.date_var, width=12)
        self.date_entry.grid(row=1, column=1, sticky="w", padx=(0, 14))

        self.apply_btn = ttk.Button(controls, text="Apply", style="Accent.TButton", command=self._apply_base_filter)
        self.apply_btn.grid(row=1, column=2, sticky="w")

        self.clear_btn = ttk.Button(controls, text="Clear", command=self._clear_filters)
        self.clear_btn.grid(row=1, column=3, sticky="w", padx=(8, 0))

        self.info_var = tk.StringVar(value="Load data to begin.")
        ttk.Label(controls, textvariable=self.info_var, style="Muted.TLabel").grid(
            row=1, column=4, sticky="w", padx=(14, 0)
        )
        controls.columnconfigure(5, weight=1)

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        self.nb = ttk.Notebook(inner)
        self.nb.pack(fill="both", expand=True)

        self.sub_data = InstDayDataSubsheet(self.nb)
        self.sub_plot = InstDayPlotSubsheet(self.nb)

        self.nb.add(self.sub_data, text="Data")
        self.nb.add(self.sub_plot, text="Plot")

        self.date_entry.bind("<Return>", lambda e: self._apply_base_filter())

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

    def _default_date_from_df(self, df: pd.DataFrame) -> Optional[date]:
        if df is None or df.empty:
            return None

        if "date" in df.columns:
            s = pd.to_datetime(df["date"], errors="coerce").dropna()
            if not s.empty:
                return s.dt.date.max()

        if "tradeTime" in df.columns:
            s = pd.to_datetime(df["tradeTime"], errors="coerce").dropna()
            if not s.empty:
                return s.dt.date.max()

        return None

    def on_df_loaded(self, df: pd.DataFrame) -> None:
        self._df_all = df

        if df is None or df.empty:
            self.underlying_cb.set_pairs([])
            self.info_var.set("No data loaded.")
            self.sub_data.set_df(None)
            self.sub_plot.set_df(None)
            return

        self.underlying_cb.set_pairs(self._build_underlying_pairs(df))

        if not self.date_var.get():
            d0 = self._default_date_from_df(df)
            if d0 is not None:
                self.date_var.set(d0.isoformat())

        self._apply_base_filter()

    def _clear_filters(self) -> None:
        self.underlying_var.set("")
        self._apply_base_filter()

    def _apply_base_filter(self) -> None:
        df = self._df_all
        if df is None or df.empty:
            self.info_var.set("No data loaded.")
            self.sub_data.set_df(None)
            self.sub_plot.set_df(None)
            return

        u = self.underlying_cb.get_real_value()

        try:
            d = parse_iso_date(self.date_var.get())
        except ValueError:
            self.info_var.set("Invalid date format. Use YYYY-MM-DD.")
            return

        view = df
        if u:
            view = view[view["underlyingName"].astype(str) == u]

        if "date" in view.columns:
            view = view[view["date"] == d]
        else:
            view = view[pd.to_datetime(view["tradeTime"], errors="coerce").dt.date == d]

        view = view.sort_values("tradeTime", kind="mergesort").reset_index(drop=True)

        self._df_base = view
        inst_txt = self._instrument_info(view)
        tag_u = u if u else "(all)"
        self.info_var.set(
            f"UnderlyingName={tag_u} | Instrument={inst_txt} | Date={d.isoformat()} | Rows={len(view):,}"
        )

        self.sub_data.set_df(view)
        self.sub_plot.set_df(view, day=d)


# ============================================================
# Data subsheet
# ============================================================
class InstDayDataSubsheet(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._sort_col: Optional[str] = None
        self._sort_asc: bool = True

        self._df_base: Optional[pd.DataFrame] = None
        self._df_view: Optional[pd.DataFrame] = None

        self._cache: Dict[str, List[str]] = {}
        self._cache_len: int = 0

        self._build()

    def _build(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=10, pady=(10, 8))

        self.info_var = tk.StringVar(value="No data.")
        ttk.Label(controls, textvariable=self.info_var, style="Muted.TLabel").pack(side="right")

        tcard = ttk.Frame(self, style="Card.TFrame")
        tcard.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        inner = ttk.Frame(tcard, style="Card.TFrame")
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

    def set_df(self, df: Optional[pd.DataFrame]) -> None:
        self._df_base = df
        self._df_view = df
        self._sort_col = None
        self._sort_asc = True

        if df is None or df.empty:
            self.info_var.set("No rows.")
            self._clear_tree()
            self._cache.clear()
            self._cache_len = 0
            return

        self._cache, self._cache_len = build_display_cache(df)
        self.info_var.set(f"{len(df):,} rows")
        self._render_from_cache()

    def _render_from_cache(self) -> None:
        df = self._df_view
        if df is None or df.empty:
            self._clear_tree()
            return

        cols = list(df.columns)
        self._clear_tree()

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
        df = self._df_view
        if df is None or df.empty:
            return

        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        try:
            self._df_view = df.sort_values(by=col, ascending=self._sort_asc, kind="mergesort").reset_index(drop=True)
        except Exception:
            self._df_view = (
                df.assign(_tmp=df[col].astype(str))
                .sort_values(by="_tmp", ascending=self._sort_asc, kind="mergesort")
                .drop(columns="_tmp")
                .reset_index(drop=True)
            )

        self._cache, self._cache_len = build_display_cache(self._df_view)
        self._render_from_cache()

    def _clear_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = []


# ============================================================
# Plot subsheet
# ============================================================
class InstDayPlotSubsheet(ttk.Frame):
    PNL_CANDIDATES = [
        "Total",
        "PremiaCum",
        "PnLVonDeltaCum",
        "feesCum",
    ]

    DELTA_CANDIDATES = [
        "deltaCum",
        "delta",
    ]

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._df: Optional[pd.DataFrame] = None
        self._day: Optional[date] = None

        self._redraw_after_id: Optional[str] = None
        self._last_legend_items: List[Tuple[str, str, str]] = []

        self._pnl_series: List[str] = []
        self._delta_series: List[str] = []

        self._build()

    def _build(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=10, pady=10)

        self.left = ttk.Frame(root, style="Card.TFrame")
        self.left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        self.left.configure(width=320)
        self.left.grid_propagate(False)

        self.right = ttk.Frame(root, style="Card.TFrame")
        self.right.grid(row=0, column=1, sticky="nsew")
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        pad = ttk.Frame(self.left, style="Card.TFrame")
        pad.pack(fill="both", expand=True, padx=12, pady=12)

        pnl_header = ttk.Frame(pad, style="Card.TFrame")
        pnl_header.pack(fill="x")
        ttk.Label(pnl_header, text="PnL Lines", style="Muted.TLabel").pack(side="left")
        ttk.Button(pnl_header, text="All", width=6, command=lambda: self._select_all(self.pnl_lb)).pack(side="right")
        ttk.Button(pnl_header, text="None", width=6, command=lambda: self._select_none(self.pnl_lb)).pack(
            side="right", padx=(0, 6)
        )

        self.pnl_lb = tk.Listbox(pad, selectmode="extended", activestyle="none", exportselection=False, height=8)
        self.pnl_lb.pack(fill="x", pady=(6, 12))

        d_header = ttk.Frame(pad, style="Card.TFrame")
        d_header.pack(fill="x")
        ttk.Label(d_header, text="Delta Lines", style="Muted.TLabel").pack(side="left")
        ttk.Button(d_header, text="All", width=6, command=lambda: self._select_all(self.delta_lb)).pack(side="right")
        ttk.Button(d_header, text="None", width=6, command=lambda: self._select_none(self.delta_lb)).pack(
            side="right", padx=(0, 6)
        )

        self.delta_lb = tk.Listbox(pad, selectmode="extended", activestyle="none", exportselection=False, height=4)
        self.delta_lb.pack(fill="x", pady=(6, 12))

        btn_row = ttk.Frame(pad, style="Card.TFrame")
        btn_row.pack(fill="x", pady=(4, 10))

        self.redraw_btn = ttk.Button(btn_row, text="Redraw", style="Accent.TButton", command=self.redraw)
        self.redraw_btn.pack(side="left")

        ttk.Separator(pad, orient="horizontal").pack(fill="x", pady=(10, 10))
        ttk.Label(pad, text="Legend", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))

        self.legend = tk.Canvas(pad, highlightthickness=0, bg="#FFFFFF")
        self.legend.pack(fill="both", expand=True)

        self.right.rowconfigure(0, weight=2)
        self.right.rowconfigure(1, weight=5)
        self.right.columnconfigure(0, weight=1)

        spot_wrap = ttk.Frame(self.right, style="Card.TFrame")
        spot_wrap.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 8))
        self.canvas_spot = tk.Canvas(spot_wrap, highlightthickness=0, bg="#FFFFFF")
        self.canvas_spot.pack(fill="both", expand=True)

        main_wrap = ttk.Frame(self.right, style="Card.TFrame")
        main_wrap.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.canvas_main = tk.Canvas(main_wrap, highlightthickness=0, bg="#FFFFFF")
        self.canvas_main.pack(fill="both", expand=True)

        self.canvas_spot.bind("<Configure>", lambda e: self._schedule_redraw(250))
        self.canvas_main.bind("<Configure>", lambda e: self._schedule_redraw(250))
        self.legend.bind("<Configure>", lambda e: self._schedule_redraw(300))

    def _select_all(self, lb: tk.Listbox) -> None:
        lb.selection_set(0, "end")

    def _select_none(self, lb: tk.Listbox) -> None:
        lb.selection_clear(0, "end")

    def _schedule_redraw(self, delay_ms: int = 200) -> None:
        if self._redraw_after_id is not None:
            try:
                self.after_cancel(self._redraw_after_id)
            except Exception:
                pass
        self._redraw_after_id = self.after(delay_ms, self._do_redraw)

    def _do_redraw(self) -> None:
        self._redraw_after_id = None
        self.redraw()

    def set_df(self, df: Optional[pd.DataFrame], day: Optional[date] = None) -> None:
        self._df = df
        self._day = day

        self.pnl_lb.delete(0, "end")
        self.delta_lb.delete(0, "end")

        self._pnl_series = [c for c in self.PNL_CANDIDATES if df is not None and c in df.columns]
        self._delta_series = [c for c in self.DELTA_CANDIDATES if df is not None and c in df.columns]

        for s in self._pnl_series:
            self.pnl_lb.insert("end", s)
        for s in self._delta_series:
            self.delta_lb.insert("end", s)

        if self._pnl_series:
            self.pnl_lb.selection_set(0)
        if self._delta_series:
            self.delta_lb.selection_set(0)

        self.redraw()

    def redraw(self) -> None:
        self.canvas_spot.delete("all")
        self.canvas_main.delete("all")
        self.legend.delete("all")
        self._last_legend_items = []

        df = self._df
        day = self._day
        if df is None or df.empty or day is None:
            self._draw_empty(self.canvas_spot, "No data to plot.")
            self._draw_empty(self.canvas_main, "No data to plot.")
            return

        pnl_cols = [self._pnl_series[i] for i in self.pnl_lb.curselection() if i < len(self._pnl_series)]
        delta_cols = [self._delta_series[i] for i in self.delta_lb.curselection() if i < len(self._delta_series)]

        self._draw_spot_plot(df, day)

        if not pnl_cols and not delta_cols:
            self._draw_empty(self.canvas_main, "Select at least one line.")
            return

        legend_items = self._draw_main_plot(df, day, pnl_cols, delta_cols)
        self._last_legend_items = legend_items
        self._draw_legend_sidebar(legend_items)

    def _draw_empty(self, canvas: tk.Canvas, msg: str) -> None:
        w = max(300, canvas.winfo_width())
        h = max(200, canvas.winfo_height())
        canvas.create_text(w / 2, h / 2, text=msg, fill="#5E6B85", font=("Segoe UI", 11))

    def _draw_legend_sidebar(self, legend_items: List[Tuple[str, str, str]]) -> None:
        c = self.legend
        c.delete("all")
        w = max(260, c.winfo_width())
        h = max(160, c.winfo_height())

        if not legend_items:
            c.create_text(12, 18, text="(No lines)", anchor="w", fill="#5E6B85", font=("Segoe UI", 10))
            return

        box_h = min(h - 12, 16 + 20 * len(legend_items))
        c.create_rectangle(6, 6, w - 6, 6 + box_h, outline="#D8E1F0", fill="#FFFFFF")

        y = 18
        for col, label, grp in legend_items:
            c.create_line(16, y, 44, y, fill=col, width=3)
            c.create_text(54, y, text=f"{label} ({grp})", anchor="w", fill="#0B1220", font=("Segoe UI", 10))
            y += 20

    def _get_window(self, day: date) -> Tuple[pd.Timestamp, pd.Timestamp]:
        full_start = pd.Timestamp(f"{day.isoformat()} 08:00:00")
        full_end = pd.Timestamp(f"{day.isoformat()} 22:00:00")
        return full_start, full_end

    def _downsample(self, secs: List[float], vals: List[float], max_points: int = 1400) -> Tuple[List[float], List[float]]:
        n = len(secs)
        if n <= max_points:
            return secs, vals
        step = max(1, n // max_points)
        s2 = secs[::step]
        v2 = vals[::step]
        if s2[-1] != secs[-1]:
            s2.append(secs[-1])
            v2.append(vals[-1])
        return s2, v2

    def _draw_x_axis(self, c: tk.Canvas, day: date, start_dt: pd.Timestamp, end_dt: pd.Timestamp, x_map, y1: float) -> None:
        hours = ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00", "22:00"]
        for lab in hours:
            tmark = pd.Timestamp(f"{day.isoformat()} {lab}:00")
            if start_dt <= tmark <= end_dt:
                s = (tmark - start_dt).total_seconds()
                xx = x_map(s)
                c.create_line(xx, y1, xx, y1 + 6, fill="#D1E2FF", width=1)
                c.create_text(xx, y1 + 10, text=lab, fill="#5E6B85", font=("Segoe UI", 8), anchor="n")
        c.create_text((x_map(0) + x_map((end_dt - start_dt).total_seconds())) / 2, y1 + 28,
                      text="Time", fill="#5E6B85", font=("Segoe UI", 9), anchor="n")

    def _draw_spot_plot(self, df: pd.DataFrame, day: date) -> None:
        c = self.canvas_spot
        w = max(420, c.winfo_width())
        h = max(120, c.winfo_height())

        left, right, top, bottom = 70, 70, 22, 40
        x0, y0 = left, top
        x1, y1 = w - right, h - bottom

        start_dt, end_dt = self._get_window(day)
        total_sec = (end_dt - start_dt).total_seconds()
        if total_sec <= 0:
            self._draw_empty(c, "Bad window.")
            return

        if "tradeUnderlyingSpotRef" not in df.columns:
            self._draw_empty(c, "Missing tradeUnderlyingSpotRef.")
            return

        t = pd.to_datetime(df["tradeTime"], errors="coerce")
        mask = (t >= start_dt) & (t <= end_dt)
        sub = df.loc[mask, ["tradeTime", "tradeUnderlyingSpotRef"]].copy()
        if sub.empty:
            self._draw_empty(c, "No trades in window.")
            return

        sub.sort_values("tradeTime", inplace=True, kind="mergesort")
        secs = (pd.to_datetime(sub["tradeTime"]) - start_dt).dt.total_seconds().astype("float64").tolist()
        yvals = pd.to_numeric(sub["tradeUnderlyingSpotRef"], errors="coerce").astype("float64").tolist()

        secs, yvals = self._downsample(secs, yvals, max_points=1200)

        yclean = pd.Series(yvals).dropna()
        if yclean.empty:
            self._draw_empty(c, "No spot data.")
            return

        ymin, ymax = float(yclean.min()), float(yclean.max())
        if ymin == ymax:
            ymin -= 1.0
            ymax += 1.0
        pad = 0.06 * (ymax - ymin)
        ymin -= pad
        ymax += pad

        def x_map(s: float) -> float:
            return x0 + (s / total_sec) * (x1 - x0)

        def y_map(v: float) -> float:
            return y1 - ((v - ymin) / (ymax - ymin)) * (y1 - y0)

        for i in range(5):
            frac = i / 4
            yy = y1 - frac * (y1 - y0)
            v = ymin + frac * (ymax - ymin)
            c.create_text(x0 - 8, yy, text=f"{v:,.0f}", anchor="e", fill="#5E6B85", font=("Segoe UI", 9))

        c.create_rectangle(x0, y0, x1, y1, outline="#D8E1F0", width=1)

        for i in range(7):
            xx = x0 + i * (x1 - x0) / 6
            c.create_line(xx, y0, xx, y1, fill="#EEF3FF")
        for i in range(4):
            yy = y0 + i * (y1 - y0) / 3
            c.create_line(x0, yy, x1, yy, fill="#F3F6FF")

        self._draw_x_axis(c, day, start_dt, end_dt, x_map, y1)

        pts: List[float] = []
        for ss, vv in zip(secs, yvals):
            if vv is None or pd.isna(vv):
                continue
            pts.extend([x_map(float(ss)), y_map(float(vv))])
        if len(pts) >= 4:
            c.create_line(*pts, fill="#2E7BFF", width=2)

        c.create_text(x0, y0 - 10, text="Underlying Spot Ref", anchor="w", fill="#0B1220", font=("Segoe UI Semibold", 10))

    def _draw_main_plot(self, df: pd.DataFrame, day: date, pnl_cols: List[str], delta_cols: List[str]) -> List[Tuple[str, str, str]]:
        c = self.canvas_main
        w = max(520, c.winfo_width())
        h = max(280, c.winfo_height())

        left, right, top, bottom = 70, 70, 30, 50
        x0, y0 = left, top
        x1, y1 = w - right, h - bottom

        start_dt, end_dt = self._get_window(day)
        total_sec = (end_dt - start_dt).total_seconds()
        if total_sec <= 0:
            self._draw_empty(c, "Bad window.")
            return []

        t = pd.to_datetime(df["tradeTime"], errors="coerce")
        mask = (t >= start_dt) & (t <= end_dt)

        needed = ["tradeTime"] + list(dict.fromkeys(pnl_cols + delta_cols))
        cols = [col for col in needed if col in df.columns]
        sub = df.loc[mask, cols].copy()
        if sub.empty:
            self._draw_empty(c, "No trades in window.")
            return []

        sub.sort_values("tradeTime", inplace=True, kind="mergesort")
        secs = (pd.to_datetime(sub["tradeTime"]) - start_dt).dt.total_seconds().astype("float64").tolist()

        def max_abs_for(cols_: List[str]) -> float:
            if not cols_:
                return 1.0
            s_all = []
            for col in cols_:
                if col in sub.columns:
                    s = pd.to_numeric(sub[col], errors="coerce").astype("float64")
                    s_all.append(s)
            if not s_all:
                return 1.0
            s_cat = pd.concat(s_all, axis=0).dropna()
            if s_cat.empty:
                return 1.0
            m = float(s_cat.abs().max())
            return max(1.0, m * 1.08)

        pnl_maxabs = max_abs_for(pnl_cols)
        d_maxabs = max_abs_for(delta_cols)

        pnl_min, pnl_max = -pnl_maxabs, +pnl_maxabs
        d_min, d_max = -d_maxabs, +d_maxabs

        def x_map(s: float) -> float:
            return x0 + (s / total_sec) * (x1 - x0)

        def y_map_left(v: float) -> float:
            return y1 - ((v - pnl_min) / (pnl_max - pnl_min)) * (y1 - y0)

        def y_map_right(v: float) -> float:
            return y1 - ((v - d_min) / (d_max - d_min)) * (y1 - y0)

        c.create_rectangle(x0, y0, x1, y1, outline="#D8E1F0", width=1)

        for i in range(11):
            xx = x0 + i * (x1 - x0) / 10
            c.create_line(xx, y0, xx, y1, fill="#EEF3FF")
        for i in range(5):
            yy = y0 + i * (y1 - y0) / 4
            c.create_line(x0, yy, x1, yy, fill="#F3F6FF")

        y_zero = y_map_left(0.0)
        c.create_line(x0, y_zero, x1, y_zero, fill="#B8C7E6", width=2)

        for i in range(5):
            frac = i / 4
            yy = y1 - frac * (y1 - y0)
            vL = pnl_min + frac * (pnl_max - pnl_min)
            vR = d_min + frac * (d_max - d_min)
            c.create_text(x0 - 8, yy, text=f"{vL:,.0f}", anchor="e", fill="#5E6B85", font=("Segoe UI", 9))
            c.create_text(x1 + 8, yy, text=f"{vR:,.4f}", anchor="w", fill="#5E6B85", font=("Segoe UI", 9))

        full_day = day
        t1 = pd.Timestamp(f"{full_day.isoformat()} 09:00:00")
        uo = us_open_berlin(full_day)
        t2 = pd.Timestamp(f"{full_day.isoformat()} {uo.strftime('%H:%M:%S')}")
        for tmark, label in [(t1, "09:00"), (t2, f"US open {uo.strftime('%H:%M')}")]:
            if start_dt <= tmark <= end_dt:
                s = (tmark - start_dt).total_seconds()
                xx = x_map(s)
                c.create_line(xx, y0, xx, y1, fill="#D1E2FF", width=2)
                c.create_text(xx, y0 - 6, text=label, fill="#2667D6", font=("Segoe UI Semibold", 9), anchor="s")

        self._draw_x_axis(c, day, start_dt, end_dt, x_map, y1)

        c.create_text(x0, y0 - 14, text="PnL", anchor="w", fill="#0B1220", font=("Segoe UI Semibold", 10))
        c.create_text(x1, y0 - 14, text="Δ (right)", anchor="e", fill="#0B1220", font=("Segoe UI Semibold", 10))

        palette = ["#2E7BFF", "#00B6D6", "#7C3AED", "#16A34A", "#F97316", "#EF4444", "#0EA5E9", "#A855F7"]
        legend_items: List[Tuple[str, str, str]] = []

        k0 = 0
        for colname in pnl_cols:
            if colname not in sub.columns:
                continue
            color = palette[k0 % len(palette)]
            k0 += 1
            svals = pd.to_numeric(sub[colname], errors="coerce").fillna(0.0).astype("float64").tolist()
            secs2, svals2 = self._downsample(secs, svals, max_points=1400)

            pts: List[float] = []
            for ss, vv in zip(secs2, svals2):
                pts.extend([x_map(float(ss)), y_map_left(float(vv))])
            if len(pts) >= 4:
                c.create_line(*pts, fill=color, width=2)
                legend_items.append((color, colname, "PnL"))

        for colname in delta_cols:
            if colname not in sub.columns:
                continue
            color = palette[k0 % len(palette)]
            k0 += 1
            svals = pd.to_numeric(sub[colname], errors="coerce").fillna(0.0).astype("float64").tolist()
            secs2, svals2 = self._downsample(secs, svals, max_points=1400)

            pts: List[float] = []
            for ss, vv in zip(secs2, svals2):
                pts.extend([x_map(float(ss)), y_map_right(float(vv))])
            if len(pts) >= 4:
                c.create_line(*pts, fill=color, width=2)
                legend_items.append((color, colname, "Δ"))

        return legend_items