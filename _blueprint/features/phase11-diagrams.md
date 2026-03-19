## BReakdown

Good. Let me now build up the full picture of what the auth dependency layer looks like after
these changes, and then map it against all the routes.                                      
                                                                                            
Proposed Auth Dependency Design (post-cleanup)                                               
                                                                                            
Utility functions (pure, no FastAPI):                                                        
                                                                                            
Function: verify_jwt(token, realm)                                                           
Input: token string, realm                                                                   
Output: claims dict                                                                          
Notes: Unchanged                                                                             
────────────────────────────────────────                                                     
Function: resolve_session(handle, store, secret_key)                                         
Input: signed cookie OR refresh_token, store, key                                            
Output: session dict | None                                                                  
Notes: Renamed from cookie param — accepts any signed session handle                         
────────────────────────────────────────                                                   
Function: check_permission(email, service, perm, authority, whitelist)                     
Input: explicit args                                                                       
Output: bool                                                                                 
Notes: Unchanged                                                                          
────────────────────────────────────────                                                     
Function: verify_google_credential(token, realm, issuers, audiences, url)                  
Input: explicit args                                                                         
Output: typed credential                                                                   
Notes: Unchanged                                                                             
                                                                                            
Allow gates (router-level, raise 401/403):                                                 
                                                                                            
┌─────────────────────────┬────────────────────┬─────────────┬──────────────────────────┐    
│          Gate           │    Auth method     │   Failure   │         Used by          │ 
├─────────────────────────┼────────────────────┼─────────────┼──────────────────────────┤    
│ allow_jwt               │ Bearer JWT         │ 401         │ API routes (claims,      │  
│                         │                    │             │ permissions)             │  
├─────────────────────────┼────────────────────┼─────────────┼──────────────────────────┤    
│                         │ Cookie OR          │ 401         │ Session API routes       │    
│ allow_session           │ refresh_token →    │ (changed    │ (/auth/session/*)        │    
│                         │ session            │ from 307)   │                          │    
├─────────────────────────┼────────────────────┼─────────────┼──────────────────────────┤  
│ allow_google_credential │ Google JWT/access  │ 401         │ Service route            │    
│                         │ token              │             │ (/auth/service/token)    │  
├─────────────────────────┼────────────────────┼─────────────┼──────────────────────────┤    
│ allow_jwt_admin         │ Bearer JWT + admin │ 401/403     │ Admin API routes         │  
│                         │  check             │             │ (/admin/*)               │    
└─────────────────────────┴────────────────────┴─────────────┴──────────────────────────┘  
                                                                                            
Removed gates:                                                                               
- allow_jwt_or_session — replaced by separate allow_session (session routes) and allow_jwt 
(CLI route)                                                                                  
- allow_session_admin — replaced by get_admin_session for UI                               
                                                                                            
Info dependencies (per-route, never raise):                                                  
                                                                                            
┌───────────────────┬───────────────────┬────────────────────────────────────────────────┐   
│        Dep        │      Returns      │                    Used by                     │   
├───────────────────┼───────────────────┼────────────────────────────────────────────────┤ 
│ get_jwt_claims    │ claims dict | {}  │ Claims route                                   │ 
├───────────────────┼───────────────────┼────────────────────────────────────────────────┤ 
│ get_google_claims │ typed credential  │ Exchange/service route                         │   
│                   │ | None            │                                                │   
├───────────────────┼───────────────────┼────────────────────────────────────────────────┤   
│ get_session_user  │ session dict | {} │ Updated: cookie OR refresh_token               │   
├───────────────────┼───────────────────┼────────────────────────────────────────────────┤ 
│ get_admin_session │ session dict |    │ New: cookie-only, checks admin. UI routes use  │   
│                   │ None              │ this + redirect pattern                        │ 
└───────────────────┴───────────────────┴────────────────────────────────────────────────┘   
                                                                                            
System checks (unchanged):                                                                 
                                                                                            
┌─────────────────────┬─────────────────────────┐                                            
│         Dep         │         Purpose         │
├─────────────────────┼─────────────────────────┤                                            
│ needs_admin_storage │ 503 if no admin SM      │                                          
├─────────────────────┼─────────────────────────┤                                          
│ needs_session_store │ 503 if no session store │                                            
└─────────────────────┴─────────────────────────┘
                                                                                            
Removed info deps:                                                                           
- get_session_or_jwt_email — was for the old mixed token route. Session routes use         
get_session_user, CLI route uses get_jwt_claims  



## DAG View


                        ┌──────────────────────┐
                        │    app.state.*       │
                        │ (runtime singletons) │
                        └──────────┬───────────┘
                                    │
        ┌─────────────────────────┼─────────────────────────────┐
        │                         │                             │
        ▼                         ▼                             ▼
┌──────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ get_session_store│  │    get_authority     │  │  get_admin_storage   │
│ → SessionStore   │  │    → Authority       │  │  → AdminSecrets      │
└────────┬─────────┘  └─────────┬────────────┘  └──────────────────────┘
        │                      │
        │  ┌───────────────────┤
        │  │                   │
        ▼  ▼                   ▼
┌───────────────────┐  ┌───────────────────────┐
│  resolve_session  │  │  check_permission     │
│                   │  │                       │
│ Args:             │  │ Args:                 │
│  handle: str|None │  │  email: str           │
│  store: SessionSt │  │  service: str         │
│  secret_key: str  │  │  permission: str      │
│                   │  │  authority: Authority  │
│ Returns:          │  │  whitelist: set|None  │
│  dict | None      │  │                       │
└───┬───┬───┬───────┘  │ Returns: bool         │
    │   │   │           └───┬───────────────────┘
    │   │   │               │
    │   │   │               │
    │   │   └───────────────┼──────────────────────┐
    │   │                   │                      │
    ▼   ▼                   ▼                      ▼
┌───────────────┐  ┌──────────────────┐  ┌─────────────────────┐
│ allow_session │  │ get_session_user │  │ get_admin_session   │
│               │  │                  │  │                     │
│ DI inputs:    │  │ DI inputs:       │  │ DI inputs:          │
│  request      │  │  request         │  │  request            │
│  settings     │  │  settings        │  │  settings           │
│  cookie(Cookie│  │  cookie (Cookie) │  │  cookie (Cookie)    │
│  body→refresh │  │  body→refresh    │  │  (NO refresh_token) │                                                       
│               │  │                  │  │                     │                                                       
│ Calls:        │  │ Calls:           │  │ Calls:              │                                                       
│  resolve_ses  │  │  resolve_session │  │  resolve_session    │                                                       
│  (cookie OR   │  │  (cookie OR      │  │  (cookie only)      │                                                     
│   refresh)    │  │   refresh)       │  │  check_permission   │                                                       
│               │  │                  │  │                     │                                                       
│ Returns:      │  │ Returns:         │  │ Returns:            │                                                       
│  dict (raises │  │  dict | {}       │  │  dict | None        │                                                       
│  401 on fail) │  │  (never raises)  │  │  (never raises)     │                                                       
└───────────────┘  └──────────────────┘  └─────────────────────┘                                                       
        │                                                                                                              
        │ (used as router gate)                                                                                        
        ▼                                                                                                              
                                                                                                                        
┌──────────────────┐         ┌─────────────────┐                                                                     
│    verify_jwt    │         │    app.state.*   │                                                                    
│                  │         │                  │                                                                    
│ Args:            │◄────────│  .realm          │                                                                  
│  token: str      │         │  .token_issuer   │                                                                    
│  realm: object   │         └────────┬─────────┘                                                                    
│                  │                  │                                                                              
│ Returns:         │                  │                                                                              
│  dict (claims)   │      ┌───────────┼──────────┐                                                                   
└──┬────┬──────────┘      │           │          │                                                                   
    │    │                 ▼           ▼          ▼                                                                   
    │    │        ┌────────────┐ ┌──────────┐ ┌────────────────┐                                                      
    │    │        │ allow_jwt  │ │get_jwt_  │ │get_token_issuer│                                                      
    │    │        │            │ │claims    │ │→ TokenIssuer   │                                                    
    │    │        │ DI inputs: │ │          │ └────────────────┘                                                      
    │    │        │  request   │ │DI inputs:│                                                                         
    │    │        │  creds(HTTP│ │ request  │                                                                         
    │    │        │   Bearer)  │ │ creds    │                                                                         
    │    │        │            │ │          │                                                                         
    │    │        │ Calls:     │ │Calls:    │                                                                         
    │    │        │  verify_jwt│ │verify_jwt│                                                                         
    │    │        │            │ │          │                                                                       
    │    │        │ Returns:   │ │Returns:  │                                                                         
    │    │        │  dict      │ │dict | {} │                                                                         
    │    │        │ (401 fail) │ │(never    │                                                                         
    │    │        └──┬─────────┘ │raises)   │                                                                         
    │    │           │           └──────────┘                                                                         
    │    │           │                                                                                                
    │    │           ▼                                                                                                
    │    │  ┌─────────────────┐                                                                                       
    │    │  │allow_jwt_admin  │                                                                                       
    │    │  │                 │                                                                                     
    │    │  │ DI inputs:      │                                                                                       
    │    │  │  Depends(       │                                                                                       
    │    │  │   allow_jwt)    │                                                                                       
    │    │  │  settings       │                                                                                       
    │    │  │  request        │                                                                                       
    │    │  │                 │                                                                                       
    │    │  │ Calls:          │                                                                                     
    │    │  │  check_permiss. │                                                                                       
    │    │  │                 │
    │    │  │ Returns: dict   │                                                                                       
    │    │  │ (401/403 fail)  │                                                                                       
    │    │  └─────────────────┘                                                                                       
    │    │                                                                                                            
    │    │                                                                                                            
    ▼    ▼                                                                                                            
┌──────────────────────────────┐                                                                                       
│  verify_google_credential    │                                                                                        
│                              │                                                                                       
│ Args:                        │                                                                                       
│  token: str                  │                                                                                       
│  realm: object | None        │                                                                                     
│  authorized_issuers: set     │                                                                                       
│  authorized_audiences: set   │
│  tokeninfo_url: str          │                                                                                       
│                              │                                                                                       
│ Calls:                       │                                                                                     
│  verify_jwt (JWT path)       │                                                                                       
│  validate_access_token       │                                                                                     
│   (access token fallback)    │                                                                                       
│                              │
│ Returns:                     │                                                                                       
│  GoogleJWTCredential |       │                                                                                       
│  GoogleAccessTokenCredential │                                                                                     
└──────┬───────┬───────────────┘                                                                                       
        │       │                                                                                                     
        ▼       ▼                                                                                                       
┌──────────────────┐  ┌──────────────────┐                                                                           
│allow_google_cred │  │get_google_claims │                                                                             
│                  │  │                  │                                                                             
│ DI inputs:       │  │ DI inputs:       │                                                                           
│  request         │  │  request         │                                                                             
│  settings        │  │  settings        │                                                                           
│  creds (Bearer)  │  │  creds (Bearer)  │                                                                             
│                  │  │                  │                                                                             
│ Calls:           │  │ Calls:           │                                                                           
│  verify_google_  │  │  verify_google_  │                                                                             
│  credential      │  │  credential      │                                                                             
│                  │  │                  │                                                                           
│ Returns:         │  │ Returns:         │                                                                             
│  credential      │  │  credential|None │                                                                           
│  (401 on fail)   │  │  (never raises)  │                                                                             
└──────────────────┘  └──────────────────┘                                                                             
                                                                                                                        
Summary: dependency chains per route                                                                                   
                                                                                                                    
GET  /auth/session/principal                                                                                           
└─ router: allow_session(cookie|refresh → resolve_session → 401)                                                     
└─ route:  get_session_user(cookie|refresh → resolve_session → {})                                                   
                                                                                                                        
POST /auth/session/token                                                                                               
└─ router: allow_session                                                                                           
└─ route:  get_session_user, get_token_issuer                                                                        
                                                                                                                    
GET  /auth/session/list                                                                                                
└─ router: allow_session                                                                                           
└─ route:  get_session_user, get_session_store                                                                     
                                                                                                                        
POST /auth/service/token
└─ router: allow_google_credential(Bearer → verify_google_credential → 401)                                          
└─ route:  get_google_claims, get_token_issuer                                                                       
                                                                                                                    
POST /auth/cli/token                                                                                                   
└─ router: allow_jwt(Bearer → verify_jwt → 401)                                                                    
└─ route:  get_jwt_claims, get_token_issuer                                                                        
                                                                                                                        
GET  /auth/claims
└─ router: allow_jwt                                                                                                 
└─ route:  get_jwt_claims                                                                                          
                                                                                                                    
GET  /auth/has, /auth/has/{s}/{t}/{p}
└─ router: allow_jwt
└─ route:  get_jwt_claims                                                                                            

POST /auth/login/code                                                                                                  
└─ (no gate — public, auth code validated in route)                                                                
                                                                                                                        
POST /auth/logout
└─ (no gate — accepts cookie or refresh_token, best-effort delete)                                                   
                                                                                                                        
GET/POST /ui/*  (admin pages)                                                                                        
└─ (no router gate)                                                                                                  
└─ route:  get_admin_session(cookie → resolve_session → check_permission → dict|None)                                
            if None → return RedirectResponse("/ui/login")                                                            
                                                                                                                        
GET/POST/PUT/DELETE /admin/*                                                                                           
└─ router: allow_jwt_admin(Bearer → verify_jwt → check_permission → 401/403)  



## REdirects and router dependency

Router-level dependency return values:

┌──────────────────────────────────┬───────────────────────────────────────────────┐   
│        What the dep does         │                 What happens                  │   
├──────────────────────────────────┼───────────────────────────────────────────────┤   
│ Returns a value (dict, bool,     │ Silently discarded. The route runs normally.  │ 
│ string, anything)                │ False, None, 0 — all succeed.                 │   
├──────────────────────────────────┼───────────────────────────────────────────────┤   
│                                  │ Short-circuits. Route never runs. FastAPI     │   
│ Raises HTTPException(401)        │ returns JSON: {"detail": "..."} with the      │   
│                                  │ status code.                                  │ 
├──────────────────────────────────┼───────────────────────────────────────────────┤   
│ Raises HTTPException(307,        │ Short-circuits. Returns a redirect response   │ 
│ headers={"Location": ...})       │ (this is the current allow_session hack).     │   
├──────────────────────────────────┼───────────────────────────────────────────────┤ 
│ Raises any other exception       │ 500 Internal Server Error. Route never runs.  │   
└──────────────────────────────────┴───────────────────────────────────────────────┘ 

So specifically:

# This gate does NOTHING useful — False is silently discarded, route runs anyway
async def bad_gate():
    return False

router = APIRouter(dependencies=[Depends(bad_gate)])
# ← all routes in this router will execute normally despite "False"

That's why router-level gates MUST raise an exception to block access. Returning False or None doesn't stop anything. The only mechanism is raise HTTPException(...).

This is also why the allow_* / get_* split exists:
- allow_* gates raise on failure (the only way to block at router level)
- get_* info deps return data (including empty/None) without raising

And it's why the UI pattern we discussed works: get_session_user returns {} on no session (doesn't block), and the route code decides what to do with that empty dict. If it were a router-level dep, returning {} would just let everyone through.  

You mean something like allow_session_or_redirect that raises a 307 instead of 401?    

It works mechanically — FastAPI will honor the 307 HTTPException at router level.
That's what the current allow_session does today.

The problem is it couples auth logic to UI behavior:
- The same session verification logic can't be reused for API routes (which need 401)
- You end up with allow_session (401) AND allow_session_or_redirect (307) — two gates doing the same auth check with different failure modes
- If you add a third failure mode later (e.g., return JSON error for HTMX requests),you need a third gate

The naming makes the intent clear, which is better than the current unnamed 307 hack. But it's still mixing concerns — auth verification shouldn't know about HTTP redirects.

The cleaner separation is what we already landed on:
- Gates answer: "is this request authenticated?" (yes/no via 401)
- Routes answer: "what do I do for an unauthenticated request?" (redirect, error page, etc.)

That said — if you find the per-route if not user: return redirect boilerplate annoying and want a one-liner router-level solution, the redirect gate is a pragmatic shortcut.