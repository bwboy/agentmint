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
                connector_id="conn_test",
                connector_token="conn_sk_test",
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


if __name__ == "__main__":
    unittest.main()
