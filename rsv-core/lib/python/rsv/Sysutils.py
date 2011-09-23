#!/usr/bin/python

# Global libraries
import os
import re
import sys
import time
import fcntl
import select
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

            # Set the child's STDERR to non blocking if possible.
            # This prevents the child from hanging due to it blocking on stderr 
            # or stdout 
            err_fd = child.childerr.fileno()
            flags = fcntl.fcntl(err_fd, fcntl.F_GETFL, 0) 
            flags |= os.O_NONBLOCK
            fcntl.fcntl(err_fd, fcntl.F_SETFL, flags)

            # do the same for stdout            
            out_fd = child.fromchild.fileno()
            flags = fcntl.fcntl(out_fd, fcntl.F_GETFL, 0) 
            flags |= os.O_NONBLOCK
            fcntl.fcntl(out_fd, fcntl.F_SETFL, flags)

            # We are going to loop and read from STDOUT and STDERR.  When they are
            # hot but return 0 bytes we know that they have been closed by our child.
            # Loop until both of them have been closed or we hit the timeout.
            fds = [out_fd, err_fd]
            while True:
                if not fds:
                    # When we have no more fds to read from we are done
                    break
                
                interval = (start + timeout) - time.time()
                ready_fds = select.select(fds, [], [], interval)
                if ready_fds[0] != []:
                    new_fds = []  # new_fds keeps track of fds that are not closed.
                    for fd in fds:
                        # Either there is out/err to read or else we will get 0 bytes
                        # and that indicates that the child closed that pipe.
                        if fd not in ready_fds[0]:
                            new_fds.append(fd)
                        else:
                            new_data = os.read(fd, 2048)
                            if len(new_data) == 0:
                                # This indicates that the fd is closed by the child.
                                # We will not add it to new_fds so that we stop
                                # select()ing on it.
                                pass
                            else:
                                new_fds.append(fd)
                                if fd == out_fd:
                                    out += new_data
                                elif fd == err_fd:
                                    err += new_data

                    fds = new_fds
                                  
                if ((time.time() - start) > timeout):
                    # probe has been running for more than timeout seconds,
                    # raise an exception to time out the execution
                    raise TimeoutError

            # So now that both STDOUT and STDERR have been closed we need to also wait
            # for the process to finish so that we can reap it and avoid a zombie.
            # This is a rare case that probably indicates that the child forcibly closed
            # STDOUT and STDERR and intends to continue running.
            while True:
                if child.poll() != -1:
                    break

                if (time.time() - start) > timeout:
                    raise TimeoutError

                time.sleep(1)

            # When we are finally done we can grab the return code from the child.  This
            # should not block because we will only get here if child.poll() told us that
            # the child process is finished.
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


    def watch_log(self, log_path, keywords, timeout=300, sleep_interval=10):
        """ Watch the specified log for the keywords.  Return the keyword that matches. """

        self.rsv.log("DEBUG", "Watching log '%s' for keywords [%s].  Timeout is %ss" %
                     (log_path, ', '.join(keywords), timeout))

        start_time = int(time.time())
        mtime = 0

        while 1:
            if int(time.time()) - start_time >= timeout:
                raise TimeoutError("Timeout while watching log (%ss)" % timeout)
            
            new_mtime = os.stat(log_path).st_mtime
            if new_mtime != mtime:
                mtime = new_mtime
                contents = self.slurp(log_path)

                for keyword in keywords:
                    if re.search(keyword, contents):
                        return (keyword, contents)

            time.sleep(sleep_interval)
        
        return (None, None)
    

    def slurp(self, file, must_exist=0):
        """ Given a path, read the contents of that file """
        self.rsv.log("DEBUG", "Slurping file '%s'" % file)
        
        try:
            f = open(file, 'r')
            contents = f.read()
            f.close()
        except IOError, err:
            print "Error: %s" % err
            if must_exist:
                self.rsv.log("ERROR", "Could not read file: %s" % err, indent=4)
                raise
            else:
                self.rsv.log("DEBUG", "Could not read file: %s" % err, indent=4)
                contents = ""
            
        return contents
