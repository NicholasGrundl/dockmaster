from typing import Annotated
import json

import httpx
from fastapi import FastAPI, Cookie
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .configuration import GoogleOAuth2Settings
from .logger_config import setup_uvicorn_logger
from .authenticate.google import GoogleOAuth2Client
from .session.memory_session import MemorySession
from .session.schemas import SessionInterface

app_logger = setup_uvicorn_logger(log_level="DEBUG")
app = FastAPI()

def query_discovery(metadata_url):
    r = httpx.get(metadata_url)
    return r.json()

google_settings = GoogleOAuth2Settings()
discovery = query_discovery(google_settings.metadata_url)
oauth_client = GoogleOAuth2Client(
    client_id=google_settings.client_id,
    client_secret=google_settings.client_secret,
    scopes=google_settings.scopes,
    redirect_uri=None,
)
server_session: SessionInterface = MemorySession()



@app.get('/discovery')
def get_discovery(request: Request):
    url = google_settings.metadata_url
    r = httpx.get(url)
    return r.json()


@app.get('/config')
def get_config(request: Request):
    return google_settings


@app.get('/')
def homepage(request: Request,):
    user = request.cookies.get('user')
    app_logger.debug(f"{user=}")
    if user:
        user_data = json.loads(user)
        html_profile = [
            f'<li><b>{key}</b>: {value}</li>' for key, value in user_data.items()
        ]
        html = (
            '<div>'
            '<h1> Dockmaster - Console </h1>'
            f'<div>{"".join(html_profile)}</div>'
            '<a href="auth/logout"><button>Logout</button></a>'
            '</div>'
        )
        return HTMLResponse(html)

    html_content = (
        '<div>'
        '<h1> Dockmaster - Public </h1>'
        '<p> Login to access the console </p>'
        '<a href="auth/login/google"><button>Login</button></a>'
        '</div>'
    )
    return HTMLResponse(html_content)


@app.get('auth/login/google')
def google_login(request: Request):
    """OAuth2 flow, step 1: have the user log into google to obtain an authorization code grant
    """
    redirect_uri = request.url_for('google_callback') #make sure this is added to the google IAM allowed paths
    app_logger.debug(f"Redirect after authentication to: {redirect_uri}")
    authorization_endpoint=discovery['authorization_endpoint'] 

    # Create state and pass in
    uri, state = oauth_client.create_authorization_url(
        authorization_endpoint=authorization_endpoint,
        redirect_uri=redirect_uri
    )
    
    # Create login session and store state
    app_logger.debug(uri)
    app_logger.debug(f"{state=}")
    session_id = server_session.store_session({'state': state})
    app_logger.debug(f"{session_id=}")

    # Redirect with login session cookie
    response = RedirectResponse(url=uri)
    response.set_cookie('session_id', session_id) #TODO: configure cookie name for dockmaster
    return response

@app.get('/auth/callback/google')
def google_callback(request: Request, code: str, state: str, session_id: Annotated[str, Cookie()]):
    """OAuth2 flow, step 2: exchange the authorization code for access token
    """
    redirect_uri = request.url_for('homepage')
    app_logger.debug(f"Redirect after token exchange to: {redirect_uri}")
    access_token_url=discovery['token_endpoint'] #exchange the code for access tokens
    
    # Load and validate login session (state + code)
    app_logger.debug(f"{code=}")
    app_logger.debug(f"{state=}")
    app_logger.debug(f"{session_id=}")
    session_data = server_session.retrieve_session(session_id)
    

    # Exchange valid code for tokens
    tokens = oauth_client.exchange_code_for_tokens(access_token_url, code)
    app_logger.debug(f"{tokens.keys()=}")

    # Verify ID token and create auth session
    id_token = tokens['id_token']
    id_token_payload = oauth_client.verify_google_id_token(id_token)
    authentication_user_id = id_token_payload.get('sub') #unique id
    # TODO: clear flow session, create auth session
    # - store tokens in auth session for refresh

    # Get user id and dockmaster username from authentication_user_id
    dockmaster_username = id_token_payload.get('email') #TODO: lookup via whitelist on user_id
    
    # Redirect to home with auth cookie
    response = RedirectResponse(url='/')
    if dockmaster_username:
        user_json = json.dumps({'username': dockmaster_username})
        response.set_cookie('user', user_json)
    return response


@app.get('auth/logout')
def logout(request: Request):
    response = RedirectResponse(url='/')
    response.delete_cookie('user')
    return response
