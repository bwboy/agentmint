import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


def load_ws_client_module():
    path = Path(__file__).with_name("ws_client.py")
    package_name = "agentmint_hermes_plugin_ws_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(path.parent)]
    sys.modules[package_name] = package
    spec = importlib.util.spec_from_file_location(f"{package_name}.ws_client", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReconnectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ws_client = load_ws_client_module()

    def test_connect_backoff_retries_until_explicitly_closed(self):
        ws_client = self.ws_client

        async def run_case():
            client = ws_client.ArenaWSClient(
                platform_url="ws://arena.test/ws",
                runtime_node_id="rn_test",
                runtime_node_token="rn_sk_test",
                on_question=lambda msg: None,
            )
            attempts = 0
            original_schedule = ws_client.BACKOFF_SCHEDULE
            original_max_attempts = getattr(ws_client, "MAX_ATTEMPTS", None)
            ws_client.BACKOFF_SCHEDULE = [0]
            if hasattr(ws_client, "MAX_ATTEMPTS"):
                ws_client.MAX_ATTEMPTS = 1

            async def always_down():
                nonlocal attempts
                attempts += 1
                if attempts >= 3:
                    client._closed.set()
                raise OSError("platform down")

            client._connect_once = always_down
            try:
                result = await client._connect_with_backoff()
            finally:
                ws_client.BACKOFF_SCHEDULE = original_schedule
                if original_max_attempts is not None:
                    ws_client.MAX_ATTEMPTS = original_max_attempts

            return result, attempts

        result, attempts = asyncio.run(run_case())

        self.assertIsNone(result)
        self.assertGreaterEqual(attempts, 3)

    def test_connection_refused_is_treated_as_retryable_network_error(self):
        ws_client = self.ws_client

        async def run_case():
            client = ws_client.ArenaWSClient(
                platform_url="ws://arena.test/ws",
                runtime_node_id="rn_test",
                runtime_node_token="rn_sk_test",
                on_question=lambda msg: None,
            )
            attempts = 0
            original_schedule = ws_client.BACKOFF_SCHEDULE
            ws_client.BACKOFF_SCHEDULE = [0]

            async def refused():
                nonlocal attempts
                attempts += 1
                if attempts >= 3:
                    client._closed.set()
                raise ConnectionRefusedError("connect call failed")

            client._connect_once = refused
            try:
                result = await client._connect_with_backoff()
            finally:
                ws_client.BACKOFF_SCHEDULE = original_schedule

            return result, attempts

        result, attempts = asyncio.run(run_case())

        self.assertIsNone(result)
        self.assertGreaterEqual(attempts, 3)

    def test_run_reconnects_when_connected_socket_goes_idle(self):
        ws_client = self.ws_client

        class IdleWebSocket:
            def __init__(self):
                self.closed = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                return await self.recv()

            async def recv(self):
                await asyncio.sleep(60)

            async def close(self):
                self.closed = True

        async def run_case():
            client = ws_client.ArenaWSClient(
                platform_url="ws://arena.test/ws",
                runtime_node_id="rn_test",
                runtime_node_token="rn_sk_test",
                on_question=lambda msg: None,
            )
            original_timeout = getattr(ws_client, "SERVER_IDLE_TIMEOUT_SECONDS", None)
            ws_client.SERVER_IDLE_TIMEOUT_SECONDS = 0.01
            sockets = []

            async def fake_connect_with_backoff():
                if len(sockets) >= 2:
                    client._closed.set()
                    return None
                ws = IdleWebSocket()
                sockets.append(ws)
                return ws

            client._connect_with_backoff = fake_connect_with_backoff
            try:
                await asyncio.wait_for(client._run(), timeout=1)
            finally:
                if original_timeout is None:
                    delattr(ws_client, "SERVER_IDLE_TIMEOUT_SECONDS")
                else:
                    ws_client.SERVER_IDLE_TIMEOUT_SECONDS = original_timeout

            return sockets

        sockets = asyncio.run(run_case())

        self.assertEqual(len(sockets), 2)
        self.assertTrue(sockets[0].closed)

    def test_send_pairing_required_uses_special_message_type(self):
        ws_client = self.ws_client

        async def run_case():
            client = ws_client.ArenaWSClient(
                platform_url="ws://arena.test/ws",
                runtime_node_id="rn_test",
                runtime_node_token="rn_sk_test",
                on_question=lambda msg: None,
            )
            sent = []

            async def fake_send(payload):
                sent.append(payload)
                return True

            client.send = fake_send
            ok = await client.send_pairing_required(
                "probe_a_test_123",
                code="KJ5S6H25",
                command="hermes pairing approve agentmint KJ5S6H25",
                agent_id="a_test",
            )
            return ok, sent

        ok, sent = asyncio.run(run_case())

        self.assertTrue(ok)
        self.assertEqual(sent, [{
            "type": "pairing_required",
            "request_id": "probe_a_test_123",
            "agent_id": "a_test",
            "code": "KJ5S6H25",
            "command": "hermes pairing approve agentmint KJ5S6H25",
        }])


if __name__ == "__main__":
    unittest.main()
