#!/usr/bin/env python3

import datetime
import json
import logging
import time
from types import SimpleNamespace

import config
import requests
from bot_common.decorators import allow_only
from telegram import Update
from telegram.ext import (CallbackContext, CommandHandler, PicklePersistence,
                          Updater)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.WARNING
)

logger = logging.getLogger(__name__)


def get_game(game_id):
    URL = f"https://lichess.org/game/export/{game_id}"
    res = requests.get(
        URL,
        params={
            "pgnInJson": "true",
            "moves": "false",
        },
        headers={"Accept": "application/json"},
    )
    return res


def get_current_games(user_ids: list[str]) -> dict[str, str]:
    URL = "https://lichess.org/api/users/status"
    page = requests.get(
        URL,
        params={
            "ids": ",".join(user_ids),
            "withGameIds": "true",
        },
    )
    if page.status_code != 200:
        raise RuntimeError(f"Failed to get lichess status: {page.status_code}")

    res = dict()
    for v in page.json():
        n = v["name"]
        if n:
            game_id = v.get("playingId", None)
            res[n] = game_id

    return res


def update_game(context: CallbackContext) -> None:
    try:
        sent_msg = context.job.context["msg"]
        game_id = context.job.context["game_id"]

        game = get_game(game_id)
        if game.status_code != 200:
            context.bot.edit_message_text(
                sent_msg.text + f"\nCouldn't update game status: {game.status_code}",
                chat_id=sent_msg.chat.id,
                message_id=sent_msg.message_id,
                disable_web_page_preview=True,
            )
            return

        game = json.loads(game.text, object_hook=lambda d: SimpleNamespace(**d))
        if game.status in ["created", "started"]:
            context.job_queue.run_once(
                update_game, context=context.job.context, when=60
            )
            return

        white = game.players.white
        black = game.players.black
        colors = ["⚪️", "⚫️"]
        ratings_str = ""
        # TODO: aborted game have no rating diff
        for i, player in enumerate([white, black]):
            ratings_str = (
                ratings_str
                + f"\n{colors[i]}{player.user.name} rating {player.rating} "
                + "{0:+d}".format(player.ratingDiff)
            )

        context.bot.edit_message_text(
            sent_msg.text + f"\nGame finished: {game.status}" + ratings_str,
            chat_id=sent_msg.chat.id,
            message_id=sent_msg.message_id,
            disable_web_page_preview=True,
        )
    except Exception as e:
        # TODO: specific exception types
        context.bot.send_message(sent_msg.chat.id, text=f"update msg error: {e}")


def update_current_games(context: CallbackContext) -> None:
    job = context.job
    cur_playing = job.context["cur_playing"]

    if not cur_playing:
        return

    new_games = get_current_games(cur_playing.keys())

    for n in cur_playing.keys():
        if n not in new_games:
            logger.warning(f"User {n} not found")
            continue

        if cur_playing[n] != new_games[n] and new_games[n]:
            old_game_id = cur_playing[n]

            game_url = "https://lichess.org/" + new_games[n]
            sent_msg = context.bot.send_message(
                job.context["chat_id"],
                text=f"{n} is playing:\n{game_url}",
                disable_web_page_preview=True,
                disable_notification=True,
            )

            # TODO: time config constant
            context.job_queue.run_once(
                update_game,
                when=60,
                context={
                    "msg": sent_msg,
                    "game_id": new_games[n],
                },
            )

            cur_playing[n] = new_games[n]


def start_updater_job(chat_id, job_queue, chat_data, bot):
    if "cur_playing" not in chat_data:
        chat_data["cur_playing"] = dict()

    remove_job_if_exists(str(chat_id), job_queue)
    job_queue.run_repeating(
        update_current_games,
        first=1,
        interval=config.POLL_INTERVAL,
        context={
            "chat_id": chat_id,
            "cur_playing": chat_data["cur_playing"],
        },
        name=str(chat_id),
    )
    users = list(chat_data["cur_playing"].keys())
    bot.send_message(
        chat_id,
        text="Bot enabled\n" f"Lichess users: {users}",
    )


@allow_only(config.OWNER_USERNAME)
def start(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    start_updater_job(chat_id, context.job_queue, context.chat_data, context.bot)
    context.bot_data["active_chats"].add(chat_id)


@allow_only(config.OWNER_USERNAME)
def stop(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    remove_job_if_exists(str(chat_id), context.job_queue)
    context.bot_data.get("active_chats", list()).remove(chat_id)
    update.message.reply_text("Bot stopped")


# TODO: allow_only after start
@allow_only(config.OWNER_USERNAME)
def add_user(update: Update, context: CallbackContext) -> None:
    if "cur_playing" not in context.chat_data:
        context.chat_data["cur_playing"] = {}

    for n in context.args:
        context.chat_data["cur_playing"][n] = None
    update.message.reply_text("Added users: " + str(context.args))


# TODO: allow_only after start
@allow_only(config.OWNER_USERNAME)
def del_user(update: Update, context: CallbackContext) -> None:
    if "cur_playing" not in context.chat_data:
        context.chat_data["cur_playing"] = {}

    for n in context.args:
        del context.chat_data["cur_playing"][n]
    update.message.reply_text("Removed users: " + str(context.args))


def status(update: Update, context: CallbackContext) -> None:
    if len(context.args) >= 2:
        context.user_data[context.args[0]] = context.args[1]
        context.chat_data[context.args[0]] = context.args[1]
        context.bot_data[context.args[0]] = context.args[1]

    update.message.reply_text("args: " + str(context.args))
    update.message.reply_text("user data: " + str(context.user_data))
    update.message.reply_text("chat data: " + str(context.chat_data))
    update.message.reply_text("bot  data: " + str(context.bot_data))


@allow_only(config.OWNER_USERNAME)
def clear_all(update: Update, context: CallbackContext) -> None:
    for d in [context.user_data, context.chat_data, context.bot_data]:
        d.clear()


def remove_job_if_exists(name: str, job_queue) -> bool:
    current_jobs = job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


def restore_saved_jobs(dispatcher):
    for chat_id in dispatcher.bot_data["active_chats"]:
        start_updater_job(
            chat_id, dispatcher.job_queue, dispatcher.chat_data[chat_id], dispatcher.bot
        )


def main() -> None:
    persistence = PicklePersistence(filename="lichess_spy_bot.pickle")
    updater = Updater(config.TELEGRAM_TOKEN, persistence=persistence)

    dispatcher = updater.dispatcher

    if "active_chats" not in dispatcher.bot_data:
        dispatcher.bot_data["active_chats"] = set()

    restore_saved_jobs(dispatcher)

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stop", stop))
    dispatcher.add_handler(CommandHandler("status", status))
    dispatcher.add_handler(CommandHandler("clear_all", clear_all))
    dispatcher.add_handler(CommandHandler("add_user", add_user))
    dispatcher.add_handler(CommandHandler("del_user", del_user))

    updater.start_polling()

    updater.idle()


if __name__ == "__main__":
    main()
