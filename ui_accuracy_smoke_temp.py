import time
import tkinter as tk
from pathlib import Path
from PIL import ImageGrab

import flow
from flow_hub import Hub

root = tk.Tk()
root.withdraw()
hub = Hub(root, flow)
hub.show_page("accuracy")
hub.top.geometry("940x680+120+80")
hub.top.deiconify()
hub.top.attributes("-topmost", True)
hub.top.lift()
hub.top.focus_force()
root.update()
time.sleep(0.5)
root.update()
x = hub.top.winfo_rootx()
y = hub.top.winfo_rooty()
w = hub.top.winfo_width()
h = hub.top.winfo_height()
ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(
    Path(r"C:\Users\Kariim\AppData\Local\Temp\flow-state-accuracy-native.png")
)
root.destroy()