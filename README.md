SSHLauncher facilitates the execution of distributed, reproducible,
SSH based experiments 

Copyright (c) 2008 Zdravko Bozakov

License:

SSHLauncher is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, either version 3 of the License, or (at your
option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Summary:

Simulation and emulation experiments are widely used for investigating new
approaches and verifying existing theories in communication networks.
SSHLauncher is a tool for performing automated experiments in distributed
testbeds such as Emulab or PlanetLab. Using an intuitive configuration file
syntax, large sets of complex command sequences can be executed with minimal
user interaction. As a result, the repeated execution of experiments and the
generation of controlled, documented, and reproducible results is greatly
facilitated.

# Installation:

For a system-wide SSHLauncher installation run

    $ python setup.py install

you will probably require root privileges. However, SSHLauncher can also be
executed as a stand alone application from the local directory. Note, that you
will probably have to install the (included) pexpect package first.


# Usage:

    $ sshlauncher [-d] [-e] [-s] configfile

Please refer to the included [PDF][PDF] file for detailed instructions on
setting up the configuration file.

[PDF]: ./test



