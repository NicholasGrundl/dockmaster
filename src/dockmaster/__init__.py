"""Python package for Authentication and Authorization microservice."""

# Package meta data (for publishing)
__version__ = (0, 0, 2)
__author__ = "Nick Grundl"
__author_email__ = '"Nick Grundl" <nicholasgrundl@gmail.com>'
__maintainer__ = "Nick Grundl"
__maintainer_email__ = '"Nick Grundl" <nicholasgrundl@gmail.com>'

#####################
# Consider these endpoints (from https://github.com/dmontagu/fastapi-auth)
#
# "/auth/token",
# "/auth/token/refresh",
# "/auth/token/validate",
# "/auth/token/logout",
# "/auth/token/logout/all",
# "/auth/register",
# "/auth/self",
# "/admin/users/{user_id}",
# "/admin/users",
#
#############################







#####################
# TODO
# check each init file for todos
#
# Implement a cookie based JWT system
# - no session based refresh tokens yet
# - just a single JWT expiry then relogin
# - session based authentication 
#   - holds state and nonce
#   - holds the destination url and params if sso triggered from middleware
#
# SSO authentication class
# - encapsulate SSO call in a class
#   - initialized with global configs
# - takes input args for the SSO flow
# - returns the google (ID, access, refresh) tokens
#
# Implement a JWT dockmaster class
# - encapsulates issueing dockmaster JWTs
#   - initialized with global configs
# - takes an authenticated email and issues a JWT
#   - no RBAC claims yet
#   - checks a whitelist of users
#
# implemennt the middleware
# unittests
# update the top level routes
#  - should handle prefixes
#  - use the middle ware to pass from a destimation through auth to the destination if passing
#
# check the remaining stages f implementation
####################
