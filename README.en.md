[简体中文](README.md) | [English](README.en.md)

![MKT Max 1 event planning workflow](assets/readme-hero.png)

# MKT Max 1

MKT Max 1 helps a planner develop an event idea and turn the chosen direction into a readable proposal. In the first stage, **you are the lead author**. The assistant researches the market, investigates creative leads and helps you test alternatives. In the second stage, **you commission chapters and the assistant writes them** using your original material and decisions. A local Python runtime keeps the work available across conversations.

**Experimental release candidate 1.2.0-rc.4.** The skill and its working references are primarily in Chinese. The release has three known runtime defects, including a privacy issue after rollback. [Version record](version.json) · [Known issues](#validation-and-known-issues)

## How a project moves through the two stages

| Step | What the planner does | What the assistant brings back |
|---|---|---|
| 1. Frame the assignment | Share your words, existing material and the question you want to work on. Confirm the current scope and which earlier choices carry forward. | A short brief, verified constraints, its understanding of the purpose and a question that could change the next step. New full projects and restarts begin with this handback. |
| 2. Research and develop ideas | Write freely, add a fragment, change the research question or keep several possibilities open. Decide which findings to develop and where to investigate further. | Dated sources, useful details, counterevidence, unresolved conditions and a small trial grounded in the material. The assistant brings findings back to your developing draft. |
| 3. Choose a direction and hand it over | Select the experience or wording you want, explain your trade-off and identify what the writer may change. | The original passage alongside your decision, its reason, rejected alternatives, unresolved conditions and the chapters this material can support. It distinguishes wording to keep verbatim, wording open to editing, intent to preserve and material to withhold. |
| 4. Write commissioned chapters | Specify the sections, audience, purpose and depth. Review each chapter and give the next instruction. You can explicitly commission a group to be drafted together. | The actual chapter, its connection to your original and any choice still needing your judgment. The default is chapter-by-chapter review. An explicit batch commission covers only its listed group. |
| 5. Revise and accept | When a condition changes, decide any affected business or creative question. Identify the exact text you accept. | Rechecked evidence, revised passages and a review copy. The assistant also reads the surrounding prose for implications outside the recorded dependency links. |

The workflow retains **A for the current brief, B for direction and C for review**, with specific human checkpoints between them. The planner decides how to use research findings. Selecting a creative direction allows that direction to develop. A writing commission specifies which chapters the assistant may produce. Each response records the material shown, the actual decision, its scope and the current discussion round. [Workflow and checkpoints](references/workflow-and-decisions.md) · [Authorship and chapter writing](references/author-and-chapter-writing.md)

| Human checkpoint | What you receive | What your response opens |
|---|---|---|
| Current brief and restart scope | The purpose, known constraints, proposed carryover and the question for this round | Research and development within that scope |
| Research handback | Original details, counterevidence, possible uses and a small trial | Your additions, a line to develop, further investigation or continued exploration |
| Creative choice | Readable alternatives, differences and their costs | Development of the specific choice you make |
| Writing commission | Original passages, editing permissions and a chapter plan | The commissioned chapters, reader purpose and depth |
| Chapter and complete-copy review | Actual text, changes and unresolved conditions | Revisions, the next commissioned chapter or group, and acceptance of the text actually seen |
| Reconsideration after a change | New and old conditions, affected passages and possible revisions | A new decision on the affected trade-off, with valid material carried forward |

A current, explicit instruction can satisfy the corresponding checkpoint. Asking to shorten a paragraph authorizes that edit. Research, arithmetic, saving and organization continue within the commission. A focused request can finish with an invitation, cost check or revised passage. Publication, spending and implementation retain their actual authorizations and receipts.

If you commission a post-event review, the assistant compares actual attendance, participant choices, costs and unexpected effects with the original objectives. Before the event it can prepare what to observe, when and by whom. [Seven planning tasks](references/workflow-and-decisions.md)

## Research, simulation and decision owners

The event format follows what participants must actually do and which outcome the organizer would miss most. A “theatre open day” can call for three different plans. A public experience needs a visitor to hear a difference between seats. Volunteer recruitment needs a newcomer to lead a short reading and receive feedback. A recognition ceremony needs a colleague’s verified contribution and their consent to share it. When two outcomes compete for the same time or staff, the planner chooses which governs the research and first draft. [Event routing and examples](references/event-routing.md)

The assistant starts with a decision that could change. For a dated price, recruitment channel or competing event, it retrieves the current source, records the date and scope, compares it with the prior assumption and explains which choice the finding affects. Live retrieval requires search and page access from the host. Consumer simulation follows one person's choices across real alternatives, including price, time, friction and reasons to leave. Scenario rehearsal follows the people who must handle a disruption, capacity limit or handover. Simulated reactions stay labelled as hypotheses until checked against interviews, observations or records. [Dynamic research and simulation](references/dynamic-research-and-simulation.md)

| Decision | Who contributes or decides | What they see |
|---|---|---|
| Invest, defer or redirect spending | The budget holder decides. Insights and data owners check the audience, baseline and attribution. | Incremental benefit against the existing activity, competing uses of money and staff, a recommendation and the evidence that could reverse it. |
| Choose a creative direction or release a claim | The creative lead selects the experience. Brand, product or rights owners verify the specific claim. The authorized publisher decides release. | The original and trial wording, supporting source, intended audience and exact version proposed for the channel. |
| Recruit and serve participants | Sales, CRM, stores or channel owners verify matching rules, capacity, staffing and follow-up within their remit. | One example traced from entry to handover, distinguishing existing demand, additional demand and occupied slots. |
| Commit production resources or partner benefits | The producer, supplier or partner confirms what they control. The authorized project owner commits the project. | The relevant run sheet, resource or benefit, dependency, deadline and fallback. |

A department enters when its evidence or authority can resolve the current decision. For a series, the team can share an overall direction while tracking location-specific decisions and effects across dates. [Decision routing](references/event-routing.md) · [Series planning](references/series-orchestration.md)

A commissioning client might need a proposal they can read at a meeting. A producer taking over the same event might need a timed run sheet, cue, owner and fallback for each handover. Budgets, media copy, design briefs and follow-up measures enter when someone has a use for them. The bundled assembler produces Markdown. Office documents and artwork require suitable host tools and a check of the actual exported file. [Production and design handoff](references/staffing-and-design-handoff.md) · [Costs](references/commercial-and-cost.md) · [Measurement](references/measurement-and-learning.md)

## Where the planning methods come from

The skill adapts published excerpts from six event-planning books. Wang Chunlei and Chen Xiaolian connect the organizer’s purpose to observable stakeholder outcomes. Frissen, Janssen and Luijer connect the experience to participant effort, opportunity cost and the action expected afterwards. Raj and Rashid inform the comparison with competing events, willingness to pay, sponsorship and feasibility. Matthews informs supplier checks before committing to production. Su Hai distinguishes the concept proposal, budget, assignments and event-day schedule. Getz informs the distinction between an output delivered and a later outcome, including costs borne by other stakeholders. The reading guide identifies the edition, pages or preview available, source links and the specific planning action derived from each. The human checkpoints and two-stage handover belong to this skill’s collaboration design. [Reading guide and source pages](references/event-planning-books.md) · [ceyuan and software provenance](references/provenance.md)

## Try it in one project

Clone the complete directory. From your agent host, point the current project at the checkout’s `SKILL.md`. Your host needs file access and local command execution to persist work. The scripts use Python 3.10+ and the standard library. [Skill entry point](SKILL.md)

```shell
git clone https://github.com/DONGaOtang/mkt-max-.git mkt-max-1
cd mkt-max-1
python --version
```

On Windows, run the following from the checkout in PowerShell. Copy the example once, then edit `workspace_root` in your personal `config.json` to an absolute folder for your projects, such as `C:/MktMaxWorkspace`. On other systems use an absolute path appropriate to your machine. [Example configuration](config.example.json)

```powershell
if (!(Test-Path -LiteralPath config.json)) {
    Copy-Item -LiteralPath config.example.json -Destination config.json
}
notepad config.json
```

```shell
python scripts/start_agent.py init --name "Demo workshop" --id demo-workshop --config config.json
python scripts/start_agent.py resume --project demo-workshop --task "Research the audience and competing events" --config config.json
```

Then ask your agent, for example, *“Use this checkout’s SKILL.md and resume demo-workshop. I’m considering an after-work workshop. Find two ways people already solve this problem and bring me a first-hand observation or a source for each. I’ll write the opening.”* Once a direction is chosen, a second request could be *“Keep my opening verbatim. Write the participant experience and staffing chapters for internal review.”*

### Persistence and reader copies

`init` creates a collaborative project and initial revision. `resume` returns the current revision, discussion round and a task packet for the agent to read. The runtime stores source material, decisions, handovers, modules and revision history under the configured workspace. The agent submits changes with `writeback.py`, identifying the base revision and operation. The project hub (`项目中枢.md`) provides navigation back to the records and actual chapter text. The scripts manage files and revisions. Research and writing are done by the agent with the tools available in its host. [Runtime commands and payloads](references/runtime-protocol.md) · [Context and recovery](references/context-and-recovery.md)

For a new collaborative project, the default assembly is the internal working copy. It can include incomplete work, attachments, questions and blockers. The client view assembles current, reviewable chapters explicitly designated for the client, subject to role, dependency and blocker checks. It exports Markdown and a manifest used to identify the exact version shown. A person still checks the contents for sensitive wording and authorizes distribution. Internal drafts can receive chapter feedback tied to their actual text and revision. New formal output from older projects first requires the restart described below. [Reader delivery](references/reader-delivery.md)

```shell
python scripts/assemble.py --project demo-workshop --view editor --config config.json
python scripts/assemble.py --project demo-workshop --view client --config config.json
```

## Restart an existing project

Older projects remain available for reading and historical reference. In rc.4, a renewed commission or a request to start over uses `reopen` to create a new discussion round in the research phase. Original files, prior versions, actual business facts and external events remain available. Earlier direction and writing permissions are reviewed for carryover into the current round. A task description saying “return to stage one” changes the task text alone. [Round, restart and review protocol](references/runtime-protocol.md)

The assistant first saves and registers the planner’s actual restart request as a source. In this example, replace `CURRENT_REV` with the revision returned by `resume`, `RestartRequest` with that registered source ID, and the file path with the saved request.

```shell
python scripts/start_agent.py reopen --project demo-workshop --base CURRENT_REV --operation-id restart-001 --file restart-request.md --source-id RestartRequest --reason "Reconsider the event direction" --config config.json
```

If the planner explicitly retains a module, the command can include its actual reference, such as `--retain-ref module:Opening`. The assistant then hands back the proposed carryover, records the current brief, research choice, direction and chapter commission, and writes within that scope. Formal chapter submissions check the current round and the writing commission covering the chapter. Chapter-by-chapter mode requires feedback on the current preceding chapter before the next chapter. Explicit batch mode covers the named group. Internal `draft` feedback uses the shown chapter text and revision. [Reader copies and feedback](references/reader-delivery.md)

## Validation and known issues

The existing **rc.3** development record reports **76 runtime tests and 9 collaboration tests passed**. Its simulated product roadshow also exercised a mid-project change. All six apparent bookings matched existing store appointments. For that batch the six slots were occupied and the incremental booking count was zero. The team reopened the funding decision, recommended retaining the store allocation and revised the budget and reception chapters. The superseded budget copy was blocked. The planner’s chosen blind-listening opening remained byte-for-byte identical for internal rehearsal. This was a simulated review with no actual spending decision or customer results. The test suite and trial workspace are development materials outside this package.

In an isolated development workspace, rc.4 passed **99/99 tests with no skips**, comprising 76 runtime, 9 collaboration and 14 human-checkpoint tests. These cover genuine older-format project reopening, research handback, writing scope, chapter and batch review, current text fingerprints, cross-round rollback and mixed-scope permissions. Runtime and test-file hashes stayed unchanged across all four execution groups. An independent model restart sample returned the scope and paused for a human response. The development records cover synthetic program and model behavior.

| Known issue carried into the current candidate | Practical handling |
|---|---|
| A public-role task packet after rollback can reveal the path to a full comparison report containing private values. | Keep the report and packet with a trusted operator. Inspect them before sharing. Role filtering operates at the application level. |
| A module update can store a new blocking question alongside a `reviewable` status. | Read the updated blockers and status together. Client assembly checks current blockers separately. |
| A newly declared unit in `module.units` can immediately be marked `stale`. | Check the affected unit and downstream handovers against their evidence before resuming work. |

Exported Markdown is a reader copy. Reassembly writes from the registered chapter text. When a person edits an exported copy or an external original, the assistant should first preserve that revision as a source and write the changes back to the affected chapters. In-place Word and PowerPoint comments and round trips require verification with the actual host tools.

Code and documentation use the MIT License. For bug reports, include the version, a minimal reproduction, and the expected and observed behavior, using sample inputs that can be shared. [License](LICENSE) · [GitHub Issues](https://github.com/DONGaOtang/mkt-max-/issues)
