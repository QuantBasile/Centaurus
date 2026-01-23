from __future__ import annotations
import tkinter as tk
from tkinter import ttk

class FuturisticTheme:
    def apply(self, root: tk.Tk) -> None:
        root.title("Post-Trade Analyzer")
        root.geometry("1280x760")
        root.minsize(1080, 650)

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.bg = "#F5F7FB"
        self.panel = "#FFFFFF"
        self.panel2 = "#F8FAFF"
        self.nav = "#EEF3FF"
        self.border = "#D8E1F0"
        self.text = "#0B1220"
        self.muted = "#5E6B85"
        self.accent = "#2E7BFF"
        self.accent_hover = "#2667D6"

        root.configure(bg=self.bg)

        style.configure(".", font=("Segoe UI", 10), background=self.bg, foreground=self.text)
        style.configure("TFrame", background=self.bg)
        style.configure("TLabel", background=self.bg, foreground=self.text)
        style.configure("Muted.TLabel", foreground=self.muted)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 14), foreground=self.text)

        style.configure("Header.TFrame", background=self.panel2)
        style.configure("HeaderCard.TFrame", background=self.panel2)
        style.configure("HeaderLine.TSeparator", background=self.border)

        style.configure("Card.TFrame", background=self.panel)
        style.configure("CardTitle.TLabel", background=self.panel, font=("Segoe UI Semibold", 11), foreground=self.text)
        style.configure("CardBody.TLabel", background=self.panel, foreground=self.muted)

        style.configure("TEntry", fieldbackground=self.panel, bordercolor=self.border, padding=(10, 8))

        style.configure("TButton", padding=(12, 10), borderwidth=0)
        style.configure("Accent.TButton", background=self.accent, foreground="#FFFFFF")
        style.map("Accent.TButton",
                  background=[("active", self.accent_hover), ("!disabled", self.accent)],
                  foreground=[("!disabled", "#FFFFFF")])

        style.configure("Nav.TFrame", background=self.nav)
        style.configure("NavTitle.TLabel", background=self.nav, foreground=self.muted, font=("Segoe UI Semibold", 10))
        style.configure("Nav.TButton", background=self.nav, foreground=self.text, anchor="w", padding=(14, 10))
        style.map("Nav.TButton",
                  background=[("active", "#DCE8FF")],
                  foreground=[("!disabled", self.text)])
        style.configure("NavSelected.TButton", background="#D1E2FF", foreground=self.text)

        style.configure("TProgressbar", thickness=8)

        style.configure("TNotebook", background=self.bg, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 8))
        style.map("TNotebook.Tab",
                  background=[("selected", self.panel), ("!selected", "#EAF1FF")],
                  foreground=[("selected", self.text), ("!selected", self.muted)])

        style.configure("Futur.Treeview",
                        background=self.panel,
                        fieldbackground=self.panel,
                        foreground=self.text,
                        rowheight=24,
                        bordercolor=self.border,
                        lightcolor=self.border,
                        darkcolor=self.border)
        style.configure("Futur.Treeview.Heading",
                        font=("Segoe UI Semibold", 10),
                        background="#EDF3FF",
                        foreground=self.text,
                        relief="flat")
        style.map("Futur.Treeview",
                  background=[("selected", "#CFE1FF")],
                  foreground=[("selected", self.text)])
