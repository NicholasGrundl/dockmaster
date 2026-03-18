# Dockmaster Admin Panel UI

The dockmaster service includes a lightweight web-based admin panel for managing RBAC roles and grants. It was built with jQuery 3.6 + UIKit 3.x and served from the `/console/` route. **It is a skeleton** -- the authentication framework works, the layout is complete, but the actual RBAC management UI was never implemented.

## Current State

```mermaid
graph TD
    Browser["Browser at /console/"] --> HTML["index.html"]
    HTML --> AppJS["app.js (App class)"]
    HTML --> UIKit["UIKit 3.x + jQuery 3.6"]
    HTML --> CSS["site.css (from another project)"]

    AppJS --> CheckAuth["checkAuth()"]
    CheckAuth --> Principal["/console/auth/principal"]
    Principal --> |"200 + email"| LoggedIn["Show user name + Logout"]
    Principal --> |"no email"| NotLoggedIn["Show 'Please login.'"]

    AppJS --> RolesTab["Roles Tab Click"]
    RolesTab --> Empty1["(empty handler -- NOT IMPLEMENTED)"]

    AppJS --> GrantsTab["Grants Tab Click"]
    GrantsTab --> Empty2["(empty handler -- NOT IMPLEMENTED)"]

    AppJS --> Relogin["relogin()"]
    Relogin --> Modal["UIKit modal: 'Session expired'"]
    Modal --> |"Accept"| Login["/console/login"]

    style Empty1 fill:#f66,color:#fff
    style Empty2 fill:#f66,color:#fff
    style CSS fill:#fa0,color:#fff
```

### What Works

| Feature | Status | Details |
|---------|--------|---------|
| Page layout | Done | Navbar with login/logout, two-tab switcher (Roles, Grants) |
| Auth check | Done | `checkAuth()` fetches `/auth/principal`, shows user name or "Please login" |
| Login/Logout | Done | Redirects to `/console/auth/login` and `/console/auth/logout` |
| Session expiry | Done | Detects 401 responses, shows modal offering re-login |
| UIKit framework | Loaded | CSS, JS, and icon library all present |

### What's Missing

| Feature | Status | Details |
|---------|--------|---------|
| Role listing | Not started | No API call, no table rendering |
| Role CRUD | Not started | No create/edit/delete forms or handlers |
| Grant listing | Not started | No API call, no table rendering |
| Grant CRUD | Not started | No create/edit/delete forms or handlers |
| Backend CRUD endpoints | Not started | `service.py` only has `/has` for permission checks, no role/grant management endpoints |
| Console routes | Commented out | Lines 382-389 in `service.py`: `/console/` and `/console/assets/` routes are commented out |
| CSS styles | Wrong project | `site.css` contains styles for `.biolector-card`, `table.experiments`, `table.tasks` -- copied from a lab equipment monitoring project |

## File Inventory

```
service/dockmaster_service/
  templates/
    index.html          # 41 lines -- navbar + 2 empty tab panels
  assets/
    js/
      app.js            # 99 lines -- App class: auth works, CRUD empty
      jquery-3.6.0.min.js   # vendored
      uikit.min.js          # vendored (UIKit 3.x)
      uikit.js              # vendored (unminified)
      uikit-icons.min.js    # vendored
      uikit-icons.js        # vendored (unminified)
    css/
      site.css          # 80 lines -- styles from biolector/experiments project
      uikit.min.css         # vendored
      uikit.css             # vendored (unminified)
      uikit-rtl.min.css     # vendored (RTL variant)
      uikit-rtl.css         # vendored (unminified RTL)
```

## How the Auth Flow Works (the part that IS implemented)

```mermaid
sequenceDiagram
    participant B as Browser
    participant C as /console/
    participant A as /console/auth/*

    B->>C: GET /console/
    C->>B: index.html (loads app.js)
    B->>A: fetch('/console/auth/principal')
    alt Has valid session
        A-->>B: {email, name, picture, ...}
        B->>B: Show "Dr. Sarah Chen - Logout"
    else No session
        A-->>B: {}
        B->>B: Show "Please login." in both tabs
    end

    Note over B: User clicks Login
    B->>A: GET /console/auth/login
    A->>B: Redirect to Google OAuth
    B->>B: Google login flow
    B->>A: GET /console/auth/authenticated?code=...&state=...
    A->>A: Exchange code for token, store in Redis session
    A->>B: Redirect back to /console/

    Note over B: On 401 from any API call
    B->>B: relogin() shows UIKit modal
    B->>B: "Session expired. Log in again?"
    B->>A: GET /console/login (on accept)
```

## What Was Planned

Based on the tab structure, data attributes, and response filters in `app.js`, the intended design was:

```mermaid
sequenceDiagram
    participant Admin as Admin User
    participant UI as Admin Panel
    participant API as Dockmaster API
    participant SM as GCP Secret Manager

    Note over Admin,SM: Roles Management
    Admin->>UI: Click "Roles" tab
    UI->>API: GET /roles (list all)
    API->>SM: List secrets matching role-*
    SM-->>API: [role-lab-technician, role-principal-investigator, ...]
    API-->>UI: [{name, permissions}, ...]
    UI->>Admin: Render roles table (paginated, limit=30)

    Admin->>UI: Click "Create Role"
    UI->>Admin: Show form (name, permissions)
    Admin->>UI: Submit
    UI->>API: POST /roles {name: "instrument-operator", permissions: ["instrument:calibrate"]}
    API->>SM: Create secret role-instrument-operator
    SM-->>API: OK
    API-->>UI: 201 Created

    Note over Admin,SM: Grants Management
    Admin->>UI: Click "Grants" tab
    UI->>API: GET /grants (list all services)
    API->>SM: List secrets matching service-grants-*
    SM-->>API: [service-grants-lims, service-grants-dashboard, ...]
    API-->>UI: [{service, grants: [{subject, roles}]}, ...]
    UI->>Admin: Render grants table

    Admin->>UI: Click "Grant Role"
    UI->>Admin: Show form (service, subject email, roles)
    Admin->>UI: Submit
    UI->>API: POST /grants/lims {subject: "sarah.chen@shipyard.com", roles: ["principal-investigator"]}
    API->>SM: Update secret service-grants-lims
```

### Missing Backend Endpoints

None of these exist in `service.py` -- they would need to be created:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/roles` | GET | List all roles |
| `/roles/{name}` | GET | Get a specific role |
| `/roles/{name}` | POST | Create a role |
| `/roles/{name}` | PUT | Update a role's permissions |
| `/roles/{name}` | DELETE | Delete a role |
| `/grants` | GET | List all service grants |
| `/grants/{service}` | GET | Get grants for a service |
| `/grants/{service}` | POST | Add/update grants for a service |
| `/grants/{service}/{subject}` | DELETE | Revoke a subject's grants |

The underlying storage logic already exists in `rbac.py` (`SecretsStorage.load`, `.save`, `.delete`) and the CLI (`__main__.py`) already does CRUD via these classes. The backend endpoints would just expose the same operations over HTTP.

## Reimplementation Options

```mermaid
flowchart TD
    RBAC["RBAC Management"] --> A["Option A: CLI Only"]
    RBAC --> B["Option B: Admin Route in Astro Site"]
    RBAC --> C["Option C: FastAPI Admin Endpoints + Any Frontend"]

    A --> A1["Already works today via python -m dockmaster"]
    A --> A2["Good for: small team, infrequent changes"]

    B --> B1["Protected /admin route in your Astro site"]
    B --> B2["Calls dockmaster API for CRUD"]
    B --> B3["Good for: integrated experience, SSR auth"]

    C --> C1["Add CRUD endpoints to dockmaster service"]
    C --> C2["Any frontend can consume them"]
    C --> C3["Good for: flexibility, API-first"]

    A1 --> CLI["CLI Commands"]
    CLI --> CLI1["python -m dockmaster role create lab-technician sample:create sample:read"]
    CLI --> CLI2["python -m dockmaster service grant lims 'sarah@co.com:lab-technician'"]
    CLI --> CLI3["python -m dockmaster test sarah@co.com lims sample:create"]
```

### Recommendation

For a reimplementation, **Option C** (FastAPI CRUD endpoints) is the foundation regardless of frontend choice. The existing `rbac.py` classes (`Role`, `Grant`, `ServiceGrants`, `Authority`, `SecretsStorage`) and CLI logic in `__main__.py` provide the complete storage layer -- the FastAPI endpoints are thin wrappers around these.

If you build a UI, it can live as a protected route in your Astro site (Option B) that calls these API endpoints. The CLI remains useful for scripting and CI/CD.
