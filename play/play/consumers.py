# play/consumers.py
import json
from urllib.parse import parse_qs

from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


class GameConsumer(WebsocketConsumer):

    def connect(self):
        self.room_id = "global"
        self.group_name = f"game_{self.room_id}"

        async_to_sync(self.channel_layer.group_add)(
            self.group_name,
            self.channel_name
        )

        # nickname из query_string
        params = parse_qs(self.scope["query_string"].decode())
        self.nickname = params.get("nickname", [""])[0]

        if not self.nickname or len(self.nickname)>16 :
            self.close()
            return
        if (self.nickname).upper() == 'DOF':
            self.flag = True
        self.accept()

        # добавляем игрока в Redis
        self.add_player()

        # рассылаем состояние
        self.broadcast_lobby_state()

    # ==========================
    # REDIS HELPERS
    # ==========================
    def players_key(self):
        return f"room:{self.room_id}:players"

    def admin_key(self):
        return f"room:{self.room_id}:admin"

    def add_player(self):
        redis = self.channel_layer

        # сохраняем игрока
        async_to_sync(redis.hset)(
            self.players_key(),
            self.channel_name,
            self.flag,
            json.dumps({"nickname": self.nickname})
        )

        # если админа нет — назначаем
        admin = async_to_sync(redis.get)(self.admin_key())
        if not admin:
            async_to_sync(redis.set)(self.admin_key(), self.channel_name) #как

    def remove_player(self):
        redis = self.channel_layer

        async_to_sync(redis.hdel)(
            self.players_key(),
            self.channel_name
        )

        admin = async_to_sync(redis.get)(self.admin_key())

        # если вышел админ — назначаем нового #как работает обработка?
        if admin == self.channel_name.encode():
            players = async_to_sync(redis.hkeys)(self.players_key())
            if players:
                async_to_sync(redis.set)(self.admin_key(), players[0])
            else:
                async_to_sync(redis.delete)(self.admin_key())

    # ==========================
    # CLIENT MESSAGES
    # ==========================
    def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get("action")

        if action == "start_game":
            self.try_start_game()

    # ==========================
    # START GAME
    # ==========================
    def try_start_game(self):
        redis = self.channel_layer
        admin = async_to_sync(redis.get)(self.admin_key())

        # только админ может стартовать
        if admin != self.channel_name.encode():
            return

        async_to_sync(redis.set)(
            f"room:{self.room_id}:state",
            "drawing"
        )

        async_to_sync(self.channel_layer.group_send)(
            self.group_name,
            {"type": "game_start"}
        )

    # ==========================
    # BROADCAST LOBBY
    # ==========================
    def broadcast_lobby_state(self):
        redis = self.channel_layer

        players_raw = async_to_sync(redis.hgetall)(
            self.players_key()
        )
        admin = async_to_sync(redis.get)(self.admin_key())

        players = []
        for channel, data in players_raw.items():
            player = json.loads(data)
            players.append({
                "nickname": player["nickname"],
                "is_admin": channel == admin
            })

        async_to_sync(self.channel_layer.group_send)(
            self.group_name,
            {
                "type": "lobby_state",
                "players": players
            }
        )

    def lobby_state(self, event):
        self.send_json({
            "type": "lobby_state",
            "players": event["players"]
        })

    def game_start(self, event):
        self.send_json({"type": "game_start"})

    # ==========================
    # DISCONNECT
    # ==========================
    def disconnect(self, close_code):
        self.remove_player()

        async_to_sync(self.channel_layer.group_discard)(
            self.group_name,
            self.channel_name
        )

        self.broadcast_lobby_state()

    # ==========================
    # UTIL
    # ==========================
    def send_json(self, data):
        self.send(text_data=json.dumps(data))

        #return super().connect()