[简体中文](README.md) | [English](README.en.md)

![MKT Max 1 — From research and decisions to complete content and project continuity](assets/readme-hero.png)

# MKT Max 1

**An Agent skill and local file runtime for event projects: research the brief, establish a direction, produce complete content, and resume the work in a later conversation.**

For planners, event leads, and the content, design, operations, and commercial collaborators who review or take over their work. Requirements, sources, decisions, content, and changes live in readable project files, with a short hub for navigation rather than a chat summary carrying all project knowledge.

> **Current release: experimental 1.1.0.** [version.json](version.json) is the version authority. Confirmed problems with permission propagation, submission status, and unit invalidation remain unresolved; read “Current status and known issues” below before use. Existing validation does not establish performance in real roles, with real audiences, or in the market.

**Language status:** the skill instructions and reference library are primarily in Chinese. This English README documents usage; English-language deliverables have not been independently validated.

## What it helps with

- **Research that can support production.** Retain original source locations, declared reading coverage, the current direction, its conditions, and open questions, so the next stage can inspect the evidence.
- **Deliverables with actual content.** Write the agreed scenes, flows, rules, copy, and handover files. Outlines, schedules, status tables, and representative samples do not replace promised full content.
- **Continuity and focused revisions.** Use revision-bound task packets to locate current content and evidence, identify affected work through registered dependencies, and retain candidates and history.
- **Scope that follows the project.** Initialization creates no fixed marketing modules. Work is classified as needed now, needed later, not needed, or not yet known before it is scheduled.

The package contains skill instructions, 17 references loaded as needed, and 7 Python scripts. **The scripts do not call a model, start an Agent, provide web search, or generate native Word, PowerPoint, or design source files.** Search, reading, judgment, writing, image inspection, and other document production depend on the host's actual capabilities.

## Suitable projects and optional modules

Use it for online, physical, or hybrid events; individual events or series; and partial deliverables, reviews, or revisions of existing plans. Research depth, content depth, and handover format follow the recipient's intended use.

| Project need | Relevant work |
|---|---|
| New project, unclear direction, or insufficient material | Requirements, evidence checks, comparisons, counterarguments, direction, and stage handover |
| An established direction needing reviewable or usable content | Content units, participant experiences, concrete scenes, mechanisms, rules, and full copy |
| Recruitment, communication, or online service | Materials based on real channels, entry points, follow-through, and service conditions |
| Staffing, venues, technology, or production | Roles, capacity, shifts, design handovers, operational interfaces, and failure handling |
| Pricing, ticketing, sales, partnerships, or sponsorship | Costs, transaction terms, benefits, inventory, and fulfillment as needed |
| Multiple events, content installments, or shared resources | Series relationships, calendars, resources, costs, and rescheduling effects |
| Measurement, closeout, or learning | Metric definitions, evidence, feedback, validity conditions, and reusable records |

Marketing, sales, slogans, temporary staffing, full design work, ticketing, sponsorship, and series coordination are enabled by actual requirements. A technique used in one case does not become mandatory for every project. This package is not an automatic publishing, campaign operations, or event execution system.

## Two stages, a short hub, and actual content

**Stage 1: research, judgment, and direction.** Start with the brief, audience needs, and source material. Check important claims, compare alternatives, develop the strongest counterargument, and assess whether the material is sufficient. Hand over the effective direction, original source locations, reading coverage, conditions, open questions, and production tasks.

**Stage 2: complete content production and delivery.** Write the contracted material: what happens, who it serves, what participants see, hear, and do, how it starts and ends, what they receive, and the dependencies and failure handling. Continue an established direction; revisit the relevant research or decision when new evidence overturns it.

Closeout and feedback remain follow-up work within the original project, without adding a third plan-approval stage.

The project preserves three layers:

| Layer | Purpose |
|---|---|
| Short hub, `项目中枢.md` | Navigate the current stage, module status, important conditions, and file locations |
| Original sources, actual content, and handover files | Support research, writing, review, and delivery; large bodies are not embedded in every task packet |
| Revisions, dependencies, and task packets | Record the current baseline, input fingerprints, change effects, and locations needed to resume |

Summaries do not replace originals, and listing a file does not prove it was read. Facts, user decisions, creative proposals, and outcome hypotheses are distinguished. Written completion, confirmed resources, user approval, external execution, and observed results are checked separately. Judgments use high / medium / low / unknown confidence; model self-ratings do not establish market outcomes.

## Requirements and installation

Use **Python 3.10 or later**. The scripts use only the standard library; no `pip install` is needed. Git is required for the clone command below; downloading and extracting a repository archive is another option.

Your Agent host must be able to read the complete skill and its references, read and write the project workspace, and execute local Python. Online research additionally requires search and page-reading tools supplied by the host. In a text-only environment without these capabilities, the method can still inform work, but files cannot be claimed as saved, packets as restored, or commands as executed.

### 1. Obtain the complete directory

```shell
git clone https://github.com/DONGaOtang/mkt-max-.git mkt-max-1
cd mkt-max-1
python --version
```

The local directory is named `mkt-max-1` to match the skill name in [SKILL.md](SKILL.md). Follow your host's installation rules to place the **complete directory** in its skills location. Alternatively, ask the Agent to read the full absolute path to your local `SKILL.md`, such as `C:/your-path/mkt-max-1/SKILL.md`, and load adjacent references as needed. Installation, discovery, and tool permissions differ by host; this repository does not provide a universal installer.

### 2. Create a personal configuration

Run the following commands from the repository root. The `workspace_root` value in [config.example.json](config.example.json) is a placeholder and cannot be used directly. For initial setup, run this complete single line: it preserves the example's other fields, selects an absolute directory under your home directory, creates it, and writes the Git-ignored `config.json`.

```shell
python -c "import json; from pathlib import Path; p = Path.home().joinpath('mkt-max-workspace').resolve(); p.mkdir(parents=True, exist_ok=True); c = json.loads(Path('config.example.json').read_text(encoding='utf-8-sig')); c['workspace_root'] = str(p); Path('config.json').write_text(json.dumps(c, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'); print(p)"
```

This single line works in PowerShell, Windows Command Prompt, and common POSIX shells. Running it again overwrites your personal `config.json`; retain or edit an existing configuration instead. You may choose another workspace, but `workspace_root` must be an absolute path. Keep real project material out of the public repository.

### 3. Initialize and locate the resume packet

These two commands are ready to run after configuration:

```shell
python scripts/start_agent.py init --name "Demo workshop" --id demo-workshop --config config.json
python scripts/start_agent.py resume --project demo-workshop --config config.json
```

`init` creates the project and its initial revision; it does not produce a plan. `resume` saves a task packet and checkpoint and returns JSON fields such as `current_revision`, `context_path`, and `context_json_path`. The Agent must then read the indicated files and perform the work. Despite its name, `start_agent.py` does not start an Agent.

Project files live at `<workspace_root>/projects/demo-workshop/`. To include a real brief during initial creation, add `--brief "C:/your-path/brief.md"` to `init`. Original sources and the brief default to the `master` scope. Role fields filter task packets; they are not filesystem permissions.

## Everyday CLI: resume, write back, roll back, and assemble

See the [runtime protocol](references/runtime-protocol.md) for complete payload fields and response contracts. JSON responses report status, current revision, file locations, warnings, and next actions. Exit code 0 means the mechanical operation succeeded or the identical request was already applied.

### Resume a task

```shell
python scripts/start_agent.py resume --project demo-workshop --task "Review the current brief and identify missing inputs" --page 1 --page-size 40 --config config.json
```

Add `--module` after the module has been registered. Packets default to 40 entries per page, with a maximum of 100. Read further pages and required originals according to the returned coverage information. `--task` does not perform semantic search or guarantee that all relevant material has been located.

Repeat `--required-ref` when this task needs objects outside its currently registered dependencies. For example, `--required-ref source:YOUR_REGISTERED_SOURCE_ID` **only applies when that source ID actually exists in this project**; replace it with a real ID. Explicit required references do not persist dependencies. If the content uses them, register the relationship through `source_ids` or `depends_on` during writeback.

### Save real sources and content

Writeback types are `source`, `contract`, `handoff`, `module`, `change`, and `review`. Every JSON payload must use `file` to reference an existing, nonempty file. Each type has additional required fields; build payloads from the runtime protocol instead of editing authoritative snapshots directly.

The following are **templates requiring replacement values**, not commands to run immediately after initialization:

```shell
python scripts/writeback.py source --project demo-workshop --base CURRENT_REVISION --operation-id register-source-001 --payload "C:/your-path/source-payload.json" --config config.json
python scripts/writeback.py module --project demo-workshop --base CURRENT_REVISION --operation-id revise-module-001 --payload "C:/your-path/module-payload.json" --config config.json
```

Replace `CURRENT_REVISION` with the real revision returned by the latest `resume`, and supply an actual payload file. Modules must already exist in the contract, and production must meet the relevant handover conditions. Every successful submission creates a new revision; check the baseline again before the next submission. An `operation-id` identifies one request: the same ID and request can be retried idempotently; changed content needs a new ID.

On a baseline conflict, the runtime retains a candidate. Read the current revision, compare and revise the content, then submit with a new operation ID. Merely changing `--base` does not replace that comparison. `reviewable` means ready for review, not approved, and requires manual checking against the known status problem below.

### Restore historical content

Read the rollback-report permission issue below first. This is also a template requiring real revision values:

```shell
python scripts/rollback.py --project demo-workshop --base CURRENT_REVISION --operation-id restore-content-001 --to ANCESTOR_REVISION --reason "Restore the reviewed content for comparison" --config config.json
```

`ANCESTOR_REVISION` must be a committed ancestor. Rollback creates a new revision, restores historical content and source references, retains current facts, current decisions, and all external events, and produces a difference report. It does not undo real messages, contracts, purchases, or events, or automatically reactivate historical approvals.

### Assemble a deliverable and run supporting checks

Run these after the project has eligible contracted modules and actual content:

```shell
python scripts/assemble.py --project demo-workshop --config config.json
python scripts/cost_check.py --project demo-workshop --config config.json
python scripts/repair.py --project demo-workshop --config config.json
```

By default, `assemble` combines `now` modules in contract order into `deliverables/<revision>/complete-plan.md` with an input-fingerprint manifest. Use `--modules` with real module IDs for a selection. Missing content, stale dependencies, or relevant blocking conditions prevent assembly. Assembly does not write missing content, assess its quality, or export `.docx` or `.pptx`.

`cost_check` is a read-only structural and arithmetic check of registered costs; it does not verify quotations. `repair` rebuilds derived views such as the hub and catalogs and reports diagnostics. It does not repair corrupt authoritative history or forcibly unlock projects. Handle warnings, blockers, and unfinished work according to their actual causes.

## Three example Agent requests

Load the complete skill in the host first, or provide the Agent with the absolute path to your local `SKILL.md`. Project IDs must refer to initialized projects. Replace source locations, scope, and intended use with the actual brief.

**Research and direction:**

```text
Use mkt-max-1 to resume demo-workshop with this repository's config.json.
This is a workshop for first-time participants; use my Brief as the authority for its goals and inputs.
Read the packet, Brief, and required originals. Check audience needs, content material, and key conditions.
Research and compare choices, develop the strongest counterargument, and separate facts, proposals,
and untested hypotheses with explicit confidence levels. Deliver a reviewable direction and stage
handover, saving source locations, reading coverage, open questions, and production tasks.
```

**Complete content production:**

```text
Use mkt-max-1 to resume demo-workshop. Continue the current effective direction and contract.
Read the stage handover and the original material actually used. Write complete content for modules
needed now, including participant experiences, scenes, rules, all agreed copy, and handover files.
Handle gaps according to the current intended use. Pause only finalization that depends on a
substantive decision, and continue other authorized work. Save each part, cross-check shared facts
and interfaces, then assemble Markdown and accurately list unfinished items.
```

**Focused revision:**

```text
Use mkt-max-1 to resume demo-workshop. I will provide a new event date and evidence of approval.
Check the current revision and originals, record the change, and examine affected content,
staffing, resources, costs, and copy. Revise the actual content and handover files while retaining
unaffected valid work. Check stale markers and open questions, write back against the current
baseline, and report changes, affected scope, and outstanding confirmations. Do not edit snapshots.
```

## File layout

```text
mkt-max-1/
├── SKILL.md                 # Skill entry point and working protocol
├── agents/openai.yaml       # Agent interface metadata
├── references/              # 17 references, including runtime protocol and provenance
├── scripts/
│   ├── start_agent.py       # init / resume
│   ├── writeback.py         # source / contract / handoff / module / change / review
│   ├── rollback.py          # Restore content as a new revision
│   ├── assemble.py          # Assemble actual Markdown content
│   ├── cost_check.py        # Cost structure and arithmetic checks
│   ├── repair.py            # Derived-view rebuilding and diagnostics
│   └── hub_runtime.py       # Standard-library runtime implementation
├── assets/readme-hero.png
├── config.example.json      # Distributable example configuration
├── config.json              # Personal configuration; created during setup and Git-ignored
├── version.json
├── LICENSE
├── README.md
└── README.en.md
```

Under the configured workspace, `projects/<project-id>/` holds `项目中枢.md`, `HEAD.json`, `revisions/`, `assets/`, `candidates/`, `work/`, `operations/`, and `deliverables/`. Originals, history, and candidates remain in the project; the public repository contains no real project material. Back up complete content, historical revisions, and your original inputs together.

## Current status and known issues

**1.1.0 is experimental. These three confirmed problems remain unresolved.** Checks and filtering described in the runtime protocol are not a guarantee that the current implementation is defect-free.

| Known issue | Current effect and usage boundary |
|---|---|
| Rollback difference reports do not inherit permissions for private values | A `public` task packet can expose a location for the full report, which may contain private values. Use full rollback reports only in the master-controlled environment; inspect packets after rollback before distributing them to other roles. Packet filtering is not an operating-system ACL. |
| Module submission checks old `unresolved` entries before storing the new ones | A submission can leave `reviewable` status alongside a newly added `blocking` question. Manually check the content status and all new unresolved entries after submission; the status field does not establish readiness for finalization. |
| Units included in a `module.units` submission can be incorrectly marked `stale` | Newly saved units and downstream work may be blocked. Inspect the actual objects, evidence, and effects. Do not bypass this by changing version numbers or directly editing authoritative snapshots. |

There are also two explicit validation limits:

- The blind-draft validator does not sufficiently check the one-to-one correspondence between `source` and `anonymous` drafts. Inspection of the current 48 drafts found no mismatches, but this does not establish that the validator covers this failure mode.
- First-packet token counts exclude later navigation: the recorded first-packet comparison is 7,304 versus 6,832, while the complete two-page count is 7,659. Different reading scopes cannot support a direct benefit comparison; no token-saving claim is made from these numbers.

Synthetic cases and model reviews do not replace handover to real professionals, actual audience experience, or market validation. The historical 76-test result does not certify the current release as defect-free. Structural checks, content review, permission checks, and verification of real execution remain separate tasks.

## Provenance, license, and feedback

The method draws on this workspace's ceyuan2, ceyuan3, and ceyuan4, reorganized into requirements-driven research, conditional reasoning, content production, and delivery. File navigation, task packets, and revision mechanisms draw on fixed versions of Agent Skills, Deep Agents, OpenSpec, GSD Core, and Aider. See [provenance](references/provenance.md) for the adoption boundaries and pinned links. The runtime is independently implemented with Python's standard library and does not require those frameworks.

Code and documentation are released under the [MIT License](LICENSE). Preserve the license and copyright notices. Using this package does not automatically grant redistribution rights to third-party material or user project originals.

Report feedback through [GitHub Issues](https://github.com/DONGaOtang/mkt-max-/issues). Include the version, a minimal reproduction command, expected and actual behavior, and sample inputs with private material removed. Do not upload a complete private project or a rollback report containing private values.
