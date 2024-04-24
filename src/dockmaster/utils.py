"""Utilities for the dockmaster app."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def requests_retry_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504), session=None):
    """Create a requests session that implements retries
    - use for critical requests that may occur over unreliable networks
    - e.g. google auth requests sometimes experiance 5XX server errors
      (https://www.bluefrontier.co.uk/company/blog/item/a-guide-to-http-500-server-error-codes)
    """
    session = requests.Session() if session is None else session
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session