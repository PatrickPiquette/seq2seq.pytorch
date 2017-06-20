#!/usr/bin/env python
# -*- coding: utf-8 -*-
import torch
from torch.autograd import Variable
from tools.config import EOS, BOS, LANGUAGE_TOKENS
from tools.beam_search import SequenceGenerator
from torch.nn.functional import adaptive_avg_pool2d


class Translator(object):

    def __init__(self, model, src_tok, target_tok,
                 beam_size=5,
                 length_normalization_factor=0,
                 max_sequence_length=50,
                 batch_first=False,
                 return_all=False,
                 get_attention=False,
                 cuda=False):
        self.model = model
        self.src_tok = src_tok
        self.target_tok = target_tok
        self.insert_target_start = [BOS]
        self.insert_src_start = [BOS]
        self.insert_src_end = [EOS]
        self.batch_first = batch_first
        self.return_all = return_all
        self.cuda = cuda
        if self.cuda:
            model.cuda()
        else:
            model.cpu()
        model.eval()
        self.generator = SequenceGenerator(
            model=self.model.generate,
            beam_size=beam_size,
            batch_first=batch_first,
            max_sequence_length=max_sequence_length,
            get_attention=get_attention,
            length_normalization_factor=length_normalization_factor)

    def set_src_language(self, language):
        lang = self.src_tok.special_tokens.index(LANGUAGE_TOKENS[language])
        self.insert_src_start = [BOS, lang]

    def set_target_language(self, language):
        lang = self.target_tok.special_tokens.index(LANGUAGE_TOKENS[language])
        self.insert_target_start = [BOS, lang]

    def translate(self, input_sentence, target_priming=''):
        src = self.src_tok.tokenize(input_sentence,
                                    insert_start=self.insert_src_start,
                                    insert_end=self.insert_src_end)
        bos = self.target_tok.tokenize(
            target_priming, insert_start=self.insert_target_start)
        shape = (1, -1) if self.batch_first else (-1, 1)
        src = Variable(src.view(*shape), volatile=True)
        bos = Variable(bos.view(*shape), volatile=True)
        if self.cuda:
            src = src.cuda()
            bos = bos.cuda()

        self.model.clear_state()
        context = self.model.encode(src)
        if hasattr(self.model, 'bridge'):
            context = self.model.bridge(context)
        preds, logprobs, attentions = self.generator.beam_search(bos, context)
        num_return = len(preds) if self.return_all else 1
        output = [self.target_tok.detokenize(
            preds[i][:-1]) for i in range(num_return)]
        output = [' '.join([target_priming, o]) for o in output]
        if len(output) == 1:
            output = output[0]
        return output


class CaptionGenerator(Translator):

    def __init__(self, model, img_transform, target_tok,
                 beam_size=5,
                 length_normalization_factor=0,
                 max_sequence_length=50,
                 batch_first=False,
                 return_all=False,
                 get_attention=False,
                 cuda=False):
        self.img_transform = img_transform
        super(CaptionGenerator, self).__init__(model,
                                               None,
                                               target_tok,
                                               beam_size,
                                               length_normalization_factor,
                                               max_sequence_length,
                                               batch_first,
                                               return_all,
                                               get_attention,
                                               cuda)

    def set_src_language(self, language):
        pass

    def describe(self, input_img, target_priming=''):
        src_img = self.img_transform(input_img)

        bos = self.target_tok.tokenize(
            target_priming, insert_start=self.insert_target_start)
        shape = (1, -1) if self.batch_first else (-1, 1)
        src = Variable(src_img.unsqueeze(0).unsqueeze(0), volatile=True)
        bos = Variable(bos.view(*shape), volatile=True)
        if self.cuda:
            src = src.cuda()
            bos = bos.cuda()

        self.model.clear_state()
        context = self.model.encode(src)
        _, c, h, w = list(context[0].size())
        if hasattr(self.model, 'bridge'):
            context = self.model.bridge(context)

        preds, logprobs, attentions = self.generator.beam_search(bos, context)
        num_return = len(preds) if self.return_all else 1
        output = [self.target_tok.detokenize(
            preds[i][:-1]) for i in range(num_return)]
        output = [' '.join([target_priming, o]) for o in output]
        if len(output) == 1:
            output = output[0]

        if attentions is not None:
            attentions = [[a.view(h,w) for a in a_list] for a_list in attentions]
        return output, attentions
        # for s,p in zip(sentences,logprob):
        #     print(target_tok.detokenize(s)[::-1],' p=%s' % math.exp(p))
