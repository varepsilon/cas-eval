#!/usr/bin/env python

import collections
import csv
import argparse
import sys

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            description='Remove some items from the task. Removal process is'
                    'controled by queries/labels files or --prev_task')
    parser.add_argument('--queries_file', help='txt file with queries (one per line)')
    parser.add_argument('--labels_file',
            help='txt file with labels (one per line; 1 - keep, 0 - filter out)')
    parser.add_argument('--prev_task', help='csv file with previously judged items',
            action='append')
    parser.add_argument('--task_csv', help='input csv file', required=True)
    parser.add_argument('--spammers',
            help='File with ids of malicious workers (one per line)',
            action='append')
    parser.add_argument('--min_ratings_per_item',
            help='Min ratings that item must have in order not to be sent for more ratings',
            type=int, default=5)
    parser.add_argument('--max_output_items',
            help='Max amount of items to output. Used for batching the tasks on CF.',
            type=int)

    args = parser.parse_args()

    if args.prev_task is None and (args.queries_file is None or args.labels_file is None):
        print >>sys.stderr, 'Either --prev_task or labels/queries files have to be set'
        parser.print_help()
        sys.exit(1)

    query_filter_labels = None
    if args.queries_file is not None and args.labels_file is not None:
        with open(args.queries_file) as q_file:
            with open(args.labels_file) as l_file:
                query_filter_labels = {q.rstrip(): int(l) for (q, l) in zip(q_file, l_file)}

    spammers = set()
    if args.spammers is not None:
        for s_file_name in args.spammers:
            with open(s_file_name) as f:
                for worker_id in f:
                    spammers.add(worker_id.rstrip())

    judged_items = collections.defaultdict(lambda: 0)
    if args.prev_task is not None:
        for fname in args.prev_task:
            with open(fname) as f:
                for row in csv.DictReader(f):
                    if row['_worker_id'] not in spammers:
                        judged_items[row['log_id']] += 1

    num_judged_distribution = collections.Counter()
    with open(args.task_csv) as input:
        num = 0
        reader = csv.DictReader(input)
        writer = csv.DictWriter(sys.stdout, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if query_filter_labels is not None and query_filter_labels[row['query']] != 1:
                continue
            num_judged_items = judged_items[row['log_id']]
            num_judged_distribution[num_judged_items] += 1
            if args.min_ratings_per_item is not None \
                    and num_judged_items >= args.min_ratings_per_item:
                continue
            writer.writerow(row)
            num += 1
            if args.max_output_items is not None and num >= args.max_output_items:
                break

    print >>sys.stderr, 'Judgements per item stats:', num_judged_distribution
