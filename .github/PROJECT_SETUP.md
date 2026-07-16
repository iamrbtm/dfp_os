# DFPos GitHub Project Board Setup

This repo uses GitHub Issues + Projects for tracking work. The project board is configured as a **Kanban-style** board with these columns:

## Columns

| Column | Purpose |
|--------|---------|
| **📋 Backlog** | Unstarted work, prioritized by milestone |
| **🎯 To Do** | Work targeted for current/next milestone |
| **🚧 In Progress** | Actively being worked on (one per person) |
| **👀 Review** | PR open, needs review |
| **✅ Done** | Merged and deployed |

## Automation

- **New issues** → automatically added to Backlog
- **PR opened** → moves linked issue to Review
- **PR merged** → moves linked issue to Done
- **Reopened issue** → moves back to To Do

## Labels

Labels are organized into categories:

- **Type:** `bug`, `enhancement`, `task`, `tests`, `documentation`, `security`, `performance`, `refactor`
- **Module:** `module:pos`, `module:inventory`, `module:analytics`, etc.
- **Priority:** `priority:critical`, `priority:high`, `priority:medium`, `priority:low`
- **Status:** `blocked`, `needs-triage`, `good-first-issue`, `duplicate`, `wontfix`

## Milestones

Milestones represent major releases or phases. Current milestones map to the Phase structure in `docs/`.

## Using the Board

1. **Create an issue** using the provided templates (Bug Report, Feature Request, Task)
2. **Label it** with the appropriate type, module, and priority
3. **Assign it** to the relevant milestone
4. **Move to In Progress** when you start working
5. **Link your PR** to the issue using closing keywords like "Closes #123"
