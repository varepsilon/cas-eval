# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
################################################################################
#
# Collection of utils used by the logs management server.

from datetime import datetime, timedelta
import flask
import random
import string

#
# CSRF protection.
#
# Not enabled for every request because of save_page method that is tricky
# (it comes from a different domain).
def csrf_protect():
    if flask.request.method == "POST":
        token = flask.session.pop('_csrf_token', None)
        if not token or token != flask.request.form.get('_csrf_token'):
            flask.abort(403)


def id_generator(N):
   return ''.join(random.choice(string.ascii_letters + string.digits) for _ in xrange(N))


def generate_csrf_token():
    if '_csrf_token' not in flask.session:
        flask.session['_csrf_token'] = id_generator(50)
    return flask.session['_csrf_token']


def format_time(ts):
    # TODO(chuklin): use proper timezones.
    return (ts + timedelta(hours=2)).strftime('%a %d %b %X CEST')


def default(obj):
    """Default JSON serializer."""
    import calendar, datetime

    if isinstance(obj, datetime.datetime):
        if obj.utcoffset() is not None:
            obj = obj - obj.utcoffset()
    millis = int(
        calendar.timegm(obj.timetuple()) * 1000 +
        obj.microsecond / 1000
    )
    return millis
