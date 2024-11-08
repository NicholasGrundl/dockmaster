from typing import Annotated
import json
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Cookie
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import HTTPException

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
def homepage(request: Request, session_id: Annotated[str | None, Cookie()] = None):
    #Proxy for a auth check via session_id
    if session_id is not None:
        app_logger.debug(f"Found credentials in cookies. {session_id=}")
        #verify session and remove cookie
        session_data=server_session.retrieve_data(session_id)
        if session_data is None:
            app_logger.debug(f"Session data not found. Removing {session_id=}")
            server_session.remove_data(session_id)
            response = RedirectResponse(url='/')
            response.delete_cookie('session_id')
            return response
        else:
            app_logger.debug(f"Session data found. {list(session_data.keys())}")
            #Only login if session_data is available
            app_logger.debug(f"{session_id=}")
            
            #Obtain profile if available
            user_id = session_data.get('user_id')
            user_profile = session_data.get('user_profile',{})
            image_url = user_profile.get('picture', None)
            
            #Render HTML
            html_user_id = f'<div><h2> User ID: {user_id}</h2></div>' if user_id else '<div></div>'
            html_image =f'<div><img src={image_url} alt="User Image"></div>' if image_url else '<div></div>'
            html_profile = "".join([
                f'<li><b>{key}</b>: {value}</li>' for key, value in user_profile.items()
            ])
            html = (
                '<div>'
                '<h1> Dockmaster - Console </h1>'
                f'{html_user_id}'
                f'{html_image}'
                f'<div>{html_profile}</div>' 
                '<a href="auth/logout"><button>Logout</button></a>'
                '</div>'
            )
            return HTMLResponse(html)
    app_logger.debug(f"No credentials found. Showing public homepage.")
    app_logger.debug(f"{session_id=}")
    html_content = (
        '<div>'
        '<h1> Dockmaster - Public </h1>'
        '<p> Login to access the console </p>'
        '<a href="auth/login/google"><button>Login</button></a>'
        '</div>'
    )
    return HTMLResponse(html_content)


@app.get('/auth/login/google')
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
    app_logger.debug(uri)
    app_logger.debug(f"{state=}")
    
    # Create login session and store state
    session_id = server_session.store_data({'state': state})
    app_logger.debug(f"Created authentication flow session. {session_id=}")

    # Redirect with login session cookie
    response = RedirectResponse(url=uri)
    #TODO: configurable cookie name for dockmaster
    response.set_cookie('session_id', session_id, secure=True, httponly=True, samesite='lax') 
    return response

@app.get('/auth/callback/google')
def google_callback(
    request: Request, 
    code: str, 
    state: str | None = None, 
    session_id: Annotated[str | None, Cookie()] = None
):
    """OAuth2 flow, step 2: exchange the authorization code for access token
    """
    redirect_uri = request.url_for('homepage')
    app_logger.debug(f"Redirect after token exchange to: {redirect_uri}")
    
    # Validate login session (state + code)
    if (session_id is None):
        app_logger.warning("Session not found.")
        raise HTTPException(status_code=401, detail="Session not found")
    app_logger.debug(f"Found a login session {session_id=}")
    session_data = server_session.retrieve_data(session_id)
    session_state = session_data.get('state')
    if state != session_state:
        app_logger.warning("Unauthorized request. Session state '{session_state}' does not match state '{state}'.")
        raise HTTPException(status_code=401, detail="Session not found")
    server_session.remove_data(session_id)

    # Exchange valid code for tokens
    access_token_url=discovery['token_endpoint'] #exchange the code for access tokens
    try:
        # TODO: implement retry logic on the client here for token exchange
        tokens = oauth_client.exchange_code_for_tokens(access_token_url, code)
        app_logger.debug(f"Code '{code=}' exchanged successfully.")
        app_logger.debug(f"{tokens.keys()}")
    except Exception as e:
        app_logger.debug(f"Cannot exchange code, {e}")
        raise HTTPException(status_code=401, detail=e)
    
    # Verify ID token and obtain Dockmaster User ID
    id_token = tokens['id_token']
    app_logger.debug(f"Code exchanged for id_token={id_token}")
    id_token_payload = oauth_client.verify_google_id_token(id_token)
    # - obtain unique user_id for dockmaster
    # TODO: For more login mehtods:
    #       use id_token_payload['sub'] with a 'google_' prefix as global_user_id in a database
    #       use database table to find dockmaster_user_id from global_user_id
    #       Allows various global_user_id to dockmaster_user_id many to one mapping for multiple login approaches
    #TODO: check a list of authorized user_ids
    #      - fail fast on authentication check
    user_id = id_token_payload.get('email') #dockmaster user_id

    # Obtain RBAC roles and create JWT

    # Create an authorization session
    session_data = {
        'user_id': user_id,
        'user_profile' : id_token_payload,
        'tokens': tokens,
        'created_at': datetime.now(timezone.utc)
    }
    session_id = server_session.store_data(session_data)
    app_logger.debug(f"Created authorization session. {session_id=}")

    # Redirect to home with auth cookie
    # TODO: allow pass through redirect after successful login?
    response = RedirectResponse(url=redirect_uri)
    response.set_cookie('session_id', session_id, secure=True, httponly=True, samesite='lax')
    return response


@app.get('/auth/logout')
def logout(request: Request):
    response = RedirectResponse(url='/')
    response.delete_cookie('session_id')
    return response
