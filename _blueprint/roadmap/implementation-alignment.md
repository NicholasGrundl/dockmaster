# Implementation Alignment Report

*Generated: 2026-03-16*
*Last updated: 2026-03-13 (alignment session)*
*Purpose: Identify inconsistencies between blueprint docs and actual implementation state.*

---

## ToDo Items

1. Tests are messy or could be more streamlined with the setting and app factory pattern
- identify all the uses of a app with specific settings that are used for the tests
- each group of app + settings will get a fixture that makes its settings
- each group will construct an app/test client using our factory fixturer

2. consider implementing the hybrid Depends(settings) <pattern>


<pattern>
To satisfy both your need for **test isolation** (avoiding that sticky `lru_cache` state) and your colleague's preference for **idiomatic injection**, the "State-Bound Dependency" is the gold standard.

This pattern treats `app.state` as the "Source of Truth" and the `Depends` callable as the "Public API" for your routes.

### The Hybrid Pattern Implementation

Here is how you structure the application to ensure that settings are strictly tied to the specific app instance being tested.

```python
from fastapi import FastAPI, Depends, Request
from pydantic_settings import BaseSettings
from typing import Annotated

# 1. Define your Settings
class Settings(BaseSettings):
    app_name: str = "Awesome API"
    admin_email: str
    items_per_user: int = 50

# 2. The "Bridge" Dependency
# This replaces the lru_cache version. It pulls from the request's app instance.
def get_settings(request: Request) -> Settings:
    return request.app.state.settings

# 3. Create a Type Alias for cleaner route signatures
SettingsDep = Annotated[Settings, Depends(get_settings)]

# 4. App Factory (Crucial for your testing style)
def create_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    
    @app.get("/info")
    async def get_info(settings: SettingsDep):
        return {"name": settings.app_name, "email": settings.admin_email}
        
    return app
```

---

### Why this solves your conflict

#### 1. Zero Cache Poisoning (Your Win)
Because `get_settings` looks at `request.app.state`, it is physically impossible for a test using **App A** to accidentally receive settings from **App B**. There is no global `@lru_cache` function holding onto old variables.

#### 2. Idiomatic Route Signatures (Colleague's Win)
Your colleague gets to use `Depends(get_settings)`. This means:
* The routes remain **Type Hinted** (autocomplete works perfectly).
* The routes are **Explicit** (you see `SettingsDep` in the parameters).
* OpenAPI (Swagger) still recognizes the dependency structure.

#### 3. No `dependency_overrides` Needed
Since you are using an **App Factory**, you don't even need to use FastAPI's override system. You simply bake the "mock" or "test" settings into the `app.state` when you initialize the app for your test suite.

---

### How to use it in your tests
Since you mentioned creating different app constructions for different modules, this fits perfectly into your workflow:

```python
def test_production_config():
    prod_settings = Settings(admin_email="prod@company.com", app_name="PROD")
    app = create_app(prod_settings)
    # ... test logic ...

def test_staging_config():
    stage_settings = Settings(admin_email="dev@company.com", app_name="STAGING")
    app = create_app(stage_settings)
    # This app will have its own unique settings in state
    # get_settings will pull the RIGHT ones every time.
```
</pattern>

