#!/usr/bin/env python

# A wrapper script that run-rsv-metric redirects to.  It will drive the
# rest of the process.

import rsv

rsv.initialize()

rsv.ping_test()

rsv.execute_job()
