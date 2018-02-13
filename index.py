#!/usr/bin/python
import re
import nltk
import sys
import getopt
import os
import string
import bisect
import pickle

from nltk.stem import PorterStemmer
from nltk.tokenize import sent_tokenize, word_tokenize
stemmer = PorterStemmer()

from skip_list import SkipList

with open('stopwords.txt') as f:
    stopwords = set(map(lambda ln: ln.strip(), f.readlines()))

'''
Create a dictionary[stem] -> sorted([postings]) and write to the dictionary and postings file
    - dictionary is a dictionary whose keys are stems and whose values are sorted posting lists
    - postings will then be converted into a skip list with sqrt(postings.length) skip pointers 
'''
def do_indexing(documents_directory, dictionary_file, postings_file):
    dictionary = {}
    seen_postings_by_stem = {}
    for root, directories, files in os.walk(documents_directory):
        for posting in files:
            with open(os.path.join(root, posting)) as f:
                text = get_preprocessed(f.read())
                for stem in text:
                    posting = int(posting)
                    if stem not in dictionary:
                        dictionary[stem] = [posting]
                        seen_postings_by_stem[stem] = set((posting,))
                    else:
                        if posting not in seen_postings_by_stem[stem]:
                            bisect.insort(dictionary[stem], posting)
                            seen_postings_by_stem[stem].add(posting)
    stems = dictionary.keys()
    with open(dictionary_file, 'w') as d:
        d.write('\n'.join(stems))
    with open(postings_file, 'wb') as p:
        for stem in stems:
            postings = SkipList()
            postings.build_from(dictionary[stem])
            pickle.dump(postings, p)

'''
Preprocess a text string in the following order:
    1. Sentence tokenize via sent_tokenize
    2. Word tokenize via word_tokenize and remove duplicates via set()
    3. Do case folding on each token
    4. Filter out punctuations, non-alphabetical words, and stopwords from the tokens
    5. Stem the remaining words
    6. Return a flattened set of stemmed words
'''
def get_preprocessed(text):
    sentences = map(
        lambda sentence: list(map(
            lambda word: stemmer.stem(word),
            filter(
                lambda token: token not in string.punctuation and token.isalpha() and token not in stopwords,
                map(
                    lambda token: token.lower(),
                    set(word_tokenize(sentence))
                )))),
        sent_tokenize(text))
    return set((stem for stems in sentences for stem in stems))

def usage():
    print('Usage: ' + sys.argv[0] + ' -i directory-of-documents -d dictionary-file -p postings-file')

input_directory_d = output_file_d = output_file_p = None
try:
    opts, args = getopt.getopt(sys.argv[1:], 'i:d:p:')
except (getopt.GetoptError, err) as e:
    usage()
    sys.exit(2)
for o, a in opts:
    if o == '-i':
        input_directory_d = a
    elif o == '-d':
        output_file_d = a
    elif o == '-p':
        output_file_p = a
    else:
        assert False, 'Unhandled option'
if input_directory_d == None or output_file_d == None or output_file_p == None:
    usage()
    sys.exit(2)

do_indexing(input_directory_d, output_file_d, output_file_p)
