# Non-Nix installer for the Nelko BLE CUPS driver.
#
# Targets:
#   make fetch       Download the vendor .deb from Nelko's CDN
#   make install     Install backend, filter, PPDs system-wide (needs sudo)
#   make uninstall   Remove the installed files
#   make help

DEB_URL  := https://cdn.shopify.com/s/files/1/0657/6626/0980/files/NELKO_PL70e-BT_Linux_v3.0.1.407.deb
DEB_SHA  := 2229d68a009a03d5955937932fac7e017432bc118251b38abb5b218d88da6d46
DEB      := drivers/nelko_pl70e_linux.deb
EXTRACT  := drivers/extracted

PREFIX        ?= /usr
CUPS_LIBDIR   ?= $(PREFIX)/lib/cups
CUPS_DATADIR  ?= $(PREFIX)/share/cups
BINDIR        ?= $(PREFIX)/local/bin

FILTER_DIR  := $(CUPS_LIBDIR)/filter/Nelko/Filter
BACKEND_DIR := $(CUPS_LIBDIR)/backend
PPD_DIR     := $(CUPS_DATADIR)/model/Nelko

.PHONY: help fetch extract install uninstall check-deps

help:
	@echo "Nelko PL70e-BT CUPS driver — non-Nix installer"
	@echo
	@echo "  make fetch       download the vendor .deb"
	@echo "  make install     install everything (needs sudo)"
	@echo "  make uninstall   remove installed files"
	@echo
	@echo "After install: run 'nelko-setup' to scan and register a queue."

check-deps:
	@command -v curl >/dev/null  || { echo "missing: curl"; exit 1; }
	@command -v ar >/dev/null    || { echo "missing: ar (binutils)"; exit 1; }
	@command -v tar >/dev/null   || { echo "missing: tar"; exit 1; }
	@command -v lpadmin >/dev/null || { echo "missing: lpadmin (install CUPS)"; exit 1; }
	@python3 -c "import bleak" 2>/dev/null || { \
	    echo "missing: python3 'bleak' module — pip install bleak"; exit 1; }

$(DEB):
	@mkdir -p drivers
	curl -fL --output $@ "$(DEB_URL)"
	@echo "$(DEB_SHA)  $@" | sha256sum --check --status \
	    || { echo "checksum mismatch"; rm -f $@; exit 1; }

fetch: $(DEB)

extract: $(DEB)
	@rm -rf $(EXTRACT)
	@mkdir -p $(EXTRACT)
	cd $(EXTRACT) && ar x ../../$(DEB) && tar -xJf data.tar.xz

install: check-deps extract
	# CUPS filter and PPDs from the vendor deb.
	install -d $(DESTDIR)$(FILTER_DIR)
	install -m 755 $(EXTRACT)/usr/lib/cups/filter/Nelko/Filter/rastertolabel \
	    $(DESTDIR)$(FILTER_DIR)/rastertolabel
	install -d $(DESTDIR)$(PPD_DIR)
	install -m 644 $(EXTRACT)/usr/share/cups/model/Nelko/PL70e-BT.ppd \
	    $(DESTDIR)$(PPD_DIR)/PL70e-BT.ppd
	install -m 644 $(EXTRACT)/usr/share/cups/model/Nelko/PL420.ppd \
	    $(DESTDIR)$(PPD_DIR)/PL420.ppd
	# Our BLE backend, named for the URI scheme it handles.
	install -d $(DESTDIR)$(BACKEND_DIR)
	install -m 755 cups_backend/pl70e_ble.py $(DESTDIR)$(BACKEND_DIR)/ble
	# Setup CLI on PATH.
	install -d $(DESTDIR)$(BINDIR)
	install -m 755 bin/nelko-setup $(DESTDIR)$(BINDIR)/nelko-setup
	@echo
	@echo "Installed. Next steps:"
	@echo "  1) systemctl restart cups"
	@echo "  2) Allow the 'lp' user to talk to BlueZ — see README polkit section."
	@echo "  3) nelko-setup           # scan and register a printer"
	@echo "  4) lp -d PL70e file.pdf"

uninstall:
	rm -f $(DESTDIR)$(BACKEND_DIR)/ble
	rm -f $(DESTDIR)$(FILTER_DIR)/rastertolabel
	rm -f $(DESTDIR)$(PPD_DIR)/PL70e-BT.ppd
	rm -f $(DESTDIR)$(PPD_DIR)/PL420.ppd
	rm -f $(DESTDIR)$(BINDIR)/nelko-setup
	rmdir $(DESTDIR)$(FILTER_DIR) 2>/dev/null || true
	rmdir $(DESTDIR)$(PPD_DIR) 2>/dev/null || true
