" Charon: RequestHandler subclass."

import logging
import urllib
import weakref

import tornado.web
import couchdb

from . import settings
from . import constants
from . import utils


class RequestHandler(tornado.web.RequestHandler):
    "Base request handler."

    def prepare(self):
        "Get the database connection. Set up caches."
        self.db = utils.get_db()
        self._cache = weakref.WeakValueDictionary()
        self._users = weakref.WeakValueDictionary()
        self._projects = weakref.WeakValueDictionary()
        self._samples = weakref.WeakValueDictionary()
        self._libpreps = weakref.WeakValueDictionary()

    def http_error(self, status_code, reason):
        "Output an HTTP error message."
        raise tornado.web.HTTPError(status_code, reason=str(reason))

    def get_template_namespace(self):
        "Set the variables accessible within the template."
        result = super(RequestHandler, self).get_template_namespace()
        result['settings'] = settings
        result['constants'] = constants
        result['current_user'] = self.get_current_user()
        result['self_url'] = self.request.uri
        return result

    def get_current_user(self):
        "Get the currently logged-in user."
        try:
            status = self._user.get('status')
        except AttributeError:
            email = self.get_secure_cookie(constants.USER_COOKIE_NAME)
            if not email:
                return None
            try:
                user = self.get_user(email)
            except KeyError:
                return None
            if user.get('status') != constants.ACTIVE:
                return None
            self._user = user
        else:
            if status != constants.ACTIVE:
                self.set_secure_cookie(constants.USER_COOKIE_NAME, '')
                self._user = None
        return self._user

    def get_user(self, email):
        """Get the user identified by the email address.
        Raise KeyError if no such user."""
        try:
            return self._users[email]
        except KeyError:
            return self.get_and_cache('user/email', email, self._users)

    def get_project(self, projectid):
        """Get the project by the projectid.
        Raise KeyError if no such project."""
        try:
            return self._projects[projectid]
        except KeyError:
            return self.get_and_cache('project/projectid',
                                      projectid,
                                      self._projects)

    def get_projects(self):
        "Get all projects."
        return [self.get_project(r.key) for r in
                self.db.view('project/projectid')]

    def get_sample(self, projectid, sampleid):
        """Get the sample by the projectid and sampleid.
        Raise KeyError if no such sample."""
        key = (projectid, sampleid)
        try:
            return self._samples[key]
        except KeyError:
            return self.get_and_cache('sample/sampleid', key, self._samples)

    def get_samples(self, projectid):
        "Get all samples for the project."
        startkey = (projectid, '')
        endkey = (projectid, constants.HIGH_CHAR)
        return [self.get_sample(*r.key) for r in
                self.db.view('sample/sampleid')[startkey:endkey]]

    def get_libprep(self, projectid, sampleid, libprepid):
        key = (projectid, sampleid, libprepid)
        try:
            return self._libpreps[key]
        except KeyError:
            return self.get_and_cache('libprep/libprepid', key, self._libpreps)

    def get_libpreps(self, projectid, sampleid):
        startkey = (projectid, sampleid, '')
        endkey = (projectid, sampleid, constants.HIGH_CHAR)
        return [self.get_libprep(*r.key) for r in
                self.db.view('libprep/libprepid')[startkey:endkey]]

    def get_and_cache(self, viewname, key, cache):
        view = self.db.view(viewname, include_docs=True)
        rows = list(view[key])
        if len(rows) == 1:
            item = cache[key] = rows[0].doc
            self._cache[item['_id']] = item
            return item
        else:
            self.http_error(404, 'no such item')

    def get_logs(self, id):
        "Return the log documents for the given doc id."
        view = self.db.view('log/doc', include_docs=True)
        return sorted([r.doc for r in view[id]],
                      cmp=utils.cmp_timestamp,
                      reverse=True)
