#!/usr/bin/python3
# server.py

# import the network interface library
from takumi_connection import Connection
from takumi_connection import Server
from datetime import datetime
import random

'''
protocol guideline:
- messages are sent in categories, which is seperated using \r\n (we'll
  represent it using a space)
- the frontmost part seperated by \r\n is a command.
- the following are arguments related to the command.
- These are the commands used throughout the protocol.
  - conn.accept_msg - the client has just connected to the server.
                      server must response with `auth`.
  - `auth` - server want the user information from client
  - `auth_res [username] [room id | none]` - client response for the need of
                                             user info.
  - `let_in [username] [room id] [room member 1] [room member 2] ...`
        server allow the current user to enter the existing (or a new) chat
        room, and tell the client the chat room informanion.
  - `empty_res` - client send a response without any information. (happened most
                    of the time when there's really nothing to send to the
                    server, and server might send this as well)
  - `stat_update [warning|new_member|member_leave] [related arguments] ...`
                server send the info about the chat room's recent
                status, such as someone entering or leaving the room.
  - `msg_in [message content]` - client send a message to server
  - `msg_out [username] [message content] [date]` - server send a message from the
                                              other person.
            note: server will `msg_out` the same message sent by the client as
            well, to confirm the integrity and the message arrival time on the
            server.
  - `quit` - quit the session. (close the connection)
    - any sides can send it, for some reasons.

chat room id: consists of 4 random digits, stored as a string.
'''

class ChatServer:
    def __init__(self, host, port, is_prompt=False):
        self.server = Server(host, port, is_prompt)
        # a dict which stores `Connection` instances of clients.
        self.chatrooms = dict() # (chat room id, ChatRoom instance)
        self.authorized_user = dict() # (sock addr, User instance)

        self.is_running = False

    def client_handler(self, recv, conn):
        # notice: every cases must send a message in some ways.

        is_valid = True # flag to specify the validity of arguments.
        invalid_msg = '' # if args are invalid, why.

        if recv[0] == conn.accept_msg:  # the client has just connected.
            conn.send('auth')
        elif recv[0] == 'auth_res':     # the client send user info to server.
            # check if the info is in the valid form.
            # auth_res [username] [room id|none]
            if len(recv) == 3 and\
                    recv[1].isidentifier() and\
                    (recv[2].isnumeric() or recv[2] == 'none') and\
                    len(recv[2]) == 4:

                chatRoom = None
                # check the availabitily of chat room.
                if recv[2] == 'none':
                    # in case user didn't pick up a room id, create a chat room.
                    chatRoom = ChatRoom()
                elif recv[2] not in self.chatrooms:
                    # user put a valid chat room id, but not exist.
                    invalid_msg = 'The Room ID you specified does not exist.'
                    is_valid = False
                else:
                    # that room exists.
                    chatRoom = self.chatrooms[recv[2]]

                # check if this username already exists in that chatroom.
                if recv[1].lower() in chatRoom.usernames:
                    is_valid = False
                    invalid_msg = f'The name "{recv[1]}" already exists in the room with ID {recv[2]}'

                # if room id is valid.
                if is_valid:
                    # create a ChatUser instance
                    newUser = ChatUser(recv[1], chatRoom, conn)

                    # get the current members of that room.
                    chatRoomCurrMember = [chatRoom.users[x].name for x in chatRoom.users]

                    self.authorized_user[conn.addr] = newUser

                    # sending room info to users
                    conn.send_multiple(['let_in', recv[1], chatRoom.id,
                                        *chatRoomCurrMember])
                    #
                    # put the user to the chat room.
                    chatRoom.add_user(newUser)
                    self.chatrooms[chatRoom.id] = chatRoom


            # some arguments are incorrect.
            else:
                is_valid = False
                invalid_msg = 'Either username or room ID is invalid.'

        elif recv[0] == 'msg_in':
            # check the incoming message first
            if recv[1] == '':
                conn.send('empty_res')
            elif recv[1][0] == '\\':
                if recv[1][1:] == 'quit':
                    # user want to disconnect
                    self.authorized_user[conn.addr].room.remove_user(self.authorized_user[conn.addr])
                    conn.stop()

                # not a supported command.
                else:
                    is_valid = False
                    invalid_msg = f'Unknown command {recv[1][1:]}'

            else:
                self.authorized_user[conn.addr].room.broadcast('msg_out',
                                                               self.authorized_user[conn.addr].name,
                                                               recv[1],
                                                               datetime.now().strftime("%m/%d/%Y, %H:%M:%S"))

        elif recv[0] == 'quit':
            if conn.addr in self.authorized_user:
                self.authorized_user[conn.addr].room.remove_user(self.authorized_user[conn.addr])

            conn.stop()

        elif recv[0] == 'empty_res':
            if conn.addr not in self.authorized_user:
                conn.send('auth')

        if not(is_valid):
            conn.send_multiple(['stat_update', 'WARNING', invalid_msg])

    def run(self):
        self.server.set_request_handler(self.client_handler)
        self.server.run()

        self.is_running = True

    def stop(self):
        for user in self.authorized_user:
            user.conn.send('quit')

        self.is_running = False
        self.server.stop()

class ChatUser:
    def __init__(self, name, room, conn):
        self.name = name
        self.room = room
        self.conn = conn

class ChatRoom:
    def __init__(self):
        self.id = ''.join([str(random.randint(0, 9)) for _ in range(4)])
        self.users = dict()  # (socket name, ChatUser instance)
        self.usernames = set() # just to validate to avoid repeated names.

    def add_user(self, chat_user):
        self.users[chat_user.conn.addr] = chat_user
        self.usernames.add(chat_user.name.lower())
        self.broadcast('stat_update', 'NOTICE', f'{chat_user.name} joined the chat.')

    def remove_user(self, chat_user):
        self.users.pop(chat_user.conn.addr)
        self.usernames.remove(chat_user.name.lower())
        self.broadcast('stat_update', 'NOTICE', f'{chat_user.name} left the chat.')

    def broadcast(self, msg_type, *msg):
        for user in self.users:
            self.users[user].conn.send_multiple([msg_type, *msg])

if __name__ == '__main__':
    host = '127.0.0.1'
    port = 9999

    chat = ChatServer(host, port, is_prompt=True)
    chat.run()
