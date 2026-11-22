import json
import tempfile
import unittest
from pathlib import Path

from agents_tree.claude import scan
from agents_tree.cli import _render


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        write(
            self.home / ".claude" / "skills" / "demo" / "SKILL.md",
            "---\nname: demo\ndescription: Fa la demo\n---\nbody",
        )
        write(
            self.home / ".claude" / "settings.json",
            json.dumps(
                {
                    "skillOverrides": {"demo": "off"},
                    "enabledPlugins": {"x@market": True},
                    "hooks": {
                        "PreToolUse": [
                            {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
                        ]
                    },
                }
            ),
        )
        write(
            self.home / ".claude.json",
            json.dumps(
                {
                    "mcpServers": {"gh": {"command": "gh-mcp", "env": {"TOKEN": "secret"}}},
                    "projects": {},
                }
            ),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_skills_overrides_plugins_hooks_and_mcp(self):
        data = scan(self.home)
        skill = data["skills"][0]
        self.assertEqual(skill["name"], "demo")
        self.assertEqual(skill["state"], "off")
        self.assertEqual(skill["description"], "Fa la demo")
        self.assertEqual(data["plugins"], [{"id": "x@market", "enabled": True}])
        self.assertEqual(data["hooks"][0]["event"], "PreToolUse")
        self.assertEqual(data["hooks"][0]["matcher"], "Bash")
        self.assertEqual(data["override_count"], 1)

    def test_mcp_env_values_never_leave_the_scan(self):
        data = scan(self.home)
        server = data["mcp_servers"][0]
        self.assertEqual(server["env_keys"], ["TOKEN"])
        self.assertNotIn("secret", json.dumps(data))

    def test_project_scope_only_for_given_folders(self):
        project = Path(self.tmp.name) / "proj"
        write(project / ".mcp.json", json.dumps({"mcpServers": {"p": {"url": "http://x"}}}))
        write(project / "CLAUDE.md", "memo")
        without = scan(self.home)
        self.assertEqual(without["memory_files"], [])
        with_project = scan(self.home, [project])
        names = [s["name"] for s in with_project["mcp_servers"]]
        self.assertIn("p", names)
        self.assertEqual(len(with_project["memory_files"]), 1)

    def test_missing_files_do_not_crash(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        data = scan(empty)
        self.assertEqual(data["skills"], [])
        self.assertEqual(data["mcp_servers"], [])

    def test_tree_renders(self):
        text = _render(scan(self.home))
        self.assertIn("demo", text)
        self.assertIn("[user, off]", text)


if __name__ == "__main__":
    unittest.main()
