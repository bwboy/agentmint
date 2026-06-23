import importlib.util
import asyncio
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


def load_adapter_module():
    path = Path(__file__).with_name("adapter.py")
    package_name = "agentmint_hermes_plugin_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(path.parent)]
    sys.modules[package_name] = package
    spec = importlib.util.spec_from_file_location(f"{package_name}.adapter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class UsageExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = load_adapter_module()

    def test_platform_hint_discourages_approval_triggering_commands(self):
        hint = self.adapter.AGENTMINT_PLATFORM_HINT
        self.assertIn("curl ... | python", hint)
        self.assertIn("do not request approval", hint)
        self.assertIn("safer alternative", hint)

    def test_extract_usage_from_direct_usage_metadata(self):
        self.assertEqual(self.adapter._extract_usage({
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            }
        }), {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        })

    def test_extract_usage_from_hermes_turn_result_metadata(self):
        self.assertEqual(self.adapter._extract_usage({
            "prompt_tokens": 11,
            "completion_tokens": 22,
            "total_tokens": 33,
        }), {
            "prompt_tokens": 11,
            "completion_tokens": 22,
            "total_tokens": 33,
        })

    def test_extract_usage_from_usage_object(self):
        usage = SimpleNamespace(prompt_tokens=12, completion_tokens=23, total_tokens=35)
        self.assertEqual(self.adapter._extract_usage({"usage": usage}), {
            "prompt_tokens": 12,
            "completion_tokens": 23,
            "total_tokens": 35,
        })

    def test_extract_usage_from_hermes_gateway_result_tokens(self):
        self.assertEqual(self.adapter._extract_usage({
            "input_tokens": 13,
            "output_tokens": 24,
            "cache_read_tokens": 5,
        }), {
            "prompt_tokens": 13,
            "completion_tokens": 24,
            "total_tokens": 37,
            "cached_tokens": 5,
        })

    def test_estimate_usage_marks_source_and_nonzero_total(self):
        usage = self.adapter._estimate_usage("Explain Rust ownership", "Ownership controls moves and borrows.", "hermes")

        self.assertGreater(usage["prompt_tokens"], 0)
        self.assertGreater(usage["completion_tokens"], 0)
        self.assertEqual(usage["total_tokens"], usage["prompt_tokens"] + usage["completion_tokens"])
        self.assertTrue(usage["estimated"])
        self.assertEqual(usage["source"], "agentmint_plugin_estimate")

    def test_capture_handler_result_usage_by_chat_id(self):
        adapter_mod = self.adapter

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {}

            def build_source(self, **kwargs):
                return SimpleNamespace(**kwargs)

        async def run_case():
            adapter = TestAdapter()

            async def handler(event):
                return {
                    "final_response": "ok",
                    "input_tokens": 14,
                    "output_tokens": 25,
                    "model": "test-model",
                }

            adapter.set_message_handler(handler)
            event = SimpleNamespace(source=SimpleNamespace(chat_id="req_1"))
            await adapter._message_handler(event)
            return adapter._last_turn_metadata["req_1"]

        self.assertEqual(asyncio.run(run_case()), {
            "prompt_tokens": 14,
            "completion_tokens": 25,
            "total_tokens": 39,
            "model": "test-model",
        })

    def test_send_uploads_usage_captured_from_handler_result(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def mark(self, request_id, status, **kwargs):
                self.marked.append((request_id, status, kwargs))
                return True

        class FakeClient:
            def __init__(self):
                self.sent = None

            async def send_answer(self, request_id, **kwargs):
                self.sent = (request_id, kwargs)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {
                    "req_2": {
                        "prompt_tokens": 10,
                        "completion_tokens": 15,
                        "total_tokens": 25,
                        "model": "test-model",
                    }
                }
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                await adapter.send("req_2", "answer text", metadata={"notify": True})
            finally:
                adapter_mod.SendResult = original_send_result
            return adapter._client.sent, adapter._queue.marked

        sent, marked = asyncio.run(run_case())
        self.assertEqual(sent[0], "req_2")
        self.assertEqual(sent[1]["model"], "test-model")
        self.assertEqual(sent[1]["usage"], {
            "prompt_tokens": 10,
            "completion_tokens": 15,
            "total_tokens": 25,
        })
        self.assertEqual(marked[0][2]["answer"]["usage"], {
            "prompt_tokens": 10,
            "completion_tokens": 15,
            "total_tokens": 25,
        })

    def test_send_estimates_usage_when_hermes_provides_none(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def mark(self, request_id, status, **kwargs):
                self.marked.append((request_id, status, kwargs))
                return True

            def by_request_id(self, request_id):
                return None

        class FakeClient:
            def __init__(self):
                self.sent = None

            async def send_answer(self, request_id, **kwargs):
                self.sent = (request_id, kwargs)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {}
                self._prompt_text_by_request = {"req_3": "Question prompt text"}
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                await adapter.send("req_3", "Answer text", metadata={"notify": True})
            finally:
                adapter_mod.SendResult = original_send_result
            return adapter._client.sent, adapter._queue.marked, adapter._prompt_text_by_request

        sent, marked, prompts = asyncio.run(run_case())
        usage = sent[1]["usage"]
        self.assertGreater(usage["total_tokens"], 0)
        self.assertTrue(usage["estimated"])
        self.assertEqual(usage["source"], "agentmint_plugin_estimate")
        self.assertEqual(marked[0][2]["answer"]["usage"], usage)
        self.assertNotIn("req_3", prompts)

    def test_send_creates_synthetic_queue_row_when_answer_has_no_job(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []
                self.inserted = []

            def mark(self, request_id, status, **kwargs):
                self.marked.append((request_id, status, kwargs))
                return len(self.inserted) > 0

            def by_request_id(self, request_id):
                return None

            def upsert_pending(self, request_id, chat_id, question):
                self.inserted.append((request_id, chat_id, question))
                return True

        class FakeClient:
            def __init__(self):
                self.sent = None

            async def send_answer(self, request_id, **kwargs):
                self.sent = (request_id, kwargs)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {}
                self._prompt_text_by_request = {"req_missing": "Prompt text"}
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                await adapter.send("req_missing", "Answer text", metadata={})
            finally:
                adapter_mod.SendResult = original_send_result
            return adapter._queue.inserted, adapter._queue.marked, adapter._client.sent

        inserted, marked, sent = asyncio.run(run_case())
        self.assertEqual(inserted[0][0], "req_missing")
        self.assertTrue(inserted[0][2]["synthetic"])
        self.assertEqual(marked[0][1], "answered")
        self.assertEqual(marked[1][1], "answered")
        self.assertEqual(marked[2][1], "uploaded")
        self.assertEqual(sent[0], "req_missing")


class YamlConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = load_adapter_module()

    def tearDown(self):
        for key in (
            "AGENTMINT_CONNECTOR_ID",
            "AGENTMINT_CONNECTOR_TOKEN",
            "AGENTMINT_PLATFORM_URL",
            "AGENTMINT_MAX_CONCURRENT",
            "AGENTMINT_QUEUE_DB",
            "AGENTMINT_HOME_CHANNEL",
        ):
            os.environ.pop(key, None)

    def test_apply_yaml_config_accepts_nested_extra_shape(self):
        out = self.adapter._apply_yaml_config({
            "enabled": True,
            "extra": {
                "connector_id": "conn_from_yaml",
                "connector_token": "conn_sk_from_yaml",
                "platform_url": "ws://arena.example/ws",
                "home_channel": "agentmint-home",
            },
        }, {})

        self.assertEqual(out["connector_id"], "conn_from_yaml")
        self.assertEqual(out["connector_token"], "conn_sk_from_yaml")
        self.assertEqual(out["platform_url"], "ws://arena.example/ws")
        self.assertEqual(out["home_channel"], {
            "chat_id": "agentmint-home",
            "name": "AgentMint",
        })
        self.assertEqual(os.environ["AGENTMINT_CONNECTOR_ID"], "conn_from_yaml")
        self.assertEqual(os.environ["AGENTMINT_CONNECTOR_TOKEN"], "conn_sk_from_yaml")
        self.assertEqual(os.environ["AGENTMINT_HOME_CHANNEL"], "agentmint-home")

    def test_apply_yaml_config_accepts_home_channel_dict(self):
        out = self.adapter._apply_yaml_config({
            "enabled": True,
            "extra": {
                "connector_id": "conn_from_yaml",
                "connector_token": "conn_sk_from_yaml",
                "home_channel": {
                    "chat_id": "agentmint-home",
                    "name": "Arena Results",
                    "thread_id": "thread-1",
                },
            },
        }, {})

        self.assertEqual(out["home_channel"], {
            "chat_id": "agentmint-home",
            "name": "Arena Results",
            "thread_id": "thread-1",
        })
        self.assertEqual(os.environ["AGENTMINT_HOME_CHANNEL"], "agentmint-home")

    def test_apply_yaml_config_uses_platform_cfg_argument_from_hermes(self):
        full_yaml_cfg = {
            "gateway": {
                "platforms": {
                    "agentmint": {
                        "enabled": True,
                        "extra": {
                            "connector_id": "conn_from_platform_arg",
                            "connector_token": "conn_sk_from_platform_arg",
                            "platform_url": "ws://arena.example/ws",
                            "home_channel": "agentmint-home",
                        },
                    },
                },
            },
        }
        platform_cfg = full_yaml_cfg["gateway"]["platforms"]["agentmint"]

        out = self.adapter._apply_yaml_config(full_yaml_cfg, platform_cfg)

        self.assertEqual(out["connector_id"], "conn_from_platform_arg")
        self.assertEqual(out["connector_token"], "conn_sk_from_platform_arg")
        self.assertEqual(out["home_channel"], {
            "chat_id": "agentmint-home",
            "name": "AgentMint",
        })

    def test_env_enablement_returns_home_channel_dict(self):
        os.environ["AGENTMINT_CONNECTOR_ID"] = "conn_from_env"
        os.environ["AGENTMINT_CONNECTOR_TOKEN"] = "conn_sk_from_env"
        os.environ["AGENTMINT_HOME_CHANNEL"] = "agentmint-home"

        out = self.adapter._env_enablement()

        self.assertEqual(out["home_channel"], {
            "chat_id": "agentmint-home",
            "name": "AgentMint",
        })

    def test_check_requirements_accepts_config_yaml_without_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text(
                """
plugins:
  enabled:
    - platforms/agentmint

gateway:
  platforms:
    agentmint:
      enabled: true
      extra:
        connector_id: conn_from_file
        connector_token: conn_sk_from_file
        platform_url: ws://arena.example/ws
""".strip(),
                encoding="utf-8",
            )
            os.environ["HERMES_CONFIG"] = str(config_path)
            try:
                self.assertTrue(self.adapter.check_requirements())
            finally:
                os.environ.pop("HERMES_CONFIG", None)


class QueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = load_adapter_module()

    def test_mark_reports_whether_row_was_updated(self):
        queue_mod = __import__(f"{self.adapter.__package__}.queue", fromlist=["JobQueue"])

        with tempfile.TemporaryDirectory() as tmp:
            queue = queue_mod.JobQueue(str(Path(tmp) / "jobs.db"))
            try:
                self.assertFalse(queue.mark("missing", "answered", answer={"text": "no row"}))
                self.assertTrue(queue.upsert_pending("req_1", "req_1", {"title": "Question"}))
                self.assertTrue(queue.mark("req_1", "answered", answer={"text": "ok"}))
                self.assertEqual(queue.by_request_id("req_1")["answer"], {"text": "ok"})
            finally:
                queue.close()


if __name__ == "__main__":
    unittest.main()
