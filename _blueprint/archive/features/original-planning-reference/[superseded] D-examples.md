# Appendix D: Example Scripts Walkthrough

This appendix documents each example script in the `examples/` directory, explaining what it does, its dependencies, and how it relates to the dockmaster system.

---

## 1. `get_token_dockmaster.py` -- Generate JWT via dockmaster library

**Source:** `examples/get_token_dockmaster.py`
**Dependencies:** `click`, `dockmaster`

### Purpose

Generates a signed JWT using the dockmaster `ServiceUser` class. This is functionally identical to `python -m dockmaster token <keyfile>`.

### Usage

```bash
# Using --keyfile
python examples/get_token_dockmaster.py --keyfile /path/to/key.json

# Using ISSUER env var
export ISSUER=/path/to/key.json
python examples/get_token_dockmaster.py

# With custom subject and audience
python examples/get_token_dockmaster.py --subject user@example.com --service https://my-api.example.com/
```

### Options

| Option | Default | Description |
|---|---|---|
| `--keyfile` | `$ISSUER` env var | Path to GCP service account JSON key file |
| `--subject` | None (defaults to service account email) | JWT `sub` and `email` claim |
| `--service` | None (no `aud` claim) | JWT `aud` claim |

### Flow

1. Reads the key file via `ServiceUser(keyfile)`
2. Calls `user.get_token(subject=subject, service_name=service)`
3. Decodes the bytes to UTF-8 and prints to stdout

### Notes

- The `token.decode('utf-8')` call assumes `get_token()` returns bytes. With newer versions of `google-auth`, `jwt.encode()` may return a string directly, which would cause an `AttributeError`.

---

## 2. `get_token_google.py` -- Interactive Google SSO Login

**Source:** `examples/get_token_google.py`
**Dependencies:** `click`, `requests`, `google-auth`, `google-auth-oauthlib`

### Purpose

Performs an interactive Google OAuth2 login flow using a local browser, then outputs the resulting tokens (refresh token, ID token, access token). This is useful for obtaining a refresh token that can later be used with the dockmaster `/refresh` endpoint.

### Usage

```bash
# Default: uses client.json in current directory
python examples/get_token_google.py

# Custom client config
python examples/get_token_google.py --client /path/to/client.json

# With specific audience
python examples/get_token_google.py --service https://my-api.example.com/
```

### Options

| Option | Default | Description |
|---|---|---|
| `--client` | `client.json` | Path to Google OAuth2 client configuration JSON |
| `--service` | `http://dockmaster.service.example.net/` | Not used in the flow (appears to be vestigial) |
| `--scope` | email, profile, openid | OAuth2 scopes to request |
| `--log-level` | `$LOG_LEVEL` env var | Python logging level |

### Flow

1. Loads client config from JSON file (Google OAuth2 "installed" application format)
2. Runs `InstalledAppFlow.run_local_server()` -- opens browser for Google login
3. After authentication, fetches user profile from Google's userinfo endpoint
4. Decodes and prints the ID token claims
5. Outputs `REFRESH_TOKEN`, `ID_TOKEN`, and `ACCESS_TOKEN` to stdout

### Known Bug

Line 54: `refresh_token = app.oauth2session.token['access_token']` -- This assigns the **access token** to `refresh_token` instead of reading `app.oauth2session.token['refresh_token']`. The output `REFRESH_TOKEN=...` will actually contain the access token.

### Client Config Format

The `client.json` file must be a Google OAuth2 client configuration with the `installed` key:

```json
{
  "installed": {
    "client_id": "...",
    "client_secret": "...",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "redirect_uris": ["http://localhost"]
  }
}
```

---

## 3. `get_token_jwt.py` -- Generate JWT via PyJWT

**Source:** `examples/get_token_jwt.py`
**Dependencies:** `click`, `PyJWT` (`jwt`)

### Purpose

Generates a signed JWT using the PyJWT library directly (not the dockmaster library or `google-auth`). This demonstrates JWT creation without any dockmaster or Google dependencies.

### Usage

```bash
# From a key file
python examples/get_token_jwt.py --keyfile /path/to/key.json

# From individual components
python examples/get_token_jwt.py --private-key /path/to/key.pem --kid abc123 --issuer me@example.com

# With custom subject and audience
python examples/get_token_jwt.py --keyfile key.json --subject user@example.com --service https://api.example.com/
```

### Options

| Option | Default | Description |
|---|---|---|
| `--keyfile` | `$ISSUER` env var | GCP service account JSON key file (extracts kid, private_key, issuer) |
| `--private-key` | None | Path to PEM private key file (alternative to --keyfile) |
| `--kid` | None | Key ID for JWT header (required with --private-key) |
| `--issuer` | None | JWT `iss` claim (required with --private-key) |
| `--subject` | Issuer email | JWT `sub` and `email` claims |
| `--service` | None | JWT `aud` claim |

### Flow

1. If `--keyfile` is provided: extracts `private_key_id`, `private_key`, and `client_email` from the JSON
2. If `--private-key` is provided: reads the PEM file, requires `--kid` and `--issuer`
3. Constructs payload with `iat`, `exp` (3600s), `iss`, `email`, `sub`, and optionally `aud`
4. Signs with `jwt.encode(payload, private_key, algorithm='RS256', headers={'kid': kid})`
5. Prints the JWT to stdout

### Notes

- Uses `datetime.utcnow()` (deprecated in Python 3.12+) for timestamp generation
- This is the only example that uses PyJWT instead of `google-auth` for signing
- The generated JWT is compatible with dockmaster's verification (same RS256 + kid header format)

---

## 4. `google_refresh.py` -- Refresh Google Access Token

**Source:** `examples/google_refresh.py`
**Dependencies:** `click`, `requests`

### Purpose

Refreshes a Google access token using a refresh token, calling Google's token endpoint directly (not via dockmaster). Useful for testing whether a refresh token is still valid.

### Usage

```bash
# Using environment variables
export CLIENT_ID=...
export CLIENT_SECRET=...
export ACCESS_TOKEN=...
export REFRESH_TOKEN=...
python examples/google_refresh.py

# Using direct values
python examples/google_refresh.py \
  --client-id "109370504310-xxx.apps.googleusercontent.com" \
  --client-secret "GOCSPX-xxx" \
  --access-token "ya29.xxx" \
  --refresh-token "1//0xxx"

# Force refresh even if current token is valid
python examples/google_refresh.py --force
```

### Options

| Option | Default | Description |
|---|---|---|
| `--client-id` | `env:CLIENT_ID` | Google OAuth2 client ID |
| `--client-secret` | `env:CLIENT_SECRET` | Google OAuth2 client secret |
| `--access-token` | `env:ACCESS_TOKEN` | Current access token (checked for validity) |
| `--refresh-token` | `env:REFRESH_TOKEN` | Google refresh token |
| `--force` | False | Skip validity check, always refresh |

### Environment Variable Indirection

All options default to `env:VAR_NAME` format. The script resolves these by reading from environment:

```python
if client_id.startswith('env:'):
    client_id = os.environ.get(client_id[4:])
```

This allows storing sensitive values in environment variables rather than command-line arguments (which are visible in process listings).

### Flow

1. Resolves all option values from environment if using `env:` prefix
2. Validates that no values are empty
3. Checks if the current access token is still valid via Google's tokeninfo endpoint
4. If valid and `--force` not set: exits with "Token is still valid"
5. If invalid or forced: calls Google's token endpoint with the refresh token
6. Prints the refreshed token response JSON

### Notes

- Uses `requests.post(url, params=...)` for the refresh call, sending parameters as query string instead of form body. This matches the same pattern (and potential issue) as the dockmaster service's `/refresh` endpoint.
- The tokeninfo check uses a GET request with `params={'access_token': ...}`.

---

## 5. `authentication.ipynb` -- Jupyter Notebook Tutorial

**Source:** `examples/authentication.ipynb`
**Dependencies:** `requests`, `IPython`

### Purpose

An interactive Jupyter notebook that demonstrates the end-to-end authentication workflow: obtaining a JWT via the `/refresh` endpoint, inspecting claims via `/claims`, and using the JWT to access a downstream service.

### Prerequisites

The `GOOGLE_REFRESH_TOKEN` environment variable must be set with a valid Google refresh token (obtained via `get_token_google.py` or another OAuth2 flow).

### Cell-by-Cell Walkthrough

#### Cell 1: Helper Functions

Defines three utility functions:

**`decode_jwt(token)`** -- Decodes and prints each segment (header, payload, signature) of a JWT for inspection.

**`issue_jwt(service=None)`** -- Calls dockmaster's `/refresh` endpoint:
```python
url = 'https://dockmaster.service.example.net/refresh'
data = {'token': refresh_token}
if service is not None:
    data['service'] = service
response = requests.post(url, json=data)
```
Returns the signed JWT string from the response.

**`get_claims(token)`** -- Calls dockmaster's `/claims` endpoint:
```python
url = 'https://dockmaster.service.example.net/claims'
response = requests.get(url, headers={'Authorization': f'Bearer {token}'})
```
Returns the decoded claims dictionary.

#### Cell 2: Markdown -- "Establish authentication"

Explains the authentication flow:
1. Use a Google refresh token to call `/refresh`
2. The service refreshes the Google token, verifies it, and issues a dockmaster JWT
3. The JWT can then be used to access other services

#### Cell 3: Issue a JWT

```python
auth_token = issue_jwt(service='https://myservice.service.example.net/')
```

Obtains a JWT with the audience set to the "myservice" service.

#### Cell 4: Inspect Claims

```python
JSON(get_claims(auth_token))
```

Displays the JWT claims as formatted JSON in the notebook.

#### Cell 5: Markdown -- "Using authentication"

Explains that the JWT can be used as a Bearer token to access any service.

#### Cell 6: Use JWT to Access a Service

```python
headers = {'Authorization': f'Bearer {auth_token}'}
response = requests.get('http://myservice.service.example.net/', headers=headers)
```

Demonstrates using the dockmaster JWT to authenticate against a downstream service ("myservice").

### Notes

- The notebook targets the production service URL (`dockmaster.service.example.net`)
- The downstream service (`myservice.service.example.net`) is an example of a service-to-service authentication pattern using dockmaster JWTs
- No `client_id` is passed in the `/refresh` call, so it uses the service's `DEFAULT_CLIENT_ID`
- The notebook uses `http://` (not `https://`) for the myservice service call, which may be intentional (cluster-internal) or an oversight

---

## Summary: Which Example to Use When

| Goal | Script |
|---|---|
| Generate a JWT for testing (have a key file) | `get_token_dockmaster.py` or `get_token_jwt.py` |
| Obtain a Google refresh token interactively | `get_token_google.py` |
| Test if a refresh token works against Google directly | `google_refresh.py` |
| Full end-to-end demo with dockmaster service | `authentication.ipynb` |
| Generate a JWT without dockmaster library dependency | `get_token_jwt.py` |
