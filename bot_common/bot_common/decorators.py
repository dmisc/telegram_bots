
from telegram import Update

def allow_only(allowed_username):
    def wrap1(func):
        def wrap2(*args, **kwargs):
            update = args[0]
            if not isinstance(update, Update):
                raise ValueError("@allow_only expects first decorated function argument to be telegram.Update")

            user = update.effective_user
            if not user or user.username != allowed_username:
                update.message.reply_text("User not recognized")
                return

            return func(*args, **kwargs)

        return wrap2
    return wrap1
