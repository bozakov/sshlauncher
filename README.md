SSHLauncher facilitates the execution of distributed, reproducible,
SSH-based experiments.
Copyright (c) 2008 Zdravko Bozakov

# License:

This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program; If not, see <http://www. gnu. org/licenses/>.

# Summary:

Simulation and emulation experiments are widely used for investigating new approaches and verifying existing theories in communication networks. SSHLauncher is a tool for performing automated experiments in distributed testbeds such as Emulab or PlanetLab. Using an intuitive configuration file syntax, large sets of complex command sequences can be executed with minimal user interaction. As a result, the repeated execution of experiments and the generation of controlled, documented, and reproducible results is greatly facilitated.

![Typical SSHLauncher experimental setup.](http://cdn.rawgit.com/bozakov/sshlauncher/testing/doc/img/setup_light.svg)

# Installation:

For a system-wide SSHLauncher installation run

    $ python setup.py install

you will probably require root privileges. However, SSHLauncher can also be executed as a stand alone application from the local directory. Note, that SSHLauncher relies on the excellent [pexpect](https://github.com/pexpect/pexpect) package which you may need to install first (a version is included for convenience).

    $ pip install pexpect

SSHLauncher requires Python version >= 2.6 and has been tested with `pexpect` version 3.3.

# Usage:

    $ sshlauncher [options] configfile

    Options:
    --version       show program's version number and exit
    -h, --help      show this help message and exit
    -d, --debug     enable debug mode
    -e, --escape    enable interpretation of backslash escapes in commands
    -s, --simulate  simulates the sshlauncher configuration by replacing
    commands by relevant echos

For each SSH session which should be spawned, the configuration file contains a block specifying the host name, the command to be executed as well as any potential dependencies on the output of other sessions.

    # prepare receiver
    [receiver]
    host: nodeA.filab.uni-hannover.de
    password: xyz123
    command: iperf -s

    # start sender when receiver is ready
    [sender_session]
    host: nodeB.filab.uni-hannover.de
    command: iperf -c nodeA.filab.uni-hannover.de
    after: {'receiver':'Server listening'}

Additional parameters may be passed from the shell through environment variables. Please refer to the [technical report](sshlauncher_tr.pdf) for detailed instructions on setting up the configuration file.
