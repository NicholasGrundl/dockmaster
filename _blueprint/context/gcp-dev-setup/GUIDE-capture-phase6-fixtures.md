# Guide: Capture Phase 6 Fixtures — Secret Manager List Operations

Captures the `list_secrets` responses used by `list_roles()` and `list_service_grants()`.
These fixtures document the real GCP response shape for the list operations added in Phase 6.

**Prerequisites**:
- `.env` populated with `SECRETS_PROJECT`, `ADMIN_SA_KEY_FILE`
- Admin SA (`dockmaster-admin`) has `roles/secretmanager.admin` on the project
- At least one role secret (`role-*`) and one service grants secret (`service-grants-*`) exist
- Phase 6 E2E verification already passed (sub-task 14)

**Note**: The capture scripts (`scripts/capture_list_roles.py`, `scripts/capture_list_service_grants.py`,
`scripts/verify_list_operations.py`) were removed after fixtures were captured. The commands below
are preserved for reference if fixtures need to be re-captured — recreate the scripts or run the
equivalent commands inline.

---

## Step 1: Dry run — inspect the output

```bash
uv run python scripts/capture_list_roles.py
```

```bash
uv run python scripts/capture_list_service_grants.py
```

Review the JSON. Each should show secrets with full resource paths like
`projects/.../secrets/role-admin`.

---

## Step 2: Save fixtures

```bash
mkdir -p tests/fixtures/gcp/secret_manager
```

```bash
uv run python scripts/capture_list_roles.py > tests/fixtures/gcp/secret_manager/list_roles.json
```

```bash
uv run python scripts/capture_list_service_grants.py > tests/fixtures/gcp/secret_manager/list_service_grants.json
```

---

## Step 3: Verify round-trip

```bash
uv run python scripts/verify_list_operations.py
```

**Expected**: Lists all roles and services, then fetches each one individually. Example:

```
Roles (1): ['admin']
  role/admin: ['admin']
Services (1): ['dockmaster']
  service/dockmaster: 1 grants

All list + get operations verified.
```

---

## Verification Checklist

- [ ] `uv run python scripts/capture_list_roles.py` prints valid JSON (Step 1)
- [ ] `uv run python scripts/capture_list_service_grants.py` prints valid JSON (Step 1)
- [ ] `tests/fixtures/gcp/secret_manager/list_roles.json` saved (Step 2)
- [ ] `tests/fixtures/gcp/secret_manager/list_service_grants.json` saved (Step 2)
- [ ] `uv run python scripts/verify_list_operations.py` passes (Step 3)

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `DefaultCredentialsError` | ADC not set | Scripts set `GOOGLE_APPLICATION_CREDENTIALS` from `.env` automatically |
| `ADMIN_SA_KEY_FILE not set` | Missing from `.env` | Add `ADMIN_SA_KEY_FILE=/path/to/key.json` to `.env` |
| Empty list | No secrets with matching prefix | Create at least one role and one service grant via admin UI or gcloud |
| `PERMISSION_DENIED` | SA lacks list permission | Grant `roles/secretmanager.admin` to admin SA |
| `Reauthentication needed` | Stale ADC cache | Delete `~/.config/gcloud/application_default_credentials.json` and retry |
