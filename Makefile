.PHONY: deploy rollback backup logs ps shell superuser migrations-local test-local
deploy:
	bash ./deploy/deploy.sh
rollback:
	bash ./deploy/rollback.sh
backup:
	bash ./deploy/backup.sh
logs:
	sudo journalctl -u offlet -f --no-pager
ps:
	systemctl status offlet --no-pager
shell:
	set -a; . ./.env; set +a; ./venv/bin/python manage.py shell
superuser:
	set -a; . ./.env; set +a; ./venv/bin/python manage.py createsuperuser
migrations-local:
	DEBUG=1 ./venv/bin/python manage.py makemigrations core
test-local:
	DEBUG=1 ./venv/bin/python manage.py test
