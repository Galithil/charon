" Charon: Various utility functions. "

import urlparse
import uuid
import datetime
import unicodedata

import tornado.web
import couchdb

from charon import constants
from charon import settings


def check_settings():
    """Raise KeyError if a settings variable is missing.
    Raise ValueError if the settings variable value is invalid."""
    for key in ['DB_SERVER', 'DB_DATABASE', 'COOKIE_SECRET',
                'USERMAN_URL', 'USERMAN_API_KEY']:
        if key not in settings:
            raise KeyError("no '{0}' in settings".format(key))
        if not settings[key]:
            raise ValueError("setting {0} has invalid value".format(key))
    if len(settings['COOKIE_SECRET']) < 10:
        raise ValueError('setting COOKIE_SECRET too short')

def get_port(url):
    "Get the port number (integer) from the URL."
    parts = urlparse.urlparse(url)
    items = parts.netloc.split(':')
    if len(items) == 2:
        return int(items[1])
    if parts.scheme == 'http':
        return 80
    elif parts.scheme == 'https':
        return 443
    else:
        raise ValueError("could not determine port from URL {0}".format(url))

def get_db():
    "Return the handle for the CouchDB database."
    try:
        return couchdb.Server(settings['DB_SERVER'])[settings['DB_DATABASE']]
    except couchdb.http.ResourceNotFound:
        raise KeyError("CouchDB database '%s' does not exist" %
                       settings['DB_DATABASE'])

def get_iuid():
    "Return a unique instance identifier."
    return uuid.uuid4().hex

def timestamp(days=None):
    """Current date and time (UTC) in ISO format, with millisecond precision.
    Add the specified offset in days, if given."""
    instant = datetime.datetime.utcnow()
    if days:
        instant += datetime.timedelta(days=days)
    instant = instant.isoformat()
    return instant[:-9] + "%06.3f" % float(instant[-9:]) + "Z"

def to_ascii(value):
    "Convert any non-ASCII character to its closest equivalent."
    if not isinstance(value, unicode):
        value = unicode(value, 'utf-8')
    return unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')

def to_bool(value):
    " Convert the value into a boolean, interpreting various string values."
    if not value: return False
    value = value.lower()
    return value in ['true', 'yes'] or value[0] in ['t', 'y']

def log(db, doc, changed={}, deleted={}, current_user=None):
    "Create a log entry for the given document."
    entry = dict(_id=get_iuid(),
                 doc=doc['_id'],
                 doctype=doc[constants.DB_DOCTYPE],
                 changed=changed,
                 deleted=deleted,
                 timestamp=timestamp())
    entry[constants.DB_DOCTYPE] = constants.LOG
    try:
        if current_user:
            entry['operator'] = current_user['email']
    except KeyError:
        pass
    db.save(entry)

def cmp_timestamp(i, j):
    "Compare the two documents by their 'timestamp' values."
    return cmp(i['timestamp'], j['timestamp'])

def delete_project(db, project):
    "Delete the project and all its dependent entities."
    startkey = (project['projectid'], '')
    endkey = (project['projectid'], constants.HIGH_CHAR)
    view = db.view('sample/sampleid', include_docs=True)
    samples = [r.doc for r in view[startkey:endkey]]
    for sample in samples:
        delete_sample(db, sample)
    delete_logs(db, project['_id'])
    del db[project['_id']]

def delete_sample(db, sample):
    "Delete the sample and all its dependent entities."
    delete_logs(db, sample['_id'])
    startkey = (sample['projectid'], sample['sampleid'], '')
    endkey = (sample['projectid'], sample['sampleid'], constants.HIGH_CHAR)
    view = db.view('libprep/libprepid', include_docs=True)
    libpreps = [r.doc for r in view[startkey:endkey]]
    for libprep in libpreps:
        delete_libprep(db, libprep)
    del db[sample['_id']]

def delete_libprep(db, libprep):
    "Delete the libprep and all its dependent entities."
    delete_logs(db, libprep['_id'])
    del db[libprep['_id']]

def delete_logs(db, id):
    "Delete the log documents for the given doc id."
    ids = [r.id for r in db.view('log/doc')[id]]
    for id in ids:
        del db[id]
