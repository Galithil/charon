" Charon: setup for tests using nosetest. "

import json

import requests
from nose import with_setup


HOST_URL = 'http://localhost:8881'
BASE_URL = HOST_URL + '/api/v1'

# This key is associated with a user account, and must be current.
apikey = {'X-Charon-API-key': '45b14d3709e0449c904b820aca41e36c'}

def url(*segments):
    "Synthesize absolute URL from path segments."
    return BASE_URL + '/' + '/'.join([str(s) for s in segments])
