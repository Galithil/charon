" Charon: User account handling."

import logging
import json
import urllib

import tornado.web
import couchdb
import requests

from . import constants
from . import settings
from . import utils
from .requesthandler import RequestHandler
from .saver import DocumentSaver


class UserSaver(DocumentSaver):
    doctype = constants.USER


class Login(RequestHandler):
    "Login handler."

    def get(self):
        self.render('login.html',
                    error=None,
                    next=self.get_argument('next', None))

    def post(self):
        self.check_xsrf_cookie()
        try:
            email = self.get_argument('email')
            if not email:
                raise ValueError('no email given')
            url = "{0}/{1}".format(settings['AUTH']['AUTH_HREF'],
                                   urllib.quote(email))
            password = self.get_argument('password')
            if not password:
                raise ValueError('no password given')
            data = json.dumps(dict(password=password, service='Charon'))
            headers = {'X-Userman-API-token': settings['AUTH']['API_TOKEN']}
            response = requests.post(url, data=data, headers=headers)
            if response.status_code != requests.codes.ok:
                raise ValueError(str(response.reason))
            try:
                user = self.get_user(email)
            except tornado.web.HTTPError:
                user = response.json()
            else:
                user.update(response.json())
            with UserSaver(doc=user, rqh=self) as saver:
                # All other changes already made.
                if not user.get('api_token'):
                    saver['api_token'] = utils.get_iuid()
            self.set_secure_cookie(constants.USER_COOKIE_NAME, email)
            url = self.get_argument('next', None)
            if not url:
                url = self.reverse_url('home')
            self.redirect(url)
        except (tornado.web.MissingArgumentError, ValueError), msg:
            logging.debug("login error: %s", msg)
            self.render('login.html',
                        error=str(msg),
                        next=self.get_argument('next', None))


class Logout(RequestHandler):
    "Logout handler."

    def post(self):
        self.check_xsrf_cookie()
        self.set_secure_cookie(constants.USER_COOKIE_NAME, '')
        self.redirect(self.reverse_url('login'))


class User(RequestHandler):
    "User account handler."

    @tornado.web.authenticated
    def get(self, email):
        user = self.get_user(email)
        if user != self.get_current_user() and user['role'] != 'admin':
            raise tornado.web.HTTPError(403)
        self.render('user.html',
                    user=user,
                    logs=self.get_logs(user['_id']))


class UserApiToken(RequestHandler):
    "API token handler for user account."

    @tornado.web.authenticated
    def post(self, email):
        "Set the API token for the user."
        self.check_xsrf_cookie()
        user = self.get_user(email)
        if user != self.get_current_user() and user['role'] != 'admin':
            raise tornado.web.HTTPError(403)
        with UserSaver(doc=user, rqh=self) as saver:
            saver['api_token'] = utils.get_iuid()
        self.redirect(self.reverse_url('user', user['email']))
