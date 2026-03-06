from __future__ import annotations

import threading
import queue
import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional

import pandas as pd

from .theme import FuturisticTheme
from .ui_header import HeaderBar
from .ui_nav import LeftNav
from .utils.time_utils import parse_iso_date
from .data_provider import TradeDataProvider

from .sheets.raw_data import RawDataSheet
from .sheets.end_of_day import EndOfDaySheet
from .sheets.instrument_day import InstrumentDaySheet
from .sheets.day_report import DayReportSheet


class PostTradeApp(tk.Tk):
    def __init__(self, provider: TradeDataProvider) -> None:
        super().__init__()
        FuturisticTheme().apply(self)

        self.provider = provider
        self._result_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()

        self._trades_df: Optional[pd.DataFrame] = None

        self.header = HeaderBar(self, on_load=self.load_button_pressed)

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.nav = LeftNav(main, on_select_sheet=self.show_sheet)
        self.nav.pack(side="left", fill="y")
        self.nav.configure(width=240)

        self.content = ttk.Frame(main)
        self.content.pack(side="left", fill="both", expand=True)

        self.sheets: Dict[str, object] = {}
        self._init_sheets()
        self.show_sheet("raw")

        self.after(50, self._poll_results)

    def _init_sheets(self) -> None:
        raw = RawDataSheet(self.content)
        eod = EndOfDaySheet(self.content)
        instday = InstrumentDaySheet(self.content)
        dayrep = DayReportSheet(self.content)

        self.sheets[raw.sheet_id] = raw
        self.sheets[eod.sheet_id] = eod
        self.sheets[instday.sheet_id] = instday
        self.sheets[dayrep.sheet_id] = dayrep

        self.nav.set_sheets(list(self.sheets.values()))
        for s in self.sheets.values():
            s.place(relx=0, rely=0, relwidth=1, relheight=1)

    def show_sheet(self, sheet_id: str) -> None:
        if sheet_id not in self.sheets:
            return
        self.nav.set_selected(sheet_id)
        self.sheets[sheet_id].tkraise()
        # PERFORMANCE: never recompute on tab switch

    def load_button_pressed(self, from_s: str, to_s: str) -> None:
        try:
            from_date = parse_iso_date(from_s)
            to_date = parse_iso_date(to_s)
        except ValueError as e:
            self.header.show_error("Invalid date", str(e))
            return

        if to_date < from_date:
            self.header.show_error("Invalid range", "To date must be >= From date.")
            return

        self.header.set_loading(True)
        self.header.set_status("Loading trades…")
        self.header.set_rows_info(None)

        t = threading.Thread(target=self._load_worker, args=(from_date, to_date), daemon=True)
        t.start()

    def _load_worker(self, from_date, to_date) -> None:
        try:
            trades = self.provider.load(from_date, to_date)
            self._result_queue.put(("ok", trades))
        except Exception as e:
            self._result_queue.put(("err", e))

    def _poll_results(self) -> None:
        try:
            kind, payload = self._result_queue.get_nowait()
        except queue.Empty:
            self.after(50, self._poll_results)
            return

        if kind == "ok":
            trades = payload  # type: ignore[assignment]
            self._trades_df = trades

            self.header.set_loading(False)
            self.header.set_status("Loaded.")
            self.header.set_rows_info(trades)

            for s in self.sheets.values():
                if hasattr(s, "on_df_loaded"):
                    s.on_df_loaded(self._trades_df)

        else:
            err = payload
            self.header.set_loading(False)
            self.header.set_status("Ready.")
            self.header.show_error("Load failed", f"{type(err).__name__}: {err}")

        self.after(50, self._poll_results)