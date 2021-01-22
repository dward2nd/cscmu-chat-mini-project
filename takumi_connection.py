#!/usr/bin/python3
# takumi_connection.py

# ======= PART 1: Setting up the server =======

# Import essential module
from select import select
from threading import Event
from threading import Thread
import socket
import sys
import time
import traceback

# make a class of the connection, for the easier management.
class Server:
    def __init__(self, host, port, is_prompt=False):
        # server info
        self.host = host
        self.port = port

        # determine whether the server should print the connection status to the
        # standard i/o.
        self.is_prompt = is_prompt

        # set the initial running state to False
        self.is_running = False

        # set the initial connection opening to None
        self.open_connection = None

        # set the initial handler status to None
        self.request_handler = None

        # set the initial flag for the terminal kill signal working.
        self.is_terminal_getch_running = False

        # set the initial handler status to the empty tuple.
        self.request_handler_args = ()

    def set_request_handler(self, handler, *args):
        if self.is_running:
            raise Exception('The handler must be set before the connection was established.')

        self.request_handler = handler
        self.request_handler_args = args

    def run(self):

        # The handler has to be set before running this method.
        if not callable(self.request_handler):
            raise Exception('No proper connection request handler is set.')

        if self.is_running:
            raise Exception('Close the connection before making a new one.')

        # socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # listen to the specific port.
        self.socket.bind((self.host, self.port))
        self.socket.listen()

        # Tell the user that the server started listening to the specific port.
        if self.is_prompt:
            print('The server started listening to %s, at port %d'%(self.host,
                                                                    self.port))
        # set the running state to True
        self.is_running = True

        # keep the server running
        while self.is_running:

            # These lines just keep waiting for a command to kill (stop)
            # server from working.
            # The default command is set to 'qt' (quit)
            if not self.is_terminal_getch_running:
                tg_thread = Thread(target=self.wait_to_kill)
                tg_thread.start()

            try:
                client_socket, client_addr = self.socket.accept()

                if self.is_prompt:
                    print(f'Client from {client_addr} request to connect.')

                curr_process = Connection(socket=client_socket,
                                          addr=client_addr,
                                          request_handler=self.request_handler,
                                          request_args=self.request_handler_args,
                                          send_accept_msg=True,
                                          is_prompt=self.is_prompt,
                                          daemon=True)
                curr_process.start()

            except socket.timeout:
                if self.is_prompt:
                    print('There was a request, but reached the connection timeout.')

    def wait_to_kill(self):
        if not self.is_terminal_getch_running:
            self.is_terminal_getch_running = True
            terminal_getch = ''
            while terminal_getch != 'qt':
                terminal_getch = sys.stdin.read(2)

            self.stop()

    def stop(self):

        if not(self.is_running):
            raise Exception('No connection is currently running.')

        # set the running status to False
        self.is_running = False

        # prevent the server from accepting more requests.
        socket.socket(socket.AF_INET,
                      socket.SOCK_STREAM).connect((self.host, self.port))

        # properly close the connection
        self.socket.close()

        if self.is_prompt:
            print('The server stopped listening to %s, at port %d'%(self.host,
                                                                    self.port))

    # when the program is terminated, close the connection
    def __del__(self):

        if self.is_running:

            # Simply run `stop()` method.
            self.stop()

class Connection(Thread):

    def __init__(self, socket, addr, request_handler,
                 accept_msg='200: Success', send_accept_msg=False, group=None, target=None, name=None,
                 request_args=(), args=(), kwargs={},
                 is_prompt=False, event=None, *, daemon=None):
        super().__init__(group=group, target=target, name=name, args=args,
                        kwargs=kwargs, daemon=daemon)

        self.socket = socket
        self.addr = addr
        self.accept_msg = accept_msg

        self.is_running = False
        self.is_prompt = is_prompt

        # the list for awaited data to be sent to the client.
        self.awaited_data = []

        self.send_accept_msg = send_accept_msg
        self.event = event

        # the function which will be handle the current connection.
        self.request_handler = request_handler
        self.request_args = request_args    # note that args has to accept at least 1
                                            # argument for received data.

    def send(self, data):
        self.awaited_data.append(data)

    def send_multiple(self, data):
        self.awaited_data.append('\r\n'.join(data))

    def quarantine(self):
        read_ready, write_ready, in_error = select([self.socket],
                                                   [self.socket],
                                                   [self.socket], 30)

        # the connection must have been lost for now.
        # let's just stop it.
        if len(read_ready) == 0 and len(write_ready) == 0:
            self.stop()

    def run(self):

        if not callable(self.request_handler):
            raise Exception('No request handler for each session was defined.')

        if self.send_accept_msg:
            self.socket.send(f'{self.accept_msg}\r\n'.encode('utf-8'))
        # keep updating the status from client.
        self.is_running = True

        while self.is_running:
            try:
                read_ready, write_ready, in_error = select([self.socket],
                                                           [self.socket],
                                                           [], 30)
                #if len(in_error):
                    # do when the socket has some errors.
                    #self.quarantine()

                if len(read_ready):
                    # do when the socket is ready to receive data..
                    read_data = self.socket.recv(2048).decode('utf-8')

                    if self.is_prompt:
                        print(f'Received from {self.addr}: "{read_data}"')

                    if read_data == '200: Close the connection\r\n' or\
                       read_data == '':
                        self.stop()
                    else:
                        self.request_handler(read_data.split('\r\n'), self, *self.request_args)

                if len(write_ready) != 0 and len(self.awaited_data) != 0:
                    # do when the socket is ready to send data,
                    # only when the socket isn't available for reading,
                    # this is due to the thread-safe connection.
                    msg = self.awaited_data[0]
                    sent = self.socket.send(msg.encode('utf-8'))

                    if self.is_prompt:
                        print(f'Sent to {self.addr}: "{msg}"')

                    if sent > 0:
                        del self.awaited_data[0]

                # wait until the next responding to clients.
                #time.sleep(0.2)

            # in case the connection suddenly reset, mark it as not running
            # without running the stop method.
            except Exception as e:
                self.is_running = False
                if (self.event):
                    self.event.set()
                if self.is_prompt:
                    print(f'The connection to {self.addr} has UNEXPECTEDLY stopped.')
                print('There was an unexpected error:', e)
                print('Traceback:', traceback.format_exc())


    def stop(self):
        if not(self.is_running):
            raise Exception('The current client connection has already stopped.')

        self.socket.send('200: Close the connection\r\n'.encode('utf-8'))
        self.socket.close()
        self.is_running = False
        if self.event:
            self.event.set()

        if self.is_prompt:
            print(f'The connection to {self.addr} has stopped.')

    def __del__(self):
        if self.is_running:
            self.stop()

# client-side connection
class Client:
    def __init__(self, host, port, is_prompt=False):
        # destination info
        self.host = host
        self.port = port

        # set the default response handler
        self.response_handler = None
        self.response_args = ()

        # set the running status.
        self.is_running = False
        self.is_prompt = is_prompt

        # set the queue of data to be sent to server.
        self.sending_queue = []

        # count the sent no. of data
        self.sent_count = 0

    def set_response_handler(self, handler, *args):
        self.response_handler = handler
        self.response_args = args

    def run(self, accept_msg='200: Success'):
        if self.is_running:
            raise Exception('Close the connection before the new session is started.')

        try:
            # generate the socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))

            # Check if server accept the connection
            if self.socket.recv(2048).decode('utf-8') == f'{accept_msg}\r\n':
                if self.is_prompt:
                    print(f'The connection to server {self.host}:{self.port} has started.')

                conn_event = Event()
                self.conn = Connection(socket=self.socket,
                                       addr=self.socket.getsockname(),
                                       request_handler=self.response_handler,
                                       request_args=self.response_args,
                                       is_prompt=self.is_prompt,
                                       send_accept_msg=True,
                                       event=conn_event,
                                       daemon=True)

                self.conn.start()
                self.is_running = True

                conn_event.wait()

            else:
                raise Exception('There was a problem connected to the server.')
        except:
            raise Exception('The server can\'t be reached for some reasons.')

    '''
    def request(self, message, max_byte_received=2048, args=()):
        if not self.is_running:
            raise Exception('The request must be set after the connection was established.')

        self.socket.send(message.encode('utf-8'))
        res = self.socket.recv(max_byte_received)

        if callable(self.response_handler):
            return self.response_handler(res, *args)

        return res.decode('utf-8')
    '''

    def stop(self):
        if not(self.is_running):
            raise Exception('No connection is currently running.')

        self.conn.stop()

        if self.is_prompt:
            print(f'The connection to server {self.host}:{self.port} has stopped.')

    def __del__(self):
        if self.is_running:
            self.stop()


# only for testing purpose.
if __name__ == '__main__':
    print('This is a test!')

    # demo server request handler
    # required args: received data
    def demo_server_handler(recd_data, conn):
        toclient = ''
        try:
            result = float(recd_data[0])** 2
            toclient = '%.4f' % result
        except:
            if recd_data[0] == conn.accept_msg:
                toclient = 'Input a number'
            else:
                toclient = 'Invalid input'
        conn.send(toclient)
        print(f'To client {conn.addr}: {toclient}')

    def demo_client_handler(recd_data, conn):
        user_input = input(' -> ')
        if user_input == 'q':
            conn.stop()
        else:
            conn.send(user_input)

    # Setting up the connection credential
    host = '127.0.0.1'
    port = 8765
    #max_request_queue = 10

    if input('select mode [sc]: ') == 's':
        # establish the server to the another thread.
        server = Server(host, port, is_prompt=True)
        server.set_request_handler(demo_server_handler)
        server.run()
    else:

        # establish the client to the another thread, that connected to the server.
        client = Client(host, port, is_prompt=True)
        client.set_response_handler(demo_client_handler)
        client.run()
