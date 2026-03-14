# Project Management Docs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a project-wide status dashboard and a handoff document so future agents can understand phase progress and continue work with minimal rediscovery.

**Architecture:** Use one stable overview document for project management and one root-level handoff document for engineering continuity. The status file should be checklist-driven and phase-oriented; the handoff file should be operational and branch-aware, with explicit verification evidence and known pitfalls.

**Tech Stack:** Markdown, git history, existing plans in `docs/plans/`, current repository state on `codex/phase1-runtime`

---

### Task 1: Add Phase Overview Status Board

**Files:**
- Create: `docs/project-status.md`

**Step 1: Write the failing test**

Use a manual checklist:

```text
- File exists at docs/project-status.md
- Contains Phase 1, Phase 2, and Phase 3 sections
- Uses checklists for milestones and todo items
- Includes current branch-aware status note
```

**Step 2: Run test to verify it fails**

Run: `test -f docs/project-status.md`
Expected: exit code 1 because the file does not exist yet.

**Step 3: Write minimal implementation**

Create `docs/project-status.md` with:

- current snapshot
- phase-by-phase milestone checklists
- outstanding deployment and merge tasks
- known risks/blockers

**Step 4: Run test to verify it passes**

Run: `rg -n "Phase 1|Phase 2|Phase 3|Milestones|Todo|Risks" docs/project-status.md`
Expected: matching lines prove the status board structure exists.

**Step 5: Commit**

```bash
git add docs/project-status.md
git commit -m "docs: add project status dashboard"
```

### Task 2: Add Engineering Handoff Document

**Files:**
- Create: `HANDOFF.md`

**Step 1: Write the failing test**

Use a manual checklist:

```text
- File exists at HANDOFF.md
- Explains current branch and important commits
- Lists what was tried, what worked, and what failed
- Includes next recommended steps and deploy prerequisites
```

**Step 2: Run test to verify it fails**

Run: `test -f HANDOFF.md`
Expected: exit code 1 because the file does not exist yet.

**Step 3: Write minimal implementation**

Create `HANDOFF.md` with:

- project snapshot
- verified commands and outcomes
- completed work summary
- ineffective or broken approaches already discovered
- remaining work and deployment prerequisites
- important files to inspect next

**Step 4: Run test to verify it passes**

Run: `rg -n "Project Snapshot|What Worked|What Did Not Work|Next Recommended Steps|Deployment Prereqs" HANDOFF.md`
Expected: matching lines prove the handoff structure exists.

**Step 5: Commit**

```bash
git add HANDOFF.md
git commit -m "docs: add engineering handoff notes"
```
