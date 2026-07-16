# Not Needed Archive

This folder contains non-code files removed from the active project tree on
2026-07-16. Nothing was deleted.

## Archived items

- `generated/coverage/`: old coverage database outputs.
- `generated/browser-tests/playwright-mcp/`: Playwright browser capture logs and
  page snapshots.
- `generated/browser-tests/test-results/`: generated end-to-end test failure
  reports.
- `generated/one-off-output/test.json`: a one-off cost-engine response dump.
- `local-tooling/idea/`: machine-specific JetBrains IDE project state. This
  directory stays local and is excluded from version control because IDE
  connection metadata can contain private host and account details.
- `system-metadata/ds-store/`: macOS Finder metadata, stored under its original
  relative paths.

The IDE folder's original `.gitignore` is named `gitignore.archived.txt` here so
it does not hide other files inside this archive.

These files are not required to run, test, build, or deploy DFPos. Generated
test and coverage artifacts may reappear after running development tools; the
repository ignore rules now cover them.

## Intentionally retained

Project documentation, business data imports, research reports, lock files,
environment examples, migrations, static assets, and `product page.pdf` remain
in their original locations because they are either required or may be useful
reference material.
