# Install, test and clean the Scaletainer FreeCAD add-on.
#
#   make install                    copy into the Flatpak Mod directory
#   make link                       symlink instead (for development)
#   make install DESTDIR=~/.local/share/FreeCAD/Mod   a non-Flatpak install
#   make uninstall
#   make test                       all tests, needs freecadcmd
#   make test-params                parameter tests only (plain Python)
#   make test-config                configuration file tests only (plain Python)

SRC     := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
NAME    := Scaletainer
FREECAD ?= flatpak run --command=freecadcmd org.freecad.FreeCAD

# Default target: the Flatpak user Mod directory.
DESTDIR ?= $(HOME)/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod

# The add-on lives at the repository root, so only these files are installed;
# the git history and repository metadata stay out of the Mod directory.
PAYLOAD := Init.py InitGui.py package.json README.md DEVELOPER.md LICENSE.md scaletainer resources tests

.PHONY: install uninstall link test test-params test-config lint

install:
	@mkdir -p "$(DESTDIR)"
	rm -rf "$(DESTDIR)/$(NAME)"
	@mkdir -p "$(DESTDIR)/$(NAME)"
	@for item in $(PAYLOAD); do \
	    cp -r "$(SRC)/$$item" "$(DESTDIR)/$(NAME)/$$item"; \
	done
	@find "$(DESTDIR)/$(NAME)" -name '__pycache__' -type d -prune -exec rm -rf {} +
	@echo "installed $(SRC) -> $(DESTDIR)/$(NAME)"
	@echo "restart FreeCAD to pick up the workbench"

link:
	@mkdir -p "$(DESTDIR)"
	rm -rf "$(DESTDIR)/$(NAME)"
	ln -s "$(SRC)" "$(DESTDIR)/$(NAME)"
	@echo "linked $(SRC) -> $(DESTDIR)/$(NAME)"

uninstall:
	rm -rf "$(DESTDIR)/$(NAME)"
	@echo "removed $(DESTDIR)/$(NAME)"

test-params:
	@cd "$(SRC)" && python3 -m unittest discover -s tests -p 'test_params.py' -v

test-config:
	@cd "$(SRC)" && python3 -m unittest discover -s tests -p 'test_config.py' -v

test:
	@cd "$(SRC)" && QT_QPA_PLATFORM=offscreen $(FREECAD) tests/run_tests.py

lint:
	@cd "$(SRC)" && python3 -c "import ast,glob,sys; \
	[ast.parse(open(f).read(), f) for f in glob.glob('**/*.py', recursive=True)]; \
	print('all files parse')"
