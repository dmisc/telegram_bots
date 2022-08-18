#!/usr/bin/env python3

import logging
import requests
import time, datetime
import json

from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

from config import *

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

LAST_SOLVED = { n : None for n in LEETCODE_NAMES }
LAST_ERROR = None

def request_question_data(title_slug):
    url = "https://leetcode.com/graphql/"
    request_data = {
        "query": 
            """
            query questionData($titleSlug: String!) {
              question(titleSlug: $titleSlug) {
                title
                titleSlug
                difficulty
                categoryTitle
                stats
              }
            }
            """,
        "variables": {
	    "titleSlug": title_slug,
        },
    }

    headers = {
            #"Referer": f"https://leetcode.com/{username}/",
            "Content-Type": "application/json",
    }
                
    x = requests.post(url, json = request_data, headers = headers)

    return x.json()["data"]["question"]

def request_submissions(username, item_count = 5):
    url = "https://leetcode.com/graphql/"
    request_data = {
        "query": 
            """query recentAcSubmissions($username: String!, $limit: Int!) {
                recentAcSubmissionList(username: $username, limit: $limit) {
                    id
                    title
                    titleSlug
                    timestamp
                }
            }""",
        "variables": {
            "username": username,
            "limit": item_count,
        },
    }

    headers = {
            "Referer": f"https://leetcode.com/{username}/",
            "Content-Type": "application/json",
    }
                
    x = requests.post(url, json = request_data, headers = headers)
    return x.json()

DIFFICULTY_EMOJI = {
    "Easy": "🟢",
    "Medium": "🟡",
    "Hard": "🔴",
}

def update_latest_submissions(context: CallbackContext) -> None:
    global LEETCODE_NAMES
    global LAST_ERROR
    job = context.job

    try:
        for name in LEETCODE_NAMES:
            subm_response = request_submissions(name)
            submissions = subm_response["data"]["recentAcSubmissionList"]
            if len(submissions) == 0:
                pass

            if submissions[0]["titleSlug"] != LAST_SOLVED[name]:
                msg = ""
                for sub in submissions:
                    if sub["titleSlug"] == LAST_SOLVED[name]:
                        break

                    msg += f'{name} solved <a href="https://leetcode.com/problems/{sub["titleSlug"]}/">{sub["title"]}</a>'
                    try:
                        q_data = request_question_data(sub["titleSlug"])
                        difficulty = DIFFICULTY_EMOJI[q_data["difficulty"]]
                        acceptance = json.loads(q_data["stats"])["acRate"]
                        msg += f"{difficulty} (acceptance {acceptance})"
                    except Exception as e:
                        msg += f" {e}"
                        pass
                    msg += "\n\n"

                LAST_SOLVED[name] = submissions[0]["titleSlug"]
                context.bot.send_message(job.context, text=msg, disable_web_page_preview=True, parse_mode="HTML")

    except Exception as e:
        LAST_ERROR = f"{datetime.datetime.now()}\nException: {str(e)}\nResponse: {subm_response}"
        # context.bot.send_message(job.context, text=f'Exception while requesting submissions:\n{str(e)}')
        pass


def start(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    user = update.effective_user
    if user and user.username == OWNER_USERNAME:
        remove_job_if_exists(str(chat_id), context)
        context.job_queue.run_repeating(update_latest_submissions, first=1, interval=POLL_INTERVAL, context=chat_id, name=str(chat_id))
        update.message.reply_text(
            "Bot enabled\n"
            f"Leetcode users: {LEETCODE_NAMES}"
        )
    else:
        update.message.reply_text("User not recognized")

def status(update: Update, context: CallbackContext) -> None:
    if LAST_ERROR:
        update.message.reply_text(LAST_ERROR)
    else:
        update.message.reply_text("No errors")


def stop(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Bot stopped")
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
    dispatcher.add_handler(CommandHandler("status", status))
    dispatcher.add_handler(CommandHandler("stop", stop))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
