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



#### Build ####
VERSION=`grep version setup.cfg | awk '{print $$3}'`
TAGNAME=v$(VERSION)

.PHONY: publish.tag
publish.tag:
	@echo "---Tagging commit hash $(TAGNAME) "
	git tag -a $(TAGNAME) -m"Release $(TAGNAME)"
	git push origin $(TAGNAME)
	@echo "---Pushed tag as version=$(VERSION)"


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

