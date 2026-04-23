# Copyright (c)

.PHONY: clean clean-dist clean-build build docs help test tests style check checks sct

# ==================================================================================================
# Variables
# ==================================================================================================

SRC_FOLDERS:=daemon_hhc_n818op tests
PACKAGE_NAME=daemon_hhc_n818op
TEST:=tests

ifeq ($(OS),Windows_NT)
	PYTHON?=python
else
	PYTHON?=python3
endif
PIPX?=pipx
ifeq ($(OS),Windows_NT)
	UV_LOCAL := $(shell cygpath -u "$$USERPROFILE" 2>/dev/null)/.local/bin/uv.exe
	ifneq ($(wildcard $(UV_LOCAL)),)
		UV?=$(UV_LOCAL)
	else
		UV?=uv
	endif
else
	UV?=uv
endif
PYTEST_HTML_REPORT_ARGS?=--html=report-unit-tests.html --self-contained-html

PYTHON_VERSION:=$(shell cat .python-version | grep -v '^#')
UV_VERSION := $(shell cat .uv-version | grep -v '^#')

MIN_COVERAGE_PERCENT:= 0
SHELL:=/bin/bash
DONT_FORGET_NIX:="if you want to use nix, don't forget to run nix develop (or use direnv)"

CI?=false  # Gitlab-CI sets this to true

UNAME_S := $(shell uname -s)

# ==================================================================================================
# General Functions
# ==================================================================================================

ifeq ($(UNAME_S),Darwin)
# Check if sed is GNU sed; if so, skip setting OSX_SED_I
ifeq ($(shell sed --version 2>&1 | grep -q 'GNU' && echo true),true)
OSX_SED_I=
else
OSX_SED_I=''
endif
OPEN_CMD="open"
else
OSX_SED_I=
OPEN_CMD="xdg-open"
endif

define BROWSER_PYSCRIPT
import os, webbrowser, sys
from urllib.request import pathname2url
webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT
BROWSER := $(PYTHON) -c "$$BROWSER_PYSCRIPT"

define PRINT_HELP_PYSCRIPT
import re, sys
for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-30s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT


# ==================================================================================================
# help target
# ==================================================================================================

help:  ## This help message
	@$(PYTHON) -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)


# ==================================================================================================
# do-it-all targets
# ==================================================================================================

all: dev style checks dists test  ## Build everything

dev: ensure-uv check-versions uv-sync        ## Setup dev environment with forced tools versions

dev-no-check: ensure-uv uv-sync              ## Setup dev environment without forced tools versions

initial-dev: dev-no-check style  ## Initial dev environment

# ==================================================================================================
# Install targets
# ==================================================================================================

ensure-uv:
	@if ! [ "$$IN_NIX_SHELL" ]; then \
		install_uv=false; \
		if ! command -v $(UV) &> /dev/null; then install_uv=true; fi; \
		if ! $(UV) --version | grep -q $(UV_VERSION); then install_uv=true; fi; \
		if $$install_uv; then \
			$(PIPX) install --force "uv==$(UV_VERSION)"; \
		fi; \
	fi

# use on nix develop shell (@uv, python versions managed by nix)
check-versions:
	@if [ "$$IN_NIX_SHELL" ]; then \
		echo "Versions provided by Nix: $(shell $(UV) run $(PYTHON) --version) and $(shell $(UV) --version)"; \
		echo "Versions expected by the tool: $(PYTHON_VERSION) and $(UV_VERSION)"; \
	else \
		if $(UV) --version | grep -q $(UV_VERSION); then \
			echo Right uv version: $(UV_VERSION); \
		else \
			echo "Bad uv version: current: $$($(UV) --version) expected: $(UV_VERSION)"; \
			exit 1; \
		fi; \
		if $(PYTHON) --version | grep -q $(PYTHON_VERSION); then \
			echo Right python version: $(PYTHON_VERSION) ;\
		else \
			echo "Bad python version:";\
			echo "    current on venv: $$($(UV) run $(PYTHON) --version)" ;\
			echo "    current on system: $$($(PYTHON) --version)" ;\
			echo "    expected: $(PYTHON_VERSION)" ;\
			exit 1; \
		fi; \
	fi


# If needed, you can add UV_GIT_LFS=1 to the command line to install git-lfs objects to
uv-sync:
	@echo "Install dependencies"
	$(UV) sync $(UV_SYNC_OPTS)
	@if [ "$$IN_NIX_SHELL" ]; then \
		echo "In NIX SHELL $$IN_NIX_SHELL": \
		patch_libs.sh; \
	fi

clean-venv:
	@rm -fr .venv

install-pre-commit:
	$(UV) run pip install pre-commit
	$(UV) run pre-commit install

uninstall-pre-commit:
	$(UV) run pre-commit uninstall

pre-commit:
	$(UV) run pre-commit run --all-files

version:
	sed -i $(OSX_SED_I) "s/^version = \".*\"/version = \"$(shell cat buildinfo/VERSION)\"/" pyproject.toml
	$(MAKE) uv-sync

show-all-dep:
	$(UV) tree --no-group dev


# ==================================================================================================
# Code formatting targets
# ==================================================================================================

style: isort black  ## Format code

isort:
	$(UV) run isort $(SRC_FOLDERS)

black:
	$(UV) run black $(SRC_FOLDERS)

format: style


# ==================================================================================================
# Static checks targets
# ==================================================================================================

checks: isort-check black-check flake8 pylint mypy bandit ruff ## Static analysis

ruff:
	$(UV) run ruff check $(SRC_FOLDERS)

isort-check:
	$(UV) run isort -c $(SRC_FOLDERS)

black-check:
	$(UV) run black --check $(SRC_FOLDERS)

flake8:
	$(UV) run flake8 $(PACKAGE_NAME)

pylint:
	$(UV) run pylint --rcfile=.pylint.toml --output-format=colorized $(SRC_FOLDERS)

mypy:
	# Static type checker only enabled on methods that uses Python Type Annotations
	$(UV) run mypy $(SRC_FOLDERS)

bandit:
	$(UV) run bandit -c .bandit.yml -r $(SRC_FOLDERS)

pydocstyle:
	$(UV) run pydocstyle $(SRC_FOLDERS)

clean-mypy:
	rm -rf .mypy_cache || true

sc: style check

sct: style check test

# ==================================================================================================
# Test targets
# ==================================================================================================

tests:  ## Execute unit tests
	$(UV) run pytest -v \
		-m "not integration_tests" \
		$(PYTEST_HTML_REPORT_ARGS) \
		--junitxml=report-unit-tests.xml \
		-o junit_suite_name=unit_tests \
		$(SRC_FOLDERS)

tests-v:  ## Execute verbose unit tests
	$(UV) run pytest -vvs \
		-m "not integration_tests" \
		--log-cli-level=DEBUG \
		$(PYTEST_HTML_REPORT_ARGS) \
		--junitxml=report-unit-tests.xml \
		-o junit_suite_name=unit_tests \
		$(SRC_FOLDERS)

tests-coverage:
	$(UV) run pytest -v \
		-m "not integration_tests" \
		--cov $(PACKAGE_NAME) \
		--cov-config pyproject.toml \
		--cov-report xml:report-coverage.xml \
		--cov-report html:coverage_html \
		--cov-report term \
		--cov-fail-under=$(MIN_COVERAGE_PERCENT) \
		--junitxml=report-unit-tests.xml \
		-o junit_suite_name=unit_tests \
		$(SRC_FOLDERS)

tests-integration:
	$(UV) run pytest -v \
		-m "integration_tests" \
		--junitxml=report-integration-tests.xml \
		-o junit_suite_name=integration_tests \
		$(SRC_FOLDERS)

watch-unittests:  ## Watch unit test (restrict with: make watch-unittests TEST=myunittesttoway)
	$(UV) run ptw $(TEST) \
		--onfail "notify-send -t 1000 -i face-angry \"Unit tests failed!\"" \
		--onpass "notify-send -t 1000 -i face-wink \"Unit tests succeed!\"" \
		-- -vv -m "not integration_tests"



# ==================================================================================================
# Distribution packages targets
# ==================================================================================================

export-requirements:
	$(UV) export --no-hashes -n -o dist/requirements.txt \
		--no-group dev
	sed -i $(OSX_SED_I) '/^-e ./$/d' dist/requirements.txt
	@echo "Generated dist/requirements.txt"

sbom: export-requirements
	rm -f dist/sbom*
	mkdir -p dist/
	( $(UV) run cyclonedx-py requirements dist/requirements.txt --output-format json --output-file dist/sbom.json )
	( $(UV) run cyclonedx-py requirements dist/requirements.txt --output-format xml --output-file dist/sbom.xml )


build: sbom  ## Build all distribution packages

	# Solution found here: https://github.com/astral-sh/uv/issues/8729#issuecomment-2654619679
	# Backup lock and pyproject files, the pyproject.toml file will be modified by uv during this process
	cp pyproject.toml pyproject.toml.bak
	cp uv.lock uv.lock.bak

	# Create a requirements files with all dependencies and their versions
	$(UV) export --locked --no-dev --no-hashes --no-emit-workspace \
		--output-file dist/pinned-requirements.txt

	# Add the pinned requirements to the pyproject.toml file with pinned versions, this modifies the pyproject.toml
	# file, adding a set of optional dependecies called "pinned" including transitively all the run-time dependencies
	# of the project. Installing the "wheel" package with "pinned" extra permits to install dependencies with fixed
	# versions.
	$(UV) add --optional pinned -r dist/pinned-requirements.txt

	# Build packages
	$(UV) build

	# List actual content of the wheel
	unzip -l dist/*.whl

	# Restore original lock and pyproject files
	mv pyproject.toml.bak pyproject.toml
	mv uv.lock.bak uv.lock

wheel: build
dists: build
sdist: build

clean-dist:
	rm -rfv build dist/


# ==================================================================================================
# Misc targets
# ==================================================================================================

shell:
	source .venv/bin/activate

ctags:
	find -name '*.py' -exec ctags -a {} \;

update: uv-update  ## Update dependencies
update-dt: uv-update-dt

uv-update:
	$(MAKE) uv-sync UV_SYNC_OPTS="--upgrade"

uv-update-dt:
	$(MAKE) uv-sync-dt UV_SYNC_OPTS="--upgrade"

update-recreate: update style check test

githook: style


# ==================================================================================================
# Publish targets
# ==================================================================================================

push: githook
	git push origin --all
	git push origin --tags


# ==================================================================================================
# Clean targets
# ==================================================================================================

clean: clean-dist clean-docs clean-mypy clean-venv  ## Clean environment
	find . -name '__pycache__'  -exec rm -rf {} \; || true
	find . -name '.cache'  -exec rm -rf {} \; || true
	find . -name '*.egg-info'  -exec rm -rf {} \; || true
	find . -name "*.pyc" -exec rm -f {} \; || true
	rm -rf .pytest_cache || true
	rm -rf coverage_html || true


# ==================================================================================================
# Documentation targets
# ==================================================================================================

DOCS_EXCLUSION=$(foreach m, $(SRC_FOLDERS), $m/tests)

docs: all-docs  ## Build online documentation
all-docs: \
		clean-docs \
		docs-generate-changelog \
		docs-run-sphinx

apidoc:  ## Generate API doc skeletton with sphinx-apidoc
	$(UV) run sphinx-apidoc \
		--force \
		--separate \
		--module-first \
		--doc-project "API Reference" \
		--separate \
		-d 6 \
		--templatedir docs/apidoctpl \
		-o docs/source/reference/editme \
		$(SRC_FOLDERS) \
			$(DOCS_EXCLUSION)
	echo "Now manually edit the content of docs/source/reference/editme into docs/source/reference."
	echo "You would want to remove docs/source/reference/apidoc before commiting"

docs-generate-changelog:
	$(UV) run cz changelog \
		--file-name docs/source/changelog.sections.md \
		--unreleased-version UNRELEASED_VERSION
	echo "# Changelog" > docs/source/changelog.md
	echo "" >> docs/source/changelog.md
	cat docs/source/changelog.sections.md >> docs/source/changelog.md
	rm -f docs/source/changelog.sections.md

docs-run-sphinx:
	$(UV) run make -C docs/ html

clean-docs:
	rm -rf docs/_build docs/source/reference/editme/*.rst

docs-open:
	$(OPEN_CMD) docs/_build/html/index.html

docs-autobuild:  ## Start live-reload webserver on doc generation
	$(UV) run sphinx-autobuild docs/source docs/_build/html



# ==================================================================================================
# Aliases to gracefully handle typos on poor dev's terminal
# ==================================================================================================

check: checks
coverage: tests-coverage
devel: dev
develop: dev
dist: dists
doc: docs
integration-tests: tests-integration
it: tests-integration
styles: style
test-coverage: tests-coverage
test-integration: tests-integration
test-unit: tests
test: tests
unit-tests: tests
unittest: tests
unittests: tests
ut: tests
wheels: wheel
