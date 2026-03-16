.PHONY: bootstrap install run doctor test tunnel

bootstrap:
	./scripts/bootstrap_macos.sh

install:
	./install.sh

run:
	./venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000

doctor:
	./venv/bin/python -m compileall src
	bash -n action/1_android.sh action/1_ios.sh local_run.sh scripts/restart_local_server.sh

test:
	./venv/bin/python -m unittest discover -s tests -p 'test_*.py'

tunnel:
	ngrok http 8000
