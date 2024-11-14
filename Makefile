#### Python Environment ####
.PHONY: install
install: 
	pip install -r ./build-requirements.txt
	pipconf --set personal-config
	pip install -r ./requirements.txt
	pip install -r ./dev-requirements.txt

.PHONY: uninstall
uninstall:
	pipconf --set personal-config
	@bash -c "pip uninstall -y -r <(pip freeze)"

#### Testing ####
TEST_COMMANDS = \
	--cov=tea \
	--cov-config=setup.cfg \
	--cov-report html \
	--cov-report term

.PHONY: test
test: test.clean test.unit 
	rm -rf htmlcov/
	rm -f .coverage

.PHONY: test.clean
test.clean:
	rm -rf htmlcov/
	rm -f .coverage

.PHONY: test.unit
test.unit: 
	pytest -rfEP $(TEST_COMMANDS) test/unit

#### Code Style ####
LINT_DIRS = src/ test/
LINT_COMMANDS = \
	isort -q --profile black --check-only $(LINT_DIRS) && \
	black -q --check --diff $(LINT_DIRS) && \
	flake8 $(LINT_DIRS) && \
# eventually use mypy --> mypy --show-error-codes $(LINT_DIRS)

.PHONY: lint
lint:
	$(LINT_COMMANDS)

.PHONY: format
format:
	isort -q --profile black $(LINT_DIRS)
	black -q $(LINT_DIRS)



#### Build/Publish ####
# --- Env vars
-include .env.publish
ARTIFACT_REGISTRY_HOST ?= $(or $(ARTIFACT_REGISTRY_HOST),us-west1-docker.pkg.dev/)
DOCKER_IMAGE ?= $(or $(DOCKER_IMAGE),dockmaster)

# --- Version from package
VERSION=`grep __version__ src/dockyard/__init__.py | awk '{print $$3}' | tr -d '"'`
TAGNAME=v$(VERSION)
DOCKER_TAG=$(VERSION)

# # --- Local build ---
# .PHONY: publish.build
# build:
# 	@echo "Building frontend..."
# 	npm run build

.PHONY: publish.tag
publish.tag:
	@echo "---Tagging commit hash $(TAGNAME)"
	git tag -a $(TAGNAME) -m "Release $(TAGNAME)"
	git push origin $(TAGNAME)
	@echo "---Pushed tag as version=$(VERSION)"

#### Docker Commands ####
.PHONY: docker.help
docker.help:
	@echo "Docker commands:"
	@echo "  make docker.build      - Build Docker image and tag for production"
	@echo "  make docker.build.dev  - Build Docker image for local development"
	@echo "  make docker.push       - Push to Google Artifact Repository"

.PHONY: docker.build
docker.build:
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .
	docker tag $(DOCKER_IMAGE):$(DOCKER_TAG) $(DOCKER_IMAGE):latest
	docker tag $(DOCKER_IMAGE):$(DOCKER_TAG) $(ARTIFACT_REGISTRY_HOST)/$(DOCKER_IMAGE):$(DOCKER_TAG)
	docker tag $(DOCKER_IMAGE):$(DOCKER_TAG) $(ARTIFACT_REGISTRY_HOST)/$(DOCKER_IMAGE):latest

.PHONY: docker.build.dev
docker.build.dev:
	docker build --target python-base -t $(DOCKER_IMAGE):local .
	docker tag $(DOCKER_IMAGE):local $(DOCKER_IMAGE):latest

.PHONY: docker.push
docker.push:
	@echo "Pushing waypoint image to GAR..."
	docker push ${ARTIFACT_REGISTRY_HOST}/${DOCKER_IMAGE}:$(DOCKER_TAG)
	docker push ${ARTIFACT_REGISTRY_HOST}/${DOCKER_IMAGE}:latest
	@echo "Push completed successfully"

#### Context ####
.PHONY: context
context: context.clean context.src context.public context.settings

.PHONY: context.src
context.src:
	repo2txt -r ./src/ -o ./context/context-src.txt \
	&& python -c 'import sys; open("context/context-src.md","wb").write(open("context/context-src.txt","rb").read().replace(b"\0",b""))' \
	&& rm ./context/context-src.txt

.PHONY: context.settings
context.settings:
	repo2txt -r . -o ./context/context-settings.txt \
	--exclude-dir context src notebooks \
	--ignore-types .md \
	--ignore-files LICENSE README.md \
	&& python -c 'import sys; open("context/context-settings.md","wb").write(open("context/context-settings.txt","rb").read().replace(b"\0",b""))' \
	&& rm ./context/context-settings.txt

.PHONY: context.clean
context.clean:
	rm ./context/context-*


#### Development ####
.PHONY: jupyter
jupyter: 
	@jupyter lab --autoreload

# .PHONY: flask.config
# flask.config:
# 	. ~/.bash_custom_functions;set_environment ~/flask.env

.PHONY: flask.debug
flask.debug:
	@python -m flask --debug run

