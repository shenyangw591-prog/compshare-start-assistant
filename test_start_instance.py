"""离线验证：不连接云平台，不产生开机或计费操作。"""
import io
import json
import unittest
import threading
from unittest.mock import patch

import start_instance as app


class FakeClock:
    def __init__(self):
        self.now = 0
        self.delays = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.delays.append(seconds)
        self.now += seconds


class FakeClient:
    def __init__(self, states, errors=()):
        self.states = iter(states)
        self.errors = iter(errors)
        self.starts = 0
        self.last = "Stopped"

    def instance(self, *args):
        self.last = next(self.states, self.last)
        if isinstance(self.last, Exception):
            raise self.last
        return {"State": self.last, "GPU": 1}

    def start(self, *args):
        self.starts += 1
        error = next(self.errors, None)
        if error:
            raise error
        return {"RetCode": 0}


class StartTests(unittest.TestCase):
    def run_case(self, client, minutes=2):
        timer = FakeClock()
        with patch.object(app, "log"), patch.object(app.random, "uniform", return_value=0):
            result = app.wait_for_start(client, "uhost-test", "region", "zone", 10,
                                        minutes, clock=timer.clock, sleep=timer.sleep)
        return result, timer

    def test_official_signature_vector(self):
        params = {"Action": "DescribeUHostInstance", "Region": "cn-bj2", "Limit": 10,
                  "PublicKey": "ucloudsomeone@example.com1296235120854146120"}
        result = app.sign(params, "46f09bb9fab4f12dfc160dae12273d5332b5debe")
        self.assertEqual(result, "cba5cf5ec4d4233d206b1b54951e3787350a642f")

    def test_capacity_retry_then_confirm_running(self):
        client = FakeClient(["Stopped", "Stopped", "Starting", "Running"],
                            [app.ApiError(8357, "资源不足"), None])
        result, _ = self.run_case(client)
        self.assertEqual(result, 0)
        self.assertEqual(client.starts, 2)

    def test_running_instance_never_started(self):
        client = FakeClient(["Running"])
        result, _ = self.run_case(client)
        self.assertEqual(result, 0)
        self.assertEqual(client.starts, 0)

    def test_226604_retries_at_configured_interval_until_running(self):
        error = app.ApiError(226604, "This GPU type is currently out of resources. Please refresh or try again later.")
        client = FakeClient(["Stopped", "Stopped", "Stopped", "Starting", "Running"],
                            [error, error, None])
        result, timer = self.run_case(client)
        self.assertEqual(result, 0)
        self.assertEqual(client.starts, 3)
        self.assertEqual(timer.delays, [10, 10, 10, 10])

    def test_quota_expiry_and_unknown_errors_still_stop(self):
        for code in (8095, 8429, 9998):
            with self.subTest(code=code):
                client = FakeClient(["Stopped"], [app.ApiError(code, "需要处理")])
                with self.assertRaises(app.ApiError):
                    self.run_case(client)
                self.assertEqual(client.starts, 1)

    def test_80th_request_accepted_then_initializing_then_running(self):
        client = FakeClient(["Stopped"] * 80 + ["Initializing"] * 3 + ["Running"],
                            [app.ApiError(226604, "资源不足")] * 79 + [None])
        result, _ = self.run_case(client, minutes=30)
        self.assertEqual(result, 0)
        self.assertEqual(client.starts, 80)

    def test_initializing_beyond_operation_lock_never_submits_start(self):
        client = FakeClient(["Initializing"] * 65 + ["Running"])
        result, timer = self.run_case(client, minutes=12)
        self.assertEqual(result, 0)
        self.assertEqual(client.starts, 0)
        self.assertGreater(timer.now, 600)

    def test_initializing_can_time_out_without_starting(self):
        client = FakeClient(["Initializing"])
        result, timer = self.run_case(client, minutes=.5)
        self.assertEqual(result, 2)
        self.assertEqual(client.starts, 0)
        self.assertEqual(timer.now, 30)

    def test_initializing_can_be_stopped(self):
        client = FakeClient(["Initializing"])
        event = threading.Event()
        def receive(kind, **data):
            if kind == "waiting":
                event.set()
        with patch.object(app, "log"):
            result = app.wait_for_start(client, "id", "r", "z", stop_event=event, on_event=receive)
        self.assertEqual(result, 130)
        self.assertEqual(client.starts, 0)

    def test_acceptance_not_treated_as_success(self):
        client = FakeClient(["Stopped", "Starting"])
        result, _ = self.run_case(client, minutes=1)
        self.assertEqual(result, 2)
        self.assertEqual(client.starts, 1)

    def test_no_duplicate_during_operation_lock(self):
        client = FakeClient(["Stopped"], [app.ApiError(9999, "InstanceOperationInProgress")])
        result, _ = self.run_case(client, minutes=1)
        self.assertEqual(result, 2)
        self.assertEqual(client.starts, 1)

    def test_acceptance_waits_through_stale_stopped_state(self):
        client = FakeClient(["Stopped", "Stopped", "Stopped", "Running"])
        result, _ = self.run_case(client)
        self.assertEqual(result, 0)
        self.assertEqual(client.starts, 1)

    def test_permission_error_stops_immediately(self):
        client = FakeClient(["Stopped"], [app.ApiError(171, "签名错误")])
        with self.assertRaises(app.ApiError):
            self.run_case(client)
        self.assertEqual(client.starts, 1)

    def test_throttle_backs_off(self):
        client = FakeClient([app.ApiError(153, "限流"), app.ApiError(153, "限流"), "Running"])
        result, timer = self.run_case(client)
        self.assertEqual(result, 0)
        self.assertEqual(timer.delays, [30, 60])
        self.assertEqual(client.starts, 0)

    def test_ambiguous_start_checks_state_before_retry(self):
        client = FakeClient(["Stopped", "Running"], [app.TemporaryError("超时")])
        result, _ = self.run_case(client)
        self.assertEqual(result, 0)
        self.assertEqual(client.starts, 1)

    def test_deadline_no_further_requests(self):
        client = FakeClient(["Stopped"], [app.ApiError(8357, "资源不足")])
        result, timer = self.run_case(client, minutes=0.1)
        self.assertEqual(result, 2)
        self.assertEqual(client.starts, 1)
        self.assertEqual(timer.now, 6)

    def test_request_never_contains_private_key_or_without_gpu(self):
        client = app.Client("dummy-public", "dummy-private", "org-test")
        client.opener.open = lambda *args, **kwargs: io.BytesIO(b'{"RetCode": 0}')
        with patch.object(client.opener, "open", wraps=client.opener.open) as opened:
            client.start("uhost-test", "region", "zone")
        request = opened.call_args.args[0]
        params = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.compshare.cn")
        self.assertNotIn("dummy-private", request.data.decode())
        self.assertNotIn("WithoutGpuSpec", params)
        self.assertEqual(params["ProjectId"], "org-test")
        self.assertEqual(params["Action"], "StartCompShareInstance")

    def test_find_instance_on_second_page(self):
        client = app.Client("pub", "priv")
        pages = [{"UHostSet": [{"UHostId": "other"}], "TotalCount": 2},
                 {"UHostSet": [{"UHostId": "target", "State": "Stopped"}], "TotalCount": 2}]
        with patch.object(client, "invoke", side_effect=pages) as invoke:
            self.assertEqual(client.instance("target", "r", "z")["State"], "Stopped")
        self.assertEqual(invoke.call_args.kwargs["Offset"], 1)

    def test_secret_redaction_in_api_errors(self):
        client = app.Client("pub-secret", "priv-secret")
        raw = json.dumps({"RetCode": 171, "Message": "pub-secret priv-secret"}).encode()
        with patch.object(client.opener, "open", return_value=io.BytesIO(raw)):
            with self.assertRaises(app.ApiError) as error:
                client.start("id", "r", "z")
        self.assertNotIn("pub-secret", str(error.exception))
        self.assertNotIn("priv-secret", str(error.exception))

    def test_invalid_numeric_config(self):
        for value in (float("nan"), float("inf"), -1, True):
            with self.assertRaises(ValueError):
                app.number(value, "test", 0)

    def test_stop_before_query_prevents_any_operation(self):
        event = threading.Event()
        event.set()
        client = FakeClient(["Stopped"])
        with patch.object(app, "log"):
            result = app.wait_for_start(client, "id", "r", "z", stop_event=event)
        self.assertEqual(result, 130)
        self.assertEqual(client.starts, 0)

    def test_stop_during_query_prevents_start(self):
        event = threading.Event()
        client = FakeClient(["Stopped"])
        def query(*args):
            event.set()
            return {"State": "Stopped"}
        client.instance = query
        with patch.object(app, "log"):
            result = app.wait_for_start(client, "id", "r", "z", stop_event=event)
        self.assertEqual(result, 130)
        self.assertEqual(client.starts, 0)

    def test_wait_can_be_interrupted_without_another_start(self):
        event = threading.Event()
        client = FakeClient(["Stopped"], [app.ApiError(8357, "缺卡")])
        events = []
        def receive(kind, **data):
            events.append(kind)
            if kind == "waiting":
                event.set()
        with patch.object(app, "log"):
            result = app.wait_for_start(client, "id", "r", "z", stop_event=event, on_event=receive)
        self.assertEqual(result, 130)
        self.assertEqual(client.starts, 1)
        self.assertIn("retry", events)
        self.assertIn("stopped", events)


if __name__ == "__main__":
    unittest.main()
