"""已确认效果图的主窗口布局。业务流程仍由 App 管理。"""
import tkinter as tk
from tkinter import ttk
from pathlib import Path

from ui_widgets import Input, InstanceList, Progress


def build(app):
    p = app.px
    app.columnconfigure(0, weight=1)
    app.rowconfigure(2, weight=1)
    app.settings_window = None
    app.help_window = None
    app.logs_open = False

    header = tk.Frame(app, bg="white")
    header.grid(row=0, column=0, sticky="ew", padx=p(36), pady=(p(15), p(15)))
    brand_scale = min((100, 125, 150), key=lambda value: abs(value/100-app.ui_scale))
    brand_path = Path(__file__).resolve().parent / "assets" / f"brand-header-{brand_scale}.png"
    app._brand_image = tk.PhotoImage(file=str(brand_path))
    app.brand_logo = tk.Label(header, image=app._brand_image, bg="white", borderwidth=0, padx=0, pady=0)
    app.brand_logo.asset_path = brand_path
    app.brand_logo.pack(side="left")
    tk.Frame(header, bg="#e3dfea", width=p(1), height=p(24)).pack(side="left", padx=p(18))
    app.label(header, "开机助手", 22, bold=True).pack(side="left")
    app.help_button = app.button(header, "帮助", app.help, width=60, quiet=True)
    app.help_button.pack(side="right")
    app.settings_button = app.button(header, "设置", app.toggle_advanced, width=60, quiet=True)
    app.settings_button.pack(side="right", padx=(0, p(8)))
    app.log_toggle = app.button(header, "运行记录", app.toggle_logs, width=90, quiet=True)
    app.log_toggle.pack(side="right", padx=(0, p(8)))
    app.demo_button = app.button(header, "退出演示", app.toggle_demo, width=90, quiet=True)
    if app.demo:
        app.demo_button.pack(side="right", padx=(0, p(8)))
    app.mode_label = app.label(header, "演示模式", 13, "#5030f5")
    tk.Frame(app, bg="#efedf3", height=1).grid(row=1, column=0, sticky="ew")

    workspace = tk.Frame(app, bg="white")
    workspace.grid(row=2, column=0, sticky="nsew", padx=p(38), pady=(p(18), p(16)))
    workspace.columnconfigure(0, weight=1)
    workspace.rowconfigure(2, weight=1)
    app.hero_title = app.label(workspace, "实例开机", 36, bold=True)
    app.hero_title.grid(row=0, column=0, sticky="w", pady=(0, p(20)))

    account = tk.Frame(workspace, bg="white")
    account.grid(row=1, column=0, sticky="ew", pady=(0, p(20)))
    account.columnconfigure(0, weight=1, uniform="credentials")
    account.columnconfigure(1, weight=1, uniform="credentials")
    title_row = tk.Frame(account, bg="white")
    title_row.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, p(13)))
    app.label(title_row, "账户连接", 19, bold=True).pack(side="left", padx=(0, p(16)))
    tk.Frame(title_row, bg="#eeebf3", height=1).pack(side="left", fill="x", expand=True)
    app.label(account, "公钥 PublicKey", 13, "#8b8694").grid(row=1, column=0, sticky="w", pady=(0, p(7)))
    app.label(account, "私钥 PrivateKey", 13, "#8b8694").grid(row=1, column=1, sticky="w", padx=(p(20), 0), pady=(0, p(7)))
    public_box = Input(account, app.public, app.font(), app.ui_scale, secret=True,
                       on_reveal=lambda: app.toggle_field("public"))
    public_box.grid(row=2, column=0, sticky="ew")
    private_box = Input(account, app.private, app.font(), app.ui_scale, secret=True,
                        on_reveal=lambda: app.toggle_field("private"))
    private_box.grid(row=2, column=1, sticky="ew", padx=(p(20), 0))
    app.pub_entry, app.key_entry = public_box.entry, private_box.entry
    app.show_buttons = [public_box.reveal_button, private_box.reveal_button]
    app.show_button = app.show_buttons[0]
    app.connect_button = app.button(account, "连接账户", app.connect, width=122, height=44, primary=True)
    app.connect_button.grid(row=2, column=2, padx=(p(20), p(16)))
    app.connection_indicator = app.label(account, "● 未连接", 13, "#8b8694")
    app.connection_indicator.grid(row=2, column=3, sticky="w")
    storage_row = tk.Frame(title_row, bg="white")
    storage_row.pack(side="right", padx=(p(16),0))
    app.remember_check = tk.Checkbutton(storage_row, text="记住密钥", variable=app.remember_keys,
                                       command=app.remember_changed, font=app.font(14), bg="white",
                                       activebackground="white", fg="#3b3745", selectcolor="white",
                                       highlightthickness=0, borderwidth=0, padx=0, pady=0)
    app.remember_check.pack(side="left")
    app.forget_button = app.button(storage_row, "清除已保存密钥", app.forget_credentials,
                                   width=154, height=26, quiet=True)
    app.forget_button.pack(side="left", padx=(p(12),0))

    middle = tk.Frame(workspace, bg="white")
    middle.grid(row=2, column=0, sticky="nsew")
    middle.columnconfigure(0, weight=1)
    middle.columnconfigure(2, minsize=p(280))
    middle.rowconfigure(0, weight=1)
    app.instance_card = tk.Frame(middle, bg="white")
    app.instance_card.grid(row=0, column=0, sticky="nsew")
    instance_heading = tk.Frame(app.instance_card, bg="white")
    instance_heading.pack(fill="x", pady=(0, p(14)))
    app.label(instance_heading, "选择实例", 19, bold=True).pack(side="left")
    app.instance_count = app.label(instance_heading, "", 13, "#8b8694")
    app.instance_count.pack(side="right")
    app.table_frame = tk.Frame(app.instance_card, bg="white")
    app.table_frame.pack(fill="both", expand=True)
    app.tree = InstanceList(app.table_frame, app.ui_scale)
    app.tree.pack(side="left", fill="both", expand=True)
    app.table_scroll = ttk.Scrollbar(app.table_frame, orient="vertical", style="Thin.Vertical.TScrollbar",
                                     command=app.tree.yview)
    app.tree.configure(yscrollcommand=app._scroll_instances)
    app.tree.bind("<Configure>", app._size_columns, add="+")
    app.tree.bind("<<TreeviewSelect>>", app.selected)
    app.tree.bind("<Double-Button-1>", app.show_instance_details)
    app.empty_hint = app.label(app.table_frame, "连接账户后显示实例", 14, "#8b8694")
    app.empty_hint.place(relx=.5, rely=.58, anchor="center")

    tk.Frame(middle, bg="#eeebf3", width=1).grid(row=0, column=1, sticky="ns", padx=(p(27), p(27)))
    status = tk.Frame(middle, bg="white")
    status.grid(row=0, column=2, sticky="nsew")
    status.columnconfigure(0, weight=1)
    status.rowconfigure(7, weight=1)
    app.label(status, "运行状态", 19, bold=True).grid(row=0, column=0, sticky="w")
    headline = tk.Frame(status, bg="white")
    headline.grid(row=1, column=0, sticky="ew", pady=(p(14), p(8)))
    app.status_dot = app.label(headline, "●", 19, "#5030f5")
    app.status_dot.pack(side="left", padx=(0, p(10)))
    app.status_label = app.label(headline, "等待连接", 30, bold=True)
    app.status_label.pack(side="left")
    target = tk.Frame(status, bg="white")
    target.grid(row=2, column=0, sticky="ew", pady=(0, p(10)))
    target.columnconfigure(1, weight=1)
    app.label(target, "选中实例：", 13, "#8b8694").grid(row=0, column=0, sticky="nw")
    app.selection_label = app.label(target, "", 14, bold=True, wraplength=p(188), justify="left",
                                     height=2, textvariable=app.target_text)
    app.selection_label.configure(anchor="nw")
    app.selection_label.grid(row=0, column=1, sticky="ew")
    app.progress = Progress(status, app.ui_scale)
    app.progress.grid(row=3, column=0, sticky="ew", pady=(0, p(14)))
    metrics = tk.Frame(status, bg="white")
    metrics.grid(row=4, column=0, sticky="ew", pady=(0, p(16)))
    for column, (title, variable) in enumerate((("已等待", app.elapsed_text), ("开机尝试", app.attempt_text),
                                               ("下次检查", app.countdown_text))):
        metrics.columnconfigure(column*2, weight=1, uniform="metrics")
        group = tk.Frame(metrics, bg="white")
        group.grid(row=0, column=column*2, sticky="ew")
        app.label(group, title, 13, "#8b8694").pack(anchor="w")
        app.label(group, "", 20, bold=True, textvariable=variable).pack(anchor="w", pady=(p(8), 0))
        if column < 2:
            tk.Frame(metrics, bg="#eeebf3", width=1).grid(row=0, column=column*2+1, sticky="ns", padx=p(10))
    app.console_button = app.button(status, "打开控制台", lambda: app.open_console(), width=145, height=38, outlined=True)
    app.console_button.grid(row=5, column=0, sticky="w")

    app.action_bar = tk.Frame(app, bg="white")
    app.action_bar.grid(row=3, column=0, sticky="ew", padx=p(38), pady=(0, p(18)))
    tk.Frame(app.action_bar, bg="#eeebf3", height=1).pack(fill="x")
    actions = tk.Frame(app.action_bar, bg="white")
    actions.pack(fill="x", pady=(p(18), 0))
    app.start_button = app.button(actions, "开始自动开机", app.start, width=182, height=46,
                                   primary=True, state="disabled")
    app.start_button.pack(side="right", padx=(p(14), 0))
    app.stop_button = app.button(actions, "停止等待", app.stop, width=120, height=46, state="disabled")
    app.stop_button.pack(side="right", padx=(p(16), 0))
    for title, variable, values, attribute in (
        ("重试间隔", app.interval, ("5 秒", "10 秒", "20 秒", "30 秒", "60 秒"), "interval_box"),
        ("等待上限", app.limit, ("30 分钟", "1 小时", "2 小时", "4 小时", "不限时"), "limit_box"),
    ):
        group = tk.Frame(actions, bg="white")
        group.pack(side="left", padx=(0, p(22)))
        app.label(group, title, 13, "#615a70").pack(side="left", padx=(0, p(10)))
        control = ttk.Combobox(group, textvariable=variable, values=values, width=9,
                               state="readonly", font=app.font(14))
        control.pack(side="left")
        setattr(app, attribute, control)

    app.log_window = tk.Toplevel(app)
    app.log_window.withdraw()
    app.log_window.title("运行记录")
    app.log_window.configure(bg="white")
    app.log_window.geometry(f"{p(720)}x{p(340)}")
    app.log_window.minsize(p(450), p(220))
    app.log_window.protocol("WM_DELETE_WINDOW", lambda: app.show_logs(False))
    app.log_body = tk.Frame(app.log_window, bg="white")
    app.log_body.pack(fill="both", expand=True, padx=p(18), pady=p(18))
    app.log_text = tk.Text(app.log_body, relief="flat", bg="white", fg="#615a70", font=app.font(13),
                           wrap="word", state="disabled", padx=p(12), pady=p(8), borderwidth=0)
    log_scroll = ttk.Scrollbar(app.log_body, orient="vertical", style="Thin.Vertical.TScrollbar", command=app.log_text.yview)
    log_scroll.pack(side="right", fill="y")
    app.log_text.configure(yscrollcommand=log_scroll.set)
    app.log_text.pack(side="left", fill="both", expand=True)
    app.append_log("离线演示已就绪。" if app.demo else "请连接账户。")
