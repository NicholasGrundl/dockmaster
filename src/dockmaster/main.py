from fastapi import FastAPI

app = FastAPI()

@app.get("/auth/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "ok",
    }

@app.get("/auth")
async def root()-> dict[str, str]:
    return {
        "service" : "dockmaster",
        "status": "ok"
    }


@app.get("/auth/v1/{username}")
async def greet_user(username: str):
    return {"message": f"Hello {username}"}