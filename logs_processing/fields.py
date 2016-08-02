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
