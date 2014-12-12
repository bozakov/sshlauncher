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
import thread
import time
import code
import logging


logging.debug('test!')
DEBUG = False
DEBUG_LABEL = '\033[1;32mDEBUG\033[m:'
ERROR_LABEL = '\033[1;32mERROR\033[m:'

def log_debug(text, level=1):
    if DEBUG:
        print DEBUG_LABEL + text

class ConfigError(Exception):
    def __init__(self):
        print "terminating thread!"
        thread.exit()


class TerminateException(Exception):
    pass


class SSHControl (threading.Thread):
    """Starts a thread which establishes an SSH connection and executes a command.

    """

    # pxssh instance
    s = []
    # strore all ssh threads
    ssh_threads = []

    # pseudo static vars
    ESCAPE = False
    SIMULATE = False
    # lsd-style debug output

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

        self.afterList = {}
        self.syncList = []
        self.id = id

        self.connected = False
        self.registeredAfter = False
        self.registeredSync = False
        self.syncNotified = False
        self.forcequit = False
        self.init = False

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

        threading.Thread.__init__(self)
        self.setDaemon(True)


    def run(self):
        """thread method"""
        self.setName(self.id)
        self.init = True
        time.sleep(self.delay)

        # wait until all threads are alive
        while [t for t in SSHControl.ssh_threads if not t.init]:
            time.sleep(1)

        # register own expect string on thread id specified by after
        if self.after:
            for t in SSHControl.ssh_threads:
                for key in self.after.keys():
                    if t.getName() == str(key):
                        t.registerAfter(self.id, self.after[key])
        self.registeredAfter = True

        # wait until all threads have registered
        while [t for t in SSHControl.ssh_threads if not t.registeredAfter]:
            time.sleep(1)

        # register sync expect string on thread id specified by sync
        if self.sync:
            for t in SSHControl.ssh_threads:
                for key in self.sync:
                    if t.getName() == str(key):
                        t.registerSync(self.id)
        self.registeredSync = True

        # wait until all threads are synchonized
        while [t for t in SSHControl.ssh_threads if not t.registeredSync]:
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
        print "%s:\t executing: \033[34m%s\033[m " % (str(self), self.command)
        # self.command = self.BASH_SETUP + self.command
        # spawn a new bash session on remote host and pipe command string to it
        if SSHControl.ESCAPE:
            self.command = 'echo -e \' ' + self.BASH_SETUP + self.command + '\' | ' + self.BASH
        else:
            self.command = 'echo \' ' + self.BASH_SETUP + self.command + '\' | ' + self.BASH

        # send comand
        self.s.sendline(self.command)

        # start loop to match expect strings and notify other threads
        self.__expectWait()

        # wait for section command to finish (i.e. reach the prompt) and disconnect
        if self.s.prompt(self.PROMPT_TIMEOUT):
            self.sshDisconnect()
        else:
            print "%s:\t did not reach prompt! something went wrong\n" % (str(self),)
            print self.s.before
            raise SystemError
            # if DEBUG : self.s.interact()


    def registerAfter(self, id, afterCommand):
        """register an expect string on this block"""
        self.lock.acquire()
        try:
            self.afterList[afterCommand].append(id)
        except KeyError:
            self.afterList[afterCommand] = [id]
        finally:
            self.lock.release()
        log_debug(" %s:\t->\t registered \"%s\" on %s" % (self.__cid(id), afterCommand, str(self)))


    def checkConfig(self):
        """very rudimentary check for valid section configuration"""

        if self.after:
            # check for circular refences
            for remote_after in [t for t in SSHControl.ssh_threads if (t.getName() in self.after.keys())]:
                if (remote_after.after and (self.id in remote_after.after.keys())):
                    print "%s:\t***** ERROR: cirular references %s <-> %s? *****" \
                        % (str(self), str(self), self.__cid(remote_after.id))
                    raise ConfigError

            # check for invalid section ids in AFTER
            for a in self.after:
                if not a in [t.id for t in SSHControl.ssh_threads]:
                    print "%s:\t***** ERROR: '%s' is not a valid section id in AFTER *****" % (str(self), a)
                    raise ConfigError
                # print [t.getName() for t in SSHControl.ssh_threads]

            # check for invalid section ids in SYNC
            if not (self.sync is None):
                for a in self.sync:
                    if not a in [t.id for t in SSHControl.ssh_threads]:
                        print "%s:\t***** ERROR: '%s' is not a valid section id in SYNC *****" % (str(self), a)
                        self.sync.remove(a)

        print "%s:\t configuration seems ok" % (str(self))
        return True

    
    def registerSync(self, id):
        """register an expect string on this block"""
        self.lockSync.acquire()
        try:
            self.syncList.append(id)
        except KeyError:
            self.syncList = [id]
        finally:
            self.lockSync.release()
        log_debug(" %s:\t->\t synchronized with %s" % (self.__cid(id), str(self)))



    def __expectWait(self):
        """wait until all expect strings matched and remove corresponding entries from
        the threads after: queues.

        """
        try:
            while self.afterList.keys():
                res = self.s.expect(self.afterList.keys(), self.PEXPECT_TIMEOUT)
                after = self.afterList.keys()[res]
                log_debug(" %s:\t \"%s\" matched..." % (str(self), after))

                for tid in self.afterList[after]:
                    for t in SSHControl.ssh_threads:
                        if t.getName() == tid:
                            t.notifyAfter(self.id, after)

                self.lock.acquire()
                try:
                    del self.afterList[after]
                finally:
                    self.lock.release()

        except pexpect.EOF:
            print "%s:\t EOF!" % (str(self),)
        except pexpect.TIMEOUT, e:
            print "%s:\t pexpect timed-out waiting for: %s" % (str(self), self.afterList.keys())
            log_debug(str(e))


    def __str__(self):
        return "\033[1;31m[%s]\033[m" % self.id

    def __cid(self, id):
        """print section id in color"""
        return "\033[1;31m[%s]\033[m" % id


    def notifyAfter(self, id, after):
        """notify a thread that the expect string has been matched"""
        print "%s:\t notified from %s (matched \"%s\")" % (str(self), self.__cid(id), after)
        self.lock.acquire()
        try:
            del self.after[id]
        finally:
            self.lock.release()


    def notifySync(self, id):
        """notify a thread that to start in sync mode"""
        print "%s:\t SYNC: notified from %s" % (str(self), self.__cid(id))
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
        print "%s:\t connecting to %s:%s ... " % (str(self),
                                                  self.hostname, self.port)
        if not self.s:
            self.s = pxssh.pxssh()

            #code.interact(local=locals())

        try:
            # p.hollands suggestion: original_prompt=r"][#$]|~[#$]|bash.*?[#$]|[#$] |.*@.*:.*>"
            # BROKEN original_prompt=r"[#$]|$"
            self.s.login(hostname, username, passwd,
                            login_timeout=self.SSH_LOGIN_TIMEOUT,
                            port=sshport, auto_prompt_reset=True)
            print "%s:\t ...connected to %s " % (str(self), self.hostname)

            self.s.set_unique_prompt

            # TODO: disabling echo currently only works reliably under bash, so also trying this way
            self.s.setecho(False)
            self.s.sendline('stty -echo; ')
            if not self.s.prompt(self.PROMPT_TIMEOUT):
                    print "could not match the prompt!"   # match the prompt within X seconds
            self.connected = True

            if DEBUG:
                    log_debug("\t writing log file to %s.log" % (self.id))
                    fout = file('%s.log' % (self.id), 'w')
                    self.s.logfile = fout

        except pxssh.ExceptionPxssh as e:

            if e.message=='password refused':
                print str(self) + ':\t' + str(e)
                print 'NOT continuing!' # TODO
                self.s.close()
                self.s = []
                return False

            log_debug(str(e))

            code.interact(local=locals())


            print "%s:\t SSH session login to %s FAILED.... retrying in %s s" % (str(self), self.hostname,
                                                                                 self.SSH_LOGIN_REPEAT_TIMEOUT)

            time.sleep(self.SSH_LOGIN_REPEAT_TIMEOUT)
            self.s.close()
            self.s = []
            self.sshConnect(self.hostname, self.port, self.username, self.passwd)
        return True



    def sshDisconnect(self):
        if self.s:
            self.s.timeout = self.PEXPECT_TIMEOUT
            self.connected = False
            self.s.kill(9)
            self.s = []
            print "%s:\t disconnected." % (str(self))
        SSHControl.ssh_threads.remove(self)

    def sshAbort(self):
        SSHControl.ssh_threads = []


    def simCommand(self):
        result = ""
        for t in SSHControl.ssh_threads:
            if not (t.after is None):
                if self.id in t.after.keys():
                    result = result + "echo \"" + t.after.get(self.id) + "\"; "
        return result
