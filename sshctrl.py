#
#    Copyright 2008 Zdravko Bozakov
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
import pxssh
import pexpect
import threading
import thread
import time
import sys

class ConfigError(Exception): 
    def __init__(self):
	print "terminating thread!"
	thread.exit()

class TerminateException(Exception): pass

class SshControl ( threading.Thread ):
    """ Starts a thread which establishes an SSH connection and executes a command. """
    
    s = []
    sshThreads = []                # contains all ssh threads
    sshThreadsConnected = False    # True if all connections have been established

    # pseudo static vars
    DEBUG = False
    DEBUG_LABEL = '\033[1;32mDEBUG\033[m:'
    BASH = '/bin/bash -is'
    BASH_SETUP = 'unset HISTFILE; '
    SSH_LOGIN_REPEAT_TIMEOUT = 10
    SSH_LOGIN_TIMEOUT=15
    PROMPT_TIMEOUT=5

    def __init__ ( self, id, hostname, username, passwd, command, after = {}, delay=0 ):
        """ """
        self.expectList = {}
        self.id  = id
       
        self.connected = False
        self.registered = False
        self.forcequit = False
        self.init = False

        self.hostname = hostname
        self.username = username
        self.passwd = passwd
        self.delay = delay
        self.command = command
        self.after = after

        
	threading.Thread.__init__ ( self )
	
        #self.setDaemon( True )
 
       
        
    def checkConfig (self):
        """ check if section configuration is valid """
	
        if self.after:            
            # check for circular refences
            for remote_after in [t for t in self.sshThreads if (t.getName() in self.after.keys())]:
                if (remote_after.after and (self.id in remote_after.after.keys())):
                    print "%s:\t***** ERROR: cirular references %s <-> %s? *****" \
                        % (self.cid(self.id), self.cid(self.id), self.cid(remote_after.id))
		    raise ConfigError

            # check for invalid section ids
            for a in self.after:
               if not a in [t.id for t in self.sshThreads]:
                   print "%s:\t***** ERROR: '%s' is not a valid section id *****" % (self.cid(self.id), a)
                   raise ConfigError
               #print [t.getName() for t in self.sshThreads]

        print "%s:\t configuration seems ok" % (self.cid(self.id))
        return True


	
    def cid (self, id):
        """ print section id in color """
	return "\033[1;31m[%s]\033[m" % id



    def run (self):
        """ thread method """
        self.setName( self.id )
        self.init = True    
        time.sleep( self.delay )

        # wait until all threads are alive
        while [ th for th in self.sshThreads if not th.init ]:
            time.sleep(1)
        
        # register own expect string on thread id specified by after
        if self.after: 
            for t in self.sshThreads :
                for key in self.after.keys() :
                    if t.getName()==str(key) :
                        t.register(self.id, self.after[key])
        self.registered = True

        # wait until all threads have registered
        while [ t for t in self.sshThreads if not t.registered ]:
            time.sleep(1)

	self.checkConfig()
	
        # wait until all expect strings registered by current thread have been matched
        while self.after :
            time.sleep(1)
            
        # then connect
        self.sshConnect( self.hostname, self.username, self.passwd )
                
        # execute command string
        print "%s:\t executing: \033[34m%s\033[m " % (self.cid(self.id), self.command)
	#self.command = self.BASH_SETUP + self.command	
	#self.command = 'echo \"unset HISTFILE; ' + self.command + '\" | ' + self.BASH
        # spawn a new bash session on remote host and pipe command string to it
	self.command = 'echo \' ' + self.BASH_SETUP + self.command + '\' | ' + self.BASH
        self.s.sendline( self.command )
        
        # start loop to match expect strings and notify other threads
        self.__expectWait()
        
   
               
    def register ( self, id, afterCommand ) :
        """ register an expect string on this block """
        try :
            self.expectList[afterCommand].append(id)
        except KeyError :
            self.expectList[afterCommand] = [id]
        if SshControl.DEBUG: print self.DEBUG_LABEL + " %s:\t->\t registered \"%s\" on %s" % (self.cid(id), afterCommand, self.cid(self.id))


    def __expectWait ( self ):
        """ wait until all expect strings matched and remove corresponding entries from the threads after: queues """
        try : 
            while self.expectList.keys():
                res = self.s.expect(self.expectList.keys(), 5000)
                after =  self.expectList.keys()[res]
                if SshControl.DEBUG: print self.DEBUG_LABEL + " %s:\t \"%s\" matched..." % (self.cid(self.id), after)
                
                for tid in self.expectList[after]:
                    for t in self.sshThreads : 
                        if t.getName()==tid :
                            t.notify( self.id, after )
                del self.expectList[after]

            # START EXPERIMENTAL sometimes we get password prompts in a running session -> switch to interactive mode
            res = self.s.expect([self.s.PROMPT, 'passwor'], timeout=5000) 
            if res == 1 :
                time.sleep(50)
                print "%s:\t still connected! switching to interactive mode:\n" % (self.cid(self.id),)
                print self.s.before
                self.s.interact()
            elif res == 0 :
                self.sshDisconnect()
	    # END EXPERIMENTAL
        except pexpect.EOF :
            print "%s:\t EOF!" % (self.cid(self.id),)
        except pexpect.TIMEOUT :
            print "%s:\t pexpect timed-out waiting for: %s" % (self.cid(self.id), self.expectList.keys())





    def notify( self, id, after ):
        """ notify a thread that the expect string has been matched """
        print "%s:\t notified from %s (matched \"%s\")" % (self.cid(self.id), self.cid(id), after)
        del self.after[id]


        
    def getInfo (self):
        print 'thread: %s\tthread alive: %s' % (self.getName(), self.isAlive())
        if self.s:
            print 'ssh connection %s' % (self.s.isalive(),)



    def sshConnect ( self, hostname, username, passwd ):
        print "%s:\t connecting to %s ... " % (self.cid(self.id), self.hostname)
        if not self.s:
            self.s = pxssh.pxssh()
        
        try:
            if self.s.login (hostname, username, passwd, login_timeout=self.SSH_LOGIN_TIMEOUT):
                print "%s:\t ...connected to %s " % (self.cid(self.id), self.hostname)


                self.s.prompt(self.PROMPT_TIMEOUT)                    # match the prompt within X seconds
                self.connected = True

	        # TODO: disabling echo currently only works reliably under bash
	        self.s.setecho(False)
		# TODO: so trying to disable echo this way
                self.s.sendline('stty -echo; ')
                                
                if SshControl.DEBUG :
                    print self.DEBUG_LABEL + "\t writing log file to %s.log" % (self.id)  
                    fout = file('%s.log' % (self.id) ,'w')
                    self.s.logfile = fout
            else:
                raise pxssh.ExceptionPexpect('connection error!')

              
        except pxssh.ExceptionPexpect, e:    
            print "%s:\t SSH session login to %s FAILED.... retrying in %s s" % (self.cid(self.id), self.hostname, self.SSH_LOGIN_REPEAT_TIMEOUT) 
            if SshControl.DEBUG: print e

            time.sleep(self.SSH_LOGIN_REPEAT_TIMEOUT)
            self.s.close()
            self.s = []
            self.sshConnect( self.hostname, self.username, self.passwd )     
            #print str(self.s)




    def sshDisconnect ( self ):
        if self.s:
            self.connected = False
            self.s.logout()
            self.s.close()
            self.s = []
            print "%s:\t disconnected." % (self.cid(self.id))
        SshControl.sshThreads.remove(self)


