#!/usr/bin/env python

from collections import defaultdict, namedtuple
import glob
import gzip
import itertools
import math
import pickle
import random
import threading
import sys
from Queue import Queue


try:
  import __pypy__
  USE_PYPY = True
except ImportError:
  USE_PYPY = False

USE_PYPY = True

DETAILED_LOG = False

MAX_MARK = 3

RANK_DEPTH = 10
assert RANK_DEPTH <= 10

#METRICS = ['CAST', 'CASTnoreg', 'CASTnosat', 'CASTnosatnoreg', 'UBM', 'PBM', 'DCG', 'uUBM']
METRICS = ['CAST', 'CASTnoreg', 'CASTnosat', 'CASTnosatnoreg']


################################################################################
# Params used in uUBM metric in
# Chuklin, A., Serdyukov, P., & de Rijke, M. (2013).
# Click model-based information retrieval metrics. In SIGIR (pp. 493--502)
# http://doi.org/10.1145/2484028.2484071
UBM_GAMMAS = """
0.0000  0.0000  0.0000  0.0000  0.0000  0.0000  0.0000  0.0000  0.0000  1.0000
0.0000  0.0000  0.0000  0.0000  0.0000  0.0000  0.0000  0.0000  0.6980  0.0029
0.0000  0.0000  0.0000  0.0000  0.0000  0.0000  0.0000  0.6483  0.0023  0.0106
0.0000  0.0000  0.0000  0.0000  0.0000  0.0000  0.5461  0.0032  0.0082  0.0263
0.0000  0.0000  0.0000  0.0000  0.0000  0.5747  0.0042  0.0101  0.0215  0.0305
0.0000  0.0000  0.0000  0.0000  0.4816  0.0067  0.0179  0.0280  0.0303  0.0599
0.0000  0.0000  0.0000  0.5670  0.0099  0.0248  0.0476  0.0434  0.0620  0.0917
0.0000  0.0000  0.5410  0.0187  0.0426  0.0716  0.0713  0.0826  0.0813  0.1518
0.0000  0.8951  0.0331  0.0794  0.1242  0.1210  0.1449  0.1268  0.1559  0.1901
0.9921  0.1199  0.2395  0.3230  0.3004  0.3107  0.3018  0.3212  0.3221  0.4149
"""

gammas = [[0.0 for j in xrange(10)] for k in xrange(10)]

m = 0
for line in UBM_GAMMAS.split('\n'):
    line = line.strip()
    if not line:
        continue
    n = 0
    for item in line.split():
        if not item:
            continue
        if n + m >= 9:
            gammas[n][n + m - 9] = float(item)
        n += 1
    m += 1

UBM_GAMMAS = gammas
del gammas


UBM_RELS = """
IRRELEVANT      0.491912
RELEVANT        0.570803
USEFUL  0.695883
VITAL   0.931482
"""

UBM_RELS = [float(x.split()[-1]) for x in UBM_RELS.split('\n') if x]
assert len(UBM_RELS) == MAX_MARK + 1

################################################################################

def markToIntRel(mark):
    mark = int(mark)
    if mark == -2:
        mark = 0
    return mark


def markToRelDcg(mark):
    mark = markToIntRel(mark)
    assert mark in range(MAX_MARK + 1), '%d not in %s' % (mark, str(range(MAX_MARK + 1)))
    return (2 ** float(mark) - 1) / (2 ** MAX_MARK)


def markToRelUbm(mark):
    mark = markToIntRel(mark)
    return UBM_RELS[mark]


def avg(l):
    s = 0.0; n = 0
    for x in l:
        s += x; n += 1
    return float(s) / n if n else 0.0


def prod(l):
    return math.exp(sum(math.log(x) for x in l))


def frac(x, y):
    if x == 0:
        return 0.0
    if y == 0:
        return float('inf')
    else:
        return float(x) / y


def systemName(fileName):
    return fileName.split('/')[-1].split('.', 1)[-1]


# decorator
def intent_aware(func):
    def func1(rels, doc_list):
        intents = rels.keys()
        N = len(intents)
        # we use equal topical distribution
        return sum(func(rels[i], doc_list) for i in intents) / N if N else 0
    return func1
# end decorator


def __DCG(rels, doc_list):
    return sum(float(markToRelDcg(rels[doc])) / math.log(k + 2, 2) for (k, doc) in enumerate(doc_list[:RANK_DEPTH]))

DCG = intent_aware(__DCG)

@intent_aware
def uUBM(rels, doc_list):
    p = [1.0]
    s = 0.0
    alpha = [markToRelUbm(rels[doc]) for doc in doc_list[:RANK_DEPTH]]
    for rank, doc in enumerate(doc_list[:RANK_DEPTH]):
        p.append(alpha[rank] * sum(p[j] * UBM_GAMMAS[rank][j] * prod((1 - alpha[k] * UBM_GAMMAS[k][j]) for k in xrange(j, rank)) for j in xrange(rank + 1)))
        s += p[-1] * markToRelDcg(rels[doc])
    return s


############################### CAS paper ############################################
from pyclick.click_models.PBM import PBM as pyclick_PBM
from pyclick.click_models.UBM import UBM as pyclick_UBM

import click_model
import create_tasks

assert click_model.RelContainer.grades_R == MAX_MARK + 1

class MarkToIntRelDict(dict):
    def __missing__(self, key):
        rel = click_model.RelContainer()
        rel.Rs.append((markToIntRel(key), 1))
        return rel
MARK_TO_INT_REL_DICT = MarkToIntRelDict()


FAKE_SERP = [{'emup': '372;16;842;496;147', 'class': [u'g']} for i in xrange(RANK_DEPTH)]
def CASModelFromFile(fname, use_sat=True):
    with open(fname) as f:
        _CAS_params = pickle.load(f)
    _CAS = click_model.CAS(MARK_TO_INT_REL_DICT, use_D=False, trec_style=True, sat_term_weight=1 if use_sat else 0)
    def metric(rels, doc_list):
        session = [create_tasks.LogItem(rels[doc]) for doc in doc_list[:RANK_DEPTH]]
        return _CAS.utility(_CAS_params, session, FAKE_SERP)
    return intent_aware(metric)

CAST = CASModelFromFile('CAST.params')
CASTnoreg = CASModelFromFile('CASTnoreg.params')
CASTnosat = CASModelFromFile('CASTnosat.params')
CASTnosatnoreg = CASModelFromFile('CASTnosatnoreg.params')


def pyclick_params_to_model(model_class, params):
    model = model_class()
    model.params = {model.param_names.attr: params['attr'], model.param_names.exam: params['exam']}
    return model

with open('UBM.params') as f:
    _UBM_pyclick_model = pyclick_params_to_model(pyclick_UBM, pickle.load(f))
_UBM = click_model.PyClickModel('UBM', MARK_TO_INT_REL_DICT)
@intent_aware
def UBM(rels, doc_list):
    session = [create_tasks.LogItem(rels[doc]) for doc in doc_list[:RANK_DEPTH]]
    return _UBM.utility(_UBM_pyclick_model, session, FAKE_SERP)

with open('PBM.params') as f:
    _PBM_pyclick_model = pyclick_params_to_model(pyclick_PBM, pickle.load(f))
_PBM = click_model.PyClickModel('PBM', MARK_TO_INT_REL_DICT)
@intent_aware
def PBM(rels, doc_list):
    session = [create_tasks.LogItem(rels[doc]) for doc in doc_list[:RANK_DEPTH]]
    return _PBM.utility(_PBM_pyclick_model, session, FAKE_SERP)

############################### CAS paper end ############################################

def ASL(x, y, nsamples=1000):
    """ Compute achieved significance level (ASL).
            x -- vector of metric values for sytem X
            y -- vector of metric values for sytem Y
        [1] Sakai, T. 2006. Evaluating evaluation metrics based on the bootstrap. SIGIR 2006
    """
    n = len(x)
    assert n == len(y)

    def t(a):
        aBar = avg(a)
        aSigma = math.sqrt(sum(1.0 / (n - 1) * (a1 - aBar) ** 2 for a1 in a))
        return frac(aBar, aSigma) * math.sqrt(n)

    z = [p[0] - p[1] for p in zip(x, y)]
    tZ = abs(t(z))
    zBar = avg(z)
    w = [z1 - zBar for z1 in z]
    count = 0
    for b in xrange(nsamples):
        wStar = [random.choice(w) for i in xrange(n)]
        if abs(t(wStar)) >= tZ:
            count += 1
    return float(count) / nsamples


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print >>sys.stderr, 'Usage: {0:s} qrels_file directory_with_trec_results'.format(sys.argv[0])
        sys.exit(1)

    random.seed()

    # rels[query_id][intent_id][document_id]
    rels = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: 0.0)))
    with open(sys.argv[1]) as f:
        for line in f:
            query_id, topic_id, document_id, mark = line.rstrip().split()
            rels[query_id][topic_id][document_id] = mark

    inputFiles = glob.glob('{0:s}/input.*.gz'.format(sys.argv[2]))
    metricRanks = defaultdict(lambda: [])   # metric_name -> avg system scores (for all systems)
    metricRanksDetailed = defaultdict(lambda: [])   # metric_name -> system_num -> query_id -> score
    for filename in inputFiles:
        with gzip.open(filename) as f:
            #           query_id  doc_ids
            #               |       |
            #               |       |
            #               v       v
            rankings = [(query_id, [l.split()[2] for l in lines]) for (query_id, lines) \
                    in itertools.groupby((l for l in f if l.rstrip()), key=lambda line: line.split()[0])]
            for m in METRICS:
                metricFunction = globals()[m]
                ranks = [metricFunction(rels[l[0]], l[1]) for l in rankings]
                metricRanks[m].append(avg(ranks))
                # print [x[0] for x in rankings] #       <----   we assume that query order is the same for all systems
                metricRanksDetailed[m].append(ranks)

    #print >>sys.stderr, '\t'.join(str(avg(c[i] for c in EBU_CLICK_PROBS)) for i in xrange(RANK_DEPTH))
    print >>sys.stderr, 'Finish reading the data'

    if USE_PYPY:
        # This branch would be too slow w/o PyPy
        nSystems = len(inputFiles)
        taskQueue = Queue()
        resultQueue = Queue()

        def calcDiscPower():
            m1 = taskQueue.get()
            detailedRanks = metricRanksDetailed[m1]
            differ = 0
            count = 0
            if DETAILED_LOG:
                logFile = open('logs/' + m1 + '.log', 'w')
            for i in xrange(nSystems):
                for j in xrange(i + 1, nSystems):
                    s1 = detailedRanks[i]
                    s2 = detailedRanks[j]
                    if s1 == s2:
                        continue
                    asl = ASL(s1, s2)
                    if asl < 0.05:
                        differ += 1
                    elif DETAILED_LOG:
                        print >>logFile, 'COLLISION:', m1, 'ASL:', asl, \
                            '{0:s} ({1:f})'.format(systemName(inputFiles[i]), metricRanks[m1][i]), \
                            '{0:s} ({1:f})'.format(systemName(inputFiles[j]), metricRanks[m1][j])
                    count += 1
            if DETAILED_LOG:
                logFile.close()
            resultQueue.put('discriminative_power({0:s}) = {1:f}'.format(m1, float(differ) / count))

        workers = []
        for m in METRICS:
            taskQueue.put(m)
            t = threading.Thread(target=calcDiscPower)
            workers.append(t)
            t.start()

        for w in workers:
            w.join()
            print >>sys.stderr, resultQueue.get()
    else:
        # We can't import these w/ PyPy
        import scipy
        import scipy.stats
        print '\\begin{{tabular}}{{{0:s}}}'.format(''.join('c' for m in xrange(len(METRICS))))
        print '\\toprule'
        print '\t&\t'.join([''] + METRICS[1:]) + '\t\\\\'
        print '\\midrule'
        for i in xrange(len(METRICS) - 1):
            vals = ['---' for x in xrange(i)]
            m_i = METRICS[i]
            for j in xrange(i + 1, len(METRICS)):
                m_j = METRICS[j]
                v = scipy.stats.stats.kendalltau(metricRanks[m_i], metricRanks[m_j])[0]
                vals.append('{0:.3f}'.format(v) if v < 0.9 else '\\textbf{{{0:.3f}}}'.format(v))
            print '\t&\t'.join([m_i] + vals) + '\t\\\\'
        print '\\bottomrule'
        print '\\end{tabular}'

