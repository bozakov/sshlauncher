SSHLauncher facilitates the execution of distributed, reproducible,
SSH-based experiments.
Copyright (c) 2008 Zdravko Bozakov, Michael Bredel

# License:

This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program; If not, see <http://www.gnu.org/licenses/>.

# Summary:

Simulation and emulation experiments are widely used for investigating new approaches and verifying existing theories in communication networks. SSHLauncher is a tool for performing automated experiments in distributed testbeds such as Emulab or PlanetLab. Using an intuitive configuration file syntax, large sets of complex command sequences can be executed with minimal user interaction. As a result, the repeated execution of experiments and the generation of controlled, documented, and reproducible results is greatly facilitated.

In contrast to tools such as `parallel-ssh`, SSHLauncher allows users to specify the order in which ssh sessions are spawned by defining dependencies based on the output of the executed commands.

![Typical SSHLauncher experimental setup.](http://cdn.rawgit.com/bozakov/sshlauncher/master/doc/img/setup_light.svg)

# Installation:

For a system-wide SSHLauncher installation, clone the repository and run

    $ python setup.py install

you will probably need root privileges. However, SSHLauncher can also be executed directly from the local directory. Note, that SSHLauncher relies on the excellent [pexpect](https://github.com/pexpect/pexpect) package which you may need to install first.

    $ pip install pexpect

SSHLauncher requires Python version >= 2.6 and has been tested with `pexpect` version 3.3. Note: as of November 2015 the 4.x branch of expect does not run with Python 2.x. You can checkout the last working version using `sudo pip install pexpect==3.3`

You can also install SSHLauncher from PyPI, which will also install `pexpect`:

    $ pip install sshlauncher


# Usage:

For each SSH session which should be spawned, the configuration file contains a block specifying the host name (`host:`), user (`user:`), the command to be executed (`comand:`) as well as any potential dependencies on the output of other sessions (`after:`).

```INI
# prepare receiver
[receiver]
user: bozakov
host: nodeA.filab.uni-hannover.de
password: xyz123
command: iperf -s

# start sender when receiver is ready
[sender_session]
user: bozakov
host: nodeB.filab.uni-hannover.de
command: iperf -c nodeA.filab.uni-hannover.de
after: {'receiver':'Server listening'}
```

A `[DEFAULT]` section may be added to set default values or variables for use within each session: 

```
[DEFAULT]
user: bozakov
RCV_IP = 192.168.1.147
```

then: 

```
[sender_session]
host: nodeB.filab.uni-hannover.de
command: iperf -c  %(RCV_IP)s
after: {'receiver':'Server listening'}
```


Additional parameters may be passed from the OS shell to the sshlauncher script for iterating through experiment parameters: when sshlauncher is started all environment variables with a name beginning with `SL_` are imported. An example of setting TCP window sizes within a script is

    command: iperf -c nodeA.filab.uni-hannover.de -w %(SL_WIN_SIZE)s

Please refer to the [technical report](sshlauncher_tr. pdf) for detailed instructions on setting up the configuration file.

To run SSHLauncher use:

```
    $ sshlauncher [options] configfile

    Options:
    --version       show program's version number and exit
    -h, --help      show this help message and exit
    -d, --debug     enable debug mode
    -e, --escape    enable interpretation of backslash escapes in commands
    -s, --simulate  simulates the execution of a test run by mimicking the expected outputs
```


## Tips

* If you are planning on opening many simultaneous SSH on a machine sessions you should consider increasing the parameter `MaxStartups` in your `sshd_config`.
