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
# Some constants shared across multiple python scripts.
# Make sure the values are in sync with rating_collection/*.

import collections

orig_query = collections.defaultdict(lambda: 'query', D='orig_query')

non_english = {
    'D': 'copy_a_nonenglish_word_from_the_question_or_text',
    'A': 'non_english',
    'R': 'non_english',
}

rel_column = {
    'D': 'main',
    'A': 'main',
    'R': 'rel',
}

rel_grades = {
    'D': ['D2', 'D1', 'D0', 'D-1', 'D-2'],
    'A': ['A1', 'A0', 'A-1', 'A-2'],
    'R': ['R3', 'R2', 'R1', 'R0', 'R-2', 'R-3'],
}

# Only for A and R
free_text_fields = [
    # DEPRECATED in favor of 'marginally_relevant_detailed'
    'copy_a_few_words_from_the_document_that_supports_the_fact_that_the_document_and_the_question_are_talking_about_related_topics',
    'marginally_relevant_detailed',
    'copy_a_nonenglish_word_from_the_document',
    'copy_an_answer_from_the_document',
    'cannot_open_other',
    'no_other',
    'what_is_the_document_talking_about',
    'yes_other',
]
