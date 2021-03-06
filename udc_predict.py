import codecs
import os
import sys

import jieba
import numpy as np
import tensorflow as tf
from pybloom import BloomFilter

import udc_hparams
import udc_model
from models.dual_encoder import dual_encoder_model

# from termcolor import colored

tf.flags.DEFINE_string("model_dir", None, "Directory to load model checkpoints from")
tf.flags.DEFINE_string("vocab_processor_file", "./data/BoP2017_DBAQ_dev_train_data/vocab_processor.bin",
                       "Saved vocabulary processor file")

tf.flags.DEFINE_string(
    "input_dir", os.path.abspath("./data/BoP2017_DBAQ_dev_train_data/"),
    "Input directory containing original CSV data files (default = './data/BoP2017_DBAQ_dev_train_data/')")

tf.flags.DEFINE_string(
    "output_dir", os.path.abspath("./data/BoP2017_DBAQ_dev_train_data/"),
    "Output directory for TFrEcord files (default = './..data/BoP2017_DBAQ_dev_train_data/')")

FLAGS = tf.flags.FLAGS
DEV_PATH = os.path.join(FLAGS.input_dir, "dev.txt")

PREDICT_PATH = os.path.join(FLAGS.input_dir, "output.txt")
TEST_PATH = os.path.join(FLAGS.input_dir, "test.txt")

LINESEP = os.linesep

if not FLAGS.model_dir:
    print("You must specify a model directory")
    sys.exit(1)


# 结巴分词进行初始化
def init_jieba():
    # 加载用户词典
    jieba.load_userdict(os.path.join(FLAGS.input_dir, "userdict.txt"))
    pass


init_jieba()

bloomFilter = BloomFilter(capacity=100, error_rate=0.001)


# 加载停顿词
def load_stop_word():
    with codecs.open(os.path.join(FLAGS.input_dir, "stopword.txt"), 'rb', encoding='utf-8') as f:
        for line in f:
            bloomFilter.add(line.rstrip())


load_stop_word()


# 分词
def tokenizer_fn(iterator):
    # return (x.split(" ") for x in iterator)
    # # 精确模式 HMM 参数用来控制是否使用 HMM 模型  于未登录词，采用了基于汉字成词能力的 HMM 模型，使用了 Viterbi 算法
    for x in iterator:
        # seg_list = jieba.cut(x, cut_all=False, HMM=True)
        seg_list = jieba.cut(x, cut_all=True, HMM=True)  # 精确模式
        # seg_list = jieba.cut_for_search("小明硕士毕业于中国科学院计算所，后在日本京都大学深造")  # 搜索引擎模式
        # print('seg_list', seg_list)
        no_stop_list = remove_stop(seg_list)
        yield no_stop_list


# 去除停顿词
def remove_stop(seg_list):
    return [word for word in seg_list if word not in bloomFilter]


# Load vocabulary
vp = tf.contrib.learn.preprocessing.VocabularyProcessor.restore(
    FLAGS.vocab_processor_file)

INPUT_questions = {}
POTENTIAL_RESPONSES = []
last_question = None
is_first = True
with codecs.open(TEST_PATH, encoding='utf-8') as file:
    for line in file:
        line = line.rstrip()

        # label, question, answer = line.split('\t')
        # items = line.split('\t')
        # print('line: ', line)
        question, answer = line.split('\t')

        if is_first: #记录第一个问题
            last_question = question
            is_first = False

        if question != last_question:
            INPUT_questions[last_question] = POTENTIAL_RESPONSES
            POTENTIAL_RESPONSES = []

        POTENTIAL_RESPONSES.append(answer)

        last_question = question

print('len INPUT_questions: ', len(INPUT_questions))

# Load your own data here
# INPUT_question = "香港会议展览中心会展2期的屋顶的是由什么建成的，形状是什么？"
# POTENTIAL_RESPONSES = [
#     "香港会议展览中心（简称会展；英语：Hong Kong Convention and Exhibition Centre，缩写：HKCEC）是香港的主要大型会议及展览场地，位于香港岛湾仔北岸，是香港地标之一；由香港政府及香港贸易发展局共同拥有，由新创建集团的全资附属机构香港会议展览中心（管理）有限公司管理。",
#     "会展2期的屋顶以4万平方呎的铝合金造成，形状像是一只飞鸟。"]



def get_features(question, answer):
    question_matrix = np.array(list(vp.transform([question])))
    answer_matrix = np.array(list(vp.transform([answer])))
    question_len = len(question.split(" "))
    answer_len = len(answer.split(" "))
    features = {
        "question": tf.convert_to_tensor(question_matrix, dtype=tf.int64),
        "question_len": tf.constant(question_len, shape=[1, 1], dtype=tf.int64),
        "answer": tf.convert_to_tensor(answer_matrix, dtype=tf.int64),
        "answer_len": tf.constant(answer_len, shape=[1, 1], dtype=tf.int64),
    }
    return features, None


# 提交时间：2017年6月6日12:00am前
if __name__ == "__main__":

    # # Ugly hack, seems to be a bug in Tensorflow
    # # estimator.predict doesn't work without this line
    # estimator._targets_info = tf.contrib.learn.estimators.tensor_signature.TensorSignature(
    #   tf.constant(0, shape=[1,1])
    # )

    hparams = udc_hparams.create_hparams()
    model_fn = udc_model.create_model_fn(hparams, model_impl=dual_encoder_model)

    estimator = tf.contrib.learn.Estimator(model_fn=model_fn, model_dir=FLAGS.model_dir)

    predict_file = open(PREDICT_PATH, 'w', encoding='utf-8')
    for question, answers in INPUT_questions.items():
        for a in answers:
            prob = estimator.predict(input_fn=lambda: get_features(question, a))
            # print("prob float", float(prob))
            # print("prob list", list(prob))
            prob = list(prob)[0][0]
            # print("{} - {} : {}".format(question, a, prob))
            # write to file
            predict_file.write(str(prob) + LINESEP)

    # for question in INPUT_questions:
    #     answers = INPUT_questions.get(question)
    #     print("question: {}".format(question))
    #     for a in answers:
    #         prob = estimator.predict(input_fn=lambda: get_features(question, a))
    #         # print("prob float", float(prob))
    #         # print("prob list", list(prob))
    #         prob = list(prob)[0][0]
    #         print("prob ", prob)
    #         # write to file
    #         predict_file.write(str(prob) + LINESEP)
    predict_file.close()


    # predict_file = open(PREDICT_PATH, 'w', encoding='utf-8')
    # print("question: {}".format(INPUT_question))
    # for r in POTENTIAL_RESPONSES:
    #     prob = estimator.predict(input_fn=lambda: get_features(INPUT_question, r))
    #     # print("prob type", type(prob))
    #     prob = list(prob)[0][0]
    #     print("prob ", prob)
    #     #write to file
    #     predict_file.write(str(prob) + LINESEP)
    #     # print("prob ", list(prob)[0].sum())
    #     # print("{}: {}".format(r, prob.next()[0]))
    # predict_file.close()