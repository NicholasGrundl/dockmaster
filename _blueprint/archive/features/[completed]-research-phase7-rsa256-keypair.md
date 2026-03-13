# Dockmaster Key pair notes and concept

Moving to **in-memory ephemeral keys** and a **JWKS endpoint** is a classic architectural move for high-security standalone services. It solves the "Golden Ticket" problem because even if someone steals your SA key from your server's disk, they only get your GCP credentials—they *cannot* forge user tokens because the signing key only exists in the app's RAM.

Here is how to structure that logic.

---

## 1. The Strategy: "Memory-Only Rotation"

Since you are okay with a restart rotating the keys, your service will:

1. **On Startup:** Generate a new RSA key pair.
2. **The Registry:** Maintain a list of "Active Public Keys" (the new one + any from the previous hour).
3. **The Endpoint:** Serve `/.well-known/jwks.json` containing only the public parts.

### The "Append" Logic

To prevent valid tokens from breaking on every restart, you can persist just the **public** keys to a simple JSON file or database. Since they are public, there is no risk in storing them.

---

## 2. Implementation: Generating JWKs with PyJWT

PyJWT doesn't just do tokens; it has helpers for converting keys to the JWK format that other services expect.

```python
import uuid
import json
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt

class KeyManager:
    def __init__(self):
        self.current_private_key = None
        self.current_kid = None
        self.public_jwks = [] # List of JWK dicts

    def rotate_keys(self):
        # 1. Generate a new 2048-bit RSA key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        kid = str(uuid.uuid4())
        
        # 2. Convert public part to JWK format for your endpoint
        # PyJWT's RSAAlgorithm can help export the dictionary
        public_key = private_key.public_key()
        jwk_dict = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
        jwk_dict.update({"kid": kid, "use": "sig", "alg": "RS256"})

        # 3. Update state
        self.current_private_key = private_key
        self.current_kid = kid
        # Keep the last 3 keys to handle overlap
        self.public_jwks.insert(0, jwk_dict)
        self.public_jwks = self.public_jwks[:3]

    def get_jwks(self):
        return {"keys": self.public_jwks}

# Initialize on startup
km = KeyManager()
km.rotate_keys()

```

---

## 3. Serving the JWKS Endpoint

In your Auth service (Flask, FastAPI, etc.), you just need one route:

```python
@app.route('/.well-known/jwks.json')
def jwks():
    return jsonify(km.get_jwks())

```

### How other services use this:

Your other microservices no longer need Google SA keys or Secret Manager access. They just need the URL to this endpoint. Most JWT libraries (including PyJWT) can be configured to "Phone Home" to this URL to fetch the keys.

---

## 4. Why this is strictly better than your current setup

1. **Isolation:** If your server is hacked, the attacker gets the **Public Keys** (already public) and an **Ephemeral Private Key** (which disappears when you kill the process).
2. **Least Privilege:** Your other microservices now have **Zero** access to GCP. They only have "Read" access to your auth service's public keys.
3. **No Environment Variable Risk:** Environment variables are often logged or visible in process managers (`ps aux`). Keeping the private key strictly as a Python object in RAM is the "gold standard."

---

## One small "Gotcha"

If you restart the service, the **Private Key** is gone forever. If a user has a token that expires in 1 hour, and you restart at minute 10, their token is now "unverifiable" because the matching private key is lost.


That is a very common point of confusion, but the short answer is: **No, you cannot verify a token with only the public key if the private key that signed it is gone.**

Here is the breakdown of why the "persisted public key" isn't enough to save a session after a restart.

---

## 1. The Math: Signing vs. Verifying

Think of a JWT signature as a **mathematical lock**.

* **The Private Key** is the physical key that *closes* the lock (creates the signature).
* **The Public Key** is the tool used to *check* if the lock was closed by that specific private key.

If you restart your service and generate a **new** private key, any token signed by the **old** private key is effectively locked with a key that no longer exists in the universe. Even though you still have the "checking tool" (the old public key) persisted in your JWKS, that tool will only tell you: *"Yes, this was signed by the old private key."*

**The Problem:** The "old private key" is dead. If you didn't persist the private key, you can never "re-sign" or "refresh" that session.

---

## 2. Why persisting the Public Key is still useful

Even though the private key is gone, persisting the public key in your JWKS for a short "grace period" is actually a **great idea**.

* **Scenario:** Your Auth Service restarts. A user sends a JWT to your *Billing Service*.
* **Verification:** The Billing Service fetches your `jwks.json`. It sees the "old" public key is still there. It verifies the signature and says, *"This is a valid token issued by the Auth Service 5 minutes ago."*
* **Result:** The user is **authenticated**! The session stays alive even though the Auth Service "forgot" the private key.

**The "Catch":** The moment that token expires, the user comes back to the Auth Service to get a new one. Since the Auth Service only has a **new** private key now, it issues a token with a **new `kid**`. Your JWKS will now need to show both the old and the new public keys so other services don't break.

---

## 3. The "Lost Private Key" Trap

The only time the "Lost Private Key" actually breaks things is if your service needs to **interact** with the token itself in a way that requires signing (like refreshing a token or modifying its claims).

| If you... | Then... |
| --- | --- |
| **Only Verify** (Other Services) | Persisted Public Keys work perfectly! |
| **Issue/Refresh** (Auth Service) | You **must** have the Private Key. You'll have to issue a brand new token with the new key. |

---

## Summary of your Plan

Your idea of **appending to the JWKS file** is the correct "High Availability" move. It allows your entire microservice ecosystem to keep trusting "old" tokens until they naturally expire, even if the Auth Service has moved on to a new key.

### A Quick Logic Check

When you restart:

1. **Generate** `Private_Key_B`.
2. **Keep** `Public_Key_A` (from before the restart) in your `jwks.json`.
3. **Add** `Public_Key_B` to `jwks.json`.
4. **Wait** until all tokens signed by `Private_Key_A` have expired (e.g., 1 hour).
5. **Cleanup:** Remove `Public_Key_A` from the JWKS.






# Design Checklist

To hand this off to a developer, you need to define the **Stateful JWKS Pattern**. This approach moves the "Source of Truth" for security from a static GCP Service Account file to an ephemeral, memory-resident key system backed by a public discovery endpoint.

Here is the architectural summary for the dev hand-off:

---

## **Project: Ephemeral RS256 Auth & JWKS Discovery**

### **1. Objective**

Decouple the Application Signing Identity from the Infrastructure (GCP) Identity. The service will sign JWTs using ephemeral RSA keys generated at runtime, while other services verify these tokens via a standard JWKS (JSON Web Key Set) endpoint.

### **2. Core Components**

#### **A. Ephemeral Key Manager**

* **Startup:** On boot, the service generates a new **2048-bit RSA Private/Public key pair**.
* **Identification:** Generate a unique `kid` (Key ID) for each pair.
* **In-Memory Signing:** The Private Key resides **only in RAM**. It is never written to disk or environment variables.
* **Rotation:** On service restart (deployment/crash), a new key is generated.

#### **B. The Persistent Public Registry**

* **Storage:** A simple, local persistent store (JSON file or lightweight DB) that tracks **Public Keys only**.
* **Retention:** When a new key is generated, it is appended to the registry. Keys older than the maximum JWT TTL (e.g., 24 hours) are purged.
* **Why:** This allows "Old" tokens to remain valid across service restarts until they naturally expire.

#### **C. JWKS Endpoint (`/.well-known/jwks.json`)**

* **Format:** Standardized JSON according to [RFC 7517](https://datatracker.ietf.org/doc/html/rfc7517).
* **Output:** Serves the list of all currently valid Public Keys from the Registry.
* **Security:** This is a public endpoint. No authentication is required to read it.

---

### **3. Implementation Requirements**

* **Signing Logic:**
* Use `pyJWT` for the `encode()` process.
* **Must** include the `kid` in the JWT header so verifiers know which key to pull from the JWKS.


* **Verification Logic (for other services):**
* Services fetch the JWKS from the Auth Service.
* Libraries like `pyJWT` or `auth0-python` should be configured to cache these public keys to avoid hitting the Auth Service on every request.


* **GCP SA Role:**
* The Service Account (SA) JSON key stays on disk but is **only** used for administrative tasks (reading Secret Manager/IAM for RBAC data).
* It is **never** used to sign user-facing JWTs.



---

### **4. Security Benefits**

1. **Blast Radius Reduction:** If the GCP SA key is leaked, an attacker cannot forge user JWTs because the signing key isn't in GCP.
2. **Zero-Persistence Signing:** If the server is seized or the disk is imaged, the active Private Key is lost immediately (it was only in RAM).
3. **Infrastructure Independence:** Microservices no longer need Google credentials to verify internal tokens; they only need network access to the Auth Service's JWKS endpoint.

---

### **5. Success Criteria**

* Auth Service can restart without logging out currently active users.
* Verification services can successfully decode tokens using only the `jwks.json` endpoint.
* No Private Keys are stored in the application logs or environment variables.


### **Sample JWKS Response Format**

This is the standard JSON structure your `/.well-known/jwks.json` endpoint must return. Verifying libraries expect this exact schema to locate the correct public key using the `kid`.

```json
{
  "keys": [
    {
      "kty": "RSA",
      "alg": "RS256",
      "use": "sig",
      "kid": "v2-2026-03-13-rotate",
      "n": "vX-S1... (Base64URL encoded modulus)",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "alg": "RS256",
      "use": "sig",
      "kid": "v1-2026-03-12-expired",
      "n": "m9_A2... (Base64URL encoded modulus)",
      "e": "AQAB"
    }
  ]
}

```

**Key Definitions for the Dev:**

* **`kty`**: Key Type (always `RSA`).
* **`use`**: Intended use (always `sig` for signature).
* **`kid`**: Unique identifier matching the `kid` in the JWT header.
* **`n`**: The public modulus.
* **`e`**: The public exponent (usually `AQAB` for `65537`).
