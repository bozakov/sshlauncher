from distutils.core import setup
setup(name='sshlauncher',
      version='2.0.2',
      py_modules=['sshctrl'],
      scripts=['sshlauncher'],
      requires=['pexpect'],
      description='SSHLauncher is allows an easy, scripted, parallel execution of applications on multiple hosts.',
      author='Zdravko Bozakov, Michael Bredel',
      author_email='zdravko.bozakov@ikt.uni-hannover.de',
      url='http://www.ikt.uni-hannover.de',
      license='GPL',
      platforms='UNIX',
      long_description='Simulation and emulation experiments are widely used for verifying new approaches as well as existing theories in communication networks. In this report, we present a tool for performing automated experiments in distributed testbeds such as Emulab or PlanetLab. Using an intuitive configuration file syntax, large sets of complex command sequences can be executed with minimal user interaction. As a result, repeated execution of experiments and the generation of controlled, documented, and reproducible results is greatly facilitated.',
      )
