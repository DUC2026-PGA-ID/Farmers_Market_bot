from bot_server import BOT_MODE, run_local_server, run_polling


if __name__ == "__main__":
    if BOT_MODE == "polling":
        run_polling()
    else:
        run_local_server()
