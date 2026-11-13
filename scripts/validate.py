#!/usr/bin/env python3
"""Structural checks for the three marketplaces in this repo.

    python3 scripts/validate.py

Covers what each host rejects or mis-installs, plus the gateway wiring:
  - ChatGPT (chatgpt/.agents/plugins/marketplace.json): the checks the workspace
    importer applies, and no MCP declaration anywhere in chatgpt/, because any
    mcpServers / mcp.json / .mcp.json labels the plugin Desktop only.
  - Claude Code (.claude-plugin/marketplace.json) and Cursor
    (.cursor-plugin/marketplace.json): manifests, sources, MCP config.
  - gateway.json is the single record of the MCP URL, the ChatGPT app id, and
    the product codes skills route to; every copy must agree with it.
  - The three plugin.json files and three marketplace entries mirror name,
    version and description; skill copies match skills/ (scripts/sync.py).
  - The repo is public: no real email addresses and no token-shaped strings.

Requires PyYAML (pip install pyyaml).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync  # noqa: E402

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# OpenAI's packaging docs: .app.json must reference the registered MCP app's
# technical id from the admin URL, which starts with plugin_asdk_app_.
APP_ID = re.compile(r"^plugin_asdk_app_[0-9a-f]{32}$")
PLUGIN_ID = re.compile(r"^plugin_[A-Za-z0-9_]+$")
PRODUCT_LINE = re.compile(r"\*\*Product:\*\*\s*`([a-z0-9_-]+)`")
MD_LINK = re.compile(r"\]\((\.?/?[A-Za-z0-9_./-]+\.(?:md|svg|png|yaml|json))\)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org")
SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".sh", ".txt", ""}
MIRRORED = ("name", "version", "description")

CHATGPT = ROOT / "chatgpt"
CODEX_MKT = CHATGPT / ".agents/plugins/marketplace.json"
CLAUDE_MKT = ROOT / ".claude-plugin/marketplace.json"
CURSOR_MKT = ROOT / ".cursor-plugin/marketplace.json"
GATEWAY = ROOT / "gateway.json"


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def load_json(r: Report, path: Path) -> Any:
    if not path.is_file():
        r.err(f"missing {rel(path)}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        r.err(f"{rel(path)}: not valid JSON ({exc})")
        return None


def resolve_source(r: Report, base: Path, source: Any, label: str) -> Path | None:
    path = source.get("path") if isinstance(source, dict) else source
    if not isinstance(path, str) or not path:
        r.err(f"{label}: source has no path")
        return None
    if path.startswith("/") or ".." in Path(path).parts:
        r.err(f"{label}: source {path!r} must be relative without '..'")
        return None
    d = (base / path).resolve()
    if not d.is_dir():
        r.err(f"{label}: source {path!r} does not exist")
        return None
    return d


def check_skills(r: Report, plugin: Path, skills_dir: Path, *, openai: bool) -> None:
    if not skills_dir.is_dir():
        r.err(f"{rel(plugin)}: skills dir {rel(skills_dir)} missing")
        return
    found = False
    for sd in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        found = True
        sm = sd / "SKILL.md"
        if not sm.is_file():
            r.err(f"{rel(sd)}: missing SKILL.md")
            continue
        text = sm.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            r.err(f"{rel(sm)}: no frontmatter")
            continue
        try:
            fm = yaml.safe_load(text.split("---\n", 2)[1]) or {}
        except yaml.YAMLError as exc:
            r.err(f"{rel(sm)}: frontmatter is not valid YAML ({exc})")
            continue
        if fm.get("name") != sd.name:
            r.err(f"{rel(sm)}: frontmatter name {fm.get('name')!r} != folder {sd.name!r}")
        if not fm.get("description"):
            r.err(f"{rel(sm)}: missing description")
        for link in MD_LINK.findall(text):
            if not (sd / link.removeprefix("./")).is_file():
                r.err(f"{rel(sm)}: link {link} not found")
        y = sd / "agents/openai.yaml"
        if not openai:
            if y.exists():
                r.err(f"{rel(y)}: ChatGPT metadata outside the ChatGPT plugin")
            continue
        if not y.is_file():
            continue
        try:
            meta = yaml.safe_load(y.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            r.err(f"{rel(y)}: not valid YAML (quote values containing ': ' or '#')")
            continue
        extra = set((meta.get("policy") or {})) - {"allow_implicit_invocation"}
        if extra:
            r.err(f"{rel(y)}: policy keys {sorted(extra)} not allowed (only allow_implicit_invocation)")
        for key in ("icon_small", "icon_large"):
            icon = (meta.get("interface") or {}).get(key)
            if icon and not (sd / icon).is_file():
                r.err(f"{rel(y)}: {key} {icon} not found")
    if not found:
        r.err(f"{rel(plugin)}: no skills in {rel(skills_dir)}")


def check_mcp(r: Report, path: Path, gateway: dict) -> None:
    data = load_json(r, path)
    if data is None:
        return
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or set(servers) != {"gateway"}:
        r.err(f"{rel(path)}: mcpServers must contain exactly the 'gateway' server")
        return
    server = servers["gateway"]
    if server.get("type") != "http":
        r.err(f"{rel(path)}: gateway server type must be 'http'")
    if server.get("url") != gateway.get("mcp_url"):
        r.err(f"{rel(path)}: gateway url {server.get('url')!r} != gateway.json mcp_url {gateway.get('mcp_url')!r}")


def check_codex(r: Report, gateway: dict) -> tuple[list[dict], list[dict]]:
    manifests: list[dict] = []
    entries: list[dict] = []
    mkt = load_json(r, CODEX_MKT)
    if mkt is None:
        return manifests, entries
    if not (mkt.get("name") and (mkt.get("interface") or {}).get("displayName") and isinstance(mkt.get("plugins"), list)):
        r.err(f"{rel(CODEX_MKT)}: needs name, interface.displayName, plugins[]")
        return manifests, entries
    registered: set[str] = set()
    for entry in mkt["plugins"]:
        name = entry.get("name", "")
        label = f"{rel(CODEX_MKT)} entry {name!r}"
        registered.add(name)
        entries.append(entry)
        if not entry.get("category"):
            r.err(f"{label}: missing category")
        policy = entry.get("policy") or {}
        if policy.get("installation") not in ("AVAILABLE", "INSTALLED_BY_DEFAULT", "NOT_AVAILABLE"):
            r.err(f"{label}: bad policy.installation {policy.get('installation')!r}")
        if policy.get("authentication") not in ("ON_INSTALL", "ON_USE"):
            r.err(f"{label}: bad policy.authentication {policy.get('authentication')!r}")
        if "pluginId" in entry and not PLUGIN_ID.match(str(entry["pluginId"])):
            r.err(f"{label}: pluginId {entry['pluginId']!r} must be the id after /admin/plugins/ (plugin_...)")
        d = resolve_source(r, CHATGPT, entry.get("source"), label)
        if d is None:
            continue
        if d.name != name:
            r.err(f"{label}: folder name {d.name!r} differs")
        man_path = d / ".codex-plugin/plugin.json"
        man = load_json(r, man_path)
        if man is None:
            continue
        manifests.append(man)
        if man.get("name") != name:
            r.err(f"{rel(man_path)}: name does not match {name!r}")
        if not SEMVER.match(str(man.get("version", ""))):
            r.err(f"{rel(man_path)}: version {man.get('version')!r} is not semver")
        iface = man.get("interface") or {}
        if not (man.get("description") and (man.get("author") or {}).get("name")
                and all(iface.get(k) for k in ("displayName", "shortDescription", "longDescription", "developerName", "category"))):
            r.err(f"{rel(man_path)}: missing description, author.name, or required interface fields")
        if "hooks" in man:
            r.err(f"{rel(man_path)}: 'hooks' is not supported by the ChatGPT importer")
        if "mcpServers" in man:
            r.err(f"{rel(man_path)}: 'mcpServers' makes the plugin Desktop only; reference the gateway app via .app.json")
        prompts = iface.get("defaultPrompt") or []
        if len(prompts) > 3:
            r.err(f"{rel(man_path)}: defaultPrompt has {len(prompts)} entries (max 3)")
        for p in prompts:
            if len(p) > 128:
                r.err(f"{rel(man_path)}: defaultPrompt over 128 chars: {p}")
        for key in ("composerIcon", "logo", "logoDark"):
            if iface.get(key) and not (d / iface[key].removeprefix("./")).is_file():
                r.err(f"{rel(man_path)}: asset {iface[key]} not found")
        for shot in iface.get("screenshots") or []:
            if not (d / shot.removeprefix("./")).is_file():
                r.err(f"{rel(man_path)}: screenshot {shot} not found")
        for key in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
            if iface.get(key) and not str(iface[key]).startswith("https://"):
                r.err(f"{rel(man_path)}: {key} must be https")
        app_path = d / ".app.json"
        if man.get("apps") != "./.app.json":
            r.err(f"{rel(man_path)}: apps must be './.app.json'")
        app = load_json(r, app_path)
        if app is not None:
            apps = app.get("apps")
            if not isinstance(apps, dict) or set(apps) != {"gateway"}:
                r.err(f"{rel(app_path)}: apps must contain exactly the 'gateway' key")
            else:
                app_id = (apps["gateway"] or {}).get("id", "")
                if not APP_ID.match(app_id):
                    r.err(f"{rel(app_path)}: id {app_id!r} must be plugin_asdk_app_ + 32 hex chars (the admin URL id)")
                elif app_id != gateway.get("chatgpt_app_id"):
                    r.err(f"{rel(app_path)}: id {app_id!r} != gateway.json chatgpt_app_id")
        check_skills(r, d, d / str(man.get("skills", "./skills/")).removeprefix("./"), openai=True)
    for d in sorted(p for p in (CHATGPT / "plugins").iterdir() if p.is_dir()) if (CHATGPT / "plugins").is_dir() else []:
        if d.name not in registered:
            r.err(f"{rel(d)} exists but is not in {rel(CODEX_MKT)}")
    for p in sorted(CHATGPT.rglob("*")):
        if p.name in ("mcp.json", ".mcp.json"):
            r.err(f"{rel(p)}: an MCP file in the ChatGPT tree makes the plugin Desktop only")
    return manifests, entries


def check_claude(r: Report, gateway: dict) -> tuple[list[dict], list[dict]]:
    manifests: list[dict] = []
    mkt = load_json(r, CLAUDE_MKT)
    if mkt is None:
        return manifests, []
    if not (mkt.get("name") and (mkt.get("owner") or {}).get("name") and isinstance(mkt.get("plugins"), list)):
        r.err(f"{rel(CLAUDE_MKT)}: needs name, owner.name, plugins[]")
        return manifests, []
    for entry in mkt["plugins"]:
        name = entry.get("name", "")
        label = f"{rel(CLAUDE_MKT)} entry {name!r}"
        if not KEBAB.match(name):
            r.err(f"{label}: name must be kebab-case")
        d = resolve_source(r, ROOT, entry.get("source"), label)
        if d is None:
            continue
        man_dir = d / ".claude-plugin"
        man = load_json(r, man_dir / "plugin.json")
        if man is None:
            continue
        manifests.append(man)
        if man.get("name") != name:
            r.err(f"{rel(man_dir / 'plugin.json')}: name {man.get('name')!r} != entry name {name!r}")
        if not SEMVER.match(str(man.get("version", ""))):
            r.err(f"{rel(man_dir / 'plugin.json')}: version is not semver")
        stray = [p.name for p in man_dir.iterdir() if p.name != "plugin.json"]
        if stray:
            r.err(f"{rel(man_dir)}: only plugin.json belongs here, found {sorted(stray)}")
        check_mcp(r, d / ".mcp.json", gateway)
        check_skills(r, d, d / "skills", openai=False)
    return manifests, mkt["plugins"]


def check_cursor(r: Report, gateway: dict) -> tuple[list[dict], list[dict]]:
    manifests: list[dict] = []
    mkt = load_json(r, CURSOR_MKT)
    if mkt is None:
        return manifests, []
    if not (KEBAB.match(str(mkt.get("name", ""))) and (mkt.get("owner") or {}).get("name") and isinstance(mkt.get("plugins"), list)):
        r.err(f"{rel(CURSOR_MKT)}: needs a kebab-case name, owner.name, plugins[]")
        return manifests, []
    for entry in mkt["plugins"]:
        name = entry.get("name", "")
        label = f"{rel(CURSOR_MKT)} entry {name!r}"
        if not KEBAB.match(name):
            r.err(f"{label}: name must be kebab-case")
        d = resolve_source(r, ROOT, entry.get("source"), label)
        if d is None:
            continue
        man_path = d / ".cursor-plugin/plugin.json"
        man = load_json(r, man_path)
        if man is None:
            continue
        manifests.append(man)
        if man.get("name") != name:
            r.err(f"{rel(man_path)}: name {man.get('name')!r} != entry name {name!r}")
        if not SEMVER.match(str(man.get("version", ""))):
            r.err(f"{rel(man_path)}: version is not semver")
        logo = man.get("logo")
        if logo and not (d / logo).is_file():
            r.err(f"{rel(man_path)}: logo {logo} not found")
        if "mcpServers" in man:
            r.err(f"{rel(man_path)}: keep the MCP config in mcp.json so it is discovered by default")
        check_mcp(r, d / "mcp.json", gateway)
        check_skills(r, d, d / "skills", openai=False)
    return manifests, mkt["plugins"]


def check_mirrors(r: Report, manifests: list[dict], entries: list[dict]) -> None:
    for field in MIRRORED:
        values = {json.dumps(m.get(field)) for m in manifests}
        if len(values) > 1:
            r.err(f"plugin.json {field} differs across harnesses: {sorted(values)}")
        canonical = manifests[0].get(field) if manifests else None
        for e in entries:
            if field in e and e[field] != canonical:
                r.err(f"marketplace entry {e.get('name')!r}: {field} {e[field]!r} != plugin.json {canonical!r}")


def check_gateway(r: Report) -> dict:
    gateway = load_json(r, GATEWAY) or {}
    url = gateway.get("mcp_url", "")
    if not re.match(r"^https://[a-z0-9.-]+/mcp$", str(url)):
        r.err(f"gateway.json: mcp_url {url!r} must be https://<host>/mcp")
    if not APP_ID.match(str(gateway.get("chatgpt_app_id", ""))):
        r.err("gateway.json: chatgpt_app_id must be plugin_asdk_app_ + 32 hex chars")
    products = gateway.get("products")
    if not (isinstance(products, list) and products and all(isinstance(p, str) and p for p in products)):
        r.err("gateway.json: products must be a non-empty list of product codes")
        return gateway
    routed: set[str] = set()
    for routing in sorted((ROOT / "skills").glob("*/references/*.md")):
        routed |= set(PRODUCT_LINE.findall(routing.read_text(encoding="utf-8")))
    for code in sorted(routed - set(products)):
        r.err(f"skills route to product {code!r}, which gateway.json does not list")
    for code in sorted(set(products) - routed):
        r.err(f"gateway.json lists product {code!r}, which no skill routes to")
    return gateway


def check_hygiene(r: Report) -> None:
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or ".git" in p.parts or p.suffix not in TEXT_SUFFIXES:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in EMAIL.finditer(text):
            if not m.group(0).lower().endswith(ALLOWED_EMAIL_DOMAINS):
                r.err(f"{rel(p)}: real-looking email {m.group(0)!r} in a public repo (use example.com)")
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                r.err(f"{rel(p)}: token-shaped string matching {pat.pattern!r}")


def main() -> int:
    r = Report()
    gateway = check_gateway(r)
    codex_m, codex_e = check_codex(r, gateway)
    claude_m, claude_e = check_claude(r, gateway)
    cursor_m, cursor_e = check_cursor(r, gateway)
    check_mirrors(r, codex_m + claude_m + cursor_m, codex_e + claude_e + cursor_e)
    for target in sync.TARGETS:
        for problem in sync.drift(target):
            r.err(f"{problem} (run python3 scripts/sync.py)")
    check_hygiene(r)
    for e in r.errors:
        print(f"ERROR: {e}", file=sys.stderr)
    if r.errors:
        return 1
    print(f"OK: 3 marketplaces, {len(codex_m) + len(claude_m) + len(cursor_m)} plugin manifests validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
