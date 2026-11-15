# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.trapyze]
# name = "{name}"
# description = "{description}"
# icon = "cube"
# color = "rose"
# version = "0.1.0"
# ///
"""{name}: a small program with its own window.

A starting point made by traPYze, using tkinter (it comes with Python). traPYze
starts it when you click the tile; closing the window ends the run.
"""

import time
import tkinter as tk
from tkinter import ttk

root = tk.Tk()
root.title("{name}")
root.geometry("360x200")
frame = ttk.Frame(root, padding=24)
frame.pack(fill="both", expand=True)

clock = ttk.Label(frame, font=("Segoe UI", 28))
clock.pack(pady=(0, 16))
count = tk.IntVar(value=0)
ttk.Button(frame, text="Click me", command=lambda: count.set(count.get() + 1)).pack()
ttk.Label(frame, textvariable=count).pack(pady=8)


def tick():
    clock.config(text=time.strftime("%H:%M:%S"))
    root.after(500, tick)


tick()
root.mainloop()
