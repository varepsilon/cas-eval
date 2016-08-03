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
# Compute Cohen's kappa https://en.wikipedia.org/wiki/Cohen%27s_kappa
# Handle missing values using a dummy class.

from __future__ import division

import collections
import itertools

def cohen_kappa(data, missing_functor=lambda x: False, convert_items=lambda x: x):
    '''
        Compute Cohen's kappa
        - data is in the format
            [
                {unit1:value, unit2:value, ...},  # worker 1
                {unit1:value, unit3:value, ...},  # worker 2
                ...                               # more workers
            ]
        - missing_functor is a bool-valued function used to separate missing_functor items
        - convert_items a function to convert_items values (e.g., binarize them)
    '''

    sum_kappas = 0
    num_kappas = 0
    for w1_answers, w2_answers in itertools.combinations(data, 2):
        converted_answers = collections.defaultdict(lambda: 0)  # confusion matrix
        # Count cases where w1 has a rating.
        for key1, a1 in w1_answers.iteritems():
            if missing_functor(a1):
                continue
            a2 = w2_answers.get(key1)
            if missing_functor(a2):
                a2 = None
            converted_answers[(convert_items(a1), None if a2 is None else convert_items(a2))] += 1

        # Now count cases where w2 has a rating, but w1 does not.
        for key2, a2 in w2_answers.iteritems():
            if missing_functor(a2):
                continue
            a1 = w1_answers.get(key2)
            if a1 is None or missing_functor(a1):
                converted_answers[(None, convert_items(a2))] += 1

        s_overlapping = 0
        categories = set()
        for x, count in converted_answers.iteritems():
            if x[0] is not None:
                categories.add(x[0])
            if x[1] is not None:
                categories.add(x[1])
            if (x[0] is not None) and (x[1] is not None):
                s_overlapping += count
        if s_overlapping < 1:
            continue

        # Add a dummy category
        categories_w_dummy = categories | set([None])
        # Probability of agreement (only look at the overlapping data).
        p_a = sum(converted_answers[(c, c)] for c in categories) / s_overlapping
        # Probability of agreeing by chance (also include dummy category).
        p_e = sum(
            sum(converted_answers[(k, i)] for i in categories_w_dummy) *
            sum(converted_answers[(j, k)] for j in categories_w_dummy) for k in categories) / (
                    sum(converted_answers.itervalues()) ** 2)
        if p_a != p_e:
            # Precaution to avoid 0/0 division error.
            sum_kappas += (p_a - p_e) / (1 - p_e)
        num_kappas += 1
    return sum_kappas / num_kappas

