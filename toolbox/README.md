# Toolbox module: the powers Kit to Clip can use

Kit to Clip makes videos with its engine (HyperFrames). It can also call on more powers when a job needs one: a voice,
a cutout, a Lottie file, particles, a smooth slow-motion. Every power is **free** and **runs on this computer**. Each
has a **fallback**, so a video never fails because a power is missing.

```
the job ─▶ which capabilities? ─▶ toolbox.py which <capability>
                                      ├─ ✅ ready ──▶ read its recipe (and the docs it names) ─▶ use it
                                      ├─ ⬜ not installed ──▶ two lines + size ─▶ ✋ Add it / Use the fallback
                                      └─ ⚠️ / ❌ licence ──▶ use the fallback, say why in one line
```

| File | What it holds |
|---|---|
| `capabilities.json` | The jobs Kit to Clip recognises, the words people use for them, and each one's fallback |
| `cards/<id>.json` | One power: what it does, how it is detected and installed (pinned version, checksum), its licence, size, smoke test |
| `recipes/<id>.md` | What we learned using it: commands that work, traps, the docs to read first |
| `policy.json` | The licence rules: what is allowed, what a person must read first, what is blocked forever |
| `scripts/toolbox.py` | `doctor`, `which`, `check`, `install`, `smoke`, `path`, `vendor`, `licence`, `updates`, `pin`, `lint` |

## 1. Plan the powers (every job, after Step 3 in `SKILL.md`)

Read the brief and list the capabilities it needs (`capabilities.json`; match the meaning, not the words). Most jobs
need only what is built in. Then, for each extra capability:

```bash
python3 <kit-to-clip>/scripts/toolbox.py which <capability>     # exit 0 ready, 3 not ready (it prints the install line and the fallback)
```

Examples:
- *"text behind the player"* → `video-mask`
- *"for our app"* → `lottie-export`
- *"add a voice"* → `voice-over`
- *"confetti"* → `particles`
- *"logo is only an .ai file"* → `logo-convert`
- *"make it like this video"* → `video-link-read`

## 2. Equip

| `which` says | Do this |
|---|---|
| ✅ ready | Read the card's recipe (`toolbox/recipes/<id>.md`), and the upstream docs it names (`read_before_use` or the tool's own skill or `llms.txt`), before writing any code for it |
| ⬜ not installed | Say in two lines what it adds to *this* video and what it costs: disk size, free, runs here, "young tool" when the card says `early`. Ask ✋ **Add <power>** (recommended when it serves the brief) / **Use <fallback>**. On yes: `toolbox.py install <id>`, then `toolbox.py smoke <id>`. Relay ✅ or ❌ in plain words. On ❌: read the log it names, fix what is fixable, otherwise use the fallback and say so |
| 🔄 another version pinned | Install the pinned version (same ✋ as above); it replaces the old one |
| ⚠️ licence review / ❌ blocked | Never install. Use the fallback and say why in one line ("its licence doesn't allow commercial use") |

Rules:
- **Nothing installs without a ✋ yes.**
- **No uploads.** Nothing goes to an online service, and no accounts or keys are used.
- **Homebrew is welcome when present.** A card with an `install.brew` formula uses it when Homebrew is already on the
  computer. Never install Homebrew itself (it needs an admin password); without it the card's own route is used.
- **Installed powers live in `<engine>/tools/`**, never in the repo.
- **Browser libraries go into one project:** `toolbox.py vendor <id> <project>` copies their files into the project's
  `vendor/` and credits them in `CREDITS.md`. The engine renders offline, so never load them from a CDN.
- **Everything in a render must be seekable:** the same time always gives the same frame. A power whose recipe says
  "bake" is simulated once to a data file, which the video then plays.

## 3. Learn

After a job that used a power, add what you learned to its recipe only when it would help the next person: a command
that worked, a trap, a better setting. Keep it short and dated. In a studio or a public install, write it to the local
lessons instead (`memory.py lesson`). Shared recipes change through a Kit to Clip release.

## 4. Stay current and clean

- **Weekly at most, in Step 0:** `toolbox.py updates --if-due`. It checks new versions, plus new or changed agent docs,
  skills, `llms.txt`, MCP servers and CLI commands in each tool's repo, and the licence of the new version.
- **On "check for updates":** `toolbox.py updates`, then `toolbox.py updates --try <id>`. The second one installs
  the newer version in a scratch folder and runs its smoke test. Show the person what is new; with their yes, run
  `toolbox.py pin <id> <version>` and `toolbox.py install <id>`.
- **Licence watch:** `toolbox.py licence --online --deps` checks every card and every package the engine and the
  powers bring along. Blocked means never used. "Review" means a person reads the licence and the decision is
  recorded, either on the card (`licence.decision`) or in `<engine>/state/licence-decisions.json`.

## Adding a power (for maintainers)

A power earns its card through a pilot. Each card needs:
- a licence check against `policy.json`
- a pinned version with a checksum (or a pinned package version)
- a smoke test
- a fallback
- a recipe with real tested lessons

Then `toolbox.py lint` and `python3 tests/run.py toolbox` must pass.
