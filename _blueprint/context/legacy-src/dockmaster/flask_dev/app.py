"""The routes for the micro service"""

import os
import secrets
import base64
from urllib.parse import urlencode

import requests
from flask import Flask, render_template, redirect, url_for, flash
from flask import current_app, request, abort, session
from flask import Blueprint, jsonify

from .authentication.login import auth_endpoint


def get_session_key():
    """Obtains the session key for the microservice.
    
    - run the following command to generate a new session key
    ```python
    import secrets
    secrets.token_hex()
    ```
    """
    session_key = b'8efbaddc8bee8774fd92e51c5474ece27c84ceaa0a974016eab662065a7ad48d'
    return session_key

#TODO: Implment this configuration
def get_default_config():
    """Obtains the configuration for the microservice
    
    Google OAuth 2.0 documentation:
    https://developers.google.com/identity/protocols/oauth2/web-server#httprest
    """
    config = {
        'NO_AUTH': [], #list of urls that do not require authentication
        'NO_AUTH_PREFIXES' : [], #list of url prefixes that do not require authentication   
        'PROVIDER_CLIENT_ID': "103999402146-hr1lj72kcib0iit3fvqtd0h26b05jld8.apps.googleusercontent.com",
        'PROVIDER_AUTHORIZE_URL': 'https://accounts.google.com/o/oauth2/auth',
        'PROVIDER_TOKEN_URL': 'https://oauth2.googleapis.com/token',
        'PROVIDER_SCOPES': ['openid', 'email', 'profile'],
        'REDICT_URI': 'http://localhost:5000/',
        #secrets.token_hex()
        'SESSION_KEY': b'8efbaddc8bee8774fd92e51c5474ece27c84ceaa0a974016eab662065a7ad48d',
    }
    return config


app = Flask("dockmaster", template_folder="templates",static_folder='assets')
app.secret_key = base64.b64decode(get_session_key())

app.register_blueprint(auth_endpoint, url_prefix='/auth')

# @app.before_request
# def sso_authenticate():
#     #authenticate with sso
#     return login_authenticate()

@app.route('/')
def index():
    """Expose the login buttons and public homepage"""
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)