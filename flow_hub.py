"""Modern Tkinter Hub for Flow State.

The Hub receives the running ``flow`` module as ``app`` so it can control the
existing single-process microphone and settings state without circular imports.
"""

from __future__ import annotations

import os
import threading
import time
import tkinter as tk
import winsound
from pathlib import Path
from tkinter import filedialog, messagebox

import numpy as np
import pyperclip


LIGHT = {
    "bg": "#e8e5df",
    "paper": "#faf8f3",
    "paper2": "#f0ede6",
    "text": "#27262c",
    "muted": "#716e76",
    "border": "#d7d2ca",
    "grid": "#e5e1da",
    "major": "#d9d6e8",
    "brand": "#4a4a73",
    "success": "#287a53",
    "danger": "#b72f28",
    "track": "#aaa397",
}

DARK = {
    "bg": "#121315",
    "paper": "#1a1b1f",
    "paper2": "#222329",
    "text": "#f2efe8",
    "muted": "#b7b3bd",
    "border": "#3d3d47",
    "grid": "#292a31",
    "major": "#3c3952",
    "brand": "#aaa7d4",
    "success": "#62c899",
    "danger": "#ff7669",
    "track": "#4a5149",
}


class Switch(tk.Canvas):
    def __init__(self, parent, variable, colors, command=None):
        super().__init__(
            parent,
            width=46,
            height=26,
            bg=colors["paper"],
            highlightthickness=0,
            cursor="hand2",
        )
        self.variable = variable
        self.colors = colors
        self.command = command
        self.bind("<Button-1>", self._toggle)
        self.variable.trace_add("write", lambda *_: self.draw())
        self.draw()

    def _toggle(self, _event=None):
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def draw(self):
        self.delete("all")
        on = bool(self.variable.get())
        track = self.colors["track"]
        self.create_oval(2, 3, 22, 23, fill=track, outline=track)
        self.create_oval(24, 3, 44, 23, fill=track, outline=track)
        self.create_rectangle(12, 3, 34, 23, fill=track, outline=track)
        cx = 34 if on else 12
        knob = self.colors["brand"]
        self.create_oval(cx - 9, 4, cx + 9, 22, fill=knob, outline="", width=0)


class Hub:
    NAV = [
        ("history", "History"),
        ("recovery", "Recovery"),
        ("dictionary", "Dictionary"),
        ("general", "General"),
        ("dictation", "Dictation"),
        ("audio", "Audio & mic"),
        ("appearance", "Appearance"),
        ("privacy", "Privacy"),
        ("files", "Files & meetings"),
        ("stats", "Statistics"),
    ]

    def __init__(self, root, app):
        self.app = app
        self.top = tk.Toplevel(root)
        self.top.title("Flow State - Hub")
        self.top.geometry("940x680")
        self.top.minsize(800, 560)
        self.top.protocol("WM_DELETE_WINDOW", self.top.withdraw)
        try:
            self.top.iconbitmap(app.ICON_FILE)
        except tk.TclError:
            pass
        self.current_page = "history"
        self.nav_rows = {}
        self._scroll_window = None
        self._grid_after = None
        self.history_records = []
        self.recovery_records = []
        self.recovery_badge = None
        self.dictionary_rules = []
        self.mic_map = {"System default": None}
        self._init_vars()
        self.colors = DARK if self.theme_var.get() == "dark" else LIGHT
        self._build_shell()
        self.show_page("history")

    def _init_vars(self):
        a = self.app
        self.autostart_var = tk.BooleanVar(value=a.get_autostart())
        self.open_hub_var = tk.BooleanVar(value=False)
        self.verbatim_var = tk.BooleanVar(value=bool(a.VERBATIM))
        self.polish_var = tk.BooleanVar(value=bool(a.POLISH))
        self.sound_var = tk.BooleanVar(value=bool(a.SOUND_CUES))
        self.save_audio_var = tk.BooleanVar(value=bool(a.SAVE_AUDIO))
        self.inject_var = tk.StringVar(value=a.INJECTION)
        self.engine_var = tk.StringVar(value=a.ENGINE)
        self.profile_var = tk.StringVar(value=a.PROFILE)
        self.auto_stop_var = tk.StringVar(value=str(a.AUTO_STOP))
        self.max_record_var = tk.StringVar(value=str(a.MAX_RECORD))
        self.fade_var = tk.StringVar(value=str(a.IDLE_FADE))
        self.retention_var = tk.StringVar(value=str(a.HISTORY_DAYS))
        self.hotkey_var = tk.StringVar(value=a.HOTKEY)
        self.continuous_hotkey_var = tk.StringVar(value=a.CONTINUOUS_HOTKEY)
        self.command_hotkey_var = tk.StringVar(value=a.COMMAND_HOTKEY)
        self.theme_var = tk.StringVar(value=a.THEME)
        self.mic_var = tk.StringVar(value="System default")

    def _build_shell(self):
        c = self.colors
        self.top.configure(bg=c["bg"])
        self.shell = tk.Frame(self.top, bg=c["paper"])
        self.shell.pack(fill="both", expand=True, padx=14, pady=14)
        self.sidebar = tk.Frame(self.shell, width=230, bg=c["paper2"])
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.content = tk.Frame(self.shell, bg=c["paper"])
        self.content.pack(side="left", fill="both", expand=True)

        brand = tk.Frame(self.sidebar, bg=c["paper2"])
        brand.pack(fill="x", padx=18, pady=(18, 24))
        tk.Label(
            brand,
            text="F",
            font=("Bodoni MT Black", 31, "bold"),
            fg=c["brand"],
            bg=c["paper2"],
            width=1,
        ).pack(side="left")
        name = tk.Frame(brand, bg=c["paper2"])
        name.pack(side="left", padx=(6, 0), pady=(2, 0))
        tk.Label(
            name, text="Flow State", font=("Georgia", 13, "bold"),
            fg=c["text"], bg=c["paper2"],
        ).pack(anchor="w", pady=(0, 2))
        tk.Label(
            name, text="LOCAL DICTATION", font=("Segoe UI Semibold", 8),
            fg=c["muted"], bg=c["paper2"],
        ).pack(anchor="w")

        for _index, (key, label) in enumerate(self.NAV):
            if key == "general":
                tk.Label(
                    self.sidebar, text="SETTINGS", font=("Segoe UI Semibold", 8),
                    fg=c["muted"], bg=c["paper2"],
                ).pack(fill="x", padx=18, pady=(14, 5))
            row = tk.Frame(self.sidebar, bg=c["paper2"], cursor="hand2")
            row.pack(fill="x", padx=9, pady=1)
            icon = self._nav_icon(row, key)
            icon.pack(side="left", padx=(9, 8), pady=7)
            text = tk.Label(
                row, text=label, font=("Segoe UI", 10), anchor="w",
                fg=c["text"], bg=c["paper2"], cursor="hand2",
            )
            text.pack(side="left", fill="x", expand=True, pady=7)
            widgets = [row, icon, text]
            if key == "recovery":
                self.recovery_badge = tk.Label(
                    row, text="", font=("Segoe UI Semibold", 8),
                    fg=c["paper"], bg=c["brand"], padx=6, pady=1,
                    cursor="hand2",
                )
                widgets.append(self.recovery_badge)
            for widget in widgets:
                widget.bind("<Button-1>", lambda _e, page=key: self.show_page(page))
            self.nav_rows[key] = (row, icon, text)
        self._update_recovery_badge()
        tk.Label(
            self.sidebar, text="Flow State | offline", font=("Segoe UI", 8),
            fg=c["muted"], bg=c["paper2"],
        ).pack(side="bottom", anchor="w", padx=18, pady=16)

        self.header = tk.Frame(self.content, bg=c["paper"], height=108)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)
        titles = tk.Frame(self.header, bg=c["paper"])
        titles.pack(side="left", padx=28, pady=(17, 13))
        self.eyebrow = tk.Label(
            titles, text="FLOW STATE", font=("Segoe UI Semibold", 8),
            fg=c["muted"], bg=c["paper"],
        )
        self.eyebrow.pack(anchor="w")
        self.title = tk.Label(
            titles, text="", font=("Georgia", 19, "bold"),
            fg=c["text"], bg=c["paper"],
        )
        self.title.pack(anchor="w", pady=(2, 4))
        status = tk.Frame(self.header, bg=c["paper"])
        status.pack(side="right", padx=28, pady=(0, 4))
        tk.Label(status, text="●", fg=c["success"], bg=c["paper"],
                 font=("Segoe UI", 9)).pack(side="left")
        self.status = tk.Label(
            status, text="Ready", fg=c["success"], bg=c["paper"],
            font=("Segoe UI Semibold", 9),
        )
        self.status.pack(side="left", padx=(5, 0))

        tk.Frame(self.content, bg=c["border"], height=1).pack(fill="x")
        self.page_canvas = tk.Canvas(
            self.content, bg=c["paper"], highlightthickness=0,
        )
        self.scrollbar = tk.Scrollbar(
            self.content, orient="vertical", command=self.page_canvas.yview,
        )
        self.page_canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.page_canvas.pack(fill="both", expand=True)
        self.page_canvas.bind("<Configure>", self._on_canvas_configure)
        self.page_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self.footer = tk.Frame(self.content, bg=c["paper"], height=58)
        self.footer.pack(fill="x", side="bottom")
        self.footer.pack_propagate(False)
        tk.Frame(self.footer, bg=c["border"], height=1).pack(fill="x")
        self.save_button = self._button(
            self.footer, "Save changes", self.save_settings, primary=True,
        )
        self.save_button.pack(side="right", padx=(8, 28), pady=11)
        self._button(self.footer, "Reset page", self.show_current).pack(
            side="right", pady=11
        )

    def _nav_icon(self, parent, key):
        c = self.colors
        icon = tk.Canvas(
            parent, width=18, height=18, bg=c["paper2"], highlightthickness=0,
        )
        color = c["muted"]
        if key == "history":
            icon.create_oval(3, 3, 15, 15, outline=color, width=1.5)
            icon.create_line(9, 5, 9, 9, 12, 11, fill=color, width=1.5)
        elif key == "recovery":
            icon.create_oval(2, 2, 16, 16, outline=color, width=1.5)
            icon.create_oval(6, 6, 12, 12, outline=color, width=1.2)
            icon.create_line(4, 4, 7, 7, 11, 11, 14, 14, fill=color, width=1.2)
            icon.create_line(14, 4, 11, 7, 7, 11, 4, 14, fill=color, width=1.2)
        elif key == "dictionary":
            icon.create_rectangle(2, 3, 8, 15, outline=color)
            icon.create_rectangle(10, 3, 16, 15, outline=color)
        elif key == "general":
            icon.create_oval(5, 5, 13, 13, outline=color, width=1.5)
            icon.create_line(9, 1, 9, 5, 9, 13, 9, 17, fill=color)
            icon.create_line(1, 9, 5, 9, 13, 9, 17, 9, fill=color)
        elif key == "dictation":
            icon.create_oval(6, 2, 12, 11, outline=color, width=1.5)
            icon.create_arc(
                3, 6, 15, 15, start=0, extent=-180,
                style=tk.ARC, outline=color,
            )
            icon.create_line(9, 14, 9, 17, fill=color)
        elif key == "audio":
            for x, height in ((3, 6), (6, 12), (9, 16), (12, 10), (15, 5)):
                icon.create_line(x, 9 - height / 2, x, 9 + height / 2, fill=color)
        elif key == "appearance":
            icon.create_oval(2, 2, 16, 16, outline=color)
            icon.create_oval(5, 5, 8, 8, fill=color, outline="")
            icon.create_oval(10, 4, 13, 7, fill=color, outline="")
        elif key == "privacy":
            icon.create_polygon(9, 2, 15, 5, 14, 12, 9, 16, 4, 12, 3, 5,
                                outline=color, fill="", width=1.5)
        elif key == "files":
            icon.create_rectangle(3, 5, 15, 15, outline=color)
            icon.create_line(3, 5, 7, 2, 11, 5, fill=color)
        else:
            icon.create_line(3, 15, 3, 10, 7, 10, 7, 5, 11, 5, 11, 12,
                             15, 12, 15, 2, fill=color, width=1.5)
        return icon

    def _on_canvas_configure(self, event):
        if self._scroll_window:
            self.page_canvas.itemconfigure(self._scroll_window, width=event.width)
        self._draw_grid(event.width, max(event.height, 1200))

    def _draw_grid(self, width, height):
        self.page_canvas.delete("grid")
        c = self.colors
        for x in range(16, int(width), 16):
            color = c["major"] if x % 80 == 0 else c["grid"]
            self.page_canvas.create_line(x, 0, x, height, fill=color, tags="grid")
        for y in range(16, int(height), 16):
            color = c["major"] if y % 80 == 0 else c["grid"]
            self.page_canvas.create_line(0, y, width, y, fill=color, tags="grid")
        self.page_canvas.tag_lower("grid")

    def _on_mousewheel(self, event):
        if self.top.winfo_viewable():
            self.page_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _clear_page(self):
        self.page_canvas.delete("all")
        self.page = tk.Frame(self.page_canvas, bg=self.colors["paper"])
        self._scroll_window = self.page_canvas.create_window(
            0, 0, anchor="nw", window=self.page,
        )
        self.page.bind(
            "<Configure>",
            lambda _e: self.page_canvas.configure(
                scrollregion=self.page_canvas.bbox("all")
            ),
        )
        for x in range(16, 880, 16):
            color = self.colors["major"] if x % 80 == 0 else self.colors["grid"]
            tk.Frame(self.page, bg=color, width=1).place(x=x, y=0, relheight=1)
        for y in range(16, 1500, 16):
            color = self.colors["major"] if y % 80 == 0 else self.colors["grid"]
            tk.Frame(self.page, bg=color, height=1).place(x=0, y=y, relwidth=1)

    def _section(self, title, note=""):
        c = self.colors
        section = tk.Frame(
            self.page, bg=c["paper"], highlightthickness=1,
            highlightbackground=c["border"],
        )
        section.pack(fill="x", padx=28, pady=(0, 16))
        tk.Label(
            section, text=title, font=("Segoe UI Semibold", 11),
            fg=c["text"], bg=c["paper"],
        ).pack(anchor="w", padx=16, pady=(15, 4 if note else 12))
        if note:
            tk.Label(
                section, text=note, font=("Segoe UI", 9),
                fg=c["muted"], bg=c["paper"], anchor="w", justify="left",
            ).pack(fill="x", padx=16, pady=(0, 8))
        return section

    def _row(self, section, title, help_text="", control_factory=None):
        c = self.colors
        row = tk.Frame(section, bg=c["paper"])
        row.pack(fill="x", padx=16, pady=8)
        copy = tk.Frame(row, bg=c["paper"])
        copy.pack(side="left", fill="x", expand=True)
        tk.Label(
            copy, text=title, font=("Segoe UI Semibold", 9),
            fg=c["text"], bg=c["paper"], anchor="w",
        ).pack(fill="x")
        if help_text:
            tk.Label(
                copy, text=help_text, font=("Segoe UI", 8),
                fg=c["muted"], bg=c["paper"], anchor="w", justify="left",
                wraplength=320,
            ).pack(fill="x", pady=(2, 0))
        if control_factory is not None:
            copy.pack_forget()
            host = tk.Frame(row, bg=c["paper"])
            control = control_factory(host)
            control.pack()
            host.pack(side="right", padx=(16, 0))
            copy.pack(side="left", fill="x", expand=True)
        return row

    def _entry(self, parent, variable, width=22):
        c = self.colors
        return tk.Entry(
            parent, textvariable=variable, width=width, font=("Segoe UI", 9),
            bg=c["paper2"], fg=c["text"], insertbackground=c["text"],
            relief="flat", highlightthickness=1,
            highlightbackground=c["border"], highlightcolor=c["brand"],
        )

    def _choice(self, parent, variable, choices, width=16):
        c = self.colors
        menu = tk.OptionMenu(parent, variable, *choices)
        menu.configure(
            width=width, anchor="w", font=("Segoe UI", 9), bg=c["paper2"],
            fg=c["text"], activebackground=c["border"], relief="flat",
            highlightthickness=1, highlightbackground=c["border"],
        )
        menu["menu"].configure(bg=c["paper"], fg=c["text"], font=("Segoe UI", 9))
        return menu

    def _button(self, parent, text, command, primary=False, danger=False):
        c = self.colors
        fg = c["paper"] if primary else c["danger"] if danger else c["text"]
        bg = c["brand"] if primary else c["paper2"]
        return tk.Button(
            parent, text=text, command=command, font=("Segoe UI Semibold", 9),
            fg=fg, bg=bg, activeforeground=fg, activebackground=bg,
            relief="flat", bd=0, padx=13, pady=7, cursor="hand2",
            highlightthickness=1, highlightbackground=c["border"],
        )

    def _intro(self, text):
        tk.Label(
            self.page, text=text, font=("Segoe UI", 10), fg=self.colors["muted"],
            bg=self.colors["paper"], anchor="w", justify="left", wraplength=650,
        ).pack(fill="x", padx=28, pady=(22, 18))

    def show(self):
        self.show_current()
        self.top.deiconify()
        self.top.lift()

    def show_current(self):
        self.show_page(self.current_page)

    def _update_recovery_badge(self, count=None):
        if count is None:
            try:
                count = len(self.app.RECOVERY.orphans())
            except (OSError, ValueError):
                count = 0
        if self.recovery_badge and self.recovery_badge.winfo_exists():
            if count:
                self.recovery_badge.configure(text=str(count))
                self.recovery_badge.pack(side="right", padx=(4, 9), pady=6)
            else:
                self.recovery_badge.pack_forget()

    def show_page(self, key):
        self.current_page = key
        for page, (row, icon, label) in self.nav_rows.items():
            active = page == key
            bg = self.colors["paper"] if active else self.colors["paper2"]
            fg = self.colors["brand"] if active else self.colors["text"]
            row.configure(bg=bg)
            icon.configure(bg=bg)
            label.configure(bg=bg, fg=fg, font=("Segoe UI Semibold" if active else "Segoe UI", 10))
        title = dict(self.NAV)[key]
        if key == "recovery":
            eyebrow = "LOCAL SAFETY"
        elif key in ("history", "dictionary"):
            eyebrow = "FLOW STATE"
        else:
            eyebrow = "SETTINGS"
        self.eyebrow.configure(text=eyebrow)
        self.title.configure(text=title)
        self.status.configure(text="Ready", fg=self.colors["success"])
        self._clear_page()
        renderer = getattr(self, "_page_" + key)
        renderer()
        self.page_canvas.yview_moveto(0)

    def _page_general(self):
        self._intro("Control how Flow State starts, listens, and inserts text.")
        section = self._section("Startup", "Keep Flow State ready without opening a full window.")
        self._row(section, "Start with Windows", "Launch quietly in the system tray.",
                  lambda host: Switch(host, self.autostart_var, self.colors))
        self._row(section, "Open Hub at startup", "Show this window after Flow State launches.",
                  lambda host: Switch(host, self.open_hub_var, self.colors))
        section = self._section("Shortcuts", "Click a field and type a keyboard combination.")
        self._row(section, "Hold or tap to dictate", "Release to finish, or tap for silence detection.",
                  lambda host: self._entry(host, self.hotkey_var))
        self._row(section, "Continuous dictation", "Keeps listening until pressed again.",
                  lambda host: self._entry(host, self.continuous_hotkey_var))
        self._row(section, "Selected-text command", "Select text, press once, speak, then press again.",
                  lambda host: self._entry(host, self.command_hotkey_var))
        section = self._section("Text insertion")
        self._row(section, "Insert using", "Paste is fastest; typing works in more apps.",
                  lambda host: self._choice(host, self.inject_var, ["paste", "type"]))

    def _page_dictation(self):
        self._intro("Choose recognition, cleanup, timing, and per-app writing behavior.")
        section = self._section("Processing")
        self._row(section, "Speech engine", "Moonshine is fast English; Whisper supports more languages.",
                  lambda host: self._choice(host, self.engine_var, ["moonshine", "whisper"]))
        self._row(section, "Polish", "Removes false starts, formats lists, and applies profiles.",
                  lambda host: Switch(host, self.polish_var, self.colors))
        self._row(section, "Verbatim", "Keep exact recognized words with no cleanup.",
                  lambda host: Switch(host, self.verbatim_var, self.colors))
        self._row(section, "Writing profile", "Auto follows the foreground app.",
                  lambda host: self._choice(
                      host, self.profile_var,
                      ["auto", "default", "messages", "email", "notes", "coding"],
                  ))
        section = self._section("Timing")
        self._row(section, "Silence before stopping", "Seconds after tap-to-dictate; 0 disables.",
                  lambda host: self._entry(host, self.auto_stop_var, 10))
        self._row(section, "Maximum recording", "Safety limit for hold/tap mode.",
                  lambda host: self._entry(host, self.max_record_var, 10))

    def _page_audio(self):
        self._intro("Choose and test the microphone Flow State listens to.")
        self.mic_map = {"System default": None}
        selected_label = "System default"
        for index, name in self.app.available_microphones():
            label = f"{name} [{index}]"
            self.mic_map[label] = index
            if index == self.app.MICROPHONE:
                selected_label = label
        self.mic_var.set(selected_label)
        section = self._section("Microphone")
        self._row(section, "Input device", "Flow State keeps this device when available.",
                  lambda host: self._choice(host, self.mic_var, list(self.mic_map), 34))

        def audio_controls(host):
            buttons = tk.Frame(host, bg=self.colors["paper"])
            self._button(buttons, "Test microphone", self.test_microphone).pack(side="left")
            self.meter = tk.Canvas(
                buttons, width=150, height=10, bg=self.colors["paper2"],
                highlightthickness=1, highlightbackground=self.colors["border"],
            )
            self.meter.pack(side="left", padx=(10, 0))
            return buttons

        self._row(
            section, "Input level", "A short local test; no audio is saved.",
            audio_controls,
        )
        self._row(section, "Sound cues", "Quiet start and stop chimes.",
                  lambda host: Switch(host, self.sound_var, self.colors))

    def test_microphone(self):
        device = self.mic_map.get(self.mic_var.get())
        self.flash("Listening for 1 second...")

        def work():
            try:
                audio = self.app.sd.rec(
                    int(self.app.SAMPLE_RATE),
                    samplerate=self.app.SAMPLE_RATE,
                    channels=1,
                    dtype="float32",
                    device=device,
                )
                self.app.sd.wait()
                level = min(1.0, float(np.sqrt(np.mean(audio ** 2))) * 12)
                self.top.after(0, lambda: self._show_meter(level))
            except Exception as exc:
                self.top.after(0, lambda: self.flash("Microphone test failed: " + str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _show_meter(self, level):
        if not getattr(self, "meter", None) or not self.meter.winfo_exists():
            return
        self.meter.delete("all")
        color = self.colors["success"] if level > 0.05 else self.colors["danger"]
        self.meter.create_rectangle(0, 0, int(150 * level), 10, fill=color, outline="")
        self.flash("Microphone heard you" if level > 0.05 else "No voice detected")

    def _page_appearance(self):
        self._intro("Keep the paper-and-ink identity while tuning the Hub and floating pill.")
        section = self._section("Hub")
        self._row(
            section, "Theme", "Light drafting paper or charcoal night paper.",
            lambda host: self._choice(host, self.theme_var, ["light", "dark"]),
        )
        section = self._section("Flow pill")
        self._row(section, "Fade when idle", "Seconds before the pill hides.",
                  lambda host: self._entry(host, self.fade_var, 10))
        tk.Label(
            section,
            text="The microphone badge is compact and centered inside the existing pill. "
                 "Its screen position and waveform geometry are unchanged.",
            font=("Segoe UI", 8), fg=self.colors["muted"], bg=self.colors["paper"],
            justify="left", wraplength=600,
        ).pack(anchor="w", padx=16, pady=(4, 12))
        section = self._section("App icon")
        self._row(
            section, "One icon everywhere",
            "Desktop shortcut, Hub title bar, and system tray use models/flow.ico.",
            lambda host: tk.Label(
                host, text="Waveform icon", fg=self.colors["brand"],
                bg=self.colors["paper"], font=("Segoe UI Semibold", 9),
            ),
        )

    def _page_privacy(self):
        self._intro("Flow State remains offline. These controls govern local files only.")
        section = self._section("Local history")
        self._row(section, "Save recording audio", "Enables playback and retry after a failure.",
                  lambda host: Switch(host, self.save_audio_var, self.colors))
        self._row(section, "Delete history after", "Days to retain local entries; 0 keeps forever.",
                  lambda host: self._entry(host, self.retention_var, 10))
        self._row(
            section, "Clear all history",
            "Permanently removes Flow State JSON history and owned recording WAVs.",
            lambda host: self._button(
                host, "Clear history...", self.clear_history, danger=True,
            ),
        )
        section = self._section("Network")
        self._row(
            section, "Offline processing",
            "Microphone audio, transcripts, profiles, and history stay on this computer.",
            lambda host: tk.Label(
                host, text="Enabled", fg=self.colors["success"],
                bg=self.colors["paper"], font=("Segoe UI Semibold", 9),
            ),
        )

    def clear_history(self):
        if not messagebox.askyesno(
            "Clear Flow State history",
            "Permanently remove all saved transcript history and owned recordings?",
            parent=self.top,
        ):
            return
        count = self.app.HISTORY.clear()
        self.flash(f"Removed {count} history item(s)")
        if self.current_page == "history":
            self.show_current()

    def _page_dictionary(self):
        self._intro("Recognition words improve casing; replacements expand exact spoken phrases.")
        section = self._section("Recognition vocabulary")
        vocab_path = Path(self.app.BASE_DIR) / "vocabulary.txt"
        vocabulary = []
        try:
            vocabulary = [
                line.strip() for line in vocab_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]
        except OSError:
            pass
        vocab_list = tk.Listbox(
            section, height=5, font=("Segoe UI", 9), bg=self.colors["paper2"],
            fg=self.colors["text"], relief="flat", highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        for word in vocabulary:
            vocab_list.insert("end", word)
        vocab_list.pack(fill="x", padx=16, pady=(4, 8))
        vocab_var = tk.StringVar()
        controls = tk.Frame(section, bg=self.colors["paper"])
        self._entry(controls, vocab_var, 26).pack(side="left")

        def save_vocab():
            word = vocab_var.get().strip()
            if not word:
                return
            items = [vocab_list.get(i) for i in range(vocab_list.size())]
            if word.lower() not in [x.lower() for x in items]:
                items.append(word)
            vocab_path.write_text(
                "# Recognition vocabulary, one exact word or phrase per line.\n"
                + "\n".join(items) + "\n",
                encoding="utf-8",
            )
            self.flash("Vocabulary saved")
            self.show_current()

        self._button(controls, "Add word", save_vocab, primary=True).pack(side="left", padx=8)
        controls.pack(fill="x", padx=16, pady=(0, 12))

        section = self._section("Replacements and snippets")
        self.dictionary_rules = self.app.read_rules(self.app.DICT.path)
        self.rule_list = tk.Listbox(
            section, height=8, font=("Segoe UI", 9), bg=self.colors["paper2"],
            fg=self.colors["text"], relief="flat", highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        for spoken, typed in self.dictionary_rules:
            self.rule_list.insert("end", f"{spoken}  ->  {typed}")
        self.rule_list.pack(fill="x", padx=16, pady=(4, 8))
        say_var, type_var = tk.StringVar(), tk.StringVar()
        controls = tk.Frame(section, bg=self.colors["paper"])
        self._entry(controls, say_var, 18).pack(side="left")
        tk.Label(controls, text="to", bg=self.colors["paper"], fg=self.colors["muted"]).pack(side="left", padx=6)
        self._entry(controls, type_var, 24).pack(side="left")

        def add_rule():
            spoken, typed = say_var.get().strip(), type_var.get().strip()
            if not spoken or not typed:
                self.flash("Fill in both replacement fields")
                return
            rules = [r for r in self.app.read_rules(self.app.DICT.path)
                     if r[0].lower() != spoken.lower()]
            rules.append((spoken, typed))
            self.app.write_rules(self.app.DICT.path, rules)
            self.flash("Replacement saved")
            self.show_current()

        def delete_rule():
            selection = self.rule_list.curselection()
            if not selection:
                self.flash("Select a replacement first")
                return
            victim = self.dictionary_rules[selection[0]]
            self.app.write_rules(
                self.app.DICT.path,
                [r for r in self.app.read_rules(self.app.DICT.path) if r != victim],
            )
            self.flash("Replacement removed")
            self.show_current()

        self._button(controls, "Add", add_rule, primary=True).pack(side="left", padx=7)
        self._button(controls, "Delete", delete_rule, danger=True).pack(side="left")
        controls.pack(fill="x", padx=16, pady=(0, 12))

    def _page_recovery(self):
        self._intro("Interrupted dictations stay here until you recover or remove them.")
        try:
            self.recovery_records = self.app.RECOVERY.orphans()
        except (OSError, ValueError) as exc:
            self.recovery_records = []
            section = self._section("Recovery could not be opened")
            tk.Label(
                section,
                text="Your files were left untouched. " + str(exc),
                font=("Segoe UI", 9), fg=self.colors["danger"],
                bg=self.colors["paper"], wraplength=580, justify="left",
            ).pack(anchor="w", padx=16, pady=(0, 14))
            self.status.configure(text="Recovery unavailable", fg=self.colors["danger"])
            return

        count = len(self.recovery_records)
        self._update_recovery_badge(count)
        self.status.configure(
            text=f"{count} recoverable" if count else "Ready",
            fg=self.colors["success"],
        )
        if not self.recovery_records:
            section = self._section("Nothing needs recovery")
            tk.Label(
                section,
                text="Interrupted dictations will appear here automatically. "
                     "Completed dictations remain in History.",
                font=("Segoe UI", 9), fg=self.colors["muted"],
                bg=self.colors["paper"], wraplength=580, justify="left",
            ).pack(anchor="w", padx=16, pady=(0, 14))
            return

        section = self._section(
            "Interrupted dictations",
            "Newest first. Recovery files stay on this PC and are never removed automatically.",
        )
        body = tk.Frame(section, bg=self.colors["paper"])
        body.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.recovery_list = tk.Listbox(
            body, width=31, height=15, font=("Segoe UI", 9),
            bg=self.colors["paper2"], fg=self.colors["text"], relief="flat",
            highlightthickness=1, highlightbackground=self.colors["border"],
            selectbackground=self.colors["major"], selectforeground=self.colors["text"],
            activestyle="none",
        )
        self.recovery_list.pack(side="left", fill="both", expand=True)
        for record in self.recovery_records:
            stamp = record.get("started", "").replace("T", " ")[5:16] or "Unknown time"
            profile = str(record.get("profile", "default")).replace("_", " ").title()
            segments = record.get("segments", 0)
            self.recovery_list.insert("end", f"{stamp}  {profile}  ({segments} segments)")

        right = tk.Frame(body, bg=self.colors["paper"])
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        tk.Label(
            right, text="RECOVERED TEXT", font=("Segoe UI Semibold", 8),
            fg=self.colors["muted"], bg=self.colors["paper"],
        ).pack(anchor="w", pady=(0, 5))
        self.recovery_text = tk.Text(
            right, width=39, height=11, wrap="word", font=("Segoe UI", 9),
            bg=self.colors["paper2"], fg=self.colors["text"], relief="flat",
            highlightthickness=1, highlightbackground=self.colors["border"],
            padx=9, pady=9,
        )
        self.recovery_text.pack(fill="both", expand=True)
        self.recovery_text.configure(state="disabled")
        self.recovery_meta = tk.Label(
            right, text="", font=("Segoe UI", 8), fg=self.colors["muted"],
            bg=self.colors["paper"], anchor="w",
        )
        self.recovery_meta.pack(fill="x", pady=(7, 0))
        buttons = tk.Frame(right, bg=self.colors["paper"])
        buttons.pack(fill="x", pady=(8, 0))
        self._button(buttons, "Copy text", self.copy_recovery).pack(side="left", padx=(0, 6))
        self._button(
            buttons, "Retry delivery", self.retry_recovery, primary=True,
        ).pack(side="left", padx=(0, 6))
        self._button(
            buttons, "Remove...", self.delete_recovery, danger=True,
        ).pack(side="left")
        self.recovery_list.bind("<<ListboxSelect>>", self.select_recovery)
        self.recovery_list.selection_set(0)
        self.select_recovery()

    def _selected_recovery(self):
        selection = self.recovery_list.curselection() if hasattr(self, "recovery_list") else ()
        return self.recovery_records[selection[0]] if selection else None

    def select_recovery(self, _event=None):
        record = self._selected_recovery()
        if not record:
            return
        text = record.get("text", "") or "No recognized text was saved."
        self.recovery_text.configure(state="normal")
        self.recovery_text.delete("1.0", "end")
        self.recovery_text.insert("1.0", text)
        self.recovery_text.configure(state="disabled")
        started = record.get("started", "").replace("T", " ") or "Unknown time"
        profile = str(record.get("profile", "default")).replace("_", " ").title()
        self.recovery_meta.configure(
            text=f"{record.get('segments', 0)} saved segments  |  {profile}  |  {started}"
        )

    def copy_recovery(self):
        record = self._selected_recovery()
        if record and record.get("text"):
            pyperclip.copy(record["text"])
            self.flash("Recovered text copied")

    def retry_recovery(self):
        record = self._selected_recovery()
        if not record or not record.get("text"):
            self.flash("No recovered text to deliver")
            return
        if not messagebox.askyesno(
            "Retry recovered text",
            "Flow State will hide the Hub and send this text to the app behind it. Continue?",
            parent=self.top,
        ):
            return
        self.top.withdraw()
        self.status.configure(text="Retrying delivery...", fg=self.colors["brand"])

        def work():
            try:
                result = self.app.deliver_text(
                    record["text"], trailing_space=False,
                    original=record["text"], profile=record.get("profile", "default"),
                    source="recovery",
                )
                if result and self.app.RECOVERY.complete(record["id"]):
                    message = "Recovered text delivered"
                elif result:
                    message = "Delivered; recovery copy kept"
                else:
                    message = "Delivered; recovery kept because history was not saved"
            except Exception as exc:
                message = "Delivery failed; recovery kept: " + str(exc)
            self.top.after(0, lambda: (self.show(), self.flash(message)))

        self.top.after(
            180,
            lambda: threading.Thread(target=work, daemon=True).start(),
        )

    def delete_recovery(self):
        record = self._selected_recovery()
        if not record:
            return
        if not messagebox.askyesno(
            "Remove recovered dictation",
            "Permanently remove this recovered text? This cannot be undone.",
            parent=self.top,
        ):
            return
        if self.app.RECOVERY.complete(record["id"]):
            self.flash("Recovered dictation removed")
            self.show_current()
        else:
            self.flash("Recovery file was already unavailable")

    def _page_history(self):
        self._intro("Search, copy, play, retry, or remove saved dictations.")
        section = self._section("Recent dictations")
        search_var = tk.StringVar()
        search = self._entry(section, search_var, 34)
        search.pack(anchor="w", padx=16, pady=(3, 8))
        body = tk.Frame(section, bg=self.colors["paper"])
        body.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.history_list = tk.Listbox(
            body, width=38, height=15, font=("Segoe UI", 9),
            bg=self.colors["paper2"], fg=self.colors["text"], relief="flat",
            highlightthickness=1, highlightbackground=self.colors["border"],
            selectbackground=self.colors["border"], selectforeground=self.colors["text"],
        )
        self.history_list.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=self.colors["paper"])
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.history_text = tk.Text(
            right, width=38, height=11, wrap="word", font=("Segoe UI", 9),
            bg=self.colors["paper2"], fg=self.colors["text"], relief="flat",
            highlightthickness=1, highlightbackground=self.colors["border"],
        )
        self.history_text.pack(fill="both", expand=True)
        buttons = tk.Frame(right, bg=self.colors["paper"])
        buttons.pack(fill="x", pady=(8, 0))
        for label, command, danger in (
            ("Copy", self.copy_history, False),
            ("Play", self.play_history, False),
            ("Retry", self.retry_history, False),
            ("Delete", self.delete_history, True),
        ):
            self._button(buttons, label, command, danger=danger).pack(side="left", padx=(0, 6))

        def refresh(*_):
            query = search_var.get().lower()
            self.history_records = [
                r for r in self.app.HISTORY.read()
                if query in r.get("final", "").lower()
                or query in r.get("timestamp", "").lower()
            ]
            self.history_list.delete(0, "end")
            for record in self.history_records:
                stamp = record.get("timestamp", "").replace("T", " ")[5:16]
                text = " ".join(record.get("final", "").split())
                self.history_list.insert("end", f"{stamp}  {text[:55]}")
            self.history_text.delete("1.0", "end")

        search_var.trace_add("write", refresh)
        self.history_list.bind("<<ListboxSelect>>", self.select_history)
        refresh()

    def _selected_history(self):
        selection = self.history_list.curselection() if hasattr(self, "history_list") else ()
        return self.history_records[selection[0]] if selection else None

    def select_history(self, _event=None):
        record = self._selected_history()
        if not record:
            return
        details = (
            f"{record.get('final', '')}\n\n"
            f"Original: {record.get('original', '')}\n\n"
            f"Profile: {record.get('profile', 'default')}  |  "
            f"Duration: {record.get('duration', 0):.1f}s  |  "
            f"Work: {record.get('latency', 0):.1f}s\n"
            f"Engine: {record.get('engine', '')}\n"
            f"Source: {record.get('source', 'dictation')}"
        )
        self.history_text.delete("1.0", "end")
        self.history_text.insert("1.0", details)

    def copy_history(self):
        record = self._selected_history()
        if record:
            pyperclip.copy(record.get("final", ""))
            self.flash("Copied")

    def play_history(self):
        record = self._selected_history()
        path = record.get("audio_path", "") if record else ""
        if not path or not os.path.exists(path):
            self.flash("No saved audio for this item")
            return
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)

    def retry_history(self):
        record = self._selected_history()
        path = record.get("audio_path", "") if record else ""
        if not path or not os.path.exists(path):
            self.flash("No saved audio to retry")
            return
        self.flash("Retrying transcription...")

        def work():
            try:
                result = self.app.transcribe_wav_path(path, "retry")
                message = "Retry saved" if result else "Retry heard nothing"
            except Exception as exc:
                message = "Retry failed: " + str(exc)
            self.top.after(0, lambda: (self.flash(message), self.show_current()))

        threading.Thread(target=work, daemon=True).start()

    def delete_history(self):
        record = self._selected_history()
        if not record:
            return
        if self.app.HISTORY.delete(record["id"]):
            self.flash("History item removed")
            self.show_current()

    def _page_files(self):
        self._intro("Bring in recordings and see which advanced capture features are available locally.")
        section = self._section("Audio files", "16-bit PCM WAV files are transcribed with the active local engine.")
        self._row(
            section, "Transcribe a WAV file",
            "The transcript and source audio are added to recoverable history.",
            lambda host: self._button(
                host, "Choose WAV...", self.choose_wav, primary=True,
            ),
        )
        section = self._section("Meetings")
        self._row(
            section, "Microphone meetings",
            "Use Continuous dictation with the Notes profile for long local capture.",
            lambda host: tk.Label(
                host, text="Available", fg=self.colors["success"],
                bg=self.colors["paper"], font=("Segoe UI Semibold", 9),
            ),
        )
        self._row(
            section, "System audio",
            "Choose Realtek Stereo Mix under Audio & mic to capture computer playback.",
            lambda host: tk.Label(
                host, text="Available via Stereo Mix", fg=self.colors["success"],
                bg=self.colors["paper"], font=("Segoe UI Semibold", 9),
            ),
        )
        self._row(
            section, "Speaker separation",
            "Unavailable: no local speaker-identification model is installed.",
            lambda host: tk.Label(
                host, text="Unavailable", fg=self.colors["muted"],
                bg=self.colors["paper"], font=("Segoe UI Semibold", 9),
            ),
        )

    def choose_wav(self):
        path = filedialog.askopenfilename(
            parent=self.top,
            title="Transcribe WAV file",
            filetypes=[("WAV audio", "*.wav")],
        )
        if not path:
            return
        self.flash("Transcribing file...")

        def work():
            try:
                result = self.app.transcribe_wav_path(path)
                message = "File transcript saved" if result else "No speech found"
            except Exception as exc:
                message = "File failed: " + str(exc)
            self.top.after(0, lambda: self.flash(message))

        threading.Thread(target=work, daemon=True).start()

    def _page_stats(self):
        self._intro("A private summary calculated from local history.")
        stats = self.app.HISTORY.stats()
        section = self._section("All time")
        for title, value in (
            ("Dictations", stats["dictations"]),
            ("Words", stats["words"]),
            ("Minutes spoken", stats["minutes"]),
            ("Average processing time", f"{stats['average_latency']:.2f} seconds"),
            ("Most-used profile", stats["top_profile"].title()),
        ):
            self._row(
                section, title, "",
                lambda host, value=value: tk.Label(
                    host, text=str(value), fg=self.colors["brand"],
                    bg=self.colors["paper"], font=("Georgia", 14, "bold"),
                ),
            )

    def save_settings(self):
        try:
            auto_stop = max(0.0, float(self.auto_stop_var.get()))
            max_record = max(5, int(float(self.max_record_var.get())))
            fade = max(5, int(float(self.fade_var.get())))
            retention = max(0, int(float(self.retention_var.get())))
        except ValueError:
            self.flash("Use numbers in timing and retention fields")
            return
        data = {
            "HOTKEY": self.hotkey_var.get().strip().lower() or "ctrl+windows",
            "CONTINUOUS_HOTKEY": self.continuous_hotkey_var.get().strip().lower()
            or "ctrl+windows+space",
            "COMMAND_HOTKEY": self.command_hotkey_var.get().strip().lower()
            or "ctrl+windows+alt",
            "ENGINE": self.engine_var.get(),
            "INJECTION": self.inject_var.get(),
            "VERBATIM": bool(self.verbatim_var.get()),
            "POLISH": bool(self.polish_var.get()),
            "PROFILE": self.profile_var.get(),
            "MICROPHONE": self.mic_map.get(self.mic_var.get()),
            "SOUND_CUES": bool(self.sound_var.get()),
            "SAVE_AUDIO": bool(self.save_audio_var.get()),
            "AUTO_STOP": auto_stop,
            "MAX_RECORD": max_record,
            "IDLE_FADE": fade,
            "HISTORY_DAYS": retention,
            "THEME": self.theme_var.get(),
            "OPEN_HUB": bool(self.open_hub_var.get()),
        }
        self.app.save_settings(data)
        self.app.set_autostart(bool(self.autostart_var.get()))
        if retention:
            self.app.HISTORY.prune(retention)
        theme_changed = self.colors is not (DARK if self.theme_var.get() == "dark" else LIGHT)
        self.flash("Saved; restart applies engine, microphone, and shortcuts")
        if theme_changed:
            self.colors = DARK if self.theme_var.get() == "dark" else LIGHT
            self.top.after(350, self._rebuild_for_theme)

    def _rebuild_for_theme(self):
        for child in self.top.winfo_children():
            child.destroy()
        self.nav_rows = {}
        self._build_shell()
        self.show_current()

    def flash(self, message):
        self.status.configure(text=message, fg=self.colors["brand"])
        self.top.after(
            2600,
            lambda: self.status.configure(text="Ready", fg=self.colors["success"])
            if self.status.winfo_exists() else None,
        )
