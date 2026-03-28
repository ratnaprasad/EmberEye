.PHONY: suite-1x suite-1x-installer

suite-1x:
	python scripts/build_suite_1x.py --field-mode onedir --clean

suite-1x-installer:
	python scripts/build_suite_1x.py --field-mode onedir --field-installer --clean
