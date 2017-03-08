import sys

from utilities import logging, bit_fields
from utilities.logging import log
from utilities.bit_fields import testBit, setBit, clearBit

from arch import machine
if machine == "ARM":
    from arm import armcpu, emulate
    from arm.emulate import ArmCpu
    from arm.armcpu import address_mask, TBIT, THUMBBIT
    from arm.armcpu import section_addrs, section_bytes
elif machine == "MSP430":
    from msp430 import msp430cpu, emulate
    from msp430.emulate import MSP430Cpu
    from msp430.msp430cpu import address_mask, section_addrs, section_bytes
else:
    print("Need to specify a machine type in arch.py")
    sys.exit(-1)

try:
    import elftools
except ImportError:
    sys.path.extend(['.', '..'])
from elftools.common.exceptions import ELFError
from elftools.elf.descriptions import (describe_sh_type, describe_sh_flags)
from elftools.common.py3compat import (
        ifilter, byte2int, bytes2str, itervalues, str2bytes)

from elf import readelf
from elf.readelf import ReadElf



def load_elf(filename, cpu):
    """ Load from .elf file into emulated memory."""
    nulldict = dict()
    try:
        with open(filename, 'rb') as file:
            try:
                #log("Loading from {:s}".format(filename))
                readelf = ReadElf(file, sys.stdout)
                elfheader = readelf.elffile.header
                init_addr, init_bytes = readelf.get_section_data(".init")        
                if init_bytes:
                    cpu.setup_memory(init_bytes, init_addr) 
                    log("Loaded 0x{:x} bytes at 0x{:x} from section {:s}".format(
                               len(init_bytes), init_addr, ".init"))
                    section_addrs[init_addr] = '.init'
                    section_bytes['.init'] = len(init_bytes)                    
                    
                text_addr, text_bytes = readelf.get_section_data(".text")
                if text_bytes:
                    cpu.setup_memory(text_bytes, text_addr)
                    log("Loaded 0x{:x} bytes at 0x{:x} from section {:s}".format(
                                  len(text_bytes), text_addr, ".text"))
                    section_addrs[text_addr] = '.text'
                    section_bytes['.text'] = len(text_bytes)
                    
                data_addr, data_bytes = readelf.get_section_data(".data")
                if data_bytes:
                    cpu.setup_memory(data_bytes, data_addr)
                    log("Loaded 0x{:x} bytes at 0x{:x} from section {:s}".format(
                            len(data_bytes), data_addr, ".data")) 
                    section_addrs[data_addr] = '.data'
                    section_bytes['.data'] = len(data_bytes)                    
                # TBD check for other loadable sections use something 
                # more like load_out()
                entry_address = elfheader['e_entry']
                cpu.pc = entry_address & address_mask
                if machine == "ARM":
                    if (entry_address & 1):  # currently armv7-M is all Thumb mode
                        cpu.thumb_mode = True
                        cpu.apsr = setBit(cpu.apsr, TBIT)
                    else:  # currently, armv7-A is all ARM mode (in this emulation)
                        cpu.thumb_mode = False
                        cpu.apsr = clearBit(cpu.apsr, THUMBBIT)
                
                return readelf.get_symbol_dictionary()
            except ELFError as ex:
                    log("ELF error: {:s}\n".format(ex))
                    return nulldict
                
    except FileNotFoundError:
        log( "File <"+filename+"> not found." ) 
        return nulldict
        
def load_out(filename, cpu):
    """ Load from .out file into emulated memory. """
    nulldict = dict()
    try:
        with open(filename, 'rb') as file:
            try:
                log("Loading from {:s}".format(filename))
                readelf = ReadElf(file, sys.stdout)        
                elfheader = readelf.elffile.header
                for nsec, section in enumerate(readelf.elffile.iter_sections()):
                    # something of a hack
                    if (describe_sh_type(section['sh_type']) == "PROGBITS" and
                        describe_sh_flags(section['sh_flags']) != ""):
                        section_name = bytes2str(section.name)
                        #log("Loading from section {:s}".format(section_name))
                        addr, nbytes = readelf.get_section_data(section_name)
                        if nbytes:
                            cpu.setup_memory(nbytes, addr) 
                            log("Loaded 0x{:x} bytes at 0x{:x} from section {:s}".format(
                                len(nbytes), addr, section_name))
                            section_addrs[addr] = section_name
                            section_bytes[section_name] = len(nbytes)                            

                entry_address = elfheader['e_entry']
                cpu.pc = entry_address & address_mask
                if machine == "ARM":
                    if (entry_address & 1):
                        cpu.thumb_mode = True
                        cpu.apsr = setBit(cpu.apsr, TBIT)
                    else:
                        cpu.thumb_mode = False
                        cpu.apsr = clearBit(cpu.apsr, THUMBBIT)
                return readelf.get_symbol_dictionary()
            except ELFError as ex:
                log("ELF error: {:s}\n".format(ex)) 
                return nulldict
                                
    except FileNotFoundError:
        log( "File <"+filename+"> not found." )
        return nulldict
         


def dump_elf(filename):
    """ Use the readelf routines to get section and header dumps as strings. """
    res = ""
    try:
        with open(filename, 'rb') as file:
            try:
                readelf = ReadElf(file, None) 
                res = "------------------- File Header --------------------\n"
                res += readelf.display_file_header()
                res += "----------------- Program Header --------------------"
                res += readelf.display_program_headers(show_heading=True)
                res += "----------------- Section Headers --------------------\n"
                res += readelf.display_section_headers(show_heading=True)
                res += "----------------- Symbol tables --------------------"
                res += readelf.display_symbol_tables()
                #add more if you want. NYI most DWARF stuff in readelf not
                #modified yet to return a string
            except ELFError as ex:
                    res +="ELF error: {:s}\n".format(ex)        
                
    except FileNotFoundError:
        res +=  "File <"+filename+"> not found."     
    return res