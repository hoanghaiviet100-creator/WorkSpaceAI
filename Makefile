.PHONY: test verify

test:
	python -m unittest tests/test_feature3_email_backend.py

verify:
	python verify.py

