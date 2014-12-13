#
#    Copyright 2008 Zdravko Bozakov and Michael Bredel
#
#    This file is part of SSHLauncher.
#
#    SSHLauncher is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
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
import threading
import time
import code
import select
import logging


logging.debug('test!')
DEBUG = False
# LSD-style debug output
DEBUG_LABEL = '\033[1;32mDEBUG\033[m:'
ERROR_LABEL = '\033[1;32mERROR\033[m:'

def log_debug(text, level=1):
    if DEBUG:
        print DEBUG_LABEL + text

def color(id_str, ascii_fg=31, ascii_bg=47, bold=22):
    """print section id in color"""
    h = hash(id_str)
    ascii_fg = 30 + (h & 7)
    #ascii_bg = 40 + (-h & 7)
    bold = 1
    return "\033[%dm\033[%dm\033[%dm[%s]\033[0m" % (ascii_bg, bold, ascii_fg, id_str)


class ConfigError(Exception):
    def __init__(self):
        print "terminating thread!"
        #thread.exit()


class SSHControl (threading.Thread):
    """Starts a thread which establishes an SSH connection and executes a command.

    """

    # pxssh instance
    s = None
    # strore all ssh threads
    ssh_threads = []
    terminate_threads = False

    # pseudo static vars
    ESCAPE = False
    SIMULATE = False

    # start a login (l) or interactive(i) bash shell when issuing remote command
    # TODO this should be an option
    BASH = '/bin/bash -ls'
    # commands which should always executed before the command string
    BASH_SETUP = 'unset HISTFILE; '
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

        self.connected = False
        self.registered_after = False
        self.sync_registered = False
        self.syncNotified = False
        self.forcequit = False
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
            time.sleep(1)

        # register own expect string on thread id specified by after
        if self.after:
            for t in SSHControl.ssh_threads:
                for key in self.after.keys():
                    if t.getName() == str(key):
                        t.registerAfter(self.id, self.after[key])
        self.registered_after = True

        # wait until all threads have registered
        while [t for t in SSHControl.ssh_threads if not t.registered_after]:
            time.sleep(1)

        # register sync expect string on thread id specified by sync
        if self.sync:
            for t in SSHControl.ssh_threads:
                for key in self.sync:
                    if t.getName() == str(key):
                        t.register_sync(self.id)
        self.sync_registered = True

        # wait until all threads are synchonized
        while [t for t in SSHControl.ssh_threads if not t.sync_registered]:
            time.sleep(1)

        # now check the configuration
        self.checkConfig()

        # wait until all expect strings registered by current thread have been matched
        while (self.after and not self.syncNotified):
            time.sleep(1)

        # then connect
        if not self.sshConnect(self.hostname, self.port, self.username, self.passwd):
            return #TODO

        # notify all other threads in sync-group
        for tid in self.syncList:
            for t in SSHControl.ssh_threads:
                if t.getName() == tid:
                    t.notifySync(self.id)

        # wait until all sync-group threads have been connected
        while self.sync:
            time.sleep(1)
        # keep execution order
        while (self.after):
            time.sleep(1)

        # if simulate only
        if SSHControl.SIMULATE:
            self.command = self.simCommand()

        # execute command string
        self.info("executing: \033[1;34m%s\033[m " % (self.command))
        # self.command = self.BASH_SETUP + self.command
        # spawn a new bash session on remote host and pipe command string to it
        if SSHControl.ESCAPE:
            self.command = 'echo -e \' ' + self.BASH_SETUP + self.command + '\' | ' + self.BASH
        else:
            self.command = 'echo \' ' + self.BASH_SETUP + self.command + '\' | ' + self.BASH

        try:
            # send comand
            self.s.sendline(self.command)

            # start loop to match expect strings and notify other threads
            self.__expectWait()

            # wait for section command to finish (i.e. reach the prompt) and disconnect
            if self.s.prompt(self.PROMPT_TIMEOUT):
                self.ssh_disconnect()
            else:
                self.info("did not reach prompt! something went wrong\n")
                print self.s.before
                raise SystemError
                # if DEBUG : self.s.interact()
        except (select.error, IOError, OSError):
            self.ssh_abort();
            return


    def registerAfter(self, id, afterCommand):
        """register an expect string on this block"""
        self.lock.acquire()
        try:
            self.afterList[afterCommand].append(id)
        except KeyError:
            self.afterList[afterCommand] = [id]
        finally:
            self.lock.release()
        log_debug(" %s:\t->\t registered \"%s\" on %s" % (color(id), afterCommand, color(self.id)))


    def checkConfig(self):
        """very rudimentary check for valid section configuration"""

        if self.after:
            # check for circular refences
            for remote_after in [t for t in SSHControl.ssh_threads if (t.getName() in self.after.keys())]:
                if (remote_after.after and (self.id in remote_after.after.keys())):
                    self.info("***** ERROR: cirular references %s <-> %s? *****" \
                        % (color(self.id), color(self.id), color(remote_after.id)))
                    raise ConfigError

            # check for invalid section ids in AFTER
            for a in self.after:
                if not a in [t.id for t in SSHControl.ssh_threads]:
                    print "%s:\t***** ERROR: '%s' is not a valid section id in AFTER *****" % (color(self.id), a)
                    raise ConfigError
                # print [t.getName() for t in SSHControl.ssh_threads]

            # check for invalid section ids in SYNC
            if not (self.sync is None):
                for a in self.sync:
                    if not a in [t.id for t in SSHControl.ssh_threads]:
                        print "%s:\t***** ERROR: '%s' is not a valid section id in SYNC *****" % (color(self.id), a)
                        self.sync.remove(a)

        self.info("configuration seems ok")
        return True

    def register_sync(self, id):
        """register an expect string on this block"""
        self.lockSync.acquire()
        try:
            self.syncList.append(id)
        except KeyError:
            self.syncList = [id]
        finally:
            self.lockSync.release()
        log_debug(" %s:\t->\t synchronized with %s" % (color(id), color(self.id)))



    def __expectWait(self):
        """wait until all expect strings matched and remove corresponding entries from
        the threads after: queues.

        """
        try:
            while self.afterList.keys():
                res = self.s.expect(self.afterList.keys(), self.PEXPECT_TIMEOUT)
                after = self.afterList.keys()[res]
                log_debug(" %s:\t \"%s\" matched..." % (color(self.id), after))

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
            print "%s:\t EOF!" % (color(self.id),)
        except pexpect.TIMEOUT, e:
            print "%s:\t pexpect timed-out waiting for: %s" % (color(self.id), self.afterList.keys())
            log_debug(str(e))

    def __str__(self):
        return color(self.id)

    def info(self, text):
        print "%s: \t%s" % (color(self.id), text )

    def notifyAfter(self, id, after):
        """notify a thread that the expect string has been matched"""
        self.info("matched \"%s\" from %s" % (after, color(id) ))
        self.lock.acquire()
        try:
            del self.after[id]
        finally:
            self.lock.release()

    def notifySync(self, id):
        """notify a thread that to start in sync mode"""
        self.info("SYNC: notified from %s" % (color(id)))
        self.lockSync.acquire()
        try:
            self.sync.remove(id)
            self.syncNotified = True
        finally:
            self.lockSync.release()

    def getInfo(self):
        """print some info on the conneciton"""
        print '\nthread: %s\talive: %s' % (self.getName(), self.isAlive())
        if self.s:
            print 'ssh connection is alive :%s' % (self.s.isalive(),)
            print self.s.PROMPT

    def sshConnect(self, hostname, port, username, passwd):
        sshport = int(port)
        self.info("connecting to %s:%s ... " % (self.hostname, self.port))
        if not self.s:
            self.s = pxssh.pxssh()

            #code.interact(local=locals())

        try:
            # p.hollands suggestion: original_prompt=r"][#$]|~[#$]|bash.*?[#$]|[#$] |.*@.*:.*>"
            # BROKEN original_prompt=r"[#$]|$"
            self.s.login(hostname, username, passwd,
                            login_timeout=self.SSH_LOGIN_TIMEOUT,
                            port=sshport, auto_prompt_reset=True)
            self.s.set_unique_prompt

            # TODO: disabling echo currently only works reliably under bash, so also trying this way
            self.s.setecho(False)
            self.s.sendline('stty -echo;')
            if not self.s.prompt(self.PROMPT_TIMEOUT):
                print "could not match the prompt!"   # match the prompt within X seconds

            if not self.s.isalive():
                return False

            self.connected = True
            print "%s:\t\t ...connected to %s " % (color(self.id), self.hostname)

            if DEBUG:
                    log_debug("\t writing log file to %s.log" % (self.id))
                    fout = file('%s.log' % (self.id), 'w')
                    self.s.logfile = fout

        except pxssh.ExceptionPxssh as e:
            if e.message=='password refused':
                print color(self.id) + ':\t' + str(e)
                print 'NOT continuing!' # TODO
                self.ssh_abort(e)
                return False

            log_debug(str(e))

            self.info("SSH session login to %s FAILED.... retrying in %s s" % (self.hostname,
                                                                                 self.SSH_LOGIN_REPEAT_TIMEOUT))

            time.sleep(self.SSH_LOGIN_REPEAT_TIMEOUT)
            self.s.close()
            self.sshConnect(self.hostname, self.port, self.username, self.passwd)
        except (select.error,IOError,OSError) as e:
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
            #self.s.kill(9)
            self.s = None
            self.info("disconnected.")
        self.connected = False
        self.remove()



    def simCommand(self):
        result = ""
        for t in SSHControl.ssh_threads:
            if not (t.after is None):
                if self.id in t.after.keys():
                    result = result + "echo \"" + t.after.get(self.id) + "\"; "
        return result
