from __future__ import annotations

from typing import Dict, List
import tkinter as tk
from tkinter import ttk

class LeftNav(ttk.Frame):
    def __init__(self, master: tk.Misc, on_select_sheet) -> None:
        super().__init__(master, style="Nav.TFrame")
        self.on_select_sheet = on_select_sheet
        self._buttons: Dict[str, ttk.Button] = {}
        self._build()

    def _build(self) -> None:
        self.pack_propagate(False)
        header = ttk.Frame(self, style="Nav.TFrame")
        header.pack(fill="x", padx=10, pady=(12, 8))
        ttk.Label(header, text="SHEETS", style="NavTitle.TLabel").pack(anchor="w")

        self.btn_container = ttk.Frame(self, style="Nav.TFrame")
        self.btn_container.pack(fill="both", expand=True, padx=6, pady=(0, 10))

    def set_sheets(self, sheets: List[object]) -> None:
        for child in self.btn_container.winfo_children():
            child.destroy()
        self._buttons.clear()

        for s in sheets:
            b = ttk.Button(
                self.btn_container,
                text=f"  {getattr(s, 'sheet_title', 'Sheet')}",
                style="Nav.TButton",
                command=lambda sid=getattr(s, 'sheet_id', ''): self.on_select_sheet(sid),
            )
            b.pack(fill="x", pady=4, padx=6)
            self._buttons[getattr(s, 'sheet_id', '')] = b

    def set_selected(self, sheet_id: str) -> None:
        for sid, b in self._buttons.items():
            b.configure(style="NavSelected.TButton" if sid == sheet_id else "Nav.TButton")
