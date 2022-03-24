#!/usr/bin/env python3

import logging
import requests
import time, datetime

from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

from config import *

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

CUR_PLAYING = { n : None for n in LICHESS_NAMES }

def test_req(context: CallbackContext) -> None:
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

    #print(page.json())
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
            game_url = "https://lichess.org/" + tmp[n]
            context.bot.send_message(job.context, text=f'{n} is playing:\n{game_url}')
            CUR_PLAYING[n] = tmp[n]

    #context.bot.send_message(job.context, text=f'{page.json()}')

def start(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    user = update.effective_user
    if user and user.username == OWNER_USERNAME:
        remove_job_if_exists(str(chat_id), context)
        context.job_queue.run_repeating(test_req, interval=POLL_INTERVAL, context=chat_id, name=str(chat_id))
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
