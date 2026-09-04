.PHONY: help install sweep table gaps serve export web test detect grow

VENV = .venv/bin

help:
	@echo "Internship Radar — common tasks"
	@echo "  make install    create venv + install backend and web deps"
	@echo "  make sweep      run a tier-0 collection sweep"
	@echo "  make table      print the current open table"
	@echo "  make gaps       print the cross-posting gap rollup"
	@echo "  make serve      run the local read/write API (:8787)"
	@echo "  make export     dump web/public/data.json for the static UI"
	@echo "  make web        run the Next.js dev server (:3000)"
	@echo "  make test       run the Python test suite"

install:
	python3 -m venv .venv
	$(VENV)/pip install -q --upgrade pip
	$(VENV)/pip install -q -r requirements.txt pytest
	cd web && npm install

sweep:
	$(VENV)/python -m radar.run sweep --tier 0 --lists

table:
	$(VENV)/python -m radar.run table

gaps:
	$(VENV)/python -m radar.run gaps

serve:
	$(VENV)/python -m radar.run serve

export:
	$(VENV)/python -m radar.run export

web:
	cd web && npm run dev

test:
	$(VENV)/python -m pytest -q

detect:
	$(VENV)/python -m radar.run detect "$(NAME)" "$(HOME_URL)"

grow:
	$(VENV)/python -m radar.run grow
