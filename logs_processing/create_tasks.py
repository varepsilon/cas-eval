#!/usr/bin/env python

import collections
import csv
import glob
import itertools
import json
import jsonpickle
import os
import os.path
import sys

import bs4

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname('__file__'), os.path.pardir)))

from logs_management.shared.logs import parse_href

TMP_DIR = '<YOUR_DIRECTORY_PATH_GOES_HERE>'
DEBUG = True
ONLY_WITH_FEEDBACK = False
ONLY_ASCII_QUERIES = True

# Only include items that have been moused over.
ONLY_HOVERED = False

# Add this prefix to all the log_ids to distinguish from
# the previous runs.
LOG_ID_PREFIX = 'v2_'

DEBUG_HTML_HEADER = """
<!DOCTYPE html>
<html>
<head>
<link rel="stylesheet" href="blocks/style.css">
<style>
.snippet {
  border: 1px solid;
  margin: 5px;
}
ol, ul, li {
    border: 4px;
    margin: 5px;
    padding: 5px;
}
</style>
</head>
<body>
"""

DEBUG_HTML_FOOTER = """
</body>
</html>
"""

def format_snippet_debug(query, descendant, snippet, rank):
    if rank is None:
        rank = -1
    print >>sys.stderr, '<li>'
    print >>sys.stderr, 'Non-link click for [%s]' % query
    print >>sys.stderr, '<ul style="list-style-type:circle">'
    print >>sys.stderr, '<li>Clicked: <div class="snippet">%s</div></li>' % descendant
    print >>sys.stderr, '<li>Full: <ol class="snippet" start="%d">%s</div></ol>' % (rank, snippet)
    print >>sys.stderr, '</ul>'
    print >>sys.stderr, '</li>'


def cleanup_link(node):
    node.attrs.pop('href', None)
    node.attrs.pop('target', None)
    node.attrs.pop('onmousedown', None)


def remove_inline_image(snippet):
    for descendant in snippet.descendants:
        if type(descendant) != bs4.element.Tag:
            continue
        if descendant.name == 'img' and descendant.get('src', '').startswith('data:image/'):
            del descendant['src']
            return True
    return False


Action = collections.namedtuple('Action', ['type', 'ts', 'target', 'rank'])

class LogItem:
    def __init__(self, log_id, actions=None):
        self.log_id = log_id
        self.actions = actions if actions is not None else []
        self.long_click = False
        self.fixation = self.click  # click implies fixation for sure

    @property
    def click(self):
        return any(a.type == 'Click' for a in self.actions)

    def __str__(self):
        if self.long_click:
            prefix = 'lc'
        elif self.click:
            prefix = 'c'
        elif self.fixation:
            prefix = 'f'
        elif len(self.actions) > 0:
            prefix = 'h'
        else:
            return self.log_id
        return '%s [%s]' % (self.log_id, prefix)

    def score(self):
        if self.long_click:
            return 4
        elif self.click:
            return 3
        elif self.fixation:
            return 2
        elif len(self.actions) > 0:
            return 1
        else:
            return 0

    def max_ts(self):
        return 0 if len(self.actions) == 0 else max(a.ts for a in self.actions)

    def __repr__(self):
        return self.__str__()

    def clear_after(self, ts):
        """ Remove all actions after particular timestamp. """
        self.actions = [a for a in self.actions if a.ts <= ts]


class QueryLogProcessor:
    """ A class to update some parameters of LogItem's using the context of other actions. """

    SESSION_CUT_OFF = 30 * 60 * 1000  # 30 mins
    LONG_CLICK_THRESHOLD = 30 * 1000  # 30 seconds
    FIXATION_THRESHOLD = 200  # 200 ms

    def __init__(self):
        self.actions = []
        self.emu_id_to_log_item = {}

    def process(self):
        self.actions.sort(key=lambda x: x['action'].ts)
        enter_times = {}  # log_id -> ts of entering the log item (snippet)
        first_log_item = self.emu_id_to_log_item.get(self.actions[0]['emu_id'])
        if first_log_item is not None:
            enter_times[first_log_item.log_id] = self.actions[0]['action'].ts
        end_timestamp = None
        for i in xrange(1, len(self.actions)):
            cur = self.actions[i]
            prev = self.actions[i - 1]
            # Read corresponding log items (only defined for snippets, otherwise None).
            cur_log_item = self.emu_id_to_log_item.get(cur['emu_id'])
            prev_log_item = self.emu_id_to_log_item.get(prev['emu_id'])
            if cur_log_item != prev_log_item:
                # Transition to a different SERP area.
                if cur_log_item is not None:
                    # This is an incoming transition into a snippet.
                    # Record the time of (re-)entering it.
                    enter_times[cur_log_item.log_id] = cur['action'].ts
                if prev_log_item is not None:
                    # This is an outgoing transition from a snippet.
                    if cur['action'].ts - enter_times[prev_log_item.log_id] \
                            >= self.FIXATION_THRESHOLD:
                        # Within-snippet dwell time is big enough.
                        prev_log_item.fixation = True
                    # TODO: proper way of counting long clicks:
                    #  - record the last click item
                    #  - look for PageHide event
                    #  - measure the time between it and the next event
                    if prev_log_item.click and \
                            cur['action'].ts - prev['action'].ts >= self.LONG_CLICK_THRESHOLD:
                        prev_log_item.long_click = True
            time_to_prev = cur['action'].ts - prev['action'].ts
            if time_to_prev >= self.SESSION_CUT_OFF:
                #print >>sys.stderr, 'Found a really big break between %s and %s: +%d min' % (
                        #prev['action'], cur['action'], time_to_prev / 60000)
                end_timestamp = prev['action'].ts
                break
        if end_timestamp is not None:
            for a in self.actions:
                log_item = self.emu_id_to_log_item.get(a['emu_id'])
                if log_item is not None:
                    log_item.clear_after(end_timestamp)
        else:
            last_log_item = self.emu_id_to_log_item.get(self.actions[-1]['emu_id'])
            if last_log_item is not None:
                # The last item always assumed to be fixated for long.
                last_log_item.fixation = True
                if last_log_item.click:
                    # If it has click, it's considered to be a long click.
                    last_log_item.long_click = True

        #if DEBUG and any(len(l.actions) > 0 and not l.fixation \
                #for l in self.emu_id_to_log_item.itervalues()):
            #for i, a in enumerate(self.actions):
                #delta = a['action'].ts - self.actions[i - 1]['action'].ts if i > 0 else 0
                #emu_id = a['emu_id']
                #print >>sys.stderr, self.emu_id_to_log_item.get(emu_id), emu_id, \
                        #a['action'], '+%d ms' % delta


if __name__ == '__main__':
    print >>sys.stderr, DEBUG_HTML_HEADER
    print >>sys.stderr, '<pre>'
    print >>sys.stderr, 'Usage: %s [previous_results.csv] <search_log.txt >task.csv' % sys.argv[0]
    print >>sys.stderr, ('When supplied, previous results are used to remove all ' +
            'previously judged queries, unless they are test queries.')
    print >>sys.stderr, '</pre>'
    writer = csv.DictWriter(sys.stdout,
            fieldnames=['log_id', 'emu_ids', 'actions', 'sat_feedback', 'query', 'link', 'snippet'])
    print >>sys.stderr, '<ul style="list-style-type:decimal">'
    writer.writeheader()
    interesting_selectors = set()
    styles = set()
    previously_judged_queries = set()
    test_queries = set()
    if len(sys.argv) == 2:
        with open(sys.argv[1]) as results_file:
            for row in csv.DictReader(results_file):
                query = row['query']
                previously_judged_queries.add(query)
                if row['_golden'] == 'true':
                    test_queries.add(query)
    html_files_dumped = False
    for query_num, line in enumerate(sys.stdin):
        try:
            search_log = json.loads(line)
        except ValueError:
            print >>sys.stderr, 'Error reading line %d. Skipping...' % query_num
            continue
        sat_feedback = None
        for a in search_log['actions']:
            if a['event_type'] == 'SatFeedback':
                sat_feedback = a['fields']['val']
                if sat_feedback == 'OTH':
                    sat_feedback += ' (%s)' % a['fields'].get('reason')
                break
        else:
            if ONLY_WITH_FEEDBACK:
                continue
            else:
                sat_feedback = 'absent'
        query = search_log['q']
        if query in test_queries:
            continue
        if DEBUG and not html_files_dumped:
            for f in glob.glob(TMP_DIR + '*.html'):
                os.unlink(f)
            with open(TMP_DIR + 'serp.html', 'w') as f:
                print >>f, search_log['serp_html'].encode('utf-8')
        if ONLY_ASCII_QUERIES and not all(ord(c) < 128 for c in query):
            continue
        if query in previously_judged_queries and query not in test_queries:
            continue
        log_processor = QueryLogProcessor()
        emu_id_to_actions = collections.defaultdict(lambda: [])
        for a in search_log['actions']:
            emu_id = a['fields'].get('emu_id')
            target = None
            if a['event_type'] == 'MMov':
                # This is a mouse-move event, we can safely ignore it
                continue
            elif a['event_type'] == 'Click':
                target = parse_href(a['fields'].get('href'))
            action = Action(type=a['event_type'], ts=a['ts'],
                            target=target, rank=a['fields'].get('rank'))
            emu_id_to_actions[emu_id].append(action)
            log_processor.actions.append({'emu_id': emu_id, 'action': action})

        parsed_html = bs4.BeautifulSoup(search_log['serp_html'], 'html.parser')
        for style in parsed_html.find_all('style'):
            styles.add(unicode(style.string).encode('utf-8'))
        query_rows = []
        for snippet in parsed_html.find_all(
                lambda b: b.name == 'li' and 'g' in b.get('class', [])):
            log_id = LOG_ID_PREFIX + '%d_%s' % (query_num, snippet['emu_id'])
            snippet_emu_ids = []
            snippet_actions = []
            link = None
            rank = None
            for descendant in itertools.chain([snippet], snippet.descendants):
                if type(descendant) != bs4.element.Tag:
                    continue
                if descendant.name == 'script':
                    descendant.clear()
                    continue
                classes = set('.' + c for c in descendant.get('class', []))
                interesting_selectors.update(classes)
                id = descendant.get('id')
                if id is not None:
                    interesting_selectors.add('#' + id)
                cleanup_link(descendant)
                emu_id = descendant['emu_id']
                if (emu_id is not None) and (emu_id in emu_id_to_actions):
                    snippet_emu_ids.append(emu_id)
                    actions = emu_id_to_actions[emu_id]
                    if link is None:
                        for a in actions:
                            if a.target is not None:
                                link = a.target
                                rank = a.rank
                                break
                    if any(a.type == 'Click' for a in actions) and link is None:
                        snippet_actions += [a for a in actions if not a.type == 'Click']
                        if DEBUG:
                            format_snippet_debug(query, descendant, snippet, rank)

                    else:
                        snippet_actions += actions
            if ONLY_HOVERED and len(snippet_actions) == 0:
                continue
            snippet_encoded = snippet.encode('utf-8')
            while len(snippet_encoded) > 60000:
                if not remove_inline_image(snippet):
                    print >>sys.stderr, 'The snippet is too long: ', len(snippet_encoded)
                    # print >>sys.stderr, snippet_encoded
                    break
                snippet_encoded = snippet.encode('utf-8')
            else:
                log_item = LogItem(log_id, snippet_actions)
                for emu_id in snippet_emu_ids:
                    log_processor.emu_id_to_log_item[emu_id] = log_item
                query_rows.append({
                    'query': query.encode('utf-8'),
                    'snippet': snippet_encoded,
                    'link': link,
                    'log_id': log_id,
                    'emu_ids': ' '.join(snippet_emu_ids),
                    'actions': log_item,
                    'sat_feedback': sat_feedback,
                })
                if DEBUG and not html_files_dumped:
                    with open(TMP_DIR + log_id + '.html', 'w') as f:
                        print >>f, snippet.prettify().encode('utf-8')
                    html_files_dumped = True
        # All the data for the query is read, do the processing now.
        log_processor.process()
        for row in query_rows:
            writer.writerow(dict((k, (v if type(v) in [str, unicode] else jsonpickle.encode(v))) \
                    for k, v in row.iteritems()))
    print >>sys.stderr, '</ul>'

    with open(TMP_DIR + 'classes.txt', 'w') as f:
        for c in sorted(interesting_selectors):
            print >>f, c
    print >>sys.stderr, len(styles), 'different stylesheets found'
    print >>sys.stderr, 'Writing style.css to %s' % TMP_DIR
    with open(TMP_DIR + 'style.css', 'w') as f:
        for s in styles:
            print >>f, s

    print >>sys.stderr, DEBUG_HTML_HEADER

