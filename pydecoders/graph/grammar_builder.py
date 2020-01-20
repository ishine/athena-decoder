"""Transfer Arpa tri-gram language model to WFST format

Python versioin arpa2fst scripts, Now only support trigram
arpa language model
"""

import math
import re
from absl import logging
import openfst_python as fst

def convert_weight(prob):
    """Convert probility to weight in WFST"""
    weight = -1.0 * math.log(10.0) * float(prob)
    return weight

class GrammarBuilder:
    """GrammarBuilder
    Builder class to transfer language model to WFST
    """
    def __init__(self):
        self.unigram2state = {}
        self.bigram2state = {}
        self.grammar_fst = fst.Fst()
        self.order = 0
        self.grammar_fst.add_state()
        self.grammar_fst.set_start(0)
        self.unigram2state['<start>'] = 0
        self.grammar_fst.add_state()
        self.grammar_fst.set_start(1)
        self.unigram2state['<s>'] = 1
        self.disambig_symbol = '#0'
        self.words_table = {}

    def arpa2fst(self, arpa_file):
        """
        Parse arpa language model and build WFST

        Args:
            arpa_file: arpa file to be convert
        """
        arpa = open(arpa_file, 'r')
        for line in arpa:
            line = line.strip()
            if line == '':
                continue
            elif line.startswith('#'):
                continue
            elif line.startswith('\\data'):
                continue
            elif line.startswith('ngram '):
                continue
            elif line.startswith('\\end'):
                continue
            elif line.startswith('\\'):
                self.order = int(line.replace('\\', '').replace('-grams:', ''))
                logging.info("reading {}-grams".format(self.order))
                continue
            assert self.order != 0
            if self.order == 1:
                self.process_unigram(line)
            elif self.order == 2:
                self.process_bigram(line)
            elif self.order == 3:
                self.process_trigram(line)
            else:
                raise NotImplementedError
        arpa.close()

    def __call__(self, arpa_file, words_table_file):
        """functional callback

        Args:
            arpa_file: arpa file to be convert
            words_table_file: words table file from word to id
        Return:
            grammar_fst: result wfst
        """
        with open(words_table_file, 'r') as f:
            for line in f:
                word, idx = line.strip().split()
                self.words_table[word] = int(idx)
        self.arpa2fst(arpa_file)
        self.remove_redundant_states()
        self.grammar_fst.arcsort(sort_type='ilabel')
        return self.grammar_fst

    def sid(self, symbol):
        """Wrapper for words table

        """
        if symbol not in self.words_table:
            raise IndexError
        else:
            return self.words_table[symbol]

    def remove_redundant_states(self):
        """ Remove states which only have one back off arc """
        for state in self.grammar_fst.states():
            if (self.grammar_fst.num_arcs(state) == 1
                    and self.grammar_fst.final(state).to_string() ==
                    fst.Weight.Zero('tropical').to_string()):
                aiter = self.grammar_fst.mutable_arcs(state)
                while not aiter.done():
                    arc = aiter.value()
                    if arc.ilabel == self.sid('#0'):
                        arc.ilabel = self.sid('<eps>')
                        aiter.set_value(arc)
                    aiter.next()
        self.grammar_fst.rmepsilon()

    def process_unigram(self, gram):
        """Process unigram in arpa file"""
        parts = re.split(r'\s+', gram)
        boff = '0.0'
        if len(parts) == 3:
            prob, word, boff = parts
        elif len(parts) == 2:
            prob, word = parts
        else:
            raise NotImplementedError
        if word not in self.words_table:
            return
        weight = convert_weight(prob)
        boff = convert_weight(boff)
        if word == '</s>':
            src = self.unigram2state['<start>']
            self.grammar_fst.set_final(src, weight)
        elif word == '<s>':
            src = self.unigram2state['<s>']
            des = self.unigram2state['<start>']
            self.grammar_fst.add_arc(src, fst.Arc(self.sid('#0'), self.sid('<eps>'), boff, des))
        else:
            src = self.unigram2state['<start>']
            if word in self.unigram2state:
                des = self.unigram2state[word]
            else:
                des = self.grammar_fst.add_state()
                self.unigram2state[word] = des
            self.grammar_fst.add_arc(src, fst.Arc(self.sid(word), self.sid(word), weight, des))
            self.grammar_fst.add_arc(des, fst.Arc(self.sid('#0'), self.sid('<eps>'), boff, src))

    def process_bigram(self, gram):
        """Process bigram in arpa file"""
        parts = re.split(r'\s+', gram)
        boff = '0.0'
        if len(parts) == 4:
            prob, hist, word, boff = parts
        elif len(parts) == 3:
            prob, hist, word = parts
        else:
            raise NotImplementedError
        if (hist not in self.words_table
                or word not in self.words_table):
            return
        weight = convert_weight(prob)
        boff = convert_weight(boff)
        if hist not in self.unigram2state:
            logging.info('[{} {} {}] skipped: no parent (n-1)-gram exists'.format(prob, hist, word))
            return
        if word == '</s>':
            src = self.unigram2state[hist]
            self.grammar_fst.set_final(src, weight)
        else:
            src = self.unigram2state[hist]
            bigram = hist + '/' + word
            if bigram in self.bigram2state:
                des = self.bigram2state[bigram]
            else:
                des = self.grammar_fst.add_state()
                self.bigram2state[bigram] = des
                if word in self.unigram2state:
                    boff_state = self.unigram2state[word]
                else:
                    boff_state = self.unigram2state['<start>']
                self.grammar_fst.add_arc(des, fst.Arc(self.sid('#0'),
                    self.sid('<eps>'), boff, boff_state))
            self.grammar_fst.add_arc(src, fst.Arc(self.sid(word), self.sid(word), weight, des))

    def process_trigram(self, gram):
        """Process trigram in arpa file"""
        prob, hist1, hist2, word = re.split(r'\s+', gram)
        if (hist1 not in self.words_table
                or hist2 not in self.words_table
                or word not in self.words_table):
            return
        boff = '0.0'
        weight = convert_weight(prob)
        boff = convert_weight(boff)
        bigram1 = hist1 + '/' + hist2
        if bigram1 not in self.bigram2state:
            logging.info('[{} {} {} {}] skipped: no parent (n-1)-gram exists'.format(prob,
                hist1, hist2, word))
            return
        bigram2 = hist2 + '/' + word
        src = self.bigram2state[bigram1]
        if word == '</s>':
            self.grammar_fst.set_final(src, weight)
        else:
            if bigram2 in self.bigram2state:
                des = self.bigram2state[bigram2]
            else:
                des = self.grammar_fst.add_state()
                self.bigram2state[bigram2] = des
                if word in self.unigram2state:
                    boff_state = self.unigram2state[word]
                else:
                    boff_state = self.unigram2state['<start>']
                self.grammar_fst.add_arc(des, fst.Arc(self.sid('#0'), 
                    self.sid('<eps>'), boff, boff_state))
            self.grammar_fst.add_arc(src, fst.Arc(self.sid(word), self.sid(word), weight, des))
