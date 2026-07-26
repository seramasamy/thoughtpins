from __future__ import annotations


class FakeTelegramUser:
    def __init__(self, user_id: int = 12345):
        self.id = user_id


class FakeTelegramChat:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def send_action(self, action: str) -> None:
        self.actions.append(action)


class FakeTelegramMessage:
    def __init__(self, text: str, *, chat_id: str = "chat-e2e", user_id: int = 12345):
        self.text = text
        self.chat_id = chat_id
        self.message_id = 1001
        self.from_user = FakeTelegramUser(user_id)
        self.chat = FakeTelegramChat()
        self.replies: list[str] = []
        self.documents: list[dict] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)

    async def reply_document(self, **kwargs) -> None:
        self.documents.append(kwargs)


class FakeTelegramUpdate:
    def __init__(self, text: str, *, chat_id: str = "chat-e2e", user_id: int = 12345):
        self.message = FakeTelegramMessage(text, chat_id=chat_id, user_id=user_id)


class FakeTelegramContext:
    def __init__(self, args: list[str] | None = None):
        self.args = list(args or [])
