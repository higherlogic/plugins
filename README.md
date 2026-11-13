# Higher Logic plugins

One plugin, `gateway`, published to three hosts from this repo: ChatGPT, Claude Code, and Cursor. Its skill, `ask-gateway` (invoke with `@gateway`), works with a Higher Logic customer's data through the [Higher Logic gateway](https://github.com/higherlogic/gateway) MCP. It picks the tenant and routes each instruction to the matching product:

| Domain | Gateway product |
| --- | --- |
| Contacts and people | `cm` Contact Manager |
| Communities and community membership | `oc` Online Community (`admin` surface) |
| Orders, payments, refunds, membership billing | `ec` Commerce |
| Knowledge base and AI assistant | `kb` AI Assistant Studio |
| Support requests | `sh` Support Harness |

Before any data-changing call, the skill confirms with the user, and it honours the gateway's own approval step. It replaces the per-account plugins in [account-plugins](https://github.com/higherlogic/account-plugins), which needed one connector per tenant and product.

This repo is **public**. Never commit tenant data, real email addresses, credentials, or customer names beyond what a tenant code in an example prompt shows.

## Layout

```
plugins/
├── gateway.json                         # MCP URL, ChatGPT app id, product codes: every copy must agree
├── skills/ask-gateway/                  # CANONICAL skill; edit here, then run scripts/sync.py
├── assets/logo.png                      # canonical logo
├── evals/routing-questions.md           # manual eval rows
├── .claude-plugin/marketplace.json      # Claude Code catalog -> plugins/claude/gateway
├── .cursor-plugin/marketplace.json      # Cursor catalog      -> plugins/cursor/gateway
├── plugins/claude/gateway/              # .claude-plugin/plugin.json, .mcp.json, skills/ (copy)
├── plugins/cursor/gateway/              # .cursor-plugin/plugin.json, mcp.json, skills/ (copy)
├── chatgpt/                             # ChatGPT import root (Path = chatgpt)
│   ├── .agents/plugins/marketplace.json
│   └── plugins/gateway/                 # .codex-plugin/plugin.json, .app.json, skills/ (copy)
└── scripts/
    ├── sync.py                          # copy skills/ and assets/ into each plugin; --check for drift
    └── validate.py                      # structural + gateway-wiring + public-repo checks
```

ChatGPT gets its own folder because ChatGPT labels an imported plugin **Desktop only** when it declares any MCP server (`mcpServers`, `mcp.json`, or `.mcp.json`), even a remote HTTPS one. The ChatGPT plugin therefore references the existing gateway app through `.app.json` and carries no MCP config. Claude Code and Cursor connect to the gateway MCP directly.

## Change something

```bash
pip install pyyaml               # once
# edit skills/, assets/, a manifest, or gateway.json
python3 scripts/sync.py          # refresh the three plugin copies
python3 scripts/validate.py      # what CI runs
```

- **Bump the version** in all three `plugin.json` files (and the Claude and Cursor marketplace entries) on every change that reaches `main`. `validate.py` fails when they disagree.
- **Add a product route:** add a `**Product:** \`<code>\`` section to `skills/ask-gateway/references/routing.md` and the code to `gateway.json`.
- The gateway's HLAdmin **Plugins** page validates this repo against the gateway's own product registry and its configured MCP URL and app id.

## Install

| Host | How |
| --- | --- |
| ChatGPT | Admin Console > Plugins > Add > **Import marketplace**. Source `https://github.com/higherlogic/plugins`, Path `chatgpt`, Branch `main`. Then open the plugin, set its installation policy, and enable the gateway app for the roles that need it. Sync runs daily, or click **Sync now**. |
| Claude Code | `claude plugin marketplace add higherlogic/plugins`, then `claude plugin install gateway@higherlogic`. |
| Cursor | Dashboard > Plugins > Team Marketplaces > **Import from Repo**: `https://github.com/higherlogic/plugins`. |

To bring an existing ChatGPT workspace plugin under this repo's management, add `"pluginId": "<id after /admin/plugins/ in its admin URL>"` to the entry in `chatgpt/.agents/plugins/marketplace.json`. The entry's `name` must equal that plugin's name.

## References

- [OpenAI: Importing and syncing plugin marketplaces from GitHub](https://help.openai.com/en/articles/20001504-importing-and-syncing-plugin-marketplaces-from-github)
- [Claude Code: Create a marketplace](https://code.claude.com/docs/en/plugins/create-marketplace)
- [Cursor: Plugins reference](https://cursor.com/docs/reference/plugins)
