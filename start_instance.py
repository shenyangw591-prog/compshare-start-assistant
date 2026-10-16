#!/usr/bin/env python3
"""优云智算已有 GPU 实例自动开机。Python 3.9+，仅使用标准库。"""
import argparse
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import random
import socket
import sys
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

ENDPOINT = "https://api.compshare.cn"
ROOT = Path(__file__).resolve().parent
CAPACITY_CODES = {8357, 226604}
RETRY_CODES = {110, 130, 150, 153}
STATE_NAMES = {"Stopped": "已关机", "Starting": "启动中", "Running": "运行中",
               "Initializing": "初始化中", "Stopping": "关机中", "Install": "安装中", "Rebooting": "重启中"}
TRANSITION_STATES = frozenset(STATE_NAMES) - {"Stopped", "Running"}


def log(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


class ApiError(Exception):
    def __init__(self, code, message):
        super().__init__(f"API {code}: {message}")
        self.code = code
        self.message = message


class TemporaryError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def sign(params, private_key):
    content = "".join(str(k) + str(v) for k, v in sorted(params.items()))
    return hashlib.sha1((content + private_key).encode("utf-8")).hexdigest()


class Client:
    def __init__(self, public_key, private_key, project_id=""):
        self.public_key = public_key
        self.private_key = private_key
        self.project_id = project_id
        self.opener = build_opener(NoRedirect())

    def invoke(self, action, **params):
        params.update(Action=action, PublicKey=self.public_key)
        if self.project_id:
            params["ProjectId"] = self.project_id
        params["Signature"] = sign(params, self.private_key)
        request = Request(ENDPOINT, data=json.dumps(params).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self.opener.open(request, timeout=30) as response:
                data = json.load(response)
        except HTTPError as error:
            if error.code == 429 or 500 <= error.code < 600:
                raise TemporaryError(f"HTTP {error.code}，稍后重试") from None
            raise RuntimeError(f"HTTP {error.code}，请检查 API 权限及网络") from None
        except (URLError, TimeoutError, socket.timeout, ConnectionError):
            raise TemporaryError("网络异常或请求超时，将先查询状态再决定是否重试") from None
        except (ValueError, UnicodeError):
            raise TemporaryError("接口未返回有效 JSON，将稍后重试") from None
        if not isinstance(data, dict) or "RetCode" not in data:
            raise RuntimeError("API 响应格式异常，已停止")
        try:
            code = int(data["RetCode"])
        except (ValueError, TypeError):
            raise RuntimeError("API 返回码格式异常，已停止") from None
        if code:
            message = str(data.get("Message", data.get("ErrMsg", "未提供错误说明")))
            # 服务端错误信息也可能包含请求参数，避免回显密钥。
            for secret in (self.public_key, self.private_key, params["Signature"]):
                if secret:
                    message = message.replace(secret, "[已隐藏]")
            raise ApiError(code, message)
        return data

    def instances(self, region="", zone=""):
        offset = 0
        while True:
            params = {"Limit": 100, "Offset": offset}
            if region:
                params["Region"] = region
            if zone:
                params["Zone"] = zone
            data = self.invoke("DescribeCompShareInstance", **params)
            page = data.get("UHostSet")
            if not isinstance(page, list):
                raise RuntimeError("查询结果缺少 UHostSet，已停止")
            yield from page
            offset += len(page)
            if offset >= int(data.get("TotalCount", offset)):
                break
            if not page:
                raise RuntimeError("实例分页结果异常，已停止")

    def instance(self, instance_id, region, zone):
        for instance in self.instances(region, zone):
            if instance.get("UHostId") == instance_id:
                return instance
        raise RuntimeError("未找到指定实例，请检查实例 ID、地域、可用区及 ProjectId")

    def start(self, instance_id, region, zone):
        # 不传 WithoutGpuSpec，使用有卡开机。
        return self.invoke("StartCompShareInstance", UHostId=instance_id,
                           Region=region, Zone=zone)


def retry_kind(error):
    if isinstance(error, TemporaryError):
        return "network"
    if isinstance(error, ApiError):
        if "InstanceOperationInProgress" in error.message:
            return "busy"
        if error.code in CAPACITY_CODES:
            return "capacity"
        if error.code in RETRY_CODES:
            return "service"
    return None


def wait_for_start(client, instance_id, region, zone, interval=10, max_minutes=120,
                   clock=time.monotonic, sleep=time.sleep, stop_event=None,
                   logger=None, on_event=None):
    logger = logger or log
    on_event = on_event or (lambda kind, **data: None)

    def cancelled():
        return stop_event is not None and stop_event.is_set()

    def stopped():
        logger("已停止本地重试；已提交的云端开机操作可能继续，请查看控制台。")
        on_event("stopped")
        return 130

    deadline = clock() + max_minutes * 60 if max_minutes else math.inf
    next_start = 0
    failures = 0
    attempts = 0
    logger(f"目标 {instance_id} | {region} / {zone}")
    while clock() < deadline:
        if cancelled():
            return stopped()
        delay = interval
        try:
            instance = client.instance(instance_id, region, zone)
            if cancelled():
                return stopped()
            if clock() >= deadline:
                break
            state = instance.get("State")
            logger(f"实例状态：{state}")
            on_event("state", state=state)
            if state == "Running":
                if instance.get("GPU") in (0, "0"):
                    raise RuntimeError("实例已运行，但 GPU 数量为 0，请到控制台检查开机模式")
                logger("实例已运行，自动重试结束。可连接后用 nvidia-smi 检查 GPU。")
                on_event("success")
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except (ImportError, RuntimeError):
                    print("\a", end="", flush=True)
                return 0
            if state == "Stopped" and clock() >= next_start:
                if instance.get("IsExpire") == "Yes":
                    raise RuntimeError("实例已过期，请先在控制台处理续费或欠费")
                attempts += 1
                logger(f"第 {attempts} 次申请有卡开机")
                on_event("attempt", attempts=attempts)
                # 请求结果不明时，先观察状态一分钟，避免立即重复提交。
                next_start = clock() + 60
                if cancelled():
                    return stopped()
                client.start(instance_id, region, zone)
                next_start = clock() + 600
                logger("启动请求已接受，等待 Running；操作锁期间只查询状态")
                on_event("accepted")
            elif state == "Stopped":
                logger(f"等待已有操作完成，约 {max(1, int(next_start - clock()))} 秒后可重试")
            elif state not in TRANSITION_STATES:
                raise RuntimeError(f"未知实例状态 {state!r}，请在控制台检查")
            failures = 0
        except (ApiError, TemporaryError) as error:
            kind = retry_kind(error)
            if not kind:
                raise
            logger(str(error))
            if kind == "capacity":
                next_start = 0
                failures = 0
                logger("当前资源不足，等待下一轮")
            elif kind == "busy":
                next_start = clock() + 600
                failures = 0
                logger("实例已有操作，先等待并查询状态")
            else:
                failures += 1
                delay = min(max(30, interval) * 2 ** min(failures - 1, 4), 300)
            on_event("retry", reason=kind)
        remaining = deadline - clock()
        if remaining <= 0:
            break
        duration = min(delay + random.uniform(0, 2), remaining)
        on_event("waiting", seconds=duration)
        if stop_event is not None:
            stop_event.wait(duration)
        else:
            sleep(duration)
    if cancelled():
        return stopped()
    logger("达到等待时限，脚本已停止；已提交的云端开机操作可能继续，请查看控制台。")
    on_event("timeout")
    return 2


def number(value, name, minimum):
    if isinstance(value, bool):
        raise ValueError(f"{name} 必须是数字")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"{name} 必须 >= {minimum}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="只列出实例，不开机")
    mode.add_argument("--check", action="store_true", help="只查询目标状态，不开机")
    args = parser.parse_args()
    config_path = args.config
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    elif config_path == ROOT / "config.json":
        config = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    else:
        raise ValueError(f"配置文件不存在：{config_path}")
    if not isinstance(config, dict):
        raise ValueError("配置文件必须是 JSON 对象")
    interval = number(config.get("interval_seconds", 10), "interval_seconds", 5)
    max_minutes = number(config.get("max_wait_minutes", 120), "max_wait_minutes", 0)
    public_key = os.getenv("COMPSHARE_PUBLIC_KEY", "").strip()
    private_key = os.getenv("COMPSHARE_PRIVATE_KEY", "").strip()
    if not public_key or not private_key:
        print("在本机输入账户中心的 API 公钥/私钥（输入隐藏，不保存）。")
        public_key = public_key or getpass.getpass("PublicKey: ").strip()
        private_key = private_key or getpass.getpass("PrivateKey: ").strip()
    if not public_key or not private_key:
        raise ValueError("API 公钥和私钥不能为空")
    client = Client(public_key, private_key, config.get("project_id", "").strip())
    region = config.get("region", "").strip()
    zone = config.get("zone", "").strip()
    instance_id = config.get("instance_id", "").strip()
    if args.list or not instance_id:
        instances = list(client.instances(region, zone))
        if not instances:
            raise ValueError("未找到实例，请检查 ProjectId、地域筛选或 API 密钥所属账号")
        for index, instance in enumerate(instances, 1):
            print(f"{index}. {instance.get('Name', '')} | {instance.get('UHostId')} | "
                  f"{instance.get('Region', '')}/{instance.get('Zone', '')} | "
                  f"{instance.get('GpuType', '')} | {instance.get('State')}")
        if args.list:
            return 0
        choice = int(input("请输入要自动开机的实例序号："))
        if not 1 <= choice <= len(instances):
            raise ValueError("实例序号超出范围")
        selected = instances[choice - 1]
        instance_id = selected["UHostId"]
        region = selected.get("Region") or region
        zone = selected.get("Zone") or zone
    elif not region or not zone:
        selected = client.instance(instance_id, region, zone)
        region = selected.get("Region") or region
        zone = selected.get("Zone") or zone
    if not region or not zone:
        raise ValueError("请在配置中填写实例 region、zone，取值可在控制台实例详情查看")
    if args.check:
        instance = client.instance(instance_id, region, zone)
        log(f"{instance_id} | {region}/{zone} | {instance.get('State')} | "
            f"GPU: {instance.get('GpuType', '')} x {instance.get('GPU', '?')}")
        return 0
    return wait_for_start(client, instance_id, region, zone, interval, max_minutes)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("已停止本地重试；已提交的云端开机操作可能继续，请查看控制台。")
        sys.exit(130)
    except (ApiError, TemporaryError, RuntimeError, ValueError, OSError, EOFError) as error:
        log(f"停止：{error}")
        sys.exit(1)
