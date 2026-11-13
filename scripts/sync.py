#!/usr/bin/env python3
"""Copy the canonical skills/ and assets/ into each harness plugin.

    python3 scripts/sync.py           # write the copies
    python3 scripts/sync.py --check   # exit 1 if any copy differs (CI)

The skill tree lives once at the repo root. Each harness plugin carries a copy
because the ChatGPT importer, Cursor, and Claude Code each read only the plugin
folder, and symlink handling is not documented for the ChatGPT importer.
agents/openai.yaml is ChatGPT metadata, so only the ChatGPT copy keeps it.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
LOGO = ROOT / "assets" / "logo.png"


@dataclass(frozen=True)
class Target:
    plugin: Path
    keep_openai_yaml: bool
    plugin_logo: bool
    skill_logo: bool


TARGETS = (
    Target(ROOT / "chatgpt/plugins/gateway", keep_openai_yaml=True, plugin_logo=True, skill_logo=True),
    Target(ROOT / "plugins/claude/gateway", keep_openai_yaml=False, plugin_logo=False, skill_logo=False),
    Target(ROOT / "plugins/cursor/gateway", keep_openai_yaml=False, plugin_logo=True, skill_logo=False),
)


def expected_files(target: Target) -> dict[Path, Path]:
    """Map each destination file to its canonical source."""
    out: dict[Path, Path] = {}
    for src in sorted(SKILLS.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(SKILLS)
        if rel.parts[1:2] == ("agents",) and not target.keep_openai_yaml:
            continue
        out[target.plugin / "skills" / rel] = src
    if target.plugin_logo:
        out[target.plugin / "assets" / "logo.png"] = LOGO
    if target.skill_logo:
        for skill in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
            out[target.plugin / "skills" / skill.name / "assets" / "logo.png"] = LOGO
    return out


def managed_roots(target: Target) -> list[Path]:
    roots = [target.plugin / "skills"]
    if target.plugin_logo:
        roots.append(target.plugin / "assets")
    return roots


def drift(target: Target) -> list[str]:
    want = expected_files(target)
    problems = [
        f"{dst.relative_to(ROOT)}: differs from {src.relative_to(ROOT)}"
        if dst.is_file()
        else f"{dst.relative_to(ROOT)}: missing (copy of {src.relative_to(ROOT)})"
        for dst, src in want.items()
        if not (dst.is_file() and filecmp.cmp(dst, src, shallow=False))
    ]
    for root in managed_roots(target):
        if root.is_dir():
            problems += [
                f"{p.relative_to(ROOT)}: not in the canonical tree"
                for p in sorted(root.rglob("*"))
                if p.is_file() and p not in want
            ]
    return problems


def write(target: Target) -> None:
    for root in managed_roots(target):
        if root.is_dir():
            shutil.rmtree(root)
    for dst, src in expected_files(target).items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report drift instead of writing")
    args = parser.parse_args()
    if not args.check:
        for target in TARGETS:
            write(target)
        print(f"synced {len(TARGETS)} plugin copies")
        return 0
    problems = [p for target in TARGETS for p in drift(target)]
    for p in problems:
        print(f"ERROR: {p} (run python3 scripts/sync.py)", file=sys.stderr)
    if not problems:
        print(f"OK: {len(TARGETS)} plugin copies match skills/ and assets/")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
