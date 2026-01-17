from slack_bolt import App

from .app_mentioned import app_mentioned_callback
from .message import message_callback


def register(app: App):
    app.event("app_mention")(app_mentioned_callback)
    app.event("message")(message_callback)
