# coding=utf-8

PORT = 8787

import socket
import errno
import datetime
import functools
import uuid
import json

from tornado import ioloop, iostream


class RoomHandler(object):
    @staticmethod
    def create_room(data):
        pass

    @staticmethod
    def get_room_list(data):
        pass

    @staticmethod
    def join_room(data):
        pass


HANDLER_MAP = {
    10: RoomHandler.create_room,
    12: RoomHandler.get_room_list,
    14: RoomHandler.join_room,
}


class Connecttion(object):

    def __init__(self, connection, address):
        self.stream = iostream.IOStream(connection)
        self.stream.set_close_callback(self.on_close)
        self.address = address
        self.write_data({
            "enentId": 1,
            "status": 1,
            "id": str(uuid.uuid4())
        })
        self._read()

    def write_data(self, data):
        self.stream.write(json.dumps(data))
        self.stream.write("\r\n")

    def _read(self):
        self.stream.read_until("\r\n", self.callback)

    def callback(self, data):
        self.handle_data(data)

    def on_close(self):
        print self.address, "closed at", datetime.datetime.now()

    def handle_data(self, data):
        try:
            data = json.loads(data[:-1])

            # eventId is must
            if "eventId" not in data or data["eventId"] not in HANDLER_MAP:
                print "NO eventId!!", data
            else:
                self.write_data(HANDLER_MAP[data["eventId"]](data))
            self._read()
        except ValueError as e:
            print datetime.datetime.now(), e


def connection_ready(sock, fd, events):
    while True:
        try:
            connection, address = sock.accept()
        except socket.error, e:
            if e[0] not in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise
            return
        else:
            print address, "connected at", datetime.datetime.now()
            connection.setblocking(0)
            Connecttion(connection, address)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setblocking(0)
    sock.bind(("", PORT))
    sock.listen(1)

    io_loop = ioloop.IOLoop.instance()
    callback = functools.partial(connection_ready, sock)
    io_loop.add_handler(sock.fileno(), callback, io_loop.READ)

    try:
        print "start on 127.0.0.1:%s" % (PORT, )
        io_loop.start()
    except KeyboardInterrupt:
        io_loop.stop()
        print "exited cleanly"


if __name__ == "__main__":
    main()
