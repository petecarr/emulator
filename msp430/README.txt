msp430.

ccs 5 generates elf eabi (metronome_430.out)
ccs 4 generates legacy coff as in HelloWorld.out.
 

yagarto objdump understands the elf (but not -d since it is msp430 not arm)
readelf/loadelf probably work. machine architecture appears to be unknown.
