"""CompShare 开机助手：本地图形界面；--demo 可离线体验。"""
import argparse
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk

from start_instance import Client, wait_for_start, STATE_NAMES, TRANSITION_STATES
from ui_layout import Layout, enable_dpi_awareness, BG, INK, MUTED, BLUE
from credential_store import CredentialStore, CredentialError

VERSION = "0.4.6"


class DemoClient:
    """完全离线的演示数据，从不发送网络请求。"""
    def __init__(self):
        self.queries = 0
        self.accepted = False

    def instances(self):
        return [{"UHostId": "demo-4090", "Name": "训练实例", "GPU": 1,
                 "GpuType": "RTX 4090", "State": "Stopped", "Region": "cn-wlcb",
                 "Zone": "cn-wlcb-01"},
                {"UHostId": "demo-a800", "Name": "备用实例", "GPU": 1,
                 "GpuType": "A800", "State": "Stopped", "Region": "cn-sh2",
                 "Zone": "cn-sh2-02"}]

    def instance(self, instance_id, region, zone):
        self.queries += 1
        if self.accepted:
            state = "Running" if self.queries >= 5 else "Initializing"
        else:
            state = "Stopped"
        return {"State": state, "GPU": 1}

    def start(self, *args):
        from start_instance import ApiError
        if self.queries < 3:
            raise ApiError(226604, "This GPU type is currently out of resources. Please refresh or try again later.")
        self.accepted = True
        return {"RetCode": 0}


def gpu_label(instance):
    model = instance.get("GpuType") or "未知型号"
    count = instance.get("GPU")
    # 关机实例可能返回 0；没有明确的正整数卡数时只展示型号，不猜测配置。
    if not isinstance(count, bool) and str(count).isascii() and str(count).isdigit() and int(count) > 0:
        return f"{model} ×{int(count)}"
    return str(model)


def friendly_error(error):
    code = getattr(error, "code", None)
    hints = {171: "密钥验证失败，请重新复制账户 API 公钥和私钥。",
             172: "未找到账户，请检查 API 公钥。",
             174: "密钥已失效，请到 API 密钥页面检查。",
             299: "当前密钥没有实例操作权限，请检查子账号授权。",
             292: "项目不存在，请检查高级设置中的 ProjectId。",
             293: "没有该可用区的访问权限，请检查账户授权。",
             294: "当前网络 IP 不在 API 访问白名单内。",
             8095: "账户配额不足，请到控制台处理或联系平台支持。",
             8429: "实例已过期或欠费，请先到控制台处理。"}
    return hints.get(code, str(error))


class App(Layout, tk.Tk):
    def update_window_title(self):
        self.title(f"CompShare 开机助手 v{VERSION}" + (" · 演示模式" if self.demo else ""))

    def __init__(self, demo=False, ui_scale=None, credential_store=None):
        enable_dpi_awareness()
        super().__init__()
        self.demo = demo
        self.update_window_title()
        self._init_geometry(ui_scale)
        icon_path = Path(__file__).resolve().parent / "assets" / "icon.png"
        if icon_path.exists():
            self._icon = tk.PhotoImage(file=str(icon_path))
            self.iconphoto(True, self._icon)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.busy = False
        self.running = False
        self.client = None
        self.instances_by_id = {}
        self.started_at = None
        self.next_poll = None
        self.success_window = None
        self._success_notified = False
        self.credential_store = credential_store if credential_store is not None else CredentialStore()
        self.remember_keys = tk.BooleanVar(value=self.credential_store.available)
        self.public = tk.StringVar(value="" if demo else os.getenv("COMPSHARE_PUBLIC_KEY", ""))
        self.private = tk.StringVar(value="" if demo else os.getenv("COMPSHARE_PRIVATE_KEY", ""))
        self.project = tk.StringVar()
        self.show_key = tk.BooleanVar(value=False)
        self.interval = tk.StringVar(value="10 秒")
        self.limit = tk.StringVar(value="2 小时")
        self.selection_text = tk.StringVar(value="未选择实例")
        self.target_text = tk.StringVar(value="未选择实例")
        self.elapsed_text = tk.StringVar(value="00:00")
        self.attempt_text = tk.StringVar(value="0 次")
        self.countdown_text = tk.StringVar(value="—")
        self._style()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(80, self._drain)
        self.after(250, self._tick)
        self.public.trace_add("write", self._credentials_changed)
        self.private.trace_add("write", self._credentials_changed)
        self.project.trace_add("write", self._credentials_changed)
        self.append_log(f"CompShare 开机助手 v{VERSION}")
        self._storage_controls()
        if not demo:
            self.restore_credentials()
        if demo:
            self.connect()

    def _storage_controls(self):
        state = "disabled" if self.busy or self.demo or not self.credential_store.available else "normal"
        self.remember_check.configure(state=state)
        self.forget_button.configure(state=state)

    def restore_credentials(self):
        if self.demo or not self.credential_store.available:
            return
        # 环境变量作为独立的一组临时凭证，不与保存的密钥混合。
        env_public = os.getenv("COMPSHARE_PUBLIC_KEY", "")
        env_private = os.getenv("COMPSHARE_PRIVATE_KEY", "")
        if env_public or env_private:
            self.public.set(env_public)
            self.private.set(env_private)
            self.project.set("")
            return
        try:
            saved = self.credential_store.load()
        except CredentialError as error:
            self.append_log(str(error))
            self.set_status("请重新输入密钥", "保存的密钥无法读取，可清除后重新保存。", "#ae6514")
            return
        if saved:
            self.public.set(saved["public_key"])
            self.private.set(saved["private_key"])
            self.project.set(saved["project_id"])
            self.remember_keys.set(True)
            self.append_log("已填入保存的密钥，请点击连接账户。")

    def save_credentials(self):
        if self.demo or not self.remember_keys.get() or not self.credential_store.available or self.client is None:
            return
        try:
            self.credential_store.save(self.client.public_key, self.client.private_key, self.client.project_id)
            self.append_log("密钥已加密保存，下次打开自动填入。")
        except CredentialError as error:
            self.append_log(str(error))
            self.show_logs(True)
            self.set_status("密钥未保存", "本次可继续使用；请检查运行记录。", "#ae6514")

    def remember_changed(self):
        if self.busy or self.demo:
            return
        if self.remember_keys.get():
            self.save_credentials()
        else:
            try:
                self.credential_store.delete()
                self.append_log("已取消记住密钥，并删除保存的信息。")
            except CredentialError as error:
                self.remember_keys.set(True)
                self.append_log(str(error))
                self.show_logs(True)

    def forget_credentials(self):
        if self.busy or self.demo:
            return
        try:
            self.credential_store.delete()
        except CredentialError as error:
            self.append_log(str(error))
            self.show_logs(True)
            return
        self.remember_keys.set(False)
        self.public.set("")
        self.private.set("")
        self.project.set("")
        self.show_key.set(False)
        self.toggle_key()
        self.append_log("已清除保存的密钥。")
        self.set_status("密钥已清除", "重新输入公钥与私钥后连接。")

    def toggle_key(self):
        for entry in (self.pub_entry, self.key_entry):
            entry.configure(show="" if self.show_key.get() else "●")
        

    def _credentials_changed(self, *_):
        if not self.busy and self.client is not None:
            self.client = None
            self.instances_by_id.clear()
            self.tree.delete(*self.tree.get_children())
            self.selection_text.set("未选择实例")
            self.target_text.set("未选择实例")
            self.connection_indicator.configure(text="● 未连接", fg=MUTED)
            self.empty_hint.configure(text="请重新连接账户")
            self.empty_hint.place(relx=.5,rely=.58,anchor="center")
            self.instance_count.configure(text="")
            self.start_button.configure(state="disabled")
            self.set_status("请重新连接", "密钥或项目已修改，请重新连接。")

    def set_status(self, title, hint, color=INK):
        self.status_label.configure(text=title, fg=INK)
        self.status_dot.configure(fg=BLUE if color==INK else color)
        self.status_detail = hint

    def append_log(self, message):
        # 界面仅接收已脱敏的业务日志，不输出请求体或实例完整数据。
        for secret in (self.public.get().strip(), self.private.get().strip()):
            if secret:
                message = message.replace(secret, "[已隐藏]")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{time.strftime('%H:%M:%S')}  {message}\n")
        if int(self.log_text.index("end-1c").split(".")[0]) > 600:
            self.log_text.delete("1.0", "100.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _lock(self, busy, running=False):
        self.busy = busy
        self.running = running
        self._storage_controls()
        for control in (self.pub_entry, self.key_entry, self.connect_button, self.settings_button):
            control.configure(state="disabled" if busy else "normal")
        for control in (self.interval_box, self.limit_box):
            control.configure(state="disabled" if busy else "readonly")
        self.tree.state(["disabled"] if busy else ["!disabled"])
        self.start_button.configure(state="disabled" if busy or not self.tree.selection() or self.client is None else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.demo_button.configure(state="disabled" if busy else "normal")
        if busy:
            self.show_key.set(False)
            self.toggle_key()
            for button in self.show_buttons:
                button.configure(state="disabled")
            self.progress.start(15)
        else:
            for button in self.show_buttons:
                button.configure(state="normal")
            self.progress.stop()
            self.progress.configure(value=0)

    def connect(self):
        if self.busy:
            return
        if not self.demo and (not self.public.get().strip() or not self.private.get().strip()):
            self.set_status("还差一步", "填入公钥与私钥，然后连接账户。", "#ae6514")
            self.pub_entry.focus_set()
            return
        self.client = None
        self.instances_by_id.clear()
        self.tree.delete(*self.tree.get_children())
        self.selection_text.set("未选择实例")
        self.target_text.set("未选择实例")
        self.connection_indicator.configure(text="● 连接中", fg=MUTED)
        self._lock(True)
        self.set_status("读取实例中", "正在连接账户，请稍候。")
        client = DemoClient() if self.demo else Client(self.public.get().strip(), self.private.get().strip(), self.project.get().strip())

        def work():
            try:
                instances = list(client.instances())
                self.events.put(("connected", (client, instances)))
            except Exception as error:
                self.events.put(("error", friendly_error(error)))
        threading.Thread(target=work, daemon=True).start()

    def selected(self, _event=None):
        if self.busy:
            return
        selection = self.tree.selection()
        if not selection:
            return
        instance = self.instances_by_id.get(selection[0])
        if instance is None:
            return
        self.selection_text.set(f"{instance.get('Name', '未命名实例')}\n{instance['UHostId']}")
        self.target_text.set(instance.get("Name") or instance["UHostId"])
        if not self.busy:
            self.start_button.configure(state="normal" if self.client else "disabled")
            self.set_status("准备就绪", "点击下方按钮，开始自动开机。", BLUE)

    def start(self):
        if self.busy or self.client is None or not self.tree.selection():
            return
        instance = self.instances_by_id[self.tree.selection()[0]]
        if not instance.get("Region") or not instance.get("Zone"):
            self.set_status("缺少地域信息", "请到控制台检查实例地域。", "#b5483b")
            return
        self.dismiss_success_notification()
        self._success_notified = False
        interval = int(self.interval.get().split()[0])
        max_minutes = {"30 分钟": 30, "1 小时": 60, "2 小时": 120, "4 小时": 240, "不限时": 0}[self.limit.get()]
        if self.demo:
            self.client = DemoClient()
        client = self.client
        self.stop_event = threading.Event()
        event = self.stop_event
        self.started_at = time.monotonic()
        self.next_poll = None
        self.elapsed_text.set("00:00")
        self.attempt_text.set("0 次")
        self._lock(True, True)
        self.set_status("正在检查", "正在读取实例状态。", BLUE)
        self.append_log(f"开始任务：{instance['UHostId']}" + ("（离线演示，约 10 秒完成）" if self.demo else ""))

        def work():
            try:
                result = wait_for_start(client, instance["UHostId"], instance["Region"], instance["Zone"],
                                        interval=1 if self.demo else interval, max_minutes=max_minutes,
                                        stop_event=event, logger=lambda msg: self.events.put(("log", msg)),
                                        on_event=lambda kind, **data: self.events.put(("engine", (kind, data))))
                self.events.put(("finished", result))
            except Exception as error:
                self.events.put(("error", friendly_error(error)))
        threading.Thread(target=work, daemon=True).start()

    def stop(self):
        if self.running:
            self.stop_event.set()
            self.stop_button.configure(state="disabled")
            self.set_status("正在停止", "正在结束等待，请稍候。")

    def _engine_event(self, kind, data):
        if self.stop_event.is_set() and kind not in {"stopped", "success"}:
            return
        if kind == "state":
            state = data["state"]
            selected = self.tree.selection()
            if selected:
                self.tree.set(selected[0], "state", STATE_NAMES.get(state, state))
            if state in TRANSITION_STATES:
                self.set_status(STATE_NAMES[state], "正在等待云端完成操作。", BLUE)
        elif kind == "attempt":
            self.attempt_text.set(f"{data['attempts']} 次")
            self.set_status("申请开机中", "正在提交有卡开机请求。", BLUE)
        elif kind == "accepted":
            self.set_status("启动已受理", "请求已受理，等待实例运行。", BLUE)
        elif kind == "retry":
            reason = data["reason"]
            title, hint = {"capacity": ("等待空闲 GPU", "资源不足，将自动重试。"),
                           "busy": ("等待云端操作", "实例已有操作，正在等待。"),
                           "network": ("等待网络恢复", "连接暂时中断，将稍后重试。"),
                           "service": ("稍后自动重试", "接口繁忙，已自动延长间隔。")}[reason]
            self.set_status(title, hint, "#ae6514")
        elif kind == "waiting":
            self.next_poll = time.monotonic() + data["seconds"]
        elif kind == "success":
            self.set_status("实例已运行", "开机成功，可前往控制台连接。", "#168363")
        elif kind == "timeout":
            self.set_status("已到等待时限", "等待已结束，请到控制台查看实例。", "#ae6514")
        elif kind == "stopped":
            self.set_status("已停止等待", "本地重试已结束，请到控制台查看实例。")

    def _drain(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "connected":
                    self.client, instances = data
                    self.connection_indicator.configure(text="● 已连接", fg="#29ad68")
                    for index, instance in enumerate(instances):
                        iid = str(index)
                        self.instances_by_id[iid] = instance
                        self.tree.insert("", "end", iid=iid, values=(instance.get("Name") or "未命名实例",
                            gpu_label(instance),
                            STATE_NAMES.get(instance.get("State"), instance.get("State", "未知")), instance.get("Zone", "")))
                    self._lock(False)
                    self.instance_count.configure(text=f"{len(instances)} 台实例")
                    if instances:
                        self.empty_hint.place_forget()
                    else:
                        self.empty_hint.configure(text="未找到实例，请检查账户或项目")
                        self.empty_hint.place(relx=.5,rely=.58,anchor="center")
                    self.set_status("请选择实例" if instances else "未找到实例", "点击列表，选择一台实例。" if instances else "确认密钥所属账户，并检查 ProjectId。")
                    self.append_log(f"读取完成：{len(instances)} 台实例。")
                    self.save_credentials()
                elif kind == "engine":
                    self._engine_event(*data)
                elif kind == "log":
                    self.append_log(data)
                elif kind == "finished":
                    self._lock(False)
                    self.started_at = None
                    self.next_poll = None
                    self.countdown_text.set("—")
                    if data == 0:
                        self.show_success_notification()
                elif kind == "error":
                    self._lock(False)
                    self.started_at = None
                    self.next_poll = None
                    self.countdown_text.set("—")
                    # 不调用含错误详情的系统弹窗，统一在本地日志中脱敏后展示。
                    if self.client is None:
                        self.connection_indicator.configure(text="● 未连接", fg=MUTED)
                    self.append_log(data)
                    self.show_logs(True)
                    self.set_status("需要处理", "请展开运行记录，查看错误详情。", "#b5483b")
        except queue.Empty:
            pass
        self.after(80, self._drain)

    def _tick(self):
        if self.started_at is not None:
            seconds = int(time.monotonic() - self.started_at)
            self.elapsed_text.set(f"{seconds // 60:02d}:{seconds % 60:02d}")
        if self.next_poll is not None and self.running:
            remaining = max(0, int(self.next_poll - time.monotonic() + 0.99))
            self.countdown_text.set(f"{remaining} 秒" if remaining else "检查中")
        self.after(250, self._tick)

    def close(self):
        self.stop_event.set()
        self.progress.stop()
        self.public.set("")
        self.private.set("")
        self.client = None
        for timer in self.tk.call("after", "info"):
            self.after_cancel(timer)
        self.destroy()


def main():
    parser = argparse.ArgumentParser(description="CompShare 开机助手")
    parser.add_argument("--demo", action="store_true", help="离线演示，不连接云平台")
    parser.add_argument("--smoke-test-report", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = App(demo=args.demo or args.smoke_test_report is not None)
    result = {"ok": False}
    if args.smoke_test_report:
        import json
        import sys
        app.withdraw()
        started = [False]
        deadline = time.monotonic() + 35

        def verify():
            if not started[0] and not app.busy and app.tree.get_children():
                app.tree.selection_set("0")
                app.selected()
                app.start()
                started[0] = True
            if (started[0] and not app.busy) or time.monotonic() >= deadline:
                result.update(ok=app.status_label.cget("text") == "实例已运行",
                              status=app.status_label.cget("text"), attempts=app.attempt_text.get(),
                              frozen=bool(getattr(sys, "frozen", False)), version=VERSION, mode="offline demo",
                              success_popup=bool(app.success_window and app.success_window.winfo_exists()))
                result["ok"] = result["ok"] and result["success_popup"]
                args.smoke_test_report.parent.mkdir(parents=True, exist_ok=True)
                # 冻结版也验证 Windows 加密能力，只操作专用测试文件与虚构密钥。
                from uuid import uuid4
                probe = CredentialStore(args.smoke_test_report.parent / f"credentials-smoke-{uuid4().hex}.bin")
                result["encrypted_credentials"] = False
                try:
                    probe.save("offline-test-public", "offline-test-private", "offline-project")
                    saved = probe.load()
                    result["encrypted_credentials"] = (saved == dict(public_key="offline-test-public",
                        private_key="offline-test-private", project_id="offline-project")
                        and b"offline-test-private" not in probe.path.read_bytes())
                except (CredentialError, OSError):
                    pass
                finally:
                    try:
                        probe.delete()
                    except CredentialError:
                        result["encrypted_credentials"] = False
                result["ok"] = result["ok"] and result["encrypted_credentials"]
                args.smoke_test_report.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
                app.close()
                return
            app.after(80, verify)
        app.after(80, verify)
    app.mainloop()
    return 0 if not args.smoke_test_report or result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
