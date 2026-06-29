import importlib.util
import sys
import tempfile
import types
import unittest
from argparse import Namespace
from pathlib import Path


def load_configure_module():
    path = Path(__file__).with_name("configure.py")
    package_name = "agentmint_hermes_plugin_configure_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(path.parent)]
    sys.modules[package_name] = package
    spec = importlib.util.spec_from_file_location(f"{package_name}.configure", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ConfigureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.configure_mod = load_configure_module()

    def test_configure_merges_agentmint_without_dropping_existing_platforms(self):
        args = Namespace(
            connector_id="conn_test",
            connector_token="conn_sk_test",
            platform_url="ws://arena.test/ws",
            max_concurrent=5,
            usage_wait_seconds=2.5,
            debug_usage=True,
            queue_db="~/.hermes/agentmint-jobs.db",
        )
        data = {
            "plugins": {"enabled": ["platforms/lark"]},
            "gateway": {
                "platforms": {
                    "lark": {"enabled": True},
                }
            },
        }

        updated = self.configure_mod.configure(data, args)

        self.assertEqual(updated["plugins"]["enabled"], ["platforms/lark", "platforms/agentmint"])
        self.assertTrue(updated["gateway"]["platforms"]["lark"]["enabled"])
        agentmint = updated["gateway"]["platforms"]["agentmint"]
        self.assertTrue(agentmint["enabled"])
        self.assertEqual(agentmint["home_channel"]["chat_id"], "agentmint-home")
        self.assertEqual(agentmint["extra"]["connector_id"], "conn_test")
        self.assertEqual(agentmint["extra"]["connector_token"], "conn_sk_test")
        self.assertEqual(agentmint["extra"]["platform_url"], "ws://arena.test/ws")
        self.assertEqual(agentmint["extra"]["max_concurrent"], 5)
        self.assertEqual(agentmint["extra"]["usage_wait_seconds"], 2.5)
        self.assertTrue(agentmint["extra"]["debug_usage"])
        self.assertEqual(agentmint["extra"]["queue_db"], "~/.hermes/agentmint-jobs.db")

    def test_backup_creates_timestamped_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("gateway: {}\n", encoding="utf-8")

            backup_path = self.configure_mod.backup(path)

            self.assertIsNotNone(backup_path)
            self.assertTrue(backup_path.exists())
            self.assertEqual(backup_path.read_text(encoding="utf-8"), "gateway: {}\n")


if __name__ == "__main__":
    unittest.main()
