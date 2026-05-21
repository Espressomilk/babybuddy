import json

from channels.generic.websocket import AsyncWebsocketConsumer


class TrackConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if not self.scope["user"].is_authenticated:
            await self.close()
            return

        self.child_slug = self.scope["url_route"]["kwargs"]["child_slug"]
        self.group_name = f"track_{self.child_slug}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass  # server-push only; clients don't send messages

    async def state_changed(self, event):
        await self.send(text_data=json.dumps({"type": "refresh"}))
