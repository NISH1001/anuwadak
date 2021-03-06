#!/usr/bin/env python3

import re
import time
from collections import defaultdict, OrderedDict
import operator

try:
    from .ngramdb import NgramDB
    from .ngram_mem import NgramMem
except:
    from ngramdb import NgramDB
    from ngram_mem import NgramMem

"""
Ngram class: 
-- For now we use upto quadgrams
-- uses our ngram database handler ngramdb 
-- sqlite database is used

attributes:
    bigrams,trigrams,quadgrams are all dictionary with key as tuple of words
    eg: bigrams[('happy', 'man)] = somecount

functions:
    count()                         : get the occurence count of the ngrams sequence
    probability()                   : get the probability of count -> count/total
    __generate_probability_table    : private function to generate our probablity table (uses bigrams)
    generate_sentence               : get the final sentence using the probability table
"""
class Ngram(object):

    def __init__(self, data_path="../data/ngrams/", load_type="memory"):
        self.load_type = load_type
        self.unigrams = OrderedDict()
        self.bigrams  = OrderedDict()
        self.trigrams = OrderedDict()
        self.quadgrams = OrderedDict()

        # this is ngrams database handler
        self.ngramdb = NgramDB(data_path+"ngrams.db")
        #self.ngramdb.create_table_all()
        if load_type=="memory":
            ngram_mem = NgramMem(data_path=data_path)
            ngram_mem.load_all(pickle=True)
            self.__count = ngram_mem.count
            self.__count_vocab = ngram_mem.count_vocab
        else:
            self.__count = self.ngramdb.count

    def close_ngramdb(self):
        self.ngramdb.close()

    def count(self, seq, total=False):
        """
        get integer count of the sequence of words
        seq : is a tuple of words
        returns count of occurences of such sequence
        if total count is needed just set total to True
            and pass garbage seq
        """

        return self.__count(seq, total)

    def probability(self, seq):
        """ get probability of the ngram sequence"""

        length = len(seq)
        count = self.count(seq, total=False)

        # get lower ngram tuple
        lower = tuple( seq[0:length-1] )

        # total is the count of that lower ngram
        count_lower = self.count(lower, total=False)

        """
        if not count or not count_lower:
            return 1e-9
        else:
            #return count/total
        """
        # smoothing is done finally
        return (count+1) / (count_lower + self.__count_vocab(n=length-1) )

    def probability_sentence(self, seq, n=3):
        """
            calculates the probability of given sentence
            using markov chain
        """

        if len(seq) < n:
            n = 2
        
        prob = 1
        for i in range( len(seq) - (n-1) ):
            tup = tuple( seq[i:i+n] )
            prob *= self.probability(tup)
        return prob
    
    """ private function: create our 2d table with probability using list comprehension"""
    def __generate_probability_table(self, seq):
        n = len(seq)
        table = [ 
                    [
                        -1.0
                        if x==y or seq[x]==seq[y] else 1*self.probability( tuple([ seq[x],seq[y] ]) ) 
                        for y in range(n)
                    ] 
                for x in range(n) 
            ]
        return table

    """ generate the first phase sentence
    """
    def generate_sentence(self, seq):
        n = len(seq)
        table = self.__generate_probability_table(seq) # get the table

        # track the row index in the table
        index_row = 0
        # resultant list
        res = [seq[0]]

        # main generator
        for i in range(n-1):
            # get the word with max probablity ie word(x+1) that is likley to occur after the world(x)
            index_col, max_prob = max(enumerate(table[index_row]), key=lambda x: x[1])

            res.append(seq[index_col])
            #table[index_col] = [0.0]*n
            # set the column prob negative -> no need of previous words for upcoming words
            for i in range(n):
                table[i][index_row] = -1

            # new index row 
            index_row = index_col
        return tuple(res)

    # our overlapper -> overlapping tuple processer
    def __overlapper(self, seq, start_with, trie):
        overlap_list = [start_with]
        closed_set = set(start_with)

        for i in range(1,len(seq)-2):
            # get previous tuple in the overlap list
            prev_key = overlap_list[i-1]
            # our next best tuple
            next_tuple = None
            # for getting best probability shit :D
            prev_prob = -1

            # iterate over all the trigrams in the trie
            # cannot delete an element from a dict while in the loop -> hence copy
            temp_dict = trie.copy()
            for key in temp_dict:

                # if current key/tuple begins with the words previous tuple in our overlap_list has
                if (key[0], key[1],) == (prev_key[1], prev_key[2],) and key[2] not in closed_set:
                    if trie[key] > prev_prob:
                        prev_prob, next_tuple = trie[key], key
                        del trie[key]

            # if we get the next tuple 
            if next_tuple:
                # update our closed set
                closed_set.update(next_tuple)
                # update our flood list
                overlap_list.append(next_tuple)

        return overlap_list

    def generate_sentence2(self, seq):
        n = len(seq)

        # create our trigrams dict
        # it is not a trie and following variable name 'trie' is hallucinating :P
        trie = {}
        # 3 nested-loops
        for i in range(n):
            for j in range(n):
                for k in range(n):
                    key = (seq[i], seq[j], seq[k])
                    if i==j==k or len(key)!=len(set(key)):
                        continue
                    #print(key, self.count(key))
                    trie[key] = self.probability(key)
        #trie = OrderedDict(sorted(trie.items(), key=operator.itemgetter(1),  reverse=True))

        # find the starting 3 words (a tuple) from trigrams
        start_word = seq[0]
        start_with = None
        prev = -1
        for key in trie:
            if key[0]==start_word:
                if trie[key] > prev:
                    prev, start_with = trie[key], key

        if not start_with:
            return seq

        # use our overlapper (overlapping technique)
        overlap_list = self.__overlapper(seq, start_with, trie)

        final = list(start_with)
        for i in range(1,len(overlap_list)):
            tup = overlap_list[i]
            final.append(tup[2])

        return tuple(final)
    
    def generate_sentences_from_list(self, seq_list):
        return [ self.generate_sentence2(seq) for seq in seq_list ]

    def generate_sentence_best(self, seq_list):
        prev = 0
        best = None
        for sentence in seq_list:
            prob = self.probability_sentence(sentence)
            if prob >= prev:
                prev, best = prob, sentence
        return best

def main():
    start = time.time()
    ngram = Ngram(data_path="../data/ngrams/", load_type="memory")
    print("time : ",time.time() - start)

    # just a ngram tester
    while True:
        seq = str(input("enter sequence of words: "))
        seq = tuple(seq.split())
        if not seq:
            continue
        if seq=="exit":
            break
        #print(ngram.cnf_separator(seq))
        sentence = ngram.generate_sentence2(seq)
        print(sentence)
        print("prob : ", ngram.probability_sentence(sentence, n=3))

    ngram.close_ngramdb()

if __name__=="__main__":
    main()




