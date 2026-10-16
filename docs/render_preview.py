"""从本项目自己的 Tk 控件布局生成文档示意图，不截图桌面或账户。需要 Pillow。"""
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from PIL import Image, ImageDraw, ImageFont
from app import App, BG, INK, MUTED, BLUE


def main():
    app = App(demo=True)
    deadline = time.monotonic() + 5
    while app.busy and time.monotonic() < deadline:
        app.update()
        time.sleep(0.02)
    app.tree.selection_set("0")
    app.selected()
    app.update()
    width, height = app.winfo_width(), app.winfo_height()
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    font_dir = Path("C:/Windows/Fonts")
    origin_x, origin_y = app.winfo_rootx(), app.winfo_rooty()

    def font(size=13, bold=False):
        return ImageFont.truetype(str(font_dir / ("msyhbd.ttc" if bold else "msyh.ttc")), size)

    def font_info(value):
        actual=tkfont.Font(font=value)
        size=int(actual.cget("size"))
        pixels=-size if size<0 else round(size*float(app.tk.call("tk","scaling")))
        return pixels,actual.actual()["weight"]=="bold"

    def text_box(bounds, text, color=INK, size=13, bold=False, padding=2, wrap=True):
        x, y, w, h = bounds
        f = font(size, bold)
        lines = []
        for paragraph in str(text).split("\n"):
            line = ""
            for character in paragraph:
                if wrap and line and draw.textlength(line + character, font=f) > w - padding * 2:
                    lines.append(line)
                    line = character
                else:
                    line += character
            lines.append(line)
        line_height = size + 5
        top = y + max(0, (h - len(lines) * line_height) // 2)
        for index, line in enumerate(lines):
            draw.text((x + padding, top + index * line_height), line, font=f, fill=color)

    def render(widget):
        if not widget.winfo_ismapped():
            return
        x, y = widget.winfo_rootx() - origin_x, widget.winfo_rooty() - origin_y
        w, h = widget.winfo_width(), widget.winfo_height()
        bounds = (x, y, w, h)
        kind = widget.winfo_class()
        if kind in {"Frame", "Canvas", "Label", "Button", "Text"}:
            draw.rectangle((x, y, x + w, y + h), fill=widget.cget("bg"))
            if kind == "Frame" and int(widget.cget("highlightthickness")):
                draw.rectangle((x, y, x + w - 1, y + h - 1), outline=widget.cget("highlightbackground"))
        if kind == "Canvas":
            for item in widget.find_all():
                item_kind=widget.type(item)
                coords=widget.coords(item)
                if item_kind=="polygon":
                    xx=coords[::2]; yy=coords[1::2]
                    fill=widget.itemcget(item,"fill") or BG
                    outline=widget.itemcget(item,"outline") or fill
                    if len(coords)>=20:
                        draw.rounded_rectangle((x+min(xx),y+min(yy),x+max(xx),y+max(yy)),
                                               radius=round(2*app.ui_scale),fill=fill,outline=outline,
                                               width=max(1,round(float(widget.itemcget(item,"width")))))
                    else:
                        draw.polygon([(x+coords[i],y+coords[i+1]) for i in range(0,len(coords),2)],fill=fill)
                elif item_kind=="text":
                    size,bold=font_info(widget.itemcget(item,"font"))
                    anchor={"center":"mm","w":"lm","e":"rm","nw":"lt","n":"mt","ne":"rt"}.get(widget.itemcget(item,"anchor"),"mm")
                    draw.text((x+coords[0],y+coords[1]),widget.itemcget(item,"text"),font=font(size,bold),
                              fill=widget.itemcget(item,"fill"),anchor=anchor)
                elif item_kind=="oval":
                    fill=widget.itemcget(item,"fill") or None
                    outline=widget.itemcget(item,"outline") or None
                    draw.ellipse((x+coords[0],y+coords[1],x+coords[2],y+coords[3]),fill=fill,outline=outline,
                                 width=max(1,round(float(widget.itemcget(item,"width")))))
                elif item_kind=="line":
                    draw.line([(x+coords[i],y+coords[i+1]) for i in range(0,len(coords),2)],
                              fill=widget.itemcget(item,"fill"),width=max(1,round(float(widget.itemcget(item,"width")))))
                elif item_kind=="arc":
                    start=float(widget.itemcget(item,"start")); extent=float(widget.itemcget(item,"extent"))
                    draw.arc((x+coords[0],y+coords[1],x+coords[2],y+coords[3]),start=-(start+extent),end=-start,
                             fill=widget.itemcget(item,"outline"),width=max(1,round(float(widget.itemcget(item,"width")))))
        if kind in {"Label", "Button"}:
            if kind == "Label" and widget.cget("image"):
                asset = Image.open(widget.asset_path).convert("RGBA")
                image.paste(asset, (x, y), asset)
                return
            size,bold=font_info(widget.cget("font"))
            value = widget.cget("text")
            variable = widget.cget("textvariable") if kind == "Label" else ""
            if variable:
                value = widget.getvar(variable)
            wrap = kind == "Label" and float(widget.cget("wraplength")) > 0
            text_box(bounds, value, widget.cget("fg"), size, bold, wrap=wrap)
        elif kind == "Entry":
            value=widget.get()
            if widget.cget("show"):
                value=widget.cget("show")*len(value)
            size,bold=font_info(widget.cget("font"))
            text_box(bounds,value,INK,size,bold,wrap=False)
        elif kind in {"TButton", "TEntry", "TCombobox"}:
            primary = kind == "TButton" and widget.cget("style") == "Primary.TButton"
            disabled = widget.instate(["disabled"])
            fill = ("#eae8f0" if disabled else BLUE) if primary else "white"
            draw.rounded_rectangle((x, y, x + w - 1, y + h - 1), radius=5, fill=fill,
                                   outline=fill if kind == "TButton" else "#dedbe5")
            value = widget.cget("text") if kind == "TButton" else widget.get()
            text_box((x + 8, y, w - 16, h), value, "#8f9bb4" if disabled else ("white" if primary else INK), padding=0)
            if kind == "TCombobox":
                draw.polygon([(x+w-18, y+h//2-2), (x+w-10, y+h//2-2), (x+w-14, y+h//2+3)], fill=MUTED)
        elif kind in {"TCheckbutton", "Checkbutton"}:
            draw.rectangle((x + 2, y + h//2 - 6, x + 14, y + h//2 + 6), fill="white", outline="#b5c0d1")
            if kind == "Checkbutton" and widget.getvar(widget.cget("variable")):
                draw.line([(x+4,y+h//2),(x+7,y+h//2+3),(x+12,y+h//2-3)],fill=BLUE,width=2)
            size = font_info(widget.cget("font"))[0] if kind == "Checkbutton" else 12
            text_box((x + 20, y, w - 20, h), widget.cget("text"), MUTED, size=size, wrap=False)
        elif kind == "Treeview":
            draw.rectangle((x, y, x+w, y+h), fill="white")
            rowheight=int(ttk.Style(app).lookup("Treeview","rowheight"))
            header_height=widget.winfo_reqheight()-int(widget.cget("height"))*rowheight-2
            draw.rectangle((x, y, x+w, y+header_height), fill="#f6f8fc")
            xx = x
            for column in widget["columns"]:
                column_width = widget.column(column, "width")
                text_box((xx + 7, y, column_width - 14, header_height), widget.heading(column, "text"), MUTED, size=app.px(13))
                xx += column_width
            for iid in widget.get_children():
                for column in widget["columns"]:
                    bbox = widget.bbox(iid, column)
                    if not bbox:
                        continue
                    bx, by, bw, bh = bbox
                    selected = iid in widget.selection()
                    draw.rectangle((x+bx, y+by, x+bx+bw, y+by+bh), fill="#e8eeff" if selected else "white")
                    text_box((x+bx+7, y+by, bw-14, bh), widget.set(iid, column), BLUE if selected else INK, size=app.px(14), wrap=False)
        elif kind == "TProgressbar":
            draw.rounded_rectangle((x, y, x+w, y+h), radius=2, fill="#e8edf6")
        elif kind == "TScrollbar":
            draw.rectangle((x, y, x+w, y+h), fill="#edf1f7")
        elif kind == "Text":
            lines = widget.get("1.0", "end").strip().splitlines()[-2:]
            text_box((x+10, y, w-20, h), "\n".join(lines), "#4c607d", size=12, wrap=False)
        for child in widget.winfo_children():
            render(child)

    for child in app.winfo_children():
        render(child)
    target = Path(__file__).with_name("preview.png")
    image.save(target)
    app.close()
    print(target)


if __name__ == "__main__":
    main()
