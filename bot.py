# from flask import Flask, request
# from pymessenger.bot import Bot
import ConfigParser as cp
from collections import OrderedDict

import aiml
import nltk

# nltk.download('punkt')
# nltk.download('averaged_perceptron_tagger')

# os.environ['SCR_ROOT'] = os.path.abspath(os.path.join(__file__))
# sys.path.append(os.environ['SCR_ROOT'])

cfg = None
fix = 0
app = None
bot = None
mozg = None
current_state = 'problem_description'
prev_state = 'problem_description'
stage_1 = {
    'problem_description': None,
    'problem_objects': set(),
    'environment_objects': set(),
    'undesired_effect': None,
    'so_what': set(),
    'why': set(),
    'potential_objects': set()
}
dones = OrderedDict([
    ('problem_description_done', 0),
    ('problem_objects_done', 0),
    ('environment_objects_done', 0),
    ('undesired_effect_done', 0),
    ('so_what_done', 0),
    ('why_done', 0)
])
stage_1_done = False
stage_2 = dict()


def start(state):
    global mozg
    mozg = aiml.Kernel()
    mozg.learn("std_startup.xml")
    mozg.respond("load aiml b")
    mozg.learn(state + '.aiml')
    return mozg

def calculate_response(input):
    r = mozg.respond(input).split("\\n")
    res = list()
    for i in r:
        if "And what about" in i:
            if "potential_objects" in stage_1.keys() \
                    and len(stage_1["potential_objects"]) != 0:
                res.append("Bot: " + str(i) + ", ".join(stage_1["potential_objects"])
                           + "?..")
        else:
            res.append("Bot: " + str(i))
    return res

def get_variable(aiml_name):
    return str(mozg.getPredicate(aiml_name))

def parse_config(cnf_file):
    global cfg
    cfg = cp.RawConfigParser()
    cfg.read(cnf_file)


# app = Flask(__name__)
# ACCESS_TOKEN = 'EAAGwTQv0Us8BABYVAdDsACx0rDQctPJs88X4AEmE9xqU6vqyI48AcCuVl8sIRG0ZArOZAK2ZB5mHQObmAXYEoZBwAhrff4ZCRES5zBck3PXB0Ee3ZCRuJThAUHKVIUuKmUKmPYQ95tH43Jv6kOA9i5PPwve2ZCc0z4rCF0ypIxYwQZDZD'
# VERIFY_TOKEN = '6eextR37a81QUwt1vK1Kx_7L94tNN73XiewAyH45QbF'
# bot = Bot(ACCESS_TOKEN)


# receive messages that Facebook sends bot at this endpoint
# # @app.route("/", methods=['GET', 'POST'])
# def receive_message():
#     if request.method == 'GET':
#         # Facebook implementation of a verify token that confirms all requests that your bot receives came from Facebook
#         token_sent = request.args.get("hub.verify_token")
#         return verify_fb_token(token_sent)
#     else:
#         # get whatever message a user sent the bot
#         output = request.get_json()
#         for event in output['entry']:
#             messaging = event['messaging']
#             for message in messaging:
#                 if message.get('message'):
#                     # Facebook Messenger ID for user so we know where to send response back to
#                     recipient_id = message['sender']['id']
#                     if message['message'].get('text'):
#                         response_sent_text = get_message(message['message'].get('text'))
#                         send_message(recipient_id, response_sent_text)
#                     # if user sends us a GIF, photo,video, or any other non-text item
#                     if message['message'].get('attachments'):
#                         response_sent_nontext = get_message()
#                         send_message(recipient_id, response_sent_nontext)
#     return "Message Processed"


# def verify_fb_token(token_sent):
#     # take token sent by facebook and verify it matches the verify token you sent
#     # if they match, allow the request, else return an error
#     if token_sent == VERIFY_TOKEN:
#         return request.args.get("hub.challenge")
#     return 'Invalid verification token'

def evaluate_variables():
    global stage_1, dones, fix, mozg
    try:
        if get_variable('fix') == '1':
            fix = 1
    except Exception as e:
        pass
    for k in stage_1.keys():
        try:
            if type(stage_1[k]) is set:
                v = get_variable(k).strip()
                varr = [x.strip() for x in v.split(",")]
                for v in varr:
                    if v != '':
                        already_there = 0
                        for i in [x for x in stage_1.keys() if x != k]:
                            if type(stage_1[i]) is set:
                                if v in stage_1[i]:
                                    already_there = 1
                        if not already_there:
                            if v in stage_1[k]:
                                stage_1[k].remove(v)
                            else:
                                stage_1[k].add(v)
            else:
                stage_1[k] = get_variable(k).strip()
                if k == 'problem_description' and len(stage_1['potential_objects']) == 0:
                    is_noun = lambda pos: pos[:2] == 'NN'
                    tokenized = nltk.word_tokenize(stage_1[k])
                    stage_1['potential_objects'] = set(
                        [word for (word, pos) in nltk.pos_tag(tokenized) if is_noun(pos)]
                    )

                    # mozg.setBotPredicate("potential_objects",
                    #                      ", ".join(stage_1['potential_objects']) + ", etc...")
        except Exception as e:
            print "got exception", str(e)
            pass
    for d in dones.keys():
        try:
            dones[d] = int(get_variable(d).strip())
        except Exception as e:
            pass

def print_data():
    print "Variables: ", stage_1
    print "Stage: ", dones

def get_message(input):
    global current_state, prev_state, fix, stage_1_done
    if input == 'print all':
        print_data()
        return ''
    reply = calculate_response(input)
    evaluate_variables()
    for k in stage_1.keys():
        # print "set predicate {} to {}".format(k, stage_1[k])
        if type(stage_1[k]) is set:
            mozg.setBotPredicate(k, ", ".join(stage_1[k]))
        else:
            mozg.setBotPredicate(k, stage_1[k])
    for d in dones.keys():
        if dones[d] == 0:
            prev_state = current_state
            current_state = d.rstrip('_done')
            # print "learning ", current_state
            mozg.learn(current_state + '.aiml')
            break
        # else:
        #     stage_1_done = True
        #     mozg.start("solution_root.aiml")
    if fix == 1:
        fix = 0
        mozg.setBotPredicate('fix', '0')
    return reply

def local_run():
    print "Starting a test run..."
    while 1:
        res = get_message(raw_input("You: "))
        for r in res:
            print r

# # uses PyMessenger to send response to user
# def send_message(recipient_id, response):
#     # sends user the text message provided via input response parameter
#     bot.send_text_message(recipient_id, response)
#     return "success"

if __name__ == "__main__":
    # if len(sys.argv) < 2 or not os.path.isfile(sys.argv[1]):
    #     print(sys.argv[1])
    #     print("-E- no configuration file provided")
    #     sys.exit(1)
    # app.run()
    global stage_1, dones, current_state, mozg, prev_state
    # print current_state
    mozg = start(current_state)
    local_run()

