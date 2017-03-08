# emulator

An emulator for ARM machines and also for the TI MSP430 (selectable by 
modifying the arch file.
Written in Python 3
Consists of 
  1. A GUI debugger/disassembler/elf or coff dumper using tkinter
  2. A command line debugger.
  3. A command line disassembler.

Uses pyelftools. Sorry, I copied it into this repository as I'm a relative 
newbie to git. I hoped to allow anyone to use this program out of the box.

The various targets I used were the Raspberry Pi with some kernel Images I built
following Tutorials from a Cambridge University Lecturer (Robert Mullins)f.
http://www.cl.cam.ac.uk/projects/raspberrypi/tutorials/os/index.html
Started by producing a disassembler and the built a small command line emulator
debugger (dbg).
I then produced the gui debugger (gui_dbgr) so things are not very well 
structured. It would be nice to use a more modern GUI but Qt and PySide 
only recently moved up to Python 3.
I then drifted on to using the TI Launchpad for Tiva upon which I found I 
needed Thumb code and elf executables.
After this I felt a need to try to make a more general purpose emulator so I
grafted in support for the MSP430 Launchpad. This is a much simpler machine but
the version of CCS (Code Composer Studio) I was using generated Coff 
executables.


I provided some useful documentation under docs. The help menu also 
provides some info.
