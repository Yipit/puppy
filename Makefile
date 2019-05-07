SHELL := /bin/bash

clean:
	@echo "Removing garbage..."
	@find . -name '*.pyc' -delete
	@find . -name '*.so' -delete
	@find . -name __pycache__ -delete
	@rm -rf .coverage *.egg-info *.log build dist MANIFEST yc

# Only releasing privately for now
release: clean
	@if [ -z $$CUSTOM_PIP_INDEX ]; then \
		echo "Need to set a CUSTOM_PIP_INDEX to release"; \
		exit 1; \
	fi
	@if [ -e "$$HOME/.pypirc" ]; then \
		echo "Uploading to '$(CUSTOM_PIP_INDEX)'"; \
		python setup.py register -r "$(CUSTOM_PIP_INDEX)"; \
		python setup.py sdist upload -r "$(CUSTOM_PIP_INDEX)"; \
	else \
		echo "You should create a file called '.pypirc' under your home dir.\n"; \
		echo "That's the right place to configure 'pypi' repos.\n"; \
		exit 1; \
	fi

setup: clean
	@echo "Installing dependencies..."; \
	pip install --quiet -r development.txt;
