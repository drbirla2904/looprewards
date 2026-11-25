.PHONY: deploy rollback backup logs ps shell superuser migrations-local migrations-check check-local test-local verify-local collectstatic-local run-local
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
migrations-check:
	DEBUG=1 ./venv/bin/python manage.py makemigrations --check
check-local:
	DEBUG=1 ./venv/bin/python manage.py check
test-local:
	DEBUG=1 ./venv/bin/python manage.py test
verify-local: check-local migrations-check test-local
collectstatic-local:
	DEBUG=1 ./venv/bin/python manage.py collectstatic --noinput
run-local:
	DEBUG=1 ./venv/bin/python manage.py runserver
