# KYAPTURE AGENT RULES (read before every task)
- Branch: feature/landing-page-redesign. Never merge to main. Never touch cPanel/AWS/production unless the task says so.
- Never touch benchmark/, benchmark-artifacts/, DB volumes, Docker volumes.
- Trace existing code first. Reuse existing models/APIs/helpers. No duplicate endpoints, models or systems.
- Backend is authoritative (auth, ownership, plan entitlement). Frontend only presents.
- No fake UI: every button real; success toast only after real API success; no decorative toggles.
- Preserve all earlier tasks. Smallest safe change set. No unrelated refactors.
- Originals stay private and byte-preserved. Never expose private storage paths.
- Claims need evidence (test output, measured numbers). Never write 'optimized' without numbers.
- Always run relevant backend tests + frontend build. Browser-verify every UI change (desktop + 390px).
- Final report max 25 lines: files changed, endpoints/models changed, tests run + result, browser QA, known gaps, git diff --stat. Then STOP.
## Settings / UI rules (apply to every settings screen)
- Match the Pixieset layout in docs/pixieset-ref/ screenshot for that screen; KYAPTURE colors/fonts only.
- Flat sections, no card-inside-card, no big upsell boxes. Locked Pro options show a short inline "Upgrade required. Upgrade" link to Billing.
- Every setting autosaves on change/blur/Enter with a small toast "Collection updated". No separate Save/Set buttons.
- Optional features use an On/Off toggle; turning On reveals its field. Off = disabled (null), never a leftover value.
- Secrets (password/PIN): typed by the photographer, never auto-generated, never returned in plain text; show masked with Change.
- No fake controls: every control is wired to the backend and enforced server-side.
- Verify at desktop and 390px; screenshot next to the Pixieset target.
QA cleanup: delete ONLY rows by exact id/email created in this session. Never delete by pattern (endswith / contains / LIKE). Before deleting, print the rows and confirm the count matches what you created.