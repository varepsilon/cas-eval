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
# Run the processing of the data. Similar to data_analysis/Results.ipynb,
# but can run without Jupyter notebook server.

from __future__ import division

from abc import ABCMeta, abstractmethod
import argparse
import bs4
import collections
import csv
import itertools
import jsonpickle
import math
import multiprocessing
import pandas as pd
import sys

import numpy as np
import scipy.optimize
import scipy.stats
import sklearn.cross_validation

from pyclick.click_models.PBM import PBM as pyclick_PBM
from pyclick.click_models.UBM import UBM as pyclick_UBM
from pyclick.search_session.SearchResult import SearchResult as pyclick_SearchResult
from pyclick.search_session.SearchSession import SearchSession as pyclick_SearchSession

from create_tasks import Action, LogItem
from fields import orig_query, rel_column


DEBUG = False
USE_CF_TRUST = True


def prod(l):
    return math.exp(sum(math.log(x) for x in l))

class PrettyFloat(float):
    def __repr__(self):
        return "%.2f" % self


def parse_sat(sat_feedback):
    if sat_feedback == 'SAT':
        return True
    elif sat_feedback == 'DSAT':
        return False
    return None


def parse_relevance_rating(rel, offset=1):
    if len(rel) == 0:
        return None
    try:
        int_rel = int(rel[offset:])
    except ValueError:
        print >>sys.stderr, 'Incorrect relevance:', rel
        return None
    return int_rel if int_rel >= 0 else None


# Distribution of ratings for all the items.
D_dist = np.array([0.5, 0.3, 0.2])
R_dist = np.array([0.1, 0.1, 0.3, 0.5])


def rel_dist(ratings, rel_aspect, trec_style=False):
    """ Convert list of ratings to a row of features.
        If trec_style is set to true consider only one rating (the most common one).
    """
    assert (rel_aspect in ['D', 'R']), rel_aspect
    num_bins = RelContainer.grades_D if rel_aspect == 'D' else RelContainer.grades_R
    row = np.zeros(num_bins)
    if trec_style:
        row[rel_most_common(ratings)] = 1
        return row
    if len(ratings) == 0:
        return D_dist if rel_aspect == 'D' else R_dist
    for r in ratings:
        row[r[0]] += r[1]
    return row / row.sum()


def rel_most_common(ratings):
    """ Return the most common relevance label assigned by the raters. """
    if len(ratings) == 0:
        return 0
    counter = collections.defaultdict(lambda: 0)
    for r in ratings:
        counter[r[0]] += 1
    return max(counter.iteritems(), key=lambda p: p[1])[0]


def rel_avg(ratings):
    """ Average of the ratings. """
    N = len(ratings)
    if N == 0:
        return 0
    # TODO: try weighted average
    return sum(r[0] for r in ratings) / N


def sigma(x):
    if x > 0:
        return 1 / (1 + math.exp(-x))
    else:
        return math.exp(x - math.log(1 + math.exp(x)))


class RelContainer:
    """ All the labels assigned by the crowd workers to a query-doc pair.

        Since different raters can assign different relevance labels,
            each relevance param is a list
    """

    grades_D = 3    # 0, 1, 2
    grades_R = 4    # 0, 1, 2, 3

    def __init__(self):
        self.Ds = []
        self.Rs = []

    @staticmethod
    def _format_rel(rel):
        return ''.join(str(x[0]) for x in rel)

    def __str__(self):
        return 'Rel(D=%s, R=%s)' % (
            self._format_rel(self.Ds),
            self._format_rel(self.Rs),
        )

    def __repr__(self):
        return self.__str__()

    @staticmethod
    def add_rel(container, rel, trust):
        rel = parse_relevance_rating(rel)
        if rel is not None:
            container.append((rel, trust))

    def __nonzero__(self):
        return len(self.Ds) > 0 and len(self.Rs) > 0


SNIPPET_CLASSES = [
    frozenset([u'g']),
    frozenset([u'_oqc', u'g']),
    frozenset([u'g', u'g-blk', u'kno-kp', u'mnr-c']),
    frozenset([u'g', u'g-blk', u'mnr-c', u'rhsvw']),
    frozenset([u'g', u'g-blk', u'kno-kp', u'mnr-c', u'rhsvw']),
    frozenset([u'g',
            u'g-blk',
            u'kno-fb-suppressed',
            u'kno-kp',
            u'mnr-c',
            u'rhsvw']),
    frozenset([u'_Nn', u'_wbb', u'card-section', u'g']),
    frozenset([u'_df', u'_mZd', u'card-section', u'g']),
    frozenset([u'_Abb', u'_Nn', u'card-section', u'g']),
    frozenset([u'currency', u'g', u'obcontainer', u'vk_c'])
]


# Reserve one feature for the intercept.
CLASSES_TO_FEATURE_NUM = dict((c, 2 + k) for k, c in enumerate(SNIPPET_CLASSES))


MAX_OFFSET_TOP = 1869
MIN_WIDTH = 338
MAX_WIDTH = 539
MIN_HEIGHT = 33
MAX_HEIGHT = 896


LogLikelihood = collections.namedtuple('LogLikelihood', ['full',
                                                         'gaussian',
                                                         'clicks',
                                                         'sat']
)


class UserModel:
    __metaclass__ = ABCMeta

    @abstractmethod
    def train(self, data):
        pass

    @abstractmethod
    def log_likelihood(self, p, session, serp, sat, f_only=False):
        pass

    @abstractmethod
    def utility(self, p, session, serp):
        pass


class RandomSatModel(UserModel):
    def train(self, data):
        """ Return optimal model params """
        num_sat = sum(1 for d in data if d['sat'])
        p_sat = num_sat / len(data)

        num_clicked = sum(sum(1 for l in d['session'] if l.click) for d in data)
        num_results = sum(sum(1 for l in d['session']) for d in data)
        p_click = num_clicked / num_results
        return p_click, p_sat

    def log_likelihood(self, p, session, serp, sat, f_only=False):
        assert f_only
        p_click, p_sat = p
        ll_click = 0
        for l in session:
            ll_click += math.log(p_click if l.click else (1 - p_click))
        ll_sat = math.log(p_sat if sat else (1 - p_sat))
        ll_full = ll_click + ll_sat
        return LogLikelihood(full=ll_full,
                             gaussian=float('NaN'),
                             clicks=ll_click,
                             sat=ll_sat)

    def utility(self, p, session, serp):
        p_click, p_sat = p
        return p_sat


class PyClickModel(UserModel):
    def __init__(self, model_name, log_id_to_rel):
        self.model_name = model_name
        self.log_id_to_rel = log_id_to_rel

    def train(self, data):
        train_sessions = []
        for d in data:
            train_sessions.append(self._to_pyclick_session(d['session']))
        pyclick_model = globals()['pyclick_%s' % self.model_name]()
        pyclick_model.train(train_sessions)
        return pyclick_model

    def log_likelihood(self, pyclick_model, session, serp, sat, f_only=False):
        assert f_only
        click_probs = pyclick_model.get_conditional_click_probs(
                self._to_pyclick_session(session))
        ll_click = sum(math.log(prob) for prob in click_probs)

        rel_vector = np.array([
                rel_most_common(self.log_id_to_rel[log_item.log_id].Rs) \
                    for log_item in session
        ])
        p_sat = sigma(rel_vector.dot(click_probs))
        ll_sat = math.log(p_sat if sat else (1 - p_sat))
        ll_full = ll_click + ll_sat
        return LogLikelihood(full=ll_full,
                             gaussian=float('NaN'),
                             clicks=ll_click,
                             sat=ll_sat)

    def utility(self, pyclick_model, session, serp):
        rel_vector = np.array([
                rel_most_common(self.log_id_to_rel[log_item.log_id].Rs) \
                    for log_item in session
        ])
        click_probs = np.array(pyclick_model.get_full_click_probs(
                self._to_pyclick_session(session)))
        return rel_vector.dot(click_probs)

    def _to_pyclick_session(self, session):
        pyclick_session = pyclick_SearchSession('dummy_query')
        for log_item in session:
            doc_id = rel_most_common(self.log_id_to_rel[log_item.log_id].Rs)
            pyclick_session.web_results.append(
                pyclick_SearchResult(doc_id, log_item.click))
        return pyclick_session


class DCG(UserModel):
    def __init__(self, log_id_to_rel):
        self.log_id_to_rel = log_id_to_rel

    def train(self, data):
        pass

    def log_likelihood(self, unused, session, serp, sat, f_only=False):
        # Interpret discounts as click probabilities
        N = len(session)
        discount = self._discount(N)
        ll_click = 0
        for l, d in zip(session, discount):
            if d == 1 and not l.click:
                ll_click = float("-inf")
                break
            ll_click += math.log(d if l.click else (1 - d))

        utility = self.utility(unused, session, serp)
        p_sat = sigma(utility)
        ll_sat = math.log(p_sat if sat else (1 - p_sat))
        ll_full = ll_click + ll_sat
        return LogLikelihood(full=ll_full,
                             gaussian=float('NaN'),
                             clicks=ll_click,
                             sat=ll_sat)

    @staticmethod
    def _discount(N):
        d = np.zeros(N)
        for rank in xrange(N):
            d[rank] = 1 / math.log(2 + rank, 2)
        return d

    def utility(self, _, session, serp):
        rel_vector = np.array([
            2 ** rel_most_common(self.log_id_to_rel[log_item.log_id].Rs) - 1\
                for log_item in session
        ])
        N = len(session)
        discount = self._discount(N)
        return rel_vector.dot(discount)

################################################################################
# Params used in uUBM metric in
# Chuklin, A., Serdyukov, P., & de Rijke, M. (2013).
# Click model-based information retrieval metrics. In SIGIR (pp. 493--502).
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


class uUBM(UserModel):
    def __init__(self, log_id_to_rel):
        self.log_id_to_rel = log_id_to_rel

    def train(self, data):
        pass

    def log_likelihood(self, unused, session, serp, sat, f_only=False):
        ll_click = 0
        prev_click_rank = -1
        for rank, log_item in enumerate(session[:10]):
            a = UBM_RELS[rel_most_common(self.log_id_to_rel[log_item.log_id].Rs)]
            p_click = a * UBM_GAMMAS[rank][prev_click_rank + 1]
            if log_item.click:
                prev_click_rank = rank
                ll_click += math.log(p_click)
            else:
                ll_click += math.log(1 - p_click)

        return LogLikelihood(full=float('NaN'),
                             gaussian=float('NaN'),
                             clicks=ll_click,
                             sat=float('NaN'))

    def utility(self, _, session, serp):
        p = [1.0]
        utility = 0.0
        alpha = [UBM_RELS[rel_most_common(self.log_id_to_rel[l.log_id].Rs)] for l in session[:10]]
        for rank, l in enumerate(session[:10]):
            p.append(alpha[rank] * sum(
                    p[j] * UBM_GAMMAS[rank][j] *
                        prod((1 - alpha[k] * UBM_GAMMAS[k][j]) for k in xrange(j, rank)) for j in xrange(rank + 1)))
            utility += p[-1] * rel_most_common(self.log_id_to_rel[l.log_id].Rs)
        return utility

################################################################################

class CAS(UserModel):
    num_features_epsilon = 1 + len(SNIPPET_CLASSES) + 1 + 5               # 0'th coefficient is intercept
    num_features_alpha = 1 + RelContainer.grades_R                        # 0'th coefficient is intercept
    num_tau_D = RelContainer.grades_D
    num_tau_R = RelContainer.grades_R

    num_features = num_features_epsilon + num_features_alpha + 1 + num_tau_D + num_tau_R

    def __init__(self, log_id_to_rel, reg_coeff=1, sat_term_weight=1, use_D=True,
                 use_class=True, use_geometry=True, trec_style=False):
        self.log_id_to_rel = log_id_to_rel
        self.reg_coeff = reg_coeff
        self.sat_term_weight = sat_term_weight
        self.use_D = use_D
        self.use_class = use_class
        self.use_geometry = use_geometry
        self.trec_style = trec_style

    @classmethod
    def weight_epsilon(cls, params):
        return params[:cls.num_features_epsilon]

    @classmethod
    def weight_alpha(cls, params):
        begin = cls.num_features_epsilon
        end = begin + cls.num_features_alpha
        return params[begin:end]

    @classmethod
    def tau_0(cls, params):
        begin = cls.num_features_epsilon + cls.num_features_alpha
        end = begin + 1
        return params[begin:end]

    @classmethod
    def tau_D(cls, params):
        begin = cls.num_features_epsilon + cls.num_features_alpha + 1
        end = begin + cls.num_tau_D
        return params[begin:end]

    @classmethod
    def tau_R(cls, params):
        begin = cls.num_features_epsilon + cls.num_features_alpha + 1 + cls.num_tau_D
        end = begin + cls.num_tau_R
        return params[begin:end]

    def regularization_weight(self):
        # Here we assume that a SERP has roughly 10 documents
        # and thus weigh regularization of w_e and w_a accordingly
        if self.trec_style:
            w_e = np.zeros(self.num_features_epsilon)
            w_e[1] = 1
        else:
            w_e = np.ones(self.num_features_epsilon)
            if not self.use_class:
                for idx in xrange(2, 2 + len(SNIPPET_CLASSES)):
                    w_e[idx] = 0
            if not self.use_geometry:
                for idx in xrange(2 + len(SNIPPET_CLASSES), self.num_features_epsilon):
                    w_e[idx] = 0

        w_a = np.ones(self.num_features_alpha)

        tau_size = 1 + self.num_tau_D + self.num_tau_R
        tau = np.zeros(tau_size) if self.sat_term_weight == 0 else np.ones(tau_size) / 10

        # Make sure we don't regularize the intercept
        w_e[0] = 0
        w_a[0] = 0
        tau[0] = 0
        return np.concatenate([w_e, w_a, tau])

    @classmethod
    def bounds(cls):
        bounds_e = [(None, None)] * cls.num_features_epsilon
        bounds_e[1] = (None, 0)  # Examination cannot grow with rank.

        bounds_a = [(None, None)] * cls.num_features_alpha
        bounds_a[-1] = (0, None) # Highest relevance should imply click.

        # Highest relevance should increase utility / satisfaction prob.
        bounds_tau = ([(None, None)] + [(None, None), (None, None), (0, None)] +
            [(None, None), (None, None), (None, None), (0, None)])
        return bounds_e + bounds_a + bounds_tau

    @classmethod
    def initial_guess(cls):
        theta_e = np.ones(cls.num_features_epsilon)
        theta_e[1] = -1

        theta_a = -1 * np.ones(cls.num_features_alpha)
        theta_a[0] = 1
        theta_a[-1] = 1

        tau_0 = 1
        tau_d = -1 * np.ones(cls.num_tau_D)
        tau_d[-1] = 1
        tau_r = -1 * np.ones(cls.num_tau_R)
        tau_r[-1] = 1

        return np.concatenate([theta_e, theta_a, [tau_0], tau_d, tau_r])

    def _exam_features(self, rank, snippet, second_column):
        # TODO: think about smarter feature regularization or normalization.
        features = np.zeros(self.num_features_epsilon)
        features[0] = 1  # intercept feature
        features[1] = (1 + rank) / 10

        if not self.trec_style:
            if self.use_class:
                classes = frozenset(snippet['class'])
                features[CLASSES_TO_FEATURE_NUM[classes]] = 1
            if self.use_geometry:
                geom_features_start_index = 2 + len(SNIPPET_CLASSES)
                _, _, offset_top, width, height = [int(d) for d in snippet['emup'].split(';')]
                features[geom_features_start_index] = 1 if second_column else 0
                features[geom_features_start_index + 1] = offset_top / MAX_OFFSET_TOP
                features[geom_features_start_index + 2] = (width - MIN_WIDTH) / (MAX_WIDTH - MIN_WIDTH)
                features[geom_features_start_index + 3] = (height - MIN_HEIGHT) / (MAX_HEIGHT - MIN_HEIGHT)
                features[geom_features_start_index + 4] = (
                        (width * height - MIN_WIDTH * MIN_HEIGHT) / (MAX_WIDTH * MAX_HEIGHT - MIN_WIDTH * MIN_HEIGHT)
                )
                assert geom_features_start_index + 4 == self.num_features_epsilon - 1
        return features

    def _exam_features_serp(self, session, serp):
        """ Compute exam features for the whole serp/session. """
        rank = 0
        # Track emu_id's of the "offset parents" to identify which column the snippet is located in.
        # "offset parent" is a reference DOM elements used to specify offset. See third_party/EMU
        offset_parent_set = set()
        exam_features = []
        for log_item, snippet in zip(session, serp):
            offset_parent = snippet['emup'].split(';')[0]
            new_column = offset_parent_set and (offset_parent not in offset_parent_set)
            offset_parent_set.add(offset_parent)
            assert len(offset_parent_set) <= 2, (serp, session)
            if new_column:
                # Reset the rank
                rank = 0
            exam_features.append(self._exam_features(rank, snippet, new_column))
            rank += 1
        return exam_features

    @staticmethod
    def _attr_features(rels, trec_style=False):
        # Start with 1 to account for intercept.
        return np.concatenate([[1], rel_dist(rels, 'R', trec_style)])

    def _exam(self, params, features):
        return sigma(self.weight_epsilon(params).dot(features))

    @classmethod
    def _attr(cls, params, features):
        return sigma(cls.weight_alpha(params).dot(features))

    def utility(self, params, session, serp):
        tau_D = self.tau_D(params)
        tau_R = self.tau_R(params)
        exam_features = self._exam_features_serp(session, serp)

        utility = 0
        for i, log_item in enumerate(session):
            epsilon_f = exam_features[i]
            epsilon = self._exam(params, epsilon_f)

            rels = self.log_id_to_rel[log_item.log_id]
            alpha_f = self._attr_features(rels.Rs, self.trec_style)
            alpha = self._attr(params, alpha_f)
            if self.sat_term_weight == 0:
                utility += epsilon * ((rel_most_common(rels.Ds) if self.use_D else 0) +
                                      alpha * rel_most_common(rels.Rs))
            else:
                tau_f_D = rel_dist(rels.Ds, 'D', self.trec_style) if self.use_D else np.zeros(RelContainer.grades_D)
                tau_f_R = rel_dist(rels.Rs, 'R', self.trec_style)
                utility += epsilon * (tau_D.dot(tau_f_D) + alpha * tau_R.dot(tau_f_R))
        return utility


    def log_likelihood(self, params, session, serp, sat, f_only=False):
        """ Compute log-likelihood of a single session and gradient thereof
            (unless f_only == True).
        """
        tau_0 = self.tau_0(params)
        tau_D = self.tau_D(params)
        tau_R = self.tau_R(params)
        exam_features = self._exam_features_serp(session, serp)

        ll = 0
        click_ll = 0
        f_epsilon_ll_prime = np.zeros(self.num_features_epsilon)
        f_alpha_ll_prime = np.zeros(self.num_features_alpha)
        f_tau_0_ll_prime = 0
        f_tau_D_ll_prime = np.zeros(self.num_tau_D)
        f_tau_R_ll_prime = np.zeros(self.num_tau_R)
        utility = 0
        for i, log_item in enumerate(session):
            epsilon_f = exam_features[i]
            epsilon = self._exam(params, epsilon_f)

            rels = self.log_id_to_rel[log_item.log_id]
            alpha_f = self._attr_features(rels.Rs, self.trec_style)
            alpha = self._attr(params, alpha_f)

            tau_f_D = rel_dist(rels.Ds, 'D', self.trec_style) if self.use_D else np.zeros(RelContainer.grades_D)
            tau_f_R = rel_dist(rels.Rs, 'R', self.trec_style)

            if log_item.fixation:
                ll += math.log(epsilon)
                utility += tau_D.dot(tau_f_D)
                f_epsilon_ll_prime += (1 - epsilon) * epsilon_f
                if log_item.click:
                    ll += math.log(alpha)
                    click_ll += math.log(epsilon) + math.log(alpha)
                    utility += tau_R.dot(tau_f_R)
                    f_alpha_ll_prime += (1 - alpha) * alpha_f
                else:
                    ll += math.log(1 - alpha)
                    click_ll += math.log(1 - epsilon * alpha)
                    f_alpha_ll_prime += -alpha * alpha_f
            else:
                # We don't actually know if there was an examination or not.

                # TODO: use the info that some snippets were
                # beyond the fold and therefore could not be examined.
                utility += epsilon * tau_D.dot(tau_f_D)
                if log_item.click:
                    ll += math.log(epsilon) + math.log(alpha)
                    click_ll += math.log(epsilon) + math.log(alpha)
                    utility += tau_R.dot(tau_f_R)
                    f_epsilon_ll_prime += (1 - epsilon) * epsilon_f
                    f_alpha_ll_prime += (1 - alpha) * alpha_f
                else:
                    ll += math.log(1 - epsilon * alpha)
                    click_ll += math.log(1 - epsilon * alpha)
                    f_epsilon_ll_prime += (1 - epsilon) * epsilon * alpha / (epsilon * alpha - 1) * epsilon_f
                    f_alpha_ll_prime += (1 - alpha) * epsilon * alpha / (epsilon * alpha - 1) * alpha_f

        # Finally, the satisfaction term in the likelihood.
        sat_prob = sigma(tau_0 + utility)
        sat_ll = math.log(sat_prob if sat else (1 - sat_prob))
        # TODO: make this term weighted / optimize separately (multi-objective).
        ll += self.sat_term_weight * sat_ll
        if f_only:
            # A shortcut to avoid extra loop when it's not needed.
            return LogLikelihood(full=ll,
                                 gaussian=None,
                                 clicks=click_ll,
                                 sat=sat_ll)

        # Now compute the contribution of the satisfaction term.
        # Compute the derivative of the sat term: log P(S = sat)
        d_sat_term_d_U = self.sat_term_weight * ((1 - sat_prob) if sat else (-sat_prob))
        f_tau_0_ll_prime += d_sat_term_d_U
        for i, log_item in enumerate(session):
            epsilon_f = exam_features[i]
            epsilon = self._exam(params, epsilon_f)

            rels = self.log_id_to_rel[log_item.log_id]
            tau_f_D = rel_dist(rels.Ds, 'D', self.trec_style) if self.use_D else np.zeros(RelContainer.grades_D)
            tau_f_R = rel_dist(rels.Rs, 'R', self.trec_style)

            if not log_item.fixation:
                f_epsilon_ll_prime += (
                        d_sat_term_d_U * tau_D.dot(tau_f_D) *  # <-- d_sat_term_d_epsilon
                        epsilon * (1 - epsilon) * epsilon_f
                )
                f_tau_D_ll_prime += d_sat_term_d_U * epsilon * tau_f_D
            if log_item.click:
                f_tau_R_ll_prime += d_sat_term_d_U * tau_f_R

        gaussian = np.concatenate([
            f_epsilon_ll_prime,
            f_alpha_ll_prime,
            [f_tau_0_ll_prime],
            f_tau_D_ll_prime,
            f_tau_R_ll_prime,
        ])
        return LogLikelihood(full=ll,
                             gaussian=gaussian,
                             clicks=click_ll,
                             sat=sat_ll)

    def train(self, data):
        reg_weight = self.regularization_weight()

        def f(theta):
            ll = 0
            for d in data:
                session = d['session']
                if DEBUG:
                    assert len(session) > 5
                    assert len(session) < 15
                ll += self.log_likelihood(theta, session, d['serp'], d['sat'], f_only=True).full
            N = len(data)
            reg_term = 0.5 * self.reg_coeff / N * np.multiply(reg_weight, theta).dot(theta)
            if DEBUG:
                self.debug_theta(theta)
                print 'mean LL = %f, reg_term = %f, N = %d' % (ll/N, reg_term, N)
            return -ll / N + reg_term

        def fprime(theta):
            ll_prime = np.zeros(self.num_features)
            for d in data:
                ll_prime += self.log_likelihood(theta, d['session'], d['serp'], d['sat']).gaussian
            N = len(data)
            return -ll_prime / N + self.reg_coeff / N * np.multiply(reg_weight, theta)

        theta0 = self.initial_guess()
        opt_res = scipy.optimize.minimize(f, theta0, method='L-BFGS-B', jac=fprime, options=dict(maxiter=100))
        return opt_res.x

    @classmethod
    def debug_theta(cls, theta):
        print '-' * 80
        epsilon = cls.weight_epsilon(theta)
        print 'weight_epsilon:'
        print '\tintercept:', epsilon[0]
        print '\trank feature:', epsilon[1]
        print '\tclass features:', epsilon[2:(2 + len(SNIPPET_CLASSES))]
        print '\tgeom features:', epsilon[(2 + len(SNIPPET_CLASSES)):]

        print 'weight_alpha', cls.weight_alpha(theta)
        print '\talpha(R): {%s}' % ', '.join(
                '%s: %.3f' % (R, cls._attr(theta, cls._attr_features([(R, 1)]))) \
                    for R in xrange(RelContainer.grades_R)
        )
        print 'tau_0', cls.tau_0(theta)
        print 'tau_D', cls.tau_D(theta)
        print 'tau_R', cls.tau_R(theta)
        sys.stdout.flush()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            description='Build a model that predicts clicks and satisfaction '
                    'given mousing')
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
    args = parser.parse_args()

    spammers = set()
    if args.spammers is not None:
        for s_file_name in args.spammers:
            with open(s_file_name) as f:
                for worker_id in f:
                    spammers.add(worker_id.rstrip())

    print '%d spammers' % len(spammers)

    # log_id (query-doc pair id) to relevance mapping.
    log_id_to_rel = collections.defaultdict(RelContainer)
    log_id_to_query = {}
    with open(args.results_D) as results_D:
        for row in csv.DictReader(results_D):
            # TODO: vary threshold to mark someone as a spammer and see
            #       how the end result changes
            if row['_worker_id'] not in spammers:
                trust = float(row['_trust']) if USE_CF_TRUST else 1
                log_id = row['log_id']
                RelContainer.add_rel(log_id_to_rel[log_id].Ds, row[rel_column['D']], trust)
                log_id_to_query[log_id] = row[orig_query['D']]

    for result_AR in args.results_AR:
        with open(result_AR) as results_AR:
            for row in csv.DictReader(results_AR):
                if row['_worker_id'] not in spammers:
                    trust = float(row['_trust']) if USE_CF_TRUST else 1
                    log_id = row['log_id']
                    RelContainer.add_rel(log_id_to_rel[log_id].Rs, row[rel_column['R']], trust)
                    query = row[orig_query['R']]
                    old_query = log_id_to_query.setdefault(log_id, query)
                    if old_query != query:
                        print >>sys.stderr, ('The same log_id '
                                '(%s) maps to two different queries: [%s] and [%s]' % (
                                        log_id, old_query, query))
                        sys.exit(1)

    print '%d items with complete relevance' % sum(
            1 for r in log_id_to_rel.itervalues() if r)

    print '%d queries with at least one completely judged document' % len(set(
            log_id_to_query[k] for k, r in log_id_to_rel.iteritems() if r))

    data = []
    with open(args.serps) as task_file:
        sat_labels = []
        num_skipped = 0
        num_sat_true = 0
        num_total = 0
        reader = csv.DictReader(task_file)
        for key, query_rows_iter in itertools.groupby(reader,
                        key=lambda row: (row['log_id'].split('_')[:-1], # SERP id
                                         row[orig_query['query']],
                                         row['sat_feedback'])):
            sat = key[2]
            if DEBUG and sat == 'undefined':
                print >>sys.stderr, 'Undefined sat label for query [%s]' % query
            sat_labels.append(sat)
            sat = parse_sat(sat)
            if sat is None:
                num_skipped += 1
                continue
            elif sat:
                num_sat_true += 1
            data_row = {'query': key[1], 'sat': sat, 'session': [], 'serp': []}
            for row in query_rows_iter:
                data_row['session'].append(jsonpickle.decode(row['actions']))
                data_row['serp'].append(
                        bs4.BeautifulSoup(row['snippet'], 'html.parser').li)
            data.append(data_row)
            num_total += 1
        #print collections.Counter(sat_labels)
        print 'Skipped %d rows out of %d' % (num_skipped, num_total + num_skipped)
        print '%.1f%% of SAT labels in the data' % (num_sat_true / num_total * 100)

    N = len(data)
    data = np.array(data)

    MODELS = {
        'CAS': CAS(log_id_to_rel),
        'PBM': PyClickModel('PBM', log_id_to_rel),
        'CASnod': CAS(log_id_to_rel, use_D=False),
        'CASnosat': CAS(log_id_to_rel, sat_term_weight=0),
        'CASnoreg': CAS(log_id_to_rel, reg_coeff=0),
        'CASnoclass': CAS(log_id_to_rel, use_class=False),
        'CASnogeom': CAS(log_id_to_rel, use_geometry=False),
        'CASrank': CAS(log_id_to_rel, use_class=False, use_geometry=False),
        'random': RandomSatModel(),
    }

    for train_index, test_index in sklearn.cross_validation.ShuffleSplit(N, n_iter=1, random_state=42):
        train_data = data[train_index]
        test_data = data[test_index]
        result = {}
        for name, model in MODELS.iteritems():
            params = model.train(train_data)
            ll_values_test = [
                    model.log_likelihood(params,
                                         d['session'], d['serp'], d['sat'],
                                         f_only=True
                    ) for d in test_data
            ]
            result[name] = {}
            result[name]['full'] = np.average([l.full for l in ll_values_test])
            result[name]['click'] = np.average([l.clicks for l in ll_values_test])
            result[name]['sat'] = np.average([l.sat for l in ll_values_test])
            result[name]['sat pearson'] = scipy.stats.pearsonr(
                    [int(d['sat']) for d in test_data],
                    [model.utility(params, d['session'], d['serp']) for d in test_data]
            )[0]
        print name, result
