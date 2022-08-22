#!/usr/bin/env python3

import datetime
import json
import logging
import time
from dataclasses import dataclass

import requests
from bot_common.decorators import allow_only
from telegram import Update
from telegram.ext import CallbackContext, CommandHandler, Defaults, Updater

import config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.WARNING
)
logger = logging.getLogger(__name__)

LEETCODE_GQL_URL = "https://leetcode.com/graphql/"

DIFFICULTY_EMOJI = {
    "Easy": "🟢",
    "Medium": "🟡",
    "Hard": "🔴",
}


@dataclass
class LastError:
    value: str


def request_question_data(title_slug):
    request_data = {
        "query": """
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
        "Referer": f"https://leetcode.com/problems/{title_slug}/",
        "Content-Type": "application/json",
    }

    x = requests.post(LEETCODE_GQL_URL, json=request_data, headers=headers)

    return x.json()["data"]["question"]


def request_submissions(username, item_count=5):
    request_data = {
        "query": """
            query recentAcSubmissions($username: String!, $limit: Int!) {
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

    x = requests.post(LEETCODE_GQL_URL, json=request_data, headers=headers)
    return x.json()["data"]["recentAcSubmissionList"]


def update_latest_submissions(context: CallbackContext) -> None:
    job = context.job
    name = job.context["username"]
    chat_id = job.context["chat_id"]
    last_solved = job.context["last_solved"]

    try:
        submissions = request_submissions(name)
    except Exception as e:
        logger.error("request_submissions: ", e)
        LastError.value = (
            f"{datetime.datetime.now()}\nException: {str(e)}\nResponse: {subm_response}"
        )
        return

    if len(submissions) == 0:
        return

    if submissions[0]["titleSlug"] != last_solved:
        msg = ""
        for sub in submissions:
            if sub["titleSlug"] == last_solved:
                break

            msg += f'{name} solved <a href="https://leetcode.com/problems/{sub["titleSlug"]}/">{sub["title"]}</a>'
            try:
                q_data = request_question_data(sub["titleSlug"])
                difficulty = DIFFICULTY_EMOJI[q_data["difficulty"]]
                acceptance = json.loads(q_data["stats"])["acRate"]
                msg += f"{difficulty} (acceptance {acceptance})"
            except Exception as e:
                msg += f" {e}"

            msg += "\n\n"

        job.context["last_solved"] = submissions[0]["titleSlug"]
        context.bot.send_message(
            chat_id, text=msg, disable_web_page_preview=True, parse_mode="HTML"
        )


@allow_only(config.OWNER_USERNAME)
def start(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id

    remove_job_if_exists(str(chat_id), context)
    for username in config.LEETCODE_NAMES:
        context.job_queue.run_repeating(
            update_latest_submissions,
            first=1,
            interval=config.POLL_INTERVAL,
            context={
                "chat_id": chat_id,
                "username": username,
                "last_solved": None,
            },
            name=str(chat_id),
        )
    update.message.reply_text(
        "Bot enabled\n" f"Leetcode users: {config.LEETCODE_NAMES}"
    )


def status(update: Update, context: CallbackContext) -> None:
    if LastError.value:
        update.message.reply_text(LastError.value)
    else:
        update.message.reply_text("No errors")


@allow_only(config.OWNER_USERNAME)
def stop(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    remove_job_if_exists(str(chat_id), context)
    update.message.reply_text("Bot stopped")


def remove_job_if_exists(name: str, context: CallbackContext) -> bool:
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


def main() -> None:
    updater = Updater(config.TELEGRAM_TOKEN, defaults=Defaults(timeout=120))

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("status", status))
    dispatcher.add_handler(CommandHandler("stop", stop))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
