"""离线 GUI 集成测试。需要 Tk 桌面，不需要云平台账户。"""
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import App, DemoClient, VERSION
from credential_store import CredentialError


class MemoryCredentialStore:
    available = True

    def __init__(self):
        self.saved = None
        self.calls = []

    def load(self):
        self.calls.append("load")
        return self.saved.copy() if self.saved else None

    def save(self, public_key, private_key, project_id=""):
        self.calls.append("save")
        self.saved = dict(public_key=public_key, private_key=private_key, project_id=project_id)

    def delete(self):
        self.calls.append("delete")
        self.saved = None


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryCredentialStore()
        self.store_patch = patch("app.CredentialStore", return_value=self.store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.env_patch = patch.dict("os.environ", {"COMPSHARE_PUBLIC_KEY": "", "COMPSHARE_PRIVATE_KEY": ""})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def connect_fake_account(self, app):
        client = SimpleNamespace(public_key=app.public.get(), private_key=app.private.get(),
                                 project_id=app.project.get(), instances=lambda: DemoClient().instances())
        with patch("app.Client", return_value=client):
            app.connect()
            deadline = time.monotonic() + 3
            while app.busy and time.monotonic() < deadline:
                app.update()
                time.sleep(.01)
        self.assertFalse(app.busy)
        return client

    def test_remember_reopen_and_clear_credentials(self):
        app = App()
        try:
            app.public.set("fake-public")
            app.private.set("fake-private")
            app.project.set("fake-project")
            self.assertIsNone(self.store.saved)
            self.connect_fake_account(app)
            self.assertEqual(self.store.saved["private_key"], "fake-private")
        finally:
            app.close()
        app = App()
        try:
            self.assertEqual((app.public.get(), app.private.get(), app.project.get()),
                             ("fake-public", "fake-private", "fake-project"))
            self.assertEqual(app.key_entry.cget("show"), "●")
            self.assertIsNone(app.client)  # 自动填入后仍由用户连接。
            self.connect_fake_account(app)
            app.remember_keys.set(False)
            app.remember_changed()
            self.assertIsNone(self.store.saved)
            self.assertEqual(app.private.get(), "fake-private")
            app.remember_keys.set(True)
            app.remember_changed()
            self.assertEqual(self.store.saved["project_id"], "fake-project")
            app.forget_credentials()
            self.assertIsNone(self.store.saved)
            self.assertIsNone(app.client)
            self.assertEqual((app.public.get(), app.private.get(), app.project.get()), ("", "", ""))
            self.assertFalse(app.remember_keys.get())
            app.public.set("not-remembered-public")
            app.private.set("not-remembered-private")
            self.connect_fake_account(app)
            self.assertIsNone(self.store.saved)
        finally:
            app.close()

    def test_demo_never_reads_writes_or_deletes_saved_credentials(self):
        self.store.saved = dict(public_key="stored-public", private_key="stored-private", project_id="")
        app = App(demo=True)
        try:
            deadline = time.monotonic() + 3
            while app.busy and time.monotonic() < deadline:
                app.update()
                time.sleep(.01)
            app.save_credentials()
            app.remember_changed()
            app.forget_credentials()
            self.assertEqual(self.store.calls, [])
            self.assertEqual(app.public.get(), "")
            self.assertEqual(app.private.get(), "")
            self.assertTrue(app.forget_button.instate(["disabled"]))
        finally:
            app.close()
        self.assertEqual(self.store.saved["private_key"], "stored-private")

    def test_storage_failure_allows_manual_connection_without_secret_logs(self):
        with patch.object(self.store, "load", side_effect=CredentialError("无法读取已保存的密钥")):
            app = App()
        try:
            self.assertEqual(app.private.get(), "")
            app.public.set("fake-public")
            app.private.set("fake-private")
            with patch.object(self.store, "save", side_effect=CredentialError("无法写入密钥文件")):
                client = self.connect_fake_account(app)
            self.assertIs(app.client, client)
            self.assertEqual(app.status_label.cget("text"), "密钥未保存")
            self.assertEqual(len(app.tree.get_children()), 2)
            contents = app.log_text.get("1.0", "end")
            self.assertNotIn("fake-public", contents)
            self.assertNotIn("fake-private", contents)
        finally:
            app.close()

    def test_offline_user_journey(self):
        # 明确阻止真实网络；演示流程仍应完整成功。
        with patch("start_instance.Client.invoke", side_effect=AssertionError("测试中不允许网络")):
            app = App(demo=True)
            app.withdraw()

            def until(predicate, timeout=20):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    app.update()
                    if predicate():
                        return
                    time.sleep(0.02)
                self.fail("界面状态未在预期时间内完成")

            try:
                self.assertIn(f"v{VERSION}", app.title())
                self.assertIn("演示模式", app.title())
                self.assertIn(f"v{VERSION}", app.log_text.get("1.0", "end"))
                until(lambda: not app.busy and len(app.tree.get_children()) == 2)
                self.assertTrue(app.start_button.instate(["disabled"]))
                app.tree.selection_set("0")
                app.selected()
                self.assertFalse(app.start_button.instate(["disabled"]))
                self.assertIn("demo-4090", app.selection_text.get())
                app.start()
                self.assertTrue(app.stop_button.instate(["!disabled"]))
                self.assertTrue(app.connect_button.instate(["disabled"]))
                until(lambda: app.status_label.cget("text") == "等待空闲 GPU")
                self.assertTrue(app.running)
                self.assertTrue(app.busy)
                self.assertTrue(app.stop_button.instate(["!disabled"]))
                self.assertGreater(app.next_poll, time.monotonic())
                self.assertIsNone(app.success_window)
                until(lambda: app.status_label.cget("text") == "初始化中")
                self.assertTrue(app.running)
                self.assertEqual(app.tree.set("0", "state"), "初始化中")
                self.assertEqual(app.attempt_text.get(), "3 次")
                self.assertIsNone(app.success_window)
                until(lambda: not app.busy)
                self.assertEqual(app.status_label.cget("text"), "实例已运行")
                self.assertEqual(app.attempt_text.get(), "3 次")
                self.assertTrue(app.stop_button.instate(["disabled"]))
                self.assertTrue(app.success_window.winfo_exists())
                self.assertIn("演示", app.success_window.title())
                self.assertEqual(app.success_name_label.cget("text"), "训练实例")
                app.success_dismiss_button._activate()
                self.assertIsNone(app.success_window)
                app.start()
                app.stop()
                until(lambda: not app.busy)
                self.assertEqual(app.status_label.cget("text"), "已停止等待")
                self.assertIsNone(app.success_window)
                app.public.set("dummy-public-secret")
                app.private.set("dummy-private-secret")
                app.append_log("dummy-public-secret dummy-private-secret")
                contents = app.log_text.get("1.0", "end")
                self.assertNotIn("dummy-public-secret", contents)
                self.assertNotIn("dummy-private-secret", contents)
                self.assertIsNone(app.client)  # 修改密钥后必须重新连接。
                app.toggle_advanced()
                self.assertTrue(app.settings_window.winfo_exists())
                app.settings_window.destroy()
                app.toggle_demo()
                self.assertFalse(app.demo)
                self.assertIn(f"v{VERSION}", app.title())
                self.assertNotIn("演示模式", app.title())
                self.assertEqual(app.public.get(), "")
                self.assertEqual(app.private.get(), "")
                app.connect()
                self.assertFalse(app.busy)
                self.assertEqual(app.status_label.cget("text"), "还差一步")
            finally:
                app.close()

    def test_controls_fit_at_100_125_150_percent(self):
        for scale in (1,1.25,1.5):
            with self.subTest(scale=scale):
                app=App(ui_scale=scale)
                try:
                    app.geometry(f"{round(900*scale)}x{round(680*scale)}")
                    app.update()
                    for name in ("connect_button","start_button","stop_button","console_button",
                                 "tree","selection_label","log_toggle", "remember_check", "forget_button"):
                        widget=getattr(app,name)
                        self.assertTrue(widget.winfo_ismapped(),name)
                        x,y=widget.winfo_rootx(),widget.winfo_rooty()
                        right,bottom=x+widget.winfo_width(),y+widget.winfo_height()
                        parent=widget.master
                        while parent is not None:
                            self.assertGreaterEqual(x,parent.winfo_rootx()-1,name)
                            self.assertGreaterEqual(y,parent.winfo_rooty()-1,name)
                            self.assertLessEqual(right,parent.winfo_rootx()+parent.winfo_width()+1,name)
                            self.assertLessEqual(bottom,parent.winfo_rooty()+parent.winfo_height()+1,name)
                            parent=getattr(parent,"master",None)
                    # 查看记录不能挤压主窗口或遮住底部操作区。
                    before=app.start_button.winfo_rooty()
                    app.show_logs(True)
                    app.update()
                    self.assertEqual(before,app.start_button.winfo_rooty())
                    app.show_logs(False)
                finally:
                    app.close()

    def test_success_popup_is_visible_once_with_working_console_action(self):
        for scale in (1, 1.25, 1.5):
            with self.subTest(scale=scale):
                app = App(ui_scale=scale)
                try:
                    app.update()
                    if scale == 1:
                        app.iconify()
                        app.update()
                    app.target_text.set("训练实例名称" * 20)
                    for engine in (("accepted", {}), ("state", {"state": "Initializing"})):
                        app.events.put(("engine", engine))
                    app.events.put(("finished", 2))
                    app.events.put(("finished", 130))
                    app._drain()
                    self.assertIsNone(app.success_window)
                    app.events.put(("engine", ("success", {})))
                    app.events.put(("finished", 0))
                    app._drain()
                    app.update()
                    dialog = app.success_window
                    self.assertTrue(dialog.winfo_ismapped())
                    self.assertEqual(dialog.title(), "开机成功")
                    self.assertTrue(dialog.attributes("-topmost"))
                    self.assertEqual(app.state(), "normal")
                    self.assertFalse(app.busy)
                    for widget in (app.success_name_label, app.success_console_button, app.success_dismiss_button):
                        self.assertGreaterEqual(widget.winfo_rootx(), dialog.winfo_rootx())
                        self.assertGreaterEqual(widget.winfo_rooty(), dialog.winfo_rooty())
                        self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(), dialog.winfo_rootx()+dialog.winfo_width())
                        self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(), dialog.winfo_rooty()+dialog.winfo_height())
                    app.show_success_notification()
                    self.assertIs(app.success_window, dialog)
                    with patch("ui_layout.webbrowser.open") as opened:
                        app.success_console_button._activate()
                        opened.assert_called_once_with("https://console.compshare.cn/")
                    self.assertIsNone(app.success_window)
                    self.assertFalse(dialog.winfo_exists())
                    app.events.put(("finished", 0))
                    app._drain()
                    self.assertIsNone(app.success_window)
                finally:
                    app.close()

    def test_zero_or_unknown_gpu_count_shows_model_without_guessing(self):
        app = App()
        try:
            instances = [dict(UHostId=f"demo-{index}", Name="测试实例", GpuType="4090",
                              GPU=count, State="Stopped", Zone="cn-test-01")
                         for index, count in enumerate((0, "0", None, 1, "2"))]
            client = SimpleNamespace(public_key="fake-public", private_key="fake-private", project_id="")
            app.events.put(("connected", (client, instances)))
            app._drain()
            self.assertEqual([app.tree.set(str(index), "gpu") for index in range(5)],
                             ["4090", "4090", "4090", "4090 ×1", "4090 ×2"])
        finally:
            app.close()

    def test_instance_cards_support_selection_and_long_lists(self):
        app=App()
        try:
            for index in range(25):
                app.tree.insert("","end",iid=str(index),values=(f"实例{index}","RTX 4090 ×1","已关机","cn-wlcb-01"))
            app.update()
            x,y,width,height=app.tree.bbox("1")
            app.tree.event_generate("<Button-1>",x=round(width/2),y=round(y+height/2))
            app.update()
            self.assertEqual(app.tree.selection(),("1",))
            app.tree.focus_force()
            app.update()
            app.tree.event_generate("<Down>")
            app.update()
            self.assertEqual(app.tree.selection(),("2",))
            app.tree.event_generate("<End>")
            app.update()
            self.assertEqual(app.tree.selection(),("24",))
            _,y,_,height=app.tree.bbox("24")
            self.assertGreaterEqual(y,-1)
            self.assertLessEqual(y+height,app.tree.winfo_height()+1)
            app.tree.state(["disabled"])
            app.tree.selection_set("0")
            self.assertEqual(app.tree.selection(),("24",))
        finally:
            app.close()

    def test_key_visibility_is_independent_and_resets_during_work(self):
        app=App()
        try:
            app.toggle_field("public")
            self.assertEqual(app.pub_entry.cget("show"),"")
            self.assertEqual(app.key_entry.cget("show"),"●")
            app.toggle_field("private")
            self.assertEqual(app.key_entry.cget("show"),"")
            app._lock(True)
            self.assertEqual(app.pub_entry.cget("show"),"●")
            self.assertEqual(app.key_entry.cget("show"),"●")
            self.assertTrue(all(button.instate(["disabled"]) for button in app.show_buttons))
            app._lock(False)
            self.assertTrue(all(button.instate(["!disabled"]) for button in app.show_buttons))
        finally:
            app.close()

    def test_close_while_waiting_cancels_local_task(self):
        app=App(demo=True)
        deadline=time.monotonic()+3
        while app.busy and time.monotonic()<deadline:
            app.update()
            time.sleep(.01)
        self.assertFalse(app.busy)
        app.tree.selection_set("0")
        app.selected()
        app.start()
        self.assertTrue(app.running)
        app.close()
        self.assertTrue(app.stop_event.is_set())


if __name__ == "__main__":
    unittest.main()
