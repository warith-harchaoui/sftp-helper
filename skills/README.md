# sftp-helper as an agent skill

`skills/sftp-helper/` packages `sftp-helper` as a **Claude Skill** *and* an
**OpenCode skill** — both ecosystems read the same `SKILL.md` (YAML frontmatter
+ Markdown body + progressive-disclosure `references/`). Installing it lets an
agent discover sftp-helper and move files to/from a remote SFTP server on the
user's behalf without the user opening a terminal.

## Layout

```
skills/sftp-helper/
├── SKILL.md                 # name + trigger-rich description + instructions
└── references/
    ├── cli-reference.md      # full subcommand + flag matrix, output contract
    ├── surfaces.md           # library, CLIs, API, MCP (no GUI, by design)
    ├── config.md             # credentials contract + host-key policy
    └── triggers.md           # exhaustive, auditable trigger catalogue
```

Progressive disclosure: `SKILL.md` stays short and discoverable; the depth lives
in `references/*.md`, loaded only when a task needs it.

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
skill, so every real trigger must appear there. `references/triggers.md` is the
human-reviewable superset — keep the two in sync, and mirror the repo-root
`TRIGGERS.md` (the user-facing catalogue).

## Safety note

No secrets live in this skill. sftp-helper reads credentials the user hands it
(a config file, env vars, or `.env`), masks the password on `show-credentials`,
and enforces strict SSH host-key verification with no opt-out. It is **not**
local-first — its purpose is talking to a remote server — and it ships **no GUI**.
Never place real credentials or private keys in a skill file.
