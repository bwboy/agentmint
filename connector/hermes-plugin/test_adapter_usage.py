import importlib.util
import os
import sys
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
        ):
            os.environ.pop(key, None)

    def test_apply_yaml_config_accepts_nested_extra_shape(self):
        out = self.adapter._apply_yaml_config({
            "enabled": True,
            "extra": {
                "connector_id": "conn_from_yaml",
                "connector_token": "conn_sk_from_yaml",
                "platform_url": "ws://arena.example/ws",
            },
        }, {})

        self.assertEqual(out["connector_id"], "conn_from_yaml")
        self.assertEqual(out["connector_token"], "conn_sk_from_yaml")
        self.assertEqual(out["platform_url"], "ws://arena.example/ws")
        self.assertEqual(os.environ["AGENTMINT_CONNECTOR_ID"], "conn_from_yaml")
        self.assertEqual(os.environ["AGENTMINT_CONNECTOR_TOKEN"], "conn_sk_from_yaml")


if __name__ == "__main__":
    unittest.main()
