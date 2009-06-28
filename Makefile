# $Id: Makefile,v 1.15 2002/06/14 00:11:52 ashtong Exp $

DESTDIR = 
BIN = $(DESTDIR)/usr/local/sbin
ETC = $(DESTDIR)/usr/local/etc
INSTALL = /usr/bin/install -c

# variables for the tardist target
VERS = 0.2.1
SRC = AUTHORS COPYING INSTALL Makefile MANIFEST README \
      landiallerd.conf landiallerd.py

install:
	@echo "### Installing ..."
	$(INSTALL) -d $(BIN)
	$(INSTALL) -m755 ./landiallerd.py $(BIN)
	$(INSTALL) -d $(ETC)
	$(INSTALL) -b -m644 ./landiallerd.conf $(ETC)

tardist:
	@echo "### Building landiallerd-$(VERS).tar.gz"
	@ls $(SRC) | sed s:^:landiallerd-$(VERS)/: >MANIFEST
	@(cd ..; ln -s server landiallerd-$(VERS))
	(cd ..; tar -czvf landiallerd-$(VERS).tar.gz `cat server/MANIFEST`)
	@(mkdir -p dist)
	@(mv ../landiallerd-$(VERS).tar.gz dist)
	@(cd ..; rm landiallerd-$(VERS))

uninstall:
	@echo "### Uninstalling ..."
	rm -f $(BIN)/landiallerd.py
	rm -f $(ETC)/landiallerd.conf
