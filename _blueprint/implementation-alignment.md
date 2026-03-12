# Implementation Alignment Report

*Generated: 2026-03-12*
*Purpose: Identify inconsistencies between blueprint docs and actual implementation state.*
*Action: Use this list in a separate session to replan and fix.*

---

## 1. ROADMAP.md — Stale Status and Broken Links

**File**: `_blueprint/roadmap/ROADMAP.md`

### 1a. Phase statuses not updated (lines 18-25)
Phases 2, 3, 4 all show "PLANNED" but are COMPLETE. Only Phase 1 is marked done.
```
Phase 2: JWT Infrastructure .......................... PLANNED   ← should be ✅ COMPLETE
Phase 3: Token Exchange .............................. PLANNED   ← should be ✅ COMPLETE
Phase 4: OAuth Login + Session ....................... PLANNED   ← should be ✅ COMPLETE (4a, 4b, 4c)
```

### 1b. All spec links are broken (lines 52, 72, 90, 109, 129)
Roadmap links to files that don't exist:
- `features/phase2-jwt-infrastructure.md` → actual: `phase2-jwt-infrastructure-v2.md`
- `features/phase3-token-exchange.md` → actual: `phase3-token-exchange-v2.md`
- `features/phase4-oauth-login.md` → actual: `phase4-oauth-login-v2.md`
- `features/phase5-rbac.md` → actual: `phase5-rbac-v2.md`
- `features/phase6-rbac-management.md` → actual: `phase6-rbac-management-v2.md`

The implementation guides (`implementation-phase{N}-*.md`) also exist but are not linked.

### 1c. Phase 4 description is outdated (lines 86-101)
- Line 96: Says "Minimal Jinja2+HTMX test UI" — we used Tailwind CDN, no HTMX
- Line 88: Description doesn't mention Phase 4c (admin dashboard, UIConfig, auth guard)
- Line 99: Dependencies list is incomplete — missing `pytest-playwright`

### 1d. Phase 5 — SecretsStorage overlap (lines 105-121)
- Line 113: Lists `SecretsStorage` as a Phase 5 deliverable
- Line 119: Lists `google-cloud-secret-manager` as a Phase 5 dependency
- **Reality**: `SecretsStorage` (partial: `_load_secret`, `get_client_secret`) and `google-cloud-secret-manager` were already added in Phase 4b. Phase 5 spec should reference the existing partial implementation and only add the RBAC-specific methods.

### 1e. Phase 6 Admin UI conflict (line 134)
- Says "Admin UI — Jinja2+HTMX at `/admin/*`"
- **Reality**: Admin UI already exists at `/ui/` (built in Phase 4c) with Tailwind CSS, not HTMX. Phase 6 should extend the existing `/ui/` dashboard rather than creating a new `/admin/*` UI.

### 1f. Last updated date stale (line 12)
Shows 2026-03-08, should reflect current state.

---

## 2. decision-log.md — Outdated Decisions

**File**: `_blueprint/roadmap/decision-log.md`

### 2a. Admin UI decision is outdated (line 28)
Says: "Jinja2+HTMX admin dashboard at `/admin/*`"
**Reality**: Built with Jinja2 + Tailwind CSS at `/ui/`. No HTMX. The decision should be updated to reflect the actual implementation and the `/ui/` route prefix.

### 2b. Missing Phase 4b/4c decisions
The decision log stops at 2026-03-08. Major decisions from Phase 4 sessions are only recorded in `implementation-progress.md`, not in the decision log:
- Phase 4c: Tailwind CDN over HTMX
- Phase 4c: UIConfig as separate Pydantic model (not in core Settings)
- Phase 4c: UI auth guard via Depends() vs middleware
- Phase 4c: Session cookie auth (UI) vs JWT auth (API) — two separate patterns
- Phase 4b: SecretsStorage pulled forward from Phase 5

### 2c. Last updated date stale (line 5)
Shows 2026-03-08.

---

## 3. implementation-phase4-oauth-login.md — Stale References

**File**: `_blueprint/features/implementation-phase4-oauth-login.md`

### 3a. Decision D8 references `/ui/test` (line 29)
Says: "Post-login redirect hardcoded to `/ui/test` (MVP)"
**Reality**: Redirect changed to `/ui/` in Phase 4c. This decision is now outdated.

### 3b. Status still says "Ready to implement" (line 12)
Phase 4 is complete (4a, 4b, 4c all done). Should be marked as COMPLETE or moved to archive.

### 3c. No mention of Phase 4b or 4c
The spec was written before the phase was split into 4a/4b/4c. It doesn't cover:
- SecretsStorage (pulled from Phase 5 into 4b)
- Admin dashboard / UIConfig (4c)
- Auth guard for UI routes (4c)
- list_all() on SessionStore (4c)

---

## 4. implementation-phase5-rbac.md — SecretsStorage Overlap

**File**: `_blueprint/features/implementation-phase5-rbac.md`

### 4a. SecretsStorage constructor spec conflicts with existing code (line 92)
Spec says to implement constructor `__init__(client, project)`.
**Reality**: Already implemented in Phase 4b at `src/dockmaster/rbac/storage.py` with `_load_secret`, `_load_secret_raw`, `get_client_secret`.

### 4b. SecretsStorage methods partially done (lines 90-110)
The spec lists these as TODO:
- `_secret_path()` — may already exist
- `_load_secret()` — already exists
- `_save_secret()` — NOT yet implemented (needed for Phase 5)
- `_delete_secret()` — NOT yet implemented (needed for Phase 5)
- `get_role()`, `put_role()`, `delete_role()` — NOT yet implemented
- `get_service_grants()`, `put_service_grants()`, `delete_service_grants()` — NOT yet implemented

The spec should note which methods already exist and only list the remaining work.

### 4c. Settings addition `SECRETS_PROJECT` already exists (line 160)
Listed as a Phase 5 TODO but already in `Settings` (added Phase 4b as `secrets_project`).

### 4d. Lifespan wiring partially done (lines 150-156)
Spec says to create `SecretManagerServiceClient` and `SecretsStorage` singletons. These already exist in `main.py` lifespan (Phase 4b). Phase 5 only needs to add the `Authority` singleton.

---

## 5. implementation-phase6-rbac-management.md — Admin UI and Auth Conflicts

**File**: `_blueprint/features/implementation-phase6-rbac-management.md`

### 5a. Admin UI at `/admin/*` conflicts with existing `/ui/` (implicit)
Phase 6 spec puts CRUD API endpoints at `/admin/*` (line 90) and mentions admin UI. We already have the admin dashboard at `/ui/`. Decision needed:
- Do the CRUD API endpoints live at `/admin/*` (as spec says) or `/auth/admin/*` or somewhere else?
- Does Phase 6 add RBAC management pages to the existing `/ui/` dashboard, or create a separate admin interface?

### 5b. Admin auth (`require_admin`) partially overlaps with `require_ui_session` (line 82-88)
Phase 6 defines a new `require_admin` dependency that checks admin key or admin email.
Phase 4c built `require_ui_session` that checks session cookies.
These need to be reconciled — the admin UI will need both (session auth + admin role check).

### 5c. `DOCKMASTER_ADMIN_EMAILS` design question (line 221)
Spec says admin emails are a Settings list. But once RBAC exists, shouldn't admin status come from the RBAC system itself (e.g., user has "admin" role)? The settings-based approach might be a bootstrap mechanism only.

---

## 6. implementation-phase4c-ui-polish-plan.md — Now Complete, Should Archive

**File**: `_blueprint/features/implementation-phase4c-ui-polish-plan.md`

### 6a. Plan is complete but still in active features directory
Should be moved to archive or marked as complete. Some details are outdated:
- Line 24: Says "Keep `templates/login_test.html`" — we created new templates instead
- Line 35: Mentions "Last refresh result: JWT claims decoded" — we removed the refresh tool
- Line 41: Lists `pyproject.toml` as file to modify — done

---

## 7. polish-plan.md — Duplicate Document

**File**: `_blueprint/roadmap/polish-plan.md`

### 7a. Appears to be a duplicate of `implementation-phase4c-ui-polish-plan.md`
Same content, different location. One should be deleted.

---

## 8. feature-backlog.md — Minor Stale References

**File**: `_blueprint/roadmap/feature-backlog.md`

### 8a. "Admin UI" backlog item (line 72-76)
Says: "Phase 6 originally included a Jinja2+HTMX admin UI. Deferred because the CLI handles 100% of management tasks."
**Reality**: We already built the admin UI in Phase 4c. This backlog item is partially resolved. Should be updated to reflect that the dashboard exists and Phase 6 extends it with RBAC management.

### 8b. "FastHTML + MonsterUI" evaluation item (lines 115-118)
References "Phase 6 ships with Jinja2+HTMX admin UI" — same HTMX reference that's no longer accurate.

### 8c. "InMemorySessionStore Cleanup" item (lines 48-51)
Mentions no periodic cleanup. `list_all()` now does lazy cleanup of expired sessions, which partially addresses this. Should be updated.

---

## 9. MEMORY.md — Stale Implementation Status

**File**: `_blueprint/memory/MEMORY.md`

### 9a. Current implementation status section is outdated (lines 10-14)
Says "Phase 4–6: PLANNED — Next: Phase 4". Reality: Phase 4 (all sub-phases) is complete, 134 tests, next is Phase 5.

---

## 10. GCP SA Key Split — Admin vs Read-Only (Undocumented Decision)

**Files affected**: `_blueprint/context/gcp-dev-setup/GUIDE-setup-service-account-key.md`, Phase 5/6 specs, `decision-log.md`

### 10a. Decision exists in GCP guide but not in specs or decision log
The GCP setup guide (line 134-135) notes:
> "The runtime SA is strictly read-only. Write access to Secret Manager (for managing RBAC roles/grants) will use a separate `dockmaster-admin` SA in Phase 6."

This is a significant architectural decision but it's:
- NOT in `decision-log.md`
- NOT in the Phase 5 or Phase 6 implementation specs
- NOT reflected in the Settings model (no `ADMIN_SA_KEY_FILE` setting)

### 10b. Implications for Phase 5 and 6
- Phase 5 `SecretsStorage` currently only has read methods (`_load_secret`, `get_client_secret`). The read SA is fine here.
- Phase 6 adds write methods (`_save_secret`, `_delete_secret`, `put_role`, `put_service_grants`). These need SM write access (`roles/secretmanager.admin` or `roles/secretmanager.secretVersionAdder`).
- The Phase 6 spec assumes a single SM client but should specify whether the admin routes use a different SA credential for writes.

### 10c. Design question
Two SAs means two credential paths in the app. Options:
- **Two SA key files**: `SA_KEY_FILE` (read) + `ADMIN_SA_KEY_FILE` (write). Admin routes use the admin credential.
- **One SA with both roles**: Simpler but violates least-privilege.
- **ADC with broad permissions**: For dev only.

This needs a decision before Phase 6 implementation.

---

## 11. Admin Authorization — RBAC-Based with Settings Override

### 11a. Current Phase 6 spec uses settings-only admin auth
Phase 6 defines admin access via `DOCKMASTER_ADMIN_KEY` and `DOCKMASTER_ADMIN_EMAILS` in Settings (implementation-phase6-rbac-management.md lines 220-221).

### 11b. Preferred approach: RBAC-first with settings fallback
The preferred design is:
- **Primary**: Admin status comes from the RBAC system itself (e.g., user has an "admin" role for the dockmaster service).
- **Fallback/bootstrap**: `DOCKMASTER_ADMIN_EMAILS` in Settings overrides RBAC for initial setup, dev convenience, and emergency access (bootstrap problem: can't assign admin role via RBAC if you need admin role to access RBAC).
- **API key**: `DOCKMASTER_ADMIN_KEY` stays as a simple shared secret for CLI/automation.

### 11c. Files to update
- `implementation-phase6-rbac-management.md` — Update `require_admin` dependency to check RBAC first, fall back to settings
- `phase6-rbac-management-v2.md` — Update admin auth design section
- `decision-log.md` — Record this decision
- Consider whether this affects Phase 5 (does `Authority.has_permission` need to be available before admin routes exist?)

---

## 12. Duplicate File — Resolved

**File**: `_blueprint/roadmap/polish-plan.md` — **DELETED** (was a duplicate of `_blueprint/features/implementation-phase4c-ui-polish-plan.md`)

---

## Summary: Priority Order for Fixes

1. **ROADMAP.md** — Most impactful; this is the "single source of truth". Fix statuses, links, descriptions.
2. **Phase 5 implementation spec** — Next phase to implement; needs to account for existing SecretsStorage code.
3. **Phase 6 implementation spec** — Admin UI architecture needs reconciliation with existing `/ui/` dashboard. Admin auth needs RBAC-first design. SA key split needs specification.
4. **decision-log.md** — Backfill Phase 4 decisions + SA key split + admin auth approach.
5. **GCP SA key split** — Document the two-SA architecture decision, add `ADMIN_SA_KEY_FILE` consideration to Phase 6.
6. **feature-backlog.md** — Update stale references (HTMX, admin UI, session cleanup).
7. **Phase 4 implementation spec** — Mark complete or archive.
8. **Phase 4c plan** — Archive (complete).
9. **MEMORY.md** — Quick status update.
