from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from . import realtime, services


class GameConsumer(AsyncJsonWebsocketConsumer):
    game_id: str
    room_group_name: str
    user_id: int
    username: str
    player_slot: int | None

    async def connect(self) -> None:
        self.game_id = self.scope["url_route"]["kwargs"]["game_id"]
        self.room_group_name = realtime.room_name(self.game_id)
        self.player_slot = None

        ticket = parse_qs(self.scope["query_string"].decode("utf-8")).get("ticket", [None])[0]
        if not ticket:
            await self.close(code=4401)
            return

        try:
            self.user_id = await database_sync_to_async(services.verify_ws_ticket)(
                game_id=self.game_id,
                ticket=ticket,
            )
            state = await database_sync_to_async(services.get_game_state_for_user)(
                self.game_id,
                self.user_id,
            )
        except Exception:
            await self.close(code=4403)
            return

        self.player_slot = state["my_slot"]
        my_slot_state = next(
            (slot for slot in state["slots"] if slot["slot"] == self.player_slot),
            None,
        )
        self.username = my_slot_state["username"] if my_slot_state else "Player"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "game_state", "state": state})
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "room.presence",
                "event_name": "player_joined",
                "username": self.username,
                "sender_channel": self.channel_name,
            },
        )

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            if hasattr(self, "username"):
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "room.presence",
                        "event_name": "player_left",
                        "username": self.username,
                        "sender_channel": self.channel_name,
                    },
                )

    async def receive_json(self, content: dict, **kwargs) -> None:
        event_type = str(content.get("type") or "")
        if event_type != "chat_message":
            await self.send_json({"type": "error", "error": "Unsupported event"})
            return

        result = await database_sync_to_async(services.create_chat_message_for_user)(
            game_id=self.game_id,
            user_id=self.user_id,
            body=str(content.get("body") or ""),
        )
        if not result["ok"]:
            await self.send_json({"type": "error", "error": result["error"]})

    async def room_game_state(self, event: dict) -> None:
        try:
            state = await database_sync_to_async(services.get_game_state_for_user)(
                self.game_id,
                self.user_id,
            )
        except Exception:
            return

        self.player_slot = state["my_slot"]
        await self.send_json({"type": event["event_name"], "state": state})

    async def room_chat_message(self, event: dict) -> None:
        payload = dict(event["payload"])
        payload["mine"] = payload.get("author_slot") == self.player_slot
        await self.send_json({"type": event["event_name"], "message": payload})

    async def room_presence(self, event: dict) -> None:
        if event.get("sender_channel") == self.channel_name:
            return
        await self.send_json(
            {
                "type": event["event_name"],
                "username": event["username"],
            }
        )
