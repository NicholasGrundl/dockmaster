"""Google SSO managers and utilities."""
import secrets
from urllib.parse import urlencode

import httpx
from starlette.datastructures import URL

from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

class GoogleOAuth2Client:
    """Manage the OAuth 2 authorization flow"""

    def __init__(self, client_id : str, client_secret : str, redirect_uri:str | None, scopes : list[str]):
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes
        self._redirect_uri = redirect_uri

    @property
    def redirect_uri(self)->str:
        """Get the redirect uri"""
        if self._redirect_uri is None:
            raise ValueError("Redirect URI not set")
        return self._redirect_uri
    
    @redirect_uri.setter
    def redirect_uri(self, uri:str):
        """Set the redirect uri"""
        if not isinstance(uri, str):
            uri = str(uri)
        self._redirect_uri = uri
    
    def get_scope(self)->str:
        """Get the scopes in a single string format"""
        return " ".join(self.scopes)
    
    def create_authorization_url(
        self, 
        authorization_endpoint : str, 
        state : str | None = None, 
        redirect_uri : str | None = None
    )->tuple[str,str]:
        """Generate an authorization URL and state.
        - if state not passed creates one
        - if redirect_uri passed sets it
        """
        if state is None:
            state = secrets.token_urlsafe(16)
        if redirect_uri is not None:
            self.redirect_uri = redirect_uri

        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': self.get_scope(),
            'access_type': 'offline', # To receive a refresh token
            'state': state,
            'prompt': 'select_account'
        }
        # Use urlencode instead of URL class to prevent double-quoting
        authorization_url = f"{authorization_endpoint}?{urlencode(params)}"
        
        return authorization_url, state
    
    def exchange_code_for_tokens(self, token_endpoint : str, code : str)->dict:
        """Exchange the authorization code for access tokens"""
        
        # Assemble the json body
        body = {
            'code': code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'grant_type': 'authorization_code'
        }

        # Make the request to exchange the code for tokens
        try:
            r=httpx.post(
                url=token_endpoint, 
                json=body
            ).raise_for_status()
        except httpx.HTTPStatusError as e:
            raise e
        
        tokens = r.json()
        return tokens
    
    def verify_google_id_token(self, id_token:str, clock_skew_in_seconds: int = 10)->dict:
        """Verify the google id  and return payload"""
        try:
            id_token_payload = google_id_token.verify_oauth2_token(
                id_token=id_token, 
                request=google_requests.Request(), 
                audience=self.client_id,
                clock_skew_in_seconds=clock_skew_in_seconds
            )
        except Exception as e:
            return {}
        return id_token_payload
