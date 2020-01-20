"""Convert speller file to WFST format

Python version script
Speller file plays lexicon role in seq2seq ASR
lexicon maps words to monophone or context-dependent phone
However, in seq2seq ASR we map words to characters just
like spell the words, we call it speller file
"""

import math
from collections import OrderedDict
import openfst_python as fst

class SpellerBuilder:
    """SpellerBuilder
    Builder class to convert speller file to WFST format
    """
    def __init__(self):
        self.spellers = []
        self.disambig_chars = OrderedDict()
        self.words = OrderedDict()
        self.max_disambig = 0
        self.speller_fst = fst.Fst()

    def add_disambig(self):
        """add disambig symbols to speller items when necessary"""
        count = {}
        is_sub_seq = set()
        self.max_disambig = 0
        reserved = set()
        disambig_of = {}
        for _, char_seq in self.spellers:
            char_seq_str = ' '.join(char_seq)
            if char_seq_str in count:
                count[char_seq_str] += 1
            else:
                count[char_seq_str] = 1
            tmp_char_seq = char_seq[:]
            tmp_char_seq.pop()
            while tmp_char_seq:
                is_sub_seq.add(' '.join(tmp_char_seq))
                tmp_char_seq.pop()
        for _, char_seq in self.spellers:
            char_seq_str = ' '.join(char_seq)
            if char_seq_str not in is_sub_seq and count[char_seq_str] == 1:
                pass
            else:
                if char_seq_str == '':
                    self.max_disambig += 1
                    reserved.add(self.max_disambig)
                    char_seq = ['#' + str(self.max_disambig)]
                else:
                    if char_seq_str in disambig_of:
                        cur_number = disambig_of[char_seq_str]
                    else:
                        cur_number = 0
                    cur_number += 1
                    while cur_number in reserved:
                        cur_number += 1
                    if cur_number > self.max_disambig:
                        self.max_disambig = cur_number
                    disambig_of[char_seq_str] = cur_number
                    char_seq.append('#' + str(cur_number))

    def create_words_table(self):
        """create words table according to speller file
        eps map to 0
        """
        words_list = []
        for word, _ in self.spellers:
            words_list.append(word)
        words_list = list(set(words_list))
        words_list.sort()
        words_list.insert(0, '<eps>')
        words_list.append('#0')
        words_list.append('<s>')
        words_list.append('</s>')
        self.words = {word:idx for idx, word in enumerate(words_list)}

    def write_words_table(self, words_file='words.txt'):
        """write words table to file

        Args:
            words_file: write to words_file, default:words.txt
        """
        words_file = open(words_file, 'w')
        for word, idx in self.words.items():
            words_file.write('{} {}\n'.format(word, idx))
        words_file.close()

    def create_disambig_chars_table(self, chars_file):
        """ create disambig chars table
        this chars table is different from input chars table
        because of eps and disambig symbols
        """
        chars_list = []
        with open(chars_file, 'r') as f:
            for line in f:
                char = line.strip().split()[0]
                chars_list.append(char)
        chars_list.insert(0, '<eps>')
        disambig = 0
        self.max_disambig += 1 # for sil disambig
        while disambig <= self.max_disambig:
            chars_list.append('#' + str(disambig))
            disambig += 1
        self.disambig_chars = {char:idx for idx, char in enumerate(chars_list)}

    def write_disambig_chars_table(self, disambig_chars_file='characters_disambig.txt'):
        """write disambig chars table to file

        Args:
            disambig_chars_file: write disambig chars file to
                default:characters_disambig.txt
        """
        chars_file = open(disambig_chars_file, 'w')
        for char, idx in self.disambig_chars.items():
            chars_file.write('{} {}\n'.format(char, idx))
        chars_file.close()

    @property
    def disambig_ids(self):
        disambig_ids = [self.disambig_chars['#'+str(s)] for s in range(self.max_disambig+1)]
        return disambig_ids

    @property
    def unk_ids(self):
        unk_ids = []
        if '<unk>' in self.words:
            unk_ids.append(self.words['<unk>'])
        if '<UNK>' in self.words:
            unk_ids.append(self.words['<UNK>'])
        return unk_ids

    @property
    def words_table(self):
        return self.words

    @property
    def disambig_chars_table(self):
        return self.disambig_chars

    def make_speller_fst(self, sil_prob=0.5, sil_symbol='<space>'):
        """Convert speller to WFST format
        There is always a disambig symbols after sil_symbol
        the special disambig symbols have been added
        in self.create_disambig_chars_table function

        Args:
            sil_prob: probability from end of a word to sil symbol
            sil_symbol: 'SIL' for phone-based ASR;'<space>' for
            character-based ASR
        """
        sil_cost = -1.0 * math.log(sil_prob)
        no_sil_cost = -1.0 * math.log(1.0 - sil_prob)
        sil_disambig_id = self.disambig_chars['#' + str(self.max_disambig)]
        start_state = self.speller_fst.add_state()
        loop_state = self.speller_fst.add_state()
        sil_state = self.speller_fst.add_state()
        disambig_state = self.speller_fst.add_state()
        self.speller_fst.set_start(start_state)
        self.speller_fst.add_arc(start_state, fst.Arc(self.disambig_chars['<eps>'],
            self.words['<eps>'], no_sil_cost, loop_state))
        self.speller_fst.add_arc(start_state, fst.Arc(self.disambig_chars[sil_symbol],
            self.words['<eps>'], sil_cost, disambig_state))
        self.speller_fst.add_arc(sil_state, fst.Arc(self.disambig_chars[sil_symbol],
            self.words['<eps>'], 0.0, disambig_state))
        self.speller_fst.add_arc(disambig_state, fst.Arc(sil_disambig_id,
            self.words['<eps>'], 0.0, loop_state))
        for word, char_seq in self.spellers:
            word_id = self.words[word]
            char_id_seq = [self.disambig_chars[char] for char in char_seq]
            eps_id = self.words['<eps>']
            src = loop_state
            for pos, char_id in enumerate(char_id_seq[:-1]):
                des = self.speller_fst.add_state()
                if pos == 0:
                    self.speller_fst.add_arc(src, fst.Arc(char_id, word_id, 0.0, des))
                else:
                    self.speller_fst.add_arc(src, fst.Arc(char_id, eps_id, 0.0, des))
                src = des
            last_char_id = char_id_seq[-1]
            self.speller_fst.add_arc(src, fst.Arc(last_char_id, eps_id, no_sil_cost, loop_state))
            self.speller_fst.add_arc(src, fst.Arc(last_char_id, eps_id, sil_cost, sil_state))
        self.speller_fst.set_final(loop_state, 0.0)
        self.speller_fst.add_arc(loop_state, fst.Arc(self.disambig_chars['#0'],
            self.words['#0'], 0.0, loop_state))
        self.speller_fst.arcsort(sort_type='olabel')

    def __call__(self, speller_file, chars_file):
        """ caller interface for build speller WFST

        Args:
            speller_file: input speller file
            chars_file: input chars file
        Returns:
            speller_fst: output speller WFST
        """
        with open(speller_file, 'r') as f:
            for line in f:
                items = line.strip().split()
                word = items[0]
                char_seq = items[1:]
                self.spellers.append((word, char_seq))
        self.add_disambig()
        self.create_words_table()
        self.create_disambig_chars_table(chars_file)
        self.make_speller_fst()
        return self.speller_fst
