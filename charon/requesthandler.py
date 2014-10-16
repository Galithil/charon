" Charon: RequestHandler subclass."

import logging
import urllib
import weakref

import tornado.web
import couchdb

import charon
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
        self._seqruns = weakref.WeakValueDictionary()

    def get_template_namespace(self):
        "Set the variables accessible within the template."
        result = super(RequestHandler, self).get_template_namespace()
        result['version'] = charon.__version__
        result['settings'] = settings
        result['constants'] = constants
        result['current_user'] = self.get_current_user()
        return result

    def get_absolute_url(self, name, *args, **kwargs):
        "Get the absolute URL given the handler name and any arguments."
        if name is None:
            path = ''
        else:
            path = self.reverse_url(name, *args)
        url = settings['BASE_URL'].rstrip('/') + path
        if kwargs:
            url += '?' + urllib.urlencode(kwargs)
        return url

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
            except tornado.web.HTTPError:
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
        Raise HTTP 404 if no such user."""
        try:
            return self._users[email]
        except KeyError:
            return self.get_and_cache('user/email', email, self._users)

    def get_project(self, projectid):
        """Get the project by the projectid.
        Raise HTTP 404 if no such project."""
        try:
            return self._projects[projectid]
        except KeyError:
            try:
                return self.get_and_cache('project/projectid',
                                      projectid,
                                      self._projects)
            except tornado.web.HTTPError:
                return self.get_and_cache('project/name',
                                      projectid,
                                      self._projects)
            
    def get_not_done_projects(self):
        "Get projects that are not done."
        all = [r.value for r in
               self.db.view('project/not_done')]
        return all

    def get_not_done_samples(self, projectid=None):
        "Get samples that are not done."
        if projectid:
            all = [r.value for r in
                   self.db.view('sample/not_done') if r.key[0] == projectid]
        else:
            all = [r.value for r in
                   self.db.view('sample/not_done')]

        return all


    def get_projects(self):
        "Get all projects."
        all = [self.get_project(r.key) for r in
               self.db.view('project/projectid')]
        view1 = self.db.view('sample/count')
        view2 = self.db.view('sample/count_done')
        view3 = self.db.view('libprep/count', group_level=1)
        for project in all:
            try:
                row = view1[project['projectid']].rows[0]
            except IndexError:
                project['sample_count'] = 0
            else:
                project['sample_count'] = row.value
            try:
                row = view2[project['projectid']].rows[0]
            except IndexError:
                project['sample_count_done'] = 0
            else:
                project['sample_count_done'] = row.value
            startkey = [project['projectid']]
            endkey = [project['projectid'], constants.HIGH_CHAR]
            try:
                row = view3[startkey:endkey].rows[0]
            except IndexError:
                project['libprep_count'] = 0
            else:
                project['libprep_count'] = row.value
        return all

    def get_sample(self, projectid, sampleid):
        """Get the sample by the projectid and sampleid.
        Raise HTTP 404 if no such sample."""
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
        """Get the libprep by the projectid, sampleid and libprepid.
        Raise HTTP 404 if no such libprep."""
        key = (projectid, sampleid, libprepid)
        try:
            return self._libpreps[key]
        except KeyError:
            return self.get_and_cache('libprep/libprepid', key, self._libpreps)

    def get_libpreps(self, projectid, sampleid=''):
        """Get the libpreps for the sample if sampleid given.
        For the entire project if no sampleid."""
        startkey = (projectid, sampleid, '')
        endkey = (projectid,
                  sampleid or constants.HIGH_CHAR,
                  constants.HIGH_CHAR)
        return [self.get_libprep(*r.key) for r in
                self.db.view('libprep/libprepid')[startkey:endkey]]

    def get_seqrun(self, projectid, sampleid, libprepid, seqrunid):
        """Get the libprep by the projectid, sampleid, libprepid and seqrunid.
        Raise HTTP 404 if no such seqrun."""
        try:
            key = (projectid, sampleid, libprepid, seqrunid)
            return self._seqruns[key]
        except (ValueError, KeyError):
            return self.get_and_cache('seqrun/seqrunid', key, self._seqruns)

    def get_seqruns(self, projectid, sampleid='', libprepid=''):
        """Get the seqruns for the libprep if libprepid given.
        For the entire sample if no libprepid.
        For the entire project if no sampleid."""
        startkey = (projectid, sampleid, libprepid, '')
        endkey = (projectid,
                  sampleid or constants.HIGH_CHAR,
                  libprepid or constants.HIGH_CHAR,
                  constants.HIGH_CHAR)
        return [self.get_seqrun(*r.key) for r in
                self.db.view('seqrun/seqrunid')[startkey:endkey]]

    def get_and_cache(self, viewname, key, cache):
        """Get the item by the view name and the key.
        Try to get it from the cache, else from the database.
        Raise HTTP 404 if no such item."""
        view = self.db.view(viewname, include_docs=True)
        rows = list(view[key])
        if len(rows) == 1:
            item = cache[key] = rows[0].doc
            self._cache[item['_id']] = item
            return item
        else:
            logging.debug("{0} elements for key {1} ".format(len(rows), key))
            raise tornado.web.HTTPError(404, reason='{0} elements for key {1}'.format(len(rows), key))

    def get_logs(self, id):
        "Return the log documents for the given doc id."
        view = self.db.view('log/doc', include_docs=True)
        return sorted([r.doc for r in view[id]],
                      cmp=utils.cmp_timestamp,
                      reverse=True)

    def send_error(self, status_code=500, **kwargs):
        """ ** This is really a bug fix for Tornado!
        *** A bug fix has been pull-requested to the master Tornado repo.

        Sends the given HTTP error code to the browser.

        If `flush()` has already been called, it is not possible to send
        an error, so this method will simply terminate the response.
        If output has been written but not yet flushed, it will be discarded
        and replaced with the error page.

        Override `write_error()` to customize the error page that is returned.
        Additional keyword arguments are passed through to `write_error`.
        """
        if self._headers_written:
            gen_log.error("Cannot send error response after headers written")
            if not self._finished:
                self.finish()
            return
        self.clear()

        # reason = None               # *** Incorrect line!
        reason = kwargs.get('reason') # *** This is the corrected line.
        if 'exc_info' in kwargs:
            exception = kwargs['exc_info'][1]
            if isinstance(exception, tornado.web.HTTPError) and exception.reason:
                reason = exception.reason
        self.set_status(status_code, reason=reason)
        try:
            self.write_error(status_code, **kwargs)
        except Exception:
            app_log.error("Uncaught exception in write_error", exc_info=True)
        if not self._finished:
            self.finish()

