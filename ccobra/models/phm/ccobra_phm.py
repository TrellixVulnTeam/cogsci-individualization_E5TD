import time
import sys
import os

import ccobra
import numpy as np
import pandas as pd

import phm

class PHMModel(ccobra.CCobraModel):
    def __init__(self, name='PHM', khemlani_phrase=False, direction_bias_enabled=False, no_fit=False, mode=None):
        super(PHMModel, self).__init__(name, ['syllogistic'], ['single-choice'])
        self.phm = phm.PHM(khemlani_phrase=khemlani_phrase)

        # Member variables
        self.direction_bias_enabled = direction_bias_enabled
        self.no_fit = no_fit
        self.mode = mode

        # Individualization parameters
        self.history = []
        self.p_entailment = 0.04316547
        self.direction_bias = 0
        self.max_confidence = {'A': 0.88489209, 'I': 0.44604317, 'E': 0.25179856, 'O': 0.28776978}
        self.default_confidence = self.max_confidence

        # Time stuff
        self.start_time = None

    def start_participant(self, **kwargs):
        self.start_time = time.time()

    def end_participant(self, subj_id, **kwargs):
        # Parameterization output
        print('Fit ({:.2f}s) id={} params=[(p_entailm,{}),(direction,{}),(max_confi,{})]'.format(
            time.time() - self.start_time,
            subj_id,
            self.p_entailment,
            self.direction_bias,
            str(list(self.max_confidence.items())).replace(' ', '')
        ))
        sys.stdout.flush()

    def pre_train(self, data, **kwargs):
        if self.mode != 'pretrain':
            return

        print('pre-training...')

        for dataset in data:
            for task_data in dataset:
                item = task_data['item']
                truth = task_data['response']
                self.history.append((item, truth))

        self.adapt_grid()

    def person_train(self, dataset, **kwargs):
        if self.mode != 'persontrain':
            return

        print('person training...')

        for task_data in dataset:
            item = task_data['item']
            truth = task_data['response']
            self.history.append((item, truth))

        self.adapt_grid()

    def predict(self, item, **kwargs):
        task_enc = ccobra.syllogistic.encode_task(item.task)

        # Obtain predictions
        use_p_entailment = self.p_entailment >= 0.5
        preds = self.phm.generate_conclusions(task_enc, use_p_entailment)

        # Apply the possible direction bias
        pred = np.random.choice(preds)
        if self.direction_bias_enabled:
            pred = preds[0]
            if self.direction_bias < 0 and len(preds) == 2:
                pred = preds[1]

        # Apply max-heuristic
        if not self.phm.max_heuristic(task_enc, *[self.max_confidence[x] for x in ['A', 'I', 'E', 'O']]):
            pred = 'NVC'

        return ccobra.syllogistic.decode_response(pred, item.task)

    def adapt(self, item, truth, **kwargs):
        print('Adapting')
        if self.no_fit:
            return

        self.history.append((item, truth))
        self.adapt_grid()

    def adapt_grid(self):
        best_score = 0
        best_p_ent = 0
        best_dir_bias = 0
        best_max_conf = self.default_confidence

        max_confidence_grid = [
            {'A': 1, 'I': 1, 'E': 1, 'O': 1},
            {'A': 1, 'I': 1, 'E': 1, 'O': 0},
            {'A': 1, 'I': 1, 'E': 0, 'O': 1},
            {'A': 1, 'I': 1, 'E': 0, 'O': 0},
            {'A': 1, 'I': 0, 'E': 0, 'O': 0},
            {'A': 0, 'I': 0, 'E': 0, 'O': 0}
        ]

        # Prepare the optimization loop
        dir_bias_values = [1, 0] if self.direction_bias_enabled else [0]

        for p_ent in [1, 0]:
            for dir_bias in dir_bias_values:
                for max_conf in max_confidence_grid:
                    self.p_entailment = p_ent
                    self.direction_bias = dir_bias
                    self.max_confidence = max_conf

                    score = 0
                    for elem in self.history:
                        item = elem[0]
                        truth = elem[1]

                        pred = self.predict(item)

                        if pred == truth:
                            score += 1

                    if score >= best_score:
                        best_score = score
                        best_p_ent = p_ent
                        best_dir_bias = dir_bias
                        best_max_conf = max_conf

        self.p_entailment = best_p_ent
        self.direction_bias = best_dir_bias
        self.max_confidence = best_max_conf
