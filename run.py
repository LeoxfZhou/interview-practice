from __future__ import annotations

import errno
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from app.constants import APP_ID


HOST = "127.0.0.1"
DEFAULT_PORT = 8000
MAX_PORT_ATTEMPTS = 100
HEALTH_CHECK_ATTEMPTS = 100
HEALTH_CHECK_INTERVAL = 0.1


@dataclass
class LaunchTarget:
    port: int
    server_socket: Optional[socket.socket]
    unavailable_ports: list[int]
    existing_instance: bool


def parse_start_port(raw_port: Optional[str]) -> int:
    """读取用户指定的起始端口，并在启动前给出易懂的配置错误。"""
    if raw_port is None or not raw_port.strip():
        return DEFAULT_PORT
    try:
        port = int(raw_port)
    except ValueError as error:
        raise ValueError(f"PORT 必须是整数，当前值为：{raw_port!r}") from error
    if not 1024 <= port <= 65535:
        raise ValueError("PORT 必须在 1024 到 65535 之间")
    return port


def is_interview_deck_running(
    host: str,
    port: int,
    urlopen: Callable = urllib.request.urlopen,
) -> bool:
    """只认可带固定应用标识的健康响应，避免把其他 localhost 服务当成本应用。"""
    request = urllib.request.Request(
        f"http://{host}:{port}/api/health",
        headers={"Connection": "close"},
    )
    try:
        with urlopen(request, timeout=0.25) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return payload.get("status") == "ok" and payload.get("app") == APP_ID


def reserve_or_reuse_port(
    host: str,
    start_port: int,
    max_attempts: int = MAX_PORT_ATTEMPTS,
    socket_factory=socket.socket,
    instance_probe: Callable[[str, int], bool] = is_interview_deck_running,
) -> LaunchTarget:
    """复用已有答题本，否则原子预留下一个空闲端口。"""
    unavailable_ports: list[int] = []
    final_port = min(65535, start_port + max_attempts - 1)

    for port in range(start_port, final_port + 1):
        candidate = socket_factory(socket.AF_INET, socket.SOCK_STREAM)
        try:
            candidate.bind((host, port))
            candidate.listen(socket.SOMAXCONN)
            return LaunchTarget(port, candidate, unavailable_ports, False)
        except OSError as error:
            candidate.close()
            if error.errno not in {errno.EADDRINUSE, errno.EACCES}:
                raise
            if error.errno == errno.EADDRINUSE and instance_probe(host, port):
                return LaunchTarget(port, None, unavailable_ports, True)
            unavailable_ports.append(port)

    raise RuntimeError(
        f"从 {start_port} 到 {final_port} 都没有可用端口，请关闭占用程序或指定其他 PORT"
    )


def open_default_browser(
    url: str,
    runner: Callable = subprocess.run,
) -> bool:
    """使用 macOS 默认浏览器打开网址；失败只提示，不关闭已经启动的服务。"""
    try:
        runner(
            ["open", url],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (OSError, subprocess.CalledProcessError):
        print(f"无法自动打开默认浏览器，请手动访问：{url}")
        return False


def wait_until_ready_and_open(
    host: str,
    port: int,
    attempts: int = HEALTH_CHECK_ATTEMPTS,
    interval: float = HEALTH_CHECK_INTERVAL,
    instance_probe: Callable[[str, int], bool] = is_interview_deck_running,
    browser_opener: Callable[[str], bool] = open_default_browser,
    sleeper: Callable[[float], None] = time.sleep,
) -> bool:
    """等待 FastAPI 完成启动后再开浏览器，避免用户先看到连接失败页面。"""
    url = f"http://{host}:{port}"
    for _ in range(attempts):
        if instance_probe(host, port):
            return browser_opener(url)
        sleeper(interval)
    print(f"服务启动超时，请稍后手动访问：{url}")
    return False


def main() -> int:
    import uvicorn

    try:
        start_port = parse_start_port(os.getenv("PORT"))
        target = reserve_or_reuse_port(HOST, start_port)
    except (ValueError, RuntimeError) as error:
        print(f"启动失败：{error}")
        return 1

    url = f"http://{HOST}:{target.port}"
    if target.existing_instance:
        print(f"面试答题本已经运行，正在打开：{url}")
        return 0 if open_default_browser(url) else 1

    if target.unavailable_ports:
        skipped = "、".join(str(port) for port in target.unavailable_ports)
        print(f"端口 {skipped} 已被其他程序占用，已自动切换到 {target.port}。")

    print("")
    print("面试答题本已启动：")
    print(f"  {url}")
    print("")
    print("关闭网页不会停止服务；停止服务请按 Control-C 或关闭此 Terminal。")

    browser_thread = threading.Thread(
        target=wait_until_ready_and_open,
        args=(HOST, target.port),
        daemon=True,
        name="open-interview-deck",
    )
    browser_thread.start()

    assert target.server_socket is not None
    config = uvicorn.Config("app.main:app", host=HOST, port=target.port, reload=False)
    server = uvicorn.Server(config)
    try:
        # 直接交付已绑定的 socket，端口不会在检测完成后被另一个进程抢走。
        server.run(sockets=[target.server_socket])
    except KeyboardInterrupt:
        # Control-C 是用户主动停止服务，不应显示成应用错误 traceback。
        pass
    finally:
        target.server_socket.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
