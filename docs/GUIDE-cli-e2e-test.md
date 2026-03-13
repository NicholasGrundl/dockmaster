# CLI E2E Test Guide — Phase 6c

Manual end-to-end test script for the `dockmaster` CLI.

---

## 0. Start the server

Make sure your `.env` file is populated with OAuth credentials (`CLIENT_ID`, `CLIENT_SECRET`, etc.)
and service account keys (`SA_KEY_FILE`, `ADMIN_SA_KEY_FILE`).

```bash
# From the project root
uv run uvicorn dockmaster.main:app --reload
```

Verify it's running:

```bash
curl http://localhost:8000/auth/health
```

You should see `{"status": "ok", ...}`. Leave this terminal open and run the CLI commands in a separate terminal.

If you need to point the CLI at a different server URL:

```bash
export DOCKMASTER_URL=http://localhost:8000
```

(Defaults to `http://localhost:8000` if not set.)

---

## 1. Login flow

```bash
dockmaster login
```

- Browser should open to Google OAuth
- After authenticating, terminal should print "Login successful!"
- Verify token was stored:

```bash
cat "$(python3 -c "import platformdirs; print(platformdirs.user_data_dir('dockmaster'))")/credentials.json"
```

---

## 2. Role commands

```bash
# List existing roles
dockmaster role list

# Create a test role
dockmaster role create test-role -p read -p write

# Get it back
dockmaster role get test-role

# Add a permission
dockmaster role add test-role -p delete

# Verify it was added
dockmaster role get test-role

# Remove a permission
dockmaster role remove test-role -p delete

# Verify it was removed
dockmaster role get test-role

# Delete the role
dockmaster role delete test-role

# Verify it's gone (should error 404)
dockmaster role get test-role
```

---

## 3. Grant commands

```bash
# List all services with grants
dockmaster grant list

# Get grants for an existing service (e.g. dockmaster)
dockmaster grant get dockmaster

# Add a grant to a test service
dockmaster grant add test-svc user@example.com -r viewer -r editor

# Get it back
dockmaster grant get test-svc

# Add another subject
dockmaster grant add test-svc other@example.com -r viewer

# Verify both subjects are there
dockmaster grant get test-svc

# Remove a specific role from a subject
dockmaster grant remove test-svc user@example.com -r editor

# Verify only viewer remains
dockmaster grant get test-svc

# Remove all roles for a subject (no -r flag)
dockmaster grant remove test-svc other@example.com

# Delete the test service entirely
dockmaster grant delete test-svc

# Verify it's gone (should error 404)
dockmaster grant get test-svc
```

---

## 4. Check command

```bash
# Test with your own email against dockmaster/admin (should be Oui!)
dockmaster check YOUR_EMAIL@example.com dockmaster -p admin

# Test with a fake email (should be Non!, exit code 1)
dockmaster check nobody@example.com dockmaster -p admin
```

---

## 5. Logout

```bash
dockmaster logout

# Verify token is gone — any command should fail
dockmaster role list
# Expected: "Not logged in. Run `dockmaster login` first."
```

---

## 6. Token expiry (optional, if you want to wait 15 min)

```bash
dockmaster login
# Wait 15 minutes...
dockmaster role list
# Expected: "Not logged in. Run `dockmaster login` first."
```
