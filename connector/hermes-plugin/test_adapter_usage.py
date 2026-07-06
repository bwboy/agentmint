import importlib.util
import asyncio
import os
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
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

    def test_adapter_requires_finalize_for_streaming_upload(self):
        self.assertTrue(self.adapter.ArenaAdapter.SUPPORTS_MESSAGE_EDITING)
        self.assertTrue(self.adapter.ArenaAdapter.REQUIRES_EDIT_FINALIZE)
        self.assertGreater(self.adapter.ArenaAdapter.MAX_MESSAGE_LENGTH, 100_000)

    def test_connect_accepts_gateway_reconnect_keyword(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def close(self):
                pass

        class FakeClient:
            def __init__(self, **kwargs):
                self.is_connected = True

            def start(self):
                pass

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self.connector_id = "conn_test"
                self.connector_token = "conn_sk_test"
                self.platform_url = "ws://arena.test/ws"
                self.queue_db = ":memory:"
                self.max_concurrent = 1
                self._queue = FakeQueue()
                self._client = None
                self._start_time = 0

            async def _on_question(self, msg):
                pass

            async def _on_reconnected(self):
                pass

            def _quota_snapshot(self):
                return {}

            def _mark_connected(self):
                self.marked_connected = True

        async def run_case():
            original_client = adapter_mod.ArenaWSClient
            adapter_mod.ArenaWSClient = FakeClient
            try:
                adapter = TestAdapter()
                return await adapter.connect(is_reconnect=True), adapter.marked_connected
            finally:
                adapter_mod.ArenaWSClient = original_client

        self.assertEqual(asyncio.run(run_case()), (True, True))

    def test_platform_hint_discourages_approval_triggering_commands(self):
        hint = self.adapter.AGENTMINT_PLATFORM_HINT
        self.assertIn("curl ... | python", hint)
        self.assertIn("do not request approval", hint)
        self.assertIn("safer alternative", hint)

    def test_formatted_prompt_includes_tool_policy(self):
        prompt = self.adapter._format_prompt(
            "Research question",
            "Find current data",
            ["wow"],
            "tester",
        )

        self.assertIn("AgentMint tool policy", prompt)
        self.assertIn("curl ... | python3", prompt)
        self.assertIn("do not ask for approval", prompt)
        self.assertIn("fetch it as data first", prompt)

    def test_formatted_prompt_tells_agent_to_inspect_image_attachments(self):
        prompt = self.adapter._format_prompt(
            "这几个人都是谁",
            "",
            [],
            "tester",
            attachments=[{
                "filename": "screen.jpeg",
                "type": "image",
                "url": "http://arena/api/files/object/uploads/screen.jpeg",
            }],
        )

        self.assertIn("附件包含图片", prompt)
        self.assertIn("必须先查看或下载图片", prompt)
        self.assertIn("screen.jpeg (image): http://arena/api/files/object/uploads/screen.jpeg", prompt)

    def test_formatted_prompt_can_inline_image_attachment_data(self):
        prompt = self.adapter._format_prompt(
            "这几个人都是谁",
            "",
            [],
            "tester",
            attachments=[{
                "filename": "screen.jpeg",
                "type": "image",
                "mime": "image/jpeg",
                "url": "http://arena/api/files/object/uploads/screen.jpeg",
                "inline_data_url": "data:image/jpeg;base64,abcd",
            }],
        )

        self.assertIn("图片内容已内联", prompt)
        self.assertIn("data:image/jpeg;base64,abcd", prompt)

    def test_prepare_prompt_attachments_downloads_small_images(self):
        adapter_mod = self.adapter

        class FakeHeaders:
            def get(self, name):
                return "image/png" if name == "Content-Type" else None

        class FakeResponse:
            headers = FakeHeaders()

            def read(self, size):
                return b"png-bytes"

        @contextmanager
        def fake_urlopen(req, timeout=0):
            self.assertEqual(req.full_url, "http://arena/files/screen.png")
            self.assertEqual(timeout, 8)
            yield FakeResponse()

        original_urlopen = adapter_mod.urllib.request.urlopen
        adapter_mod.urllib.request.urlopen = fake_urlopen
        try:
            attachments = adapter_mod._prepare_prompt_attachments([{
                "filename": "screen.png",
                "type": "image",
                "mime": "image/png",
                "size_bytes": 9,
                "url": "http://arena/files/screen.png",
            }])
        finally:
            adapter_mod.urllib.request.urlopen = original_urlopen

        self.assertEqual(attachments[0]["inline_data_url"], "data:image/png;base64,cG5nLWJ5dGVz")

    def test_tool_trace_detection_does_not_block_explanatory_answers(self):
        self.assertFalse(self.adapter._looks_like_tool_trace(
            "我先说明一下：browser_navigate 和 terminal 是工具名，不是最终答案。"
        ))

    def test_vision_tool_trace_is_not_uploaded_as_final_answer(self):
        self.assertTrue(self.adapter._looks_like_tool_trace(
            '👁️ vision_analyze: "这张图片里有三位人物，请识别他们分别是《荒野大镖客：救赎2》..."'
        ))

    def test_on_question_uses_stable_agentmint_identity_for_pairing(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def upsert_pending(self, request_id, chat_id, question):
                return True

        class FakeClient:
            def __init__(self):
                self.acked = []

            async def send_ack(self, request_id):
                self.acked.append(request_id)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._queue = FakeQueue()
                self._client = FakeClient()
                self._job_started_at = {}
                self._prompt_text_by_request = {}
                self.events = []

            def build_source(self, **kwargs):
                return SimpleNamespace(**kwargs)

            async def handle_message(self, event):
                self.events.append(event)

        async def run_case():
            adapter = TestAdapter()
            original_message_event = adapter_mod.MessageEvent
            original_message_type = adapter_mod.MessageType
            adapter_mod.MessageEvent = lambda **kwargs: SimpleNamespace(**kwargs)
            adapter_mod.MessageType = SimpleNamespace(TEXT="text")
            try:
                await adapter._on_question({
                    "request_id": "req_pairing",
                    "title": "Question",
                    "body": "",
                    "tags": [],
                    "asker": {"nickname": "alice", "trust_level": 3},
                })
                return adapter.events[0].source, adapter._client.acked
            finally:
                adapter_mod.MessageEvent = original_message_event
                adapter_mod.MessageType = original_message_type

        source, acked = asyncio.run(run_case())

        self.assertEqual(acked, ["req_pairing"])
        self.assertEqual(source.user_id, "agentmint-platform")
        self.assertEqual(source.user_name, "AgentMint")
        self.assertNotIn("alice", source.user_id)

    def test_on_question_uses_conversation_id_as_chat_id(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.saved = None

            def upsert_pending(self, request_id, chat_id, question):
                self.saved = SimpleNamespace(
                    request_id=request_id,
                    chat_id=chat_id,
                    question=question,
                )
                return True

        class FakeClient:
            def __init__(self):
                self.acked = []

            async def send_ack(self, request_id):
                self.acked.append(request_id)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._queue = FakeQueue()
                self._client = FakeClient()
                self._job_started_at = {}
                self._prompt_text_by_request = {}
                self._active_request_by_chat = {}
                self._warm_conversations = set()
                self._conversation_locks = {}
                self.events = []

            def build_source(self, **kwargs):
                return SimpleNamespace(**kwargs)

            async def handle_message(self, event):
                self.events.append(event)

        async def run_case():
            adapter = TestAdapter()
            original_message_event = adapter_mod.MessageEvent
            original_message_type = adapter_mod.MessageType
            adapter_mod.MessageEvent = lambda **kwargs: SimpleNamespace(**kwargs)
            adapter_mod.MessageType = SimpleNamespace(TEXT="text")
            try:
                await adapter._on_question({
                    "request_id": "req_fu",
                    "conversation_id": "conv_q_root_a_1",
                    "turn_type": "followup",
                    "title": "More?",
                    "body": "Can you expand?",
                    "tags": ["python"],
                    "asker": {"nickname": "alice", "trust_level": 3},
                    "root_question": {
                        "title": "Root",
                        "body": "How do decorators work?",
                        "tags": ["python"],
                    },
                    "quoted_answer": {
                        "text": "Original answer about wrappers.",
                    },
                })
                return adapter
            finally:
                adapter_mod.MessageEvent = original_message_event
                adapter_mod.MessageType = original_message_type

        adapter = asyncio.run(run_case())

        self.assertEqual(adapter._client.acked, ["req_fu"])
        self.assertEqual(adapter._queue.saved.request_id, "req_fu")
        self.assertEqual(adapter._queue.saved.chat_id, "conv_q_root_a_1")
        self.assertEqual(adapter._queue.saved.question["conversation_id"], "conv_q_root_a_1")
        self.assertEqual(adapter._queue.saved.question["turn_type"], "followup")
        self.assertEqual(adapter.events[0].source.chat_id, "conv_q_root_a_1")
        self.assertEqual(adapter.events[0].message_id, "req_fu")
        self.assertIn("Original answer about wrappers.", adapter.events[0].text)
        self.assertIn("Root", adapter.events[0].text)

    def test_format_followup_prompt_warm_omits_quote_context(self):
        prompt = self.adapter._format_followup_prompt(
            "More?",
            root_question={"title": "Root", "body": "Root body", "tags": ["python"]},
            quoted_answer={"text": "Original answer"},
            include_context=False,
        )

        self.assertIn("More?", prompt)
        self.assertIn("AgentMint tool policy", prompt)
        self.assertNotIn("Root body", prompt)
        self.assertNotIn("Original answer", prompt)

    def test_format_followup_prompt_cold_includes_quote_context(self):
        prompt = self.adapter._format_followup_prompt(
            "More?",
            root_question={"title": "Root", "body": "Root body", "tags": ["python"]},
            quoted_answer={"text": "Original answer"},
            include_context=True,
        )

        self.assertIn("Root", prompt)
        self.assertIn("Root body", prompt)
        self.assertIn("Original answer", prompt)
        self.assertIn("More?", prompt)
        self.assertIn("AgentMint tool policy", prompt)

    def test_send_uses_active_request_for_conversation_chat_id(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def mark(self, request_id, status, **kwargs):
                self.marked.append((request_id, status, kwargs))
                return True

            def by_request_id(self, request_id):
                return {
                    "request_id": request_id,
                    "chat_id": "conv_q_root_a_1",
                    "status": "pending",
                    "question": {"title": "Follow-up", "body": "", "tags": [], "asker": {"nickname": "tester"}},
                    "answer": None,
                }

        class FakeClient:
            def __init__(self):
                self.sent = None

            async def send_answer(self, request_id, **kwargs):
                self.sent = (request_id, kwargs)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._active_request_by_chat = {"conv_q_root_a_1": "req_fu"}
                self._last_turn_metadata = {
                    "req_fu": {
                        "prompt_tokens": 10,
                        "completion_tokens": 15,
                        "total_tokens": 25,
                        "model": "test-model",
                    }
                }
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self._streaming_answers = {}
                self.usage_wait_seconds = 0
                self._prompt_text_by_request = {"req_fu": "Prompt"}
                self._job_started_at = {}
                self._warm_conversations = set()
                self._queue = FakeQueue()
                self._client = FakeClient()

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                result = await adapter.send("conv_q_root_a_1", "answer text", metadata={"notify": True})
            finally:
                adapter_mod.SendResult = original_send_result
            return result, adapter._client.sent, adapter._queue.marked, adapter._warm_conversations

        result, sent, marked, warm = asyncio.run(run_case())

        self.assertTrue(result.success)
        self.assertEqual(sent[0], "req_fu")
        self.assertEqual(marked[0][0], "req_fu")
        self.assertEqual(marked[-1][0], "req_fu")
        self.assertIn("conv_q_root_a_1", warm)

    def test_reconnected_pending_followup_replays_existing_conversation_chat(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def counts(self):
                return {"pending": 1, "answered": 0, "uploaded": 0, "failed": 0}

            def list_resumable(self):
                return [{
                    "request_id": "req_replay_fu",
                    "chat_id": "conv_q_root_a_1",
                    "status": "pending",
                    "question": {
                        "conversation_id": "conv_q_root_a_1",
                        "turn_type": "followup",
                        "title": "More?",
                        "body": "Can you expand?",
                        "tags": ["python"],
                        "asker": {"nickname": "alice"},
                        "deadline_at": "2026-07-01T00:00:00Z",
                        "root_question": {"title": "Root", "body": "Root body", "tags": ["python"]},
                        "quoted_answer": {"text": "Original answer"},
                    },
                    "answer": None,
                }]

            def mark(self, request_id, status, **kwargs):
                self.marked.append((request_id, status, kwargs))
                return True

        class FakeClient:
            def __init__(self):
                self.acked = []

            async def send_ack(self, request_id):
                self.acked.append(request_id)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._queue = FakeQueue()
                self._client = FakeClient()
                self._job_started_at = {}
                self._prompt_text_by_request = {}
                self._active_request_by_chat = {}
                self._warm_conversations = set()
                self._conversation_locks = {}
                self.events = []

            def build_source(self, **kwargs):
                return SimpleNamespace(**kwargs)

            async def handle_message(self, event):
                self.events.append(event)

        async def run_case():
            adapter = TestAdapter()
            original_message_event = adapter_mod.MessageEvent
            original_message_type = adapter_mod.MessageType
            adapter_mod.MessageEvent = lambda **kwargs: SimpleNamespace(**kwargs)
            adapter_mod.MessageType = SimpleNamespace(TEXT="text")
            try:
                await adapter._on_reconnected()
            finally:
                adapter_mod.MessageEvent = original_message_event
                adapter_mod.MessageType = original_message_type
            return adapter

        adapter = asyncio.run(run_case())

        self.assertEqual(adapter._client.acked, ["req_replay_fu"])
        self.assertEqual(adapter.events[0].source.chat_id, "conv_q_root_a_1")
        self.assertEqual(adapter.events[0].message_id, "req_replay_fu")
        self.assertIn("Original answer", adapter.events[0].text)
        self.assertEqual(adapter._queue.marked, [])

    def test_send_pairing_uses_queue_chat_lookup_without_active_mapping(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def by_chat(self, chat_id):
                self.by_chat_arg = chat_id
                return {
                    "request_id": "req_late_pairing",
                    "chat_id": "conv_q_root_a_1",
                    "status": "pending",
                    "question": {"title": "Follow-up", "body": "", "tags": []},
                    "answer": None,
                }

            def by_request_id(self, request_id):
                self.by_request_id_arg = request_id
                return {
                    "request_id": request_id,
                    "chat_id": "conv_q_root_a_1",
                    "status": "pending",
                    "question": {"title": "Follow-up", "body": "", "tags": []},
                    "answer": None,
                }

            def mark(self, request_id, status, **kwargs):
                self.marked.append((request_id, status, kwargs))
                return True

        class FakeClient:
            def __init__(self):
                self.pairing = []

            async def send_pairing_required(self, request_id, *, code, command):
                self.pairing.append((request_id, code, command))
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._active_request_by_chat = {}
                self._last_turn_metadata = {}
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self._streaming_answers = {}
                self.usage_wait_seconds = 0
                self._prompt_text_by_request = {}
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        pairing_text = "pairing code: ABCD-1234\nhermes pairing approve agentmint ABCD-1234"

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                result = await adapter.send("conv_q_root_a_1", pairing_text, metadata={"notify": True})
            finally:
                adapter_mod.SendResult = original_send_result
            return result, adapter

        result, adapter = asyncio.run(run_case())

        self.assertTrue(result.success)
        self.assertEqual(adapter._queue.by_chat_arg, "conv_q_root_a_1")
        self.assertEqual(adapter._queue.by_request_id_arg, "req_late_pairing")
        self.assertEqual(adapter._client.pairing[0][0], "req_late_pairing")
        self.assertEqual(adapter._queue.marked, [("req_late_pairing", "failed", {"error": "pairing_required"})])

    def test_reconnected_answered_upload_marks_conversation_warm(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def counts(self):
                return {"pending": 0, "answered": 1, "uploaded": 0, "failed": 0}

            def list_resumable(self):
                return [{
                    "request_id": "req_answered_fu",
                    "chat_id": "conv_q_root_a_1",
                    "status": "answered",
                    "question": {"title": "More?", "body": "", "tags": []},
                    "answer": {
                        "text": "Answer",
                        "model": "hermes",
                        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
                        "capability": {"engine": {"provider": "hermes", "model": "hermes"}},
                        "duration_ms": 42,
                    },
                }]

            def mark(self, request_id, status, **kwargs):
                self.marked.append((request_id, status, kwargs))
                return True

        class FakeClient:
            def __init__(self):
                self.answers = []

            async def send_answer(self, request_id, **kwargs):
                self.answers.append((request_id, kwargs))
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._queue = FakeQueue()
                self._client = FakeClient()
                self._warm_conversations = set()

        async def run_case():
            adapter = TestAdapter()
            await adapter._on_reconnected()
            return adapter

        adapter = asyncio.run(run_case())

        self.assertEqual(adapter._client.answers[0][0], "req_answered_fu")
        self.assertEqual(adapter._queue.marked, [("req_answered_fu", "uploaded", {})])
        self.assertIn("conv_q_root_a_1", adapter._warm_conversations)

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

    def test_metadata_debug_summary_omits_message_text(self):
        summary = self.adapter._metadata_debug_summary({
            "final_response": "secret answer body",
            "input_tokens": 14,
            "output_tokens": 25,
            "model": "test-model",
        })

        self.assertIn("input_tokens", summary)
        self.assertIn("output_tokens", summary)
        self.assertIn("39:provider", summary)
        self.assertNotIn("secret answer body", summary)

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
                self._last_turn_metadata = {
                    "req_2": {
                        "prompt_tokens": 10,
                        "completion_tokens": 15,
                        "total_tokens": 25,
                        "model": "test-model",
                    }
                }
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self.usage_wait_seconds = 0
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
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self.usage_wait_seconds = 0
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
                await asyncio.wait_for(next(iter(adapter._background_upload_tasks)), timeout=1)
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

    def test_send_waits_for_handler_result_usage_before_uploading(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def mark(self, request_id, status, **kwargs):
                self.marked.append((request_id, status, kwargs))
                return True

            def by_request_id(self, request_id):
                return {
                    "request_id": request_id,
                    "status": "pending",
                    "question": {"title": "Question", "body": "", "tags": [], "asker": {"nickname": "tester"}},
                    "answer": None,
                }

        class FakeClient:
            def __init__(self):
                self.sent = None

            async def send_answer(self, request_id, **kwargs):
                self.sent = (request_id, kwargs)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {}
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self.usage_wait_seconds = 0.2
                self._prompt_text_by_request = {"req_late": "Question prompt text"}
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                result = await adapter.send("req_late", "Answer text", metadata={"notify": True})
                self.assertTrue(result.success)
                self.assertIsNone(adapter._client.sent)
                adapter._capture_turn_metadata(
                    SimpleNamespace(source=SimpleNamespace(chat_id="req_late")),
                    {"input_tokens": 14, "output_tokens": 25, "model": "provider-model"},
                )
                await asyncio.wait_for(next(iter(adapter._background_upload_tasks)), timeout=1)
            finally:
                adapter_mod.SendResult = original_send_result
            return adapter._client.sent, adapter._queue.marked

        sent, marked = asyncio.run(run_case())
        self.assertEqual(sent[1]["model"], "provider-model")
        self.assertEqual(sent[1]["usage"], {
            "prompt_tokens": 14,
            "completion_tokens": 25,
            "total_tokens": 39,
        })
        self.assertFalse(sent[1]["usage"].get("estimated", False))
        self.assertEqual(marked[0][2]["answer"]["usage"], sent[1]["usage"])

    def test_streaming_preview_waits_for_finalize_and_handler_usage(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def mark(self, request_id, status, **kwargs):
                self.marked.append((request_id, status, kwargs))
                return True

            def by_request_id(self, request_id):
                return {
                    "request_id": request_id,
                    "status": "pending",
                    "question": {"title": "Question", "body": "", "tags": [], "asker": {"nickname": "tester"}},
                    "answer": None,
                }

        class FakeClient:
            def __init__(self):
                self.sent = None

            async def send_answer(self, request_id, **kwargs):
                self.sent = (request_id, kwargs)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {}
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self._streaming_answers = {}
                self.usage_wait_seconds = 0.2
                self._prompt_text_by_request = {"req_stream": "Question prompt text"}
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                preview = await adapter.send(
                    "req_stream",
                    "partial answer",
                    metadata={"expect_edits": True},
                )
                self.assertTrue(preview.success)
                self.assertEqual(preview.message_id, "req_stream")
                self.assertIsNone(adapter._client.sent)
                self.assertEqual(adapter._background_upload_tasks, set())
                self.assertIn("req_stream", adapter._prompt_text_by_request)

                final = await adapter.edit_message(
                    chat_id="req_stream",
                    message_id="req_stream",
                    content="final answer",
                    finalize=True,
                    metadata={"expect_edits": True},
                )
                self.assertTrue(final.success)
                self.assertIsNone(adapter._client.sent)

                adapter._capture_turn_metadata(
                    SimpleNamespace(source=SimpleNamespace(chat_id="req_stream")),
                    {"input_tokens": 70, "output_tokens": 816, "model": "provider-model"},
                )
                await asyncio.wait_for(next(iter(adapter._background_upload_tasks)), timeout=1)
            finally:
                adapter_mod.SendResult = original_send_result
            return adapter._client.sent, adapter._queue.marked, adapter._prompt_text_by_request

        sent, marked, prompts = asyncio.run(run_case())
        self.assertEqual(sent[0], "req_stream")
        self.assertEqual(sent[1]["text"], "final answer")
        self.assertEqual(sent[1]["model"], "provider-model")
        self.assertEqual(sent[1]["usage"], {
            "prompt_tokens": 70,
            "completion_tokens": 816,
            "total_tokens": 886,
        })
        self.assertFalse(sent[1]["usage"].get("estimated", False))
        self.assertEqual(marked[0][2]["answer"]["text"], "final answer")
        self.assertEqual(marked[0][2]["answer"]["usage"], sent[1]["usage"])
        self.assertNotIn("req_stream", prompts)

    def test_streaming_final_send_waits_for_handler_usage(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def mark(self, request_id, status, **kwargs):
                self.marked.append((request_id, status, kwargs))
                return True

            def by_request_id(self, request_id):
                return {
                    "request_id": request_id,
                    "status": "pending",
                    "question": {"title": "Question", "body": "", "tags": [], "asker": {"nickname": "tester"}},
                    "answer": None,
                }

        class FakeClient:
            def __init__(self):
                self.sent = None

            async def send_answer(self, request_id, **kwargs):
                self.sent = (request_id, kwargs)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {}
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self._streaming_answers = {}
                self.usage_wait_seconds = 0.2
                self._prompt_text_by_request = {"req_stream_final": "Question prompt text"}
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                final = await adapter.send(
                    "req_stream_final",
                    "final answer",
                    metadata={"expect_edits": True, "notify": True},
                )
                self.assertTrue(final.success)
                self.assertIsNone(adapter._client.sent)

                adapter._capture_turn_metadata(
                    SimpleNamespace(source=SimpleNamespace(chat_id="req_stream_final")),
                    {"input_tokens": 11, "output_tokens": 22, "model": "provider-model"},
                )
                await asyncio.wait_for(next(iter(adapter._background_upload_tasks)), timeout=1)
            finally:
                adapter_mod.SendResult = original_send_result
            return adapter._client.sent, adapter._queue.marked

        sent, marked = asyncio.run(run_case())
        self.assertEqual(sent[0], "req_stream_final")
        self.assertEqual(sent[1]["text"], "final answer")
        self.assertEqual(sent[1]["usage"], {
            "prompt_tokens": 11,
            "completion_tokens": 22,
            "total_tokens": 33,
        })
        self.assertFalse(sent[1]["usage"].get("estimated", False))
        self.assertEqual(marked[0][2]["answer"]["usage"], sent[1]["usage"])

    def test_tool_trace_send_is_cached_not_uploaded(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def mark(self, request_id, status, **kwargs):
                raise AssertionError("tool trace must not be saved as an answer")

            def by_request_id(self, request_id):
                return {
                    "request_id": request_id,
                    "status": "pending",
                    "question": {"title": "Question", "body": "", "tags": [], "asker": {"nickname": "tester"}},
                    "answer": None,
                }

        class FakeClient:
            def __init__(self):
                self.sent = None

            async def send_answer(self, request_id, **kwargs):
                self.sent = (request_id, kwargs)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {}
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self._streaming_answers = {}
                self.usage_wait_seconds = 0
                self._prompt_text_by_request = {"req_tool": "Question prompt text"}
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                result = await adapter.send(
                    "req_tool",
                    'browser_navigate: "https://www.google.com/search?q=finops"',
                    metadata={},
                )
            finally:
                adapter_mod.SendResult = original_send_result
            return result, adapter._client.sent, adapter._background_upload_tasks, adapter._streaming_answers

        result, sent, tasks, streaming = asyncio.run(run_case())

        self.assertTrue(result.success)
        self.assertIsNone(sent)
        self.assertEqual(tasks, set())
        self.assertEqual(streaming["req_tool"]["content"], 'browser_navigate: "https://www.google.com/search?q=finops"')

    def test_combined_tool_trace_send_is_cached_not_uploaded(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def mark(self, request_id, status, **kwargs):
                raise AssertionError("combined tool trace must not be saved as an answer")

            def by_request_id(self, request_id):
                return {
                    "request_id": request_id,
                    "status": "pending",
                    "question": {"title": "Question", "body": "", "tags": [], "asker": {"nickname": "tester"}},
                    "answer": None,
                }

        class FakeClient:
            def __init__(self):
                self.sent = None

            async def send_answer(self, request_id, **kwargs):
                self.sent = (request_id, kwargs)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {}
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self._streaming_answers = {}
                self.usage_wait_seconds = 0
                self._prompt_text_by_request = {"req_tool_combo": "Question prompt text"}
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        content = '🌐 browser_navigate: "https://www.gamersky.com/handbook/201..." 💻 terminal: "curl -sL \\"https://www.zelda.com/breath-of-the-wild\\""'

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                result = await adapter.send(
                    "req_tool_combo",
                    content,
                    metadata={
                        "notify": True,
                        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                    },
                )
            finally:
                adapter_mod.SendResult = original_send_result
            return result, adapter._client.sent, adapter._background_upload_tasks, adapter._streaming_answers

        result, sent, tasks, streaming = asyncio.run(run_case())

        self.assertTrue(result.success)
        self.assertIsNone(sent)
        self.assertEqual(tasks, set())
        self.assertEqual(streaming["req_tool_combo"]["content"], content)

    def test_working_status_send_is_cached_not_uploaded(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def mark(self, request_id, status, **kwargs):
                raise AssertionError("Hermes progress status must not be saved as an answer")

            def by_request_id(self, request_id):
                return {
                    "request_id": request_id,
                    "status": "pending",
                    "question": {"title": "Question", "body": "", "tags": [], "asker": {"nickname": "tester"}},
                    "answer": None,
                }

        class FakeClient:
            def __init__(self):
                self.sent = None

            async def send_answer(self, request_id, **kwargs):
                self.sent = (request_id, kwargs)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {}
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self._streaming_answers = {}
                self.usage_wait_seconds = 0
                self._prompt_text_by_request = {"req_working": "Question prompt text"}
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        content = "⏳ Working — 3 min — iteration 1/150, receiving stream response"

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                result = await adapter.send("req_working", content, metadata={})
            finally:
                adapter_mod.SendResult = original_send_result
            return result, adapter._client.sent, adapter._background_upload_tasks, adapter._streaming_answers

        result, sent, tasks, streaming = asyncio.run(run_case())

        self.assertTrue(result.success)
        self.assertIsNone(sent)
        self.assertEqual(tasks, set())
        self.assertEqual(streaming["req_working"]["content"], content)

    def test_final_answer_can_replace_previous_runtime_only_upload(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def mark(self, request_id, status, **kwargs):
                self.marked.append((request_id, status, kwargs))
                return True

            def by_request_id(self, request_id):
                return {
                    "request_id": request_id,
                    "chat_id": request_id,
                    "status": "uploaded",
                    "question": {"title": "Question", "body": "", "tags": [], "asker": {"nickname": "tester"}},
                    "answer": {"text": "⏳ Working — 3 min — iteration 1/150, receiving stream response"},
                }

        class FakeClient:
            def __init__(self):
                self.sent = None

            async def send_answer(self, request_id, **kwargs):
                self.sent = (request_id, kwargs)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {}
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self._streaming_answers = {}
                self.usage_wait_seconds = 0
                self._prompt_text_by_request = {"req_replace": "Question prompt text"}
                self._job_started_at = {}
                self._warm_conversations = set()
                self._queue = FakeQueue()
                self._client = FakeClient()

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                result = await adapter.send(
                    "req_replace",
                    "最终答案",
                    metadata={"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}},
                )
            finally:
                adapter_mod.SendResult = original_send_result
            return result, adapter._client.sent, adapter._queue.marked

        result, sent, marked = asyncio.run(run_case())

        self.assertTrue(result.success)
        self.assertEqual(sent[0], "req_replace")
        self.assertEqual(sent[1]["text"], "最终答案")
        self.assertEqual(marked[-1][1], "uploaded")

    def test_interrupting_status_send_is_cached_not_uploaded(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def mark(self, request_id, status, **kwargs):
                raise AssertionError("Hermes interrupt status must not be saved as an answer")

            def by_request_id(self, request_id):
                return {
                    "request_id": request_id,
                    "status": "pending",
                    "question": {"title": "Question", "body": "", "tags": [], "asker": {"nickname": "tester"}},
                    "answer": None,
                }

        class FakeClient:
            def __init__(self):
                self.sent = None

            async def send_answer(self, request_id, **kwargs):
                self.sent = (request_id, kwargs)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {}
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self._streaming_answers = {}
                self.usage_wait_seconds = 0
                self._prompt_text_by_request = {"req_interrupt": "Question prompt text"}
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        content = "⚡ Interrupting current task (1 min elapsed, iteration 6/90, running: browser_navigate). I'll respond to your message shortly."

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                result = await adapter.send("req_interrupt", content, metadata={})
            finally:
                adapter_mod.SendResult = original_send_result
            return result, adapter._client.sent, adapter._background_upload_tasks, adapter._streaming_answers

        result, sent, tasks, streaming = asyncio.run(run_case())

        self.assertTrue(result.success)
        self.assertIsNone(sent)
        self.assertEqual(tasks, set())
        self.assertEqual(streaming["req_interrupt"]["content"], content)

    def test_pairing_required_message_is_reported_not_uploaded_as_answer(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def mark(self, request_id, status, **kwargs):
                self.marked.append((request_id, status, kwargs))
                return True

            def by_request_id(self, request_id):
                return {
                    "request_id": request_id,
                    "status": "pending",
                    "question": {"title": "Probe", "body": "", "tags": [], "asker": {"nickname": "AgentMint"}},
                    "answer": None,
                }

        class FakeClient:
            def __init__(self):
                self.answers = []
                self.pairing = []

            async def send_answer(self, request_id, **kwargs):
                self.answers.append((request_id, kwargs))
                return True

            async def send_pairing_required(self, request_id, *, code, command):
                self.pairing.append((request_id, code, command))
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._last_turn_metadata = {}
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self._streaming_answers = {}
                self.usage_wait_seconds = 0
                self._prompt_text_by_request = {"probe_a_test_123": "Probe prompt"}
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        pairing_text = """Hi~ I don't recognize you yet!

Here's your pairing code: KJ5S6H25

Ask the bot owner to run: hermes pairing approve agentmint KJ5S6H25"""

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                result = await adapter.send("probe_a_test_123", pairing_text, metadata={"notify": True})
            finally:
                adapter_mod.SendResult = original_send_result
            return result, adapter._client.pairing, adapter._client.answers, adapter._queue.marked

        result, pairing, answers, marked = asyncio.run(run_case())

        self.assertTrue(result.success)
        self.assertEqual(pairing, [(
            "probe_a_test_123",
            "KJ5S6H25",
            "hermes pairing approve agentmint KJ5S6H25",
        )])
        self.assertEqual(answers, [])
        self.assertEqual(marked, [("probe_a_test_123", "failed", {"error": "pairing_required"})])

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
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self.usage_wait_seconds = 0
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
                await asyncio.wait_for(next(iter(adapter._background_upload_tasks)), timeout=1)
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

    def test_send_ignores_duplicate_answer_after_upload(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def by_request_id(self, request_id):
                return {
                    "request_id": request_id,
                    "status": "uploaded",
                    "answer": {
                        "text": "first answer",
                        "usage": {"prompt_tokens": 70, "completion_tokens": 816, "total_tokens": 886},
                    },
                }

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
                self._last_turn_metadata = {}
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self.usage_wait_seconds = 0
                self._prompt_text_by_request = {"req_4": "Prompt text"}
                self._job_started_at = {}
                self._queue = FakeQueue()
                self._client = FakeClient()

        async def run_case():
            adapter = TestAdapter()
            original_send_result = adapter_mod.SendResult
            adapter_mod.SendResult = lambda **kwargs: SimpleNamespace(**kwargs)
            try:
                result = await adapter.send("req_4", "later self-improvement message", metadata={})
            finally:
                adapter_mod.SendResult = original_send_result
            return result, adapter._queue.marked, adapter._client.sent

        result, marked, sent = asyncio.run(run_case())
        self.assertTrue(result.success)
        self.assertEqual(marked, [])
        self.assertIsNone(sent)

    def test_late_real_usage_corrects_previous_estimate(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def __init__(self):
                self.marked = []

            def by_request_id(self, request_id):
                return {
                    "request_id": request_id,
                    "status": "uploaded",
                    "answer": {
                        "text": "answer text",
                        "model": "hermes",
                        "usage": {
                            "prompt_tokens": 75,
                            "completion_tokens": 990,
                            "total_tokens": 1065,
                            "estimated": True,
                            "source": "agentmint_plugin_estimate",
                        },
                        "capability": {"engine": {"provider": "hermes", "model": "hermes"}},
                        "duration_ms": 123,
                    },
                }

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
                self._last_turn_metadata = {}
                self._turn_metadata_events = {}
                self._pending_answer_uploads = set()
                self._background_upload_tasks = set()
                self.debug_usage = False
                self._queue = FakeQueue()
                self._client = FakeClient()

        async def run_case():
            adapter = TestAdapter()
            adapter._capture_turn_metadata(
                SimpleNamespace(source=SimpleNamespace(chat_id="req_correct")),
                {"input_tokens": 70, "output_tokens": 816, "model": "provider-model"},
            )
            await asyncio.wait_for(next(iter(adapter._background_upload_tasks)), timeout=1)
            return adapter._client.sent, adapter._queue.marked

        sent, marked = asyncio.run(run_case())
        self.assertEqual(sent[0], "req_correct")
        self.assertTrue(sent[1]["usage_correction"])
        self.assertEqual(sent[1]["usage"], {
            "prompt_tokens": 70,
            "completion_tokens": 816,
            "total_tokens": 886,
        })
        self.assertEqual(marked[0][1], "uploaded")
        self.assertEqual(marked[0][2]["answer"]["usage"], sent[1]["usage"])


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
            "AGENTMINT_USAGE_WAIT_SECONDS",
            "AGENTMINT_DEBUG_USAGE",
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
                "usage_wait_seconds": 2.5,
                "debug_usage": True,
            },
        }, {})

        self.assertEqual(out["connector_id"], "conn_from_yaml")
        self.assertEqual(out["connector_token"], "conn_sk_from_yaml")
        self.assertEqual(out["platform_url"], "ws://arena.example/ws")
        self.assertEqual(out["home_channel"], {
            "chat_id": "agentmint-home",
            "name": "AgentMint",
        })
        self.assertEqual(out["usage_wait_seconds"], 2.5)
        self.assertEqual(out["debug_usage"], True)
        self.assertEqual(os.environ["AGENTMINT_CONNECTOR_ID"], "conn_from_yaml")
        self.assertEqual(os.environ["AGENTMINT_CONNECTOR_TOKEN"], "conn_sk_from_yaml")
        self.assertEqual(os.environ["AGENTMINT_HOME_CHANNEL"], "agentmint-home")
        self.assertEqual(os.environ["AGENTMINT_USAGE_WAIT_SECONDS"], "2.5")
        self.assertEqual(os.environ["AGENTMINT_DEBUG_USAGE"], "True")

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

    def test_by_chat_prefers_non_terminal_job_before_latest_uploaded(self):
        queue_mod = __import__(f"{self.adapter.__package__}.queue", fromlist=["JobQueue"])

        with tempfile.TemporaryDirectory() as tmp:
            queue = queue_mod.JobQueue(str(Path(tmp) / "jobs.db"))
            try:
                self.assertTrue(queue.upsert_pending("req_pending", "conv_1", {"title": "Pending"}))
                self.assertTrue(queue.upsert_pending("req_uploaded", "conv_1", {"title": "Uploaded"}))
                self.assertTrue(queue.mark("req_uploaded", "uploaded", answer={"text": "done"}))

                self.assertEqual(queue.by_chat("conv_1")["request_id"], "req_pending")
            finally:
                queue.close()


if __name__ == "__main__":
    unittest.main()
