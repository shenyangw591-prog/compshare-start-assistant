"""精简桌面布局。所有尺寸与字体使用同一缩放比例。"""
import os
import tkinter as tk
from tkinter import ttk
import webbrowser

from ui_widgets import Button, Input

BG = "#ffffff"
INK = "#111015"
MUTED = "#8b8694"
BLUE = "#5030f5"


def enable_dpi_awareness():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass


class Layout:
    def _init_geometry(self, ui_scale=None):
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        natural = float(self.tk.call("tk", "scaling")) / (96/72)
        self.ui_scale = ui_scale if ui_scale is not None else min(max(1, natural), 1.5, max(.9, (screen_h-100)/740))
        width = min(self.px(1160), screen_w-60)
        height = min(self.px(760), screen_h-100)
        self.geometry(f"{width}x{height}+{max(0,(screen_w-width)//2)}+{max(0,(screen_h-height)//2-20)}")
        self.minsize(min(self.px(900), width), min(self.px(680), height))
        self.configure(bg=BG)

    def px(self, value):
        return max(1, round(value*self.ui_scale))

    def font(self, size=14, bold=False):
        return ("Microsoft YaHei UI", -self.px(size), "bold" if bold else "normal")

    def label(self, parent, text, size=14, color=INK, bold=False, **kwargs):
        kwargs.setdefault("anchor", "w")
        return tk.Label(parent, text=text, font=self.font(size, bold), bg=parent.cget("bg"),
                        fg=color, padx=0, pady=0, **kwargs)

    def button(self, parent, text, command, width=120, height=40, primary=False, quiet=False, state="normal", outlined=False):
        return Button(parent, text, command, self.font(14, primary), width=width, height=height,
                      primary=primary, quiet=quiet, state=state, scale=self.ui_scale, outlined=outlined)

    def _style(self):
        self.option_add("*Font", self.font())
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox", font=self.font(14), padding=self.px(7), arrowsize=self.px(12),
                        background="white", fieldbackground="white", foreground=INK,
                        arrowcolor="#837a98", bordercolor="#dedbe5", lightcolor="#dedbe5",
                        darkcolor="#dedbe5", borderwidth=1, relief="flat")
        style.map("TCombobox", fieldbackground=[("readonly", "white")],
                  selectbackground=[("readonly", "white")], selectforeground=[("readonly", INK)],
                  foreground=[("disabled", "#a0acbe")])
        self.option_add("*TCombobox*Listbox.font", self.font(14))
        style.layout("Thin.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky":"ns", "children":[
            ("Vertical.Scrollbar.thumb", {"sticky":"nswe", "unit":"1"})]})])
        style.configure("Thin.Vertical.TScrollbar", background="#d5ddea", troughcolor="white",
                        borderwidth=0, arrowsize=self.px(7), width=self.px(7), relief="flat")
    def _build(self):
        from editorial_layout import build
        build(self)

    def _size_columns(self, event=None):
        available = max(1, self.tree.winfo_width()-2)
        sizes = [round(available*ratio) for ratio in (.36, .24, .19)]
        sizes.append(available-sum(sizes))
        for key, width in zip(("name", "gpu", "state", "zone"), sizes):
            self.tree.column(key, width=width)

    def _scroll_instances(self, first, last):
        self.table_scroll.set(first, last)
        needed = float(first)>0 or float(last)<1
        if needed and not self.table_scroll.winfo_manager():
            self.table_scroll.pack(side="right", fill="y")
        elif not needed and self.table_scroll.winfo_manager():
            self.table_scroll.pack_forget()

    def toggle_field(self, field):
        if self.busy:
            return
        entry = self.pub_entry if field == "public" else self.key_entry
        entry.configure(show="" if entry.cget("show") else "●")
        self.show_key.set(not self.pub_entry.cget("show") or not self.key_entry.cget("show"))

    def show_instance_details(self, event=None):
        if not self.tree.selection() or self.busy:
            return
        instance = self.instances_by_id.get(self.tree.selection()[0])
        if instance is None:
            return
        dialog, content = self._dialog("实例详情", 540)
        self.label(content, "实例详情", 20, bold=True).pack(anchor="w", pady=(0,self.px(18)))
        for label, key in (("名称", "Name"), ("实例 ID", "UHostId"), ("GPU", "GpuType"),
                           ("地域", "Region"), ("可用区", "Zone")):
            self.label(content, label, 13, MUTED).pack(anchor="w")
            self.label(content, str(instance.get(key, "—")), 14, wraplength=self.px(490),
                       justify="left").pack(anchor="w", pady=(self.px(4),self.px(14)))
        self.button(content, "关闭", dialog.destroy, width=90, outlined=True).pack(anchor="e")
        self._fit_dialog(dialog)

    def open_console(self):
        webbrowser.open("https://console.compshare.cn/")

    def dismiss_success_notification(self):
        dialog = self.success_window
        self.success_window = None
        if dialog is not None and dialog.winfo_exists():
            if self.grab_current() == dialog:
                dialog.grab_release()
            dialog.destroy()

    def show_success_notification(self):
        if self._success_notified:
            return
        self._success_notified = True
        if self.state() == "iconic":
            self.deiconify()
        dialog, content = self._dialog("演示完成" if self.demo else "开机成功", 480)
        self.success_window = dialog
        # 独立显示，避免 Windows 将通知与尚在恢复的最小化主窗口一起隐藏。
        dialog.transient("")
        dialog.attributes("-topmost", True)
        dialog.protocol("WM_DELETE_WINDOW", self.dismiss_success_notification)
        dialog.bind("<Escape>", lambda event: self.dismiss_success_notification())
        dialog.bind("<Return>", lambda event: self.dismiss_success_notification())
        p = self.px
        badge = tk.Canvas(content, width=p(68), height=p(68), bg="white", highlightthickness=0)
        badge.pack(pady=(p(6),p(16)))
        badge.create_oval(p(2),p(2),p(66),p(66),fill="#e7f6ef",outline="")
        badge.create_line(p(20),p(34),p(30),p(44),p(49),p(24),
                          fill="#168363",width=p(5),capstyle="round",joinstyle="round")
        self.label(content,"演示完成" if self.demo else "开机成功",30,bold=True,anchor="center").pack(fill="x")
        name = self.target_text.get()
        name = name if len(name) <= 64 else name[:63] + "…"
        self.success_name_label = self.label(content,name,18,bold=True,anchor="center",
                                             wraplength=p(420),justify="center")
        self.success_name_label.pack(fill="x",pady=(p(12),p(8)))
        self.label(content,"离线演示已完成。" if self.demo else "实例已运行，可以前往控制台连接。",
                   15,MUTED,anchor="center",wraplength=p(420),justify="center").pack(fill="x")
        actions = tk.Frame(content,bg="white")
        actions.pack(pady=(p(26),p(4)))
        self.success_dismiss_button = self.button(actions,"知道了",self.dismiss_success_notification,
                                                 width=116,height=44,outlined=True)
        self.success_dismiss_button.pack(side="left",padx=(0,p(12)))
        def open_and_close():
            self.open_console()
            self.dismiss_success_notification()
        self.success_console_button = self.button(actions,"打开控制台",open_and_close,
                                                 width=170,height=44,primary=True)
        self.success_console_button.pack(side="left")
        self._fit_dialog(dialog)
        dialog.lift()
        self.success_dismiss_button.focus_set()

    def toggle_logs(self):
        self.show_logs(not self.logs_open)

    def show_logs(self,show=True):
        self.logs_open=show
        if show:
            self.log_window.deiconify()
            self.log_window.lift()
        else:
            self.log_window.withdraw()

    def _dialog(self,title,width=480):
        dialog=tk.Toplevel(self)
        dialog.title(title)
        dialog.configure(bg="white")
        dialog.transient(self)
        dialog.resizable(False,False)
        dialog._layout_width=self.px(width)
        dialog.geometry(f"{self.px(width)}x1")
        content=tk.Frame(dialog,bg="white")
        content.pack(fill="both",expand=True,padx=self.px(24),pady=self.px(22))
        return dialog,content

    def _fit_dialog(self,dialog):
        dialog.update_idletasks()
        # Windows 首次映射前 winfo_width 可能仍为 1，使用明确的布局宽度。
        width=dialog._layout_width
        height=dialog.winfo_reqheight()
        x=self.winfo_rootx()+(self.winfo_width()-width)//2
        y=self.winfo_rooty()+max(self.px(24),(self.winfo_height()-height)//2)
        dialog.geometry(f"{width}x{height}+{max(0,x)}+{max(0,y)}")
        dialog.update_idletasks()
        if dialog.winfo_viewable():
            dialog.grab_set()
        dialog.focus_set()

    def toggle_advanced(self):
        if self.busy:
            return
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        dialog,content=self._dialog("设置")
        self.settings_window=dialog
        self.label(content,"项目设置",20,bold=True).pack(anchor="w",pady=(0,self.px(18)))
        self.label(content,"ProjectId",14).pack(anchor="w",pady=(0,self.px(8)))
        project_input=Input(content,self.project,self.font(),self.ui_scale)
        project_input.pack(fill="x")
        self.project_entry=project_input.entry
        self.label(content,"仅子账号或指定项目需要填写，其他情况留空。",13,MUTED,wraplength=self.px(430),justify="left").pack(anchor="w",pady=(self.px(12),self.px(20)))
        self.button(content,"完成",dialog.destroy,width=100,primary=True).pack(anchor="e")
        self._fit_dialog(dialog)

    def toggle_demo(self):
        if self.busy:
            return
        self.demo=not self.demo
        self.public.set("")
        self.private.set("")
        self.project.set("")
        self.client=None
        self.instances_by_id.clear()
        self.tree.delete(*self.tree.get_children())
        self.selection_text.set("未选择实例")
        self.target_text.set("未选择实例")
        self.connection_indicator.configure(text="● 未连接", fg=MUTED)
        self.attempt_text.set("0 次")
        self.elapsed_text.set("00:00")
        self.instance_count.configure(text="")
        self.empty_hint.configure(text="连接账户后显示实例")
        self.empty_hint.place(relx=.5,rely=.58,anchor="center")
        if self.demo:
            self.demo_button.pack(side="right",padx=(0,self.px(10)))
            self.mode_label.pack(side="right",padx=(0,self.px(10)))
        else:
            self.demo_button.pack_forget()
            self.mode_label.pack_forget()
        self.update_window_title()
        self._lock(False)
        self.append_log("已进入离线演示。" if self.demo else "已退出演示，请连接账户。")
        if self.demo:
            self.connect()
        else:
            self.set_status("等待连接","连接账户，读取你的实例。")
            self.restore_credentials()

    def help(self):
        if self.help_window and self.help_window.winfo_exists():
            self.help_window.lift()
            return
        dialog,content=self._dialog("帮助",520)
        self.help_window=dialog
        self.label(content,"快速开始",20,bold=True).pack(anchor="w",pady=(0,self.px(16)))
        for text in ("1. 获取账户 API 公钥与私钥，点击连接账户。",
                     "2. 在列表中选择一台已有实例。",
                     "3. 点击开始自动开机，等待运行成功。"):
            self.label(content,text,14,wraplength=self.px(470),justify="left").pack(anchor="w",pady=self.px(5))
        details=("保持电脑联网、不休眠。开机后正常计费，用完请自行关机。\n"
                 "停止等待只结束本地重试，不撤销已提交的开机操作。\n\n"
                 "勾选记住密钥后，加密保存在当前 Windows 用户下，下次自动填入。\n"
                 "取消勾选或点击清除可删除保存的信息。\n\n"
                 "本工具为社区开源项目，非官方出品。")
        self.label(content,details,13,MUTED,wraplength=self.px(470),justify="left").pack(anchor="w",pady=(self.px(14),self.px(20)))
        actions=tk.Frame(content,bg="white")
        actions.pack(fill="x")
        def demo():
            dialog.destroy()
            if not self.demo:
                self.toggle_demo()
        self.button(actions,"体验离线演示",demo,width=148,primary=True,state="disabled" if self.busy else "normal").pack(side="left")
        self.button(actions,"获取密钥",lambda:webbrowser.open("https://console.compshare.cn/uaccount/api_manage"),width=100,outlined=True).pack(side="left",padx=(self.px(10),0))
        self.button(actions,"关闭",dialog.destroy,width=90).pack(side="right")
        self._fit_dialog(dialog)
