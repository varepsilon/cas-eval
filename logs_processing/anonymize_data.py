#!/usr/bin/env python
#
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
# Anonymize queries, documents and workers to release the data.

import argparse
import bs4
import csv

from fields import orig_query, rel_column


class DynamicIDs:
    ''' Class that dynamically assigns IDs similar to defaultdict '''
    def __init__(self, prefix):
        self.prefix = prefix
        self.id_map = {}
        self.current_num = 0

    def __getitem__(self, w):
        if w in self.id_map:
            return self.id_map[w]
        else:
            cas_worker_id = '%s_%d' % (self.prefix, self.current_num)
            self.current_num += 1
            return self.id_map.setdefault(w, cas_worker_id)


def process_results_file(worker_to_id, query_to_id, in_files, out_file, rel_type):
    with open(out_file, 'w') as results_anonymized:
        results_writer = csv.DictWriter(results_anonymized,
                                          fieldnames=['cas_query_id',
                                                      'cas_log_id',
                                                      'cas_worker_id',
                                                      'cf_worker_trust',
                                                      rel_type])
        results_writer.writeheader()
        for in_file in in_files:
            with open(in_file) as results:
                    for row in csv.DictReader(results):
                        results_writer.writerow({'cas_worker_id': worker_to_id[row['_worker_id']],
                                                 'cf_worker_trust': row['_trust'],
                                                 'cas_query_id': query_to_id[row[orig_query[rel_type]]],
                                                 'cas_log_id': row['log_id'],
                                                 rel_type: row[rel_column[rel_type]],
                                                })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            description='Anonymize queries, documents and workers to release the data.')
    # Input
    parser.add_argument('--serps', help='task_with_SERPs.csv file',
            required=True)
    parser.add_argument('--results_D',
            help='CSV file with results for direct snippet relevance',
            required=True)
    parser.add_argument('--results_AR',
            help='CSV file with results for attractiveness and doc relevance',
            required=True, action='append')
    parser.add_argument('--spammers',
            help='File with ids of malicious workers (one per line)',
            action='append')
    # Output
    parser.add_argument('--out_serps',
            help='File to output the anonymized SERPs and log data',
            default='serps_anonymized.csv')
    parser.add_argument('--out_D',
            help='File to output the anonymized D ratings',
            default='results_D_anonymized.csv')
    parser.add_argument('--out_R',
            help='File to output the anonymized R ratings',
            default='results_R_anonymized.csv')
    parser.add_argument('--out_spammers',
            help='File to output the anonymized list of spammers',
            default='spammers_anonymized.csv')

    args = parser.parse_args()


    worker_to_id = DynamicIDs('w')
    query_to_id = DynamicIDs('q')

    process_results_file(worker_to_id, query_to_id,
                         [args.results_D], args.out_D, 'D')
    process_results_file(worker_to_id, query_to_id,
                         args.results_AR, args.out_R, 'R')

    if args.spammers is not None:
        spammers = set()
        for s_file_name in args.spammers:
            with open(s_file_name) as f:
                for line in f:
                    spammers.add(worker_to_id[line.rstrip()])
        with open(args.out_spammers, 'w') as out_spammers:
            out_spammers.write('\n'.join(spammers))

    classes_to_id = DynamicIDs('c')

    with open(args.serps) as task_file:
        reader = csv.DictReader(task_file)
        with open(args.out_serps, 'w') as serps_out_file:
            output_writer = csv.DictWriter(serps_out_file,
                                           fieldnames=['cas_query_id',
                                                       'cas_log_id',
                                                       'sat_feedback',
                                                       'emup',          # offset data; see third_party/EMU
                                                       'cas_item_type', # item type of this snippet
                                                       'is_complex',    # whether this is a complex snippet,
                                                                        #     i.e., not a regular Web result
                                                       'actions',       # interaction with this snippet
                                                      ])
            output_writer.writeheader()
            for row in reader:
                snippet = bs4.BeautifulSoup(row['snippet'], 'html.parser').li
                classes = frozenset(snippet['class'])
                output_writer.writerow({'cas_query_id': query_to_id[row[orig_query['query']]],
                                        'cas_log_id': row['log_id'],
                                        'sat_feedback': row['sat_feedback'],
                                        'actions': row['actions'],
                                        'emup': snippet['emup'],
                                        'cas_item_type': classes_to_id[classes],
                                        'is_complex': any(c != u'g' for c in classes),
                                        })
    # Verify that we have exactly 10 SERP item types
    assert classes_to_id.current_num == 10

