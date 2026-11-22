"""Punto d'ingresso da terminale: `agents-tree [--json] [--project DIR]...`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .claude import scan


def _render(data: dict) -> str:
    lines = [f"Claude Code  ({data['home']})", ""]

    lines.append(f"skills ({len(data['skills'])})")
    for skill in data["skills"]:
        extra = f" -> {skill['link']}" if skill["link"] else ""
        lines.append(f"  ├─ {skill['name']}  [{skill['source']}, {skill['state']}]{extra}")
        if skill["description"]:
            lines.append(f"  │    {skill['description'][:100]}")
    lines.append("")

    lines.append(f"overrides: {data['override_count']}")
    lines.append(f"plugins ({len(data['plugins'])})")
    for plugin in data["plugins"]:
        mark = "on" if plugin["enabled"] else "off"
        lines.append(f"  ├─ {plugin['id']}  [{mark}]")
    lines.append("")

    lines.append(f"mcp servers ({len(data['mcp_servers'])})")
    for server in data["mcp_servers"]:
        keys = ", ".join(server["env_keys"]) or "-"
        lines.append(
            f"  ├─ {server['name']}  [{server['transport']}, {server['scope']}] env: {keys}"
        )
    lines.append("")

    lines.append(f"hooks ({len(data['hooks'])})")
    for hook in data["hooks"]:
        matcher = hook["matcher"] or "*"
        lines.append(f"  ├─ {hook['event']} / {matcher}: {hook['command']}")
    lines.append("")

    lines.append(f"memory files ({len(data['memory_files'])})")
    for item in data["memory_files"]:
        link = " (symlink)" if item["symlink"] else ""
        lines.append(f"  ├─ {item['path']}{link}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agents-tree",
        description="Vista in sola lettura di cosa caricano i tuoi agent AI. Non scrive nulla.",
    )
    parser.add_argument("--json", action="store_true", help="stampa JSON invece dell'albero")
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        metavar="DIR",
        help="controlla anche la config di progetto in DIR (ripetibile)",
    )
    parser.add_argument("--home", default=str(Path.home()), help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"agents-tree {__version__}")
    args = parser.parse_args(argv)

    data = scan(Path(args.home), [Path(p) for p in args.project])
    if args.json:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(_render(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
