#!/usr/bin/python

# Global libraries
import os
import re
import sys
import time
#unused import fcntl
#unused import select
import signal
import subprocess

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
        """

        p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        signal.signal(signal.SIGALRM, alarm_handler)
        signal.alarm(timeout)
        try:
            (stdout, stderr) = p.communicate()
            signal.alarm(0)
        except TimeoutError:
            # p.kill() is new in Python 2.6 and we support Python 2.4 so we need to have a fallback
            if hasattr(p, "kill"):
                p.kill()
            else:
                os.kill(p.pid, signal.SIGKILL)
                
            self.rsv.log("ERROR", "Command timed out (timeout=%s): %s" % (timeout, command))
            raise TimeoutError("Command timed out (timeout=%s)" % timeout)

        self.rsv.log("INFO", "Exit code of job: %s" % p.returncode)
        return p.returncode, stdout, stderr


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
                        return keyword, contents

            time.sleep(sleep_interval)
        
        return None, None
    

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


    def which(self, program):
        """ Examine the path for supplied binary.  Return path to binary or None if not found """
        #def is_exe(fpath):
        #    return os.path.isfile(fpath) and os.access(fpath, os.X_OK)
        self.rsv.log("DEBUG", "Looking for binary named '%s'" % program)
        
        fpath, fname = os.path.split(program)
        if fpath:
            if os.path.isfile(program) and os.access(program, os.X_OK):
                self.rsv.log("DEBUG", "Fully qualified program %s is a valid executable." % program)
                return program
        else:
            for path in os.environ["PATH"].split(os.pathsep):
                exe_file = os.path.join(path, program)
                if os.path.isfile(exe_file) and os.access(exe_file, os.X_OK):
                    self.rsv.log("DEBUG", "Found program '%s' at '%s'" % (program, exe_file))
                    return exe_file

        self.rsv.log("DEBUG", "Did not find program '%s'" % program)
        return None
