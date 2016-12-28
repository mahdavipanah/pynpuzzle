#!/usr/bin/env python3
"""
pynpuzzle - Solve n-puzzle with Python

Version : 1.0.0
Author : Hamidreza Mahdavipanah
Repository: http://github.com/mahdavipanah/pynpuzzle
License : MIT License
"""
import math
import random
import re
import webbrowser
import sys
import traceback
from os import listdir
from os.path import isfile, join
import datetime
from importlib import import_module
import multiprocessing
import threading
import time
from copy import deepcopy

import tkinter
from tkinter import ttk
from tkinter import messagebox
from tkinter import simpledialog
from tkinter import filedialog, scrolledtext

import psutil

# Global variables
#
# Stores app logs
LOGS = []
# Loaded algorithms modules from ./algorithm/ folder
algorithms_modules = []
# Process that runs the algorithm
# If it's None it means app is not calculating
# If it's not None it contains multiprocessing.Process object and app is calculating
search_process = None
# An event object that tells the timer thread to stop
timer_event = multiprocessing.Event()
# The thread that updates execution time, max ram usage and ram usage information
timer_thread = None
# The thread that is waiting for the algorithm to send it's result
pipe_thread = None
# A pipe which algorithm can send it's result to app through it
output_pipe = None
# A list containing current output steps's statuses
OUTPUT_LST = []
# Number of current output's step
OUTPUT_STEP = 0
# An event object that tells the play thread to stop
play_event = None
# The thread that plays output steps one by one
play_timer = None
# A ScrolledText widget that contains application logs and is inside show logs window
logs_text = None
# Goal state
GOAL_STATE = [i for i in range(9)]
# Show logs window
logs_window = None
# About window
about_window = None
# Controls whether the output text validation is enable or not
# For the sake of user experience, output entries are not disabled and instead are bound to a validation method
#   That always returns false, but sometimes the app itself wants to change the entries values, so temporarily
#   changes this variable's value to true
OUTPUT_EDITABLE = False
# Indicates whether timer thread should clear status bar or not (It's useful when some problems happened)
timer_clear_status_bar = False

# Main window
main_window = tkinter.Tk()
main_window.title("pynpuzzle - Solve n-puzzle with Python")
main_window.grid_rowconfigure(2, weight=1)
main_window.grid_columnconfigure(0, weight=1, uniform=1)
main_window.grid_columnconfigure(1, weight=1, uniform=1)
# Main window size configurations
main_window.minsize(width=840, height=360)
main_window.geometry("840x360")

# Status bar variables that are bound to status bar labes
max_ram_var = tkinter.StringVar()
cpu_var = tkinter.StringVar()
ram_var = tkinter.StringVar()
available_ram_var = tkinter.StringVar()


def return_false_validate():
    """
    Validation function for output entry widgets.

    Returns OUTPUT_EDITABLE global variable.
    """
    return OUTPUT_EDITABLE


def draw_puzzle(puzzle_frame, n, read_only=False):
    """
    Fills a frame widget with n + 1 entry widget.

    puzzle_frame : The puzzle frame to get filled by entry widgets.
    n : Puzzle type (n-puzzle).
    read_only : Should widgets be read-only or not
    """
    n = int(math.sqrt(n + 1))

    for i in range(n):
        for j in range(n):
            entry = tkinter.Entry(puzzle_frame, width=4, justify='center')
            entry.grid(row=i, column=j, sticky='WENS')

            if read_only:
                # Bind the widget validation command to return_false_validate command and therefore
                #   OUTPUT_EDITABLE global variable.
                entry.config(validatecommand=return_false_validate, validate=tkinter.ALL)

        puzzle_frame.grid_columnconfigure(i, weight=1)
        puzzle_frame.grid_rowconfigure(i, weight=1)


def config_frame_state(frame, state):
    """
    Changes the status property of a frame children.
    """
    for child in frame.winfo_children():
        # Only output_play_button can change output_stop_button's state
        if child is output_stop_button:
            # If output is playing right now
            if play_event:
                # Someone wants to disable the output frame, so output play must stop
                play_event.set()
            continue

        child['state'] = state

    # output_0_label's and output_to_label's cursor property are depending on their frame status
    if frame is output_action_frame:
        cursor = 'arrow'
        if state == tkinter.NORMAL:
            cursor = 'fleur'
        output_0_label['cursor'] = cursor
        output_to_label['cursor'] = cursor


def config_io_frame_state(frame, state):
    """
    A special function only for changing the state of output or input label
    """
    if frame is output_labelframe:
        # For the sake of user experience output entry widgets are not getting disabled and instead their values
        #   Are not editable
        config_frame_state(output_action_frame, state)
    else:
        config_frame_state(input_puzzle_frame, state)
        config_frame_state(input_action_frame, state)


def create_puzzle_frame(parent_frame, n, current_puzzle_frame=None, read_only=False):
    """
    Creates a new puzzle frame inside a parent frame and if the puzzle frame already exists, first destroys it.
    This is done because when the n changes we have to change the puzzle frame's grid row and column configurations
    and it turned out in tkinter it can be done by recreating the frame widget!

    Returns the newly created puzzle frame.
    """
    if current_puzzle_frame:
        current_puzzle_frame.destroy()

    puzzle_frame = tkinter.Frame(parent_frame)
    puzzle_frame.grid(row=0, column=0, sticky='WENS')

    draw_puzzle(puzzle_frame, n, read_only)

    return puzzle_frame


def fill_puzzle_frame(puzzle_frame, lst):
    """
    Fills a puzzle frame with a puzzle list.
    """
    global OUTPUT_EDITABLE

    lst = lst[:]
    lst = ['' if x == 0 else x for x in lst]

    # Enable editing the output puzzle temporarily
    OUTPUT_EDITABLE = True
    i = 0
    for child in puzzle_frame.winfo_children():
        child.delete(0, tkinter.END)
        child.insert(0, lst[i])

        if puzzle_frame is output_puzzle_frame and lst[i] == '':
            child['highlightbackground'] = 'Orange'
        elif puzzle_frame is output_puzzle_frame:
            # Change the child's highlightbackground color to entry widget's default property using another
            #   entry widget which we are sure has default property's value
            child['highlightbackground'] = output_step_text['highlightbackground']

        i += 1
    # Disable editing the output puzzle
    OUTPUT_EDITABLE = False


def list_to_puzzle(lst):
    """
    Converts a one dimensional puzzle list and returns it's two dimensional representation.

    [1, 2, 3, 4, 5, 6, 7, 8, 0] --> [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    """
    n_sqrt = int(math.sqrt(len(lst)))

    puzzle = []
    for i in range(0, len(lst), n_sqrt):
        line = []
        for j in range(0, n_sqrt):
            line.append(lst[i + j])
        puzzle.append(line)

    return puzzle


def puzzle_to_list(puzzle):
    """
    Converts a two dimensional puzzle to a one dimensional puzzle.

    [[1, 2, 3], [4, 5, 6], [7, 8, 9]] --> [1, 2, 3, 4, 5, 6, 7, 8, 0]
    """
    lst = []
    for row in puzzle:
        lst.extend(row)

    return lst


def check_puzzle_list(lst, n):
    """
    Checks a puzzle one dimensional list and validates it.

    lst : The list to be validated.
    n : Puzzle type (n-puzzle).

     Returns True of it's fine and False if it's not valid.
    """
    # Check list's length
    if len(lst) != n + 1:
        return False

    lst = lst[:]

    lst = [0 if x == '' else x for x in lst]

    # Generate a new list containing numbers from 0 to n
    #   and then check if the list has all of those numbers in it
    new_lst = [i for i in range(0, n + 1)]
    for lst_item in new_lst:
        try:
            lst.remove(lst_item)
        except ValueError:
            return False

    if len(lst) != 0:
        return False

    return True


def get_puzzle_frame_list(puzzle_frame):
    """
    Returns a one dimensional puzzle list that is inside a frame widget.
    """
    lst = []
    for child in puzzle_frame.winfo_children():
        txt = child.get().strip()
        if txt == '':
            txt = 0
        lst.append(int(txt))

    return lst


def start_timer():
    """
    Starts the timer for updating status bar.
    """
    global timer_thread
    global timer_event
    global timer_clear_status_bar

    max_ram_var.set('0')
    cpu_var.set('0')

    search_process_psutil = psutil.Process(search_process.pid)

    def timing():
        while not timer_event.is_set():
            prev_val = float(max_ram_var.get())
            new_val = round(search_process_psutil.memory_full_info().uss / (2 ** 20), 3)

            ram_var.set(new_val)

            if new_val > prev_val:
                max_ram_var.set(new_val)

            cpu_times = search_process_psutil.cpu_times()
            cpu_var.set(round(cpu_times.user + cpu_times.system, 3))

            timer_event.wait(0.001)

        if timer_clear_status_bar:
            cpu_var.set('')
            max_ram_var.set('')
            ram_var.set('')

    timer_event.clear()

    timer_clear_status_bar = False
    timer_thread = threading.Thread(target=timing, daemon=True)
    timer_thread.start()


def load_output_step(n):
    """
    Fills the output puzzle with nth output step.
    """
    global OUTPUT_STEP

    OUTPUT_STEP = n
    step_n_lst = OUTPUT_LST[n]
    fill_puzzle_frame(output_puzzle_frame, step_n_lst)

    output_step_text.delete(0, tkinter.END)
    output_step_text.insert(0, n)


def piper():
    """
    A thread target that listens for algorithm's output through a pipe
    :return:
    """
    global OUTPUT_LST
    global OUTPUT_STEP
    global timer_event
    global timer_clear_status_bar

    try:
        # Waits for algorithm to send the result
        OUTPUT_LST = output_pipe.recv()

        output_error = False
        output_exception = False

        # If the returned value is a string, Some exception has have happened
        if type(OUTPUT_LST) is str:
            output_exception = True
        else:
            # Validate algorithm's output
            if not OUTPUT_LST:
                output_error = True
            elif type(OUTPUT_LST) is not list:
                output_error = True
            else:
                try:
                    n = int(n_spinbox.get())
                    sqrt_n = math.sqrt(n + 1)
                    for output_step in OUTPUT_LST:
                        if type(output_step) is not list:
                            raise BaseException()
                        if len(output_step) != sqrt_n:
                            raise BaseException()
                        for step_row in output_step:
                            if type(step_row) is not list:
                                raise BaseException()
                            if len(step_row) != sqrt_n:
                                raise BaseException()
                        if not check_puzzle_list([int(output_step[i][j])
                                                  for i in range(len(output_step))
                                                  for j in range(len(output_step))],
                                                 n):
                            raise BaseException()
                except:
                    output_error = True

            if not output_error:
                # Converts output's puzzles to one dimensional representation of them
                tmp_lst = []
                for result in OUTPUT_LST:
                    tmp_lst.append(puzzle_to_list(result))
                OUTPUT_LST = tmp_lst

    except EOFError:
        # Stop button pressed
        pass
    else:
        # Calculation successfully done!
        #
        # Stop status thread
        if output_exception or output_error:
            timer_clear_status_bar = True
        timer_event.set()

        calculation_stop()

        # If some exception has have happened inside algorithm's function
        if output_exception:
            messagebox.showerror("Algorithm exception", "Some exception happened in algorithm's source code:\n\n" +
                                 OUTPUT_LST, parent=main_window)

            OUTPUT_LST = []
            OUTPUT_STEP = 0

            return

        if output_error:
            messagebox.showerror("Algorithm output error", "Algorithm's output is not valid.", parent=main_window)

            OUTPUT_LST = []
            OUTPUT_STEP = 0

            return

        # Enable output's action frame
        config_frame_state(output_action_frame, tkinter.NORMAL)
        output_to_label['text'] = len(OUTPUT_LST) - 1
        output_0_label['text'] = '0'

        # Load the first step to output puzzle
        load_output_step(0)


def start_piping():
    """
    Starts the piper thread to listen to algorithm's output.
    """
    global pipe_thread
    global output_pipe

    output_pipe, process_pipe = multiprocessing.Pipe()

    pipe_thread = threading.Thread(target=piper, daemon=True)
    pipe_thread.start()

    # Return the sender pipe
    return process_pipe


def log_datetime():
    """
    Returns the datetime for logging.
    """
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M")


def update_logs_text_if_visible():
    """
    If show logs window is open, then update the text widget's content.
    If someone updates app logs, then should invoke this function.
    """
    if logs_text:
        logs_text['state'] = tkinter.NORMAL
        logs_text.delete(0.0, tkinter.END)
        logs_text.insert(0.0, ''.join(LOGS))
        logs_text['state'] = tkinter.DISABLED
        # Scroll to end of text
        logs_text.see(tkinter.END)


def load_algorithms():
    """
    Load algorithm's modules from ./algorithm/ folder.
    It assumes all python files as algorithms and tries to load them.
    """
    global algorithms_modules
    global LOGS

    # Get list of all files' names
    algorithms_files = [f for f in listdir('./algorithms/') if isfile(join('./algorithms/', f))]
    # Keep all python files's names
    algorithms_files = [f for f in algorithms_files if f.endswith('.py')]
    # Remove .py extension from their file's names
    algorithms_files = [f.rstrip('.py') for f in algorithms_files]

    for module in algorithms_modules:
        try:
            # If the module is already loaded remove it, so it can be reloaded.
            # This happens in algorithm's reloading process.
            del sys.modules[module.__name__]
        except:
            pass

    algorithms_modules = []

    for file in algorithms_files:
        try:
            # Try to import the module and add it to algorithms modules list
            algorithms_modules.append(import_module('algorithms.' + file))
        # If some problem happened when importing the module (For example if the module has some syntax errors).
        except:
            LOGS.append(log_datetime() + " : Error : Exception raised : " + file + ".py\n")

    for module in algorithms_modules:
        LOGS.append(log_datetime() + " : OK : Loaded : " + module.__name__[11:] + ".py\n")

    def check_search_function(module):
        """
        Checks if the module has a search function.
        """
        global LOGS

        if not getattr(module, 'search', None):
            LOGS.append(log_datetime() +
                        " : Error : Algorithm's search not defined : " +
                        module.__name__[11:] +
                        '.py\n')

            return False

        return True

    algorithms_modules = list(filter(check_search_function, algorithms_modules))

    def check_search_function_arguments(module):
        """
        Checks if the module's search function's arguments are proper.
        """
        global LOGS

        if getattr(module, 'search').__code__.co_argcount != 2:
            LOGS.append(log_datetime() +
                        " : Error : Search function should only accept 2 positional arguments : "
                        + module.__name__[11:] + '.py\n')

            return False

        return True

    algorithms_modules = list(filter(check_search_function_arguments, algorithms_modules))

    algorithms_names = []
    for module in algorithms_modules:
        search_name = module.search.__doc__
        # If algorithm's name is not defined in search function's docstring
        if not search_name:
            LOGS.append(
                log_datetime() + " : Warning : Algorithm's name not defined : " + module.__name__[11:] + '.py\n')

            search_name = module.__name__[11:]

        module.search.__doc__ = search_name.strip()
        algorithms_names.append(module.search.__doc__)

    update_logs_text_if_visible()

    prev_algorithm_name = algorithm_name.get()
    # Update algorithms combobox with loaded algorithm's names
    algorithm_combobox['values'] = algorithms_names
    # If there is any loaded algorithms
    if len(algorithms_names):
        if algorithms_names.count(prev_algorithm_name):
            # Select the previously selected algorithm
            algorithm_combobox.set(prev_algorithm_name)
        else:
            # Select the first algorithm from combobox
            algorithm_combobox.set(algorithms_names[0])


def menu_reload_algorithms_command():
    """
    Reload algorithms menu button click handler
    """
    global LOGS

    load_algorithms()

    LOGS.append(log_datetime() + ' : Reloading algorithms...\n')
    update_logs_text_if_visible()


def menu_bar_show_logs_command():
    """
    Show logs menu button click handler
    """
    global logs_window
    global logs_text
    # If there is another show logs window open
    if logs_window:
        # Bring the window to front
        logs_window.lift()

        return
    # Logs window
    logs_window = tkinter.Toplevel(main_window)
    logs_window.title("Logs")
    logs_window.geometry('680x252')
    logs_window.lift()
    # ScrolledText widget
    logs_text = scrolledtext.ScrolledText(logs_window, state=tkinter.DISABLED)
    logs_text.pack(fill=tkinter.BOTH, expand=True)
    # Load logs to text widget
    update_logs_text_if_visible()

    def on_close():
        """
        Logs window 'on close' handler
        """
        global logs_text
        global logs_window

        logs_text = None
        logs_window.destroy()
        logs_window = None

    logs_window.protocol('WM_DELETE_WINDOW', on_close)
    # Show the window
    logs_window.mainloop()


def menu_bar_about_command():
    """
    About menu button click handler
    """
    global about_window
    # If there is another about window open
    if about_window:
        # Bring the window to front
        about_window.lift()

        return
    # Logs window
    about_window = tkinter.Toplevel(main_window)
    about_window.title("About pynpuzzle")
    about_window.minsize(width=400, height=270)
    about_window.maxsize(width=400, height=270)
    about_window.geometry('400x270')
    about_window.resizable(0, 0)
    about_window.lift()
    tkinter.Label(about_window, text="pynpuzzle", font="TkDefaultFont 15 bold").pack(pady=(15, 10))
    tkinter.Label(about_window, text="1.0.0", font="TkDefaultFont 10").pack()
    tkinter.Label(about_window, text="Solve n-puzzle with Python", font="TkDefaultFont 10").pack(pady=10)
    tkinter.Label(about_window, text="Github repository:", font="TkDefaultFont 10").pack(pady=(15, 0))
    github_link = tkinter.Label(about_window, text="http://github.com/mahdavipanah/pynpuzzle", font="TkDefaultFont 10",
                                fg="Blue", cursor="fleur")
    github_link.pack(pady=(0, 10))
    github_link.bind('<Button-1>', lambda x: webbrowser.open('http://github.com/mahdavipanah/pynpuzzle'))
    tkinter.Label(about_window, text="Created by:", font="TkDefaultFont 10").pack()
    tkinter.Label(about_window, text="Hamidreza Mahdavipanah", font="TkDefaultFont 10").pack()
    tkinter.Label(about_window, text="Licensed under MIT license", font="TkDefaultFont 8").pack(pady=(20, 0))

    def on_close():
        """
        About window on close handler
        """
        global about_window

        about_window.destroy()
        about_window = None

    about_window.protocol('WM_DELETE_WINDOW', on_close)
    # Show the window
    about_window.mainloop()


def menu_change_goal_state_command():
    """
    Change goal state menu button click handler
    """
    # Current goal state
    prev_goal_state = GOAL_STATE[:]
    # Change goal window
    change_goal_window = tkinter.Toplevel(main_window)
    change_goal_window.title("Change n-puzzle's goal state")
    change_goal_window.minsize(width=590, height=252)
    change_goal_window.geometry('590x252')
    goal_puzzle_frame = create_puzzle_frame(change_goal_window, int(n_spinbox.get()))
    goal_action_frame = tkinter.Frame(change_goal_window)
    goal_action_frame.grid(row=1, column=0, sticky='WENS')

    def change():
        """
        Changes the goal state.
        """
        global GOAL_STATE

        lst = is_input_puzzle_valid(goal_puzzle_frame)
        if not lst:
            messagebox.showerror("Input error", "Inputs are not valid!", parent=change_goal_window)
            return

        GOAL_STATE = lst

        change_goal_window.destroy()

    def close_window():
        """
        Closes change goal state window.
        """
        # Check if windows' input goal state is equal to current goal state
        equal = True
        new_goal_state = get_puzzle_frame_list(goal_puzzle_frame)
        for i in range(len(GOAL_STATE)):
            if new_goal_state[i] != prev_goal_state[i]:
                equal = False
                break
        # If there is a new goal state in input, ask user if wants to save the goal state before closing the window
        if not equal:
            if messagebox.askyesno("Goal state has been changed", "Do you want to save goal state?",
                                   parent=change_goal_window):
                change()
            else:
                change_goal_window.destroy()
        else:
            change_goal_window.destroy()

    def change_goal_window_random():
        """
        Generates a shuffled list and fills goal state window's input with it.
        """
        n = int(n_spinbox.get())
        lst = [i for i in range(0, n + 1)]
        random.shuffle(lst)

        fill_puzzle_frame(goal_puzzle_frame, lst)

    # Window's widgets
    tkinter.Button(goal_action_frame, text='Save to file',
                   command=lambda: save_file_cmd(goal_puzzle_frame, change_goal_window)).grid(row=0, column=0,
                                                                                              sticky='WENS')
    tkinter.Button(goal_action_frame, text='Load from file',
                   command=lambda: read_file_cmd(goal_puzzle_frame, change_goal_window)).grid(row=0, column=1,
                                                                                              sticky='WENS')
    tkinter.Button(goal_action_frame, text='Random', command=change_goal_window_random).grid(
        row=0, column=2, sticky='WENS')
    tkinter.Button(goal_action_frame, text='Default',
                   command=lambda: fill_puzzle_frame(goal_puzzle_frame, [i for i in range(len(GOAL_STATE))])).grid(
        row=0, column=3, sticky='WENS')
    goal_cancel_border_frame = tkinter.Frame(goal_action_frame, bg='Red')
    goal_cancel_border_frame.grid(row=0, column=4, sticky='WENS')
    goal_cancel_border_frame.grid_columnconfigure(0, weight=1)
    tkinter.Button(goal_cancel_border_frame,
                   text='Cancel',
                   command=close_window).grid(row=0, column=0, sticky='WENS', padx=1, pady=1)
    goal_change_border_frame = tkinter.Frame(goal_action_frame, bg='Green')
    goal_change_border_frame.grid(row=0, column=5, sticky='WENS')
    goal_change_border_frame.grid_columnconfigure(0, weight=1)
    tkinter.Button(goal_change_border_frame,
                   text='Change',
                   command=change).grid(row=0, column=0, sticky='WENS', padx=1, pady=1)
    goal_action_frame.grid_columnconfigure(0, weight=1, uniform=1)
    goal_action_frame.grid_columnconfigure(1, weight=1, uniform=1)
    goal_action_frame.grid_columnconfigure(2, weight=1, uniform=1)
    goal_action_frame.grid_columnconfigure(3, weight=1, uniform=1)
    goal_action_frame.grid_columnconfigure(4, weight=1, uniform=1)
    goal_action_frame.grid_columnconfigure(5, weight=1, uniform=1)
    change_goal_window.grid_rowconfigure(0, weight=1)
    change_goal_window.grid_columnconfigure(0, weight=1)
    change_goal_window.lift()
    change_goal_window.grab_set()
    change_goal_window.protocol('WM_DELETE_WINDOW', close_window)
    # Initialized window's input with current goal state
    fill_puzzle_frame(goal_puzzle_frame, GOAL_STATE)
    # Show the window
    change_goal_window.mainloop()


# Menu bar
menu_bar = tkinter.Menu(main_window)
menu_bar.add_command(label="Change goal state", command=menu_change_goal_state_command)
menu_bar.add_command(label="Reload algorithms", command=menu_reload_algorithms_command)
menu_bar.add_command(label="Show logs", command=menu_bar_show_logs_command)
menu_bar.add_command(label="About", command=menu_bar_about_command)
# Add menu bar to main window
main_window['menu'] = menu_bar

# n frame
n_frame = tkinter.Frame(main_window)
n_frame.grid(row=0, column=0, sticky='EWN', padx=5, pady=5)
n_frame.grid_rowconfigure(0, weight=1)
n_frame.grid_columnconfigure(1, weight=1)
# n label
tkinter.Label(n_frame, text="n: ").grid(row=0, column=0)


def change_app_n(n):
    """
    Refreshes app based on new n.
    """
    global input_puzzle_frame
    global output_puzzle_frame
    global GOAL_STATE

    # Recreate input puzzle
    input_puzzle_frame = create_puzzle_frame(input_labelframe, n, input_puzzle_frame)
    # Recreate output puzzle
    output_puzzle_frame = create_puzzle_frame(output_labelframe, n, output_puzzle_frame, True)
    config_io_frame_state(output_labelframe, tkinter.DISABLED)
    # Regenerate goal state
    GOAL_STATE = [i for i in range(n + 1)]
    # Clear status bar
    ram_var.set('')
    max_ram_var.set('')
    cpu_var.set('')


# n spinbox
def spinbox_command(action):
    """
    n input spinbox up and down handler.
    """
    value = int(math.sqrt(int(n_spinbox.get()) + 1))
    # If up button clicked
    if action == 'up':
        value += 1
    # If down button clicked
    else:
        if value == 3:
            return
        value -= 1

    value = value * value - 1

    n_spinbox.delete(0, tkinter.END)
    n_spinbox.insert(0, value)

    change_app_n(value)


# n spinbox
n_spinbox = tkinter.Spinbox(n_frame, command=(main_window.register(spinbox_command), '%d'))
n_spinbox.insert(tkinter.INSERT, 8)
n_spinbox.grid(row=0, column=1, sticky='EWN')
# Algorithm frame
algorithm_frame = tkinter.Frame(main_window)
algorithm_frame.grid(row=0, column=1, sticky='EWN', padx=5, pady=5)
algorithm_frame.grid_rowconfigure(0, weight=1)
algorithm_frame.grid_columnconfigure(1, weight=1)
# Algorithm label
algorithm_combobox_label = tkinter.Label(algorithm_frame, text="algorithm: ")
algorithm_combobox_label.grid(row=0, column=0)
# Algorithm combobox
algorithm_name = tkinter.StringVar()
algorithm_combobox = ttk.Combobox(algorithm_frame,
                                  textvariable=algorithm_name,
                                  validate=tkinter.ALL,
                                  validatecommand=lambda: False)
algorithm_combobox.grid(row=0, column=1, sticky='EWN')


def calculation_stop():
    """
    Does some routine works that has to be done when to stop calculation.
    """
    # Show start button
    start_button.grid()
    start_button_border_frame.grid()
    # Hide progress bar
    progress_bar.grid_remove()
    progress_bar.stop()
    stop_button['state'] = tkinter.DISABLED
    # Re-enable menu bar buttons
    menu_bar.entryconfig('Reload algorithms', state=tkinter.NORMAL)
    menu_bar.entryconfig('Change goal state', state=tkinter.NORMAL)
    n_spinbox['state'] = tkinter.NORMAL
    # Enable input data entry
    config_io_frame_state(input_labelframe, tkinter.NORMAL)


def stop_button_cmd():
    """
    Stop button click handler
    """
    # Do some routines for stopping calculation
    calculation_stop()
    # Stop algorithm's process
    search_process.terminate()
    output_pipe.close()
    # Stop timer thread and stop refreshing status bar
    timer_event.set()
    # Clear status labels
    threading.Timer(0.1, max_ram_var.set, args=('',)).start()
    threading.Timer(0.1, cpu_var.set, args=('',)).start()
    threading.Timer(0.1, ram_var.set, args=('',)).start()


# Action buttons
#
# Output stop widget and it's border frame
stop_button_border_frame = tkinter.Frame(main_window, bg='Red')
stop_button_border_frame.grid(row=1, column=0, sticky='EWN', padx=5, pady=5)
stop_button_border_frame.grid_columnconfigure(0, weight=1)
stop_button = tkinter.Button(stop_button_border_frame, text="Stop", state=tkinter.DISABLED,
                             command=lambda: stop_button_cmd())
stop_button.grid(row=0, column=0, sticky='EWN', padx=1, pady=1)


def is_input_puzzle_valid(puzzle_frame):
    """
    Checks if given puzzle frame has a valid puzzle in it.

    If puzzle frame has a valid input return's it's one dimensional list and returns None otherwise.
    """
    try:
        lst = get_puzzle_frame_list(puzzle_frame)
        if not check_puzzle_list(lst, int(n_spinbox.get())):
            raise Exception
        return lst
    except:
        return None


def search_runner(func, pipe, lst, goal_state):
    """
    This function invokes the given func with lst and goal_state arguments and sends func's returned value to pipe.
    If some exception happened in func, sends print ready exception's string to show to user.
    """
    try:
        ret_val = func(lst, goal_state)
        pipe.send(ret_val)
    except BaseException as e:
        exception_message = traceback.format_exception(type(e), e, e.__traceback__)
        del exception_message[1]
        pipe.send(''.join(exception_message))


def start_button_cmd():
    """
    Start button click handler
    """
    global output_puzzle_frame
    global search_process
    global OUTPUT_EDITABLE

    if not len(algorithms_modules):
        return

    # Check if input puzzle has a valid input
    lst = is_input_puzzle_valid(input_puzzle_frame)
    if not lst:
        messagebox.showerror("Input error", "Inputs are not valid!", parent=main_window)
        return
    # Change widgets's looks
    start_button.grid_remove()
    start_button_border_frame.grid_remove()
    progress_bar.grid()
    progress_bar.start()
    stop_button['state'] = tkinter.NORMAL
    menu_bar.entryconfig('Reload algorithms', state=tkinter.DISABLED)
    menu_bar.entryconfig('Change goal state', state=tkinter.DISABLED)
    n_spinbox['state'] = tkinter.DISABLED
    config_io_frame_state(input_labelframe, tkinter.DISABLED)
    output_to_label['text'] = ''
    output_0_label['text'] = ''
    output_step_text.delete(0, tkinter.END)
    config_io_frame_state(output_labelframe, tkinter.DISABLED)
    # Clear output puzzle
    OUTPUT_EDITABLE = True
    for child in output_puzzle_frame.winfo_children():
        if child.get().strip() == '':
            child['highlightbackground'] = output_step_text['highlightbackground']
        child.delete(0, tkinter.END)
    OUTPUT_EDITABLE = False
    # Find the search function of the selected algorithm
    for module in algorithms_modules:
        if module.search.__doc__ == algorithm_name.get():
            search_function = module.search
    # Algorithm's search process
    search_process = multiprocessing.Process(target=search_runner,
                                             args=(search_function,
                                                   start_piping(),
                                                   list_to_puzzle(lst),
                                                   list_to_puzzle(GOAL_STATE)))
    search_process.daemon = True
    search_process.start()
    start_timer()


# Start button widget and it's border frame
start_button_border_frame = tkinter.Frame(main_window, bg='Green')
start_button_border_frame.grid(row=1, column=1, sticky='EWN', padx=5, pady=5)
start_button_border_frame.grid_columnconfigure(0, weight=1)
start_button = tkinter.Button(start_button_border_frame, text="Start", command=start_button_cmd)
start_button.grid(row=0, column=0, sticky='WENS', padx=1, pady=1)
# Progress bar widget
progress_bar = ttk.Progressbar(main_window, mode='indeterminate', maximum=20)
progress_bar.grid(row=1, column=1, sticky='EW', padx=5, pady=5)
progress_bar.grid_remove()
# Output labelframe
output_labelframe = tkinter.LabelFrame(main_window, text="Output")
output_labelframe.grid(row=2, column=0, sticky='WENS', padx=5, pady=5)
output_labelframe.grid_rowconfigure(0, weight=1)
output_labelframe.grid_columnconfigure(0, weight=1)
# Output puzzle frame
output_puzzle_frame = create_puzzle_frame(output_labelframe, 8, None, True)
# Output action frame
output_action_frame = tkinter.Frame(output_labelframe, bd=1, relief=tkinter.SUNKEN)


def output_0_to_label_click(n):
    """
    output_0_label click handler

    Goes to first step of the output.
    """
    if output_0_label['cursor'] == 'fleur':
        load_output_step(n)


# output_0_label widget
output_0_label = tkinter.Label(output_action_frame, cursor="fleur")
output_0_label.pack(side=tkinter.LEFT)
output_0_label.bind('<Button-1>', lambda x: output_0_to_label_click(0))


def prev_step_button():
    """
    Output's previous step button click handler

    Goes to previous step of the output.
    """
    if OUTPUT_STEP == 0:
        return False

    load_output_step(OUTPUT_STEP - 1)
    return True


tkinter.Button(output_action_frame, text="<<", width=0, command=prev_step_button).pack(side=tkinter.LEFT)


def output_stop_button_cmd():
    """
    Output's stop button click handler

    Stops playing the output.
    """
    play_event.set()

    output_play_button['state'] = tkinter.NORMAL
    output_stop_button['state'] = tkinter.DISABLED


# Output's stop button widget
output_stop_button = tkinter.Button(output_action_frame, text="Stop", width=0, fg='Red', state=tkinter.DISABLED,
                                    command=output_stop_button_cmd)
output_stop_button.pack(side=tkinter.LEFT)
output_step_text = tkinter.Entry(output_action_frame, width=10, justify=tkinter.CENTER)
output_step_text.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)


def step_text_enter(*_):
    """
    Output's step text widget 'Enter' and 'Return' key handler

    Goes to entered step of the output.
    """
    # Check if the entered text is a number
    try:
        step_num = int(output_step_text.get())
    except ValueError:
        output_step_text.delete(0, tkinter.END)
        output_step_text.insert(0, OUTPUT_STEP)
        return
    # Check if the entered number is in the range of the steps
    if not (0 <= step_num <= int(output_to_label['text'])):
        output_step_text.delete(0, tkinter.END)
        output_step_text.insert(0, OUTPUT_STEP)
        return

    load_output_step(step_num)


output_step_text.bind('<KP_Enter>', step_text_enter)
output_step_text.bind('<Return>', step_text_enter)


def play_button_command():
    """
    Output's play button click handler

    Start playing the output steps one by one.
    """
    global play_event
    global play_timer

    def playing():
        """
        Target function for play_thread

        Plays output step's one by one with one second delay between them.
        """
        time.sleep(1)
        while not play_event.is_set():
            next_step_button()
            if OUTPUT_STEP == int(output_to_label['text']):
                output_stop_button_cmd()
                return
            play_event.wait(1)

    # Disable play button
    output_play_button['state'] = tkinter.DISABLED
    # Enable stop button
    output_stop_button['state'] = tkinter.NORMAL

    # If output's step is already the last one, change the step to the first step so it can be played from beginning
    if OUTPUT_STEP == int(output_to_label['text']):
        load_output_step(0)

    play_event = threading.Event()
    play_timer = threading.Thread(target=playing)
    play_timer.start()


# Output's play button widget
output_play_button = tkinter.Button(output_action_frame, text="Play", width=0, fg='Green', command=play_button_command)
output_play_button.pack(side=tkinter.LEFT)


def next_step_button():
    """
    Output's next step button click handler

    Goes to next step of the output.
    """
    if OUTPUT_STEP == int(output_to_label['text']):
        return False

    load_output_step(OUTPUT_STEP + 1)
    return True


tkinter.Button(output_action_frame, text=">>", width=0, command=next_step_button).pack(side=tkinter.LEFT)
output_to_label = tkinter.Label(output_action_frame, text="", cursor='fleur')
output_to_label.pack(side=tkinter.LEFT)
output_to_label.bind('<Button-1>', lambda x: output_0_to_label_click(int(output_to_label['text'])))
output_action_frame.grid(row=1, column=0, sticky='WENS')
# Config output frame
config_io_frame_state(output_labelframe, tkinter.DISABLED)
# Input labelframe
input_labelframe = tkinter.LabelFrame(main_window, text="Input")
input_labelframe.grid(row=2, column=1, sticky='WENS', padx=5, pady=5)
input_labelframe.grid_rowconfigure(0, weight=1)
input_labelframe.grid_columnconfigure(0, weight=1)
# Input puzzle frame
input_puzzle_frame = create_puzzle_frame(input_labelframe, 8)
# Input action frame
input_action_frame = tkinter.Frame(input_labelframe)
input_action_frame.grid(row=1, column=0, sticky='WENS')
input_action_frame.grid_columnconfigure(0, weight=1, uniform=1)
input_action_frame.grid_columnconfigure(1, weight=1, uniform=1)
input_action_frame.grid_columnconfigure(2, weight=1, uniform=1)
input_action_frame.grid_columnconfigure(3, weight=1, uniform=1)


def save_file_cmd(puzzle_frame, parent):
    """
    Input's save to file button click handler

    puzzle_frame : The puzzle frame which it's puzzle will be saved to file
    parent : The parent window of the puzzle_frame
             This is used for showing the 'save as file' dialog so it can be showed on top of the window.
    """
    # Check if puzzle frame has a valid input, and if not, ask the user if he's sure he wants to save the puzzle
    lst = is_input_puzzle_valid(puzzle_frame)
    if not lst:
        if not messagebox.askokcancel("Input not valid",
                                      "Input puzzle is not valid, are you sure to save it as a file?",
                                      parent=parent):
            return

    # Open the 'save as file' dialog
    file_name = filedialog.asksaveasfilename(title="Choose a file to save puzzle", parent=parent)
    # Check if user has selected a file
    if not file_name:
        return

    # Generate file's content
    len_sqrt = int(math.sqrt(len(lst)))
    file_lines = []
    for i in range(0, len(lst), 3):
        line_nums = []
        for j in range(0, len_sqrt):
            line_nums.append(str(lst[i + j]))
        file_lines.append(' '.join(line_nums))

    try:
        with open(file_name, 'w') as file:
            file.write('\n'.join(file_lines))
    except:
        messagebox.showerror("Error saving to file",
                             "Some problem happened while saving puzzle to the file.",
                             parent=parent)


# Save to file button widgget
tkinter.Button(input_action_frame, text="Save to file",
               command=lambda: save_file_cmd(input_puzzle_frame, main_window)).grid(row=0, column=0, sticky='WENS')


def read_file_cmd(puzzle_frame, parent):
    """
    Input's read from file button click handler

    puzzle_frame : The puzzle frame which it's puzzle will be saved to file
    parent : The parent window of the puzzle_frame
             This is used for showing the 'save as file' dialog so it can be showed on top of the window.
    """
    # Show 'open file' dialog
    file_name = filedialog.askopenfilename(title="Choose a file as input", parent=parent)
    # Check if user has selected a file
    if not file_name:
        return
    # Try to open the input file
    try:
        with open(file_name) as file:
            lines = []
            pattern = re.compile(r'\s+')

            for line in file:
                # Check if line is empty
                if re.sub(pattern, '', line) == '':
                    # Stop reading from input file
                    break

                lines.append(line.rstrip())

            lst = []

            try:
                for line in lines:
                    line_split = line.split(' ')
                    lst.extend([int(i) for i in line_split])

                    if len(line_split) != len(lines):
                        messagebox.showerror("Input error", "Puzzle dimension is not valid.", parent=parent)
                        return

            except ValueError:
                messagebox.showerror("Input error", "Input must non-number values.", parent=parent)

            input_puzzle_n = len(lines) ** 2 - 1
            if not check_puzzle_list(lst, input_puzzle_n):
                messagebox.showerror("Input error", "Puzzle numbers are not valid.", parent=parent)
                return

            if input_puzzle_n != int(n_spinbox.get()):
                n_spinbox.delete(0, tkinter.END)
                n_spinbox.insert(0, input_puzzle_n)

                change_app_n(input_puzzle_n)

            fill_puzzle_frame(puzzle_frame, lst)

    except:
        messagebox.showerror("Error opening input file",
                             "Some problem happened while opening input file.",
                             parent=parent)


tkinter.Button(input_action_frame, text="Read from file",
               command=lambda: read_file_cmd(input_puzzle_frame, main_window)).grid(row=0, column=1, sticky='WENS')


def random_button_command(puzzle_frame):
    """
    Generates a random solvable puzzle and fills the puzzle_frame with it.

    See https://www.sitepoint.com/randomizing-sliding-puzzle-tiles/ for more information.
    """
    n = int(n_spinbox.get())
    lst = [i for i in range(0, n + 1)]
    random.shuffle(lst)

    sum_inversions = 0
    for tile in [x for x in lst if x != 0]:
        before_tiles = GOAL_STATE[:GOAL_STATE.index(tile)]
        for after_tile in [x for x in lst[lst.index(tile):] if x != 0]:
            if before_tiles.count(after_tile):
                sum_inversions += 1

    sqrt_n = math.sqrt(n + 1)

    def row_number(i):
        return math.ceil((i + 1) / sqrt_n)

    if sqrt_n % 2 == 1:
        solvable = sum_inversions % 2 == 0
    else:
        solvable = (sum_inversions + abs(row_number(lst.index(0)) - row_number(GOAL_STATE.index(0)))) % 2 == 0

    if not solvable:
        if lst[0] != 0 and lst[1] != 0:
            lst[0], lst[1] = lst[1], lst[0]
        else:
            lst[len(lst) - 1], lst[len(lst) - 2] = lst[len(lst) - 2], lst[len(lst) - 1]

    fill_puzzle_frame(puzzle_frame, lst)


# Input's random button widget
tkinter.Button(input_action_frame,
               text="Random",
               command=lambda: random_button_command(input_puzzle_frame)).grid(row=0,
                                                                               column=3,
                                                                               sticky='WENS',
                                                                               columnspan=1)


def operator(puzzle):
    """
    Returns all possible puzzle's states that are reachable from current puzzle's state
    """
    states = []

    zero_i = None
    zero_j = None

    for i in range(len(puzzle)):
        for j in range(len(puzzle)):
            if puzzle[i][j] == 0:
                zero_i = i
                zero_j = j
                break

    def add_swap(i, j):
        new_state = deepcopy(puzzle)
        new_state[i][j], new_state[zero_i][zero_j] = new_state[zero_i][zero_j], new_state[i][j]
        states.append(new_state)

    if zero_i != 0:
        add_swap(zero_i - 1, zero_j)

    if zero_j != 0:
        add_swap(zero_i, zero_j - 1)

    if zero_i != len(puzzle) - 1:
        add_swap(zero_i + 1, zero_j)

    if zero_j != len(puzzle) - 1:
        add_swap(zero_i, zero_j + 1)

    return states


def puzzles_equal(first, second):
    for i in range(len(first)):
        for j in range(len(first)):
            if first[i][j] != second[i][j]:
                return False
    return True


def n_step_random_command():
    """
    Generates a random puzzle that can be solved in n-step.
    """
    n_step = simpledialog.askinteger("n-step random", "Enter number of steps:", parent=main_window)

    if not n_step:
        return

    puzzle = list_to_puzzle(GOAL_STATE)
    prev_puzzle = puzzle
    for i in range(n_step):
        new_puzzles = operator(puzzle)

        for i in range(len(new_puzzles)):
            if puzzles_equal(new_puzzles[i], prev_puzzle):
                del new_puzzles[i]
                break

        prev_puzzle = puzzle
        puzzle = new_puzzles[random.randrange(0, len(new_puzzles))]

    fill_puzzle_frame(input_puzzle_frame, puzzle_to_list(puzzle))


# Input's n-step random button widget
tkinter.Button(input_action_frame,
               text="n-step random",
               command=n_step_random_command).grid(row=0,
                                                   column=2,
                                                   sticky='WENS',
                                                   columnspan=1)

# Status bar
status_frame = tkinter.Frame(main_window, bd=1, relief=tkinter.SUNKEN)
status_frame_1 = tkinter.Frame(status_frame, bd=1, relief=tkinter.GROOVE)
tkinter.Label(status_frame_1, text="Execution time(s): ").grid(row=0, column=0, sticky='WENS', padx=2)
tkinter.Label(status_frame_1, textvariable=cpu_var).grid(row=0, column=1, sticky='W')
status_frame_1.grid_columnconfigure(1, weight=1)
status_frame_1.grid(row=0, column=0, sticky='WENS')
status_frame_2 = tkinter.Frame(status_frame, bd=1, relief=tkinter.GROOVE)
tkinter.Label(status_frame_2, text="Max RAM usage(MB): ").grid(row=0, column=0, sticky='WENS', padx=2)
tkinter.Label(status_frame_2, textvariable=max_ram_var).grid(row=0, column=1, sticky='W')
status_frame_2.grid_columnconfigure(1, weight=1)
status_frame_2.grid(row=0, column=1, sticky='WENS')
status_frame_3 = tkinter.Frame(status_frame, bd=1, relief=tkinter.GROOVE)
tkinter.Label(status_frame_3, text="RAM usage(MB): ").grid(row=0, column=0, sticky='WENS', padx=2)
tkinter.Label(status_frame_3, textvariable=ram_var).grid(row=0, column=1, sticky='W')
status_frame_3.grid_columnconfigure(1, weight=1)
status_frame_3.grid(row=0, column=2, sticky='WENS')
status_frame_4 = tkinter.Frame(status_frame, bd=1, relief=tkinter.SUNKEN)
tkinter.Label(status_frame_4, text="Available RAM(MB): ").grid(row=0, column=0, sticky='WENS', padx=2)
tkinter.Label(status_frame_4, textvariable=available_ram_var).grid(row=0, column=1, sticky='W')
status_frame_4.grid_columnconfigure(1, weight=1)
status_frame_4.grid(row=0, column=3, sticky='WENS')
status_frame.grid(row=3, column=0, sticky='WENS', columnspan=2)
status_frame.columnconfigure(0, weight=1, uniform=1)
status_frame.columnconfigure(1, weight=1, uniform=1)
status_frame.columnconfigure(2, weight=1, uniform=1)
status_frame.columnconfigure(3, weight=1, uniform=1)

load_algorithms()


def available_ram_display():
    """
    A thread target that updates available ram status label every 1 millisecond
    """
    while True:
        available_ram_var.set(round(psutil.virtual_memory().available / (2 ** 20), 3))
        time.sleep(0.001)


threading.Thread(target=available_ram_display, daemon=True).start()

if __name__ == '__main__':
    # Support windows binary freezing
    multiprocessing.freeze_support()
    # Show the main window
    main_window.mainloop()
