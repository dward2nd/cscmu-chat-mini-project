#!/usr/bin/python3
# client.py

# import the network interface library
from takumi_connection import Client
from takumi_connection import Connection
from threading import Thread
#import curses
import os
import platform
import struct
import sys
import random

# if the operating system is Windows, make it compatible with terminal color
# display.
if platform.system() == 'Windows':
    os.system('color')
    print('WARNING: This program (client-side) might not work as expected on Windows.')

# if not, the operating system is most likely POSIX-based, so that it could
# support the way of printing text on linux.
else:
    import fcntl
    import readline
    import termios

def ansi_color(n,s):
	code = {
        # font style
        "bold": 1,
        "faint": 2,
        "italic": 3,
        "underline": 4,
        "blink_slow": 5,
        "blink_fast": 6,
        "negative": 7,
        "conceal": 8,
        "strike_th": 9,
        # font color
        "black": 30,
        "red": 31,
        "green": 32,
        "yellow": 33,
        "blue": 34,
        "magenda": 35,
        "cyan": 36,
        "white": 37,
        # font highlight
        "b_black": 40,
        "b_red": 41,
        "b_green": 42,
        "b_yellow": 43,
        "b_blue": 44,
        "b_magenda": 45,
        "b_cyan": 46,
        "b_white": 47
    }

	try:
		num = str(code[n])
		value = "".join(["\033[", num, "m", s, "\033[0m"])

		return value
	except:
		pass

def blank_current_readline():

    # only work when running on Windows
    if platform.system() != 'Windows':

        # Next line said to be reasonably portable for various Unixes
        (rows, cols) = struct.unpack('hh',
                                     fcntl.ioctl(sys.stdout,
                                                 termios.TIOCGWINSZ,
                                                 '1234'))

        text_len = len(readline.get_line_buffer()) + 2

        # ANSI escape sequences (All VT100 except ESC[0G)
        sys.stdout.write('\x1b[2K')                         # Clear current line
        sys.stdout.write('\x1b[1A\x1b[2K'*(text_len//cols)) # Move cursor up and clear line
        sys.stdout.write('\x1b[0G')                         # Move to start of line

class ChatClient:
    def __init__(self, host, port):
        self.client = Client(host, port)
        self.is_running = False
        self.is_authenticated = False
        self.chat_input_worker = None
        self.user_color = dict()    # (username, color_str)
        self.user_datetime_color = dict()   # (username, color_str)
        self.color_profile = ['b_red', 'b_green', 'b_yellow', 'b_blue',
                                     'b_magenda', 'b_cyan', 'b_white']
        self.date_time_profile = ['red', 'green', 'yellow', 'blue', 'magenda',
                                  'cyan', 'white']

    def add_user_color(self, username):
        self.user_color[username] = random.sample(self.color_profile, 1)[0]
        self.user_datetime_color[username] = self.user_color[username][2:]

    def server_handler(self, recv, conn):

        if recv[0] == 'auth':
            # ask user the username and preferred room id.
            print()
            print(ansi_color("magenda", ansi_color("bold", 'Username')),
                  ansi_color("magenda", ansi_color("italic", 'can consist of\n  - alphabets A-Z,\n  - digits 0-9\n  - underscores.\n  - must not start with a digit.')), sep='\n')

            user = input(ansi_color('bold', ansi_color('magenda', '-> ')))

            print()
            print(ansi_color("cyan", ansi_color("bold", 'Room ID')),
                  ansi_color("cyan", ansi_color("italic", 'is 4-digit code. To create new, type "none"')), sep='\n')

            roomid = input(ansi_color("bold",
                                     ansi_color("cyan",
                                                '-> ')))

            print()

            conn.send_multiple(['auth_res', user, roomid])

        elif recv[0] == 'stat_update':
            if self.is_authenticated:
                blank_current_readline()

            print(ansi_color('red', f'From server [{recv[1]}]: {recv[2]}'))

            if self.is_authenticated and platform.system() != 'Windows':
                sys.stdout.write(ansi_color('red', '> ')+ readline.get_line_buffer())
                sys.stdout.flush()

            conn.send('empty_res')

        elif recv[0] == 'let_in':

            self.user = recv[1]
            self.roomid = recv[2]

		    #value = "".join(["\033[", num, "m", s, "\033[0m"])
            print('\033[1m', end='')    # start of the bold text
            print(f'=============================================')
            print(f'Welcome {recv[1]} to Takumi Messenger!')
            print('You are in Room ID', recv[2])
            print('Current active members:')
            if len(recv[3:]):
                for mem in recv[3:]:
                    print('\t-', mem)
            else:
                print('\t--- There\'s no member yet. ---')
            print('\033[0m', end='')

            print(ansi_color('red',
                             ansi_color('bold',
                                        '\nTo quit the chat, type "\\quit"')))

            print('\033[1m', end='')
            print(f'=============================================\n')
            print('\033[0m', end='')

            self.is_authenticated = True
            self.conn = conn

            # redirect to the chat management system.
            self.chat_input_worker = Thread(target=self.chat_input,
                                            args=())
            self.chat_input_worker.start()

        elif recv[0] == 'msg_out':

            # if the current user isn't in the color profile list, add him/her.
            if recv[1] not in self.user_color:
                self.add_user_color(recv[1])

            if platform.system() != 'Windows':
                blank_current_readline()

            print()     # print a new line.
            print(ansi_color("bold",
                             ansi_color(self.user_color[recv[1]],
                                        f'  {recv[1]}  ')),
                  recv[2],
                  '\n',
                  ansi_color("italic",
                             ansi_color(self.user_datetime_color[recv[1]],
                                        ''.join(["  - ", recv[3]]))))
            print()     # print a new line.

            if platform.system() != 'Windows':
                sys.stdout.write(ansi_color('red', '> ')+ readline.get_line_buffer())
                sys.stdout.flush()

            conn.send('empty_res')

        elif recv[0] == 'quit':
            self.is_running = False
            self.is_authenticated = False
            self.client.stop()

    #def move_cursor(self, y, x):
        #print("\033[%d;%dH" % (y, x))

    def chat_input(self):
        self.conn.send('empty_res')
        # The chat has to send the acknowledgement before starting a
        # conversation.
        while self.is_authenticated:
            user_input = input(ansi_color("red", '> '))

            # clear the previous line of input
            sys.stdout.write('\033[1A\x1b[2K')
            self.conn.send_multiple(['msg_in', user_input])

    def run(self):
        self.is_running = True
        self.client.set_response_handler(self.server_handler)
        self.client.run()

    def __del__(self):
        if self.is_running:
            self.is_running = False
            self.is_authenticated = False
            self.client.stop()

if __name__ == '__main__':
    host = '127.0.0.1'
    port = 9999

    chat_client = ChatClient(host, port)
    chat_client.run()
