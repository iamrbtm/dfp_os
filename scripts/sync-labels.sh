#!/usr/bin/env bash
set -euo pipefail

# Sync DFPos labels to GitHub
# Requires: gh CLI authenticated (gh auth login)
# Usage: ./scripts/sync-labels.sh

REPO="${1:-iamrbtm/dfp_os}"

if ! command -v gh &>/dev/null; then
  echo "Error: gh CLI not installed. Install from https://cli.github.com/"
  exit 1
fi

echo "Syncing labels to $REPO ..."

gh label create bug --repo "$REPO" --force --color d73a4a --description "Something isn't working"
gh label create enhancement --repo "$REPO" --force --color a2eeef --description "New feature or request"
gh label create task --repo "$REPO" --force --color 7057ff --description "Concrete piece of work for a milestone"

# Module labels
gh label create "module:pos" --repo "$REPO" --force --color 1d76db --description "Point of Sale module"
gh label create "module:inventory" --repo "$REPO" --force --color 1d76db --description "Inventory module"
gh label create "module:analytics" --repo "$REPO" --force --color 1d76db --description "Analytics module"
gh label create "module:markets" --repo "$REPO" --force --color 1d76db --description "Markets module"
gh label create "module:receipts" --repo "$REPO" --force --color 1d76db --description "Receipts & Expenses module"
gh label create "module:cost-engine" --repo "$REPO" --force --color 1d76db --description "Cost Engine module"
gh label create "module:prep-tasks" --repo "$REPO" --force --color 1d76db --description "Prep Tasks module"
gh label create "module:products" --repo "$REPO" --force --color 1d76db --description "Products/Catalog module"
gh label create "module:print" --repo "$REPO" --force --color 1d76db --description "Printers / Print Jobs module"
gh label create "module:auth" --repo "$REPO" --force --color 1d76db --description "Authentication / Users module"
gh label create "module:api" --repo "$REPO" --force --color 1d76db --description "REST API module"
gh label create "module:settings" --repo "$REPO" --force --color 1d76db --description "Settings / Feature Flags module"
gh label create "module:audit" --repo "$REPO" --force --color 1d76db --description "Audit Logging module"

# Priority labels
gh label create "priority:critical" --repo "$REPO" --force --color b60205 --description "Blocks release or breaks core workflow"
gh label create "priority:high" --repo "$REPO" --force --color d93f0b --description "Important, should be addressed soon"
gh label create "priority:medium" --repo "$REPO" --force --color fbca04 --description "Normal priority"
gh label create "priority:low" --repo "$REPO" --force --color 0e8a16 --description "Nice-to-have, not urgent"

# Other labels
gh label create tests --repo "$REPO" --force --color 5319e7 --description "Test coverage, test improvements"
gh label create documentation --repo "$REPO" --force --color 0075ca --description "Documentation improvements"
gh label create security --repo "$REPO" --force --color b60205 --description "Security-related issues"
gh label create performance --repo "$REPO" --force --color 008672 --description "Performance improvements"
gh label create refactor --repo "$REPO" --force --color 7057ff --description "Code cleanup, architecture changes"
gh label create "good-first-issue" --repo "$REPO" --force --color 0e8a16 --description "Good for newcomers"
gh label create blocked --repo "$REPO" --force --color 000000 --description "Blocked by another issue or dependency"
gh label create "needs-triage" --repo "$REPO" --force --color d4c5f9 --description "Needs initial review and categorization"
gh label create duplicate --repo "$REPO" --force --color cfd3d7 --description "This issue or PR already exists"
gh label create wontfix --repo "$REPO" --force --color ffffff --description "This will not be worked on"
gh label create milestone --repo "$REPO" --force --color 5319e7 --description "Milestone tracking issue"

echo "Done! Labels synced to $REPO"
