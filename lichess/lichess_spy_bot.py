#!/usr/bin/env python3

import logging
import requests
import time, datetime
from types import SimpleNamespace
import json

from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

from config import *

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

CUR_PLAYING = { n : None for n in LICHESS_NAMES }

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
    global LICHESS_NAMES
    job = context.job

    URL = "https://lichess.org/api/users/status"
    page = requests.get(URL, 
        params={
            "ids": ','.join(LICHESS_NAMES),
            "withGameIds": "true",
        })
    if page.status_code != 200:
        print("lichess error code: ", page.status_code)
        # context.bot.send_message(job.context, text=f'Lichess error: {page}')

    tmp = dict()
    for v in page.json():
        n = v['name']
        if n:
            game_id = v.get('playingId', None)
            tmp[n] = game_id

    for n in LICHESS_NAMES:
        if n not in tmp:
            context.bot.send_message(job.context, text=f'User {n} not found, removing')
            LICHESS_NAMES.remove(n)
            continue

        if CUR_PLAYING[n] != tmp[n] and tmp[n]:
            #c = datetime.datetime.now().strftime("%s")
            #tv_url = f"https://lichess.org/{n}/tv?v={c}"
            old_game_id = CUR_PLAYING[n]

            game_url = "https://lichess.org/" + tmp[n]
            sent_msg = context.bot.send_message(job.context, text=f'{n} is playing:\n{game_url}', disable_web_page_preview=True, disable_notification=True)

            context.job_queue.run_once(update_game, when=60, 
                context={
                    "msg": sent_msg,
                    "game_id": tmp[n],
                    }
            )

            CUR_PLAYING[n] = tmp[n]


def start(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    user = update.effective_user
    if user and user.username == OWNER_USERNAME:
        remove_job_if_exists(str(chat_id), context)
        context.job_queue.run_repeating(update_current_games, interval=POLL_INTERVAL, context=chat_id, name=str(chat_id))
        update.message.reply_text(
            "Bot enabled\n"
            f"Lichess users: {LICHESS_NAMES}"
        )
    else:
        update.message.reply_text("User not recognized")


def stop(update: Update, context: CallbackContext) -> None:
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
    updater = Updater(TELEGRAM_TOKEN)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stop", stop))

    updater.start_polling()

    updater.idle()


if __name__ == '__main__':
    main()
