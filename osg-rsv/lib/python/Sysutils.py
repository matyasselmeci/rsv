#!/usr/bin/env python

# Global libraries
import os
import sys
import popen2
import signal

class TimeoutError(Exception):
    """ This defines an Exception that we can use if our system call times out """
    pass
            

def alarm_handler(signum, frame):
    raise TimeoutError("System call timed out")


class Sysutils:
    rsv = None

    def __init__(self, rsv):
        self.rsv = rsv


    def system(self, command, timeout):
        """ Run a system command with a timeout specified (in seconds).
        Returns:
          1) exit code
          2) STDOUT/STDERR (combined)

        I think this could be better done using the socket module, but we need
        Python 2.7 for that.
        """

        try:
            signal.signal(signal.SIGALRM, alarm_handler)
            signal.alarm(timeout)
            child = popen2.Popen3(command, capturestderr=1)
            ret = child.wait()
            signal.alarm(0)
        except TimeoutError:
            self.rsv.log("ERROR", "Command timed out (timeout=%s): %s" % (timeout, command))
            os.kill(child.pid, signal.SIGKILL)
            raise TimeoutError("Command timed out (timeout=%s)" % timeout)

        out = child.fromchild.read()
        err = child.childerr.read()
        return (ret, out, err)


    def switch_user(self, user, desired_uid, desired_gid):
        """ If the current process is not set as the desired UID, set it now.  If we are not
        root then bail out """

        this_process_uid = os.getuid()
        if this_process_uid == desired_uid:
            self.rsv.log("INFO", "Invoked as the RSV user (%s)" % user, 4)
        else:
            if this_process_uid == 0:
                self.rsv.log("INFO", "Invoked as root.  Switching to '%s' user (uid: %s - gid: %s)" %
                             (user, desired_uid, desired_gid), 4)

                try:
                    os.setgid(desired_gid)
                    os.setuid(desired_uid)
                    os.environ["USER"]     = user
                    os.environ["USERNAME"] = user
                    os.environ["LOGNAME"]  = user
                except OSError:
                    self.rsv.log("ERROR", "Unable to switch to '%s' user (uid: %s - gid: %s)" %
                                 (user, desired_uid, desired_gid), 4)

            else:
                # TODO - allow any user to run, but don't produce consumer records
                self.rsv.log("ERROR", "You can only run metrics as root or the RSV user (%s)." % user, 0)
                sys.exit(1)
