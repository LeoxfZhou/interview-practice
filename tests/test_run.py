from __future__ import annotations

import errno
import json
import subprocess
import unittest

from app.constants import APP_ID
from run import (
    is_interview_deck_running,
    open_default_browser,
    parse_start_port,
    reserve_or_reuse_port,
    wait_until_ready_and_open,
)


class FakeSocket:
    def __init__(self, occupied: bool = False) -> None:
        self.occupied = occupied
        self.bound_to = None
        self.listen_backlog = None
        self.closed = False

    def bind(self, address) -> None:
        if self.occupied:
            raise OSError(errno.EADDRINUSE, "address already in use")
        self.bound_to = address

    def listen(self, backlog: int) -> None:
        self.listen_backlog = backlog

    def close(self) -> None:
        self.closed = True


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class PortSelectionTests(unittest.TestCase):
    def test_default_and_custom_start_port(self) -> None:
        self.assertEqual(parse_start_port(None), 8000)
        self.assertEqual(parse_start_port(" 9000 "), 9000)

    def test_invalid_port_has_clear_error(self) -> None:
        for raw_port in ("abc", "80", "70000"):
            with self.subTest(raw_port=raw_port), self.assertRaises(ValueError):
                parse_start_port(raw_port)

    def test_health_probe_requires_application_identity(self) -> None:
        def correct_urlopen(*_args, **_kwargs):
            return FakeResponse({"status": "ok", "app": APP_ID})

        def unrelated_urlopen(*_args, **_kwargs):
            return FakeResponse({"status": "ok", "app": "another-app"})

        self.assertTrue(is_interview_deck_running("127.0.0.1", 8000, correct_urlopen))
        self.assertFalse(is_interview_deck_running("127.0.0.1", 8000, unrelated_urlopen))

    def test_existing_interview_deck_is_reused(self) -> None:
        target = reserve_or_reuse_port(
            "127.0.0.1",
            8000,
            max_attempts=2,
            socket_factory=lambda *_args: FakeSocket(occupied=True),
            instance_probe=lambda _host, port: port == 8000,
        )
        self.assertTrue(target.existing_instance)
        self.assertEqual(target.port, 8000)
        self.assertIsNone(target.server_socket)

    def test_unrelated_service_switches_to_next_port(self) -> None:
        sockets = [FakeSocket(occupied=True), FakeSocket()]

        def socket_factory(*_args):
            return sockets.pop(0)

        target = reserve_or_reuse_port(
            "127.0.0.1",
            8000,
            max_attempts=2,
            socket_factory=socket_factory,
            instance_probe=lambda *_args: False,
        )
        self.assertFalse(target.existing_instance)
        self.assertEqual(target.port, 8001)
        self.assertEqual(target.unavailable_ports, [8000])
        self.assertEqual(target.server_socket.bound_to, ("127.0.0.1", 8001))

    def test_exhausted_range_has_clear_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "没有可用端口"):
            reserve_or_reuse_port(
                "127.0.0.1",
                8000,
                max_attempts=2,
                socket_factory=lambda *_args: FakeSocket(occupied=True),
                instance_probe=lambda *_args: False,
            )

    def test_ready_service_opens_default_browser(self) -> None:
        opened = []
        result = wait_until_ready_and_open(
            "127.0.0.1",
            8000,
            attempts=2,
            interval=0,
            instance_probe=lambda *_args: True,
            browser_opener=lambda url: opened.append(url) or True,
            sleeper=lambda _interval: None,
        )
        self.assertTrue(result)
        self.assertEqual(opened, ["http://127.0.0.1:8000"])

    def test_health_timeout_does_not_open_browser(self) -> None:
        opened = []
        result = wait_until_ready_and_open(
            "127.0.0.1",
            8000,
            attempts=2,
            interval=0,
            instance_probe=lambda *_args: False,
            browser_opener=lambda url: opened.append(url) or True,
            sleeper=lambda _interval: None,
        )
        self.assertFalse(result)
        self.assertEqual(opened, [])

    def test_browser_open_failure_is_non_fatal(self) -> None:
        def failing_runner(*_args, **_kwargs):
            raise subprocess.CalledProcessError(1, "open")

        self.assertFalse(open_default_browser("http://127.0.0.1:8000", failing_runner))


if __name__ == "__main__":
    unittest.main()
