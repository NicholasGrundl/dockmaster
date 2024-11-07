"""Configurations for the Dockmaster application."""

import os
import pathlib
import json
from functools import lru_cache
import secrets

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class GoogleOAuth2Settings(BaseSettings):
    """Configuration for Google OAuth2.0 
    authorization_code flow."""
    client_id: str
    client_secret: str
    scopes : list[str] = ["openid", "email", "profile"]
    metadata_url: str = 'https://accounts.google.com/.well-known/openid-configuration'
    model_config = SettingsConfigDict(
        env_file=".env",
        extra='ignore',
    )







####################
class GoogleSSOSettings(BaseSettings):
    """Configuration for Google SSO authentication."""
    client_secret_filepath: str  = Field(..., description="The filepath to Google OAuth 2.0 client secret")
    client_id: str = Field(default="587317563831-amn9igi14cbmp79bfmc83fngk88aqdcb.apps.googleusercontent.com", description="The Google OAuth 2.0 client ID")
    authorize_url: HttpUrl = Field(default="https://accounts.google.com/o/oauth2/auth", description="Google's authorization endpoint")
    token_url: HttpUrl = Field(default="https://oauth2.googleapis.com/token", description="Google's token endpoint")
    scopes: list[str] = Field(default=["openid", "email", "profile"], description="OAuth 2.0 scopes for the token request")

    model_config = SettingsConfigDict(
        env_file=".env.auth",
        extra='ignore',
    )

class DockmasterSettings(BaseSettings):
    """Configuration for the Dockmaster application."""
    log_level : str = Field(default="DEBUG", description="The log level for the application")
    log_file : str = Field(default="/home/nicholasgrundl/.logs/dockmaster.log", description="The filepath for the application logs")
    
    jwt_secret_key: str = Field(..., description="The JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="The JWT algorithm to use")
    jwt_expiration: int = Field(default=3600, description="The JWT expiration time in seconds")
    
    model_config = SettingsConfigDict(
        env_file=".env.auth",
        extra='ignore',
    )