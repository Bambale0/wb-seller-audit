# AGENTS.md

## Mission
Build a production-grade seller-audit tool through small, reviewable changes.

## Required playbook
For development work, use https://github.com/Bambale0/skills as the primary engineering playbook.
Prefer engineering/productivity skills, use in-progress only when appropriate, and do not use deprecated skills.

## Product rules
- MPStats/browser data is reconstruction evidence, not the final accounting source.
- Official WB/Ozon/FNS documents remain the source of truth for final tax conclusions.
- Tax calculations must be deterministic code, never delegated to an LLM.
- LLMs may classify products or explain uncertain mappings, but must return structured data with confidence.
- Never fabricate primary documents, expenses, contracts, invoices, or retroactive records.
- Keep capture logic minimally invasive: reuse the user's authenticated browser session, never store credentials.
- Do not hardcode one seller. Seller 739228 is the initial test case only.
- Every legal/tax rule must be configurable and documented with an effective date before being treated as production logic.
