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
# Report Sheet (CEO Mode + Deluxe TOTAL row + selectable PnL extras)
# ------------------------------------------------------------

class ReportSheet(ttk.Frame):
    sheet_id = "report"
    sheet_title = "Report"

    # main metric dropdown candidates
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

    # defaults shown in PnL extras selector
    DEFAULT_EXTRA_TOTAL_METRICS = [
        "Total",
        "AufgeldCum",
        "feesCum",
        "PremiaCum",
        "PnlVonDeltaCum",
        "SpreadsCapture",
        "FullSpreadCapture",
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
        self.n_var = tk.IntVar(value=10)

        self.metric_var = tk.StringVar(value="Total")
        self.portfolio_var = tk.StringVar(value="ALL")

        self._build()

    # ----------------------------
    # UI
    # ----------------------------

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

        # Row 0 - dates, N, metric, portfolio
        r0 = ttk.Frame(inner)
        r0.pack(fill="x")

        ttk.Label(r0, text="From (YYYY-MM-DD)", style="Muted.TLabel").pack(side="left")
        self.from_entry = ttk.Entry(r0, textvariable=self.from_var, width=12)
        self.from_entry.pack(side="left", padx=(8, 14))

        ttk.Label(r0, text="To (YYYY-MM-DD)", style="Muted.TLabel").pack(side="left")
        self.to_entry = ttk.Entry(r0, textvariable=self.to_var, width=12)
        self.to_entry.pack(side="left", padx=(8, 14))

        ttk.Label(r0, text="N (Top/Bottom)", style="Muted.TLabel").pack(side="left")
        self.n_spin = ttk.Spinbox(r0, from_=1, to=50000, textvariable=self.n_var, width=7)
        self.n_spin.pack(side="left", padx=(8, 14))

        ttk.Label(r0, text="Metric", style="Muted.TLabel").pack(side="left")
        self.metric_cb = ttk.Combobox(r0, textvariable=self.metric_var, state="readonly", width=22)
        self.metric_cb.pack(side="left", padx=(8, 14))

        ttk.Label(r0, text="Portfolio", style="Muted.TLabel").pack(side="left")
        self.portfolio_cb = ttk.Combobox(r0, textvariable=self.portfolio_var, state="readonly", width=18)
        self.portfolio_cb.pack(side="left", padx=(8, 14))

        self.apply_btn = ttk.Button(r0, text="Apply", style="Accent.TButton", command=self._apply_report)
        self.apply_btn.pack(side="right")

        # Row 1 - Fields + PnL extras multi-select
        r1 = ttk.Frame(inner)
        r1.pack(fill="x", pady=(12, 0))

        fbox = ttk.Frame(r1, style="Card.TFrame")
        fbox.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Label(fbox, text="Fields to show (multi-select)", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))
        self.fields_lb = tk.Listbox(
            fbox, selectmode="extended", activestyle="none", exportselection=False, height=7
        )
        self.fields_lb.pack(fill="x", expand=True)

        pbox = ttk.Frame(r1, style="Card.TFrame")
        pbox.pack(side="left", fill="x", expand=True)
        ttk.Label(pbox, text="PnL columns to display (TOTAL row)", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))
        self.pnl_lb = tk.Listbox(
            pbox, selectmode="extended", activestyle="none", exportselection=False, height=7
        )
        self.pnl_lb.pack(fill="x", expand=True)

        # Row 2 - buttons
        r2 = ttk.Frame(inner)
        r2.pack(fill="x", pady=(12, 0))

        ttk.Button(r2, text="Fields: all", command=lambda: self._lb_select_all(self.fields_lb)).pack(side="left")
        ttk.Button(r2, text="Fields: none", command=lambda: self._lb_select_none(self.fields_lb)).pack(side="left", padx=6)

        ttk.Button(r2, text="PnL: all", command=lambda: self._lb_select_all(self.pnl_lb)).pack(side="left", padx=(14, 0))
        ttk.Button(r2, text="PnL: none", command=lambda: self._lb_select_none(self.pnl_lb)).pack(side="left", padx=6)

        ttk.Button(r2, text="Save preset", command=self._save_preset).pack(side="left", padx=(14, 0))
        ttk.Button(r2, text="Load preset", command=self._load_preset).pack(side="left", padx=6)
        ttk.Button(r2, text="Reset", command=self._reset_controls).pack(side="left", padx=6)

        ttk.Button(r2, text="Create HTML", command=self._create_html).pack(side="right")

        # Info + summary
        self.info_var = tk.StringVar(value="Load data to begin.")
        ttk.Label(inner, textvariable=self.info_var, style="Muted.TLabel").pack(anchor="w", pady=(10, 0))

        # keep summary short (CEO)
        self.summary_text = tk.Text(inner, height=2, wrap="word", relief="flat", bg="#FFFFFF")
        self.summary_text.pack(fill="x", pady=(8, 0))
        self.summary_text.configure(state="disabled")

        # Data table
        self.data = ReportDataTable(self)
        self.data.pack(fill="both", expand=True, padx=14, pady=(10, 14))

        # Key binds
        self.from_entry.bind("<Return>", lambda e: self._apply_report())
        self.to_entry.bind("<Return>", lambda e: self._apply_report())
        self.metric_cb.bind("<<ComboboxSelected>>", lambda e: self._apply_report())
        self.portfolio_cb.bind("<<ComboboxSelected>>", lambda e: self._apply_report())

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
            self.summary_text.insert("1.0", "\n".join(lines[:2]))
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

        dmin = self._df_eod["day"].min()
        dmax = self._df_eod["day"].max()
        if isinstance(dmin, date) and not self.from_var.get():
            self.from_var.set(dmin.isoformat())
        if isinstance(dmax, date) and not self.to_var.get():
            self.to_var.set(dmax.isoformat())

        existing = set(self._df_eod.columns)

        metric_cols = [c for c in self.DEFAULT_METRICS if c in existing]
        if not metric_cols:
            metric_cols = [
                c for c in self._df_eod.columns
                if pd.api.types.is_numeric_dtype(self._df_eod[c]) and c not in ("tradeNr",)
            ][:24]
        self.metric_cb["values"] = metric_cols
        if self.metric_var.get() not in metric_cols:
            self.metric_var.set(metric_cols[0] if metric_cols else "")

        portfolios = ["ALL"]
        if "portfolio" in self._df_eod.columns:
            vals = (
                self._df_eod["portfolio"]
                .astype("string")
                .fillna("")
                .replace({"<NA>": ""})
                .unique()
                .tolist()
            )
            vals = [v for v in vals if v and v.strip()]
            portfolios += sorted(set(vals))
        self.portfolio_cb["values"] = portfolios
        if self.portfolio_var.get() not in portfolios:
            self.portfolio_var.set("ALL")

        self.fields_lb.delete(0, "end")
        fields: List[str] = []
        for c in self.DEFAULT_FIELDS:
            if c in existing and c not in fields:
                fields.append(c)
        for c in self._df_eod.columns:
            if c in fields or c in metric_cols or c.startswith("flag_"):
                continue
            fields.append(c)
            if len(fields) >= 30:
                break
        for c in fields:
            self.fields_lb.insert("end", c)

        for i, c in enumerate(fields):
            if c in ("instrument", "day", "portfolio", "counterparty", "underlying"):
                self.fields_lb.selection_set(i)

        self.pnl_lb.delete(0, "end")
        pnl_candidates = [c for c in self.DEFAULT_EXTRA_TOTAL_METRICS if c in existing]
        if not pnl_candidates:
            pnl_candidates = [
                c for c in self._df_eod.columns
                if pd.api.types.is_numeric_dtype(self._df_eod[c]) and c not in ("tradeNr",)
            ][:24]
        for c in pnl_candidates:
            self.pnl_lb.insert("end", c)

        if pnl_candidates:
            self.pnl_lb.selection_set(0, "end")

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
            self.data.set_df(None)
            return

        if d_to < d_from:
            d_from, d_to = d_to, d_from
            self.from_var.set(d_from.isoformat())
            self.to_var.set(d_to.isoformat())

        n = int(self.n_var.get())
        n = max(1, min(50000, n))

        metric = (self.metric_var.get() or "").strip()
        if not metric or metric not in self._df_eod.columns:
            self.info_var.set("Select a valid metric.")
            self._set_summary([])
            self.data.set_df(None)
            return

        fields = self._selected_from_listbox(self.fields_lb)
        pnl_extras = self._selected_from_listbox(self.pnl_lb)

        base = self._df_eod
        mask = (base["day"] >= d_from) & (base["day"] <= d_to)
        rng = base.loc[mask].copy()

        pf = (self.portfolio_var.get() or "ALL").strip()
        if pf != "ALL" and "portfolio" in rng.columns:
            rng = rng[rng["portfolio"].astype("string") == pf]

        self._df_range = rng

        report, kpis = self._build_report_table_ceo_deluxe(
            rng=rng,
            metric=metric,
            fields=fields,
            n=n,
            extra_metrics=pnl_extras,
        )

        self._df_report = report
        self.data.set_df(report)

        # CEO KPIs
        kpi_txt = ""
        if kpis:
            kpi_txt = f"TOTAL Σ={kpis['total_sum']:,} • TOP Σ={kpis['top_sum']:,} • BOTTOM Σ={kpis['bottom_sum']:,} • NET={kpis['net']:,}"

        # Best/Worst badges (confirmed)
        best_txt = ""
        worst_txt = ""
        if rng is not None and not rng.empty and metric in rng.columns:
            s = pd.to_numeric(rng[metric], errors="coerce").fillna(0.0)
            try:
                i_best = int(s.idxmax())
                i_worst = int(s.idxmin())

                rb = rng.loc[i_best]
                rw = rng.loc[i_worst]

                best_txt = f"BEST: {rb.get('instrument','?')} {rb.get('day','?')} = {int(round(float(s.loc[i_best]))):,}"
                worst_txt = f"WORST: {rw.get('instrument','?')} {rw.get('day','?')} = {int(round(float(s.loc[i_worst]))):,}"
            except Exception:
                best_txt = ""
                worst_txt = ""

        msg = f"EOD rows: {len(rng):,} • Metric: {metric} • N={n} • Portfolio={pf}"
        if kpi_txt:
            msg += f" • {kpi_txt}"
        if best_txt:
            msg += f" • {best_txt}"
        if worst_txt:
            msg += f" • {worst_txt}"

        self.info_var.set(msg)
        self._set_summary(self._make_summary_lines(rng))

    @staticmethod
    def _selected_from_listbox(lb: tk.Listbox) -> List[str]:
        return [lb.get(i) for i in lb.curselection()]

    @staticmethod
    def _make_summary_lines(rng: pd.DataFrame) -> List[str]:
        if rng is None or rng.empty:
            return ["No rows in range (after portfolio filter)."]
        inst_n = rng["instrument"].nunique() if "instrument" in rng.columns else len(rng)
        day_n = rng["day"].nunique() if "day" in rng.columns else len(rng)
        return [f"Universe: instruments={inst_n:,} • days={day_n:,} • rows={len(rng):,}"]

    @staticmethod
    def _fmt_int_series(x: pd.Series) -> pd.Series:
        v = pd.to_numeric(x, errors="coerce").round(0)
        return v.astype("Int64")

    @classmethod
    def _build_report_table_ceo_deluxe(
        cls,
        rng: pd.DataFrame,
        metric: str,
        fields: List[str],
        n: int,
        extra_metrics: List[str],
    ) -> tuple[pd.DataFrame, Dict[str, int]]:
        if rng is None or rng.empty:
            return pd.DataFrame(), {}

        fields = [c for c in fields if c in rng.columns]
        for must in ("instrument", "day"):
            if must in rng.columns and must not in fields:
                fields.insert(0, must)

        work = rng.copy()
        work["_metric_value"] = pd.to_numeric(work[metric], errors="coerce").fillna(0.0)

        top = work.nlargest(n, "_metric_value").copy()
        top["section"] = "Top"
        top["rank"] = range(1, len(top) + 1)

        # Bottom ranks: rank=1 is most negative, but displayed with rank=1 at the end
        bot_raw = work.nsmallest(n, "_metric_value").copy()
        bot_raw["section"] = "Bottom"
        bot_raw["rank"] = range(1, len(bot_raw) + 1)
        bot = bot_raw.sort_values("rank", ascending=False, kind="mergesort").copy()

        # extras for TOTAL row
        extra_cols = [c for c in extra_metrics if c in work.columns and c != metric]
        extra_totals: Dict[str, float] = {}
        for c in extra_cols:
            extra_totals[c] = float(pd.to_numeric(work[c], errors="coerce").fillna(0.0).sum())

        # TOTAL row
        total_val = float(work["_metric_value"].sum())
        total_row = {c: pd.NA for c in (["section", "rank", "_metric_value"] + fields + extra_cols)}
        total_row["section"] = "TOTAL"
        total_row["rank"] = "Σ"
        total_row["_metric_value"] = total_val

        # CEO deluxe labels
        for key in ("instrument", "day", "portfolio"):
            if key in fields:
                total_row[key] = "ALL"

        for c, v in extra_totals.items():
            total_row[c] = v

        out = pd.concat([top, bot, pd.DataFrame([total_row])], ignore_index=True)

        cols = ["section", "rank", "_metric_value"] + fields + extra_cols
        cols = [c for c in cols if c in out.columns]
        out = out[cols].rename(columns={"_metric_value": "metric_value"})

        # enforce integers
        out["metric_value"] = cls._fmt_int_series(out["metric_value"])
        for c in extra_cols:
            out[c] = cls._fmt_int_series(out[c])

        # sign column
        def sign_icon(v, section: str) -> str:
            if section == "TOTAL":
                return "Σ"
            try:
                vv = float(v)
            except Exception:
                vv = 0.0
            return "🟢" if vv >= 0 else "🔴"

        out.insert(0, "sign", [sign_icon(v, s) for v, s in zip(out["metric_value"], out["section"])])

        # Order: Top, Bottom, TOTAL (Bottom is already visually reversed via bot)
        section_order = {"Top": 0, "Bottom": 1, "TOTAL": 2}
        out["_sec_ord"] = out["section"].map(section_order).fillna(9).astype(int)

        rank_num = pd.to_numeric(out["rank"], errors="coerce")
        out["_rank_num"] = rank_num
        top_mask = out["section"].astype("string") == "Top"
        bottom_mask = out["section"].astype("string") == "Bottom"
        out["_rank_key"] = out["_rank_num"].astype("float64")
        out.loc[bottom_mask, "_rank_key"] = -out.loc[bottom_mask, "_rank_key"]  # invert => descending
        out.loc[~(top_mask | bottom_mask), "_rank_key"] = 1e12

        out.sort_values(["_sec_ord", "_rank_key"], inplace=True, kind="mergesort")
        out.drop(columns=["_sec_ord", "_rank_num", "_rank_key"], inplace=True)
        out.reset_index(drop=True, inplace=True)

        # KPIs
        top_sum = int(pd.to_numeric(top["_metric_value"], errors="coerce").fillna(0).sum()) if len(top) else 0
        bottom_sum = int(pd.to_numeric(bot_raw["_metric_value"], errors="coerce").fillna(0).sum()) if len(bot_raw) else 0
        total_sum = int(round(total_val))
        kpis = {
            "top_sum": top_sum,
            "bottom_sum": bottom_sum,
            "total_sum": total_sum,
            "net": top_sum + bottom_sum,
        }

        return out, kpis

    # ----------------------------
    # Presets
    # ----------------------------

    def _get_current_preset(self) -> Dict:
        fields = self._selected_from_listbox(self.fields_lb)
        pnl_cols = self._selected_from_listbox(self.pnl_lb)
        return {
            "from": self.from_var.get().strip(),
            "to": self.to_var.get().strip(),
            "n": int(self.n_var.get()),
            "metric": self.metric_var.get(),
            "portfolio": self.portfolio_var.get(),
            "fields": fields,
            "pnl_cols": pnl_cols,
        }

    def _apply_preset(self, preset: Dict) -> None:
        if preset.get("from"):
            self.from_var.set(preset["from"])
        if preset.get("to"):
            self.to_var.set(preset["to"])
        if "n" in preset:
            self.n_var.set(int(preset["n"]))

        if preset.get("metric"):
            self.metric_var.set(preset["metric"])
        if preset.get("portfolio"):
            self.portfolio_var.set(preset["portfolio"])

        self._select_listbox_values(self.fields_lb, preset.get("fields", []))
        self._select_listbox_values(self.pnl_lb, preset.get("pnl_cols", []))
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
        self.n_var.set(10)
        if self.metric_cb["values"]:
            vals = list(self.metric_cb["values"])
            self.metric_var.set("Total" if "Total" in vals else vals[0])
        self.portfolio_var.set("ALL")

        self._lb_select_none(self.fields_lb)
        for i in range(self.fields_lb.size()):
            if self.fields_lb.get(i) in ("instrument", "day", "portfolio", "counterparty", "underlying"):
                self.fields_lb.selection_set(i)

        if self.pnl_lb.size() > 0:
            self.pnl_lb.selection_set(0, "end")

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
        n = int(self.n_var.get())
        metric = self.metric_var.get()
        portfolio = self.portfolio_var.get()

        rng = self._df_range if self._df_range is not None else pd.DataFrame()
        summary_lines = self._make_summary_lines(rng)

        html = self._report_to_html(df, d_from, d_to, n, metric, portfolio, summary_lines)

        os.makedirs("reports", exist_ok=True)
        fname = f"report_{metric}_{d_from}_to_{d_to}.html".replace(":", "-").replace(" ", "_")
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
    def _report_to_html(df: pd.DataFrame, d_from: str, d_to: str, n: int, metric: str, portfolio: str, summary_lines: List[str]) -> str:
        css = """
        <style>
          body { font-family: Segoe UI, Arial, sans-serif; background: #F6F8FC; color: #0B1220; padding: 24px; }
          .card { background: white; border: 1px solid #D8E1F0; border-radius: 14px; padding: 16px; margin: 14px 0; box-shadow: 0 8px 24px rgba(15,23,42,0.06); }
          h1 { margin: 0 0 8px 0; font-size: 22px; }
          .meta { color: #5E6B85; font-size: 12px; margin-bottom: 12px; line-height: 1.5; }
          h2 { margin: 0 0 8px 0; font-size: 16px; }
          table { width: 100%; border-collapse: collapse; font-size: 12px; }
          th, td { border-bottom: 1px solid #EEF3FF; padding: 8px 10px; white-space: nowrap; }
          th { background: #F8FAFF; text-align: left; }
          tr:hover td { background: #F3F6FF; }
          .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; border: 1px solid #D8E1F0; background: #F8FAFF; }
          .summary { white-space: pre-line; }
          .num { text-align: right; font-variant-numeric: tabular-nums; }
          .txt { text-align: center; }
          .metaRow td { background: #EEF3FF; font-weight: 700; }
        </style>
        """

        summary_html = "\n".join(summary_lines) if summary_lines else "No summary."
        header = f"""
        <div class="card">
          <h1>Post-Trade Report</h1>
          <div class="meta">
            Range: <span class="pill">{d_from}</span> → <span class="pill">{d_to}</span>
            • Metric: <span class="pill">{metric}</span>
            • Portfolio: <span class="pill">{portfolio}</span>
            • N: <span class="pill">{n}</span>
            • Rows: <span class="pill">{len(df)}</span>
            <div class="summary">{summary_html}</div>
          </div>
        </div>
        """

        block = df.copy()

        # Format numeric columns as ints with commas
        for c in block.columns:
            if c in ("sign", "section", "rank"):
                continue
            if pd.api.types.is_numeric_dtype(block[c]) or c == "metric_value":
                block[c] = (
                    pd.to_numeric(block[c], errors="coerce")
                    .fillna(0)
                    .astype(int)
                    .map(lambda x: f"{x:,}")
                )

        # Build table with right-align for numeric-like columns
        num_cols = set(["metric_value"])
        for c in block.columns:
            if c in ("sign", "section", "rank"):
                continue
            # after formatting everything is str, so we decide by name heuristic:
            if c == "metric_value":
                num_cols.add(c)

        parts = [f"<!doctype html><html><head><meta charset='utf-8'>{css}</head><body>", header]
        parts.append("<div class='card'><h2>Top / Bottom / TOTAL</h2>")

        parts.append("<table>")
        parts.append("<thead><tr>")
        for c in block.columns:
            parts.append(f"<th>{c}</th>")
        parts.append("</tr></thead>")

        parts.append("<tbody>")
        for _, row in block.iterrows():
            cls_row = "metaRow" if str(row.get("section", "")) == "TOTAL" else ""
            parts.append(f"<tr class='{cls_row}'>")
            for c in block.columns:
                val = row.get(c, "")
                if pd.isna(val):
                    val = ""
                if c in ("sign", "section", "rank"):
                    td_cls = "txt"
                elif c in num_cols:
                    td_cls = "num"
                else:
                    td_cls = "txt"
                parts.append(f"<td class='{td_cls}'>{val}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table>")

        parts.append("</div></body></html>")
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

        # numeric cols -> right align
        numeric_cols: set[str] = set(["metric_value"])
        try:
            for c in cols:
                if c in df.columns and pd.api.types.is_numeric_dtype(df[c]):
                    numeric_cols.add(c)
        except Exception:
            pass

        for c in cols:
            self.tree.heading(c, text=c, command=lambda col=c: self._sort_by(col))

            if c in ("sign", "section", "rank"):
                self.tree.column(c, width=110, minwidth=80, anchor="w", stretch=True)
            elif c in numeric_cols:
                self.tree.column(c, width=110, minwidth=80, anchor="e", stretch=True)
            else:
                self.tree.column(c, width=110, minwidth=80, anchor="c", stretch=True)

        section_idx = cols.index("section") if "section" in cols else None

        cache = self._cache
        for i in range(self._cache_len):
            values = [cache[c][i] for c in cols]

            tag = "even" if (i % 2 == 0) else "odd"
            if section_idx is not None:
                sec = values[section_idx]
                if sec == "Top":
                    tag = "toprow"
                elif sec == "Bottom":
                    tag = "bottomrow"
                elif sec == "TOTAL":
                    tag = "totalrow"

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

            if self._df_view is None:
                self._df_view = self._df

            self._cache, self._cache_len = build_display_cache(self._df_view)
            self._render_from_cache()
            win.destroy()

        ttk.Button(btns, text="All", command=select_all).pack(side="left")
        ttk.Button(btns, text="None", command=select_none).pack(side="left", padx=8)
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(btns, text="Apply", style="Accent.TButton", command=apply_and_close).pack(side="right", padx=8)
