from __future__ import annotations

import json
import os
from datetime import date
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import pandas as pd

from ..utils.table_utils import build_display_cache, sanitize_visible_cols
from ..utils.time_utils import parse_iso_date


# ------------------------------------------------------------
# Report Sheet
# ------------------------------------------------------------

class ReportSheet(ttk.Frame):
    sheet_id = "report"
    sheet_title = "Report"

    DEFAULT_METRICS = [
        "Total",
        "PremiaCum",
        "SpreadsCapture",
        "FullSpreadCapture",
        "PnlVonDeltaCum",
        "feesCum",
        "AufgeldCum",
    ]

    DEFAULT_FIELDS = [
        "instrument",
        "day",
        "portfolio",
        "counterparty",
        "underlying",
        "tradeUnderlyingSpotRef",
        "tradeNr",
        "tradeTime",
    ]

    PRESETS_DIR = "presets"  # relative to cwd

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._df_all: Optional[pd.DataFrame] = None
        self._df_eod: Optional[pd.DataFrame] = None
        self._df_range: Optional[pd.DataFrame] = None
        self._df_report: Optional[pd.DataFrame] = None

        self.from_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.n_var = tk.IntVar(value=5)

        self.mode_var = tk.StringVar(value="Value")  # "Value" | "Abs(Value)"
        self.include_top_var = tk.BooleanVar(value=True)
        self.include_bottom_var = tk.BooleanVar(value=True)

        self._build()

    def _build(self) -> None:
        # Title
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(14, 10))
        ttk.Label(top, text="Report", style="Title.TLabel").pack(side="left")

        # Controls card
        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="x", padx=14, pady=(0, 10))

        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="x", padx=12, pady=12)

        # Row 0 - dates, N, ranking
        r0 = ttk.Frame(inner)
        r0.pack(fill="x")

        ttk.Label(r0, text="From (YYYY-MM-DD)", style="Muted.TLabel").pack(side="left")
        self.from_entry = ttk.Entry(r0, textvariable=self.from_var, width=12)
        self.from_entry.pack(side="left", padx=(8, 14))

        ttk.Label(r0, text="To (YYYY-MM-DD)", style="Muted.TLabel").pack(side="left")
        self.to_entry = ttk.Entry(r0, textvariable=self.to_var, width=12)
        self.to_entry.pack(side="left", padx=(8, 14))

        ttk.Label(r0, text="N", style="Muted.TLabel").pack(side="left")
        self.n_spin = ttk.Spinbox(r0, from_=1, to=50000, textvariable=self.n_var, width=7)
        self.n_spin.pack(side="left", padx=(8, 14))

        ttk.Label(r0, text="Ranking", style="Muted.TLabel").pack(side="left")
        self.mode_cb = ttk.Combobox(r0, textvariable=self.mode_var, state="readonly", width=12)
        self.mode_cb["values"] = ["Value", "Abs(Value)"]
        self.mode_cb.pack(side="left", padx=(8, 14))

        ttk.Checkbutton(r0, text="Top", variable=self.include_top_var).pack(side="left")
        ttk.Checkbutton(r0, text="Bottom", variable=self.include_bottom_var).pack(side="left", padx=(8, 0))

        self.apply_btn = ttk.Button(r0, text="Apply", style="Accent.TButton", command=self._apply_report)
        self.apply_btn.pack(side="right")

        # Row 1 - selectors (metrics + fields)
        r1 = ttk.Frame(inner)
        r1.pack(fill="x", pady=(12, 0))

        mbox = ttk.Frame(r1, style="Card.TFrame")
        mbox.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Label(mbox, text="Metrics (multi-select)", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))
        self.metrics_lb = tk.Listbox(
            mbox, selectmode="extended", activestyle="none", exportselection=False, height=7
        )
        self.metrics_lb.pack(fill="x", expand=True)

        fbox = ttk.Frame(r1, style="Card.TFrame")
        fbox.pack(side="left", fill="x", expand=True)
        ttk.Label(fbox, text="Fields to show (multi-select)", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))
        self.fields_lb = tk.Listbox(
            fbox, selectmode="extended", activestyle="none", exportselection=False, height=7
        )
        self.fields_lb.pack(fill="x", expand=True)

        # Row 2 - buttons
        r2 = ttk.Frame(inner)
        r2.pack(fill="x", pady=(12, 0))

        ttk.Button(r2, text="Metrics: all", command=lambda: self._lb_select_all(self.metrics_lb)).pack(side="left")
        ttk.Button(r2, text="Metrics: none", command=lambda: self._lb_select_none(self.metrics_lb)).pack(side="left", padx=6)

        ttk.Button(r2, text="Fields: all", command=lambda: self._lb_select_all(self.fields_lb)).pack(side="left", padx=(14, 0))
        ttk.Button(r2, text="Fields: none", command=lambda: self._lb_select_none(self.fields_lb)).pack(side="left", padx=6)

        ttk.Button(r2, text="Save preset", command=self._save_preset).pack(side="left", padx=(14, 0))
        ttk.Button(r2, text="Load preset", command=self._load_preset).pack(side="left", padx=6)
        ttk.Button(r2, text="Reset", command=self._reset_controls).pack(side="left", padx=6)

        ttk.Button(r2, text="Create HTML", command=self._create_html).pack(side="right")

        # Info + summary
        self.info_var = tk.StringVar(value="Load data to begin.")
        ttk.Label(inner, textvariable=self.info_var, style="Muted.TLabel").pack(anchor="w", pady=(10, 0))

        self.summary_text = tk.Text(inner, height=3, wrap="word", relief="flat", bg="#FFFFFF")
        self.summary_text.pack(fill="x", pady=(8, 0))
        self.summary_text.configure(state="disabled")

        # Data table
        self.data = ReportDataTable(self)
        self.data.pack(fill="both", expand=True, padx=14, pady=(10, 14))

        # Key binds
        self.from_entry.bind("<Return>", lambda e: self._apply_report())
        self.to_entry.bind("<Return>", lambda e: self._apply_report())

    @staticmethod
    def _lb_select_all(lb: tk.Listbox) -> None:
        lb.selection_set(0, "end")

    @staticmethod
    def _lb_select_none(lb: tk.Listbox) -> None:
        lb.selection_clear(0, "end")

    def _set_summary(self, lines: List[str]) -> None:
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        if lines:
            self.summary_text.insert("1.0", "\n".join(lines[:3]))
        self.summary_text.configure(state="disabled")

    # ----------------------------
    # Data load
    # ----------------------------

    def on_df_loaded(self, df: pd.DataFrame) -> None:
        self._df_all = df
        self._df_eod = self._build_eod_df(df)

        if self._df_eod is None or self._df_eod.empty:
            self.info_var.set("No data available.")
            self._set_summary([])
            self.data.set_df(None)
            return

        # default dates
        dmin = self._df_eod["day"].min()
        dmax = self._df_eod["day"].max()
        if isinstance(dmin, date) and not self.from_var.get():
            self.from_var.set(dmin.isoformat())
        if isinstance(dmax, date) and not self.to_var.get():
            self.to_var.set(dmax.isoformat())

        # metrics list
        self.metrics_lb.delete(0, "end")
        existing = set(self._df_eod.columns)

        metric_cols = [c for c in self.DEFAULT_METRICS if c in existing]
        if not metric_cols:
            metric_cols = [
                c for c in self._df_eod.columns
                if pd.api.types.is_numeric_dtype(self._df_eod[c]) and c not in ("tradeNr",)
            ][:16]

        for c in metric_cols:
            self.metrics_lb.insert("end", c)

        if metric_cols:
            try:
                idx = metric_cols.index("Total")
            except ValueError:
                idx = 0
            self.metrics_lb.selection_set(idx)

        # fields list
        self.fields_lb.delete(0, "end")
        fields = []
        for c in self.DEFAULT_FIELDS:
            if c in existing and c not in fields:
                fields.append(c)

        for c in self._df_eod.columns:
            if c in fields or c in metric_cols or c.startswith("flag_"):
                continue
            fields.append(c)
            if len(fields) >= 24:
                break

        for c in fields:
            self.fields_lb.insert("end", c)

        for i, c in enumerate(fields):
            if c in ("instrument", "day", "portfolio", "counterparty", "underlying"):
                self.fields_lb.selection_set(i)

        self._apply_report()

    @staticmethod
    def _build_eod_df(df: pd.DataFrame) -> Optional[pd.DataFrame]:
        if df is None or df.empty:
            return None
        if "instrument" not in df.columns or "tradeTime" not in df.columns:
            return None

        tmp = df.copy()
        tmp["_day"] = tmp["tradeTime"].dt.date
        tmp.sort_values(["instrument", "_day", "tradeTime"], inplace=True, kind="mergesort")
        eod = tmp.groupby(["instrument", "_day"], sort=False, as_index=False).tail(1).copy()
        eod.rename(columns={"_day": "day"}, inplace=True)
        eod.reset_index(drop=True, inplace=True)
        return eod

    # ----------------------------
    # Apply report
    # ----------------------------

    def _apply_report(self) -> None:
        if self._df_eod is None or self._df_eod.empty:
            self.info_var.set("No data loaded.")
            self._set_summary([])
            self.data.set_df(None)
            return

        try:
            d_from = parse_iso_date(self.from_var.get().strip())
            d_to = parse_iso_date(self.to_var.get().strip())
        except ValueError:
            self.info_var.set("Invalid date. Use YYYY-MM-DD.")
            self._set_summary([])
            return

        if d_to < d_from:
            d_from, d_to = d_to, d_from
            self.from_var.set(d_from.isoformat())
            self.to_var.set(d_to.isoformat())

        n = int(self.n_var.get())
        n = max(1, min(50000, n))

        metric_cols = self._selected_from_listbox(self.metrics_lb)
        field_cols = self._selected_from_listbox(self.fields_lb)

        if not metric_cols:
            self.info_var.set("Select at least 1 metric.")
            self._set_summary([])
            return

        if not (self.include_top_var.get() or self.include_bottom_var.get()):
            self.info_var.set("Select Top and/or Bottom.")
            self._set_summary([])
            return

        base = self._df_eod
        mask = (base["day"] >= d_from) & (base["day"] <= d_to)
        rng = base.loc[mask].copy()
        self._df_range = rng

        report = self._build_report_table(
            rng,
            metric_cols,
            field_cols,
            n,
            self.mode_var.get(),
            include_top=self.include_top_var.get(),
            include_bottom=self.include_bottom_var.get(),
        )

        self._df_report = report
        self.data.set_df(report)

        self.info_var.set(
            f"EOD rows: {len(rng):,} • Metrics: {len(metric_cols)} • N={n} • Mode={self.mode_var.get()} • "
            f"Top={self.include_top_var.get()} Bottom={self.include_bottom_var.get()}"
        )

        self._set_summary(self._make_summary_lines(rng, metric_cols))

    @staticmethod
    def _selected_from_listbox(lb: tk.Listbox) -> List[str]:
        return [lb.get(i) for i in lb.curselection()]

    @staticmethod
    def _make_summary_lines(rng: pd.DataFrame, metrics: List[str]) -> List[str]:
        if rng is None or rng.empty:
            return ["No rows in range."]

        inst_n = rng["instrument"].nunique() if "instrument" in rng.columns else len(rng)
        day_n = rng["day"].nunique() if "day" in rng.columns else len(rng)
        lines = [f"Universe: instruments={inst_n:,} • days={day_n:,} • rows={len(rng):,}"]

        for m in metrics[:3]:
            if m not in rng.columns:
                continue
            s = pd.to_numeric(rng[m], errors="coerce").fillna(0.0)
            lines.append(
                f"{m}: Σ={s.sum():,.0f} | μ={s.mean():,.0f} | min={s.min():,.0f} | max={s.max():,.0f} | "
                f"+{int((s>0).sum())}/-{int((s<0).sum())}"
            )
        if len(metrics) > 3:
            lines.append("… (summary shows first 3 metrics)")
        return lines

    # ----------------------------
    # Report table build (with TOTAL rows)
    # ----------------------------

    @staticmethod
    def _build_report_table(
        df_eod: pd.DataFrame,
        metrics: List[str],
        fields: List[str],
        n: int,
        mode: str,
        include_top: bool,
        include_bottom: bool,
    ) -> pd.DataFrame:
        if df_eod is None or df_eod.empty:
            return pd.DataFrame()

        fields = [c for c in fields if c in df_eod.columns]
        for must in ("instrument", "day"):
            if must in df_eod.columns and must not in fields:
                fields.insert(0, must)

        def add_total_row(block: pd.DataFrame, metric_name: str, rank_type: str) -> pd.DataFrame:
            total = float(pd.to_numeric(block["_metric_value"], errors="coerce").fillna(0.0).sum())

            # IMPORTANT: use pd.NA (NOT "") to avoid table_utils int('') crashes
            row = {c: pd.NA for c in block.columns}
            row["_metric_value"] = total
            row["metric"] = metric_name
            row["rank_type"] = rank_type
            row["rank"] = "TOTAL"
            return pd.concat([block, pd.DataFrame([row])], ignore_index=True)

        rows: List[pd.DataFrame] = []
        for m in metrics:
            if m not in df_eod.columns:
                continue

            s = pd.to_numeric(df_eod[m], errors="coerce").fillna(0.0)
            work = df_eod.copy()
            work["_metric_value"] = s

            if mode == "Abs(Value)":
                work["_rank_key"] = work["_metric_value"].abs()
            else:
                work["_rank_key"] = work["_metric_value"]

            if include_top:
                top = work.nlargest(n, "_rank_key").copy()
                top["metric"] = m
                top["rank_type"] = "Top"
                top["rank"] = range(1, len(top) + 1)
                top = add_total_row(top, m, "Top")
                rows.append(top)

            if include_bottom:
                bot = work.nsmallest(n, "_rank_key").copy()
                bot["metric"] = m
                bot["rank_type"] = "Bottom"
                bot["rank"] = range(1, len(bot) + 1)
                bot = add_total_row(bot, m, "Bottom")
                rows.append(bot)

        if not rows:
            return pd.DataFrame()

        out = pd.concat(rows, axis=0, ignore_index=True)

        cols = ["metric", "rank_type", "rank", "_metric_value"] + fields
        cols = [c for c in cols if c in out.columns]
        out = out[cols].rename(columns={"_metric_value": "metric_value"})

        def sign_icon(v: float, is_total: bool) -> str:
            if is_total:
                return "Σ"
            return "🟢" if v >= 0 else "🔴"

        out.insert(
            0,
            "sign",
            [
                sign_icon(float(v), str(r) == "TOTAL")
                for v, r in zip(out["metric_value"].astype("float64"), out["rank"])
            ],
        )

        # Keep blocks together
        out.sort_values(["metric", "rank_type"], inplace=True, kind="mergesort")
        out.reset_index(drop=True, inplace=True)
        return out

    # ----------------------------
    # Presets
    # ----------------------------

    def _get_current_preset(self) -> Dict:
        metrics = self._selected_from_listbox(self.metrics_lb)
        fields = self._selected_from_listbox(self.fields_lb)
        return {
            "from": self.from_var.get().strip(),
            "to": self.to_var.get().strip(),
            "n": int(self.n_var.get()),
            "mode": self.mode_var.get(),
            "include_top": bool(self.include_top_var.get()),
            "include_bottom": bool(self.include_bottom_var.get()),
            "metrics": metrics,
            "fields": fields,
        }

    def _apply_preset(self, preset: Dict) -> None:
        if preset.get("from"):
            self.from_var.set(preset["from"])
        if preset.get("to"):
            self.to_var.set(preset["to"])
        if "n" in preset:
            self.n_var.set(int(preset["n"]))
        if preset.get("mode") in ("Value", "Abs(Value)"):
            self.mode_var.set(preset["mode"])

        self.include_top_var.set(bool(preset.get("include_top", True)))
        self.include_bottom_var.set(bool(preset.get("include_bottom", True)))

        self._select_listbox_values(self.metrics_lb, preset.get("metrics", []))
        self._select_listbox_values(self.fields_lb, preset.get("fields", []))

        self._apply_report()

    @staticmethod
    def _select_listbox_values(lb: tk.Listbox, values: List[str]) -> None:
        lb.selection_clear(0, "end")
        if not values:
            return
        wanted = set(values)
        for i in range(lb.size()):
            if lb.get(i) in wanted:
                lb.selection_set(i)

    def _save_preset(self) -> None:
        os.makedirs(self.PRESETS_DIR, exist_ok=True)
        name = simpledialog.askstring("Save preset", "Preset name:")
        if not name:
            return
        safe = "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_", " ")).strip().replace(" ", "_")
        if not safe:
            messagebox.showwarning("Save preset", "Invalid name.")
            return

        path = os.path.join(self.PRESETS_DIR, f"{safe}.json")
        preset = self._get_current_preset()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(preset, f, indent=2)
            messagebox.showinfo("Save preset", f"Saved:\n{os.path.abspath(path)}")
        except Exception as e:
            messagebox.showerror("Save preset", f"Failed:\n{e}")

    def _load_preset(self) -> None:
        os.makedirs(self.PRESETS_DIR, exist_ok=True)
        files = [f for f in os.listdir(self.PRESETS_DIR) if f.lower().endswith(".json")]
        if not files:
            messagebox.showinfo("Load preset", f"No presets found in {self.PRESETS_DIR}/")
            return

        win = tk.Toplevel(self)
        win.title("Load preset")
        win.geometry("380x360")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(frame, text="Select a preset", style="Title.TLabel").pack(anchor="w")

        lb = tk.Listbox(frame, activestyle="none", exportselection=False, height=12)
        lb.pack(fill="both", expand=True, pady=(10, 10))
        for f in sorted(files):
            lb.insert("end", f)

        def load_selected() -> None:
            sel = lb.curselection()
            if not sel:
                return
            fname = lb.get(sel[0])
            path = os.path.join(self.PRESETS_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    preset = json.load(fp)
                self._apply_preset(preset)
                win.destroy()
            except Exception as e:
                messagebox.showerror("Load preset", f"Failed:\n{e}")

        btns = ttk.Frame(frame)
        btns.pack(fill="x")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(btns, text="Load", style="Accent.TButton", command=load_selected).pack(side="right", padx=8)

        lb.bind("<Double-1>", lambda e: load_selected())

    def _reset_controls(self) -> None:
        self.n_var.set(5)
        self.mode_var.set("Value")
        self.include_top_var.set(True)
        self.include_bottom_var.set(True)

        self._lb_select_none(self.metrics_lb)
        self._lb_select_none(self.fields_lb)

        for i in range(self.metrics_lb.size()):
            if self.metrics_lb.get(i) == "Total":
                self.metrics_lb.selection_set(i)
                break
        else:
            if self.metrics_lb.size() > 0:
                self.metrics_lb.selection_set(0)

        for i in range(self.fields_lb.size()):
            if self.fields_lb.get(i) in ("instrument", "day", "portfolio", "counterparty", "underlying"):
                self.fields_lb.selection_set(i)

        self._apply_report()

    # ----------------------------
    # HTML export
    # ----------------------------

    def _create_html(self) -> None:
        df = self._df_report
        if df is None or df.empty:
            messagebox.showinfo("Create HTML", "No report data. Click Apply first.")
            return

        d_from = self.from_var.get().strip()
        d_to = self.to_var.get().strip()
        mode = self.mode_var.get()
        n = int(self.n_var.get())

        rng = self._df_range if self._df_range is not None else pd.DataFrame()
        metrics = self._selected_from_listbox(self.metrics_lb)
        summary_lines = ReportSheet._make_summary_lines(rng, metrics)

        html = self._report_to_html(df, d_from, d_to, mode, n, summary_lines)

        os.makedirs("reports", exist_ok=True)
        fname = f"report_{d_from}_to_{d_to}.html".replace(":", "-")
        path = os.path.join("reports", fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

        try:
            self.clipboard_clear()
            self.clipboard_append(os.path.abspath(path))
        except Exception:
            pass

        messagebox.showinfo("Create HTML", f"Saved:\n{os.path.abspath(path)}\n\n(Path copied to clipboard)")

    @staticmethod
    def _report_to_html(df: pd.DataFrame, d_from: str, d_to: str, mode: str, n: int, summary_lines: List[str]) -> str:
        css = """
        <style>
          body { font-family: Segoe UI, Arial, sans-serif; background: #F6F8FC; color: #0B1220; padding: 24px; }
          .card { background: white; border: 1px solid #D8E1F0; border-radius: 14px; padding: 16px; margin: 14px 0; box-shadow: 0 8px 24px rgba(15,23,42,0.06); }
          h1 { margin: 0 0 8px 0; font-size: 22px; }
          .meta { color: #5E6B85; font-size: 12px; margin-bottom: 12px; line-height: 1.5; }
          h2 { margin: 0 0 8px 0; font-size: 16px; }
          table { width: 100%; border-collapse: collapse; font-size: 12px; }
          th, td { border-bottom: 1px solid #EEF3FF; padding: 8px 10px; text-align: left; white-space: nowrap; }
          th { background: #F8FAFF; position: sticky; top: 0; z-index: 1; }
          tr:hover td { background: #F3F6FF; }
          .top { color: #0B6B2A; font-weight: 700; }
          .bottom { color: #B91C1C; font-weight: 700; }
          .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; border: 1px solid #D8E1F0; background: #F8FAFF; }
          .summary { white-space: pre-line; }
        </style>
        """

        summary_html = "\n".join(summary_lines) if summary_lines else "No summary."
        header = f"""
        <div class="card">
          <h1>Post-Trade Report</h1>
          <div class="meta">
            Range: <span class="pill">{d_from}</span> → <span class="pill">{d_to}</span>
            • N: <span class="pill">{n}</span>
            • Ranking: <span class="pill">{mode}</span>
            • Rows: <span class="pill">{len(df)}</span>
            <div class="summary">{summary_html}</div>
          </div>
        </div>
        """

        parts = [f"<!doctype html><html><head><meta charset='utf-8'>{css}</head><body>", header]

        for metric in df["metric"].astype("string").unique().tolist():
            d_m = df[df["metric"].astype("string") == metric].copy()

            for rtype in d_m["rank_type"].astype("string").unique().tolist():
                block = d_m[d_m["rank_type"].astype("string") == rtype].copy()
                cls = "top" if rtype == "Top" else "bottom"
                parts.append(f"<div class='card'><h2>{metric} • <span class='{cls}'>{rtype}</span></h2>")
                parts.append(block.to_html(index=False, escape=True))
                parts.append("</div>")

        parts.append("</body></html>")
        return "\n".join(parts)


# ------------------------------------------------------------
# Table widget (fast, cached, sortable, columns selector)
# ------------------------------------------------------------

class ReportDataTable(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._df: Optional[pd.DataFrame] = None
        self._df_view: Optional[pd.DataFrame] = None

        self._sort_col: Optional[str] = None
        self._sort_asc: bool = True

        self._visible_cols: Optional[List[str]] = None
        self._rendered_cols: List[str] = []

        self._cache: Dict[str, List[str]] = {}
        self._cache_len: int = 0

        self._resize_after_id: Optional[str] = None

        self._build()

    def _build(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 8))

        ttk.Button(controls, text="Columns", command=self._open_columns_dialog_simple).pack(side="left")
        self.info_var = tk.StringVar(value="")
        ttk.Label(controls, textvariable=self.info_var, style="Muted.TLabel").pack(side="right")

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True)

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
        self.tree.tag_configure("toprow", background="#F0FFF4")
        self.tree.tag_configure("bottomrow", background="#FFF5F5")
        self.tree.tag_configure("totalrow", background="#EEF3FF")

        self.tree.bind("<Configure>", self._on_tree_configure)

    def set_df(self, df: Optional[pd.DataFrame]) -> None:
        self._df = df
        self._df_view = df
        self._sort_col = None
        self._sort_asc = True

        if df is None or df.empty:
            self.info_var.set("No rows.")
            self._clear_tree()
            self._visible_cols = None
            self._cache.clear()
            self._cache_len = 0
            return

        if self._visible_cols is None:
            self._visible_cols = list(df.columns)

        self.info_var.set(f"{len(df):,} rows")
        self._cache, self._cache_len = build_display_cache(df)
        self._render_from_cache()

    def _render_from_cache(self) -> None:
        df = self._df_view
        if df is None or df.empty:
            self._clear_tree()
            return

        cols = sanitize_visible_cols(list(df.columns), self._visible_cols)
        self._rendered_cols = cols

        self._clear_tree()
        self.tree["columns"] = cols

        for c in cols:
            self.tree.heading(c, text=c, command=lambda col=c: self._sort_by(col))
            self.tree.column(c, width=110, minwidth=80, anchor="c", stretch=True)

        rank_type_idx = cols.index("rank_type") if "rank_type" in cols else None
        rank_idx = cols.index("rank") if "rank" in cols else None

        cache = self._cache
        for i in range(self._cache_len):
            values = [cache[c][i] for c in cols]

            tag = "even" if (i % 2 == 0) else "odd"

            if rank_idx is not None and str(values[rank_idx]) == "TOTAL":
                tag = "totalrow"
            else:
                if rank_type_idx is not None:
                    rt = values[rank_type_idx]
                    if rt == "Top":
                        tag = "toprow"
                    elif rt == "Bottom":
                        tag = "bottomrow"

            self.tree.insert("", "end", values=values, tags=(tag,))

        self._autofit_from_cache(sample_rows=min(200, self._cache_len))

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
                df.assign(_tmp=df[col].astype("string"))
                .sort_values(by="_tmp", ascending=self._sort_asc, kind="mergesort")
                .drop(columns="_tmp")
            )

        view = view.reset_index(drop=True)
        self._df_view = view
        self._cache, self._cache_len = build_display_cache(view)
        self._render_from_cache()

    def _clear_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = []

    def _on_tree_configure(self, _event) -> None:
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except Exception:
                pass
        self._resize_after_id = self.after(180, lambda: self._autofit_from_cache(sample_rows=140))

    def _autofit_from_cache(self, sample_rows: int = 140) -> None:
        if not self._rendered_cols or self._cache_len == 0:
            return

        import tkinter.font as tkfont

        body_font = tkfont.nametofont("TkDefaultFont")
        heading_font = tkfont.Font(
            family=body_font.actual("family"),
            size=body_font.actual("size"),
            weight="bold",
        )

        pad = 34
        n = min(sample_rows, self._cache_len)
        cache = self._cache

        max_px: Dict[str, int] = {}
        for c in self._rendered_cols:
            max_px[c] = heading_font.measure(c) + pad

        for c in self._rendered_cols:
            col_vals = cache.get(c, [])
            for i in range(n):
                w = body_font.measure(col_vals[i]) + pad
                if w > max_px[c]:
                    max_px[c] = w

        hard_min, hard_max = 80, 520
        widths = {c: max(hard_min, min(hard_max, max_px[c])) for c in self._rendered_cols}
        for c in self._rendered_cols:
            self.tree.column(c, width=widths[c], stretch=True)

    # SIMPLE + STABLE columns dialog (like your working one)
    def _open_columns_dialog_simple(self) -> None:
        df = self._df
        if df is None or df.empty:
            messagebox.showinfo("Columns", "No data to show.")
            return

        all_cols = list(df.columns)
        visible_set = set(self._visible_cols or all_cols)

        win = tk.Toplevel(self)
        win.title("Select columns")
        win.geometry("420x520")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(frame, text="Columns", style="Title.TLabel").pack(anchor="w")

        lb = tk.Listbox(frame, selectmode="extended", activestyle="none", exportselection=False, height=20)
        lb.pack(fill="both", expand=True, pady=(10, 10))

        for c in all_cols:
            lb.insert("end", c)

        for i, c in enumerate(all_cols):
            if c in visible_set:
                lb.selection_set(i)

        btns = ttk.Frame(frame)
        btns.pack(fill="x")

        def select_all() -> None:
            lb.selection_set(0, "end")

        def select_none() -> None:
            lb.selection_clear(0, "end")

        def apply_and_close() -> None:
            sel_idx = lb.curselection()
            if not sel_idx:
                messagebox.showwarning("Columns", "Select at least one column.")
                return
            chosen = [all_cols[i] for i in sel_idx]
            self._visible_cols = chosen

            # re-render using current view
            if self._df_view is None:
                self._df_view = self._df

            self._cache, self._cache_len = build_display_cache(self._df_view)
            self._render_from_cache()
            win.destroy()

        ttk.Button(btns, text="All", command=select_all).pack(side="left")
        ttk.Button(btns, text="None", command=select_none).pack(side="left", padx=8)
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(btns, text="Apply", style="Accent.TButton", command=apply_and_close).pack(side="right", padx=8)
