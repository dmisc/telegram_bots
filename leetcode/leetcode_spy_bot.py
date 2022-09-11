#!/usr/bin/env python3

import datetime
import json
import logging
import time

import config
import requests
from bot_common.decorators import allow_only
from telegram import Update
from telegram.ext import (CallbackContext, CommandHandler, Defaults,
                          PicklePersistence, Updater)

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
    chat_id = job.context["chat_id"]
    last_solved = job.context["last_solved"]

    for name in last_solved.keys():
        try:
            submissions = request_submissions(name)
        except Exception as e:
            logger.error("request_submissions: ", e)
            continue

        if len(submissions) == 0:
            continue

        if submissions[0]["titleSlug"] != last_solved[name]:
            msg = ""
            for sub in submissions:
                if sub["titleSlug"] == last_solved[name]:
                    break

                msg += f'{name} solved <a href="https://leetcode.com/problems/{sub["titleSlug"]}/">{sub["title"]}</a>'
                try:
                    q_data = request_question_data(sub["titleSlug"])
                    difficulty = DIFFICULTY_EMOJI[q_data["difficulty"]]
                    acceptance = json.loads(q_data["stats"])["acRate"]
                    msg += f"{difficulty} (acceptance {acceptance})"
                except Exception as e:
                    logger.error("request_question_data: ", e)

                msg += "\n\n"

            last_solved[name] = submissions[0]["titleSlug"]
            context.bot.send_message(
                chat_id, text=msg, disable_web_page_preview=True, parse_mode="HTML"
            )


@allow_only(config.OWNER_USERNAME)
def start(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    start_updater_job(chat_id, context.job_queue, context.chat_data, context.bot)
    context.bot_data["active_chats"].add(chat_id)


def status(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("args: " + str(context.args))
    update.message.reply_text("user data: " + str(context.user_data))
    update.message.reply_text("chat data: " + str(context.chat_data))
    update.message.reply_text("bot  data: " + str(context.bot_data))


@allow_only(config.OWNER_USERNAME)
def stop(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    remove_job_if_exists(str(chat_id), context)
    update.message.reply_text("Bot stopped")


def remove_job_if_exists(name: str, job_queue) -> bool:
    current_jobs = job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


@allow_only(config.OWNER_USERNAME)
def clear_all(update: Update, context: CallbackContext) -> None:
    for d in [context.user_data, context.chat_data, context.bot_data]:
        d.clear()


# TODO: allow_only after start
@allow_only(config.OWNER_USERNAME)
def add_user(update: Update, context: CallbackContext) -> None:
    if "last_solved" not in context.chat_data:
        context.chat_data["last_solved"] = dict()

    for n in context.args:
        context.chat_data["last_solved"][n] = None
    update.message.reply_text("Added users: " + str(context.args))


# TODO: allow_only after start
@allow_only(config.OWNER_USERNAME)
def del_user(update: Update, context: CallbackContext) -> None:
    if "last_solved" not in context.chat_data:
        context.chat_data["last_solved"] = dict()

    for n in context.args:
        del context.chat_data["last_solved"][n]
    update.message.reply_text("Removed users: " + str(context.args))


def start_updater_job(chat_id, job_queue, chat_data, bot):
    if "last_solved" not in chat_data:
        chat_data["last_solved"] = dict()

    remove_job_if_exists(str(chat_id), job_queue)
    job_queue.run_repeating(
        update_latest_submissions,
        first=1,
        interval=config.POLL_INTERVAL,
        context={
            "chat_id": chat_id,
            "last_solved": chat_data["last_solved"],
        },
        name=str(chat_id),
    )
    users = list(chat_data["last_solved"].keys())
    bot.send_message(chat_id, text=f"Bot enabled\nLeetcode users: {users}")


def restore_saved_jobs(dispatcher):
    for chat_id in dispatcher.bot_data["active_chats"]:
        start_updater_job(
            chat_id, dispatcher.job_queue, dispatcher.chat_data[chat_id], dispatcher.bot
        )


def main() -> None:
    persistence = PicklePersistence(filename="leetcode_spy_bot.pickle")
    updater = Updater(
        config.TELEGRAM_TOKEN, persistence=persistence, defaults=Defaults(timeout=120)
    )

    dispatcher = updater.dispatcher

    if "active_chats" not in dispatcher.bot_data:
        dispatcher.bot_data["active_chats"] = set()

    restore_saved_jobs(dispatcher)

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("status", status))
    dispatcher.add_handler(CommandHandler("stop", stop))
    dispatcher.add_handler(CommandHandler("clear_all", clear_all))
    dispatcher.add_handler(CommandHandler("add_user", add_user))
    dispatcher.add_handler(CommandHandler("del_user", del_user))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
