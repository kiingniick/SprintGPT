# Contributing to SprintGPT 🏃‍♂️💨

so you wanna make SprintGPT go **brrrrrr** even harder? absolute legend. welcome.

This project is chill. You don't need to be a pro. If you can run a Python script and
you've ever been passed by a 12-year-old at parkrun, you're qualified. Let's go.

---

## 🥛 The vibe

- Be nice. We're all just trying to run faster and ship funny code.
- Small PRs > giant mega PRs. Nobody wants to review 4,000 lines at 2am.
- If it works and it's readable, it's probably good. If it's cursed but funny, open it anyway and we'll talk.
- Milk optional but encouraged.

---

## 🛠️ Get it running (2 minutes, for real)

You'll need **Python 3.11+**.

```bash
# 1. grab the code
git clone https://github.com/kiingniick/SprintGPT.git
cd SprintGPT

# 2. make a virtual env (so you don't nuke your system python)
python -m venv .venv
# Windows:  .\.venv\Scripts\Activate.ps1
# macOS/Linux:  source .venv/bin/activate

# 3. install it in editable mode WITH the dev extras
pip install -e ".[dev]"

# 4. LAUNCH 🚀
python main.py
```

Boom. `http://127.0.0.1:5000`. Make an account, seed some fake runs if you want:

```bash
python main.py cli seed
```

---

## 🧠 Where stuff lives

Quick map so you're not lost:

| You want to change… | Go here |
| --- | --- |
| Web pages / routes | `sprintgpt/webapp.py` + `sprintgpt/templates/` |
| The look | `sprintgpt/static/style.css` |
| Install page platforms | `sprintgpt/platforms.py` |
| Race predictions / paces | `sprintgpt/predictor.py`, `sprintgpt/analysis.py` |
| Training plans | `sprintgpt/planner.py` |
| The coach chatbot | `sprintgpt/chat.py` |
| Data + database | `sprintgpt/storage.py`, `sprintgpt/models.py` |
| The Android app | `android/` (see `android/README.md`) |

There's a full map in the main [README](README.md#-project-layout) too.

---

## 🎨 Code style (keep it comfy)

- We use **[ruff](https://docs.astral.sh/ruff/)**. Before you push:
  ```bash
  ruff check .
  ruff format .
  ```
- Comments should explain **why**, not narrate the obvious. `# add one to i` is a crime.
- Keep functions doing one thing. If it's 300 lines, it's not a function, it's a lifestyle.
- Match the surrounding style. When in doubt, copy the vibe of the file you're in.

---

## ✅ Before you open a PR

1. Run the app and click around the thing you changed. Does it work? Cool.
2. `ruff check .` is happy.
3. If you added a dependency, put it in **both** `requirements.txt` and `pyproject.toml`. (yes both. i know. sorry.)
4. Don't commit secrets, your `.env`, or the database (`.gitignore` already dodges these).

Then:

```bash
git checkout -b your-cool-feature
git add -A
git commit -m "Made the thing go brrrrrr"
git push origin your-cool-feature
```

…and open a Pull Request on GitHub. Fill in the template, drop a meme if you're feeling it.

---

## 😂 Naming things (the important part)

We keep it **meme-esque**, DaniDev style. Descriptive enough to know what happened,
funny enough to enjoy the git log. The golden format:

> **`<what you did>` goes brrrrrr**

**Commit messages** — real examples from this very repo:
- `Improved clanker accuracy. Also new predictions go brrrrrr`
- `Quality goes brrrrrr`
- `Update reminders go brrrrrr`

Good:
- `Dark mode goes brrrrrr`
- `Fixed the pace math (it was on crack) — accuracy goes brrrrrr`

Please don't:
- `fix` (fix WHAT, John)
- `asdfasdf`
- `final FINAL v2 real`

**Release names** follow the same energy. Tag is boring (`v1.5`), the title is the party:
- `SprintGPT 1.5 — <feature> goes brrrrrr`

Basically: if it wouldn't make you smirk reading it back in 6 months, spice it up. 🌶️

---

## 🐛 Found a bug? Got an idea?

Open an [issue](https://github.com/kiingniick/SprintGPT/issues) — there are templates to
make it painless. Screenshots and "here's what I expected vs what happened" = chef's kiss.

Thanks for contributing. Now go make it faster. 🏁
