import glob
import json
import logging
import random
from itertools import groupby
from multiprocessing import Manager, Queue, Process, get_logger
from typing import Dict, Iterable, List

from allennlp.common.util import pad_sequence_to_length
from allennlp.data import DatasetReader, TokenIndexer, Tokenizer, Instance, TokenType, Token, Vocabulary, DataIterator
from allennlp.data.dataset import Batch
from allennlp.data.fields import TextField, ListField, MultiLabelField

logger = get_logger()  # pylint: disable=invalid-name
logger.setLevel(logging.INFO)


@DatasetReader.register("parallel_reader")
class ParallelLoader(DatasetReader):

    def _file_reader(self, output: Queue, file_path: str):
        items = 0
        for instance in self.reader._read(file_path):
            items += 1
            output.put(instance)

        output.put(items)

    def _read(self, file_path: str) -> Iterable[Instance]:
        """
        Assume file_path is actually prefix for real data files

        :param file_path:
        :return:
        """
        files = glob.glob(file_path)
        if len(files) == 1:
            yield from self.reader._read(files[0])
        else:
            manager = Manager()
            output_queue = manager.Queue(self.output_queue_size)

            for file in files:
                args = (output_queue, file)
                process = Process(target=self._file_reader, args=args)
                if len(self.running_processes) < self.parallel:
                    process.start()
                    self.running_processes.append(process)
                else:
                    self.waiting_processes.append(process)

            num_finished = 0
            while num_finished < len(files):
                item = output_queue.get()
                if isinstance(item, int):
                    num_finished += 1
                    logger.info(f"worker {item} finished ({num_finished} / {len(files)})")

                    if len(self.waiting_processes) > 0:
                        process = self.waiting_processes.pop()
                        process.start()
                        self.running_processes.append(process)
                else:
                    yield item

            for process in self.running_processes:
                process.join()
            self.running_processes.clear()

    def text_to_instance(self, *inputs) -> Instance:
        return self.reader.text_to_instance(*inputs)

    def __init__(self, reader: DatasetReader, parallel: int = 1, output_queue_size: int = 1000):
        super().__init__(lazy=True)
        self.output_queue_size = output_queue_size
        self.parallel = parallel
        self.reader: DatasetReader = reader

        self.waiting_processes: List[Process] = []
        self.running_processes: List[Process] = []


@DatasetReader.register("mention_categories")
class MenionsLoader(DatasetReader):

    def _read_lines(self, file_path: str):

        with open(file_path) as fd:
            for line in fd:
                category_tag, left_sent, mention, right_sent = line.strip(' ').split('\t')
                sent = f"{left_sent.strip()} {self.left_tag} {mention.strip()} {self.right_tag} {right_sent.strip()}"
                yield sent, category_tag

    def _read(self, file_path: str) -> Iterable[Instance]:
        for category_tag, sentences in groupby(self._read_lines(file_path), key=lambda x: x[1]):
            sentences = [s[0] for s in sentences]
            sentences = random.choices(sentences, k=self.sentence_sample)
            yield self.text_to_instance(sentences, category_tag)

    def text_to_instance(self, sentences: List[str], category_tag: str) -> Instance:
        categories = self.category_mapping.get(category_tag)

        sentence_fields = []
        for sentence in sentences:
            tokenized_sentence = self.tokenizer.tokenize(sentence)
            sent_field = TextField(tokenized_sentence, self.token_indexers)
            sentence_fields.append(sent_field)

        return Instance({
            'sentences': ListField(sentence_fields),
            'categories': MultiLabelField(categories)
        })

    def __init__(
            self,
            category_mapping_file: str,
            token_indexers: Dict[str, TokenIndexer],
            tokenizer: Tokenizer = None,
            sentence_sample: int = 5,
            left_tag: str = '@@mb@@',
            right_tag: str = '@@me@@'
    ):
        super().__init__(lazy=True)
        self.category_mapping_file = category_mapping_file
        with open(category_mapping_file) as fd:
            self.category_mapping = json.load(fd)

        self.right_tag = right_tag
        self.left_tag = left_tag
        self.tokenizer = tokenizer
        self.token_indexers = token_indexers
        self.sentence_sample = sentence_sample


@DatasetReader.register("vocab_mention_categories")
class VocabMentionsLoader(MenionsLoader):

    def _read(self, file_path: str) -> Iterable[Instance]:
        for sent, category_tag in self._read_lines(file_path):
            yield self.text_to_instance(sent, category_tag)

    def text_to_instance(self, sentence: str, category_tag: str) -> Instance:
        categories = self.category_mapping.get(category_tag)

        tokenized_sentence = self.tokenizer.tokenize(sentence)
        sent_field = TextField(tokenized_sentence, self.token_indexers)

        return Instance({
            'sentences': sent_field,
            'categories': MultiLabelField(categories)
        })