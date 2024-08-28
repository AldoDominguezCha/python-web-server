import socket
import threading
import argparse, sys
import os
import gzip
from collections import defaultdict
# This module provides a high-level interface for asynchronously executing callables
from concurrent.futures import ThreadPoolExecutor

HOST = '127.0.0.1'
PORT = 4221

def route(self, path):
    def decorator(handler_fn):
        self.route_handlers[path] = handler_fn

        def wrapper(*args, **kwargs):
            handler_fn(*args, **kwargs)

        return wrapper

    return decorator

def undefined_route_handler(self):
    print('Error: Requested undefined route.')

    status_code = 404
    status_message = 'Not Found'

    self.response.set_status_code(status_code)
    self.response.set_status_message(status_message)



def main():
    server_address = (HOST, PORT)
    # The 'with' statement is used to wrap the execution of a block with methods defined by a context manager. The
    # context manager handles the entry to, and the exit from, the desired runtime context for the execution of the
    # block of code. Basically 'with' executes the __enter__() and __exit__() methods provided by the context manager to properly initalize
    # and free the resources of the context manager.
    with socket.create_server(server_address, reuse_port=False) as server_socket:
        print(f'Server listening at {HOST}:{PORT}')
        # ThreadPoolExecutor is an Executor subclass that uses a pool of at most max_workers threads to execute asynchronous calls,
        # when max_workers is None or not given, it defaults to the number of processors in the machine multiplied by 5. Basically
        # the ThreadPoolExecutor provides a pool of reusable worker threads using the executor design pattern.
        with ThreadPoolExecutor(max_workers=None) as executor:
            while True:
                socket_to_client, address = server_socket.accept()
                executor.submit(lambda socket: HttpHandler(socket).handle_request(), socket_to_client)


class Request:
    method: str
    target: str
    endpoint: str
    headers = {}
    body: str

    def __init__(self, raw_message: str):
        message_parts = raw_message.split('\r\n')
        self.parse_request_line(message_parts[0])
        self.parse_headers(message_parts[1:-2])
        self.parse_body(message_parts[-1])

    def parse_request_line(self, message_request_line: str):
        self.method, self.target, _ = message_request_line.split(' ')
        # Parse the requested endpoint
        self.endpoint = self.target
        endpoint_end_idx = self.target.rfind('/')
        if endpoint_end_idx > 0:
            self.endpoint = self.target[:endpoint_end_idx]

        print(f'Target endpoint in the request: {self.endpoint}')



    def parse_headers(self, message_headers_raw: []):
        for header in message_headers_raw:
            key, value = header.split(':', 1)
            self.headers[key] = value.strip()

    def parse_body(self, raw_body):
        self.body = raw_body

class Response:
    __status_code: int
    __status_message: str
    __headers: str
    __body: str

    def __init__(self):
        self.__status_code = 200
        self.__status_message = 'OK'
        self.__headers = {}
        self.__body = ''

    def set_status_code(self, status_code: int):
        self.__status_code = status_code

    def set_status_message(self, status_message: str):
        self.__status_message = status_message

    def set_header(self, header_name, header_value):
        self.__headers[header_name] = header_value

    def get_body(self):
        return self.__body
    
    def set_body(self, body: str):
        self.__body = body

    def get_http_response_message(self, content_was_compressed):
        # Convert the headers from their original dict form to a list -> ['Header-Name: Hader-Value', ...]
        headers_list = ['{}: {}'.format(key, value) for key, value in self.__headers.items()]
        # Join all headers into a single string to be added in the HTTP response message
        joint_headers = '\r\n'.join(headers_list + [''])

        if content_was_compressed:
            return b"".join([bytes((f'HTTP/1.1 {self.__status_code} {self.__status_message}\r\n'), encoding='utf-8'), bytes((f'{joint_headers}\r\n'), encoding='utf-8'), self.__body])

        return "HTTP/1.1 {} {}\r\n{}\r\n{}".format(self.__status_code, self.__status_message, joint_headers, self.__body).encode()


class HttpHandler:
    client: socket
    request: Request
    response: Response
    route_handlers = defaultdict(lambda: undefined_route_handler)
    compression_schemes = { 'gzip' : lambda content: gzip.compress(bytes(content, 'utf-8')) }

    def __init__(self, socket_to_client):
        self.client = socket_to_client
        self.response = Response()
        self.register_routes()

    def parse(self, http_message: bytes):
        message: str = http_message.decode()
        self.request = Request(message)

    def register_routes(self):
        @route(self, '/')
        def root_handler(self):
            self.response.set_header('Content-Length', 0)

        @route(self, '/user-agent')
        def user_agent(self):
            header_value = self.request.headers.get('User-Agent', '')
            body = header_value

            self.response.set_header('Content-Type', 'text/plain')
            self.response.set_header('Content-Length', len(body))
            self.response.set_body(body)

        @route(self, '/echo')
        def echo(self):
            body = self.request.target.split('/', 2)[2]

            self.response.set_header('Content-Type', 'text/plain')
            self.response.set_header('Content-Length', len(body))
            self.response.set_body(body)

        @route(self, '/files')
        def files(self):
            parser = argparse.ArgumentParser()
            parser.add_argument('--directory')
            args = parser.parse_args()

            if self.request.method == 'GET':
                file_name = self.request.target.split('/', 2)[2]
                try:
                    file_path = args.directory + file_name
                    print(f' Target file path for retrieval: {file_path}')
                    file_size = os.path.getsize(file_path)

                    with open(file_path) as file:
                        content = file.read()

                    body = content

                    self.response.set_header('Content-Type', 'application/octet-stream')
                    self.response.set_header('Content-Length', file_size)
                    self.response.set_body(body)
                
                except FileNotFoundError as e:
                    print(e)
                    status_code = 404
                    status_message = 'Not Found'

                    self.response.set_status_code(status_code)
                    self.response.set_status_message(status_message)

            elif self.request.method == 'POST':
                file_name = self.request.target.split('/', 2)[2]
                text = self.request.body

                file_path = args.directory + file_name
                print(f' Target file path for creation: {file_path}')

                try:
                    with open(file_path, 'w') as file:
                        file.write(text)

                    status_code = 201
                    status_message = 'Created'

                    self.response.set_status_code(status_code)
                    self.response.set_status_message(status_message)
                except:
                    status_code = 400
                    status_message = 'Bad Request'

                    self.response.set_status_code(status_code)
                    self.response.set_status_message(status_message)

    def handle_request(self):
        http_message = self.client.recv(2**12)
        self.parse(http_message)

        self.route_handlers[self.request.endpoint](self)

        self.send_response(self.compress_content())

    def compress_content(self):
        if 'Accept-Encoding' in self.request.headers:
            allowed_encoding_schemes = self.request.headers['Accept-Encoding'].split(', ')

            for scheme in allowed_encoding_schemes:
                if scheme in self.compression_schemes:
                    self.response.set_body(self.compression_schemes[scheme](self.response.get_body()))
                    self.response.set_header('Content-Encoding', scheme)
                    self.response.set_header('Content-Length', len(self.response.get_body()))
                    
                    return True

        return False

            


    def send_response(self, content_was_compressed):
        # This is a high-level python method that sends the entire buffer we pass or throws an exception. It
        # does that by calling socket.send repeatedly un til the entire data has been sent or an error occurs
        self.client.sendall(self.response.get_http_response_message(content_was_compressed))
        # Mark this socket to communicate with the client as closed. All future operations
        # in the socket object will fail once it's been closed, the remote end (the socket in the actual client machine)
        # will receive no more data
        self.client.close()

if __name__ == "__main__":
    main()
