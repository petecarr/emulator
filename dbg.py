import os, sys
import array

from arch import machine
if machine == "ARM":
    from arm import armcpu, emulate
    from arm.emulate import ArmCpu
    from arm.armcpu import register_names, HIGH_MEMORY_START
    from arm.armcpu import MEMADDR, MEMSIZE
    from arm.armcpu import symdict, labels, get_sym, is_thumb32, visual_ccs
    from arm import disass
    from arm.armcpu import section_addrs, section_bytes, das_strings
    # save time if you just type l in the command entry frame
    KERNEL_IMAGE="project0.out"    
elif machine == "MSP430":
    from msp430 import msp430cpu, emulate
    from msp430.emulate import MSP430Cpu
    from msp430.msp430cpu import section_addrs, section_bytes, das_strings
    from msp430.msp430cpu import register_names
    from msp430.msp430cpu import MEMADDR, MEMSIZE
    from msp430.msp430cpu import symdict, labels, get_sym, visual_ccs
    from msp430 import disass
    # save time if you just type l in the command entry frame
    KERNEL_IMAGE="msp430/metronome_430.out"   #"kernel.img"    
else:
    print("Need to specify a machine type in arch.py")
    sys.exit(-1)
    

from elf import *
from elf.loadelf import load_elf, load_out

from coff import *
from coff.loadcoff import load_coff

from utilities import my_hex, bit_fields, check_for_diffs, logging, scripting
from utilities.bit_fields import *
from utilities.my_hex import *
from utilities.check_for_diffs import *
from utilities.logging import *
from utilities.scripting import *
from utilities import load_files
from utilities.load_files import char_repr
    


cpu = None


"""
A basic machine level debugger using (mostly) single character commands.
(See h command for help). 
Understands kernel.img files which are simple memory images starting 
at location 0. Also understands .elf files from which the img files are 
made (using objcopy). .out files are the Texas Instruments elf files 
output by their Code Composer Studio Linker.

armcpu/msp430cpu contains cpu  bit positions etc and
           general service routines for disassembly and emulation
emulate contains the CPU emulator.
"""
#---------------------------------------------------------------------------

def is_code_section(addr):
    """ Is an address in a code section. """
    # The image file is considered all instructions, it is just a raw binary
    # image starting at 0.
    for section_addr, section_name in section_addrs.items():     
        if (section_name == '.text') or (
            section_name == 'image') or (
            section_name == 'reset') or (
            section_name == '.init'):
            code_start = section_addr
            code_bytes = int(section_bytes[section_name])
            code_end = code_start + code_bytes
            if code_start <= addr < code_end:
                return True

    return False

def is_const_section(addr):
    """ Is an address in a const section. """
    for section_addr, section_name in section_addrs.items():     
        if (section_name == '.const'):
            code_start = section_addr
            code_bytes = int(section_bytes[section_name])
            code_end = code_start + code_bytes
            if code_start <= addr < code_end:
                return True

    return False


def new_section_check(addr):
    res = ""
    if addr in section_addrs:
        res += "\n======== Start of {:s} section ========\n".format(
                                section_addrs[addr])
    return res
 
if machine == "ARM":
    def dump(memory, startad, endad):
        """ Dump routine. See emulator.read_memory for the emulator approach. """
        res = ""
        gap = 0
 
        # but not always
        if cpu.thumb_mode: instr_size = 2
        else:              instr_size = 4
 
        
        # Made the caller align the address
        #startad = (startad//instr_size)*instr_size
        #endad = (endad//instr_size)*instr_size
     
        i = startad
    
        addr = startad
        while addr <= endad:
            if i <= addr:
                res += new_section_check(addr)
                #if is_const_section(addr):  # for debug
                #    pass
                membytes = cpu.read_memory(addr, instr_size)
                if membytes is not None:
                    memword = int.from_bytes(membytes, 'little')
                else:
                    print("Reading uninitialized memory, address = {:#x}".format(addr))
                    memword = 0   # should this happen
          
                if is_code_section(addr):
                    if cpu.thumb_mode: 
                        #if is_thumb32(memword):
                        #    instr_size = 4
                        #else:
                        instr_size = 2
                    else:
                        instr_size = 2  
                    
                    if memword == 0:  
                        gap += 1
                        i+= instr_size
                    else:
                        if gap > 0:
                            res += "*** gap of {:d} halfword".format(gap)
                            if gap > 1:
                                res += 's'
                            res += '\n'
                            gap = 0 
                        if addr in symdict:
                            res += '\n---------' + '<' + symdict[addr] + '>:\n'
                        mbytes = membytes[0:instr_size]
                        instr = cpu.read_memory_int(addr, 4)
                      
                        tmp_res, actual_instr_size = disass.disass(addr, 
                                                            instr, 
                                                           cpu.thumb_mode)
                        if cpu.thumb_mode:
                            if actual_instr_size == 4:
                                extrabytes = my_hex(cpu.read_memory(addr+2, 2))
                            else:
                                extrabytes = "    "
                        else:
                            extrabytes = ""
                        res += "{:08x} ".format(addr) +  my_hex(
                             mbytes) + " " + extrabytes + "  " + tmp_res + "\n"
                        i += actual_instr_size  # Thumb 2 could be either 
                else:
                    
                    if (addr % 4) == 0:
                        instr_size = 4  # not code, not an instruction
                        if memword != 0:
                            if gap > 1:
                                res += "*** repeats for {:d} word".format(gap-1)
                                if (gap-1) > 1:
                                    res += 's'
                                res += '\n'
                            gap = 0                               
                            mbytes = cpu.read_memory(addr, 4)
                            res += "{:08x} ".format(addr)+'.word '+my_hex(mbytes)+"\n"
                        else:
                            if gap == 0:
                                res += "{:08x} ".format(addr)+'.word 0\n'
                            gap += 1
                        i += 4
                    else: 
                        instr_size = 2
                        res += "{:08x} ".format(addr)+'.word '+my_hex(membytes)+"\n"
                        i += 2 
            addr = cpu.get_next_addr(addr, instr_size)
            if addr is None:
                addr = endad+instr_size  
            
        return res    
    
elif machine == "MSP430":
    
    def dump(memory, startad, endad):  # for msp430
        """ Dump routine. See emulator.read_memory for the emulator approach. """
        res = ""
        gap = 0

        #cpu.thumb_mode = False
        instr_size = 2
     
        i = startad
    
        addr = startad
        while addr <= endad:
            if i <= addr:
                res += new_section_check(addr)
                #if is_const_section(addr):  # for debug
                #    pass
                membytes = cpu.read_memory(addr, instr_size)
                if membytes is not None:
                    memword = int.from_bytes(membytes, 'little')
                else:
                    print("Reading uninitialized memory, address = {:#x}".format(addr))
                    memword = 0   # should this happen (it did due to a bug)
          
                if is_code_section(addr): 
                    if machine == "MSP430":
                        instr_size = 2 # always true in the code section
                    if memword == 0:  
                        gap += 1
                        i+= instr_size
                    else:
                        if gap > 0:
                            res += "*** gap of {:d} halfword".format(gap)
                            if gap > 1:
                                res += 's'
                            res += '\n'
                            gap = 0 
                        if addr in symdict:
                            res += '\n---------' + '<' + symdict[addr] + '>:\n'
                        mbytes = membytes[0:instr_size]
                        instr = [0,0,0]
                        instr[0] = cpu.read_memory_int(addr, instr_size)
                        instr[1] = cpu.read_memory_int(addr+2, instr_size)
                        instr[2] = cpu.read_memory_int(addr+4, instr_size)
                      
                        tmp_res, actual_instr_size = disass.disass(addr, 
                                                            instr, 
                                                            dummy = False)
                     
                        if actual_instr_size == 2:
                            extra1 = extra2 = "    "
                        elif actual_instr_size == 4:
                            extra2 = "    "
                            extra1 = '{:04x}'.format(instr[1])
                        elif actual_instr_size == 6:
                            extra1 = '{:04x}'.format(instr[1])
                            extra2 = '{:04x}'.format(instr[2])
                        else: # a bug
                            log("bug in dump")
                            extra1 = extra2 = ""
                        
                        res += "{:08x} ".format(addr) +  my_hex(
                             mbytes) + " " + extra1 + " " + extra2 + "  " + tmp_res + "\n"
                        i += actual_instr_size 
                else:
                    
                    if (addr % 4) == 0:
                        instr_size = 4  # not code, not an instruction
                        if memword != 0:
                            if gap > 1:
                                res += "*** repeats for {:d} word".format(gap-1)
                                if (gap-1) > 1:
                                    res += 's'
                                res += '\n'
                            gap = 0                               
                            mbytes = cpu.read_memory(addr, 4)
                            res += "{:08x} ".format(addr)+'.word '+my_hex(mbytes)+"\n"
                        else:
                            if gap == 0:
                                res += "{:08x} ".format(addr)+'.word 0\n'
                            gap += 1
                        i += 4
                    else: 
                        instr_size = 2
                        if membytes is not None:
                            res += "{:08x} ".format(addr)+'.word '+my_hex(
                                                               membytes)+"\n"
                        i += 2 
            addr = cpu.get_next_addr(addr, instr_size)
            if addr is None:
                addr = endad+instr_size
           
        return res

# end of MSP430 dump()

    def dump_hex(memory, startad, endad, width =4):
        """ Dump memory in hex format.  """
        res = ""
        gap = 0
        CHUNK_SIZE = 16
  
        addr = startad
        while addr < endad:
            if endad - addr < CHUNK_SIZE:
                read_chunk = endad - addr
            else:
                read_chunk = CHUNK_SIZE
            membytes = cpu.read_memory(addr, read_chunk)     
            if membytes != bytearray(CHUNK_SIZE):
                if gap > 0:
                    res += "*** gap of {:d} bytes\n".format(gap)
                    gap = 0
                res += "{:08x} ".format(addr)
                for i in range(0,len(membytes),width):
                    reversed_bytes=bytearray(width)
                    if len(membytes)-i < width:
                        #print("Partial line length= {0}", len(bytes)-i)
                        k = width-1
                        for j in range(len(membytes)-1,i,-1):   #Error here
                            reversed_bytes[k] = membytes[j]
                            k = k-1
                        
                    else:
                        if width == 4:
                            reversed_bytes = (membytes[i+3],membytes[i+2],
                                              membytes[i+1],membytes[i])
                        else:
                            reversed_bytes = (membytes[i+1],membytes[i])
                    res += my_hex(reversed_bytes)+" "
                    
                res += char_repr(membytes) +"\n"
            else:
                gap += CHUNK_SIZE
            addr += CHUNK_SIZE
           
        return res
            
def do_dumps(fmt, cmd, cnt, args, width = 4):
    """ d start_address [end_address] . Dump hexadecimal and disassembly. """
    if not cpu.loaded:
        log("Load program first")
        return
    startad = "0x0"
    endad = "{:x}".format((len(cpu.memory)-1)*4)
    if cnt >= 3:
        startad = args[1]
        endad = args[2]
    elif cnt == 2:
        startad = args[1]
        endad = args[1]
    
    # TBD implement get_radix()
    startad = int(startad, 16)
    if (startad % 2) != 0:
         # messy if you don't align on a nice bdry but allow a halfword bdry
        startad = (startad//width)*width 
    endad = int(endad, 16)
    if (endad % 2) != 0:  
        # messy if you don't align on a nice bdry but allow a halfword bdry   
        endad = (endad//width)*width
        
    if fmt == 'i':
        log(dump(cpu.memory, startad, endad))
    elif fmt == 'x':
        if startad == endad:  # show at least 1 item
            endad += width        
        log(dump_hex(cpu.memory, startad, endad, width))
    
def dump_cmd(cmd, cnt, args):
    do_dumps('i', cmd, cnt, args) 
    
def dump_hex_cmd(cmd, cnt, args):
    do_dumps('x', cmd, cnt, args)
    
def dump_hex2_cmd(cmd, cnt, args):
    do_dumps('x', cmd, cnt, args, width=2)


def show_mem(cmd, cnt, args):
    """ m - internal debugger command to display memory chunks """
    if cpu is None:
        log("Load program first") 
        return
    elif len(cpu.memory) == 0:
        log("Load program first") 
        return        
    chunk = 0
    chunk_count = len(cpu.memory)
    while chunk < chunk_count:  
        chunk_start = cpu.memory[chunk][MEMADDR]
        chunk_end = chunk_start + cpu.memory[chunk][MEMSIZE] 
        log("{:d} {:#x}..{:#x}".format(chunk, chunk_start, chunk_end)) 
        chunk += 1
    if machine == "ARM":
        if len(cpu.high_memory) != 0:
            log("High memory")
            for addr in sorted(cpu.high_memory):
                log("{:#x}".format(addr))       
#---------------------------------------------------------------------------

def load_img(filename):
    """ Load from .img file into emulated memory."""
    try:
        with open(filename, "rb") as kernel:
            img_bytes = kernel.read()
            if img_bytes:
                cpu.setup_memory(img_bytes)
            else:
                log("File size is zero.")
                return
            # make it look like it is all .text
            section_addrs[0] = 'image'
            section_bytes['image'] = len(img_bytes)
        kernel.close()
        #dump(cpu.memory, 0, len(img_bytes))
        cpu.pc = 0
        if machine == "ARM": cpu.thumb_mode = False
        log("Loaded 0x{:x} bytes from {:s}".format(len(img_bytes), filename))
    except FileNotFoundError:
        log( "File <"+filename+"> not found." )  


def get_file_type(filename):
    """ Read the magic number from the first word of the file. """
    try:
        with open(filename, 'rb') as file:
            magic = file.read(4)
            #print (magic)
            file.close()
            if magic == b'\x7fELF':
                return "elf"
            elif int.from_bytes(magic[0:2], "little") == 0xc2:
                return "coff"
            else:
                return "Unexpected file type"
            
    except FileNotFoundError:
        return "File <"+filename+"> not found."                
 

def load_cmd(cmd, cnt, args):

    if len(args) == 1:
        filename = KERNEL_IMAGE
    else:
        filename = args[1]
        
    if not filename.endswith(".img"):
        if not filename.endswith(".elf"): 
            if not filename.endswith(".out"):
                log("File <{:s}> not a supported type (.img, .elf or .out)".format(
                                           filename))
                return    
     
    # check for reload
    if len(section_addrs) != 0:
        section_addrs.clear()
        section_bytes.clear()
        symdict.clear()
        labels.clear()
        das_strings.clear()

    # This should be the way to reload. Leave old memory for garbage cleanup.
    # Still not sure why I needed to specify global here.
    global cpu
    if machine == "ARM":
        cpu = ArmCpu(filename)
    elif machine == "MSP430":
        cpu = MSP430Cpu(filename)
        
    if filename.endswith(".img"):
        load_img(filename)
    elif filename.endswith(".elf"): 
        symdict.update(load_elf(filename, cpu))
    elif filename.endswith(".out"):
        filetype = get_file_type(filename)
        if filetype == "elf":
            symdict.update(load_out(filename, cpu))
        elif filetype == "coff":
            symdict.update(load_coff(filename, cpu))
        else:
            log(filetype)
            return
        
     
     
    if machine == "ARM":
        armcpu.labels = sorted(symdict.keys())
    elif machine == "MSP430":
        msp430cpu.labels = sorted(symdict.keys())
    
    
#---------------------------------------------------------------------------

def go_cmd(cmd, cnt, args):
    """ g [cnt [address]] Start execution from current location. 
        Limited to cnt instructions (default 200).
    """
    #log("g "+str(args[1:]))
    
    if cnt == 1:
        cpu.go()
        return
    elif cnt >= 2:
        try:
            instr_count = int(args[1])
        except ValueError:
            log("Expected a decimal count - g count [from_address]") 
            return
    if cnt == 2:
        cpu.go(instr_count) 
    elif cnt >= 3:
        try:
            from_address = int(args[2], base=16)       
        except ValueError:
            log("Expected a hexadecimal address - g count [from_address]")
            return
        cpu.go(instr_count, from_address) 
          
        
    
def halt_cmd(cmd, cnt, args):
    """ Halt cpu. NYI - need a break handler, eg, in GUI. """
    log("halt")   # need an interrupt handler to do this
    cpu.halt()

    
def stepo_cmd(cmd, cnt, args):
    """ o . Step over a branch and link. """
    #log("stepo"+str(args[1:]))
    cpu.set_break(cpu.pc+4)
    cpu.list_breaks()
    go_cmd(cmd, cnt, args)
    cpu.clear_break(cpu.pc+4)
    cpu.list_breaks()
    
def stepi_cmd(cmd, cnt, args):
    """ s . Step one instruction. """
    #log("stepi"+str(args[1:]))
    return cpu.stepi()
    
    
def break_cmd(cmd, cnt, args):
    """ b hex_address . Set a breakpoint at an address. """
    if cnt == 1:
        log("Break command needs an address")
        return
    log("break"+ " {:08x}".format(int(args[1], 16)))
    cpu.set_break(int(args[1],16))
    
def clear_break_cmd(cmd, cnt, args):
    """ c hex_address . Clear a breakpoint. """
    if cnt == 1:
        log("Clear break command needs an address")
        return    
    log("clear break"+" {:08x}".format(int(args[1], 16)))
    cpu.clear_break(int(args[1],16))
    
def list_cmd(cmd, cnt, args):
    """ ? b . List breakpoints. """
    if cnt > 1:
        if args[1][0] == "b":
            cpu.list_breaks()
            
def is_float_register(regname):
    if machine == "ARM":
        if (regname[0] != 's') and (regname[0] != 'S'):
            return False
        try:
            regno = int(regname[1:])
            if regno in range(32):
                return True
            else:
                return False
        except ValueError:
            return  False 
    else:
        return False
    
def fp_register(regname):
    try:
        regno = int(regname[1:])
        return regno
    except ValueError:  # should have caught problems in is_float_register
        return  0     
            
def write_cmd(cmd, cnt, args):
    """ w regname value | w address value . Modify register or memory. """
    if cnt < 3:
        log("Expect w addr val or w rn val")
    else:
        regname = args[1]
        if regname  in register_names: 
            log("Write reg " + args[1] + " value =" + args[2])
            try:
                val = int(args[2], 16)
            except:
                log("Unable to decode value " + args[2]) 
                return
            cpu.write_reg(register_names[regname], val)
            
        elif is_float_register(regname):
            log("Write float reg " + args[1] + " value =" + args[2])
            try:
                val = float(args[2])
            except:
                log("Unable to decode value " + args[2]) 
                return
            cpu.write_fp_reg(fp_register(regname), val)            
        else:
            log("Write address {:s} with value {:s}".format(args[1], args[2]))
            try:
                addr = int(args[1], 16)
            except:
                log("Unable to decode address " + args[1])
                return
            try:
                val = int(args[2], 16)
            except:
                log("Unable to decode value " + args[2])
                return
            if val.bit_length() <= 32:
                cpu.write_memory(addr, 4, val)
            else:
                cpu.write_memory(addr, 4, val&0xffffffff)
                cpu.write_memory(addr+4, 4, (val>>32)&0xffffffff)
    
if machine == "ARM":
    def show_regs():
        """ reg - shows all registers. Called from GUI. """
        res = ""
        if cpu is None: return res
        for i in range(4):
            for j in range(4):
                reg = 4*i+j
                if reg != 15:
                    res += "r{:<2d}:{:08x}  ".format(reg, 
                                                 cpu.read_reg(reg)&0xffffffff)
            res +="\n"
    
        if cpu.thumb_mode:
            res += "pc :{0:08x} apsr:{1:08x}({2:s}) epsr:{3:08x}".format(
                                        cpu.pc, cpu.apsr,
                                        visual_ccs(cpu.apsr), 
                                        cpu.epsr)
        else:
            res += "pc :{0:08x} apsr:{1:08x}({2:s})".format(
                                                        cpu.pc, 
                                                        cpu.apsr,
                                                        visual_ccs(cpu.apsr))
                
        res += "\n"   
        for i in range(16):
            for j in range(2):
                reg = 2*i+j
                valreg = cpu.read_fp_reg(reg)
                rawreg = cpu.read_raw_fp_reg(reg) &0xffffffff  
                res += "s{:<2d}:{:#f} ({:08x})  ".format(reg, valreg, rawreg)
            res += "\n"
        else:
            res += "fpscr:{:08x}({:s})".format(cpu.fpscr, 
                                               visual_ccs(cpu.fpscr))
        return res
    
        
elif machine == "MSP430":
            
    def show_regs():
        """ reg - shows all registers. Called from GUI. """
        res = ""
        if cpu is None: return res
        for i in range(4):
            for j in range(4):
                reg = 4*i+j
                res += "r{:<2d}:{:08x}  ".format(reg, 
                                                cpu.read_reg(reg)&0xffff)
            res +="\n" 
        return res 
        
def show_regs_cmd(cmd, cnt, args):
    log(show_regs())
            
#-------------------------------------------------------------------------
    
  
def reg_display_cmd(cmd, cnt, args):
    """ r regname. Display contents of a register. """ 
    if cnt < 2:
        show_regs_cmd(cmd, cnt, args)
        return
    regname = args[1]
    if regname not in register_names:
        valid_regname = False
        if machine == "ARM":
            if cpu.thumb_mode:
                if regname == 'apsr':
                    valid_regname = True
                    log("apsr:{:08x}".format(cpu.apsr))
                elif regname == 'epsr':
                    valid_regname = True
                    log("epsr:{:08x}".format(cpu.epsr))
            else:
                if regname == 'apsr':
                    valid_regname = True
                    log("apsr:{:08x}".format(cpu.apsr))        
        if not valid_regname:
            log(regname + " is not in supported list of names, "+
                str(register_names.keys()))
        return
    regno = register_names[regname]
    if machine == "ARM" and regno == 15:
        log("pc:{:08x}".format(cpu.pc))
    else:
        log("{:s}:{:08x}  ".format(regname, cpu.read_reg(regno)&0xffffffff))


def show_fp_regs_cmd(cmd, cnt, args):
    """ freg - shows all floating point registers. """

    if machine == "ARM":
        res = ""
        for i in range(16):
            for j in range(2):
                reg = 2*i+j
                valreg = cpu.read_fp_reg(reg)
                rawreg = cpu.read_raw_fp_reg(reg) &0xffffffff  
                res +="s{:<2d}:{:#f} ({:08x})  ".format(reg, valreg, rawreg)
            res += "\n"
        else:
            res += "fpscr:{:08x}".format(cpu.fpscr)
        log(res)
    else:
        log("No floating point registers")
        
def fp_reg_display_cmd(cmd, cnt, args):
    """ fr regname. Display contents of a floating point register. """ 
    if machine == "ARM":
        if cnt < 2:
            show_fp_regs_cmd(cmd, cnt, args)
            return
        regname = args[1]
        valid_regname = True
        if (regname[0] != 's') and (regname[0] != 'S'):
            if regname == 'fpscr':
                log("fpscr:{:08x}".format(cpu.fpscr))
                return
            valid_regname = False
        else:
            try:
                regno = int(regname[1:])
            except ValueError:
                log("Invalid register name <{:s}>, expect s0..s31, fpscr".format(regname))
                return
            if regno not in range(32):
                valid_regname = False
    
        if not valid_regname:
            log(regname + " is not in supported list of names (s0..s31, fpscr) ")
            return
    
        valreg = cpu.read_fp_reg(regno)
        rawreg = cpu.read_raw_fp_reg(regno) &0xffffffff          
        log("s{:<2d}:{:#f} ({:08x})  ".format(regno, valreg, rawreg))
    else:  # not "ARM"
        log("No floating point registers")


def script_cmd(cmd, cnt, args):
    """ < file starts reading commands from script file. 
        < passes control to console. 
    """
    if cnt > 1:
        cmd_file = args[1]
        start_script(cmd_file)
    else:
        stop_scripting()
        


def log_cmd(cmd, cnt, args):
    """ > file starts logging. > stops logging. """
    if cnt > 1:
        log_file = args[1]
        start_logging(log_file)
    else:
        stop_logging()
        
        
    
def help_cmd(cmd, cnt, args):
    global cmds
    for line in help_lines:
        log(line)
        
        
def get_loc(addr):
    return "{0:#x} ;{1:s}".format(addr, get_sym(addr))

def call_stack_cmd(cmd, cnt, args):
    if len(cpu.call_stack) == 0:
        log("No call stack")
    else:
        for cs in cpu.call_stack:
            log("At {:s}, called {:s}".format(get_loc(cs[0]), get_loc(cs[1])))


        
cmds = {"g":go_cmd, "h":help_cmd, "l":load_cmd, "s":stepi_cmd, "o":stepo_cmd,
        "b":break_cmd, "c":clear_break_cmd, "cs": call_stack_cmd, "d":dump_cmd,
        "dx":dump_hex_cmd, "dx2":dump_hex2_cmd,
        "freg":show_fp_regs_cmd, "fr":fp_reg_display_cmd,
        "reg":show_regs_cmd, "r":reg_display_cmd, 
        "?":list_cmd, "w":write_cmd, "<":script_cmd, ">":log_cmd,
        "m":show_mem
        } 

help_lines= ("These commands are available: ",
             str(sorted(list(cmds.keys()))),
            "l [filename]  - load: defaults to kernel.img",
            "d [start[ [end]] - dump instructions: addresses in hex",
            "dx[2] [start[ [end] - dump hex: addresses in hex. 2=2 byte units",
            "g [cnt[ addr]]  - go [count[ from_address]]",
            "s step",
            "b addr  - set break",
            "c addr  - clear break",
            "cs - show call stack",
            "r {r0 | r1 etc to r15 | sp | lr |pc}  - print register",
            "fr {s0 to s31 | fpscr - print floating register",
            "w rn val   - write to register (hex value)", 
            "w sn val   - write to float register (float value)",
            "w addr val - write to mem (4 bytes little endian,(a+3)+(a+2+(a+1)+(a)",
            "reg        - all regs",
            "freg       - floating point regs",
            "? b        - list breaks",
            "< filename - read commands from file",
            "> filename - log output to file, no filename - stop logging",
            "h          - help")
    

#---------------------------------------------------------------------------

def emulator(filename):
    """ Main program of command line emulator. """

    while True:
        log("dbg>", end="")
        if scripting_enabled():
            cmd = from_script()
            if len(cmd) == 0:
                continue
        else:
            cmd = input()
        if logging_enabled():
            log(cmd, echo_cmd = False)
        if cmd:
            cmd = cmd.strip()
            if cmd[0] == "q":
                break
            
            args = cmd.split()
            if args[0] in cmds:
                cmds[args[0]](cmd, len(args), args)
            elif args[0][0] == "r":
                cmds["r"](cmd, len(args), args)
            else:
                log("Unsupported command. Try one of " + 
                         str(list(cmds.keys())))
    log("Exiting")
    return ""


if __name__ == '__main__': 
    filename=os.path.join(os.getcwd(),KERNEL_IMAGE)
    res = ""
    #res = "Filename is <"+filename+">\n" 
    print("Command line debugger/emulator for {:s}.\nType h for commands\n".format(machine))
    if machine == "ARM":
        cpu = ArmCpu(filename)
    elif machine == "MSP430":
        cpu = MSP430Cpu(filename)
        
    res += emulator(filename)
 