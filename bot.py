import re
import ConfigParser as cp
from collections import OrderedDict

import aiml
import nltk
import os
from slackclient import SlackClient
import time

# instantiate Slack client
slack_client = SlackClient('xoxb-797083585488-784313694066-Jf7KidV9pSXJPfWYHL35I0kp')
bot_id = None

# constants
RTM_READ_DELAY = 1 # 1 second delay between reading from RTM
EXAMPLE_COMMAND = "do"
MENTION_REGEX = "^<@(|[WU].+?)>(.*)"

# nltk.download('punkt')
# nltk.download('averaged_perceptron_tagger')

# os.environ['SLACK_BOT_TOKEN'] = 'xoxp-797083585488-799291757910-797098294005-b891a02d8e3da1035aa5c48b9dcc47da'
# os.environ['SLACK_BOT_TOKEN'] = 'xoxb-797083585488-784313694066-F4g3LX8A4lDQ4p9hCw3LWm8f'
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
                res.append(str(i) + ", ".join(stage_1["potential_objects"])
                           + "?..")
        else:
            res.append(str(i))
    return res

def get_variable(aiml_name):
    return str(mozg.getPredicate(aiml_name))

def parse_config(cnf_file):
    global cfg
    cfg = cp.RawConfigParser()
    cfg.read(cnf_file)

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


def parse_direct_mention(message_text):
    """
        Finds a direct mention (a mention that is at the beginning) in message text
        and returns the user ID which was mentioned. If there is no direct mention, returns None
    """
    matches = re.search(MENTION_REGEX, message_text)
    # the first group contains the username, the second group contains the remaining message
    return (matches.group(1), matches.group(2).strip()) if matches else (None, None)

def handle_command(command, channel):
    """
        Executes bot command if the command is known
    """
    # Default response is help text for the user
    default_response = ["Not sure what you mean... :cry:", "Try to say say something else."]

    # Finds and executes the given command, filling in response
    response = get_message(command)
    # Sends the response back to the channel
    if not response:
        slack_client.api_call(
            "chat.postMessage",
            channel=channel,
            text=default_response
        )
    else:
        for r in response:
            slack_client.api_call(
                "chat.postMessage",
                channel=channel,
                text=r
            )

def parse_bot_commands(slack_events):
    """
        Parses a list of events coming from the Slack RTM API to find bot commands.
        If a bot command is found, this function returns a tuple of command and channel.
        If its not found, then this function returns None, None.
    """
    for event in slack_events:
        if event["type"] == "message" and not "subtype" in event:
            print "in parse bot command event is: " + str(slack_events)
            user_id, message = parse_direct_mention(event["text"])
            if user_id == bot_id:
                return message, event["channel"]
    return None, None

if __name__ == "__main__":
    global stage_1, dones, current_state, mozg, prev_state
    mozg = start(current_state)
    # local_run()
    a = slack_client.rtm_connect(token='xoxb-797083585488-784313694066-Jf7KidV9pSXJPfWYHL35I0kp',
                                 with_team_state=False)
    print(a)
    if a:
        print("SIT Bot connected and running!")
        # Read bot's user ID by calling Web API method `auth.test`
        auth = slack_client.api_call("auth.test")
        print auth
        bot_id = auth["user_id"]
        print("Got bot id: " + str(bot_id))
        while True:
            command, channel = parse_bot_commands(slack_client.rtm_read())
            # print("Command {}, channel {}".format(command, channel))
            if command:
                handle_command(command, channel)
            time.sleep(RTM_READ_DELAY)
    else:
        print("Connection failed. Exception traceback printed above.")
