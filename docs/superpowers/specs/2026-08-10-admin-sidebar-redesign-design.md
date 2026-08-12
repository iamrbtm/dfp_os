# Admin Sidebar Redesign

Date: 2026-08-10

## Goal

Redesign the authenticated app sidebar so it is easier to scan and faster to use without removing any existing menu destination.

The redesign should optimize for both:

- daily operational speed
- clearer understanding of the full DFPos module structure

## Current Problem

The current sidebar is mostly a long flat list of top-level items with a few section-specific child links that only appear when the related section is active. This creates three usability issues:

- the menu feels too long because many unrelated items have equal visual weight
- the system is harder to understand because related modules are not grouped into clearer mental models
- some important child destinations feel hidden because they only appear after entering a section

## Chosen Direction

Use a workflow-first sidebar with a small quick-access area.

This keeps the app understandable at the module level while prioritizing the pages a daily operator is most likely to need.

## Information Architecture

### Quick Access

A compact top section for high-frequency entry points:

- Dashboard
- Notifications
- POS

Quick Access remains visible above the larger grouped navigation.

### Main Groups

Group all existing destinations into collapsible sections:

- Sell
- Make
- Stock
- Money
- Grow
- System

Each group header should:

- act as a disclosure control
- show an expanded/collapsed indicator
- auto-expand when the current page belongs to that group

Each primary destination inside a group remains clickable as a normal navigation link.

## Group Mapping

### Sell

- POS
- Customers
- Orders
- Custom Orders
- Pickup Board
- Order items and payments through section context links where already supported

### Make

- Products
- Categories
- Collections
- Print Jobs
- Printers
- Printer Reliability

### Stock

- Inventory
- Markets
- Prep Tasks
- Follow-Up Queue
- Impulse Tray

### Money

- Receipts
- Receipt Inbox
- Receipt Upload
- Expenses
- New Expense
- Cost Engine
- API Tokens

### Grow

- Analytics
- Report Studio
- Trend Scout
- Trend Scout Calibration
- DFP Intelligence
- Ask DFP
- Market Advisor
- Notes
- Legacy Import
- Normalized Pipeline
- Promotion

### System

- Settings
- Business Settings
- Module Status
- Themes
- Feature Flags
- Notifications if needed as a fallback destination

## Behavior

- No destination is removed.
- Existing active-state styling remains token-based.
- The active section expands automatically.
- Other groups may be expanded or collapsed by the user.
- Child links that are currently hidden behind active-section checks should be visible when their containing group is expanded.
- Mobile sidebar behavior stays consistent with the current off-canvas interaction.

## Interaction Rules

- Group headers should be visually distinct from item links.
- Primary links inside a group should keep stronger emphasis than child links.
- Child links should read as related tools, not separate top-level modules.
- The number of always-visible first-level items should be reduced substantially compared with the current flat list.

## Implementation Approach

- Replace the hand-authored flat sidebar structure with grouped navigation data assembled in the template.
- Reuse existing routes and module checks.
- Keep current theme tokens for colors, borders, and active states.
- Use Alpine state for independent group expansion.
- Preserve the existing `active_section` server-side context so the template can determine default-open groups.

## Risks

- Some destinations do not map cleanly to a single group; those choices must remain consistent.
- A group-heavy sidebar can become slower if disclosure controls are unclear.
- Existing tests may assume specific sidebar text ordering.

## Verification

- Confirm every existing destination still renders when its module is enabled.
- Confirm active sections open the correct group.
- Confirm mobile open/close behavior still works.
- Confirm theme tokens still style the sidebar correctly.
- Confirm no route or permission behavior changes.
