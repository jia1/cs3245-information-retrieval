#!/usr/bin/python
import nltk
import sys
import getopt

import pickle

from time import time

from nltk.stem import PorterStemmer
stemmer = PorterStemmer()

from constants import universal_stem, operators, precedences, peek, print_time
from skip_list import SkipList
from parse_tree import ParseTree

start_time = time()

dictionary = {}
offsets = {}

# MAIN function for search.py
def do_searching(dictionary_file_name, postings_file_name, queries_file_name, output_file_name):
    with open(dictionary_file_name) as d, open(postings_file_name, 'rb') as p, \
        open(queries_file_name) as q, open(output_file_name, 'w') as o:
        # Build the offsets dictionary for seeking later
        for line in d:
            stem, offset = line.rstrip().split(',')
            offsets[stem] = int(offset)
        # Process each query one-by-one but with the same resources
        # I.e. Duplicate stems are loaded only once
        for line in q:
            query = line.rstrip().lower()
            stems, stemmed_postfix_query = parse_query(query) # string to list in postfix form
            parse_tree = build_tree(stemmed_postfix_query, p) # list to parse tree of skip lists
            root_node = parse_tree.get_root()
            while root_node is not None and root_node.is_operator():
                operand_nodes = parse_tree.get_sorted_operands(comparator=lambda node: node.get_data().get_length())
                # Recall that node.data is a SkipList and as such the comparator compares nodes by
                # the number of postings (node.get_data().get_length())
                index = 0
                while index < len(operand_nodes): # a loop to evaluate the smallest operand possible
                    operand_node = operand_nodes[index]
                    operator_node = operand_node.get_parent()
                    operator = operator_node.get_data()
                    if operator_node.is_unary_operator():
                        operand = operand_node.get_data()
                        operation = unary_operations[operator] # e.g. NOT
                        skip_list = operation(operand, p)
                    else: # operator_node.is_binary_operator()
                        operand_node_a = operator_node.get_left()
                        operand_node_b = operator_node.get_right()
                        if operand_node_a.is_operator() or operand_node_b.is_operator():
                            # The other operand is unevaluated (i.e. not a leaf, and still a subtree
                            # with an operator as root) so we should look at the next operand with the
                            # smallest number of postings
                            index += 1
                            continue
                        operand_a = operand_node_a.get_data()
                        operand_b = operand_node_b.get_data()
                        operation = binary_operations[operator] # e.g. AND, OR
                        skip_list = operation(operand_a, operand_b)
                    # Mutate the subtree root (an operator) into the new evaluated operand (a leaf)
                    operator_node.set_data(skip_list)
                    operator_node.set_left(None)
                    operator_node.set_right(None)
                    break
            if root_node is not None: # is an operand
                final_skip_list = root_node.get_data()
                final_postings_list = map(str, final_skip_list.to_list())
                o.write(' '.join(final_postings_list))
            o.write('\n')

# Accepts a case-folded line without leading or trailing whitespaces and
# Returns a tuple of (stems in query, query in postfix list form)
def parse_query(query_string):
    query_tokens = tokenize(query_string)
    postfix_query = shunting_yard(query_tokens)
    stemmed_postfix_query = []
    stems = set()
    for token in postfix_query:
        if token in operators or token == '(' or token == ')':
            stemmed_postfix_query.append(token)
        else:
            stem = stemmer.stem(token)
            stems.add(stem)
            stemmed_postfix_query.append(stem)
    return (stems, stemmed_postfix_query)

# Accepts a string and
# Returns a list of tokens where parentheses are tokenized too
def tokenize(expression):
    final_tokens = []
    for token in expression.split(' '):
        inner_tokens = []
        if token[0] == '(':
            if token[-1] == ')':
                inner_tokens = ['(', token[1:-1], ')']
            else:
                inner_tokens = ['(', token[1:]]
        elif token[-1] == ')':
            inner_tokens = [token[:-1], ')']
        else:
            inner_tokens = [token]
        final_tokens.extend(inner_tokens)
    return final_tokens

# Accepts a list of tokens and
# Returns a list of tokens in postfix form
def shunting_yard(tokens):
    output_queue = []
    operator_stack = []
    for token in tokens:
        if token == '(':
            operator_stack.append('(')
        elif token == ')':
            last_operator = peek(operator_stack, error='Mismatched parentheses in expression')
            while last_operator != '(':
                output_queue.append(operator_stack.pop())
                last_operator = peek(operator_stack, error='Mismatched parentheses in expression')
            operator_stack.pop()
        elif token in operators:
            while operator_stack:
                last_operator = peek(operator_stack)
                if (last_operator != '('
                    and precedences[last_operator] >= precedences[token]):
                    output_queue.append(operator_stack.pop())
                else:
                    break
            operator_stack.append(token)
        else:
            output_queue.append(token)
    while operator_stack:
        last_operator = peek(operator_stack)
        if last_operator == '(':
            sys.exit('Mismatched parentheses in expression')
        output_queue.append(operator_stack.pop())
    return output_queue

# Accepts a query in postfix list form (i.e. the second return value from parse_query function) and
# Returns a parse tree of parse tree nodes (see parse_tree.py)
def build_tree(postfix_query, postings_file_object):
    postfix_expression = []
    for token in postfix_query:
        if token in operators:
            postfix_expression.append(token)
        else:
            length, postings = load_stem(token, postings_file_object)
            postfix_expression.append(postings)
    tree = ParseTree()
    tree.build_from(postfix_expression)
    return tree

# Accepts a stem, a postings file handle, and
# Returns the loaded postings skip list while storing it in memory
def load_stem(stem, postings_file_object):
    global dictionary
    if stem in dictionary:
        return dictionary[stem]
    postings = SkipList()
    if stem in offsets:
        postings_file_object.seek(offsets[stem])
        postings.build_from(pickle.load(postings_file_object))
    dictionary[stem] = (postings.get_length(), postings)
    return dictionary[stem]

# Implementation of NOT(skip list)
# Accepts a skip list and returns a negated skip list
# Dependent on the existence of universal_postings (a skip list of every posting)
def negate(skip_list, postings_file_object):
    negated_skip_list = SkipList()
    number_of_postings, universal_postings = load_stem(universal_stem, postings_file_object)
    if not number_of_postings:
        return negated_skip_list
    negated_skip_list_data = []
    node_a = universal_postings.get_head()
    node_b = skip_list.get_head()
    while node_a is not None and node_b is not None:
        data_a = node_a.get_data()
        data_b = node_b.get_data()
        if data_a < data_b:
            negated_skip_list_data.append(data_a)
        else: # data_a == data_b
            node_b = node_b.get_next()
        node_a = node_a.get_next()
    while node_a is not None:
        negated_skip_list_data.append(node_a.get_data())
        node_a = node_a.get_next()
    negated_skip_list.build_from(negated_skip_list_data)
    return negated_skip_list

# Implementation of OR(skip list A, skip list B)
# Accepts two skip lists and returns a skip list containing postings from either skip list
# OR != XOR and there will be no duplicate postings in the output skip list
def union(skip_list_a, skip_list_b):
    seen_data = set()
    union_skip_list_data = []
    node_a = skip_list_a.get_head()
    node_b = skip_list_b.get_head()
    while node_a is not None and node_b is not None:
        data_a = node_a.get_data()
        data_b = node_b.get_data()
        if data_a < data_b:
            union_skip_list_data.append(data_a)
            node_a = node_a.get_next()
        elif data_b < data_a:
            union_skip_list_data.append(data_b)
            node_b = node_b.get_next()
        else: # data_a == data_b
            union_skip_list_data.append(data_a)
            node_a = node_a.get_next()
            node_b = node_b.get_next()
    while node_a is not None:
        union_skip_list_data.append(node_a.get_data())
        node_a = node_a.get_next()
    while node_b is not None:
        union_skip_list_data.append(node_b.get_data())
        node_b = node_b.get_next()
    union_skip_list = SkipList()
    union_skip_list.build_from(union_skip_list_data)
    return union_skip_list

# Implementation of AND(skip list A, skip list B)
# Accepts two skip lists and returns a skip list containing postings which both skip lists have
# Does skipping when the skip pointer node of one skip list has a value less than the other skip list node
def merge(skip_list_a, skip_list_b):
    merged_skip_list_data = []
    node_a = skip_list_a.get_head()
    node_b = skip_list_b.get_head()
    while node_a is not None and node_b is not None:
        data_a = node_a.get_data()
        data_b = node_b.get_data()
        if data_a < data_b:
            skip_node_a = node_a.get_skip()
            if skip_node_a is not None and skip_node_a.get_data() <= data_b:
                node_a = skip_node_a
            else:
                node_a = node_a.get_next()
        elif data_b < data_a:
            skip_node_b = node_b.get_skip()
            if skip_node_b is not None and skip_node_b.get_data() <= data_a:
                node_b = skip_node_b
            else:
                node_b = node_b.get_next()
        else: # data_a == data_b:
            merged_skip_list_data.append(data_a)
            node_a = node_a.get_next()
            node_b = node_b.get_next()
    merged_skip_list = SkipList()
    merged_skip_list.build_from(merged_skip_list_data)
    return merged_skip_list

unary_operations = {
    'not': negate
}

binary_operations = {
    'or': union,
    'and': merge
}

def usage():
    print('Usage: ' + sys.argv[0] + ' -d dictionary-file -p postings-file -q file-of-queries -o output-file-of-results')

input_file_d = input_file_p = input_file_q = output_file_o = None
try:
    opts, args = getopt.getopt(sys.argv[1:], 'd:p:q:o:')
except (getopt.GetoptError, err) as e:
    usage()
    sys.exit(2)
for o, a in opts:
    if o == '-d':
        input_file_d = a
    elif o == '-p':
        input_file_p = a
    elif o == '-q':
        input_file_q = a
    elif o == '-o':
        output_file_o = a
    else:
        assert False, 'Unhandled option'
if input_file_d == None or input_file_p == None or input_file_q == None or output_file_o == None:
    usage()
    sys.exit(2)

do_searching(input_file_d, input_file_p, input_file_q, output_file_o)

stop_time = time()

print_time(start_time, stop_time)
