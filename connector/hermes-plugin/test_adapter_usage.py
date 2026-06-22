import importlib.util
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


if __name__ == "__main__":
    unittest.main()
