# sftp-helper as an agent skill

`skills/sftp-helper/` packages `sftp-helper` as a **Claude Skill** *and* an **OpenCode
skill** — both ecosystems read the same `SKILL.md` (YAML frontmatter + Markdown
body + progressive-disclosure `references/`). Installing it lets an agent
discover sftp-helper and upload, download, list and delete files over SFTP on the user's behalf, without the user opening a
terminal.

## Layout

```
skills/sftp-helper/
├── SKILL.md                  # name + trigger-rich description + instructions
└── references/
    ├── cli-reference.md      # full subcommand + flag matrix, output contract
    ├── surfaces.md           # library, two CLIs, HTTP API, MCP
    └── triggers.md           # exhaustive, auditable trigger catalogue
```

Progressive disclosure, as the published skill standard prescribes: the YAML
frontmatter is always in the host model's context, `SKILL.md`'s body loads only
when the skill looks relevant, and `references/*.md` load only when a task
actually needs that depth. The `description` stays under the 1024-character cap;
the exhaustive trigger list lives in `references/triggers.md`.

## Install for Claude Code / Claude Desktop

Skills live under `~/.claude/skills/` (user) or `.claude/skills/` (project). To
track this repo's copy rather than duplicate it, symlink it:

```bash
ln -sfn "$PWD/skills/sftp-helper" ~/.claude/skills/sftp-helper
# per-project instead:
mkdir -p /path/to/project/.claude/skills
ln -sfn "$PWD/skills/sftp-helper" /path/to/project/.claude/skills/sftp-helper
```

## Install for OpenCode

OpenCode reads skills from `~/.opencode/skills/` (or `~/.config/opencode/skills/`):

```bash
mkdir -p ~/.opencode/skills
ln -sfn "$PWD/skills/sftp-helper" ~/.opencode/skills/sftp-helper
```

## Keeping triggers enforced

The host model only sees `SKILL.md`'s `description` before deciding to load the
skill, so every real trigger must be represented there — compressed into the
1024-character budget. `references/triggers.md` is the human-reviewable
superset, and it mirrors the repo-root `TRIGGERS.md` (the user-facing catalogue). When one changes, change the other.

**This helper moves data off the machine — that is its job.** It is the suite's
honest exception to local-first: it talks to the SFTP host *the user*
configured. The skill never embeds credentials; they come from the environment
or a `settings.yaml` the user controls. Never print a password or key back to
the user, and confirm before any `delete`.
