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
# Code to handle different HTTP requests to the server.
# The core of the application.

from datetime import datetime, timedelta
import gc
import gzip
import json
import random
import urlparse
import util

import cloudstorage as gcs
from google.appengine.api import users, taskqueue
from google.appengine.ext import ndb, blobstore
from google.appengine.runtime import apiproxy_errors

from shared.logs import parse_href

# Import the Flask Framework
# Note: We don't need to call run() since our application is embedded within
# the App Engine WSGI application server.
import flask
app = flask.Flask(__name__)
app.debug = True
app.secret_key = ('secret')


app.jinja_env.globals['csrf_token'] = util.generate_csrf_token
app.jinja_env.filters['format_time'] = util.format_time

NUM_TASKS = 25

#
# Models
#
class Action(ndb.Model):
    ts = ndb.DateTimeProperty(indexed=True)
    event_type = ndb.StringProperty(indexed=True)
    fields = ndb.JsonProperty(compressed=True)


class Session(ndb.Model):
    # `tab_id` is an explicit key here
    user_id = ndb.StringProperty(indexed=True)
    q = ndb.StringProperty(indexed=True)
    serp_html = ndb.TextProperty()
    actions = ndb.StructuredProperty(Action, repeated=True)
    start_ts = ndb.DateTimeProperty(indexed=True)
    shared = ndb.BooleanProperty(default=False, indexed=True)

    @staticmethod
    def get_user_id(referer):
        """ Extract user_id from the referer URL. This method may raise an exception. """
        return urlparse.parse_qs(urlparse.urlparse(referer).query)['user_id'][0]

    @staticmethod
    def get_query(referer):
        """ Extract user_id from the referer URL. This method may raise an exception. """
        query_b = urlparse.parse_qs(urlparse.urlparse(referer.encode('utf-8')).query)['q'][0]
        return query_b.decode('utf-8')

    @staticmethod
    def convert_time(timestamp_ms):
        timestamp_ms = int(timestamp_ms)
        return (datetime.fromtimestamp(timestamp_ms // 1000) +
                timedelta(milliseconds=timestamp_ms % 1000))

    @property
    def id(self):
        return self.key.id()

    @property
    def is_sat(self):
        return self._sat() == 'SAT'

    @property
    def is_dsat(self):
        return self._sat() == 'DSAT'

    def _sat(self):
        for action in self.actions:
            if action.event_type == 'SatFeedback':
                return action.fields['val']

    @property
    def event_counts(self):
        """ This method is used in the template. """
        counts = {}
        for action in self.actions:
            event_type = action.event_type
            if event_type == 'SatFeedback':
                counts[event_type] = action.fields['val']
            else:
                if event_type == 'Click' and parse_href(action.fields.get('href')) is not None:
                    event_type = 'ResultClick'
                counts.setdefault(event_type, 0)
                counts[event_type] += 1
        return counts


class UserSettings(ndb.Model):
    # `user_id` is an explicit key here
    ts = ndb.DateTimeProperty()
    mute_deadline = ndb.DateTimeProperty()
    # `questionnaire_shown_ts` is sorted from oldest to newest
    questionnaire_shown_ts = ndb.DateTimeProperty(repeated=True)

    @property
    def id(self):
        return self.key.id()

    @staticmethod
    def convert_mute_period_m(settings_str):
        assert settings_str.startswith('mute')
        assert settings_str.endswith('h')
        return int(settings_str[len('mute'):-len('h')]) * 60

    @staticmethod
    def get_mute_deadline(ts, mute_period_m):
        return ts + timedelta(minutes=mute_period_m)

#
# Handlers.
#
@app.route('/')
def index():
    user = users.get_current_user()
    return flask.render_template('index.html', user=user, year=datetime.now().year)


@app.route('/help')
def help():
    user = users.get_current_user()
    return flask.render_template('help.html', user=user, year=datetime.now().year)


@app.route('/opensearch.xml')
def opensearch():
    user = users.get_current_user()
    if not user:
        return 'Not logged in', 401
    return flask.Response(response=flask.render_template('opensearch.xml', user=user),
                          mimetype="text/xml")


@app.route('/main', methods=['POST', 'GET'])
def main():
    user = users.get_current_user()
    if not user:
        return flask.redirect(users.create_login_url(flask.request.path))

    if flask.request.method == 'POST':
        util.csrf_protect()
        tab_ids = flask.request.values.getlist('tab_id')
        keys = [ndb.Key(Session, tab_id) for tab_id in tab_ids]
        if 'delete' in flask.request.values:
            if not all(s and s.user_id == user.user_id() for s in ndb.get_multi(keys)):
                return 'Not authorized to delete some sessions', 403
            ndb.delete_multi(keys)
        elif 'share' in flask.request.values:
            for key in keys:
                session = key.get()
                if session and session.user_id == user.user_id():
                    session.shared = True
                    session.put()
        else:
            return 'Incorrect POST name', 400
    date = flask.request.values.get('date', datetime.now().strftime('%Y-%m-%d'))
    cur_day = datetime.strptime(date, '%Y-%m-%d')
    next_day = cur_day + timedelta(days=1)
    sessions = (Session.query(Session.user_id == user.user_id(),
                Session.start_ts >= cur_day, Session.start_ts < next_day)
            .order(-Session.start_ts))
    num_shared = Session.query(Session.user_id == user.user_id(), Session.shared == True).count()
    return flask.render_template('main.html',
                                 user=user,
                                 date=date,
                                 year=datetime.now().year,
                                 logout_url=users.create_logout_url('/'),
                                 sessions=sessions,
                                 num_shared=num_shared)


@app.route('/render_log', methods=['GET'])
def render_log():
    user = users.get_current_user()
    date = flask.request.values.get('date', datetime.now().strftime('%Y-%m-%d'))
    cur_day = datetime.strptime(date, '%Y-%m-%d')
    next_day = cur_day + timedelta(days=1)
    if user:
        sessions = (Session.query(Session.user_id == user.user_id(),
                    Session.start_ts >= cur_day, Session.start_ts < next_day)
                .order(-Session.start_ts))
        return flask.render_template('log_table_body.html', sessions=sessions)
    else:
        return 'Not logged in', 401


@app.route('/leaderboard', methods=['GET'])
def leaderboard():
    user = users.get_current_user()
    num_shared = []
    for u in Session.query(projection=['user_id'], distinct=True):
        num_shared.append((
            Session.query(Session.user_id == u.user_id, Session.shared == True).count(),
            u.user_id))
    num_shared.sort(reverse=True)
    return flask.render_template('leaderboard.html', user=user, year=datetime.now().year,
        logout_url=users.create_logout_url('/'), num_shared=num_shared)


@app.route('/export', methods=['GET'])
def export():
    user = users.get_current_user()
    total_shared = Session.query(Session.shared == True).count()
    if user and users.is_current_user_admin():
        bucket_size = max(1, total_shared // (NUM_TASKS - 1))
        for i in range(NUM_TASKS):
            # start a task with delay of 60*i seconds
            taskqueue.add(url='/tasks/process_export', method='GET',
                    params={'bucket':  i, 'bucket_size': bucket_size}, countdown=60*i)
        return 'Trigerred for %d queries' % total_shared, 200
    else:
        return 'Admin access only', 403


@app.route('/tasks/process_export', methods=['GET'])
def process_export():
    bucket = int(flask.request.values['bucket'])
    filename = '/ilps-search-log.appspot.com/search_log.%d.gz' % bucket
    with gcs.open(filename, 'w' , 'text/plain', {'content-encoding': 'gzip'}) as f:
        bucket_size = int(flask.request.values['bucket_size'])
        offset = bucket * bucket_size
        with gzip.GzipFile('', fileobj=f, mode='wb') as gz:
            ndb.get_context().clear_cache()
            for s in Session.query(Session.shared == True).iter(batch_size=10,
                    offset=offset, limit=bucket_size):
                ndb.get_context().clear_cache()
                gc.collect()
                s.user_id = ''
                print >>gz, json.dumps(s.to_dict(), default=util.default,
                        ensure_ascii=False).encode('utf-8')
    response = 'Written: %s' % str(blobstore.create_gs_key('/gs' + filename))
    app.logger.info(response)
    return response, 200


@app.route('/save_page', methods=['POST', 'OPTIONS'])
def save_page():
    @flask.after_this_request
    def add_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    values = flask.request.values
    if values.get('type', '') == 'Serp':
        try:
            user_id = Session.get_user_id(values['url'])
        except Exception as e:
            app.logger.error(e)
            return 'Incorrect user_id used', 400
        try:
            query = Session.get_query(values['url'])
        except Exception as e:
            app.logger.error(e)
            return 'No query set?', 400
        for k in ['data', 'tab_id', 'time']:
            if k not in values:
                return 'Missing param: %s' % k, 400
        data = values['data']
        try:
            ts = Session.convert_time(values['time'])
        except Exception as e:
            app.logger.error(e)
            return 'Incorrect timestamp', 400
        session = Session(id=values['tab_id'], user_id=user_id, q=query,
                serp_html=data, start_ts=ts)
        n = len(data)
        while n > 1:
            session.serp_html = data[:n]
            try:
                session.put()
                break
            except apiproxy_errors.RequestTooLargeError as e:
                app.logger.error(e)
                n /= 2
        return 'Saved', 201
    return 'Only support saving SERPs using POST requests, sorry.', 403


@app.route('/save_settings', methods=['POST', 'OPTIONS'])
def save_settings():
    @flask.after_this_request
    def add_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    values = flask.request.values
    try:
        user_id = Session.get_user_id(values['url'])
    except Exception as e:
        app.logger.error(e)
        return 'Incorrect user_id used', 400
    for k in ['data', 'tab_id', 'time']:
        if k not in values:
            return 'Missing param: %s' % k, 400
    try:
        ts = Session.convert_time(values['time'])
    except Exception as e:
        app.logger.error(e)
        return 'Incorrect timestamp', 400
    mute_period_m = 0
    for data in values['data'].split(','):
        try:
            mute_period_m = max(mute_period_m, UserSettings.convert_mute_period_m(data))
        except Exception as e:
            app.logger.error(e)
            return 'Incorrect mute period settings: %s' % data, 400
    mute_deadline = UserSettings.get_mute_deadline(ts, mute_period_m)
    settings = ndb.Key(UserSettings, user_id).get()
    if settings is None:
        # Create settings for the current user
        settings = UserSettings(id=user_id, mute_deadline=mute_deadline, ts=ts)
        settings.put()
    elif settings.mute_deadline is None or settings.mute_deadline < mute_deadline:
        settings.mute_deadline = mute_deadline
        settings.ts = ts
        settings.put()
    return 'Saved', 201


@app.route('/ask_feedback', methods=['POST', 'OPTIONS'])
def ask_feedback():
    @flask.after_this_request
    def add_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    return '10', 200
    values = flask.request.values
    now = datetime.now()
    try:
        user_id = Session.get_user_id(values['url'])
    except:
        return 'Incorrect user_id used', 400
    settings = ndb.Key(UserSettings, user_id).get()
    if settings is None:
        # Create settings for the current user
        settings = UserSettings(id=user_id, ts=now)
    if settings.mute_deadline is not None and settings.mute_deadline > now:
        return '0', 200
    questionnaire_left = 10
    for prev_shown_ts in reversed(settings.questionnaire_shown_ts):
        if prev_shown_ts < now - timedelta(hours=24):
            break
        questionnaire_left -= 1
    if random.random() < 0.5:
        # Suppress the popup for 50% of all SERPs.
        questionnaire_left = 0
    if questionnaire_left > 0:
        settings.questionnaire_shown_ts.append(now)
        settings.put()
    return str(questionnaire_left), 200


@app.route('/log', methods=['POST', 'OPTIONS'])
def log():
    @flask.after_this_request
    def add_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    values = flask.request.values
    tab_id = values.get('tab_id', '')
    session = ndb.Key(Session, tab_id).get()
    if session is None:
        return 'No sessions with tab_id = %s' % tab_id, 404
    elif session.shared:
        return 'Cannot update previously shared session with tab_id = %s' % tab_id, 403
    try:
        user_id = Session.get_user_id(values['url'])
    except:
        return 'Incorrect user_id used', 400
    if session.user_id != user_id:
        return 'Session does not belong to %s' % user_id, 403
    try:
        if 'buffer' in values:
            buffer = json.loads(values['buffer'])
        else:
            buffer = [flask.request.url.split('?', 1)[-1]]
        actions = []
        for log_str in buffer:
            log_item = urlparse.parse_qs(log_str)
            ts = Session.convert_time(log_item['time'][0])
            event_type = log_item.get('ev', ['UNKNOWN'])[0]
            fields = {k: v[0] for (k, v) in log_item.iteritems() if k not in ['ev', 'time']}
            actions.append(Action(ts=ts, event_type=event_type, fields=fields))
        session.actions += actions
        session.put()
        return 'Updated', 200

    except Exception as e:
        app.logger.error(e)
        app.logger.error('Buffer: %s' % values.get('buffer', ''))
        return 'Incorrect buffer contents', 400

