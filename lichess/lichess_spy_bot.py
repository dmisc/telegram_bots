#!/usr/bin/env python3

import logging
import requests
import time, datetime
from types import SimpleNamespace
import json

from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

import config

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING
)

logger = logging.getLogger(__name__)

CUR_PLAYING = { n : None for n in config.LICHESS_NAMES }

def allow_only(allowed_username):
    def wrap1(func):
        def wrap2(*args, **kwargs):
            update = args[0]
            if not isinstance(update, Update):
                raise ValueError("@allow_only expects first arguments to be telegram.Update")

            user = update.effective_user
            if not user or user.username != allowed_username:
                update.message.reply_text("User not recognized")
                return

            return func(*args, **kwargs)

        return wrap2
    return wrap1


def get_game(game_id):
    URL = f"https://lichess.org/game/export/{game_id}"
    res = requests.get(URL, 
        params={
            "pgnInJson": "true",
            "moves": "false",
        },
        headers={
            "Accept":"application/json"
        })
    return res

def get_current_games(user_ids: list[str]) -> dict[str, str]:
    URL = "https://lichess.org/api/users/status"
    page = requests.get(URL, 
        params={
            "ids": ','.join(user_ids),
            "withGameIds": "true",
        })
    if page.status_code != 200:
        raise RuntimeError(f"Failed to get lichess status: {page.status_code}")

    res = dict()
    for v in page.json():
        n = v['name']
        if n:
            game_id = v.get('playingId', None)
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
                message_id=sent_msg.message_id, disable_web_page_preview=True)
            return

        game = json.loads(game.text, object_hook=lambda d: SimpleNamespace(**d))
        if game.status in ["created", "started"]:
            context.job_queue.run_once(update_game, context=context.job.context, when=60)
            return

        white = game.players.white
        black = game.players.black
        colors = ["⚪️", "⚫️"]
        ratings_str = ""
        for i, player in enumerate([white, black]):
            ratings_str = ratings_str + f"\n{colors[i]}{player.user.name} rating {player.rating} " + "{0:+d}".format(player.ratingDiff)

        context.bot.edit_message_text(
            sent_msg.text + f"\nGame finished: {game.status}" + ratings_str,
            chat_id=sent_msg.chat.id,
            message_id=sent_msg.message_id, disable_web_page_preview=True)
    except Exception as e:
        print(f"Exception: {e}")
        context.bot.send_message(sent_msg.chat.id, text=f"update msg error: {e}")


def update_current_games(context: CallbackContext) -> None:
    global CUR_PLAYING
    job = context.job

    new_games = get_current_games(config.LICHESS_NAMES)

    for n in config.LICHESS_NAMES:
        if n not in new_games:
            logger.warning(f"User {n} not found")
            continue

        if CUR_PLAYING[n] != new_games[n] and new_games[n]:
            old_game_id = CUR_PLAYING[n]

            game_url = "https://lichess.org/" + new_games[n]
            sent_msg = context.bot.send_message(job.context, text=f'{n} is playing:\n{game_url}', disable_web_page_preview=True, disable_notification=True)

            # TODO: time config constant
            context.job_queue.run_once(update_game, when=60, 
                context={
                    "msg": sent_msg,
                    "game_id": new_games[n],
                }
            )

            CUR_PLAYING[n] = new_games[n]


@allow_only(config.OWNER_USERNAME)
def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if not user or user.username != config.OWNER_USERNAME:
        update.message.reply_text("User not recognized")
        return

    chat_id = update.message.chat_id
    remove_job_if_exists(str(chat_id), context)
    context.job_queue.run_repeating(update_current_games, first=1, interval=config.POLL_INTERVAL, context=chat_id, name=str(chat_id))
    update.message.reply_text(
        "Bot enabled\n"
        f"Lichess users: {config.LICHESS_NAMES}"
    )


@allow_only(config.OWNER_USERNAME)
def stop(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if not user or user.username != config.OWNER_USERNAME:
        update.message.reply_text("User not recognized")
        return

    chat_id = update.message.chat_id
    remove_job_if_exists(str(chat_id), context)


def remove_job_if_exists(name: str, context: CallbackContext) -> bool:
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


def main() -> None:
    updater = Updater(config.TELEGRAM_TOKEN)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stop", stop))

    updater.start_polling()

    updater.idle()


if __name__ == '__main__':
    main()
