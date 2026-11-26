# Screenshotting a running GUI on X11 (Linux)

Goal: capture a **specific Tk window** (not the whole root) to a PNG so you can inspect the populated UI.

## What works
```bash
# In the app:  wid = str(app.root.winfo_id())
DISPLAY=:0 import -display :0 -window <wid> png:/abs/path/out.png
```
ImageMagick 7 `import` with a **specific numeric window id** and an explicit `png:` output prefix succeeds.

## What fails (don't waste time on these)
| Method | Result |
|---|---|
| `import -window root out.png` | `import: missing an image filename` (exit 1) — IM7 mis-parses `root` + the filename |
| `import -window 0 out.png` | hangs until `timeout` kills it (exit 124) |
| PIL `ImageGrab.grab(xdisplay=':0')` | `OSError: X get_image failed: error 8` — the classic X11 root-window GetImage failure |

## Drive the GUI to a known state, then capture
Do it all in one process so the window id stays valid:
1. Construct the app; set the input fields via their StringVars (`app.var_first.set("...")`).
2. Trigger the action by calling the **real** handler (`app._start_search()`), not a reimplementation.
3. Wait on the main loop: `app.root.after(9000, on_results)`; schedule follow-ups the same way (e.g. select the first result row and call the detail handler).
4. In the final callback, take the screenshot (`import -display :0 -window <wid> png:out.png`), then `app.root.destroy()`.
5. `app.root.mainloop()` blocks until `destroy()`.

Keep the window mapped for the whole wait; the id is valid for the window's lifetime. Clean up any scratch PNGs afterward.
