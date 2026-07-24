PYTHON ?= python3
PYTHONPATH := src

.PHONY: demo test lint reproduce-wm reproduce-seeded-regression

demo:
	@set +e; PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m assay demo; status=$$?; test $$status -eq 1
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m assay demo --gate-in-ci > docs/demo/github-actions-example.yml
	@echo "ASSAY demo completed; the expected BLOCKED gate returned exit 1."

test:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests -v

lint:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q src tests
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m assay check

reproduce-wm:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m assay reproduce-wm

reproduce-seeded-regression:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m assay reproduce-seeded-regression

