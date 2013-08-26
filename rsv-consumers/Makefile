prefix := /usr
localstatedir := /var
sysconfdir := /etc
libexecdir := $(prefix)/libexec
datadir := $(prefix)/share



_default:
	@echo "No default. Try 'make install'"

install:
	# Create the web areas
	install -d $(DESTDIR)$(datadir)/rsv
	install -d $(DESTDIR)$(datadir)/rsv/www
	install -m 0644 httpd/rsv.index.html $(DESTDIR)$(datadir)/rsv/www/index.html
	# Install the Apache configuration and index files
	install -d $(DESTDIR)$(sysconfdir)/httpd/conf.d
	install -d $(DESTDIR)$(datadir)/osg/www.d/
	install -m 0644 httpd/rsv.conf $(DESTDIR)$(sysconfdir)/httpd/conf.d/
	install -m 0644 httpd/rsv.site $(DESTDIR)$(datadir)/osg/www.d/
	# Install executables
	install -d $(DESTDIR)$(libexecdir)/rsv
	cp -rf libexec/consumers $(DESTDIR)$(libexecdir)/rsv/
	# Install configuration
	install -d $(DESTDIR)$(sysconfdir)/rsv/meta
	cp -rf etc/meta/consumers $(DESTDIR)$(sysconfdir)/rsv/meta/
	cp -rf etc/consumers $(DESTDIR)$(sysconfdir)/rsv/
	cp -f etc/rsv-nagios.conf $(DESTDIR)$(sysconfdir)/rsv/
	# Create the log dir
	install -d $(DESTDIR)$(localstatedir)/log/rsv/consumers
	# Put log rotation in place
	install -d $(DESTDIR)$(sysconfdir)/logrotate.d
	install -m 0644 logrotate/rsv-consumers.logrotate $(DESTDIR)$(sysconfdir)/logrotate.d/rsv-consumers


.PHONY: _default install

