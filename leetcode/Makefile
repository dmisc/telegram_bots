
all: run

.install.stamp: poetry.lock pyproject.toml
	poetry install
	touch .install.stamp

init: .install.stamp

run: init
	poetry run leetcode_spy_bot

SERVICE_NAME := leetcode_spy_bot.service
SERVICE_PATH := ${HOME}/.config/systemd/user/${SERVICE_NAME}
service_start: init
	cp ../template.service ${SERVICE_PATH}
	sed -i "s^{PROJ_ROOT}^`pwd`^g" ${SERVICE_PATH}
	sed -i "s^{POETRY}^`which poetry`^g" ${SERVICE_PATH}
	systemctl --user daemon-reload
	systemctl --user enable ${SERVICE_NAME}
	systemctl --user restart ${SERVICE_NAME}

service_stop:
	systemctl --user disable ${SERVICE_NAME}
	systemctl --user stop ${SERVICE_NAME}

service_status:
	systemctl --user status ${SERVICE_NAME}

# Lint and check for formatting
check: init
	poetry run black --check *.py
	poetry run isort -c *.py

# Autoformat
format: init
	poetry run black *.py
	poetry run isort *.py
