import sys
sys.path.append('rehastim-lib/ems_interface/modules/')
sys.path.append('rehastim-lib/ems_interface/tools-and-abstractions/')
import singlepulse
import SerialThingy
import time
import csv
import os
import pygame

import threading

from datetime import datetime

from pythonosc import osc_server
from pythonosc import udp_client
from pythonosc import dispatcher

import pandas as pd

FAKE_SERIAL = False         # False = using actual rehastim hardware 
debug = False
log_data = True
show_results = False
flip_condition_order = True # flipping sequence order to help counterbalance, experimenter can just keep runnint practice, cond#1 and cond#2

user_id = 0

target_bpm  = 50 # 50 for study and 30 for getting use to

# paths
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

### ---- N-Back Variables  ---- ####
# n
n_back = 2 

# stimulus sequence
chosen_sequence     = []
stimulus_sequences  = [['C', 'J', 'C', 'J', 'A', 'B', 'M', 'K', 'M', 'L'],
                       ['B', 'F', 'K', 'H', 'K', 'H', 'R', 'B', 'M', 'B', 'M', 'F', 'R', 'F', 'Q', 'X', 'Q', 'B', 'Q', 'F', 'R', 'X', 'H', 'X', 'K', 'Q', 'K', 'H', 'R', 'M', 'X', 'M'],
                       ['M', 'B', 'M', 'K', 'B', 'R', 'B', 'R', 'F', 'H', 'R', 'H', 'K', 'H', 'M', 'F', 'M', 'Q', 'K', 'X', 'H', 'X', 'K', 'Q', 'F', 'B', 'F', 'R', 'Q', 'X', 'Q', 'X']]
                    #   '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',

# stimulus duration
Stimulus_duration = 500 #1000 # milliseconds
# intertrial interval
Intertrial_interval = 2500 #500 # milliseconds
### ---- N-Back Variables  ---- ####

### ---- EMS variables ---- ###
serial_response_active = False
pulse_count = 5
delay = 0.0098 # 9,800 uS
EMS_on = False

#default [CH, PW, mA]
EMS_ch = [[1, 300, 8],
          [2, 400, 8],
          [3, 250, 6],
          [4, 250, 6]]

# EMS pattern sequence
pattern_sequence = [2, 3, 1, 0, # 0 - Left, 1 - Right, 2 - Up, 3 - Down
                    3, 2, 0, 1] 
pattern_delay = 1
pattern_pulsecount = 20
### ---- EMS variables ---- ###

### ---- pygame variables ---- ###
# Set the dimensions of the screen
screen_width = 800
screen_height = 600

# Define some colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
### ---- pygame variables ---- ###

### ----- OSC settings ----- ###
server_ip = "0.0.0.0"
server_port = 5006
client_ip = "127.0.0.1"
client_port = 5008

# OSC addresses
osc_start_trial = "/start"
osc_nback_log   = "/nback"
osc_unity       = "/start_nback"

msg_from_unity = None
start_nback = False

def start_trial():
    client.send_message(osc_start_trial, "1")
    print("Start trial!")

def log_nback(msg):
    client.send_message(osc_nback_log, msg)

def print_handler(address, *args):
    global start_nback
    if address == osc_unity:
        msg = args[0]
        print(msg)
        if msg == "1":
            start_nback = True
    # global msg_from_unity
    # msg_from_unity = args
    print(f"Receive message from {address}: {args}")
### ----- OSC settings ----- ###

def calibrate_EMS():
    global EMS_ch
    channel = 0
    calibrated_done = False

    while not calibrated_done:
        screen.fill(BLACK)
        ems_calib_txt = font.render(str(EMS_ch), True, WHITE)
        prompt0 = font.render("Calibrating channel " + str(channel + 1), True, WHITE)
        prompt1 = font.render("Current intensity: " + str(EMS_ch[channel][2]), True, WHITE)
        prompt2 = font.render('[s] to save and exit', True, WHITE)
        prompt3 = font.render('[space] to stimulate', True, WHITE)
        screen.blit(ems_calib_txt,(10,10))
        screen.blit(prompt0, (screen_width // 2 - prompt0.get_width() // 2, 100))
        screen.blit(prompt1, (screen_width // 2 - prompt1.get_width() // 2, 200))
        screen.blit(prompt2, (10, 300))
        screen.blit(prompt3, (10, 300 + prompt2.get_height()))
        pygame.display.flip()

        # listen to inputs
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                quit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    quit()
                elif event.key == pygame.K_UP:                   
                    EMS_ch[channel][2] += 1
                elif event.key == pygame.K_DOWN:
                    EMS_ch[channel][2] -= 1

                elif event.key == pygame.K_LEFT:
                    channel -= 1
                    if channel < 0:
                        channel = 3
                elif event.key == pygame.K_RIGHT:
                    channel += 1
                    if channel > 3:
                        channel = 0

                elif event.key == pygame.K_s:
                    # Save for current channel
                    # calibrated_ch[channel] = True
                    calibrated_done = True

                elif event.key == pygame.K_SPACE:
                    # Generate 20 pulses
                    for i in range(20):
                        time.sleep(delay)
                        # Generate a single pulse
                        pulse = [EMS_ch[channel][0], EMS_ch[channel][1], EMS_ch[channel][2]]
                        ems.write(singlepulse.generate(*pulse))
            
    # save calibration in text file
    with open(user_calib, 'w') as file:
        for channel in EMS_ch:
            file.write(','.join(map(str, channel)) + '\n')

    print("Calibration done!")
    print(EMS_ch)

# EMS pattern according the predefined sequence
def pattern_EMS():
    print("EMS Pattern starting")
    global game_over
    while not game_over:
        for direction in pattern_sequence:
            for i in range(pattern_pulsecount):
                pulse = [EMS_ch[direction][0], EMS_ch[direction][1], EMS_ch[direction][2]]
                ems.write(singlepulse.generate(*pulse))

                time.sleep(delay)
            time.sleep(pattern_delay)

def main():
    global ems, EMS_on, EMS_ch
    global screen, font, debug

    global target_bpm

    global user_calib

    global start_nback

    global game_over

    # local variables
    start_screen = True
    game_over = False

    time_left = 3
    trial_time = 30
    start_screen = True

    last_direction = None
    last_time = 0
    last_time_ems = 0

    text_color = WHITE

    channel = -1

    # init EMS
    ems = SerialThingy.SerialThingy(FAKE_SERIAL)
    if len(sys.argv) > 1:
            ems.open_port(str(sys.argv[1]),serial_response_active) # pass the port via the command line, as an argument
    else:
            ems.open_port(serial_response_active)

    # init EMS thread    
    pattern_EMS_thread = threading.Thread(target=pattern_EMS)
    pattern_EMS_thread.daemon = True

    # init pygame
    pygame.init()

    # Set the font for displaying text
    font = pygame.font.Font(None, 50)
    font_big = pygame.font.Font(None, 100)

    screen = pygame.display.set_mode((screen_width, screen_height))

    # init csv
    # create directory and result file in csv
    user_file   = "study1-user_" + str(user_id)
    user_dir    = ROOT_DIR + '/raw_data/' + user_file
    user_calib  = user_dir + '/ems_calib.txt'

    # retrieve EMS clibration from the text file
    try:
        EMS_ch = []
        with open(user_calib, 'r') as file:
            for line in file:
                channel_data = list(map(int, line.strip().split(',')))
                EMS_ch.append(channel_data)
                print(EMS_ch)
    except OSError as e:
        print("No EMS calibration found! ")
        EMS_ch = [[1, 300, 8],
                  [2, 400, 8],
                  [3, 250, 6],
                  [4, 250, 6]]

    # setup folder per user
    raw_data_header = ['current trial','trial start time','user input','response status', 'response time', 'current stimulus', 'n back','elapsed time']
    try:
        os.makedirs(user_dir) # allows to make intermediate directories
    except OSError as e:
        print("Caution: directory already exists: " + str(e))

    mode = -1 # 0: practice, 1: condition #1, 2: condition #2
    mode_text = ["practice", "condition1", "condition2"]
    mode_text_color = [text_color, text_color, text_color]

    while start_screen:
        screen.fill(BLACK)

        if EMS_on:
            EMS_on_color = GREEN
        else:
            EMS_on_color = RED
        EMS_on_text = font.render("EMS status: " + str(EMS_on), True, EMS_on_color)
        screen.blit(EMS_on_text, (10, 10))

        for index, color in enumerate(mode_text_color):
            if index == mode:
                mode_text_color[index] = GREEN
            else:
                mode_text_color[index] = text_color

        prompt0 = font.render("[1] practice", True, mode_text_color[0])
        prompt1 = font.render("[2] condition 1", True, mode_text_color[1])
        prompt2 = font.render("[3] condition 2", True, mode_text_color[2])
        prompt3 = font.render("[c] calibration", True, WHITE)
        prompt4 = font.render("[e] EMS on/off", True, WHITE)

        mode_text_height = 300
        ems_text_heght = 500
        screen.blit(prompt0, (10, mode_text_height))
        screen.blit(prompt1, (10, mode_text_height + prompt0.get_height()))
        screen.blit(prompt2, (10, mode_text_height + 2 * prompt0.get_height()))
        screen.blit(prompt3, (10, ems_text_heght))
        screen.blit(prompt4, (10, ems_text_heght + prompt3.get_height()))
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                quit()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    quit()
                elif event.key == pygame.K_RETURN:
                    print("Starting countdown!")
                    start_screen = False
                elif event.key == pygame.K_c:
                    print("Entering calibration mode")
                    calibrate_EMS()
                elif event.key == pygame.K_e:
                    EMS_on = not EMS_on
                    print(EMS_on)
                elif event.key == pygame.K_1:
                    print("practice mode")
                    mode = 0
                    target_bpm = 30
                elif event.key == pygame.K_2:
                    print("condition 1 mode")
                    if flip_condition_order:
                        mode = 2
                    else:
                        mode = 1
                elif event.key == pygame.K_3:
                    print("condition 2 mode")
                    if flip_condition_order:
                        mode = 1
                    else:
                        mode = 2
                elif event.key == pygame.K_d:
                    debug = not debug

        # Wait for a short amount of time to limit the frame rate
        pygame.time.wait(10)

    # Start countdown
    while time_left > 0:
        screen.fill(BLACK)
        countdown_text = font_big.render(str(time_left), True, WHITE)
        screen.blit(countdown_text, (screen_width // 2 - countdown_text.get_width() // 2, screen_height // 2 - countdown_text.get_height() // 2))
        pygame.display.flip()
        time.sleep(1)
        time_left -= 1

    
    # Start the trial
    start_trial()

    # Start the pattern
    if EMS_on:
        pattern_EMS_thread.start()

    screen.fill(BLACK)
    wait_text = font.render("do the pattern correctly twice", True, WHITE)
    screen.blit(wait_text, (screen_width // 2 - wait_text.get_width() // 2, screen_height // 2 - wait_text.get_height() // 2))
    pygame.display.flip()

    # wait for Unity signal
    while not start_nback:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                quit()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    quit()
                elif event.key == pygame.K_RETURN:
                    print("Starting countdown!")
                    start_nback = True
    
    
    ### n-back Loop ###
    chosen_sequence = stimulus_sequences[mode]
    task_start_time = time.time()
    user_input = []
    response_time = -1
    response_status = "None"

    correct_count = 0
    incorrect_count = 0
    no_input_count = 0

    response_log = []

    screen.fill(BLACK)
    
    for trial in range(len(chosen_sequence)):            
        
        # Display current stimulus
        current_stimulus = chosen_sequence[trial]
        stimulus_text = font_big.render(current_stimulus, True, text_color)
        stimulus_rect = stimulus_text.get_rect(center=screen.get_rect().center)
        screen.blit(stimulus_text, stimulus_rect)

        instructions = "[<] yes      [>] no"
        instruction_text = font.render(instructions, True, WHITE)
        screen.blit(instruction_text, (10, 500))

        pygame.display.flip()

        despawn_letter = False
        user_input = []

        trial_start_time = time.time() - task_start_time

        while (True):
            trial_current_time = (time.time() - task_start_time) - trial_start_time

            # stimulus time 
            if trial_current_time >= Stimulus_duration / 1000 and not despawn_letter:                    
                stimulus_rect_area = screen.fill(BLACK, rect=stimulus_rect)
                pygame.display.update(stimulus_rect_area)
                pygame.display.flip()
                despawn_letter = True

            # Intertrial interval
            if trial_current_time >= (Intertrial_interval + Stimulus_duration) / 1000:
                break

            # track user input: left = is n-back, right = not n-back
            for event in pygame.event.get():

                if event.type == pygame.KEYDOWN:
                    response_time = (time.time() - trial_start_time - task_start_time)

                    if event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        quit()
                    elif event.key == pygame.K_LEFT:
                        user_input.append(['is_n-back', response_time])
                    elif event.key == pygame.K_RIGHT:
                        user_input.append(['not_n-back', response_time])

            elapsed_time = (time.time() - task_start_time)
            pygame.time.wait(10)

        # ignore the first n=2 letters
        if trial >= n_back and len(user_input) != 0:

            if current_stimulus == chosen_sequence[trial - n_back]: # when it's n-back
                if user_input[-1][0] == 'is_n-back':

                    correct_count += 1
                    response_status = 'Correct'
                    if show_results:
                        print("Correct.")
                else:
                    incorrect_count += 1
                    response_status = 'Incorrect'
                    if show_results:
                        print("Incorrect.")
                
            elif current_stimulus != chosen_sequence[trial - n_back]: # when it's NOT n-back
                if user_input[-1][0] == 'not_n-back':

                    correct_count += 1
                    response_status = 'Correct'
                    if show_results:
                        print("Correct.")
                else:
                    incorrect_count += 1
                    response_status = 'Incorrect'
                    if show_results:
                        print("Incorrect.")
        
        if trial >= n_back and len(user_input) == 0:

            no_input_count += 1
            response_status = 'No input'
            if show_results:
                print("No input.")

        # End of trial log
        if show_results:
            print('current trial', trial, 'trial start time:', trial_start_time, 'user input:', user_input, 'response status: ', response_status,\
                'response time:', response_time, 'current stimulus:', current_stimulus, 'n back:', chosen_sequence[trial - n_back], 'elapsed time:', elapsed_time)
        
        if user_input:
            for input in user_input:
                trial_log = [trial,  trial_start_time,  input[0],  response_status,\
                    input[1],  current_stimulus,  chosen_sequence[trial - n_back],  elapsed_time]
                
                response_log.append(trial_log)
                
                ## OSC send log message
                log_nback(trial_log)   

        else:
            trial_log = [trial,  trial_start_time,  user_input,  response_status,\
                response_time,  current_stimulus,  chosen_sequence[trial - n_back],  elapsed_time]       
                        
            response_log.append(trial_log)

            ## OSC send log message
            log_nback(trial_log)        

        print('------------------------------------------------')

    ## End of task summary
    if show_results:
        print('correct count', correct_count, 'incorrect count', incorrect_count, 'no input count', no_input_count)

    if log_data:
        response_log_df = pd.DataFrame(response_log, columns=raw_data_header)
        log_filename =  user_dir + "/" + str(user_id) + '_' + mode_text[mode] + '_log' + datetime.now().strftime('%Y%m%d_%H%M') + '.csv'
        response_log_df.to_csv(log_filename, index= True)

        response_summary = [[correct_count, incorrect_count,no_input_count]]
        summary_column = ['correct count','incorrect count','no input count']
        response_summary_df = pd.DataFrame(response_summary, columns=summary_column)
        summary_filename = user_dir + "/" + str(user_id) + '_' + mode_text[mode] + '_summary' + datetime.now().strftime('%Y%m%d_%H%M') + '.csv'
        response_summary_df.to_csv(summary_filename, index = True)


    # Update the display
    pygame.display.update()

    game_over = True

    if EMS_on:
        pattern_EMS_thread.join()

    # display game over
    screen.fill(BLACK)
    final_score_text = font.render("Over!", True, WHITE)
    screen.blit(final_score_text, (screen_width // 2 - final_score_text.get_width() // 2, 200))
    pygame.display.update()

    # pygame.time.wait(5000)
    # break

    # Wait for player to press Escape
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                quit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    quit()

    # Quit the game
    pygame.quit()


if __name__ == "__main__":
    # start OSC client
    client = udp_client.SimpleUDPClient(client_ip, client_port)

    # start OSC server in a thread
    dispatcher = dispatcher.Dispatcher()
    dispatcher.map(osc_unity, print_handler)
    server = osc_server.ThreadingOSCUDPServer((server_ip, server_port), dispatcher)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    print("open an OSC server at " + server_ip + ":" + str(server_port))

    main()
