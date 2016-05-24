# coding=utf-8

PORT = 8787

import socket
import errno
import datetime
import functools
import uuid
import json
import random
import logging

logging.basicConfig(level=logging.INFO, format="[%(name)s][%(levelname)s][%(asctime)s]: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

import redis
from tornado import ioloop, iostream


stream_map = {}


def _get_user_key(user_token):
    return "fc:user:" + str(user_token)


def _get_room_key(room_id):
    return "fc:room:" + str(room_id)


def _get_room_id(room_key):
    return room_key.rsplit(":", 1)[-1]


class RedisClient(object):

    host = "localhost"
    port = 6379

    @classmethod
    def get_client(cls):
        if not hasattr(cls, "_pool"):
            cls._pool = redis.ConnectionPool(host=cls.host, port=cls.port)
        return redis.Redis(connection_pool=cls._pool)


class RoomHandler(object):

    @classmethod
    def write_data(cls, stream, data):
        stream.write(json.dumps(data))
        stream.write("\r\n")

    @classmethod
    def create_room(cls, stream, data):
        success = False
        client = RedisClient.get_client()
        previous_room = client.get(_get_user_key(data["id"]))
        if str(previous_room) == "0":
            room_id = random.randint(1, 9999)
            while client.exists(_get_room_key(room_id)):
                room_id = random.randint(1, 9999)

            # add player
            client.lpush(_get_room_key(room_id), data["id"])

            # set room info
            client.set(_get_user_key(data["id"]), room_id)

            success = True

        if success:
            logging.info(("create room", room_id))
            cls.write_data(stream, {
                "eventId": 11,
                "status": 1,
                "room_id": room_id,
                "player_sum": client.llen(_get_room_key(room_id))
            })
        else:
            logging.info((data["id"], "still in game"))
            cls.write_data(stream, {
                "eventId": 11,
                "status": 0,
                "msg": u"in game, failed to create room!"
            })

    @classmethod
    def get_room_list(cls, stream, data):
        client = RedisClient.get_client()
        room_keys = client.keys(_get_room_key("*"))
        result = [{
            "room_id": _get_room_id(room_key),
            "people_sum": client.llen(room_key)
        } for room_key in room_keys]
        cls.write_data(stream, {
            "eventId": 13,
            "status": 1,
            "result": result
        })

    @classmethod
    def join_room(cls, stream, data):
        client = RedisClient.get_client()
        previous_room = client.get(_get_user_key(data["id"]))
        if str(previous_room) == "0" and client.exists(_get_room_key(data["room_id"])):
            player_ids = client.lrange(_get_room_key(data["room_id"]), 0, -1)
            client.lpush(_get_room_key(data["room_id"]), data["id"])
            player_sum = client.llen(_get_room_key(data["room_id"]))
            client.set(_get_user_key(data["id"]), data["room_id"])
            response = {
                "eventId": 15,
                "status": 1,
                "player_sum": player_sum
            }
            other_notify = {
                "eventId": 16,
                "status": 1,
                "player_sum": player_sum
            }
            cls.write_data(stream, response)
            for player_id in player_ids:
                cls.write_data(stream_map[player_id], other_notify)
            logging.info((response, player_ids, other_notify))
        else:
            logging.info(("fail to join room", data))
            cls.write_data(stream, {
                "eventId": 15,
                "status": 0,
                "msg": "fail to join room"
            })


HANDLER_MAP = {
    10: RoomHandler.create_room,
    12: RoomHandler.get_room_list,
    14: RoomHandler.join_room,
}


class Connection(object):

    def __init__(self, connection, address):
        self.stream = iostream.IOStream(connection)
        self.stream.set_close_callback(self.on_close)
        self.address = address

        client = RedisClient.get_client()
        user_token = str(uuid.uuid4())
        while client.exists(_get_user_key(user_token)):
            user_token = str(uuid.uuid4())

        stream_map[user_token] = self.stream

        client.set(_get_user_key(user_token), 0)
        self.write_data({
            "eventId": 1,
            "status": 1,
            "id": user_token
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
                HANDLER_MAP[data["eventId"]](self.stream, data)
        except ValueError as e:
            logging.error((datetime.datetime.now(), e))
        finally:
            self._read()


def connection_ready(sock, fd, events):
    while True:
        try:
            connection, address = sock.accept()
        except socket.error, e:
            if e[0] not in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise
            return
        else:
            logging.info((address, "connected at", datetime.datetime.now()))
            connection.setblocking(0)
            Connection(connection, address)


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
    client = RedisClient.get_client()
    client.flushdb()
    main()
