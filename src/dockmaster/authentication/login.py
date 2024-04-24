"""Blueprint for login and authentication"""

from typing import Optional
import os
from datetime import datetime
from uuid import uuid4
import pickle
from urllib.parse import quote as uriencode, unquote_plus
from urllib.parse import urlencode
import json
import pathlib

from flask import Blueprint, request, session, current_app, abort
from flask import redirect, url_for, jsonify
from google.oauth2.id_token import verify_oauth2_token
from google.auth.transport import requests as google_requests


from ..utils import requests_retry_session

#### Secrets ####
def get_client_secret_key():
    """Get the client secret key from the environment
    - used for signing the session cookie
    """
    client_secret_filepath = current_app.config.get(
        'CLIENT_SECRET_FILEPATH', os.environ.get('CLIENT_SECRET_FILEPATH',None)
    )
    if isinstance(client_secret_filepath, str):
        client_secret_filepath = pathlib.Path(client_secret_filepath)
    else:
        return None
    #Open json file and grab key
    with open(client_secret_filepath, 'r') as f:
        client_secret = json.load(f).get('web').get('client_secret')
    return client_secret

#### Session management for authentication ####
def default_profile_properties():
    """Get the default properties for the user profile
    based on google SSO and OpenIDConnect
    """
    return [
        'name',
        'email',
        'picture',
        'given_name',
        'family_name',
    ]

def get_principal_profile_from_session(profile_properties:Optional[list[str]]=None)->dict:
    """Get the principal profile from the session. 
    If no profile_properties passed uses default properties.

    """
    if profile_properties is None:
        profile_properties = default_profile_properties()
    principal_profile = {}
    for property in profile_properties:
        principal_profile[property] = session.get(property,'')
    return principal_profile

def authenticated_session_exists()->bool:
    """Check if the current session has a principal
    that is authenticated and valid. 
    
    If session authentication is invalid, clears 
    invalid info and returns False.
    
    Looks for the following in the session:
    - 'token' key 
    - 'expiry' key is present and not expired
    """
    #Check for an access token in the session
    authenticated = 'token' in session and session['token'] is not None
   
    #Check that access token is valid
    if authenticated:
        if 'expiry' in session:
            #check expiration
            now = datetime.now().astimezone()
            tz = now.tzinfo
            expiry = session['expiry'].replace(tzinfo=tz)
            elapsed = expiry - now
            if elapsed.total_seconds()<0:
                #clear authentication keys
                session.pop('token',None)
                session.pop('expiry',None)
                return False
        else:
            #no expiration, consider invalid
            session.pop('token',None)
            return False
    return authenticated

#### SSO Authentication ####
#TODO: Rename this function? Its just checking that we are authenticated
def get_sso_authenticate_uri():
    """Get the uri for the OAuth provider for SSO authentication
    - typically we redirect to this uri (e.g. google SSO)
    - https://developers.google.com/identity/openid-connect/openid-connect#authenticationuriparameters
    """
    #where to go after SSO completes
    dest_uri = request.host_url+"auth/authenticated" #where the exchange and authorization occurs

    #security parameters
    state = str(uuid4())
    nonce = str(uuid4())
    session['state'] = state

    #store the original request for later
    # TODO: Make this dynamic based on the calling route
    # - currently only designed for the console login
    public_home_url = url_for('index')
    session['state.path'] = public_home_url #where to go after SSO completes
    session['state.args'] = pickle.dumps(request.args)
    
    #assemble the request uri
    #TODO: Add configuration in here via current app and environment
    provider_authorize_url = 'https://accounts.google.com/o/oauth2/auth'
    provider_scopes = ['openid', 'email', 'profile'] #https://developers.google.com/identity/protocols/oauth2/scopes#openid-connect
    provider_client_id = '103999402146-hr1lj72kcib0iit3fvqtd0h26b05jld8.apps.googleusercontent.com'
    #TODO: Add configuration in here to match app root changing
    redirect_uri = 'http://localhost:5000/auth/authenticated'

    uri_query = (
        'client_id=' + provider_client_id
        + '&prompt=select_account'
        + '&response_type=code'
        #force safe spaces not + signs
        + '&scope=' + uriencode(' '.join(provider_scopes))
        + '&redirect_uri=' + uriencode(dest_uri)
        + '&state='+state
        + '&nonce='+nonce 
    )
    
    authenticate_uri = provider_authorize_url + '?' + uri_query
    current_app.logger.debug(f"Redirect: {dest_uri}")
    current_app.logger.debug(f"Query: {uri_query}")
    return authenticate_uri

def exchange_authorization_code(authorization_code)->dict | None:
    """Exchange the authorization_code for an access token.
    returns a dictionary or None if uncuccessful

    see google developer docs for more info
    - (https://developers.google.com/identity/openid-connect/openid-connect#exchangecode)
    see OAuth spec for more info (RCF 6749)
    - (https://datatracker.ietf.org/doc/html/rfc6749#section-4.1.3)
    """
    #TODO: These should be a higher level function?
    #TODO: Add configuration in here via current app and environment
    provider_token_url = 'https://oauth2.googleapis.com/token'
    provider_scopes = ['openid', 'email', 'profile'] #https://developers.google.com/identity/protocols/oauth2/scopes#openid-connect
    provider_client_id = '103999402146-hr1lj72kcib0iit3fvqtd0h26b05jld8.apps.googleusercontent.com'
    provider_client_secret = get_client_secret_key()
    
    #TODO: Add configuration in here to match app root changing
    redirect_uri = 'http://localhost:5000/auth/authenticated'
    
    data = {
        'code' : authorization_code,
        'client_id' : provider_client_id,
        'client_secret' : provider_client_secret,
        'redirect_uri' : redirect_uri,
        'grant_type' : 'authorization_code'
    }

    exchange_response = requests_retry_session().post(
        url=provider_token_url,
        data=data,
        timeout=(5,30) #(connect_timeout, read_timeout) in seconds
    )
    if exchange_response.status_code!=200:
        return None
    return exchange_response.json()

def get_valid_id_profile(id_token:str,client_id:str,clock_skew_in_seconds:int=0)->dict | None:
    """Verify the id token (JWT) from the OAuth provider. 
    If valid returns a dictionary of the user's ID profile information 
    otherwise returns None

    see google developer docs for more info
    - (https://developers.google.com/identity/gsi/web/guides/verify-google-id-token#using-a-google-api-client-library)
    """
    try:
        id_profile = verify_oauth2_token(
            id_token=id_token, 
            request=google_requests.Request(), 
            audience=client_id, 
            clock_skew_in_seconds=0
        )
        return id_profile
    except ValueError as e:
        #invalid token
        return None

def get_id_principal(id_profile:dict)->tuple[str,dict]:
    """Get the principal from the ID profile
    
    - we use the principal for authorizing individuals
    - currently we just grab the email
    """
    #user identification via email
    # - this is not the safest solution, but is good for now
    # - people can have multiple emails for the same google identity
    # - see (https://developers.google.com/identity/gsi/web/reference/js-reference#credential)
    email = id_profile.get('email')
    return email

#### Login Service Blueprint ####
auth_endpoint = Blueprint('auth', __name__, url_prefix='/auth')

@auth_endpoint.route('/logout',methods=['GET'])
def logout():
    """Logout the current user then redirect to root URL"""
    session.clear()
    public_home_url = url_for('index')
    return redirect(public_home_url)

@auth_endpoint.route('/login',methods=['GET'])
def login():
    """Login the current user then redirect to root URL"""
    authenticated = authenticated_session_exists()
    if authenticated:
        #already authenticated, pass through request
        public_home_url = url_for('index')
        return redirect(public_home_url)
    #send to SSO redirect
    return redirect(get_sso_authenticate_uri())

@auth_endpoint.route('/principal',methods=['GET'])
def principal():
    """Obtain the current principal if authenticated
    from the session 
    
    -if authentication is valid return profile (i.e. user info JSON)
    -if authentication is invalid returns {}
    """
    #check if user has principal data (i.e. already logged in)
    if authenticated_session_exists():
        principal_profile = get_principal_profile_from_session()
    else:
        principal_profile = {}
    
    return jsonify(principal_profile)

@auth_endpoint.route('/authenticated', methods=['GET'])
def authenticated():
    """Callback for authentication from OAuth provider
    - go here after google SSO login occurs
    - validates the response
    - checks the user is authorized
    - redirects back to original path/route

    see docs for what a return should look like
    (https://developers.google.com/identity/protocols/oauth2/web-server#exchange-authorization-code)
    """  
    #assemble the request uri
    #TODO: Add configuration in here via current app and environment
    provider_client_id = '103999402146-hr1lj72kcib0iit3fvqtd0h26b05jld8.apps.googleusercontent.com'

    current_app.logger.debug(f"---------------------------------------------")
    current_app.logger.debug(f"url: {request.url}")
    current_app.logger.debug(f"args: {request.args.to_dict()}")
    #Check for response information
    if 'error' in request.args:
        current_app.logger.error(f"Error: {request.args.get('error')}")
        abort(401)
    if 'code' not in request.args:
        abort(401)

    # Check for cross-site request forgery
    if request.args.get('state','')!=session.get('state'): 
        current_app.logger.error(
            f"Unauthorized, session '{session.get('state')}' did not match state '{request.args.get('state','')}'."
        )
        abort(401)
    session.pop('state',None)

    # Exchange authorization code for ID token
    authorization_code = request.args.get('code','')
    exchange_info = exchange_authorization_code(authorization_code)
    if exchange_info is None:
        current_app.logger.error(
            f"Failed to exchange code"
        )
        abort(401)
    id_token = exchange_info.get('id_token')
    
    # Verify ID token
    id_profile = get_valid_id_profile(
        id_token=id_token,
        client_id=provider_client_id,
        clock_skew_in_seconds=0
    )
    if id_profile is None:
        current_app.logger.error(f"Invalid ID token")
        abort(401)
    current_app.logger.debug(f"id_profile: {id_profile}")
    
    # Get User info from ID token
    # - looks lik (https://developers.google.com/identity/gsi/web/reference/js-reference#credential)
    id_principal = get_id_principal(id_profile)

    #TODO: Check if user is in authorized users
    # - list of emails in google secrets?
    # - if not fail auth    

    # Set session properties for authenticated principal (email, name, etc)
    # - authentication proof
    session['token'] = id_token #store the token
    expiry_seconds = id_profile.get('exp')
    expiry_datetime = datetime.fromtimestamp(expiry_seconds) #Local time zone
    session['expiry'] = expiry_datetime #store expiration
    # - principal info (what roles they are allowed)
    profile_properties = default_profile_properties()
    for property in profile_properties:
        #store other profile properties
        session[property] = id_profile.get(property,'')
    current_app.logger.debug(
        f"Token for {id_principal} expires at {expiry_datetime.isoformat()} local time"
    )
    
    

    # Redirect to orginal path + args
    request_path = session.pop('state.path','/')
    if session.get('state.args', None) is not None:
        request_args = pickle.loads(session.pop('state.args'))
    else:
        request_args = {}
    # - assemble the redirect path with args
    redirect_uri = request_path
    for i, arg_name in enumerate(request_args):
        arg_value = request_args[arg_name]
        redirect_uri = redirect_uri + ('?' if i==0 else '&') + arg_name + '=' + uriencode(arg_value)

    return redirect(redirect_uri)