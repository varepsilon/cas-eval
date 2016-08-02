#!/usr/bin/env python

# Read the CSS file line by line and remove rules that only include classes that we are
# not interested in. This is to reduce the size of a CSS file to squeeze it into CrowdFlower.
#
# IMPORTANT! CSS file is assumed to be beutified by http://codebeautify.org/css-beautify-minify.

import sys
from cStringIO import StringIO

def in_selectors(s, selectors):
    return len(s) > 0 and (s[0] + s[1:].split('#')[0].split('.')[0].split(':')[0]) in selectors


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print >>sys.stderr, 'Usage: %s file_with_css_selectors_one_per_line <in >out' % sys.argv[0]
        sys.exit(1)
    with open(sys.argv[1]) as f:
        selectors = set(x.rstrip() for x in f)
    skipping = False
    rules = set([])
    rule = StringIO()
    for line in sys.stdin:
        line = line.rstrip()
        if line == '':
            continue
        elif line == '}':
            if not skipping:
                print >>rule, line
            rules.add(rule.getvalue())
            rule = StringIO()
            skipping = False
        elif not line.startswith('  '):
            # skip the latest two symbols ' {'
            for item in line[:-2].split(','):
                for selector in item.split():
                    if selector.split('#')[0].split('.')[0] == 'li':
                        break
                    # if at least one selector is not in the set, skip the rule
                    idx = selector.find('#')
                    if idx != -1 and not in_selectors(selector[idx:], selectors):
                        break
                    idx = selector.find('.')
                    if idx != -1 and not in_selectors(selector[idx:], selectors):
                        break
                else:
                    # All selectors are OK, so this item is OK and the rule should be kept
                    break
            else:
                skipping = True
                continue
            print >>rule, line
        elif not skipping:
            print >>rule, line
    for rule in rules:
        print rule,

