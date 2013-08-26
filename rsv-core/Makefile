prefix := /usr
localstatedir := /var
sysconfdir := /etc
bindir := $(prefix)/bin
initrddir := $(sysconfdir)/rc.d/init.d
libexecdir := $(prefix)/libexec
mandir := $(prefix)/share/man
python_sitelib := $(shell python -c 'from distutils.sysconfig import get_python_lib; print get_python_lib()')



_default:
	@echo "No default. Try 'make install'"

install:
	# Create the logging directories
	install -d $(DESTDIR)$(localstatedir)/log/rsv
	# Create the temp file area
	install -d $(DESTDIR)$(localstatedir)/tmp/rsv
	# Install the executable
	install -d $(DESTDIR)$(bindir)
	install -m 0755 bin/rsv-control $(DESTDIR)$(bindir)/
	install -d $(DESTDIR)$(libexecdir)/rsv
	cp -rf libexec/misc $(DESTDIR)$(libexecdir)/rsv/
	# Install the init script
	install -d $(DESTDIR)$(initrddir)
	install -m 0755 init/rsv.init $(DESTDIR)$(initrddir)/rsv
	# Install the configuration
	install -d $(DESTDIR)$(sysconfdir)/rsv
	install -m 0644 etc/consumers.conf $(DESTDIR)$(sysconfdir)/rsv/
	install -m 0644 etc/rsv.conf $(DESTDIR)$(sysconfdir)/rsv/
	# Install python libraries
	install -d $(DESTDIR)$(python_sitelib)
	cp -rf lib/python/rsv $(DESTDIR)$(python_sitelib)/
	# Install the man page
	install -d $(DESTDIR)$(mandir)/man1
	install -m 0644 share/man/man1/rsv-control.1 $(DESTDIR)$(mandir)/man1/


.PHONY: _default install

