#
#    Copyright 2008 Zdravko Bozakov and Michael Bredel
#
#    This file is part of SSHLauncher.
#
#    SSHLauncher is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 2 of the License, or
#    (at your option) any later version.
#
#    SSHLauncher is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Foobar.  If not, see <http://www.gnu.org/licenses/>.
#
try:
    import pxssh
    import pexpect
except ImportError:
    print "Could not find pexpect module. You can install it using:"
    print "    pip install pexpect"
    raise SystemError
import select
import threading
import time
import os

if float(pexpect.__version__) < 3.3:
    print 'The installed version of pexpect is not supported.'
    print 'Please install pexect>=3.3.'
    exit(3)

COLOR_TERM = False
if os.environ.get("TERM"):
    COLOR_TERM = True


LOOP_DELAY = .1
WAIT_NOTIFICATION_DELAY = 60  # seconds

DEBUG = False
# LSD-style debug output
DEBUG_LABEL = '\033[43;1;37mDEBUG\033[m'

def session_tag(id_str, ascii_fg=31, ascii_bg=47, bold=1):
    """Print section [id] in session_tag"""
    # TODO check if the terminal supports it
    # see also: http://pypi.python.org/pypi/colorama
    h = hash(id_str)
    ascii_fg = 30 + (h & 7)
    # ascii_bg = 40 + (-h & 7)
    bold = 1
    if COLOR_TERM:
        return "\033[%d;%d;%dm[%s]\033[0m" % (ascii_bg, bold, ascii_fg, id_str)
    else:
        return "[%s]" % id_str


def ansi_bold(msg):
    if COLOR_TERM:
        return "\033[1m%s\033[0m" % msg
    else:
        return msg


class ConfigError(Exception):
    def __init__(self):
        pass


class SSHControl (threading.Thread):
    """Starts a thread which establishes an SSH connection and executes a command.

    """
    ID_STR_LEN = 0
    # pxssh instance
    s = None
    # strore all ssh threads
    ssh_threads = []
    # kill all threads if this is set to True
    terminate_threads = False

    thread_lock = None
    ESCAPE = False
    SIMULATE = False

    # start a login (l) or interactive(i) bash shell when issuing remote command
    # TODO this should be an option
    SHELL = '/bin/bash -ls'
    # commands which should always executed before the command string
    SHELL_SETUP = 'unset HISTFILE; '
    # how long should we wait (in seconds) before assuming the ssh connection
    # cannot be established
    SSH_LOGIN_TIMEOUT = 15
    # how long should we wait (in seconds) before attempting to reestablish an
    # ssh connection
    SSH_LOGIN_REPEAT_TIMEOUT = 5
    # how long should we wait (in seconds) for an expect (after) string.
    # Consider increasing for very long experiments.
    PEXPECT_TIMEOUT = 86400     # 24 hours
    # how long should we wait (in seconds) for the prompt
    PROMPT_TIMEOUT = 86400      # 24 hours

    def __init__(self, id, hostname, port, username, passwd, command, after={},
                 sync=[], delay=0):
        """initialize class variables"""
        threading.Thread.__init__(self)
        
        self.afterList = {}
        self.syncList = []
        self.id = id
        SSHControl.ID_STR_LEN = max(len(session_tag(id)), SSHControl.ID_STR_LEN)

        self.connected = False
        self.registered_after = False
        self.registered_sync = False
        self.syncNotified = False
        self.config_ok = False
        self.ready = False

        self.hostname = hostname
        self.username = username
        self.passwd = passwd
        self.delay = delay
        self.command = command
        self.after = after
        self.sync = sync
        self.port = port

        self.lock = threading.Lock()
        self.lockSync = threading.Lock()

        self.daemon = True

    def run(self):
        """thread method"""
        self.name = self.id
        time.sleep(self.delay)
        self.ready = True

        # wait until all threads are alive
        while [t for t in SSHControl.ssh_threads if not t.ready]:
            time.sleep(LOOP_DELAY)

        # register own expect string on thread id specified by after
        if self.after:
            for t in SSHControl.ssh_threads:
                for key in self.after.keys():
                    if t.name == str(key):
                        t.register_after(self.id, self.after[key])
        self.registered_after = True

        # wait until all threads have registered
        while any([not t.registered_after for t in SSHControl.ssh_threads]):
            time.sleep(LOOP_DELAY)

        # register sync expect string on thread id specified by sync
        if self.sync:
            for t in SSHControl.ssh_threads:
                for key in self.sync:
                    if t.name == str(key):
                        t.register_sync(self.id)
        self.registered_sync = True

        # wait until all threads are synchonized
        while any([not t.registered_sync for t in SSHControl.ssh_threads]):
            time.sleep(LOOP_DELAY)

        # now check the configuration
        try:
            self._check_config()
        except ConfigError:
            self.ssh_abort()
            return
            
        # wait to see if all configurations are ok
        while any([not t.config_ok for t in SSHControl.ssh_threads]):
            time.sleep(LOOP_DELAY)

        # wait until all expect strings registered by current session have been
        # matched
        timer = time.time()
        while (self.after and not self.syncNotified):
            time.sleep(LOOP_DELAY)
            # periodically tell the user what's happening
            if time.time()-timer > WAIT_NOTIFICATION_DELAY:
                timer = time.time()
                self.info('...waiting for %s ' % ' and '.join(['"%s" from ' %v + session_tag(k) for k, v in self.after.iteritems()]))

        # then connect
        if not self.ssh_connect(self.hostname, self.port,
                                self.username, self.passwd):
            return # TODO

        # notify all other threads in sync-group
        for tid in self.syncList:
            for t in SSHControl.ssh_threads:
                if t.name == tid:
                    t.notifySync(self.id)

        # wait until all sync-group threads have been connected
        while self.sync:
            time.sleep(LOOP_DELAY)
        # keep execution order
        while (self.after):
            time.sleep(LOOP_DELAY)

        # if simulate only
        if SSHControl.SIMULATE:
            self.command = self.simCommand()

        # execute command string
        self.info("executing: \033[1;34m%s\033[m " % (self.command))
        # self.command = self.SHELL_SETUP + self.command
        # spawn a new bash session on remote host and pipe command string to it
        if SSHControl.ESCAPE:
            self.command = 'echo -e \'' + self.SHELL_SETUP + self.command + '\' | ' + self.SHELL
        else:
            self.command = 'echo \''    + self.SHELL_SETUP + self.command + '\' | ' + self.SHELL

        try:
            # send comand
            self.s.sendline(self.command)

            # start loop to match expect strings and notify other threads
            self.__expectWait()

            # wait for section command to finish (i.e. reach the prompt) and
            # disconnect
            if self.s.prompt(self.PROMPT_TIMEOUT):
                self.ssh_disconnect()
            else:
                self.error("did not reach the prompt! something went wrong")
                print self.s.before
                raise SystemError
                # if DEBUG : self.s.interact(local=locals())
        except (select.error, IOError, OSError):
            self.ssh_abort()
            return

    def register_after(self, id, afterCommand):
        """Register an expect string on this block"""
        # FIXME I don't think we really need locks here. appending to a list is
        # an atomic operation
        self.lock.acquire()
        try:
            self.afterList[afterCommand].append(id)
        except KeyError:
            self.afterList[afterCommand] = [id]
        finally:
            self.lock.release()
        self.debug('%s registered "%s"' % (session_tag(id), afterCommand))

    def _check_config(self):
        """Very rudimentary check for valid section configuration"""
        if self.terminate_threads: return False
        
        if self.after:
            # check for circular refences
            for remote_after in [t for t in SSHControl.ssh_threads if (t.name in self.after.keys())]:
                if (remote_after.after and (self.id in remote_after.after.keys())):
                    self.error("cirular reference %s <-> %s?" %
                               (session_tag(self.id),
                                session_tag(remote_after.id)))
                    raise ConfigError

            # check for invalid section ids in AFTER
            for a in self.after:
                if a not in [t.id for t in SSHControl.ssh_threads]:
                    self.error("'%s' is not a valid section id in AFTER" % a)
                    raise ConfigError

            # check for invalid section ids in SYNC
            if not (self.sync is None):
                for a in self.sync:
                    if a not in [t.id for t in SSHControl.ssh_threads]:
                        self.error("'%s' is not a valid section id in SYNC" % a)
                        self.sync.remove(a)

        self.info("configuration seems ok")
        self.config_ok = True
        return True

    def register_sync(self, id):
        """Register an expect string on this block"""
        self.lockSync.acquire()
        try:
            self.syncList.append(id)
        except KeyError:
            self.syncList = [id]
        finally:
            self.lockSync.release()
        self.debug("synchronized with %s" % session_tag(id))

    def __expectWait(self):
        """Wait until all expect strings matched and remove corresponding entries from
        the threads after: queues.

        """
        try:
            while self.afterList.keys():
                res = self.s.expect(self.afterList.keys(), self.PEXPECT_TIMEOUT)
                after = self.afterList.keys()[res]
                self.debug('"%s" matched...' % after)

                for tid in self.afterList[after]:
                    for t in SSHControl.ssh_threads:
                        if t.name == tid:
                            t.notifyAfter(self.id, after)

                self.lock.acquire()
                try:
                    del self.afterList[after]
                finally:
                    self.lock.release()

        except pexpect.EOF:
            self.info("EOF!")
        except pexpect.TIMEOUT, e:
            self.info("timed-out waiting for: %s" % (self.afterList.keys()))
            self.debug(str(e))

    def __str__(self):
        return session_tag(self.id)

    def info(self, msg, stdout=True):
        with SSHControl.thread_lock:
            id_label = session_tag(self.id).ljust(SSHControl.ID_STR_LEN)
            msg = "%s   %s" % (id_label, msg)
            if stdout:
                print msg
            return msg

    def debug(self, msg, stdout=True):
        if not DEBUG:
            return

        with SSHControl.thread_lock:
            id_label = session_tag(self.id).ljust(SSHControl.ID_STR_LEN)
            msg = "%s   %s   %s" % (id_label, msg, DEBUG_LABEL)
            if stdout:
                print msg

    def error(self, msg, stdout=True):
        with SSHControl.thread_lock:
            id_label = session_tag(self.id).ljust(SSHControl.ID_STR_LEN)
            msg = "%s   %s" % (id_label, '\033[1;31m'+msg+'\033[0m')
            if stdout:
                print msg
            return msg

    def notifyAfter(self, id, after):
        """Notify a thread that the expect string has been matched"""
        self.info("matched \"%s\" from %s" % (after, session_tag(id)))
        self.lock.acquire()
        try:
            del self.after[id]
        finally:
            self.lock.release()

    def notifySync(self, id):
        """Notify a thread to start in sync mode"""
        self.info("SYNC: notified from %s" % (session_tag(id)))
        self.lockSync.acquire()
        try:
            self.sync.remove(id)
            self.syncNotified = True
        finally:
            self.lockSync.release()

    def ssh_connect(self, hostname, port, username, passwd):
        """Connect and return True if successfull. Retry if connection fails.

        """
        sshport = int(port)
        self.info("connecting to %s:%s ... " % (ansi_bold(self.hostname),
                                                ansi_bold(self.port)))
        if not self.s:
            self.s = pxssh.pxssh()
        try:
            # p.hollands suggestion: original_prompt=r"][#$]|~[#$]|bash.*?[#$]|[#$] |.*@.*:.*>"
            # BROKEN original_prompt=r"[#$]|$"
            self.s.login(hostname, username, passwd,
                         login_timeout=self.SSH_LOGIN_TIMEOUT,
                         port=sshport, auto_prompt_reset=True)
            self.s.set_unique_prompt

            # TODO: disabling echo currently only works reliably under bash, so
            # also trying this way
            self.s.setecho(False)
            self.s.sendline('stty -echo;')
            if not self.s.prompt(self.PROMPT_TIMEOUT):
                print "could not match the prompt!"   # match the prompt within X seconds

            if not self.s.isalive():
                return False

            self.connected = True
            self.info("connected")

            if DEBUG:
                    self.debug("writing log file to %s" %
                               ansi_bold(self.id+'.log'))
                    fout = file('%s.log' % (self.id), 'w')
                    self.s.logfile = fout

        except pxssh.ExceptionPxssh as e:
            if e.message == 'password refused':
                self.error('invalid password for %s@%s! exiting...' %
                           (self.username, self.hostname))
                self.ssh_abort(e)
                return False

            self.debug(str(e))

            self.info("SSH session login to %s FAILED... retrying in %s s" % (self.hostname,
                                                                              self.SSH_LOGIN_REPEAT_TIMEOUT))

            time.sleep(self.SSH_LOGIN_REPEAT_TIMEOUT)
            self.s.close()
            self.ssh_connect(self.hostname, self.port,
                             self.username, self.passwd)
        except (select.error,IOError,OSError) as e:
            self.ssh_abort(e)
            return False
        except (pexpect.EOF) as e:
            self.error("could not connect to %s. check hostname" % txt_bold(self.hostname))
            self.ssh_abort(e)
            return False
        return True

    def ssh_abort(self, e=None):
        SSHControl.terminate_threads = True

    def remove(self):
        SSHControl.ssh_threads.remove(self)

    def ssh_disconnect(self):
        if self.s:
            try:
                self.s.close()
            except OSError:
                pass
            self.s = None
            self.info("disconnected")
        self.connected = False
        self.remove()

    def simCommand(self):
        """TODO @CK"""
        result = ""
        for t in SSHControl.ssh_threads:
            if not (t.after is None):
                if self.id in t.after.keys():
                    result = result + "echo \"" + t.after.get(self.id) + "\"; "
        return result
