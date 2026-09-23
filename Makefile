deploy:
	./scripts/dgx/deploy.sh

.PHONY: deploy run seed test extensions-test extensions-package db-start db-stop db-status db-reset models models-stop models-health models-test dgx-setup doctor dataset train train-smoke benchmark competition start stop results
run:
	./scripts/db/start.sh
	cd backend && python3 run.py
seed:
	PYTHONPATH=backend python3 scripts/demo_seed.py
test:
	./scripts/smoke_test.sh
extensions-test:
	./scripts/extensions/test_all.sh
extensions-package:
	./scripts/extensions/package_all.sh

db-start:
	./scripts/db/start.sh
db-stop:
	./scripts/db/stop.sh
db-status:
	./scripts/db/status.sh
db-reset:
	./scripts/db/reset.sh

models:
	./scripts/models/start_demo_stack.sh
models-stop:
	./scripts/models/stop_models.sh
models-health:
	./scripts/models/healthcheck.sh
models-test:
	python3 scripts/models/test_inference.py

dgx-setup:
	./scripts/dgx/setup.sh
doctor:
	./scripts/dgx/doctor.sh
dataset:
	./scripts/training/prepare_dataset.sh
train:
	./scripts/training/train_all.sh
train-smoke:
	./scripts/training/train_smoke.sh
benchmark:
	./scripts/competition/run_benchmarks.sh
competition:
	./scripts/competition/run_everything.sh
start:
	./scripts/dgx/start_stack.sh
stop:
	./scripts/dgx/stop_stack.sh
results:
	@cat experiments/results/HACKATHON_RESULTS.md
