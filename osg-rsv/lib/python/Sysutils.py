#!/usr/bin/env python

# Global libraries
import os
import fcntl
import select
import time
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
          2) STDOUT
          3) STDERR

        I think this could possibly be better done using the subprocess module, but
        that requires Python 2.4 and we need to support Python 2.3+.
        """

        out = ""
        err = ""
        ret = -1
        # although using the signal module makes life 
        # easier, it looks like it doesn't play nicely with popen3 so
        # we need to handle the timing manually instead of the using
        # SIGALRM
        try:
            start = time.time()
            child = popen2.Popen3(command, capturestderr=1)
            # set child's stderr to non blocking if possible
            # prevents the child from hanging due to it blocking on stderr 
            # or stdout 
            error_fd = child.childerr.fileno()
            flags = fcntl.fcntl(error_fd, fcntl.F_GETFL, 0) 
            flags |= os.O_NONBLOCK
            fcntl.fcntl(error_fd, fcntl.F_SETFL, flags)
            # do the same for stdout            
            out_fd = child.fromchild.fileno()
            flags = fcntl.fcntl(out_fd, fcntl.F_GETFL, 0) 
            flags |= os.O_NONBLOCK
            fcntl.fcntl(out_fd, fcntl.F_SETFL, flags)
            # use select to get output from child
            while True:
               interval = (start + timeout) - time.time()
               ready_fds = select.select([error_fd, out_fd], [], [], interval)
               if ready_fds[0] != []:
                   # there's output that needs to be read
                   if error_fd in ready_fds[0]:
                       err += os.read(error_fd, 2048)
                   if out_fd in ready_fds[0]:
                       out += os.read(out_fd, 2048)

               if child.poll() != -1:
                  # child is done, exit. 
                  break
               
               if ((time.time() - start) > timeout):
                   # probe has been running for more than timeout seconds,
                   # raise an exception to time out the execution
                   raise TimeoutError
            ret = child.wait()
        except IOError, ex: # from fcntl calls
            self.rsv.log("ERROR", "Error while changing to non-blocking output")
            os.kill(child.pid, signal.SIGKILL)
        except TimeoutError:
            self.rsv.log("ERROR", "Command timed out (timeout=%s): %s" % (timeout, command))
            os.kill(child.pid, signal.SIGKILL)
            raise TimeoutError("Command timed out (timeout=%s)" % timeout)

        self.rsv.log("INFO", "Exit code of job: %s" % ret)
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
