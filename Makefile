.PHONY: bootstrap install run doctor test tunnel

bootstrap:
	./scripts/start.sh --bootstrap-only

install:
	./install.sh

run:
	./scripts/start.sh --foreground

doctor:
	./venv/bin/python -m compileall src
	bash -n action/1_android.sh action/1_ios.sh scripts/start.sh scripts/clean.sh

test:
	./venv/bin/python -m unittest discover -s tests -p 'test_*.py'

tunnel:
	ngrok http 8000
