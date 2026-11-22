"""Claude Code adapter. Reads configuration only; never writes.

Sources read (nothing else is scanned):
  ~/.claude/settings.json         skillOverrides, enabledPlugins, hooks
  ~/.claude.json                  user-scope mcpServers, per-project mcpServers
  ~/.claude/skills/*/SKILL.md     user skills
  ~/.agents/skills/*/SKILL.md     shared skills
  <project>/.mcp.json             project MCP servers (only for --project paths)
  <project>/CLAUDE.md, AGENTS.md  memory files (only for --project paths)

Transcripts (~/.claude/projects/*.jsonl) are deliberately not read.
MCP env values are never read, only their key names.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HOOK_COMMAND_LIMIT = 140


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _skill_description(skill_md: Path) -> str:
    """Return the `description` field from a SKILL.md front matter, one line."""
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end == -1:
        return ""
    desc_lines: list[str] = []
    in_desc = False
    for line in text[3:end].splitlines():
        if line.startswith("description:"):
            value = line[len("description:") :].strip().strip("\"'")
            if value not in (">", "|", ">-", "|-"):
                desc_lines.append(value)
            in_desc = True
        elif in_desc and line.startswith((" ", "\t")):
            desc_lines.append(line.strip())
        elif in_desc:
            break
    return " ".join(part for part in desc_lines if part)[:300]


def _tilde(home: Path, path: Path) -> str:
    try:
        rel = path.relative_to(home)
    except ValueError:
        return str(path)
    return "~" if str(rel) == "." else f"~/{rel}"


def _scan_skills(home: Path, source: str, folder: Path, overrides: dict) -> list[dict]:
    if not folder.is_dir():
        return []
    skills = []
    for entry in sorted(folder.iterdir()):
        if not entry.is_dir():
            continue
        link = None
        if entry.is_symlink():
            try:
                link = _tilde(home, entry.resolve())
            except OSError:
                link = "unresolved"
        skills.append(
            {
                "name": entry.name,
                "source": source,
                "path": _tilde(home, entry),
                "description": _skill_description(entry / "SKILL.md"),
                "state": overrides.get(entry.name, "on"),
                "link": link,
            }
        )
    return skills


def _transport(cfg: dict) -> str:
    if isinstance(cfg.get("type"), str):
        return cfg["type"]
    if "command" in cfg:
        return "stdio"
    if "url" in cfg:
        return "http"
    return "unknown"


def _mcp_servers(servers: Any, scope: str, defined_in: str) -> list[dict]:
    if not isinstance(servers, dict):
        return []
    out = []
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            cfg = {}
        env = cfg.get("env")
        out.append(
            {
                "name": name,
                "scope": scope,
                "defined_in": defined_in,
                "transport": _transport(cfg),
                "env_keys": sorted(env) if isinstance(env, dict) else [],
            }
        )
    return out


def _hooks(settings: dict, origin: str) -> list[dict]:
    out = []
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return out
    for event, groups in hooks.items():
        for group in groups if isinstance(groups, list) else []:
            if not isinstance(group, dict):
                continue
            for hook in group.get("hooks", []) if isinstance(group.get("hooks"), list) else []:
                if not isinstance(hook, dict):
                    continue
                command = str(hook.get("command", ""))
                out.append(
                    {
                        "event": event,
                        "matcher": str(group.get("matcher", "")),
                        "command": command[:HOOK_COMMAND_LIMIT],
                        "origin": origin,
                    }
                )
    return out


def _memory_files(project: Path) -> list[dict]:
    out = []
    for name in ("CLAUDE.md", "AGENTS.md"):
        path = project / name
        if path.is_file():
            out.append({"path": str(path), "symlink": path.is_symlink()})
    return out


def scan(home: Path, projects: list[Path] | None = None) -> dict:
    """Return the configuration of Claude Code for `home`.

    `projects` lists project folders to inspect for project-scope config.
    Nothing outside `home` and those folders is touched.
    """
    home = Path(home).expanduser()
    settings = _read_json(home / ".claude" / "settings.json")
    settings = settings if isinstance(settings, dict) else {}
    global_json = _read_json(home / ".claude.json")
    global_json = global_json if isinstance(global_json, dict) else {}

    overrides = settings.get("skillOverrides")
    overrides = overrides if isinstance(overrides, dict) else {}

    skills = _scan_skills(home, "user", home / ".claude" / "skills", overrides)
    skills += _scan_skills(home, "agents", home / ".agents" / "skills", overrides)

    enabled = settings.get("enabledPlugins")
    plugins = [
        {"id": pid, "enabled": bool(on)}
        for pid, on in sorted((enabled or {}).items())
        if isinstance(enabled, dict)
    ]

    mcp = _mcp_servers(global_json.get("mcpServers"), "user", "~/.claude.json")
    mcp += _mcp_servers(settings.get("mcpServers"), "settings", "~/.claude/settings.json")

    hooks = _hooks(settings, "~/.claude/settings.json")

    memory: list[dict] = []
    for project in projects or []:
        project = Path(project).expanduser().resolve()
        if not project.is_dir():
            continue
        label = str(project)
        project_mcp = _read_json(project / ".mcp.json")
        if isinstance(project_mcp, dict):
            mcp += _mcp_servers(project_mcp.get("mcpServers"), "project", label + "/.mcp.json")
        per_project = (global_json.get("projects") or {}).get(label)
        if isinstance(per_project, dict):
            mcp += _mcp_servers(per_project.get("mcpServers"), "project", "~/.claude.json")
        memory += [dict(item, project=label) for item in _memory_files(project)]

    return {
        "agent": "claude-code",
        "home": str(home),
        "skills": skills,
        "plugins": plugins,
        "mcp_servers": mcp,
        "hooks": hooks,
        "memory_files": memory,
        "override_count": len(overrides),
    }
