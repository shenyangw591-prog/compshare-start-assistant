"""本地 Tk 控件：统一圆角按钮与输入框，无第三方运行依赖。"""
import tkinter as tk
import tkinter.font as tkfont


def rounded(canvas, x1, y1, x2, y2, radius, **kwargs):
    radius = min(radius, (x2-x1)/2, (y2-y1)/2)
    points = [x1+radius,y1, x2-radius,y1, x2,y1, x2,y1+radius,
              x2,y2-radius, x2,y2, x2-radius,y2, x1+radius,y2,
              x1,y2, x1,y2-radius, x1,y1+radius, x1,y1]
    return canvas.create_polygon(points, smooth=True, splinesteps=20, **kwargs)


class Button(tk.Canvas):
    def __init__(self, parent, text, command, font, width=120, height=42,
                 primary=False, quiet=False, state="normal", scale=1,
                 outlined=False, icon=None):
        self._text, self._command, self._state = text, command, state
        self._font, self._primary, self._quiet = font, primary, quiet
        self._hover, self._focus, self._scale = False, False, scale
        self._outlined, self._icon = outlined, icon
        super().__init__(parent, width=round(width*scale), height=round(height*scale),
                         bg=parent.cget("bg"), highlightthickness=0, borderwidth=0, takefocus=1)
        self.bind("<Configure>", lambda event: self._draw())
        self.bind("<Enter>", lambda event: self._set_hover(True))
        self.bind("<Leave>", lambda event: self._set_hover(False))
        self.bind("<FocusIn>", lambda event: self._set_focus(True))
        self.bind("<FocusOut>", lambda event: self._set_focus(False))
        self.bind("<Button-1>", self._activate)
        self.bind("<space>", self._activate)
        self.bind("<Return>", self._activate)

    def _set_hover(self, hover):
        self._hover = hover
        self._draw()

    def _set_focus(self, focus):
        self._focus = focus
        self._draw()

    def _activate(self, event=None):
        if self._state != "disabled":
            self.focus_set()
            self._command()
        return "break"

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        disabled = self._state == "disabled"
        if self._primary:
            fill = "#eae8f0" if disabled else ("#4022da" if self._hover else "#5030f5")
            foreground = "#aaa5b6" if disabled else "white"
        elif self._quiet:
            fill = "#f7f5ff" if self._hover and not disabled else self.cget("bg")
            foreground = "#aba7b3" if disabled else "#3b3745"
        elif self._outlined:
            fill = "#f7f5ff" if self._hover and not disabled else "white"
            foreground = "#b2aebc" if disabled else "#5030f5"
        else:
            fill = "#f1f0f5" if disabled else ("#eeebf7" if self._hover else "#f5f3fa")
            foreground = "#ada8b9" if disabled else "#4e475d"
        outline = "#5030f5" if self._outlined and not disabled else fill
        if self._focus and not disabled:
            outline = "#a799ff"
        rounded(self, 1, 1, max(2,w-1), max(2,h-1), 2*self._scale, fill=fill,
                outline=outline, width=max(1, round(self._scale)))
        if self._icon == "eye":
            x,y,r=w/2,h/2,7*self._scale
            self.create_oval(x-r,y-r*.6,x+r,y+r*.6,outline=foreground,width=max(1,self._scale))
            self.create_oval(x-r*.3,y-r*.3,x+r*.3,y+r*.3,fill=foreground,outline="")
        else:
            self.create_text(w/2, h/2, text=self._text, fill=foreground, font=self._font)
        super().configure(cursor="arrow" if disabled else "hand2", takefocus=0 if disabled else 1)

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        redraw = False
        for key, attribute in (("text", "_text"), ("state", "_state"), ("command", "_command")):
            if key in kwargs:
                setattr(self, attribute, kwargs.pop(key))
                redraw = True
        if kwargs:
            super().configure(**kwargs)
        if redraw:
            self._draw()

    config = configure

    def instate(self, states):
        return all((self._state == "disabled") == (state == "disabled") for state in states)

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "state":
            return self._state
        return super().cget(key)


class Input(tk.Canvas):
    def __init__(self, parent, variable, font, scale=1, secret=False, on_reveal=None):
        self.scale = scale
        super().__init__(parent, width=round(250*scale), height=round(44*scale), bg=parent.cget("bg"),
                         highlightthickness=0, borderwidth=0)
        self.entry = tk.Entry(self, textvariable=variable, font=font, relief="flat",
                              bg="white", fg="#17141d", insertbackground="#5030f5",
                              borderwidth=0, highlightthickness=0, show="●" if secret else "",
                              disabledbackground="white", disabledforeground="#9993a5")
        self.window = self.create_window(round(13*scale), round(22*scale),
                                         anchor="w", window=self.entry)
        self.reveal_button = None
        if on_reveal:
            self.reveal_button = Button(self, "显示密钥", on_reveal, font, width=34, height=30,
                                        quiet=True, scale=scale, icon="eye")
            self.reveal_window = self.create_window(0, 0, anchor="e", window=self.reveal_button)
        self.bind("<Configure>", self._resize)
        self.entry.bind("<FocusIn>", lambda event: self._resize())
        self.entry.bind("<FocusOut>", lambda event: self._resize())

    def _resize(self, event=None):
        width, height = self.winfo_width(), self.winfo_height()
        self.delete("surface")
        rounded(self, 1, 1, max(2,width-1), max(2,height-1), 1*self.scale,
                fill="white", outline="#7962fa" if self.entry.focus_get() == self.entry else "#dedbe5",
                width=1, tags="surface")
        self.tag_lower("surface")
        self.coords(self.window, round(13*self.scale), height/2)
        right_padding = 48 if self.reveal_button else 26
        self.itemconfigure(self.window, width=max(1,width-round(right_padding*self.scale)), height=round(25*self.scale))
        if self.reveal_button:
            self.coords(self.reveal_window, width-round(5*self.scale), height/2)


class Progress(tk.Canvas):
    def __init__(self,parent,scale=1):
        self._timer=None
        self._phase=0
        super().__init__(parent,height=max(3,round(4*scale)),width=round(200*scale),
                         bg=parent.cget("bg"),highlightthickness=0,borderwidth=0)
        self.bind("<Configure>",lambda event:self._draw())

    def _draw(self):
        self.delete("all")
        width,height=self.winfo_width(),self.winfo_height()
        rounded(self,0,0,width,height,height/2,fill="#efedf5",outline="")
        if self._timer is not None:
            length=width*.28
            left=(self._phase%1)*(width+length)-length
            right=min(width,left+length)
            if right>max(0,left):
                rounded(self,max(0,left),0,right,height,height/2,fill="#5030f5",outline="")

    def _advance(self):
        self._phase+=.012
        self._timer=self.after(25,self._advance)
        self._draw()

    def start(self,interval=25):
        self.stop()
        self._advance()

    def stop(self):
        if self._timer is not None:
            self.after_cancel(self._timer)
            self._timer=None
        self._draw()

    def configure(self,cnf=None,**kwargs):
        if cnf:
            kwargs.update(cnf)
        kwargs.pop("value",None)
        if kwargs:
            return super().configure(**kwargs)

    config=configure


class InstanceList(tk.Canvas):
    """可滚动、可键盘选择的实例行；只保存用于展示的字段。"""
    columns = ("name", "gpu", "state", "zone")
    display_columns = ("name", "gpu", "zone", "state")

    def __init__(self, parent, scale=1):
        self.scale = scale
        self.rows = {}
        self.selected_id = None
        self.disabled = False
        self.headings = {"name":"实例名称", "gpu":"GPU", "zone":"所在地域", "state":"状态"}
        self.widths = {key:100 for key in self.columns}
        self.header_height = round(34*scale)
        self.row_height = round(68*scale)
        self.gap = round(10*scale)
        self.text_font = ("Microsoft YaHei UI", -round(14*scale))
        self.name_font = ("Microsoft YaHei UI", -round(15*scale), "bold")
        self.header_font = ("Microsoft YaHei UI", -round(13*scale))
        self._measure_font = tkfont.Font(font=self.text_font)
        self._measure_name = tkfont.Font(font=self.name_font)
        super().__init__(parent, bg="white", highlightthickness=0, borderwidth=0,
                         width=1, height=round(210*scale), takefocus=1,
                         yscrollincrement=1)
        self.bind("<Configure>", lambda event:self._draw())
        self.bind("<Button-1>", self._click)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Up>", lambda event:self._move(-1))
        self.bind("<Down>", lambda event:self._move(1))
        self.bind("<Home>", lambda event:self._move_to(0))
        self.bind("<End>", lambda event:self._move_to(len(self.rows)-1))
        self.bind("<space>", lambda event:self._move(0))

    def heading(self, column, text=None, **kwargs):
        if text is not None:
            self.headings[column] = text
        return self.headings[column]

    def column(self, column, option=None, **kwargs):
        if "width" in kwargs:
            self.widths[column] = kwargs["width"]
            self._draw()
        if option == "width":
            return self.widths[column]
        return {"width": self.widths[column]}

    def insert(self, parent, index, iid, values):
        self.rows[str(iid)] = dict(zip(self.columns,values))
        self._draw()
        return str(iid)

    def get_children(self):
        return tuple(self.rows)

    def delete(self, *ids):
        for iid in ids:
            self.rows.pop(str(iid),None)
        if self.selected_id not in self.rows:
            self.selected_id = None
        self._draw()

    def selection(self):
        return (self.selected_id,) if self.selected_id in self.rows else ()

    def selection_set(self, iid):
        if self.disabled:
            return
        if str(iid) not in self.rows:
            return
        self.selected_id = str(iid)
        self._draw()
        self.event_generate("<<TreeviewSelect>>",when="tail")

    def set(self, iid, column, value=None):
        if value is None:
            return self.rows[str(iid)][column]
        self.rows[str(iid)][column] = value
        self._draw()

    def state(self, states):
        if "disabled" in states:
            self.disabled = True
        if "!disabled" in states:
            self.disabled = False
        self.configure(takefocus=0 if self.disabled else 1)

    def bbox(self, iid, column=None):
        if str(iid) not in self.rows:
            return ()
        index = list(self.rows).index(str(iid))
        y = self.header_height + index*(self.row_height+self.gap) - self.canvasy(0)
        if column is None:
            return (0, round(y), self.winfo_width(), self.row_height)
        x = sum(self.widths[key] for key in self.display_columns[:self.display_columns.index(column)])
        return (x, round(y), self.widths[column], self.row_height)

    def _click(self, event):
        if not self.disabled:
            self.focus_set()
            y = self.canvasy(event.y)-self.header_height
            index = int(y//(self.row_height+self.gap))
            if y>=0 and 0<=index<len(self.rows) and y%(self.row_height+self.gap)<self.row_height:
                self.selection_set(list(self.rows)[index])
        return "break"

    def _wheel(self, event):
        self.yview_scroll(-int(event.delta/120)*round(30*self.scale),"units")
        return "break"

    def _move(self, delta):
        ids = list(self.rows)
        index = ids.index(self.selected_id) if self.selected_id in ids else (-1 if delta>=0 else len(ids))
        return self._move_to(max(0,min(len(ids)-1,index+delta)))

    def _move_to(self, index):
        if not self.disabled and self.rows:
            index = max(0,min(len(self.rows)-1,index))
            self.selection_set(list(self.rows)[index])
            top = self.header_height + index*(self.row_height+self.gap)
            bottom = top+self.row_height
            current = self.canvasy(0)
            total = max(self.winfo_height(), self.header_height+len(self.rows)*(self.row_height+self.gap))
            if top<current:
                self.yview_moveto(top/total)
            elif bottom>current+self.winfo_height():
                self.yview_moveto(max(0,bottom-self.winfo_height())/total)
        return "break"

    def _fit(self, value, width, bold=False):
        value = str(value)
        font = self._measure_name if bold else self._measure_font
        if font.measure(value)<=width:
            return value
        while value and font.measure(value+"…")>width:
            value = value[:-1]
        return value+"…" if value else ""

    def _draw(self):
        super().delete("all")
        width = self.winfo_width()
        x = 0
        for key in self.display_columns:
            padding = round((32 if key=="name" else 12)*self.scale)
            self.create_text(x+padding, self.header_height/2, text=self.headings[key],
                             font=self.header_font, fill="#898392", anchor="w")
            x += self.widths[key]
        for index,(iid,row) in enumerate(self.rows.items()):
            y = self.header_height+index*(self.row_height+self.gap)
            selected = iid == self.selected_id
            rounded(self,1,y+1,max(2,width-1),y+self.row_height-1,2*self.scale,
                    fill="#f7f5ff" if selected else "white",outline="#5030f5" if selected else "#e7e3ed",width=1)
            cx,cy,r=round(17*self.scale),y+self.row_height/2,round(7*self.scale)
            self.create_oval(cx-r,cy-r,cx+r,cy+r,fill="white",outline="#5030f5" if selected else "#b3adbd",width=1)
            if selected:
                self.create_oval(cx-r*.5,cy-r*.5,cx+r*.5,cy+r*.5,fill="#5030f5",outline="")
            x=0
            for key in self.display_columns:
                padding=round((38 if key=="name" else 12)*self.scale)
                value = self._fit(row.get(key,""),max(1,self.widths[key]-padding-round(9*self.scale)),bold=key=="name")
                self.create_text(x+padding,cy,text=value,font=self.name_font if key=="name" else self.text_font,
                                 fill="#898392" if key=="state" else "#17141d",anchor="w")
                x+=self.widths[key]
        content_height=self.header_height+len(self.rows)*(self.row_height+self.gap)
        self.configure(scrollregion=(0,0,width,max(self.winfo_height(),content_height)))
