# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in the **sumnews** repository.

### Plans

**IMPORTANT**: Keep plan files in the project's `.claude/plans/` directory (gitignored). Use descriptive kebab-case filenames — examples: `core-domain-models.md`, `auth-refresh-flow.md`. Make all plans with checkboxes for tracking progress

### Python invocations

**IMPORTANT**: For ad-hoc Python (smoke imports, one-off `python -c "..."`, REPL probes), use `uv run python` — never raw `python` / `python3`.

- On host: `uv run python -c "..."`
- In the shell container: `docker compose exec -T shell uv run python -c "..."` (after `make shell-ensure` if not running)

`sumnews` is an installed package, so imports resolve from any working directory — no `PYTHONPATH`, no `sys.path` juggling.

## Commands

Targets are available in the Makefile; the most commonly used ones:

```bash
# Lint with ruff (src + tests); lint-fix auto-fixes; lint-all runs every source-code check
make lint
make lint-fix
make lint-all

# Type checking
make lint-typecheck

# Quick pre-commit: lint + test only
make check
# Run ALL checks (fail-fast)
make check-full

# Unit/integration tests
make test
make test ARGS="-k test_auth"
```

**IMPORTANT**: After code changes always run the full lints — `make lint` and `make lint-typecheck` (or `make lint-all`). They are instant — prefer them over per-file `ruff`/`mypy` invocations. Run `make test` as well; use `-k` filters during development for fast feedback.

Prefer the `make` target over the raw command it wraps whenever one exists, and read its output as-is. Piping it through `grep` / `head` / `sort` to filter or reshape hides both context and count, and a green `tail` over a failed command masks its exit code — on a target you're treating as a pass/fail gate, read it in full. Elsewhere, filter when the raw output is genuinely too noisy to work with.

## Workflow

### Implementing a plan or multi-item task

Work the list one item at a time — **drafting each change before touching a file**.

0. **Verify the item against current source.** Every count, location and "has no callers" is a hypothesis — re-run the greps, and check the premise, not just the symptom: a real problem can carry a wrong cause or an illusory benefit. When the fix is small, applying it and watching it fail beats more reading.
1. **Draft the item.** Show the proposed code, the trace through producers and consumers that justifies it, and any decision that's genuinely the user's. Keep it short and to the point: a draft is a proposal to react to, not a document. Touch no files yet — the draft ends your turn.
2. **Wait for accept / decline / redirect.** This is the step that earns the others — a wrong approach should die in a message, not in a diff. Argue for the draft if challenged, but drop it cleanly on new evidence.
3. **Only then edit**, and verify: `make lint`, `make lint-typecheck`, and the relevant `make test`. For a bug fix, reproduce the bug and show it gone — a new test that passes proves nothing until it has failed on the broken code.
4. **Pause for review** before the next item. Surface anything noticed but not fixed as a short addendum.

### Test writing principles

- **Guaranteed cleanup**: use fixtures with automatic teardown, not manual cleanup. Only test entities we create and can guarantee cleanup for.
- **Robustness**: tests must work when tables already contain data — check for specific entities, never assume counts or order; compare as sets, not lists.
- **Real failure scenarios**: every test should check a code path that could plausibly break. Don't test framework guarantees, language semantics, impossible inputs, or simple wrappers already covered by their dependencies' tests.
- **Fixture dependency order**: structure dependencies for correct cleanup order.

## Coding style

### Response style — concise, no compromise on detail

Be terse. No filler, no restating the request, no narrating what you're about to do beyond what's needed for the user to follow along, no trailing summary of changes already visible in the diff. Cover every part of the task, list every file touched if multiple, surface caveats — compress wording, not substance.

### Pushback — disagree when the idea is wrong

If the user's approach is bad, say so plainly with concrete evidence (failure mode, conflict, violated invariant, footgun). No diplomatic hedging, no burying the objection in alternatives, no agreeing now and quietly doing it differently. "I'd write it differently" is taste — drop it. Don't capitulate to pushback alone; update only on new information, and when you do, drop the objection cleanly.

### Verify before claiming — no guessing

Don't assert facts about this codebase, a library, or the environment that you haven't checked. Grep, Read, or run before claiming. When verification genuinely isn't possible (external system, prod-only behavior, no network), say so explicitly — "I haven't verified this, would need to check X" — rather than presenting a guess as fact. Web search is fair game when local verification can't answer it.

### Trace the chain — read files, don't infer from names

When behavior depends on how pieces connect (who sets a value vs who reads it, what a dependency injects, whether something is cached, lazy, or overridden), read the actual files end-to-end and follow the chain. Don't infer it from a symbol name, a single grep hit, or a plausible-sounding assumption. A grep locates code; it doesn't tell you the data flow. Before reasoning about a value, confirm every producer and consumer by reading them. State the trace you actually did, not what the names suggest is happening.

### Stay in scope, surface the rest

Do what was asked, not what's adjacent. When you notice unrelated issues while fixing X, finish X, then list them as a short addendum ("also noticed while in here: ... — want me to handle these?"). The user decides whether each becomes a follow-up.

Exception: if Y is genuinely required for X to work (a dependency, a broken assumption X relies on), fix it — but call out explicitly that the change grew.

### Ask when it matters — use AskUserQuestion more

When the work hinges on a decision only the user can make (which library, which behavior, which of several reasonable interpretations of the request), reach for `AskUserQuestion` rather than picking silently and hoping. Batch the decision into one structured question with 2–4 concrete options, each with a one-line description of the tradeoff. A single well-framed question early is much cheaper than rework later.

Don't ask what you can grep, don't ask permission for the obvious, don't ask trivial preferences.

### Write the best version, not the nearest one

The first shape that comes to mind is the existing code with the change grafted onto it. Ask what the code would look like written for its current requirements, and write that instead. A small diff is not the goal, and preserving an awkward structure because it is already there is not a reason.

If the better version is bigger than the task at hand, propose it and let the user decide — never settle for the nearer one silently. The same goes for anything noticed along the way: a duplicated helper, a signature that fights its callers, a check living in the wrong layer. Flag it, with what it would take.

### Bail out of failed approaches early

If two or three attempts at the same approach aren't converging, stop and reassess. Say so directly: "this isn't working because X, switching to Y" or "stuck — here's what I tried, here's where I'd look next." Don't pile band-aids on a broken approach.

### Verify the user's claims too

Users misremember their own codebase. When the user asserts something about the code ("we already handle X", "Y was removed", "Z is wired up"), check before building on it. If the code disagrees, surface it with the `file:line` — don't quietly work around the mismatch.

### File edits — batch changes together

When making multiple changes to a single file, batch them into one comprehensive Edit call rather than many small edits.

### No unnecessary defensive coding

Trust internal data flow. When a function produces a dict with known keys, use `dict["key"]` — not `.get("key", fallback)`. When an ORM model declares a relationship, don't `hasattr()` check it. When `Path.unlink` has `missing_ok`, don't pre-check `exists()`.

Reserve defensive patterns for **actual boundaries**: external API responses, user input, deserialized data from outside the system. If we created the data and control the producer, direct access is correct — a `KeyError` on missing data is a better signal than a silent fallback hiding a real bug.

### Variable naming — use full names for entities

```python
# Good:
document = Document.from_path(path=file_path)
extraction = ExtractionResult(document_id=document.id, ...)

# Bad:
doc = Document.from_path(path=file_path)
ext = ExtractionResult(document_id=doc.id, ...)
```

**Acceptable abbreviations**: `ocr`, `db`, `llm`. One-letter variables fine in comprehensions.

### Return statements — no function calls

Compute the result first, then return it:

```python
# Good:
user = await manager.user_db.get_by_name(username=username)
return user

# Bad:
return await manager.user_db.get_by_name(username=username)
```

**Exception**: Creating dicts or typed class instances in return statements is allowed.

### Settings format — description on its own line

For `pydantic` `Field()` in `Settings`, put `description` on a new line indented 4 spaces past the field name. `default` stays inline with `Field(`. This form is `Settings`-only — every other `Field()` follows the align-to-first-argument rule below.

```python
# Good:
UPLOAD_DIR: Path = Field(default=Path.cwd() / "uploads",
    description="Absolute path to upload directory")

# Also acceptable — fully broken-out form, use when args don't fit comfortably
# on two lines (e.g. long defaults, multiple kwargs):
UPLOAD_DIR: Path = Field(
    default=Path.cwd() / "uploads",
    description="Absolute path to upload directory",
)
```

### Docstrings — numpy format

Single-line when self-explanatory. Full numpy format (Parameters/Returns sections) only when parameters need clarification. Fill lines to the 120-col width — don't wrap narrow — and break a multi-sentence body one sentence per line rather than mid-sentence.

### Match the surrounding level of detail

Freshly written code attracts explanation its neighbours never got — a docstring paragraph for one of five state-dict keys, a comment on one of three matching clauses. Both read as "this one is different". Document at the level the surrounding code already uses.

### Line wrapping — align to first argument

```python
# Correct:
extraction = ExtractionResult(document_id=document.id,
                              ocr_result_id=ocr_result.id,
                              extractor_name=extractor.name)

# Wrong — aligned to opening parenthesis, not first arg:
user_data = User(username=username,
                password_hash=password_hash,  # ← one space off
                role=UserRole.USER)
```

**Rule**: Continuation lines start at the same column as the first character of the first argument.

### Keyword arguments — always explicit

```python
# Always:
user_data = User(username="alice",
                 password_hash=hashed,
                 role=UserRole.USER)

# Never:
user = User("alice", hashed, UserRole.USER)
```

### Annotations — use builtins

`list[str]`, `dict[str, int]`, `tuple[bool, str]` — never `List`, `Dict`, `Tuple` from typing.

### Enums over magic strings

Categorical values the code branches on live as enums. Never bare string literals or substring checks: compare against the member (`task.status == TaskStatus.PENDING`), key dicts and registries by it, and iterate the enum where you need its members in order rather than restating them as a tuple. New ones are `StrEnum`.

### Imports — top level unless local earns it

Module level by default. A function-local import needs a concrete reason, named in a comment beside it — an optional dependency, or flag-gated loading that must not pull in a disabled feature's module tree. A cycle is the weakest reason: attempt the layering fix first, and settle for a local import only when no refactor removes it.

### Comments — section separators in logic-heavy functions

Use `# Section name` comments to break up long functions into logical blocks.

### SQL reads like a pipeline

Chain one clause per line — leading dot, uniform +4 indent under the opening paren, closing paren on its own line — inside `execute(…)` and `x = ( … )` builder assignments alike (not the align-under-the-paren form). Trivial 2-call base builders stay on one line.

### Prompt design — write for the consumer

A tool's system prompt (and any intermediate-stage LLM call) should be framed for the _next step_ that will read its output, not for the caller or the end user. Use positive completeness instructions and name the consumer. Compression for the human reader belongs in the agent / response-generation layer, not in an extractor — the extractor doesn't get a second chance to recover info it dropped.

### CSS — use variables for consistency

Use CSS variables for related states (e.g., sidebar full vs collapsed) to prevent values from drifting.

## Tools

### Editing — Edit/Write only

Change source with the Edit/Write tools. Nothing else may write a source file — not shell redirection, not a heredoc, not `sed -i` / `awk`, and not a `python` snippet that reads a file and writes it back. This holds even when the change is mechanical and the script is obviously correct: a rewrite you didn't compose line by line is a diff you didn't review. Ad-hoc Python for _reading_ stays fine — probing state, checking a schema, computing a number, generating fixture data to paste. It's the writing that's banned.

The one carve-out is when the task itself is the sweep — a feature or fix whose whole point is a mechanical transformation across the tree, typically a pure identifier rename (same symbol, no logic change). Not "this edit would be tedious": deliberate, and Edit's `replace_all` already covers most of it. Say you're taking the carve-out before you run it, then read the full `git diff`, confirm `grep -rn '<old_name>' src tests` comes back empty, and run `make lint` + `make lint-typecheck`.

Rename **completely** — internals, ids, template variables, fixtures, tests, docstrings. Don't rename a display string and leave the old name in the code, and don't leave a dead alias behind.

For a temporary revert (verifying a test fails without its fix), err toward an inverse Edit, or a flag that switches the code off in place (`if False:`) — then undo it with a second Edit. `git stash push -- <files>` / `git stash pop` is the fallback when the change is too wide to invert by hand. Never `git checkout <file>`: it restores from the index and silently discards later work when a stash pop left something staged.

### Reading — read the flow, not isolated hits

A grep hit locates code; it doesn't explain it. Once you've located a file you'll edit or reason about, read the flow it sits in — the function with its producers and consumers, the surrounding class or module — rather than assembling an understanding out of single-line hits and inference. Cheap context now prevents wrong assumptions later, so err toward the wider read when the call is close. Reach for `grep`/Glob for genuine searches: finding where a symbol is defined or used, confirming an unknown.

Read a small file whole; on a large one, read the ranges the flow actually passes through. Coming back to a file that's already in context, re-read just the range that moved. Batch independent tool calls into one message. After a compaction, re-establish state from `git diff` / `git log` / the plan file rather than re-reading modules from scratch.