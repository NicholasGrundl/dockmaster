# Goals

This package is for developing an authorization microservice that uses:
- Google SSO for authentication
- GCloud secrets for holding the RBAC database
- JWT tokens for passing bearer tokens around to various other services

The motivation is varied but primary focus is on:
- refreshing my flask skills
- updating my knowledge of modern OAuth 2.0 and JWT web tokens
- creating a service i can use for a personal cluster gateway to expose my code to outside users with a Gmail

# Flask Development

## Configure Environment vars

See https://flask.palletsprojects.com/en/1.1.x/cli/

```
export FLASK_APP=src/dockmaster/app
export FLASK_DEBUG=1
export FLASK_ENV=development
export FLASK_RUN_HOST=127.0.0.1
export FLASK_RUN_PORT=5000
```

We need a client secret key for the exchange
```
export CLIENT_SECRET_KEY=.....
```

## Configuration for env vars

see conda setup to persist them during development

https://stackoverflow.com/a/62508395


## TODO Env vars

set up a configuration class 

class Config:
   APP_ROOT = '/'
   AUTH_PREFIX = '/auth'
   NOAUTH = []
   NOAUTH_PREFIXES = []
   AUTH_PROVIDER = 'https://accounts.google.com/o/oauth2/auth'
   TOKEN_PROVIDER = 'https://oauth2.googleapis.com/token'
   CLIENT_ID = ...
   REDIRECT_URI = '/auth/authenticated'
   SESSION_KEY = ...
