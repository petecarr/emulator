import math
from math import sqrt
import array

# Path hack for access to utilities and siblings.
import sys, os
sys.path.insert(0, os.path.abspath('..'))
   
from utilities  import  bit_fields, logging, unchecked_conversion
from utilities.bit_fields import *
from utilities.logging import *

from arm import  armcpu
from arm.armcpu import *

from arm import disass
from arm.disass import disass


# Maximum number of instructions to let the go command emulate. 
MAX_INSTRS = 200

#-------------------------------------------------------------------------------


class Code_Error(Exception):
    def __init__(self, value):
        self.value = value
      
    def __str__(self):
        return self.value
   
bna = "Branch not allowed in if-then block"
cpsna = "cps not allowed in if-then block"
nestifthen = "Nested if-then block; result is unpredictable"


def log_unpredictable(word):
    log("Unpredictable instruction {:#x}".format(word))
    

def log_undefined():    
    log("Undefined instruction")

#-----------------------------------------------------------------
    
class ArmCpu:

    
    def __init__(self, filename):
        self.thumb_mode = False
        #self.memory_words = 0
        self.memory_bytes = 0
        self.memory = []
        self.high_memory = {}
        self.loaded = False
        
        self.filename = filename
        self.format = "img"
         
        self.registers = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
        self.pc = 0  # note separate, only 15 in self.registers
        #self.cpsr = MODE_USER   # not armv7-M
        self.apsr = 0
        self.epsr = 0
        self.setflags = False
        self.fp_registers = [0 for x in range (32)]
        self.fpscr = 0
 
        self.itstate = 0
        
        self.call_stack = []
   
        self.break_count = 0
        self.breaks = []

    def get_last_address(self):
        chunk = 0
        chunk_count = len(self.memory)
        while chunk < chunk_count:
            chunk_start = self.memory[chunk][MEMADDR]
            chunk_end = chunk_start + self.memory[chunk][MEMSIZE] 
            chunk += 1
        #print("Last memory chunk loaded #{:d}, start={:x}, end = {:x}".format(
        #      chunk, chunk_start, chunk_end))        
        return chunk_end
     
    def get_next_addr(self, addr, instr_size):
        chunk = 0
        chunk_count = len(self.memory)
        next_addr = addr+instr_size
        while chunk < chunk_count:  
            chunk_start = self.memory[chunk][MEMADDR]
            chunk_end = chunk_start + self.memory[chunk][MEMSIZE] 
            if (next_addr >= chunk_start) and (next_addr < chunk_end):
                return next_addr
            elif next_addr < chunk_start:
                return self.memory[chunk][MEMADDR]
            # else try the next chunk
            chunk+= 1
        """
        while chunk < chunk_count:  
            chunk_start = self.memory[chunk][MEMADDR]
            chunk_end = chunk_start + self.memory[chunk][MEMSIZE] 
            if (next_addr >= chunk_start) and (next_addr < chunk_end):
                return next_addr
            else:
                chunk+= 1
                if chunk < chunk_count:
                    chunk_start = self.memory[chunk][MEMADDR]
                    chunk_end = chunk_start + self.memory[chunk][MEMSIZE] 
                    if (next_addr >= chunk_start) and (next_addr < chunk_end):
                        return next_addr
                    else:
                        return self.memory[chunk][MEMADDR]
                        """
        return None    
        
        
    def setup_memory(self, membytes, addr = 0):
        # Assume no overlaps, edits. We either append to an existing chunk
        # or add a new chunk leaving a gap.
        loaded = False
        byte_count = len(membytes) # +len(membytes)%4  no - must leave a gap if there is one
        chunk_count = len(self.memory)
        chunk = 0
        while not loaded and (chunk < chunk_count):
            chunk_start = self.memory[chunk][MEMADDR]
            chunk_end = chunk_start + self.memory[chunk][MEMSIZE]
            if addr < chunk_start:
                if (addr + byte_count) == chunk_start:  # extend chunk downwards
                    # TBD check with msp430 and keep in sync
                    tmp = self.memory[chunk][MEMVALS]
                    self.memory[chunk][MEMVALS] = bytearray(membytes) +tmp
                    self.memory[chunk][MEMADDR] = addr
                    self.memory[chunk][MEMSIZE] += byte_count                    
                else:                
                    self.memory.insert(chunk, [addr, byte_count, bytearray(membytes)])
                loaded = True
            elif addr == chunk_end:
                # bytearrays are mutable, bytes aren't
                self.memory[chunk][MEMVALS] += bytearray(membytes)
                self.memory[chunk][MEMSIZE] += byte_count
                loaded = True
            chunk += 1
        
        if not loaded:
            # bytearrays are mutable, bytes aren't
            self.memory.append([addr, byte_count, bytearray(membytes)])

        self.memory_bytes = self.get_last_address()
        self.loaded = True
        

    def read_reg(self, regno):
        """ Read from an ARM core register """
        if regno == 15: return self.pc
        return self.registers[regno]
    
    def write_reg(self, regno, val):
        """ Write to an ARM core register """
        if regno == 15: 
            self.pc = val  # OOD set_field(self.pc, get_field(val, 2, 27), 2, 27)  
            return
        self.registers[regno] = val
        
    def reg_list(self, word):
        """ Return a register list of the form [rx,ry,..] according to 
            bits 0..15
        """
        count = 0
        regs = []
        for regno in range(16):
            if testBit(word, regno):
                count += 1
                regs.append(regno) 
            
        return count, regs    
    
    #--------------------------------------------------------------------------
    
    # Floats appear in registers as integers which can be interpreted when 
    # output in hex as ieee754 format, but are dealt with everywhere as floats.
    # Avoiding having to implement float arithmetic as specified in the manual.
    # (for now)
    # Use raw equivalents to put FPZero, FPNan results into reg.
        
    def read_fp_reg(self, regno):
        """ Read a floating point register converting the raw value to real """
        contents = self.fp_registers[regno]
        return unchecked_conversion.convert_int_to_float(contents)
    
    def read_raw_fp_reg(self, regno):
        """ Read a floating point register as it is stored """
        return self.fp_registers[regno]
    
    def write_fp_reg(self, regno, val):
        """ Convert a real value to floating point format and write a register """
        new_contents = unchecked_conversion.convert_float_to_int(val)
        self.fp_registers[regno] = new_contents 
        
    def write_raw_fp_reg(self, regno, val):
        """ Write a floating point value to a register with no conversion """
        self.fp_registers[regno] = val
        
    def read_dfp_reg(self, regno):
        """ Double float register read => real value """
        reg=regno*2
        contents1 = self.fp_registers[reg]
        contents2 = self.fp_registers[reg+1]
        contents = (contents1 << 32) | contents2
        return unchecked_conversion.convert_int_to_float(contents)
    
    def read_raw_dfp_reg(self, regno):
        """ Double float register read raw """
        reg=regno*2
        contents1 = self.fp_registers[reg]
        contents2 = self.fp_registers[reg+1]
        return (contents1 << 32) | contents2&0xffffffff
      
    def write_dfp_reg(self, regno, val):
        """ Real => double float register write """
        reg=regno*2
        new_contents1 = unchecked_conversion.convert_float_to_int(val)
        new_contents2 = unchecked_conversion.convert_float_to_int(val)
        self.fp_registers[reg] = new_contents1 >> 32 
        self.fp_registers[reg+1] = new_contents2 & 0xffffffff
        
    def write_raw_dfp_reg(self, regno, val1, val2):
        """ Raw double float to double float register """
        reg=regno*2
        self.fp_registers[reg]   = val1
        self.fp_registers[reg+1] = val2
     
     
    #----------------------------------------------------------------------
    
    def set_break(self, addr):
        """ Set a break point (NB software breakpoint, not a bkpt instruction) """
        if not self.loaded:
            log("Load program first")
            return
        if  addr > self.memory_bytes or addr < 0:
            log ("Invalid break address {:08x}".format(addr))
            return
        if addr in  self.breaks:
            log("Break already set at {:08x}".format(addr))
            return
        self.breaks.append(addr)
        self.break_count +=1 
        self.breaks.sort()
  
    
    def clear_break(self, addr):
        """ Clear a breakpoint """
        if not self.loaded:
            log("Load program first") 
            return False
        if  addr > self.memory_bytes or addr < 0:
            log ("Invalid break address {:08x}".format(addr))
            return False
        if addr  not in  self.breaks:
            log("No break set at {:08x}".format(addr))
            return False
        self.breaks.remove(addr)
        self.break_count -=1
        return True
        
    def list_breaks(self):
        """ List the breakpoints """
        if self.break_count == 0:
            log("No breaks set")
        else:
            for addr in self.breaks:
                log("Break at {:08x}".format(addr))
  

    def read_high_memory(self, startaddr, count):
        """ Attempts to simulate high memory, eg. I/O locations """
        log("Reading {:d} bytes from high address {:08x}".format(count,
                                                                 startaddr))
        val = 0
        if not startaddr in self.high_memory:  #TBD
           
            log("Enter the hex value expected in debug I/O window \n(use '-' if needed) >", end="")
            valid_input = False
            while not valid_input:
                result = input()
                # A work in progress. Can't put this in logging.
                #result = prompt_for_value("Enter the hex value expected in debug I/O window \n(use '-' if needed) >")
                try:
                    val = int(result, 16)
                    valid_input = True
                    log(result, end = "\n")
                except ValueError:
                    log("\nInvalid hex number {:s}, try again".format(result))
            
            if not self.thumb_mode:
                if timer.is_timer(startaddr):
                    timer.set_timer_value(startaddr, val)
                elif video.is_mbox(startaddr):
                    video.set_mbox_value(startaddr, val)
            else:
                if gpio.is_PLL(startaddr):
                    self.high_memory[startaddr] = gpio.setup_PLL(
                                          startaddr).to_bytes(4, 'little')
                    return self.high_memory[startaddr]
                
       
        if not self.thumb_mode:
            if gpio.is_gpio(startaddr):
                log(gpio.gpio_function(startaddr, val)) 
            elif timer.is_timer(startaddr):
                val = timer.get_timer_value(startaddr)
                log("Timer value is {:d}".format(val))
            elif video.is_mbox(startaddr):
                val = video.get_mbox_value(startaddr)
                log("Video mailbox addressed {:x}: {:x}".format(startaddr, val))
            else:
                val = 0
        
        try:                            
            valbytes = val.to_bytes(4, 'little', signed = True)
        except OverflowError:
            log("Error: integer too big to convert")
            valbytes = 0
        if not startaddr in self.high_memory:
            self.high_memory[startaddr] = valbytes  # TBD
        return valbytes     
        
    def read_memory(self, startaddr, count):
        """ Read memory called from instruction decoding not dump command """
        if not self.loaded:
            log("Load program first")
            return -1
 
        chunk = 0
        while chunk < len(self.memory):
            chunk_start = self.memory[chunk][MEMADDR]
            chunk_end = chunk_start + self.memory[chunk][MEMSIZE]
            if startaddr+count < chunk_start: return None
            if chunk_start <= startaddr < chunk_end:
                offset = startaddr - chunk_start
                return self.memory[chunk][MEMVALS][offset:offset+count]
            chunk += 1 
            
        if startaddr > address_mask:
            if not self.thumb_mode:
                if timer.is_timer(startaddr):
                    val = timer.get_timer_value(startaddr)
                elif video.is_mbox(startaddr):
                    val = video.get_mbox_value(startaddr)
                else:
                    val = 0
                return val.to_bytes(4, 'little')
            else:
                if gpio.is_PLL(startaddr):
                    self.high_memory[startaddr] = gpio.setup_PLL(
                                          startaddr).to_bytes(4, 'little')
                    return self.high_memory[startaddr]            
            print("Enter high memory hex value here > ", end = "")
            return self.read_high_memory(startaddr, count)        
        #log("Address not found <{:x}>".format(startaddr))
        return None
    
    def read_memory_int(self, startaddr, count, signed = False):
        mbytes = self.read_memory(startaddr, count)
        if mbytes is None: return 0
        if mbytes == -1: return 0
        return int.from_bytes(mbytes[0:count], 'little', signed = signed)
    
    def write_high_memory(self, startaddr, count, values):
        """ Emulate I/O writes. """
        """ TBD should we handle counts > 1 """
        log("Writing {:d} bytes to high address {:08x}".format(count,
                                                               startaddr))
       
        if not self.thumb_mode:  # raspberry Pi
            if gpio.is_gpio(startaddr):
                log(gpio.gpio_function(startaddr, values))
            elif timer.is_timer(startaddr):
                timer.set_timer_value(startaddr, values)
                log("Timer value is {:x}".format(
                                        timer.get_timer_value(startaddr)))  
                # TBD timer stuff is in 2 places!
            elif video.is_mbox(startaddr):
                video.set_mbox_value(startaddr, values)
                log("Video mailbox addressed {:x}: {:x}".format(startaddr, 
                                        video.get_mbox_value(startaddr)))
            
                
        #allocate high memory in a dictionary as needed
        if not startaddr in self.high_memory:
            self.high_memory[startaddr] = values
            
        return 

    def write_memory(self, startaddr, count, values):
        """ Write to memory. """
        if not self.loaded:
            log("Load program first")
            return -1
        if count > 8 :
            log("Sorry, only counts of <= 8 supported in write memory")
            return 0
        if count == 4:
            values &= 0xffffffff
        elif count == 8:
            values &= 0xffffffffffffffff  # TBD still a bug here
        
        chunk = 0
        while chunk < len(self.memory):
            chunk_start = self.memory[chunk][MEMADDR]
            chunk_end = chunk_start + self.memory[chunk][MEMSIZE]
            if chunk_start <= startaddr < chunk_end:
                offset = startaddr - chunk_start
                #try:
                #tmp_bytes = [0,0,0,0,0,0,0,0]
                tmp_bytes = bytearray(values.to_bytes(count, 'little'))
            
                self.memory[chunk][MEMVALS][offset:offset+count] = tmp_bytes[0:count]
                return
                #except:
                    # blows up when I do a push(r4, lr) in example01
                    # do I need to initialize the stack? Why does it work
                    # elsewhere?
                    # because: bytearrays are mutable, bytes aren't.
                    #log("problem assigning to memory location {:x}".format(offset))
                    
            chunk += 1 
            
        
        # didn't find a match
        if startaddr > HIGH_MEMORY_START:
            self.write_high_memory(startaddr, count, values)
            return
        else:
            membytes = values.to_bytes(count, 'little')
            self.setup_memory(membytes, startaddr)
    
    def stepi(self):
        """ Advance the emulation by a single instruction """
        if not self.loaded:
            log("Load program first")
            return
        # This is the only place that emulate is called
        # Keep it that way or move the following into emulate.

        instr = self.read_memory_int((self.pc & address_mask), 4)
        return self.emulate(instr)
    
    def stepo(self):
        """ As stepi but go over the next instruction, assumed to be a bl """
        if not self.loaded:
            log("Load program first")
            return 
        dest = self.pc+4
        self.set_break(dest)
        self.list_breaks()
        self.go(self.pc)
        self.clear_break(dest)
        #self.list_breaks()
        return dest
        
    def go(self, addr):
        """ Let it go for MAX_INSTRS instructions or until a break is hit """ 
        # Note: the GUI interface implements its own version of go with a
        # different MAX_INSTRS.
        try:
            self.pc = addr
            while True:
                for i in range(MAX_INSTRS):
                    self.stepi()
                    program_counter = self.pc & address_mask
                    if program_counter in self.breaks:
                        log("Breakpoint hit at {:08x}".format(program_counter))
                        return
                msg = "{:d} instructions executed, continue (y/n)? >".format(
                                                                MAX_INSTRS)
                log(msg)
                print(msg, end="")
                ans = input()
                if ans[0] == 'n':
                    return
                    
        except:
            log("Caught exception")
    
    def halt(self):
        pass
        
    #--------------- 16 bit thumb instructions-------------------------------
    
    def et16_shift_etc(self, word):
        setflags = not self.in_it_block()
        # rewrite needed
        opcode = get_field(word, 11, 13)
        if opcode <= 2:
            # lsl, lsr, asr imm
            rd = get_field(word, 0, 2)
            rm = get_field(word, 3, 5)
            val = self.read_reg(rm)
            shift_count = get_field(word, 6, 10)
            if (opcode > 0) and (shift_count == 0):
                shift_count = 32
            (result, self.apsr) = Shift_C(opcode, val, shift_count, self.apsr)
            self.write_reg(rd, result)
        elif opcode == 3:
            # add and subtract register or 3 bit imm
            rd = get_field(word, 0, 2)
            rn = get_field(word, 3, 5)
            imm3 = rm = get_field(word, 6, 8)
            op1 = get_field(word, 9, 10)
            valn = self.read_reg(rn)
            valm = self.read_reg(rm)
            if op1 == 0:
                result = valn+valm
            elif op1 == 1:
                result = valn-valm
            elif op1 == 2:
                result = valn+imm3
            elif op1 == 3:
                result = valn-imm3
            # consider using AddWithCarry to get accurate condition codes   
            #if testBit(self.apsr, CBIT):
            #    val += 1            
            self.write_reg(rd, result)
            if setflags:
                self.apsr = arith_cond(result, self.apsr, testBit(self.apsr, CBIT))    
        elif opcode == 4: 
            # move
            result = imm8 = get_field(word, 0, 7)
            rd = get_field(word, 8, 10)
            self.write_reg(rd, imm8)
            if setflags:
                self.apsr = logical_cond(imm8, self.apsr)
        elif opcode == 5:
            # compare
            imm8 = get_field(word, 0, 7)
            rn = get_field(word, 8, 10)
            result = self.read_reg(rn) -imm8
             # TBD use AddWithCarry to get accurate condition codes
            self.apsr = arith_cond(result, self.apsr, testBit(self.apsr, CBIT))
        elif opcode >= 6:
            # add, sub 8-bit immediate
            rdn = get_field(word, 8, 10)
            imm8 = get_field(word, 0, 7)
            valdn = self.read_reg(rdn)
            # TBD use AddWithCarry to get accurate condition codes
            if opcode == 6:
                result = valdn + imm8
            else:
                result = valdn - imm8
            self.write_reg(rdn, result)
            if setflags:
                self.apsr = arith_cond(result, self.apsr, testBit(self.apsr, CBIT))
        log_result(result, self.apsr)
        self.pc += 2
        return self.pc
    
    def et16_data_processing(self, word):
        setflags = not self.in_it_block()
        rdn = get_field(word, 0, 2)
        valdn = self.read_reg(rdn)
        rm = get_field(word, 3, 5)
        valm = self.read_reg(rm)
        opcode = get_field(word, 6, 9)
        carry = get_field(self.apsr, CBIT, CBIT)
        testflags = setflags # local copy
        write_rdn = True
        if opcode == 0: # and
            valdn = valdn & valm
        elif opcode == 1: #eor
            valdn = valdn ^ valm
        elif opcode == 2:  # lsl
            valm &=0xff  # you would have thought that 0:31 would be the range
            valdn = valdn << valm
        elif opcode == 3:  # lsr
            valm &=0xff
            valdn = valdn >> valm
        elif opcode == 4:  # asr
            valm &=0xff
            if valdn >=0:
                valdn >>= valm
            else:
                valdn >>= valm
                valdn = extend_sign(valdn, 31-valm)
        elif opcode == 5: # adc
            valdn, psr = AddWithCarry(valdn, valm, self.apsr)
            if setflags:
                self.apsr |= psr
                self.apsr = logical_cond(valdn, self.apsr) # handle Z and N bits  
        elif opcode == 6: # sbc
            valdn, psr = AddWithCarry(valdn, ~valm, self.apsr)
            if setflags:
                self.apsr |= psr
                self.apsr = logical_cond(valdn, self.apsr) # handle Z and N bits
        elif opcode == 7: # ror
            valm &= 0xff
            if valm == 0: 
                carry = testBit(self.apsr, CBIT)
            else:
                retval = valdn
                retval  >>= valm
                tmp = valdn << (32-valm)
                valdn = retval | tmp 
                carry = 0 # what?
        elif opcode == 8: # tst
            valdn = valdn & valm
            write_rdn = False
            # must test
            testflags = True
        elif opcode == 9:  # rsb
            valdn = -valm
        elif opcode == 10: # cmp
            valdn = valdn - valm
            write_rdn = False
            testflags = True          
        elif opcode == 11: # cmn
            valdn = valdn + valm
            write_rdn = False
            testflags = True
        elif opcode == 12: # orr
            valdn = valdn | valm
        elif opcode == 13: # mul
            valdn = valdn*valm
        elif opcode == 14: # bic
            valdn = valdn & ~valm
        elif opcode == 15: # mvn
            valdn = ~valm
  
        if testflags:  # more - carry
            self.apsr = logical_cond(valdn, self.apsr)
            log_result(valdn, self.apsr)
        else:
            log_result(valdn)
        if write_rdn:
            self.write_reg(rdn, valdn)

        self.pc += 2
        return self.pc
    
    def et16_special_data_and_branch(self, word):
        """ high register operations branch/exchange """
        # the T2 encoding with opcode bits 10-15 == 0x11
        setflags = not self.in_it_block()
        opcode = get_field(word, 8, 9)
        msbd = get_field(word, 7, 7) << 3
        rm = get_field(word, 3, 6)
        valrm = self.read_reg(rm)
        rdn = get_field(word, 0, 2) | msbd
        testflags = setflags
        result = 0
        if opcode == 0:
            # opcode = "add"
            result = self.read_reg(rdn)
            result += valrm
            self.write_reg(rdn, result)
            # no set flags
        elif opcode == 1:
            # opcode = "cmp"
            val2 = valrm
            val1 = self.read_reg(rdn)
            result = val1 - val2
    
            self.apsr = arith_cond(result, self.apsr, testBit(self.apsr, CBIT))
            testflags = True
        elif opcode == 2:
            if rm == 8  and rdn == 8: 
                log("nop (mov r8, r8)")
                self.pc += 2
                return self.pc
            elif get_field(word, 6, 9) == 4:
                log_unpredictable(word)
                self.pc += 2
                return self.pc
            else:
                # opcode= "mov"
                result = valrm
                self.write_reg(rdn, result)
        elif opcode == 3:
            if self.in_it_block(): raise Code_Error(bna) 
            # what about last instr in it_block?
            if msbd == 0:
                # opcode = "bx"
                # We really need some sort of way to distinguish between 
                # armv7-A and armv7-M processors. For now it's probably going to
                # be Thumb mode = M and ARM mode = A
                if testBit(valrm, 0):
                    dest = valrm & address_mask
                    epsr = self.epsr
                    if not testBit(epsr, TBIT):
                        log("Attempt to enter thumb mode - how come?(armv7-M)")
                else:
                    dest = valrm
                    epsr = self.epsr
                    if testBit(epsr, TBIT):
                        log("Attempt to exit thumb mode- how come (armv7-M)")
                if len(self.call_stack) > 0:
                    self.call_stack.pop()
                self.pc = dest
                return self.pc
            else:
                # opcode = "blx"
                dest = valrm | 1
                setBit(self.epsr, TBIT)
                self.write_reg(register_names["lr"], self.pc+2)
                self.pc = dest
                if len(self.call_stack) > 0:
                    self.call_stack.pop()                
                return self.pc
        if testflags:
            log_result(result, self.apsr)
        else:
            log_result(result)
        self.pc += 2
        return self.pc
    
    def et16_load_litpool(self, word):
        # ldr literal
        imm8 = get_field(word, 0, 7) << 2
        imm8 += (self.pc//4)*4 + 4
        rt = get_field(word, 8, 10)
        self.write_reg(rt, imm8)
        log_result(imm8)
        self.pc += 2
        return self.pc
    
    def et16_load(self, word):
        opa = get_field(word, 12, 15)
        opb = get_field(word, 9, 11)
        rn = get_field(word, 3, 5)
        rt = get_field(word, 0, 2)
        if opa >= 6: # imm
            if opa == 9:
                imm8 = get_field(word, 0, 7) <<2
                rt = get_field(word, 8, 9)
                rn = SP
                addr = self.read_reg(rn) + imm8    
            else:
                imm5 = get_field(word, 6, 10) << 2
                addr = self.read_reg(rn) + imm5
            if opa == 6:
                siz = 4
            elif opa == 7:
                siz = 1
            elif opa == 8:
                siz = 2
            elif opa == 9: 
                siz = 4
            if (opb & 4) == 4:  #load
                data = self.read_memory_int(addr, siz, signed = True)
                self.write_reg(rt, data)
            else: # store
                data = self.read_reg(rt)
                self.write_memory(addr, siz, data)
        else:  # reg
            rm = get_field(word, 6, 8)
            addr = self.read_reg(rn) + self.read_reg(rm)
            if opb < 3: # store
                data = self.read_reg(rt)
                if opb == 0: #str
                    siz = 4
                elif opb == 1: #strh
                    siz = 2
                elif opb == 2:  # strb
                    siz = 1
                self.write_memory(addr, siz, data)
            else: # load
                if opb == 3: # ldrsb
                    data = self.read_memory_int(addr, 1)
                    data = extend_sign(data, 8)
                elif opb == 4:  # ldr
                    data = self.read_memory_int(addr, 4, signed = True)
                elif opb == 5: # ldrh
                    data = self.read_memory_int(addr, 2)
                elif opb == 6: # ldrb
                    data = self.read_memory_int(addr, 1)
                elif opb == 7: # ldrsh
                    data = self.read_memory_int(addr, 2)
                    data = extend_sign(data, 16)
                self.write_reg(rt, data)
        log_result(data)
        self.pc += 2
        return self.pc
    
    def et16_adr(self, word):
        rd = get_field(word, 8, 10)
        imm8 = get_field(word, 0, 7) << 2
        dest = alignPC(self.pc, 4) + imm8
        self.write_reg(rd, dest)
        log_result(dest)
        self.pc += 2
        return self.pc
    
    def et16_add_sp(self, word):
        # T1 encoding form, add rd, sp, #imm8
        imm8 = get_field(word, 0, 7) << 2
        valsp = self.read_reg(SP)
        rd = get_field(word, 8, 10)
        result = valsp+imm8
        self.write_reg(rd, result)
        log_result(result)
        self.pc += 2
        return self.pc    
   
    def et16_add_sp_imm(self, word):
        # T2 encoding form, add sp, sp, #imm7
        imm7 = get_field(word, 0, 6) << 2
        valsp = self.read_reg(SP)
        if testBit(word, 7):
            result = valsp-imm7
        else:
            result = valsp+imm7
        self.write_reg(SP, result)
        log_result(result)
        self.pc += 2
        return self.pc
    
    #----- Based on the pseudocode in the ARM manuals -------
    
    def in_it_block(self):    
        return (self.itstate & 0b1111) != 0
    
    def last_in_it_block(self):
        return (self.itstate &0b1111) == 0b1000  
    
    def it_advance(self):
        if (self.itstate & 0b111) == 0:
            self.itstate = 0
        else:
            mask = 0b11111
            low_bits = self.itstate & mask
            low_bits <<= 1 
            low_bits &= mask
            self.itstate &= ~mask
            self.itstate |= low_bits
            
    
    """
    def get_next_pc(self, word, next_pc):
        # branches not allowed in if-then block unless last instruction
        if (get_field(word, 29, 31) == 7) and (
            get_field(word, 27, 28) != 0):   # avoid the 16 bit branch
            next_pc += 4
        else:
            next_pc += 2  
        return next_pc
    """ 
    
    """ Kept here for reference about how IT works
    Examples from ARM Cortex-M manual
    ITTEE  EQ           ; Next 4 instructions are conditional
    MOVEQ  R0, R1       ; Conditional move
    ADDEQ  R2, R2, #10  ; Conditional add
    ANDNE  R3, R3, #1   ; Conditional AND
    BNE.W  dloop        ; Branch instruction can only be used in the last
                        ; instruction of an IT block 
                        
    IT     GT           ; IT block with only one conditional instruction    
    ADDGT  R1, R1, #1   ; Increment R1 conditionally
    
    CMP    R0, #9       ; Convert R0 hex value (0 to 15) into ASCII 
                        ; ('0'-'9', 'A'-'F')
    ITE    GT           ; Next 2 instructions are conditional
    ADDGT  R1, R0, #55  ; Convert 0xA -> 'A'
    ADDLE  R1, R0, #48  ; Convert 0x0 -> '0'
    
    ITTE   NE           ; Next 3 instructions are conditional
    ANDNE  R0, R0, R1   ; ANDNE does not update condition flags
    ADDSNE R2, R2, #1   ; ADDSNE updates condition flags
    MOVEQ  R2, R3       ; Conditional move

    """
    
    
    def et16_misc_ifthen(self, word):
        first_cond = opa = get_field(word, 4, 7)
        mask_field = opb = get_field(word, 0, 3)
        if mask_field != 0:
            if self.in_it_block(): 
                raise Code_Error(nestifthen)

            log("it{:s} {:s}".format(get_It_suffices(first_cond&1,
                                                     mask_field),
                                     cond(first_cond)))
            self.itstate = word & 0xff
        elif opa == 0:
            """ nop 0xbf00 """ 
        elif opa == 1:
            log('yield')
        elif opa == 2:
            log('wfe')
        elif opa == 3:
            log('wfi')
        elif opa == 4:
            log('sev')
        else:
            log('unexpected if-then')
        self.pc += 2
        return self.pc
    
    def et16_misc_extend(self, word):
        rm = get_field(word, 3, 5)
        rd = get_field(word, 0, 2)
        subopcode = get_field(word, 6, 7)
        if subopcode == 0:
            siz = 2
            signed = True
        elif subopcode == 1:
            siz = 1
            signed = True
        elif subopcode == 2:
            siz = 2
            signed = False
        elif subopcode == 3:
            siz = 1
            signed = False 
        valrm = self.read_reg(rm)
        if siz == 1:
            valrm &= 0xff
            if signed:
                valrm = extend_sign(valrm, 8)
        elif siz == 2:
            valrm &= 0xffff
            if signed:
                valrm = extend_sign(valrm, 16) 
                
        self.write_reg(rd, valrm)
        log_result(valrm)
        self.pc += 2
        return self.pc
    
    def et16_misc_rev(self, word):
        rm = get_field(word, 3, 5)
        rd = get_field(word, 0, 2)
        op = get_field(word, 6, 7)
        valrm = self.read_reg(rm)
        if op == 0: # byte reverse
            result = ((valrm & 0xff) << 24) | ((valrm & 0xff00) << 8) | (
                      (valrm & 0xff0000) >> 8) | (valrm >> 24)
        elif op == 1:  # hw reverse
            result = ((valrm & 0xff0000) << 8) | ((valrm & 0xff000000) >> 8) | (
                      (valrm & 0xff00) >> 8) | (( valrm &0xff) << 8)
        elif op == 3: # sign extend rev bytes in lower hw
            result = ((valrm & 0xff00) >> 8) | (( valrm &0xff) << 8)
            result = extend_sign(result, 16)
        else:
            pass # don't know
        self.write_reg(rd, result)
        log_result(result)
        self.pc += 2
        return self.pc
    
    def et16_misc_cps(self, word):
        log("cps, (Change Processor State) instruction encountered")
        if self.in_it_block(): raise Code_Error(cpsna)
        if not testBit(word, 4):
            log("Would enable interrupts")
        else:
            log("Would disable interrupts")
        if testBit(word, 1):
            log("Would raise priority to 0")
        if testBit(word, 0):
            log("Would raise priority to -1 (hard fault)")
        self.pc += 2
        return self.pc        
        
    
    def et16_misc(self, word):
        """ Misc 16-bit instrs. bits 12-15 == 0xb """
        opcode = get_field(word, 5, 11)
        op1 = get_field(word, 8, 11)
        if op1 == 0xf:
            self.pc = self.et16_misc_ifthen(word) 
        elif op1 == 0xe:
            log("{:#x} bkpt {:#x} instruction encountered".format(
                                         self.pc, get_field(word, 0, 7)))
            # we could call self.set_break here if the go command needs it
            # then we pretend we set it.
            self.pc += 2
        elif (op1 == 0xc) or (op1 == 0xd): #pop
            rlist = (get_field(word, 8,8) << 15) | get_field(word, 0, 7)
            count, regs = self.reg_list(rlist)
            if count == 0:
                log("No registers specified in pop, ignoring")
                self.pc += 2
                return  self.pc           
            offset = count*4
            next_item = 4
            base_val = self.read_reg(SP)
            write_back_val = base_val + offset
               
            return_address = self.pc +2   # usually, unless we pop it out of regs
            for reg in regs:
                val = self.read_memory_int(base_val, 4, signed = True)
                self.write_reg(reg, val)
                if reg == 15:
                    return_address = val
                log("popped = {:08x} from {:08x} into {:s}".format(val, 
                                                                   base_val,
                                                                   get_reg(reg)))
                base_val += next_item      
                
            self.write_reg(SP, write_back_val)                
            #self.write_reg(PC, return_address)
            self.pc = return_address
            return self.pc
        
        elif (op1 == 1) or (op1 == 3) or (op1 == 9) or (op1 == 0xb): # cb
            if self.in_it_block(): raise Code_Error(bna)
            nonzero =  get_field(word, 11, 11)
            rn = get_field(word, 0, 2)
            valrn = self.read_reg(rn)
            rniszero = (valrn == 0)
            if nonzero ^ rniszero:
                imm32 = (get_field(word, 9, 9) << 7) | (get_field(word, 3, 7) << 1)
                dest = self.pc + 2 + imm32
            else:
                dest = self.pc + 2
            log_result(dest)
            self.pc = dest
            return self.pc            
        elif op1 == 2:
            self.pc = self.et16_misc_extend(word)
        elif (op1 == 4) or (op1 == 5):  # push
            rlist = (get_field(word, 8,8) << 14) | get_field(word, 0, 7)
            count, regs = self.reg_list(rlist)
            if count == 0:
                log("No registers specified in push, ignoring")
                self.pc += 2
                return  self.pc           
            offset = count*4
            next_item = 4
            base_val = self.read_reg(SP) - offset
            write_back_val = base_val
               
            for reg in regs:
                val = self.read_reg(reg)
                self.write_memory(base_val, 4, val)
                log("pushed = {:08x} from {:s} to {:08x}".format(val, 
                                                                 get_reg(reg),
                                                                 base_val))
                base_val += next_item      
                
            self.write_reg(SP, write_back_val)
            self.pc += 2
        elif op1 == 0xa:
            self.pc = self.et16_misc_rev(word)
        elif (opcode & 0x7c) == 4: # actually sub sp, #imm
            self.pc = self.et16_add_sp_imm(word) 
        elif (opcode & 0x7c) == 0:  # add sp, #imm
            self.pc = self.et16_add_sp_imm(word)
        elif opcode == 0x33:
            self.pc = self.et16_misc_cps(word)        
        return self.pc
    
    def et16_ldm_stm(self, word):
        rn = get_field(word, 8, 10)
        st = not testBit(word, 11)
        r_list = get_field(word, 0, 7)
        count, regs = self.reg_list(r_list)
        if count == 0:
            log("No registers specified in load/store multiple, ignoring")
            self.pc += 2
            return self.pc
        offset = count*4
        next_item = 4
        base_val = self.read_reg(rn)
        write_back_val = base_val+offset

        for reg in regs:
            if not st:
                val = self.read_memory_int(base_val, 4, signed = True)
                self.write_reg(reg, val)
                log("loaded = {:08x} from {:08x} into {:s}".format(
                                           val, base_val, get_reg(reg)))
            else:
                val = self.read_reg(reg)
                self.write_memory(base_val, 4, val)
                log("stored = {:08x} from {:s} into {:08x}".format(
                                          val, get_reg(reg), base_val))
            base_val += next_item      
        if rn not in regs:
            self.write_reg(rn, write_back_val)         
        self.pc += 2
        return self.pc
    
    
    def et16_bc_svc(self, word):
        opcode = get_field(word, 8, 11)
        if opcode == 14:
            log_undefined()
        elif opcode == 15:
            log("svc instruction encountered at {:x}".format(self.pc))
        else:
            return self.et16_bc(word)
        self.pc += 2
        return self.pc
    
    def et16_bc(self, word):
        if self.in_it_block() and not self.last_in_it_block(): 
            raise Code_Error(bna)
        cond_code = get_field(word, 8, 11)
        imm8 = get_field(word, 0, 7) 
        imm32 = extend_sign(imm8, 8)
        imm32 <<= 1
        if conditions_match(cond_code, self.apsr):
            self.pc = self.pc + 4+ imm32
        else:
            self.pc += 2
        return self.pc    
    
    def et16_branch(self, word):
        if self.in_it_block() and not self.last_in_it_block(): 
            raise Code_Error(bna)
        imm11 = get_field(word, 0, 10) 
        imm32 = extend_sign(imm11, 11)
        imm32 <<= 1
        self.pc = self.pc + 4 + imm32       
        return self.pc
    
    def emulate_thumb16(self, word):
        """Emulate Thumb16 instruction"""
        hi_opcode = get_field(word, 14, 15)
        opcode = get_field(word, 10, 15)
        if hi_opcode == 0:
            self.pc = self.et16_shift_etc(word)
        elif opcode == 0x10:
            self.pc = self.et16_data_processing(word)
        elif opcode == 0x11:
            self.pc = self.et16_special_data_and_branch(word)
        elif (opcode&0x3e) == 0x12:
            self.pc = self.et16_load_litpool(word)
        elif ((opcode & 0x3c) == 0x14) or (
              (opcode & 0x38) == 0x18) or (
              (opcode & 0x38) == 0x20):
            self.pc = self.et16_load(word)
        elif (opcode & 0x3e) == 0x28:
            self.pc = self.et16_adr(word)
        elif (opcode & 0x3e) == 0x2a:
            self.pc = self.et16_add_sp(word)
        elif (opcode & 0x3c) == 0x2c:
            self.pc = self.et16_misc(word)
        elif (opcode & 0x3e) == 0x30:
            self.pc = self.et16_ldm_stm(word)  # stm
        elif (opcode & 0x3e) == 0x32:
            self.pc = self.et16_ldm_stm(word)  #ldm          
        elif (opcode & 0x3c) == 0x34:
            self.pc = self.et16_bc_svc(word)
        elif (opcode & 0x3e) == 0x38:
            self.pc = self.et16_branch(word)
        else:
            log_undefined()
            self.pc += 2
        return self.pc
    
    #---------------------------------------------------------------------------
    
    #------------------------Thumb32 support------------------------------------
    

    def et32_strex(self, word):
        rn = get_field(word, 16, 19)
        rt = get_field(word, 12, 15)
        rd = get_field(word, 8, 11)
        imm8 = get_field(word, 0, 7) << 2
        valrn = self.read_reg(rn)
        dest = valrn + imm8
        log("Exclusive store, assuming OK to update memory address {:x}".format(dest))
        valrt = self.read_reg(rt)
        self.write_memory(dest, 4, valrt)
        self.write_reg(rd, 0)
        log_result(valrt)
        self.pc += 4
        return self.pc
    
    def et32_ldrex(self, word):
        rn = get_field(word, 16, 19)
        rt = get_field(word, 12, 15)
        imm8 = get_field(word, 0, 7) << 2
        valrn = self.read_reg(rn)
        src = valrn + imm8
        log("Exclusive load, assuming OK to read memory address {:x}".format(src)) 
        result = self.read_memory_int(src, 4)
        self.write_reg(rt, result)
        log_result(result)
        self.pc += 4
        return self.pc
    
    def et32_strexb(self, word, siz):
        rn = get_field(word, 16, 19)
        rt = get_field(word, 12, 15)
        rd = get_field(word, 0, 3)
        dest = self.read_reg(rn)
        log("Exclusive store  {:d} byte(s), assuming OK to update"
            "memory address {:x}".format(siz, dest))
        valrt = self.read_reg(rt) & 0xff
        self.write_memory(dest, siz, valrt)
        self.write_reg(rd, 0)
        log_result(valrt)
        self.pc += 4
        return self.pc
    
    def et32_ldrexb(self, word, siz):
        rn = get_field(word, 16, 19)
        rt = get_field(word, 12, 15)
        src = self.read_reg(rn)
        log("Exclusive load {:d} byte(s), assuming OK to read"
            "memory address {:x}".format(siz, src)) 
        result = self.read_memory_int(src, siz)
        self.write_reg(rt, result)
        log_result(result)
        self.pc += 4
        return self.pc
    
    def et32_strd(self, word, stor = True):
        """ ldrd, strd, load,store dual immediate """
        rn = get_field(word, 16, 19)
        rt = get_field(word, 12, 15)
        rt2 = get_field(word, 8, 11)
        imm8 = get_field(word, 0, 7) << 2
        wback = get_field(word, 21, 21)
        upp = get_field(word, 23, 23)
        pre_index = get_field(word, 24, 24)
        
        valrn = self.read_reg(rn)
        if upp:
            offset_address = valrn + imm8
        else:
            offset_address  = valrn - imm8
        if pre_index:
            address = offset_address
        else:
            address = valrn
        if stor:
            valrt = self.read_reg(rt)
            valrt2 = self.read_reg(rt2)
            self.write_memory(address, 4, valrt)
            self.write_memory(address+4, 4, valrt2)
        else: # load
            val1 = self.read_memory(address, 4)
            val2 = self.read_memory(address+4, 4)
            self.write_reg(rt, val1)
            self.write_reg(rt2, val2)        
        if wback:
            self.write_reg(rn, offset_address)
        self.pc += 4
        return self.pc
    
    def et32_tbb(self, word):
        """ table branch """
        if self.in_it_block() and not self.last_in_it_block(): 
            raise Code_Error(bna)
        rn = get_field(word, 16, 19)
        rm = get_field(word, 0, 3)
        is_tbh = get_field(word, 4,4)
        valrn = self.read_reg(rn)
        valrm = self.read_reg(rm)
        if is_tbh:
            valrm <<= 1
            halfwords = self.read_memory_int(valrn+valrm, 2)  
        else:
            halfwords = self.read_memory_int(valrn+valrm, 1)
        dest = self.pc + 2*halfwords
        log_result(dest)
        self.pc = dest
        return self.pc    
    
    def et32_ls_dual_excl_tb(self, word):
        """ load, store, dual, exclusive or table branch """
        op1 = get_field(word, 23, 24)
        op2 = get_field(word, 20, 21)
        op3 = get_field(word, 4, 7)
        if op1 == 0:
            if op2 == 0:
                self.pc = self.et32_strex(word)
            elif op2 == 1:
                self.pc = self.et32_ldrex(word)
            elif (op2 == 2) or (((op1 & 2) == 2) and ((op2 & 1) == 0)):
                self.pc = self.et32_strd(word)
            elif (op2 == 3) or (((op1 & 2) == 2) and ((op2 & 1) == 1)):
                self.pc = self.et32_strd(word, stor=False)
        elif op1 == 1:
            if op2 == 0:
                if op3 == 4:
                    self.pc = self.et32_strexb(word, 1)
                elif op3 == 5:
                    self.pc = self.et32_strexb(word, 2)
            elif op2 == 1:
                if op3 == 0:
                    self.pc = self.et32_tbb(word)
                elif op3 == 1:
                    self.pc = self.et32_tbb(word)
                elif op3 == 4:
                    self.pc = self.et32_ldrexb(word, 1)
                elif op3 == 5:
                    self.pc = self.et32_ldrexb(word, 2)
        return self.pc
    
    #--------------------------- Floating Point Instructions ---------------------

    def get_sd_reg(self, word):
        return (get_field(word, 12, 15) <<1 ) | get_field(word, 22, 22)
    
    def get_sm_reg(self, word):
        return  (get_field(word,  0,  3) << 1) | get_field(word, 5, 5)
    
    def get_sn_reg(self, word):
        return (get_field(word, 16, 19) << 1) | get_field(word, 7, 7)

    
    def et32_vml(self, word):  # vmla, vmls
        adding = not get_field(word, 6,6)
        sd = self.get_sd_reg(word)
        sm = self.get_sm_reg(word)
        sn = self.get_sn_reg(word)
        #ExecuteFPCheck()
        result = self.read_fp_reg(sn) * self.read_fp_reg(sm)
        if not adding:
            result = -result
        result = self.read_fp_reg(sd) + result
        self.write_fp_reg(sd, result)  # stored away in integer format
        log_float_result(result)
        self.pc += 4
        return self.pc
        
    def et32_vnml(self, word):
        adding = not get_field(word, 6,6)
        acc = get_field(word, 24, 25) == 1
        sd = self.get_sd_reg(word)
        sm = self.get_sm_reg(word)
        sn = self.get_sn_reg(word)
        #ExecuteFPCheck()
        result = self.read_fp_reg(sn) * self.read_fp_reg(sm)
        if not adding:
            result = -result
        if acc:
            result = self.read_fp_reg(sd) + result
        self.write_fp_reg(sd, result)  # stored away in integer format
        log_float_result(result)
        self.pc += 4
        return self.pc    
        
    
    def et32_vmul(self, word):
        sd = self.get_sd_reg(word)
        sm = self.get_sm_reg(word)
        sn = self.get_sn_reg(word)
        #ExecuteFPCheck()
        result = self.read_fp_reg(sn) * self.read_fp_reg(sm)
        self.write_fp_reg(sd, result)  # stored away in integer format
        log_float_result(result)
        self.pc += 4
        return self.pc
    
    def et32_vdiv(self, word):
        sd = self.get_sd_reg(word)
        sm = self.get_sm_reg(word)
        sn = self.get_sn_reg(word)
        #ExecuteFPCheck()
        result = self.read_fp_reg(sn) / self.read_fp_reg(sm)
        self.write_fp_reg(sd, result)  # stored away in integer format
        log_float_result(result)
        self.pc += 4
        return self.pc    
    
    def et32_vadd(self, word, adding = True):
        sd = self.get_sd_reg(word)
        sm = self.get_sm_reg(word)
        sn = self.get_sn_reg(word)
        #ExecuteFPCheck()
        result = self.read_fp_reg(sn)
        valsm  = self.read_fp_reg(sm)
        if adding:
            result += valsm
        else:
            result -= valsm
        self.write_fp_reg(sd, result)  # stored away in integer format
        log_float_result(result)
        self.pc += 4
        return self.pc

    def et32_vmov_imm(self, word):
        result = vfp_expand_imm((
            get_field(word, 16, 19) << 4) | get_field( word, 0, 3))
        sd = self.get_sd_reg(word)
        #ExecuteFPCheck()
        self.write_raw_fp_reg(sd, result)  # stored away in integer format
        log_raw_float_result(result)
        self.pc += 4   
        return self.pc
    
    def et32_vmov(self, word):
        sd = self.get_sd_reg(word)
        sm = self.get_sm_reg(word)
        #ExecuteFPCheck()
        result = self.read_raw_fp_reg(sm)
        self.write_raw_fp_reg(sd, result)  # stored away in integer format
        log_raw_float_result(result)
        self.pc += 4
        return self.pc
    
    def et32_vabs(self, word):
        sd = self.get_sd_reg(word)
        sm = self.get_sm_reg(word)
        #ExecuteFPCheck()
        result = self.read_fp_reg(sm)
        if result < 0.0:
            result = -result        
        self.write_fp_reg(sd, result)  # stored away in integer format
        log_float_result(result)
        self.pc += 4
        return self.pc 
    
    
    def et32_vneg(self, word):
        sd = self.get_sd_reg(word)
        sm = self.get_sm_reg(word)
        #ExecuteFPCheck()
        result = self.read_fp_reg(sm)
        result = -result        
        self.write_fp_reg(sd, result)  # stored away in integer format
        log_float_result(result)
        self.pc += 4
        return self.pc     
    
    def et32_vsqrt(self, word):
        sd = self.get_sd_reg(word)
        sm = self.get_sm_reg(word)
        #ExecuteFPCheck()
        result = self.read_fp_reg(sm)
        result = math.sqrt(result)        
        self.write_fp_reg(sd, result)  # stored away in integer format
        log_float_result(result)
        self.pc += 4
        return self.pc         
        
        
    def et32_vcvt(self, word):
        half_to_single = testBit(word, 16)
        if testBit(word, 7):
            lowbit = 16
        else:
            lowbit = 0
        sm = self.get_sm_reg(word)
        valsm = self.read_raw_fp_reg(sm)
        sd = self.get_sd_reg(word)
        if half_to_single:
            if lowbit == 16:
                sm_half = valsm >> 16
            else:
                sm_half = valsm & 0xffff
            result, self.fpscr = FPHalfToSingle(sm_half, self.fpscr, True)
        else:
            result, self.fpscr = FPSingleToHalf(valsm, self.fpscr, True)
            valsd = self.read_raw_fp_reg(sd)
            if lowbit == 16:
                result = (valsd & 0xffff) | ((result & 0xffff) << 16)
            else:
                result = (valsd & 0xffff0000) | (result & 0xffff) 
        self.write_raw_fp_reg(sd, result)
        log_float_result(result)
        self.pc += 4
        return self.pc 
    
    def et32_vcmp(self, word):
        sd = self.get_sd_reg(word)
        sm = self.get_sm_reg(word)
        with_zero = get_field(word, 16, 16) == 1
        quiet_nan_exc = get_field(word, 7, 7)

        valsm = self.read_fp_reg(sm)
        valsd = self.read_fp_reg(sd)
        raw_valsm = self.read_raw_fp_reg(sm)
        raw_valsd = self.read_raw_fp_reg(sd)        
        if with_zero:
            valsm = 0.0
        #ExecuteFPCheck()
        self.fpscr = FPCompare(raw_valsd, raw_valsm, quiet_nan_exc, self.fpscr) 
        val = valsd-valsm
        log_float_result(val, self.fpscr)
        self.pc += 4
        return self.pc     
    
    def et32_vcvt_fi(self, word):
        # ExecuteFPCheck()
        to_int = get_field(word, 18, 18)  
        if to_int:
            round_zero = get_field(word, 16, 18) == 1
            signed = testBit(word, 16)
        else:
            signed = testBit(word, 7)
            round_fpscr = False
        sm = self.get_sm_reg(word)
        valsm = self.read_raw_fp_reg(sm)
        sd = self.get_sd_reg(word)
        if to_int:
            valsd, self.fpscr = FPToFixed(valsm, 32, 0, not signed,
                                          round_zero, self.fpscr, True)
        else:
            valsd, self.fpscr = FixedToFP(valsm, 32, 0, not signed, 
                                          round_fpscr, self.fpscr, True)
        self.write_raw_fp_reg(sd, valsd)
        log_raw_float_result(valsd)
        self.pc += 4
        return self.pc
        
    def et32_vcvt_ffx(self, word):
        to_fixed = get_field(word, 18, 18)
        unsigned = get_field(word, 16, 16)
        siz = get_field(word, 7, 7)
        imm5 = (get_field(word, 0, 3) << 1) | get_field(word, 5, 5)
        if siz:
            bit_size = 32
        else:
            bit_size = 16
        frac_bits = bit_size - imm5
        if frac_bits < 0:
            log('Error in vcvt:fractional bits < 0')
            self.pc += 4
            return self.pc
        round_zero = round_nearest = False
        if to_fixed: 
            round_zero = True
        else:
            round_nearest = True
        sd = self.get_sd_reg(word)
        valsd = self.read_raw_fp_reg(sd)
        if to_fixed:
            result, self.fpscr = FPToFixed(valsd, siz, frac_bits, unsigned, 
                                           round_zero, self.fpscr, True)
            if unsigned:
                result &= 0xffffffff
            self.write_raw_fp_reg(sd, result)
        else:
            if siz == 32:
                valsd &= 0xffffffff
            else:
                valsd &= 0xffff
            result, self.fpscr = FixedToFP(valsd, 32, frac_bits, unsigned, 
                                round_nearest, self.fpscr, True)  
        log_raw_float_result(result)
        self.pc += 4
        return self.pc
    
    def et32_vmsr(self, word):
        """ move gp reg to fpscr """
        # ExecuteFPCheck()
        # Serialize VFP
        # VPExcBarrier()
        rt = get_field(word, 12, 15)        
        self.fpscr = self.read_reg(rt)
        log_cc(self.apsr)
        self.pc += 4
        return self.pc
    
    def et32_vmrs(self, word):
        """ move value of fpscr to a gp reg or to apsr[nzcv] """
        # ExecuteFPCheck()
        # Serialize VFP
        # VPExcBarrier()
        rt = get_field(word, 12, 15)
        if rt == 15:
            nzcv = self.fpscr & 0xf0000000
            self.apsr = self.apsr& 0x0fffffff
            self.apsr |= nzcv
            log_cc(self.apsr)
        else:
            self.write_reg(rt, self.fpscr)
            log_raw_float_result(0, self.fpscr)
        
        self.pc += 4
        return self.pc
        
    def et32_fp_instr(self, word):
        opc1 = get_field(word, 20, 23) & 0b1011
        opc2 = get_field(word, 16, 19)
        opc3 = get_field(word, 6, 7)
        if opc1 == 0:
            self.pc = self.et32_vml(word)
        elif opc1 == 1:
            self.pc = self.et32_vnml(word)
        elif opc1 == 2:
            if opc3&1 == 1:
                self.pc = self.et32_vnml(word)
            else:
                self.pc = self.et32_vmul(word)
        elif opc1 == 3:
            if opc3&1 == 1:
                self.pc = self.et32_vadd(word, adding = False)
            else:
                self.pc = self.et32_vadd(word, adding = True)
        elif opc1 == 8:
            self.pc = self.et32_vdiv(word)
        elif opc1 == 11:
            if opc3 == 0:
                self.pc = self.et32_vmov_imm(word)
            elif opc2 == 0:
                if opc3 == 1:
                    self.pc = self.et32_vmov(word)
                elif opc3 == 3:
                    self.pc = self.et32_vabs(word)
            elif opc2 == 1:
                if opc3 == 1:
                    self.pc = self.et32_vneg(word)
                elif opc3 == 3:
                    self.pc = self.et32_vsqrt(word)
            elif (opc2 & 0b0010) == 2:
                if (opc3 & 1) == 1:
                    self.pc = self.et32_vcvt(word)
            elif (opc2 & 0b0100) == 4:
                if (opc3 & 1) == 1:
                    self.pc = self.et32_vcmp(word)
            elif (opc2 == 8): 
                if (opc3 & 1) == 1:
                    self.pc = self.et32_vcvt_fi(word)
            elif((opc2 & 0b1010) == 0b1010):
                if (opc3 & 1) == 1:
                    self.pc = self.et32_vcvt_ffx(word)
            elif((opc2 & 0b1100) == 0b1100):
                if (opc3 & 1) == 1:
                    self.pc = self.et32_vcvt_fi(word)
            else:
                log_undefined() 
                self.pc += 4
        else:
            log_undefined()
            self.pc += 4
        return self.pc
    
    def et32_fp_2reg_mov(self, word):
        to_arm_reg = get_field(word, 20, 20)
        rt = get_field(word, 12, 15)
        rt2 = get_field(word, 16, 19)
        dm = sm = (get_field(word,  0,  3) << 1) | get_field(word, 5, 5)
        if get_field(word, 8, 8):
            use_dbl = True
        else:
            use_dbl = False
        if use_dbl:
            if to_arm_reg:
                valdm = self.read_raw_dfp_reg(dm)
                self.write_reg(rt, valdm&0xffffffff)
                self.write_reg(rt2, (valdm >> 32) & 0xffffffff)
            else:
                valrt = self.read_reg(rt)
                valrt2 = self.read_reg(rt2)
                valdm = (valrt2 << 32) | valrt
                self.write_raw_dfp_reg(dm, valrt, valrt2)
        else:
            if to_arm_reg:
                valsm = self.read_raw_fp_reg(sm)
                self.write_reg(rt, valsm)
                valsm1 = self.read_raw_fp_reg(sm+1)
                self.write_reg(rt2, valsm1)
            else:
                valrt = self.read_reg(rt)
                self.write_raw_fp_reg(sm, valrt)
                valrt2 = self.read_reg(rt2)
                self.write_raw_fp_reg(sm+1, valrt2)
  
        self.pc += 4
        return self.pc
     
    def et32_vmov_reg_scalar(self, word):
        """ core reg to upper or lower half of doubleword reg  or vice versa """
        rt = get_field(word, 12, 15)
        dreg = ((get_field(word, 7,7) << 5) | 
                (get_field(word, 16, 19) << 1) | 
                 get_field(word, 21, 21))
        if get_field(word, 20, 20):
            result = self.read_raw_fp_reg(dreg)
            self.write_reg(rt, result)
        else:
            result = self.read_reg(rt)
            self.write_raw_fp_reg(dreg, result)
        log_raw_float_result(result)    
        self.pc += 4
        return self.pc
    
    def et32_vmov_core_sp(self, word):
        to_arm_reg = get_field(word, 24, 24)
        rt = get_field(word, 12, 15)
        sn = self.get_sn_reg(word)
        if to_arm_reg:
            result = self.read_raw_fp_reg(sn)
            self.write_reg(rt, result)
        else:
            result = self.read_reg(rt)
            self.write_raw_fp_reg(sn, result)
        log_raw_float_result(result)
        self.pc += 4
        return self.pc
    
    def et32_vstr(self, word):
        rn = get_field(word, 16, 19)
        double_reg = get_field(word, 8, 8)
        upp = get_field(word, 23, 23)
        sd = self.get_sd_reg(word)
        imm32 = get_field(word, 0, 7) << 2
        base = self.read_reg(rn)
        if imm32 != 0:
            if not upp:
                base -= imm32
            else:
                base += imm32
 
        if not double_reg:
            result = self.read_raw_fp_reg(sd)
            self.write_memory(base, 4, result)
            self.write_raw_fp_reg(sd, result)
            log_raw_float_result(result)
        else:
            result = self.read_raw_dfp_reg(sd)
            result1 = result >> 32
            result2 = result & 0xffffffff
            self.write_memory(base, 4, result2)
            self.write_memory(base+4, 4, result1)
            log_raw_dfloat_result(result2, result1)            
            
        self.pc += 4
        return self.pc    
        
        
    def et32_vldr(self, word):
        rn = get_field(word, 16, 19)
        double_reg = testBit(word, 8)
        upp = get_field(word, 23, 23)
        sd = self.get_sd_reg(word)
        imm32 = get_field(word, 0, 7) << 2
        if rn != 15:
            base = self.read_reg(rn)
            if imm32 != 0:
                if not upp:
                    base -= imm32
                else:
                    base += imm32
        else:
            base = alignPC(self.pc, 4)
        if not double_reg:
            result = self.read_memory_int(base, 4)
            self.write_raw_fp_reg(sd, result)
            log_raw_float_result(result)
        else:
            result1 = self.read_memory_int(base, 4)
            result2 = self.read_memory_int(base+4, 4)
            self.write_raw_dfp_reg(sd, result2, result1)  # little endian
            log_raw_dfloat_result(result2, result1)            
            
        self.pc += 4
        return self.pc    
        
        
    def et32_vpush(self, word):
        double_reg = testBit(word, 8)
        sd = self.get_sd_reg(word)
        imm8 = get_field(word, 0, 7)
        imm32 = imm8 << 2
        if double_reg:
            regs = imm8 >> 1
        else:
            regs = imm8
        valsp = self.read_reg(SP)
        addr = valsp -imm32
        self.write_reg(SP, addr)
        if not double_reg:
            for r in range(regs):
                val = self.read_raw_fp_reg(sd+r)
                self.write_memory(addr, 4, val)
                log("pushed = {:08x} from {:s} into {:08x}".format(
                                             val, get_fpreg(sd+r), addr))
                addr += 4
        else:
            for r in range(regs):
                val = self.read_raw_dfp_reg(sd+r)
                val1 = val & 0xffffffff
                val2 = val >> 32
                self.write_memory(addr, 4, val1)
                self.write_memory(addr+4, 4, val2)
                log("pushed = {:016x} from {:s} into {:08x}".format(
                                             val, get_dfpreg(sd+r), addr))
                addr += 8
        self.pc += 4
        return self.pc
    
    def et32_vpop(self, word):
        double_reg = testBit(word, 8)
        sd = self.get_sd_reg(word)
        imm8 = get_field(word, 0, 7)
        imm32 = imm8 << 2
        if double_reg:
            regs = imm8 >> 1
        else:
            regs = imm8
        valsp = self.read_reg(SP)
        addr = valsp
        self.write_reg(SP, addr+imm32)
        if not double_reg:
            for r in range(regs):
                val = self.read_memory_int(addr, 4)
                self.write_raw_fp_reg(sd+r, val)
                log("popped = {:08x} from {:08x} into {:s}".format(
                                             val, addr, get_fpreg(sd+r)))
                addr += 4
        else:
            for r in range(regs):
                val1 = self.read_memory_int(addr, 4)
                val2 = self.read_memory_int(addr+4, 4)
                val = ((val2&0xffffffff) << 32) | (val1 & 0xffffffff)
                self.write_raw_dfp_reg(sd+r,  val1, val2)

                log("popped = {:016x} from {:08x} into {:s}".format(
                                            val, addr, get_dfpreg(sd+r)))
                addr += 8

        self.pc += 4
        return self.pc
        
    def et32_vstm(self, word):
        use_dbl = testBit(word, 8)
        rn = get_field(word, 16, 19)
        imm8 = get_field(word, 0, 7) << 2
        addit = testBit(word, 23)
        wback = testBit(word, 21)
        if use_dbl:
            vd = (get_field(word, 22, 22) << 4) | get_field(word, 12, 15)
            regs = imm8//2
        else:
            vd = (get_field(word, 12, 15) << 1) | get_field(word, 22, 22)
            regs = imm8
        valrn = self.read_reg(rn)
        if not addit:
            addr = valrn -imm8
        else:
            addr = valrn
        if wback:
            if addit:
                wback_addr = valrn + imm8
            else:
                wback_addr = valrn - imm8
            self.write_reg(rn, wback_addr)
        if not use_dbl:
            for r in range(regs):
                val = self.read_raw_fp_reg(vd+r)
                self.write_memory(addr, 4, val)
                log("stored {:08x} from {:s} into {:08x}".format(
                                             val, get_fpreg(vd+r), addr))
                addr += 4
        else:
            for r in range(regs):
                val = self.read_raw_dfp_reg(vd+r)
                val1 = val & 0xffffffff
                val2 = val >> 32
                self.write_memory(addr, 4, val1)
                self.write_memory(addr+4, 4, val2)
                log("stored {:016x} from {:s} into {:08x}".format(
                                              val, get_dfpreg(vd+r), addr))
                addr += 8
        self.pc += 4
        return self.pc
        
    def et32_vldm(self, word):
        use_dbl = testBit(word, 8)
        rn = get_field(word, 16, 19)
        imm8 = get_field(word, 0, 7) << 2
        addit = testBit(word, 23)
        wback = testBit(word, 21)
        if use_dbl:
            vd = (get_field(word, 22, 22) << 4) | get_field(word, 12, 15)
            regs = imm8//2
        else:
            vd = (get_field(word, 12, 15) << 1) | get_field(word, 22, 22)
            regs = imm8
        valrn = self.read_reg(rn)
        if not addit:
            addr = valrn -imm8
        else:
            addr = valrn 
            if wback:
                if addit:
                    wback_addr = valrn + imm8
                else:
                    wback_addr = valrn - imm8
                self.write_reg(rn, wback_addr)        

        if not use_dbl:
            for r in range(regs):
                val = self.read_memory_int(addr, 4)
                self.write_raw_fp_reg(vd+r, val)
                log("loaded {:08x} from {:08x} into {:s}".format(
                                             val, addr, get_fpreg(vd+r)))
                addr += 4
        else:
            for r in range(regs):
                val1 = self.read_memory_int(addr, 4)
                val2 = self.read_memory_int(addr+4, 4)
                val = ((val2&0xffffffff) << 32) | (val1 & 0xffffffff)
                self.write_raw_dfp_reg(vd+r,  val1, val2)

                log("loaded {:016x} from {:08x} into {:s}".format(
                                            val, addr, get_dfpreg(vd+r)))
                addr += 8
        
        self.pc += 4
        return self.pc

    
    def et32_fp_load_store(self, word):
        opcode = get_field(word, 20, 24)
        rn = get_field(word, 16, 19)
        
        if opcode == 4 or opcode == 5: # 64 bit transfer between core and fp regs
            return self.et32_fp_2reg_mov(word)
        if (opcode & 0b10011) == 0b10000:
            return self.et32_vstr(word)
        elif (opcode & 0b10011) == 0b10001:
            return self.et32_vldr(word)
        elif ((opcode & 0b11011) == 0b10010) and (rn == 13):
            return self.et32_vpush(word)
        elif ((opcode & 0b11011) == 0b01011) and (rn == 13):
            return self.et32_vpop(word)
        elif (opcode & 1) == 0:
            return self.et32_vstm(word)
        elif (opcode & 1) == 1:
            return self.et32_vldm(word)
        self.pc += 4
        return self.pc
        
    def et32_32bit_xfer(self, word):
        # 32 bit transfer between ARM core and extension regs
        lfield = get_field(word, 20, 20)
        cfield = get_field(word, 8, 8)
        afield = get_field(word, 21, 23)
        bfield = get_field(word, 5, 6)
        if lfield == 0:
            if (cfield == 1) and (bfield == 0):
                return self.et32_vmov_reg_scalar(word) # scalar to core
            else:
                if afield == 0:
                    return self.et32_vmov_core_sp(word)
                elif afield == 7:
                    return self.et32_vmsr(word)
        else:
            if (cfield == 1) and (bfield == 0):
                return self.et32_vmov_reg_scalar(word) # core to scalar
            else:
                if afield == 0:
                    return self.et32_vmov_core_sp(word)
                elif afield == 7:
                    return self.et32_vmrs(word)
        self.pc += 4
        return self.pc
        
    #----------------------------- End of FP instrs --------------
    
    def et32_coproc1(self, word):
        
        if get_field(word, 9, 11) == 5: # Floating point == coproc 10 and 11
            if get_field(word, 24, 25) == 2:
                if testBit(word, 4):
                    return self.et32_32bit_xfer(word)
                else:
                    return self.et32_fp_instr(word)
            if get_field(word, 25, 25) == 0:
                return self.et32_fp_load_store(word)
        
        return self.pc
    
    def et32_str_reg(self, word,datasize = 4):
        rn = get_field(word, 16, 19) 
        rt = get_field(word, 12, 15)
        rm = get_field(word, 0, 3)
        imm2 = get_field(word, 4,5)
        valrm = self.read_reg(rm)
        if imm2 != 0:
            valrm = valrm << imm2
        valrn = self.read_reg(rn)
        addr = valrm + valrn
        valrt = self.read_reg(rt)
        if datasize == 1:
            valrt &= 0xff
        elif datasize == 2:
            valrt &= 0xffff        
        self.write_memory(addr, datasize, valrt)
        self.pc += 4
        return self.pc
    
    def et32_str_imm(self, word, datasize = 4):
        rn = get_field(word, 16, 19)
        rt = get_field(word, 12, 15)
        t3 = get_field(word, 23, 23)
        valrn = self.read_reg(rn)
        valrt = self.read_reg(rt)
        if datasize == 1:
            valrt &= 0xff
        elif datasize == 2:
            valrt &= 0xffff
        if t3:
            imm12 = get_field(word, 0, 12)
            addr = valrn + imm12
            wback = False
        else: 
            imm8= get_field(word, 0, 7)
            wback = get_field(word, 8, 8)
            upp =   get_field(word, 9, 9)
            pre =   get_field(word, 10, 10)
            if imm8 != 0:
                if upp: 
                    addr = valrn+imm8
                else:
                    addr = valrn-imm8
            if wback:
                self.write_reg(rn, addr)
        self.write_memory(addr, datasize, valrt)
        self.pc += 4
        return self.pc
    
    def et32_ssd(self, word):
        """ Store single data item """
        op1 = get_field(word, 21, 23)
        op2_5 = get_field(word, 11, 11)
        if op1 <= 2:
            if op1 == 0:
                datasize = 1
            elif op1 == 1:
                datasize = 2
            elif op1 == 2:
                datasize = 4
            if op2_5 == 0:
                self.pc = self.et32_str_reg(word,  datasize)
            else:
                self.pc = self.et32_str_imm(word, datasize)
        else:
            if op1 == 4:
                datasize = 1
            elif op1 == 5:
                datasize = 2
            elif op1 == 6:
                datasize = 4
            else:
                datasize = 4  # actually, 7 is undefined
            self.pc = self.et32_str_imm(word, datasize)

        return self.pc
    
    
    def et32_ldr_reg_lit(self, word, pld=False):
        upp = get_field(word, 23, 23)
        rt = get_field(word, 12, 15)
        imm12 = get_field(word, 0, 11)
        base = alignPC(self.pc, 4) +4
        if upp: 
            base += imm12
        else: 
            base -= imm12
        val = self.read_memory_int(base, 4, signed = True)
        if not pld:  
            # in this emulator, pld is a nop
            self.write_reg(rt, val)
            log_result(val)
        else:
            log("Preload hint, dest = {:x}".format(val))            
        self.pc += 4
        return self.pc
    
    def et32_ldr_reg(self, word, pld = False):
        rn = get_field(word, 16, 19)   
        rm = get_field(word, 0, 3)
        imm2 = get_field(word, 4, 5)
        if not pld:
            rt = get_field(word, 12, 15)
        valrm = self.read_reg(rm)
        if imm2 != 0:
            valrm <<= imm2
        offset_addr = self.read_reg(rn) + valrm
        result = self.read_memory_int(offset_addr, 4, signed = True)
        if not pld:
            self.write_reg(rt, result)
            log_result(result)
        else:
            log("Preload hint, dest = {:x}".format(result))            
        if rt != 15:
            self.pc += 4
        return self.pc
        
    def et32_ldrt(self, word):
        rn = get_field(word, 16, 19)
        rt = get_field(word, 12, 15)
        imm8= get_field(word, 0, 7)
        valrn = self.read_reg(rn)
        addr = valrn + imm8
        result = self.read_memory_int(addr, 4, signed = True)
        # no support for unprivileged/privileged modes, yet
        self.write_reg(rt, result)
        log_result(result)
        self.pc += 4
        return self.pc
    
    def et32_ldr_imm(self, word, pld = False):
        rn = get_field(word, 16, 19)
        if not pld:
            rt = get_field(word, 12, 15)
        t3 = get_field(word, 23, 23)
        if t3: # or t2 for ldrh or t1 for ldrsh
            imm = get_field(word, 0, 12)
            wback = False
            upp = True
            index = True
        else:  # t4  or t3 for ldrh  or t2 for ldrsh  
            imm   = get_field(word, 0, 7)
            wback = get_field(word, 8, 8)
            upp =   get_field(word, 9, 9)
            index = get_field(word, 10, 10)
            
        valrn = self.read_reg(rn)
        if upp:
            offset_addr = valrn + imm
        else:
            offset_addr = valrn - imm
        if index:
            addr = offset_addr
        else:
            addr = valrn
        result = self.read_memory_int(addr, 4, signed = True)
        if wback:
            self.write_reg(rn, offset_addr)
        if not pld:
            self.write_reg(rt, result)
            log_result(result)
        else:
            log("Preload hint, dest = {:x}".format(result))
        if (rt != 15)  or pld:   
            self.pc += 4
        return self.pc
    
    
    def et32_pld_imm_lit(self, word, pld = True):
        rn = get_field(word, 16, 19)
        upp =    get_field(word, 23,23)
        if rn == 15: # pld literal, T3 encoding
            base = alignPC(self.pc, 4)
            imm12 = get_field(word, 0, 11)
            if upp: 
                dest = base + imm12
            else:
                dest = base - imm12        
        else:   # rn != 0, pld imm
            base = self.read_reg(rn)
            if upp:
                imm12 = get_field(word, 0, 11)
                dest = base + imm12
            else:  
                imm8= get_field(word, 0, 7)
                dest = base -imm8
        log("Preload hint, dest = {:x}".format(dest))
        self.pc += 4
        return self.pc    
        
        
    
    def et32_lb(self, word):
        """ load byte and memory hints """
        op1 = get_field(word, 23, 24)
        op2 = get_field(word,  6, 11)
        rn =  get_field(word, 16, 19)
        rt =  get_field(word, 12, 15)
        if rt == 15:  # preload data
            if rn == 15:
                if op1 < 2:
                    self.pc = self.et32_ldr_reg_lit(word, pld=True)
                else:
                    self.pc = self.et32_pld_imm_lit(word, pld = True)
            else:
                if op1 == 0:
                    if op2 == 0:
                        self.pc = self.et32_ldr_reg(word, pld = True)
                    elif ((op2 & 0b110000) == 0b110000):
                        self.pc = self.et32_ldr_imm(word, pld = True)
                    else:
                        self.pc = self.pc+4
                elif op1 == 1:
                    self.pc = self.et32_ldr_imm(word, pld = True)
                elif op1 == 2:
                    if op2 == 0:
                        self.pc = self.et32_pld_imm_lit(word, pld = True)
                    elif ((op2 & 0b110000) == 0b110000):
                        self.pc = self.et32_pld_imm_lit(word, pld = True)
                    else:
                        self.pc = self.pc+4
    
                elif op2 == 3:
                    self.pc = self.et32_pld_imm_lit(word,  pld = True)
        else:  #rt != 15, loads
            if rn == 15:
                if op1 < 2:
                    self.pc = self.et32_ldr_reg_lit(word)
                else:
                    self.pc = self.et32_ldr_reg_lit(word)
            else:        
                if (op1 == 0): 
                    if (op2 == 0):
                        self.pc = self.et32_ldr_reg(word)
                    elif ((op2&0b100100) == 0b100100) or ((op2&0b110000) == 0b110000):
                        self.pc = self.et32_ldr_imm(word)
                    elif ((op2&0b111000) == 0b111000):
                        self.pc = self.et32_ldrt(word)
                elif (op1 == 1):
                    self.pc = self.et32_ldr_imm(word)
                elif (op1 == 2):
                    if (op2 == 0):
                        self.pc = self.et32_ldr_reg(word)
                    elif ((op2&0b100100) == 0b100100) or ((op2&0b110000) == 0b110000):
                        self.pc = self.et32_ldr_imm(word)
                    elif ((op2&0b111000) == 0b111000):
                        self.pc = self.et32_ldrt(word)
                elif (op1 == 3):
                    self.pc = self.et32_ldr_imm(word)
        return self.pc
    
    
    
    def et32_lh(self, word):
        
        op1 = get_field(word, 23, 24)
        op2 = get_field(word,  6, 11)
        rn =  get_field(word, 16, 19)
        rt =  get_field(word, 12, 15)
        if rn == 15:
            if rt != 15:
                if op1 < 2:
                    self.pc = self.et32_ldr_reg_lit(word)
                else:
                    self.pc = self.et32_ldr_reg_lit(word)
            else:
                self.pc = self.pc+4
                
        else:  #rn != 15
            if rt != 15:
                if (op1 == 0): 
                    if (op2 == 0):
                        self.pc = self.et32_ldr_reg(word)
                    elif ((op1&0b100100) == 0b100100) or ((op2&0b110000) == 0b110000):
                        self.pc = self.et32_ldr_imm(word)
                    elif ((op2&0b111000) == 0b111000):
                        self.pc = self.et32_ldrt(word)
                elif (op1 == 1):
                    self.pc = self.et32_ldr_imm(word)
                elif (op1 == 2):
                    if (op2 == 0):
                        self.pc = self.et32_ldr_reg(word)
                    elif ((op1&0b100100) == 0b100100) or ((op2&0b110000) == 0b110000):
                        self.pc = self.et32_ldr_imm(word)
                    elif ((op2&0b111000) == 0b111000):
                        self.pc = self.et32_ldrt(word)
                elif (op1 == 3):
                    self.pc = self.et32_ldr_imm(word)
            else: # rt == 15
                if op1 == 1:
                    self.pc = self.pc+4  # nop
                elif (op2 == 0) or ((op2 & 0b110000) == 0b110000):
                    self.pc = self.pc+4  # nop
                else:
                    self.pc+= 4 
                    log_unpredictable(word)
        return self.pc
    
    
    def et32_lw(self, word):
        op1 = get_field(word, 23, 24)
        op2 = get_field(word, 6, 11)
        rn =  get_field(word, 16, 19)
        if rn == 15:
            self.pc = self.et32_ldr_reg_lit(word)
        else:
            if op1 == 0:
                if op2 == 0:
                    self.pc = self.et32_ldr_reg(word)
                elif ((op2 & 0b11100) == 0b111000):
                    self.pc = self.et32_ldrt(word)
                else:  # actually only 0b1xx1xx and 0b1100xx
                    self.pc = self.et32_ldr_imm(word)
            elif op1 == 1:
                self.pc = self.et32_ldr_imm(word)
        return self.pc
    
    def et32_shift_reg(self, word, opcode):
        setflags = testBit(word, 20)
        rd = get_field(word, 8, 11)
        rn = get_field(word, 16, 19)
        rm = get_field(word, 0, 3)
        shift_count = self.read_reg(rm) & 0xff
        valrn = self.read_reg(rn)
        result, self.apsr = Shift_C(opcode, valrn, shift_count, self.apsr)        
        self.write_reg(rd, result)
        if setflags:
            self.apsr = arith_cond(result, self.apsr, testBit(self.apsr, CBIT))
            log_result(result, self.apsr)
        else:
            log_result(result)
        self.pc += 4
        return self.pc
     
    def et32_extend_add(self, word):
        rm = get_field(word, 0, 3)
        rd = get_field(word, 8, 11)
        rn = get_field(word, 16, 19)
        op1 = get_field(word, 20, 24)
        unsignd = testBit(op1, 0)
        add_rn = (rn != 15)
        xtab = False
        if op1 <= 1:
            siz = 2
        elif op1 <= 3:
            xtab = True
            siz = 1
        elif op1 <= 5:
            siz = 1
        if add_rn:
            valrn = self.read_reg(rn)        
        rotate = get_field(word, 4, 5) << 3
        valrm = self.read_reg(rm)
        result, carry = ror_c(valrm, 32, rotate)
        if xtab:
            low_hw = result & 0xff
            high_hw = (result >> 16) & 0xff
            if not unsignd:
                low_hw =  extend_sign(low_hw, 8) & 0xffff
                high_hw = extend_sign(high_hw, 8) & 0xffff
            if add_rn:
                low_hw = ((valrn & 0xffff) + low_hw) & 0xffff
                high_hw = ((valrn >> 16) + high_hw) & 0xffff
            result = (high_hw << 16) | low_hw 
        else:
            if siz == 1:
                result = result & 0xff
                if not unsignd:
                    result = extend_sign(result, 8)
            elif siz == 2:
                result = result & 0xffff
                if not unsignd:
                    result = extend_sign(result, 16) 
            if add_rn:
                result = result + valrn
        self.write_reg(rd, result)
        log_result(result)
        self.pc += 4
        return self.pc
    
    def et32_dpr_misc(self, word):
        op1 = get_field(word, 20, 21)
        op2 = get_field(word, 4, 5)
        rn = get_field(word, 16, 19)
        rd = get_field(word, 8, 11)
        rm = get_field(word, 0, 3)

        if op1 == 0: # qadd, qsub
            if op2 == 0:
                opcode = 'qadd'
            elif op2 == 1:
                opcode = 'qdadd'
            elif op2 == 2:
                opcode = 'qsub'
            elif op2 == 3:
                opcode = 'qdsub'
        elif op1 == 1:  # rev
            valrm = self.read_reg(rm)
            if op2 == 0: # rev.w
                result = ((valrm & 0xff) << 24) | ((valrm & 0xff00) << 8) | (
                         (valrm >> 8) & 0xff00) | (valrm >> 24)
            elif op2 == 1: # rev16.w
                result = ((valrm << 8) & 0xff00ff00) | (
                          ( valrm >> 8 ) & 0x00ff00ff)
            elif op2 == 2: # rbit
                result = rev32bits(valrm)
            elif op2 == 3: # revsh.w
                result = ((valrm >> 8) & 0xff) | (( valrm << 8) & 0xff00)
                result = extend_sign(result, 16)
            self.write_reg(rd, result)
            log_result(result)
            self.pc += 4
        elif op1 == 2: # sel
            valrm = self.read_reg(rm)
            valrn = self.read_reg(rn)
            if testBit(self.apsr, GE0):
                result = valrn & 0xff
            else:
                result = valrm & 0xff
            if testBit(self.apsr, GE1):
                result |= valrn & 0xff00
            else:
                result |= valrm & 0xff00  
            if testBit(self.apsr, GE2):
                result |= valrn & 0xff0000
            else:
                result |= valrm & 0xff0000
            if testBit(self.apsr, GE3):
                result |= valrn & 0xff000000
            else:
                result |= valrm & 0xff000000  
            self.write_reg(rd, result)
            log_result(result)
            self.pc += 4
        elif op1 == 3: # clz
            valrm = self.read_reg(rm)
            result = CountLeadingZeroBits(valrm)
            self.write_reg(rd, result)
            log_result(result)
            self.pc += 4
        return self.pc
    
            
    
    def et32_dpr(self, word):
        op1 = get_field(word, 20, 24)
        op2 = get_field(word, 4, 7)
        if (op1 & 8) == 0:
            if op2 == 0:
                self.pc = self.et32_shift_reg(word, (op1 >> 1))
            else:
                self.pc = self.et32_extend_add(word)
        else:
            if (op2 & 0xc) == 0:
                pass # TBD parallel add and subtract
            elif (op2 & 0xc) == 4:
                pass #  TBD unsigned parallel add and subtract
            elif (op2 & 0xc) == 8:
                self.pc = self.et32_dpr_misc(word)
        
        return self.pc
    
    def et32_mul(self, word, sub = False):
        rd = get_field(word, 8, 11)
        rn = get_field(word, 16, 19)
        rm = get_field(word, 0, 3)
        ra = get_field(word, 12, 15)
        result = self.read_reg(rn) * self.read_reg(rm)
        if ra != 15:  # accumulate
            if sub:
                result = self.read_reg(ra) -result
            else:
                result = self.read_reg(ra) +result
        self.write_reg(rd, result)
        log_result(result)
        self.pc += 4
        return self.pc
    
    def et32_mulh(self, word):
        rd = get_field(word, 8, 11)
        rn = get_field(word, 16, 19)
        rm = get_field(word, 0, 3)
        ra = get_field(word, 12, 15)
        tb = get_field(word, 4, 5) # 00=bb, 01=bt, 10=tb, 11=tt: rn, rm
        valrn = self.read_reg(rn)
        if tb >= 2:
            valrn = valrn >> 16
        else:
            valrn = extend_sign(valrn & 0xffff, 16)
        valrm = self.read_reg(rm)
        if (tb&1) == 1:
            valrm = valrm >> 16
        else:
            valrm = extend_sign(valrm & 0xffff, 16)
        result = valrn * valrm
        if ra != 15:  # accumulate
            result += self.read_reg(ra)
        res32 = result & 0xffffffff
        ovfl = (result != res32)
        if ovfl:
            self.write_reg(rd, res32)
            self.apsr |= 1 << QBIT
        else:
            self.write_reg(rd, result)
        log_result(res32, self.apsr)
        self.pc += 4
        return self.pc    
    
    def et32_smlad(self, word, swap_halves, sub = False):
        rd = get_field(word, 8, 11)
        ra = get_field(word, 12, 15)
        rn = get_field(word, 16, 19)
        valrn = self.read_reg(rn)
        rm = get_field(word, 0, 3)
        valrm = self.read_reg(rm)
        if swap_halves:
            valrm, carry = ror_c(valrm, 32, 16)
        result1 = extend_sign(valrn & 0xffff, 16) * extend_sign(
                              valrm & 0xffff, 16)
        result2 = ((valrn >> 16) &0xffff) * (( valrm >> 16) &0xffff)
        if sub:
            result = result1-result2
        else:
            result = result1 + result2
        if ra != 15:  # accumulate
            valra = self.read_reg(ra)
            result += valra
        self.write_reg(rd, result)
        if result != (result&0xffffffff):
            self.apsr = setBit(self.apsr, QBIT)
        log_result(result, self.apsr)
        self.pc += 4
        return self.pc 
    
    def et32_smlaw(self, word):
        rd = get_field(word, 8, 11)
        ra = get_field(word, 12, 15)
        rn = get_field(word, 16, 19)
        valrn = self.read_reg(rn)
        rm = get_field(word, 0, 3)
        valrm = self.read_reg(rm)
        m_high = testBit(word, 4)
        if m_high:
            valrm = valrm >> 16
        else:
            valrm = extend_sign(valrm & 0xffff, 16)
        result = valrn * valrm
        if ra != 15:  # accumulate
            valra = self.read_reg(ra) << 16
            result = result + valra
        result >>= 16
        self.write_reg(rd, result)
        if result != (result&0xffffffff):
            self.apsr = setBit(self.apsr, QBIT)
        log_result(result, self.apsr)
        self.pc += 4
        return self.pc 
    
    def et32_smmla(self, word, roundit, sub = False):
        rd = get_field(word, 8, 11)
        ra = get_field(word, 12, 15)
        rn = get_field(word, 16, 19)
        valrn = self.read_reg(rn)
        rm = get_field(word, 0, 3)
        valrm = self.read_reg(rm)
    
        result = valrn * valrm
        if not sub:
            if ra != 15:  # accumulate
                valra = self.read_reg(ra) << 32
                result += valra
        else:
            valra = self.read_reg(ra) << 32
            result = valra - result            
        if roundit:
            result += 0x80000000
        result  >>= 32
        self.write_reg(rd, result)
        log_result(result)
        self.pc += 4
        return self.pc         
       
        
    def et32_usad(self, word):
        rd = get_field(word, 8, 11)
        ra = get_field(word, 12, 15)
        rn = get_field(word, 16, 19)
        valrn = self.read_reg(rn)
        rm = get_field(word, 0, 3)
        valrm = self.read_reg(rm)
        absdiff1 = abs((valrn&0xff) - (valrm&0xff))
        absdiff2 = abs(((valrn>>8) &0xff) - ((valrm>>8) &0xff))
        absdiff3 = abs(((valrn>>16)&0xff) - ((valrm>>16)&0xff))
        absdiff4 = abs(((valrn>>24)&0xff) - ((valrm>>24)&0xff))
        result = absdiff1 + absdiff2 + absdiff3 + absdiff4

        if ra != 15:  # accumulate
            valra = self.read_reg(ra)
            result = result + valra
        result &= 0xffffffff
        self.write_reg(rd, result)
        log_result(result, self.apsr)
        self.pc += 4
        return self.pc         
    
    def et32_mult(self, word):
        op1 = get_field(word, 20, 22)
        op2 = get_field(word, 4, 5)
        if op1 == 0:
            if op2 == 1: # mls
                self.pc = self.et32_mul(word, sub =True)
            else:  # mul and mla
                self.pc = self.et32_mul(word, sub =False)    
        elif op1 == 1: # smla and smul + bb,bt,tb,tt
            self.pc = self.et32_mulh(word)
        elif op1 == 2: # smlad, smladx, smuad, smuadx
            swap_halves = get_field(word, 4, 4)  # x
            self.pc = self.et32_smlad(word, swap_halves, sub =False)
        elif op1 == 3:  # smlawb, smlawt, smulwb, smulwt
            self.pc = self.et32_smlaw(word)
        elif op1 == 4: # smlsd, smlsdx, smusd, smusdx
            swap_halves = get_field(word, 4, 4) # x
            self.pc = self.et32_smlad(word, swap_halves, sub =True)
        elif op1 == 5: # smmla, smmlar, smmul, smmulr
            roundit = get_field(word, 4, 4)
            self.pc = self.et32_smmla(word, roundit, sub = False)
        elif op1 == 6: # smmls, smmlsr
            roundit = get_field(word, 4, 4)
            self.pc = self.et32_smmla(word, roundit, sub = True)
        elif op1 == 7:  # usad8, usada8
            self.pc = self.et32_usad(word)
   
        return self.pc
 

    def et32_lmult_div(self, word):
        op1 = get_field(word, 20, 22)
        op2 = get_field(word, 4, 7)
        rdhi = rd = get_field(word, 8, 11)
        rdlo = get_field(word, 12, 15)
        rn = get_field(word, 16, 19)
        valrn = self.read_reg(rn)
        rm = get_field(word, 0, 3)
        valrm = self.read_reg(rm)
        if op1 == 0: # smull
            result = valrn*valrm
            self.write_reg(rdhi, (result >> 32)&0xffffffff)
            self.write_reg(rdlo, result & 0xffffffff)
        elif op1 == 1:  # sdiv
            if valrm == 0:
                result = 0   # unless IntegerZeroTrappingEnabled
            else:
                result = RoundTowardsZero(valrn, valrm)
            self.write_reg(rd, result&0xffffffff)
        elif op1 == 2:  # umull
            result = valrn*valrm
            self.write_reg(rdhi, (result >> 32)&0xffffffff)
            self.write_reg(rdlo, result & 0xffffffff)           
        elif op1 == 3:  # udiv
            if valrm == 0:
                result = 0   # unless IntegerZeroTrappingEnabled
            else:
                result = RoundTowardsZero(valrn, valrm)
            self.write_reg(rd, result&0xffffffff)
        elif op1 == 4:
            if op2 == 0: # smlal
                valrd = (extend_sign(self.read_reg(rdhi),32) << 32) | (
                         self.read_reg(rdlo) & 0xffffffff)
                result = valrn*valrm + valrd
                self.write_reg(rdhi, (result >> 32) & 0xffffffff)
                self.write_reg(rdlo, result & 0xffffffff)                  
            elif (op2&0b1100) == 0b1000: # smlal bb bt tb tt
                n_high = testBit(word, 5)
                m_high = testBit(word, 4)
                if n_high:
                    operand1 = valrn >> 16
                else:
                    operand1 = valrn & 0xffff
                if m_high:
                    operand2 = valrm >> 16
                else:
                    operand2 = valrm & 0xff
                valrd = (extend_sign(self.read_reg(rdhi), 32) << 32) | (
                             self.read_reg(rdlo) & 0xffffffff)                
                result = extend_sign(operand1, 16)*extend_sign(operand2, 16)+valrd
                self.write_reg(rdhi, (result >> 32) & 0xffffffff)
                self.write_reg(rdlo, result & 0xffffffff)                  
            elif (op2&0b1110) == 0b1100: # smlald smlaldx
                m_swap = testBit(word, 4)
                if m_swap:
                    operand2, carry = ror_c(valrm, 32, 16)
                else:
                    operand2 = valrm
                product1 = extend_sign(valrn & 0xffff, 16) * extend_sign(
                                    operand2 & 0xffff, 16)
                product2 = (valrn >> 16)*(valrm>> 16)
                valrd = (extend_sign(self.read_reg(rdhi), 32) << 32) | (
                             self.read_reg(rdlo) & 0xffffffff)
                result = product1 + product2 + valrd
                self.write_reg(rdhi, (result >> 32) & 0xffffffff)
                self.write_reg(rdlo, result & 0xffffffff)                 
        elif op1 == 5: # smlsld, smlsldx
            m_swap = testBit(word, 4)
            if m_swap:
                operand2, carry = ror_c(valrm, 32, 16)
            else:
                operand2 = valrm
            product1 = extend_sign(valrn & 0xffff, 16) * extend_sign(
                                operand2 & 0xffff, 16)
            product2 = extend_sign((valrn >> 16) & 0xffff, 16) * extend_sign(
                                (operand2 >> 16) & 0xffff, 16)
            valrd = (extend_sign(self.read_reg(rdhi), 32) << 32) | (
                     self.read_reg(rdlo) & 0xffffffff)
            result = product1 - product2 + valrd
            self.write_reg(rdhi, (result >> 32) & 0xffffffff)
            self.write_reg(rdlo, result & 0xffffffff)            
        elif op1 == 6:
            if op2 == 0:  # umlal
                valrd = (self.read_reg(rdhi) << 32) | (
                         self.read_reg(rdlo) & 0xffffffff)                
                result = valrn*valrm + valrd                 
            elif op2 == 6: # umaal
                valrdhi = self.read_reg(rdhi)
                valrdlo = self.read_reg(rdlo)
                result = valrn*valrm + valrdhi + valrdlo
            self.write_reg(rdhi, (result >> 32) & 0xffffffff)
            self.write_reg(rdlo, result & 0xffffffff)                
        else:
            log_undefined() 
        log_result(result)
        self.pc += 2    
        return self.pc
    
    def et32_coproc2(self, word):
        return self.pc+4

    def et32_lsm(self, word, st = True):
        rn = get_field(word, 16, 19)
        wback = get_field(word, 21, 21)
        r_list = get_field(word, 0, 15)
        count, regs = self.reg_list(r_list)
        if count == 0:
            log("No registers specified in load/store multiple, ignoring")
            return self.pc+4
        offset = count*4
        next_item = 4
        base_val = self.read_reg(rn)
        if not st:
            write_back_val = base_val + offset
        else:
            base_val -= offset
            write_back_val = base_val
           
        return_address = self.pc +4   # usually, unless we pop it out of regs
        for reg in regs:
            if not st:
                val = self.read_memory_int(base_val, 4, signed = True)
                self.write_reg(reg, val)
                if reg == 15:
                    return_address = val
                log("loaded = {:08x} from {:08x}".format(val, base_val))
            else:
                val = self.read_reg(reg)
                self.write_memory(base_val, 4, val)
                log("stored = {:08x} into {:08x}".format(val, base_val))
            base_val += next_item      
        if wback:    
            self.write_reg(rn, write_back_val)     
        return return_address   

        
        
    def et32_poppush(self, word, pop = True):
        #rn = get_field(word, 16, 19)  # actually, the sp
        wback = get_field(word, 21, 21)
        r_list = get_field(word, 0, 15)
        if not pop:
            r_list &= 0x5fff   # make sure 13 and 15 are not set
        count, regs = self.reg_list(r_list)
        if count == 0:
            log("No registers specified in push/pop, ignoring")
            return self.pc+4
        
        offset = count*4
        next_item = 4
        base_val = self.read_reg(SP)
        if pop:
            write_back_val = base_val + offset
        else:
            base_val -= offset
            write_back_val = base_val - offset
           
        return_address = self.pc +4   # usually, unless we pop it out of regs
        for reg in regs:
            if pop:
                val = self.read_memory_int(base_val, 4, signed = True)
                self.write_reg(reg, val)
                if reg == 15:
                    return_address = val
                log("popped = {:08x} from {:08x} into {:s}".format(val, 
                                                                   base_val, 
                                                                   get_reg(reg)))
            else:
                val = self.read_reg(reg)
                self.write_memory(base_val, 4, val)
                log("pushed = {:08x} from {:s} into {:08x}".format(val, 
                                                                   get_reg(reg), 
                                                                   base_val))
            base_val += next_item      
            
        self.write_reg(SP, write_back_val)     
        return return_address   

        

    def et32_load_store_mult(self, word):      
        op = get_field(word, 23, 24)
        l_bit = get_field(word, 20, 20)
        w_rn = (get_field(word, 21, 21) << 4) | get_field(word, 16, 19)
        if op == 1:
            if l_bit == 0:
                self.pc = self.et32_lsm(word, st = True) #stm.w
            else:
                if w_rn != 29:
                    self.pc = self.et32_lsm(word, st = False) #ldm.w
                else:
                    self.pc = self.et32_poppush(word, pop = True)
        elif op == 2:
            if l_bit == 0:
                if w_rn != 29:
                    self.pc = self.et32_lsm(word, st = True) #stmdb
                else:
                    self.pc = self.et32_poppush(word, pop = False)
                    
            else:
                self.pc = self.et32_lsm(word, st = False) #ldmdb
            
        return self.pc

    
    def et32_dp_shft_reg(self, word):
        op = get_field(word, 21, 24)
        setflags = get_field(word, 20, 20)
        rn = get_field(word, 16, 19)
        rd = get_field(word, 8, 11)
        rm = get_field(word, 0, 3)
        shift_type = get_field(word, 4, 5)
        imm3 = get_field(word, 12, 14)
        imm2 = get_field(word, 6, 7)
        imm5 = (imm3 << 2) |  imm2
        valrm = self.read_reg(rm)
        sr_type, shift_count = DecodeImmShift(shift_type, imm5)
        valrm, psr = Shift_C(sr_type, valrm, shift_count, self.apsr)
        valrn = self.read_reg(rn)        
        if (op == 0):
            if rd != 15: # and
                result = valrn & valrm
                self.write_reg(rd, result)
            else:
                if setflags == 1: # tst
                    result = valrn & valrm                   
                else:
                    log_unpredictable(word)
        elif op == 1: # bic
            result = valrn &  (~valrm)
            self.write_reg(rd, result)         
        elif op == 2:
            if rn != 15: # orr
                result = valrn | valrm
                self.write_reg(rd, result)
            else: # mov
                result = valrm
                self.write_reg(rd, result)             
        elif op == 3:
            if rn != 15: # orn
                result = valrn | (~valrm)
                self.write_reg(rd, result)
            else: # mvn
                result = valrm
                self.write_reg(rd, ~result)     
        elif op == 4:
            if rd != 15: # eor
                result = valrn ^ valrm
                self.write_reg(rd, result)              
            else:
                if setflags: # teq
                    result = valrn ^ valrm
                else:
                    log_unpredictable(word)
        elif (op == 6): # pkhbt or pkhtb
                tbform = get_field(word, 5, 5)
                if setflags or (shift_type != 0 and shift_type != 2):
                    log("Undefined pkh instruction")
                    self.pc += 4
                    return self.pc
                
                valrn = self.read_reg(rn)
                if tbform:  #tb
                    result = (valrm & 0xffff) | (valrn & 0xffff0000)
                else:       #bt
                    result = (valrn & 0xffff) | (valrm & 0xffff0000)
                self.write_reg(rd, result) 
        elif op == 8:
            if rd != 15: # add
                #  TBD needs special casing for rn == 13 (sp) or does it?           
                result = valrn + valrm
                self.write_reg(rd, result)
            else:
                if setflags:  # cmn
                    result = valrn + valrm
                else:
                    log_unpredictable(word)       
        elif op == 10: # adc 
            result, psr = AddWithCarry(valrn, valrm, self.apsr)     
        elif op == 11: # sbc 
            result, psr = AddWithCarry(valrn, ~valrm, self.apsr)         
            self.write_reg(rd, result)                   
        elif op == 13:
            if rd != 15: # sub
                # tbd special case r13 (sp) - only lsl 0-3
                result = valrn - valrm
                self.write_reg(rd, result)               
            else:
                if setflags:  # cmp
                    result = valrn - valrm
                else:
                    log_unpredictable(word)
        elif op == 14: # rsb
            result = valrm - valrn
            self.write_reg(rd, result)
                      
        if setflags:
            self.apsr = arith_cond(result, psr, testBit(psr, CBIT))            
            log_result(result, self.apsr)
        else:
            log_result(result)         
        self.pc += 4
        return self.pc
    
       
        
    def et32_dp_plain_bin_imm(self, word):
        op = get_field(word, 20, 24)
        rn = get_field(word, 16, 19)
        rd = get_field(word, 8, 11)
        setflags = False
        if (op == 0):
            if rn != 15:   # addw
                imm32 = ZeroExtend12(word)
                result = self.read_reg(rn) + imm32
                self.write_reg(rd, result)
            else:  # adr
                imm32 = ZeroExtend12(word)
                result = alignPC(self.read_reg(rn), 4) + imm32
                self.write_reg(rd, result)
        elif op == 4:   # movw
            imm32 = ZeroExtend16(word)
            result = imm32
            self.write_reg(rd, result)
        elif op == 10:
            if rn != 15:  # subw
                imm32 = ZeroExtend12(word)
                result = self.read_reg(rn) - imm32
                self.write_reg(rd, result)
            else:   # sub
                imm32 = ZeroExtend12(word)
                result = alignPC(self.read_reg(rn), 4) - imm32
                self.write_reg(rd, result)      
        elif op == 12:  # movt
            imm32 = ZeroExtend16(word)
            result = imm32  << 16
            valrd = self.read_reg(rd) & 0xffff
            result = result | valrd
            self.write_reg(rd, result)
        elif (op == 16):  # ssat
            imm2 = get_field(word, 6, 7)
            imm3 = get_field(word, 12, 14)
            imm5 = (imm3 << 2) | imm2
            sh = get_field(word, 20, 21)
            sat_imm = get_field(word, 0, 4) + 1
            result = self.read_reg(rn)
            sr_type, shift_count = DecodeImmShift(sh, imm5)
            result = Shift(result, sr_type, shift_count, self.apsr)
            result, qval = SignedSatQ(result, sat_imm)
            result = extend_sign(result, 32)
            self.write_reg(rd, result) 
            if qval:
                self.apsr |= 1 << QBIT
        elif (op == 18): # ssat16
            sat_imm = get_field(word, 0, 4) + 1
            result = self.read_reg(rn)
            result1, qval1 = SignedSatQ(result&0xffff, sat_imm)
            result1 = extend_sign(result1, 16)
            (result2, qval2) = SignedSatQ(result>>16, sat_imm)
            result2 = extend_sign(result2, 16)
            result = (result2 << 16) | (result1 & 0xffff)
            self.write_reg(rd, result) 
            if qval1  or qval2:
                self.apsr |= 1 << QBIT            
        elif op == 20: #sbfx
            lsbit = (get_field(word, 12, 14) << 2) | get_field(word, 6, 7)
            widthm1 = get_field(word, 0, 3)
            msbit = lsbit + widthm1
            valrn = self.read_reg(rn)
            valrn = get_field(valrn, lsbit, msbit)
            result = extend_sign(valrn, widthm1+1)
            self.write_reg(rd, result)
        elif op == 22:
            if rn != 15: # bfi
                lsbit = (get_field(word, 12, 14) << 2) | get_field(word, 6, 7)
                msbit = get_field(word, 0, 3)
                valrn = self.read_reg(rn) 
                valrn = get_field(valrn, 0,  msbit-lsbit)
                valrd = self.read_reg(rd)
                result = set_field(valrd, valrn, lsbit, msbit)
                self.write_reg(rd, result)
            else: #bfc
                lsbit = (get_field(word, 12, 14) << 2) | get_field(word, 6, 7)
                msbit = get_field(word, 0, 3)
                valrd = self.read_reg(rd)
                result = set_field(valrd, 0, lsbit, msbit)
                self.write_reg(rd, result)                
        elif op == 24: # usat
            imm2 = get_field(word, 6, 7)
            imm3 = get_field(word, 12, 14)
            imm5 = (imm3 << 2) | imm2
            sh = get_field(word, 20, 21)
            sat_imm = get_field(word, 0, 4) + 1
            result = self.read_reg(rn)
            sr_type, shift_count = DecodeImmShift(sh, imm5)
            result = Shift(result, sr_type, shift_count, self.apsr)
            (result, qval) = UnsignedSatQ(result, sat_imm)
            self.write_reg(rd, result) 
            if qval:
                self.apsr |= 1 << QBIT            
        elif op == 26: # usat16
            sat_imm = get_field(word, 0, 4) + 1
            result = self.read_reg(rn)
            (result1, qval1) = UnsignedSatQ(result&0xffff, sat_imm)
            (result2, qval2) = UnsignedSatQ(result>>16, sat_imm)
            result = (result2 << 16) | (result1 & 0xffff)
            self.write_reg(rd, result) 
            if qval1  or qval2:
                self.apsr |= 1 << QBIT                  
        elif op == 28: # ubfx 
            lsbit = (get_field(word, 12, 14) << 2) | get_field(word, 6, 7)
            widthm1 = get_field(word, 0, 3)
            msbit = lsbit + widthm1
            valrn = self.read_reg(rn)
            result = get_field(valrn, lsbit, msbit)
            self.write_reg(rd, result)            
        else:
            result = 0
            log_undefined()
        #if setflags: # none of these appears to set setflags
        #    self.apsr = arith_cond(result, self.apsr)
        
        log_result(result)    
        self.pc += 4
        return self.pc
    
    def et32_dp_mod_imm(self, word):
        op = get_field(word, 21, 24)
        rn = get_field(word, 16, 19)
        rd = get_field(word, 8, 11)
        setflags = testBit(word, 20)
        imm32 = ThumbExpandImm(word)
       
        test_only = False
        
        if (op == 0):
            if rd != 15:
                result = self.read_reg(rn) & imm32  # and
            else:
                if setflags:
                    result = self.read_reg(rn) & imm32  # tst
                    test_only = True
                else:
                    log_unpredictable(word)   
                    self.pc += 4
                    return self.pc
        elif op == 1:
            result = self.read_reg(rn) & (~imm32)   # bic
        elif op == 2:
            if rn != 15:
                result = self.read_reg(rn) | imm32 # orr
            else:
                result = imm32   # mov
        elif op == 3:
            if rn != 15:
                result = self.read_reg(rn) | (~imm32)   # orn
            else:
                result = ~imm32  # mvn
        elif op == 4:
            if rd != 15:
                result = self.read_reg(rn) ^ imm32 # eor
            else:
                if setflags:
                    test_only = True
                    result = self.read_reg(rn) ^ imm32  # teq
                else:
                    self.pc += 4
                    log_unpredictable(word)
                    return self.pc
        elif op == 8:
            if rd != 15:
                result = self.read_reg(rn) + imm32 # add
            else:
                if setflags:
                    test_only = True
                    result = self.read_reg(rn) + imm32   #cmn
                else:
                    self.pc += 4
                    log_unpredictable(word)  
                    return self.pc
        elif op == 10: # adc
            valrn = self.read_reg(rn)
            result, psr = AddWithCarry(valrn, imm32, self.apsr)
            if setflags:
                self.apsr |= psr
                self.apsr = logical_cond(result, self.apsr) # handle Z and N bits          
        elif op == 11:  #sbc
            valrn = self.read_reg(rn)
            result, psr = AddWithCarry(valrn, ~imm32, self.apsr)
            if setflags:
                self.apsr |= psr
                self.apsr = logical_cond(result, self.apsr) # handle Z and N bits          
        elif op == 13:
            if rd != 15:
                result = self.read_reg(rn) -imm32  # sub
            else:
                if setflags: 
                    test_only = True
                    result = self.read_reg(rn) -imm32  # cmp
                else:
                    self.pc +=4
                    log_unpredictable(word)
                    return self.pc
        elif op == 14:
            result = imm32 - self.read_reg(rn)

        if not test_only:
            self.write_reg(rd, result)
            if setflags:
                self.apsr = logical_cond(result, self.apsr)            
            log_result(result)              
        else:
            self.apsr = arith_cond(result, self.apsr, testBit(self.apsr, CBIT))
            log_cc(self.apsr)

        self.pc += 4         
        return self.pc
    
    def et32_branch_cond(self, word):
        if self.in_it_block(): 
            raise Code_Error(bna)        
        cond = get_field(word, 26, 29)
        if conditions_match(cond, self.apsr):
            j1_bit = get_field(word, 13, 13)
            j2_bit = get_field(word, 11, 11)
            s_bit =  get_field(word,  26, 26)
            imm11 =  get_field(word, 0, 10) 
            imm6  = get_field(word, 16, 21)
            imm32 = ((s_bit << 20) | (j1_bit << 19) | (j2_bit << 18) | 
                            (imm6 << 12) | (imm11 << 1))
            if s_bit:
                imm32 = extend_sign(imm32, 20)
            self.pc = self.pc + 4 + imm32
            return self.pc
        self.pc += 4
        return self.pc
    
    def et32_branch(self, word):
        if self.in_it_block(): raise Code_Error(bna)
        op = get_field(word, 20, 26)
        op1 = get_field(word, 12, 14)
        op2 = get_field(word, 8, 11)
        j1_bit = get_field(word, 13, 13)
        j2_bit = get_field(word, 11, 11)
        s_bit =  get_field(word,  26, 26)
        imm11 =  get_field(word, 0, 10) 
        if (op1&0b101) == 0:
                if (op & 0b0111000) == 0:
                    self.pc = self.et32_branch_cond(word)
        elif (op1 & 0b101) == 1:
                # branch
                if get_field(word, 12, 12) == 0:
                    #T3. armv7-M manual is missing an explanation (7-R manual OK. A8-44)
                    self.pc = self.et32_branch_cond(word)    
                else:
                    #T4
                    if self.in_it_block() and not self.last_in_it_block(): 
                        raise Code_Error(bna)                    
                    i1 = (~(j1_bit ^ s_bit)) &1
                    i2 = (~(j2_bit ^ s_bit)) &1
                    imm10 = get_field(word, 16, 25)
                    imm32 = (s_bit<<24) | (i1 << 23) | (i2 << 22) | (
                             imm10 << 12) | (imm11 << 1)
                    if s_bit: 
                        imm32 = extend_sign(imm32, 24)
                    imm32 += self.pc+4   # pc-relative
                    self.pc = imm32
        elif (op1 & 0b101) == 4:
            # "branch  with link and exchange"
            # #### not armv7-M  #####
            if self.in_it_block() and not self.last_in_it_block(): 
                raise Code_Error(bna)            
            i1 = (~(j1_bit ^ s_bit)) &1
            i2 = (~(j2_bit ^ s_bit)) &1
            imm10 = get_field(word, 16, 25)
            imm10L = imm11 >> 1
            imm32 = (s_bit << 24) | (i1 << 23) | (i2 << 22) | (
                     imm10 << 12) | (imm10L << 2)
            if s_bit: 
                imm32 = extend_sign(imm32, 24)
            imm32 += self.pc+4   # pc-relative
            # TBD set thumb bit
            self.write_reg(register_names["lr"], (self.pc+4) & address_mask)
            self.call_stack.append([self.pc, imm32])
            self.pc = imm32 
        elif (op1 & 0b101) == 5:
            # "branch with link"
            if self.in_it_block() and not self.last_in_it_block(): 
                raise Code_Error(bna)            
            i1 = (~(j1_bit ^ s_bit)) & 1
            i2 = (~(j2_bit ^ s_bit)) & 1
            imm10 = get_field(word, 16, 25)
            imm32 = (s_bit << 24) | (i1 << 23) | (i2 << 22) | (
                     imm10 << 12) | (imm11 << 1)
            if s_bit: 
                imm32 = extend_sign(imm32, 24)
            imm32 += self.pc+4   # pc-relative
            self.write_reg(register_names["lr"], (self.pc+4) & address_mask)
            self.call_stack.append([self.pc, imm32])
            self.pc = imm32                      
        
        return self.pc
    
    def et32_branch_misc_control(self, word):
        op1 = get_field(word, 12, 14)
        if op1 > 4:
            self.pc = self.et32_branch(word)
        elif op1 & 1 == 1:
            self.pc = self.et32_branch(word)
        else:
            log("TBD misc_control")
            self.pc += 4
        return self.pc
    
    def emulate_thumb32(self, word):
        """Emulate Thumb32 instruction"""
        op1 = get_field(word, 27, 28)
        op2 = get_field(word, 20, 26)
        op  = get_field(word, 15, 15)
        if op1 == 1:
            if testBit(op2, 6):
                self.pc = self.et32_coproc1(word) # includes float instructions
            elif (op2 >> 5) == 0:
                if testBit(op2, 2):
                    self.pc = self.et32_ls_dual_excl_tb(word)
                else:
                    self.pc = self.et32_load_store_mult(word)
            elif (op2 >> 5) == 1:
                self.pc = self.et32_dp_shft_reg(word)
            else:
                self.pc +=4
        elif op1 == 2:
            if op == 0:
                if testBit(op2, 5):
                    self.pc = self.et32_dp_plain_bin_imm(word)
                else:
                    self.pc = self.et32_dp_mod_imm(word) 
            else:
                self.pc = self.et32_branch_misc_control(word)
        elif op1 == 3:
            if (op2 &0b1110001) == 0:
                self.pc = self.et32_ssd(word)
            elif (op2 &0b1110001) ==0b0010000:
                self.pc = self.pc+4
                log('Instruction type not emulated') 
            elif (op2 & 0b1100111) == 1:
                self.pc = self.et32_lb(word)
            elif (op2 & 0b1100111) == 3:
                self.pc = self.et32_lh(word)       
            elif (op2 & 0b1100111) == 5:
                self.pc = self.et32_lw(word)          
            elif (op2 & 0b1100111) == 7:
                self.pc = self.pc+4
                log_undefined() 
            elif (op2 & 0b1110000) == 0b0100000:
                self.pc = self.et32_dpr(word)
            elif (op2 & 0b1111000) == 0b0110000:
                self.pc = self.et32_mult(word)
            elif (op2 & 0b1111000) == 0b0111000:
                self.pc = self.et32_lmult_div(word)
            elif (op2 & 0b1000000) != 0:
                self.pc = self.et32_coproc2(word)            
        else:
            self.pc += 4
        return self.pc
    
    def emulate_thumb(self, word):
        if is_thumb32(word):
            rev_word = ((word&0xffff) << 16) | (word >> 16)
            self.pc = self.emulate_thumb32(rev_word)
        else:
            self.pc = self.emulate_thumb16(word)
        return self.pc
    
    #--------------------------------------------------------------------    
    #def Shift_C(sh_type, val, shift_count, psr)
    #   return result, psr
    
    def do_shift(self, shift_type, val, shift_count, set_cond_code):
        # implement the shift, TBD replace with Shift_C
        retval = val
        if shift_type == 0:   #lsl
            if shift_count == 0:
                #log("lsl 0 has no effect")
                return retval
            retval <<= shift_count
            retval &= 0xffffffff
            if set_cond_code:
                set_field(self.pc, testBit(val, (32-shift_count)), CBIT, CBIT)
        elif shift_type == 1: #lsr
            if shift_count == 0:
                log("lsr 0 has no effect")
                return retval
            retval >>=shift_count
            if set_cond_code:
                set_field(self.pc, testBit(val, (shift_count-1)), CBIT, CBIT)
        elif shift_type == 2:  #asr
            if shift_count == 0:
                log("asr 0 has no effect")
                return retval
            if retval >=0:
                retval >>= shift_count
            else:
                mask = 0xffffffff
                retval >>= shift_count
                mask >>= shift_count
                mask = ~mask
                retval |= mask
            if set_cond_code:
                set_field(self.pc, testBit(val, shift_count-1), CBIT, CBIT)
               
        elif shift_type == 3: #ror
            if shift_count == 0:  # rrx, rotate right extended
                retval >>= 1
                if set_cond_code:
                    set_field(self.pc, testBit(val, 0), CBIT, CBIT)
                    set_field(retval, testBit(self.pc, CBIT), 31, 31)
            else:
                retval  >>= shift_count
                tmp = val << (32-shift_count)
                retval = retval | tmp
                if set_cond_code:
                    set_field(self.pc, testBit(val, (shift_count-1)),
                              CBIT, CBIT)
    
        return retval    
    
    def do_op(self, lhs_val, operand, rhs_val, set_cond_code):
        #log("do_op: {:08x} {:s} {:08x}".format(lhs_val, 
        #                                             dp_opcodes[operand], 
        #                                             rhs_val))
        cond_code = 0
        carry = testBit(self.pc, CBIT)
        if operand == 0:     # and 
            result = lhs_val & rhs_val
            if set_cond_code: 
                cond_code = logical_cond(result, cond_code)
        elif operand == 1:   # eor
            result = lhs_val ^ rhs_val
            if set_cond_code: 
                cond_code = logical_cond(result, cond_code)
        elif operand == 2:   # sub
            result = lhs_val - rhs_val
            carry = 1 if lhs_val >= rhs_val else 0
            if set_cond_code: 
                cond_code = arith_cond(result, cond_code, carry)
        elif operand == 3:   # rsb
            result = rhs_val - lhs_val
            carry = 1 if rhs_val >= lhs_val else 0
            if set_cond_code: 
                cond_code = arith_cond(result, cond_code, carry)        
        elif operand == 4:   # add 
            result = lhs_val + rhs_val
            carry = 1 if result.bit_length() > 32 else 0
            if set_cond_code: 
                cond_code = arith_cond(result, cond_code, carry)        
        elif operand == 5:   # adc
            result, psr = AddWithCarry(lhs_val, rhs_val, self.apsr)
            if set_cond_code:
                self.apsr |= psr
                self.apsr = logical_cond(result, self.apsr) # handle Z and N bits       
        elif operand == 6:   # sbc
            result, psr = AddWithCarry(lhs_val, ~rhs_val, self.apsr)
            if set_cond_code:
                self.apsr |= psr
                self.apsr = logical_cond(result, self.apsr) # handle Z and N bits      
        elif operand == 7:   # rsc
            result = rhs_val - lhs_val -1 + carry
            if set_cond_code: 
                cond_code = arith_cond(result, cond_code, carry)        
        elif operand == 8:   # tst
            result = lhs_val & rhs_val
            if set_cond_code: 
                cond_code = logical_cond(result, cond_code)       
        elif operand == 9:   # teq
            result = lhs_val ^ rhs_val
            if set_cond_code: 
                cond_code = logical_cond(result, cond_code)     
        elif operand == 10:  # cmp
            result = lhs_val - rhs_val
            carry = 1 if lhs_val >= rhs_val else 0
            if set_cond_code: 
                cond_code = arith_cond(result, cond_code, carry)        
        elif operand == 11:  # cmn
            result = lhs_val + rhs_val
            carry = 1 if lhs_val >= rhs_val else 0
            if set_cond_code: 
                cond_code = arith_cond(result, cond_code, carry)        
        elif operand == 12:  # orr 
            result = lhs_val | rhs_val
            if set_cond_code: 
                cond_code = logical_cond(result, cond_code)        
        elif operand == 13:  # mov
            result =  rhs_val
            if set_cond_code: 
                cond_code = logical_cond(result, cond_code)        
        elif operand == 14:  # bic 
            result = lhs_val & ~rhs_val
            if set_cond_code: 
                cond_code = logical_cond(result, cond_code)        
        elif operand == 15:  # mvn
            result =  -rhs_val
            if set_cond_code: 
                cond_code = logical_cond(result, cond_code)        
        log_result(result, cond_code)   
        return result, cond_code
    
    def branch(self, offset, word, cond_code):
        """ Branch/Branch and link. Also blx to halfword, offset."""
        if self.in_it_block(): raise Code_Error(bna)
        # Handle condition codes-- need to read psr
        if get_field(word, 28, 31) == 31:  # no conditions on this
            if testBit(word, 24):
                halfword_offset = 2
            else:
                halfword_offset = 0
            opcode = "blx"
            self.write_reg(register_names["lr"], (self.pc+4) & address_mask)
            setBit(self.apsr, THUMBBIT)
            self.thumb_mode = True
            dest = armcpu.get_dest(offset, get_field(word, 0,23))
            dest += halfword_offset
            if len(self.call_stack) > 0:
                self.call_stack.pop()            
            return dest
           
 
        if testBit(word, 24):
            opcode = "bl"
            self.write_reg(register_names["lr"], (self.pc+4) & address_mask)
        else:
            opcode = "b"
        if conditions_match(cond_code, self.pc):  # ARM only - apsr better?
            dest = armcpu.get_dest(offset, get_field(word, 0,23))
            if opcode == "bl":
                self.call_stack.append([self.pc, dest])
        else:
            dest = self.pc + 4
            
        return dest
    
    def branch_exchange(self, offset, word, cond_code):
        """ Handle switching in and out of thumb mode """
        if self.in_it_block() and not self.last_in_it_block(): 
            raise Code_Error(bna)
        rn = self.read_reg(get_field(word, 0,3))
        # rn != pc
         
        if testBit(rn, 0): 
            self.thumb_mode = True
            self.apsr = setBit(self.apsr, THUMBBIT)
        else:
            self.thumb_mode = False 
            self.apsr = clearBit(self.apsr, THUMBBIT)
        self.pc = rn & address_mask
        if testBit(word, 5):
            # blx
            self.write_reg(register_names["lr"], 
                           (self.pc+4) & address_mask)
        else:
            # bx
            pass
        if len(self.call_stack) > 0:
            self.call_stack.pop()
        return self.pc

    
    def data_processing(self, offset, word, cond_code):
        """ Emulate a data processing instruction. """      
        val = int(0)
        operand = get_field(word, 21, 24)
        opcode = dp_opcodes[operand] 
        set_cond_codes = False
        if testBit(word, 20):
            set_cond_codes = True
        if (opcode == "cmn") or (opcode == "cmp") or (opcode == 
                      "tst") or (opcode == "teq"):        
            set_cond_codes = True   # always for comparisons and tests
    
        # RD, no destination for test and compares
        write_dest = False
        if (opcode != "cmn") and (opcode != 
                      "cmp") and (opcode != 
                      "tst") and (opcode !=  
                      "teq"):
            dest_reg=get_field(word, 12, 15)
            write_dest = True
        # <lhs>  no lhs for move
        if (opcode != "mov") and (opcode != "mvn"):
            lhs_val = self.read_reg(get_field(word, 16, 19))
            use_lhs_val = True
        else:
            use_lhs_val = False
            lhs_val = 0
        # <rhs>
        if testBit(word, 25):
            rhs_val = armcpu.get_imm(get_field(word,8,11), get_field(word, 0,7))
        else:
            # rm
            rm = self.read_reg(get_field(word,0,3))
            if testBit(word, 4):  # reg shift
                shift_type = armcpu.get_shift_type(word)
                shift_count = self.read_reg(get_field(word, 8, 11))
                shift_count &= 0xff
            else:                 # immediate shift
                shift_count = get_field(word, 7, 11)
                shift_type = armcpu.get_shift_type(word)
               
            rhs_val = self.do_shift(shift_type, rm, shift_count, 
                                    set_cond_codes)
    
        result, self.apsr = self.do_op(lhs_val, operand, rhs_val, set_cond_codes)
       
        if write_dest:  
            self.write_reg(dest_reg, result)
            if dest_reg == 15:
                return self.pc
  
        return self.pc+4
    
    def count_leading_zeros(self, word, cond_code):
        """ clz. rd gets the count of leading zeros in rm  """
        rm = self.read_reg(get_field(word, 0, 3))
        i = CountLeadingZeroBits(rm)
        rd = get_field(word, 12, 15)
        # rd != 15
        self.write_reg(rd, i)
        log_result(i)
        return self.pc+4
    
    def single_data_transfer(self, word, cond_code):
        """ Emulate ldr and str instructions. """
        write_address_back = False; force_nonp = False; load_mem = False   
        immed = False if testBit(word, 25) else True
        if testBit(word, 24):
            pre = True
            write_address_back = True if testBit(word, 21) else False
        else: 
            pre = False
            force_nonp = True if testBit(word, 21) else False
        add_to_base = True if testBit(word, 23) else False 
        transfer_size = 1 if testBit(word, 22) else 4
     
        if testBit(word, 20):
            load_mem = True
            opcode = "ldr"
        else:
            load_mem = False
            opcode = "str"

        # rd
        source_dest_reg=get_field(word, 12, 15)
        # get source/destination address
        base_reg = get_field(word, 16,19)
        base_reg_val = self.read_reg(base_reg)
        if base_reg == 15:
            base_reg_val &= address_mask   
            # TBD can of worms - I'm using pc as the execute pointer -- need to
            # model the ARM better
            base_reg_val += 8
        
        if immed:
            offset = get_field(word, 0,11)
            if offset != 0:
                if add_to_base:
                    offset =  + offset
                else:   
                    offset = - offset
        else:  #reg and shift
            rm = self.read_reg(get_field(word,0,3))
            if testBit(word, 4):  # reg shift
                shift_type = armcpu.get_shift_type(word)
                shift_count = self.read_reg(get_field(word, 8, 11))
                shift_count &= 0xff
            else:                 # immediate shift
                shift_count = get_field(word, 7, 11)
                shift_type = armcpu.get_shift_type(word)
            # TBD subtleties here   
            offset = self.do_shift(shift_type, rm, shift_count, 
                              set_cond_code = False)       
       
        if pre: 
            source_dest_address = base_reg_val + offset
        #halfword boundaries
        if (source_dest_address % 4) == 2:
            log("Halfword aligned address NYI")        
        if load_mem:
            # get mem from base address and write to rd
            #TBD watch out for size (need padding? )

            val = self.read_memory_int(source_dest_address, transfer_size, signed = True)
            self.write_reg(source_dest_reg, val)
            log("Loaded = {:08x} from {:08x}".format(val, source_dest_address))
        else:
            #store rd into addr
            val = self.read_reg(source_dest_reg)
            self.write_memory(source_dest_address, transfer_size, val)
            log("Stored = {:08x} into {:08x}".format(val, source_dest_address))
        if not pre:
            source_dest_address = self.read_reg(base_reg) + offset

   
        if write_address_back: # write back into base reg
            self.write_reg(base_reg, source_dest_address)
            
            
        if base_reg == 15:  
            pass 
        if load_mem and source_dest_reg == 15:
            return self.pc

                 
        return self.pc+4
    
    def single_data_transfer_hd(self, word, cond_code):
        """ Emulate ldr and str instructions. """
        write_address_back = False; force_nonp = False; load_mem = False   
         
        if testBit(word, 24):
            pre = True
            write_address_back = True if testBit(word, 21) else False
        else: 
            pre = False
            force_nonp = True if testBit(word, 21) else False
        add_to_base = True if testBit(word, 23) else False 
        
        if testBit(word, 22): 
            use_offset = True
            offset = get_field(word, 8, 11) << 4
            offset |= get_field(word, 0, 3)
        else: 
            use_offset = False
            
        sh_bits = get_field(word, 5, 6)
        if sh_bits == 0:
            return "Error: swp instruction detected in wrong routine"            
     
        if testBit(word, 20):
            load_mem = True
            opcode = "ldr"
        else:
            if sh_bits == 2:
                load_mem = True
                opcode ="ldr"
            else:
                load_mem = False
                opcode = "str"
                
        if testBit(word, 20):
            if sh_bits == 1:
                transfer_size = 2
            elif sh_bits == 2:
                transfer_size = 1
                signed = True
            elif sh_bits == 3:
                transfer_size = 2
                signed = True
        else:
            if sh_bits == 1:
                signed = False
                transfer_size = 2
            elif sh_bits == 2:
                transfer_size = 8
            elif sh_bits == 3:
                transfer_size = 8               

        # rd
        source_dest_reg=get_field(word, 12, 15)
        # get source/destination address
        base_reg = get_field(word, 16,19)
        base_reg_val = self.read_reg(base_reg)
        if base_reg == 15:
            base_reg_val &= address_mask   
            # TBD can of worms - I'm using pc as the execute pointer -- need to
            # model the ARM better
            base_reg_val += 8
        
        if use_offset:
            offset = get_field(word, 0,11)
        else:
            offset = self.read_reg(get_field(word,0,3))
        if offset == 0:
            offset = base_reg_val
        else:
            if add_to_base:
                offset =  base_reg_val + offset
            else:   
                offset = base_reg_val - offset
     
       
        if pre: 
            source_dest_address = offset
        else: 
            source_dest_address = base_reg_val

        if load_mem:
            # get mem from base address and write to rd
            #TBD watch out for size (need padding? )

            val = self.read_memory_int(source_dest_address, transfer_size, signed = True)
            self.write_reg(source_dest_reg, val)
            log("Loaded = {:08x} from {:08x}".format(val, source_dest_address))
        else:
            #store rd into addr
            val = self.read_reg(source_dest_reg)
            self.write_memory(source_dest_address, transfer_size, val)
            log("Stored = {:08x} into {:08x}".format(val, source_dest_address))
        if not pre:
            source_dest_address = self.read_reg(base_reg) + offset

   
        if write_address_back: # write back into base reg
            self.write_reg(base_reg, source_dest_address)
            
            
        if base_reg == 15:  
            pass 
        if load_mem and source_dest_reg == 15:
            return self.pc
       
        return self.pc+4
        
    def mult(self, word, cond_code):
        """ 32-bit multiply (possible accumulate) resulting in 32-bit """
        # signed and unsigned arithmetic work the same here
        rm = self.read_reg(get_field(word, 0, 3))
        rs = self.read_reg(get_field(word, 8, 11))
        val = rm*rs
        
        if testBit(word, 21):
            #rn  accumulator
            rn =self.read_reg(get_field(word, 12, 15))
            val += rn
        #rd
        self.write_reg(get_field(word, 16, 19), val&0xffffffff)        
        if testBit(word, 20):
            if val == 0:
                setBit(self.pc, ZBIT)
            elif testBit(val, 31):
                setBit(self.pc, NBIT)
        
        log_result(val, self.apsr)
        return self.pc+4    
    

        
    def mult_long(self, word, cond_code):
        """ 32-bits*32-bits with 64-bit result """
        signed = True if testBit(word, 21) else False
        #rm
        rm = self.read_reg(get_field(word, 0, 3))
        if signed: rm = extend_sign(rm, 32)
        #if testBit(rm, 31) and signed:
        #   rm = -((-rm)&0x7fffffff)   # extend the sign
        #rs
        rs = self.read_reg(get_field(word, 8, 11))
        if signed: rs = extend_sign(rs, 32)
        val = rm*rs
        
        if testBit(word, 21):
            #rdhi  accumulator
            rn =self.read_reg(get_field(word, 16, 19)) 
            if signed: rn = extend_sign(rn, 32)
            rn <<= 32
            # rdlo
            rn |=self.read_reg(get_field(word, 12, 15))
            val += rn
        #rd
        self.write_reg(get_field(word, 16, 19), (val&0xffffffff00000000)>>32) 
        self.write_reg(get_field(word, 12, 15), val&0xffffffff)
        
        if testBit(word, 20):
            if val == 0:
                setBit(self.pc, ZBIT)
            elif testBit(val, 63):
                if signed:
                    setBit(self.pc, NBIT)
        ccs = self.pc >> 28
        log_result(val, self.apsr)
        return self.pc+4                
        
    def swp(self, word, cond_code):
        if testBit(word, 22): 
            transfer_size = 1 
        else:
            transfer_size = 4

        # rd, rm, [rn] ; rd = [rn], [rn] = rm
        # rn, base register
        rn = self.read_reg(get_field(word, 16, 19))        
        # rd
        val = self.read_memory_int(rn, transfer_size, signed = True)
        rd = get_field(word, 12, 15)
        self.write_reg(rd, val)
        # rm
        rm = self.read_reg(get_field(word, 0, 3))
        self.write_memory(rn, transfer_size, rm)
        log("Result, r{:d} gets {:x}, {:x} gets {:x}".format(
                                get_field(word, 12, 15), val, rn, rm))
        
        return self.pc+4
    

        
        
    def block_data_transfer(self, word, cond_code):
        """ LDM, STM variants. Special case pop and push if using sp. """
        base_reg = get_field(word, 16, 19)
        base_val = self.read_reg(base_reg)
        pre = True if testBit(word, 24) else False
        add_to_base = True if testBit(word, 23) else False
        load_psr = True if testBit(word, 22) else False
        write_back_address = True if testBit(word, 21) else False
        load_mem = True if testBit(word, 20) else False
        register_bits = get_field(word, 0, 15)
        count, regs = self.reg_list(register_bits)

        if count == 0:
            log("No registers specified in block data transfer, ignoring")
            return self.pc+4
        
        offset = count*4
        next_item = 4
        if not add_to_base:
            base_val -= offset
            write_back_val = base_val
        else:
            #base_val stays same
            write_back_val = base_val + offset
         
        if pre:
            if add_to_base:
                base_val += next_item
        else:
            if not add_to_base:
                base_val += next_item
                
        return_address = self.pc +4   # usually, unless we pop it out of regs
        for reg in regs:
            if load_mem:
                val = self.read_memory_int(base_val, 4, signed = True)
                self.write_reg(reg, val)
                if reg == 15:
                    return_address = val
                log("Loaded = {:08x} from {:08x}".format(val, base_val))
            else:
                val = self.read_reg(reg)
                self.write_memory(base_val, 4, val)
                log("Stored = {:08x} into {:08x}".format(val, base_val))
            base_val += next_item
            
            
        if write_back_address:
            self.write_reg(base_reg, write_back_val)
        # tbd psr handling
        #       if base_reg == 15:  if load_mem and source_dest_reg == 15
        #       return self.pc        
         
        return return_address   
    
    def coprocessor_data_transfer(self, word, cond_code):
        """ldc, stc instructions. """
        # TBD. There are so many more instructions here
        opcode = "ldc" if testBit(word, 20) else  "stc"
        if testBit(word, 28):
            opcode += "2" 
        else: 
            opcode += cond(cond_code)
        if testBit(word, 22): opcode += "l"
        log("{:s} p{:d}, c{:d}, [r{:d} + 0x{:x}]".format(
            opcode,
            get_field(word, 8, 11),
            get_field(word, 12, 15),
            get_field(word, 16, 19),
            get_field(word, 0,7)*4))  

        log("Not emulated, treated as nop")
        return self.pc+4  
    
    def swi_or_coproc(self, word):
        """ SWI and coprocessor instructions. Opcode 7. """
        # TBD. Many more instructions
        if testBit(word, 24): 
            log("SWI software interrupt {:x}".format(get_field(word, 0, 23)))
        elif testBit(word, 4):    #mrc/mcr
            opcode = "mrc" if testBit(word, 20) else "mcr"  # mcr arm -> cop

            log("{:s} p{:d}, {:d}, r{:d}, c{:d}".format(
                    opcode, 
                    get_field(word, 8,  11) ,
                    get_field(word, 21, 23),
                    get_field(word, 12, 15),
                    get_field(word, 16, 19)))
        else: #cdp   
            if get_field(word, 28, 31) == 15:
                opcode = "cdp2" 
            else:
                opcode = "cdp"
                log("{:s} p{:d}, {:d}, c{:d},c{:d},c{:d}, {:d} ".format(
                        opcode, 
                        get_field(word, 8, 11),
                        get_field(word, 20, 23),
                        get_field(word, 12, 15),
                        get_field(word, 16, 19),
                        get_field(word, 0, 3),
                        get_field(word, 5,7)))
        log("Not emulated, treated as nop")
        return self.pc+4
    
    def emulate(self, word):
        """ Emulate a single instruction. Updates and returns self.pc """
        
        # Log disassembly for the instruction and check the condition codes 
  
        addr = self.pc & address_mask
        log("{:08x}  ".format(addr), end = "")
        
        res, instr_size = disass(addr,  word, self.thumb_mode) 
        log(res)
        
        if self.thumb_mode:
            if self.in_it_block():
                cond = self.itstate >> 4
                self.it_advance()
                if not conditions_match(cond, self.apsr):
                    log("Instruction in if-then block skipped "
                        "(condition doesn't match). ")
                    self.pc += instr_size 
                    return self.pc
            
            return self.emulate_thumb(word)   #---------------->
            
        # ARM Instructions
        cond_code = get_field(word, 28, 31)
        ins_type = get_field(word, 25, 27)            
        if not conditions_match(cond_code, self.apsr):
            log("Instruction skipped (condition doesn't match). ")
            self.write_reg(PC, self.pc + instr_size)  
            return self.pc 
        
        if ins_type == 0:
            if (word & 0x0fffff00) == 0x012fff00:
                self.pc = self.branch_exchange(self.pc, word, cond_code)
                return self.pc
            if testBit(word, 4) and testBit(word, 7):
                four_seven = get_field(word, 4, 7)
                if four_seven == 9:
                    if (get_field(word, 22, 27) == 0): 
                        self.pc = self.mult(word, cond_code)
                    elif get_field(word, 23, 27) == 1:
                        self.pc = self.mult_long(word, cond_code)
                    elif get_field(word, 23, 27) == 2:
                        if (get_field(word, 20, 21) == 0):
                            self.pc = self.swp(word, cond_code)
                        else:
                            print("Unidentified instruction {:x}".format(word))
                else:
                    # ldrh, ldrd and stores
                    self.pc = self.single_data_transfer_hd(word, cond_code)
     
            else:  
                if (word & 0x0fff0ff0) == 0x016f0f10:
                    self.pc = self.count_leading_zeros(word, cond_code)
                    return  self.pc          
                # a DP type with shift
                # if bit 25 is zero, operand 2 is a register (possibly shifted) 
                # if bit 4 is zero, 5,6 are shift type, 7-11 are shift count
                # if bit 4 is 1, bit 7 is zero, bit 5-6 are shift type 8-11 are 
                # shift reg.
                # So bits 4 and 7 cannot be both set            
                self.pc = self.data_processing(self.pc, word, cond_code)
        elif ins_type ==1:
            self.pc = self.data_processing(self.pc, word, cond_code)
            
        elif ins_type ==2 or ins_type == 3:
            self.pc = self.single_data_transfer(word, cond_code)
        elif ins_type ==4:
            self.pc = self.block_data_transfer(word, cond_code)
        elif ins_type ==5:
            self.pc = self.branch(self.pc, word, cond_code)
        elif ins_type ==6:
            self.pc = self.coprocessor_data_transfer(word, cond_code)
        elif ins_type ==7:
            self.pc = self.swi_or_coproc(word)
        else:
            log_undefined()
        return self.pc   
            
#---------------------------------------------------------------------- 
    
    
#-------------------------Unit test support----------------------------

def show_mem(cpu):
    """ derived from the one in dbg """
    chunk = 0
    chunk_count = len(cpu.memory)
    while chunk < chunk_count:  
        chunk_start = cpu.memory[chunk][MEMADDR]
        chunk_end = chunk_start + cpu.memory[chunk][MEMSIZE] 
        log("{:d} {:#x}..{:#x}".format(chunk, chunk_start, chunk_end))
        #for i in range(cpu.memory[chunk][MEMSIZE]):
        #    if (i%2) ==1:
        #        print("{:2x} {:02x}{:02x}".format(i-1,
        #        cpu.memory[chunk][MEMVALS][i], cpu.memory[chunk][MEMVALS][i-1]))
        chunk += 1
    if len(cpu.high_memory) != 0:
        log("High memory")
        for addr in sorted(cpu.high_memory):
            log("{:#x}".format(addr))  
            
def reverse_hw(word):
    rev_word = ((word & 0xffff) << 16) | ((word >> 16) & 0xffff)
    return rev_word

def do_steps(last_addr):
    i = 0
    while cpu.pc < last_addr:
        instr = cpu.read_memory_int(cpu.pc, 4)
        if instr == 0: 
            print("Zero instr, ending")
            return
        if not cpu.thumb_mode:
            siz = 4
        elif is_thumb32(instr):
            siz = 4
        else:
            siz = 2
        instr = cpu.read_memory_int(cpu.pc, siz)
        print("------instr = {:#x} ------".format(instr))
        cpu.stepi()
        i += 1    

def step_through(instr_block):
    addr = 0
    for i in range(len(instr_block)):
        instr = instr_block[i]
        if (instr & 0xffff) != instr:
            siz = 4
            if cpu.thumb_mode:
                instr = reverse_hw(instr & 0xffffffff)
        else:
            siz = 2
            instr = instr & 0xffff  
        cpu.setup_memory(instr.to_bytes(siz, 'little'), addr)
        addr += siz
    #show_mem(cpu)   
    cpu.pc = 0
    cpu.loaded = True
    do_steps(addr)

def step_through_with_address(instr_block):
    """ addresses are discontiguous """
    addr = 0
    for i in range(len(instr_block)):
        if (i %2) == 0:
            addr = instr_block[i]
            instr = instr_block[i+1]
            if (instr & 0xffff) != instr:
                siz = 4
                if cpu.thumb_mode:
                    instr = reverse_hw(instr&0xffffffff)
            else:
                siz = 2
                instr = instr & 0xffff  
            cpu.setup_memory(instr.to_bytes(siz, 'little'), addr)
    #show_mem(cpu)
    cpu.pc = instr_block[0]
    cpu.loaded = True
    do_steps(cpu.get_last_address())
    
if __name__ == '__main__':
    
    log("*** armcpu.py ***")
    cpu=ArmCpu("")
    # This is not a program, just some random instructions pulled from an image
    # TBD write a program that actually sets up valid inputs and outputs and
    # checks them. See asm_test.
    cpu.thumb_mode = True
    instr_block = [
         0x207f, # MOV  R0, #0x7f
         0x257f, # MOV  R5, #0x7f
         0x2710, # MOV  R7, #0x10
         0x0441, # LSL  R1, R0, #0x11  fe0000
         0x2800, # CMP  R0, #0x0
         0x0968, # LSR  R0, R5, #0x5  3
         0x144a, # ASR  R2, R1, #0x11  7f
         0x1846, # ADD  R6, R0, R1  fe0003
         0x3E74, # SUB  R6, #0x74  fdff8f
         0x00CF, # LSL  R7, R1, #0x3  7f00000
        
         0x2410, # MOV  R4, #0x10  16
         0x41E4, # ROR  R4, R4  0x10000
         0xBFD8, # IT   LE
         0x1C41, # ADD  R1, R0, #0x1  4
         0x2371, # MOV  r3, #0x71
        
         0x207f, # MOV  R0, #0x7f
         0x2800, # CMP  R0, #0x0       ; ne
         0xbf07,     # ITTEE  EQ           ; Next 4 instructions are conditional
         0x1c08,     # MOVEQ  R0, R1       ; Conditional move
         0x3210,     # ADDEQ  R2, R2, #0x10  ; Conditional add
         0xF0030301, # ANDNE  R3 R3,#1      ; Conditional and
         0xF000B802, # BNE.W  dloop ; Branch instruction can only be 
                            #   ; used in the last instruction of an IT block 
         0xF1020201, # ADDEQ  R2, R2, #1 
    #dloop:
         0xbfc8, # IT     GT ; IT block with only one conditional
                                 #           ;instruction    
         0x1C49, # ADDGT  R1, R1,#1  ; Increment R1 conditionally
          
         0x2809, # CMP    R0,#9 ; Convert R0 hex value (0 to 15)
                                 #               ; into ASCII 
                                 #               ; ('0'-'9', 'A'-'F')
         0xbfcc, # ITE    GT  ; Next 2 instructions are conditional
         0xF1000137, # ADDGT  R1, R0,#55  ; Convert 0xA -> 'A'
         0xF1000130, # ADDLE  R1, R0,#48  ; Convert 0x0 -> '0'
          
         0xbf1a,     # ITTE   NE         ; Next 3 instructions are conditional
         0x4008,     # ANDNE  R0, R0, R1 ; ANDNE does not update
                     #                   ; condition flags
         0xF1120201, # ADDSNE R2, R2,#1  ; updates condition flags
         0x1C1A,     # MOVEQ  R2, R3     ; Conditional move 
         0xf2480d00, # mov      sp, #32768 (0x8000)
         0xe92d1fff  # push {r0-r13}
    ]
    step_through(instr_block)
    
    das_strings.clear()
    cpu=ArmCpu("")
    cpu.thumb_mode = True
    instr1 = [
    0x207f,      # MOV  R0, #0x7f
    0x237f,      # MOV  R3, #0x7f
    0xea404003,  # orr.w   r0, r0, r3, lsl #16  7f007f
    0xEEf60a00,  # VMOV   S1, #5.000000e-01
    0xEEB70a00,  # VMOV   S0, #1.000000e+00
    0xEEb60a00,  # VMOV   S0, #5.000000e+01
    0xEE600a80,  # vMUL   S1, S1, S0   s1 <= s1*s0
    0xEE600aa0,  # vMUL   S1, S1, S1  (0.25)
    0xEEB11a60,  # vneg/FNEGS   S2, S1 (0.0625)
    0xEEB11a41,  # vneg/FNEGS   S2, S2  (-0.0625)
    0xEEB41ac0,  # vcmpe/FCMPES  S2, S0  (0.0625)
    0xEEF1FA10,  # VMSR    PC, FPSCR
    0xEE010a60,  # vmls    S0, S2, S1  (0.49094)
    0xEE000a90]  # vMSR    S1, R0  (0.0)
    step_through(instr1)
    
    das_strings.clear()
    cpu=ArmCpu("")
    cpu.thumb_mode = False
    instr2 = [0,      0xea0020ce,  # b       0x8340 ( cpu.emulate(int(0xea0020ce)))
              0x8340, 0x9afffffb,  # bls     847c
              0x8334, 0xebffffba,  # bl      8584
              0x8224, 0x8afffffb,  # bhi     8020
              0x8228, 0xeaffff7d,  # b       8020
              0x8020, 0xe1a00000,  # nop 
              0x8024, 0xe7831102,  # str     r1, [r3, r2, lsl #2]
              0x8028, 0xe3c1000f,  # bic     r0, r1, #15
              0x802c, 0xe3550006,  # cmp     r5, #6
              0x8030, 0xe1720001,  # cmn     r2, r1
              0x8034, 0xe3720001,  # cmn     r2, #1
              0x8038, 0xe15b0000,  # cmp     fp, r0
              0x803c, 0xe3a0d902,  # mov      sp, #32768 (0x8000)
              0x8040, 0xc3e06000,  # mvngt   r6, #0
              0x8044, 0xe1a00000,  # nop
              0x8048, 0xe3300000,  # teq      r0, #0 (0x0)
              0x804c, 0xe2810049,  # add      r0, r1, #73 (0x49)
              0x8050, 0xe2522001,  # subs     r2, r2, #1 (0x1)
              0x8054, 0xe1a00000,  # nop
              0x8058, 0xe2602000,  # rsb     r2, r0, #0
              0x805c, 0xe0696006,  # rsb     r6, r9, r6
              0x8060, 0xe0692189,  # rsb     r2, r9, r9, lsl #3
              0x8064, 0xe1b000c0,  # asrs    r0, r0, #1
              0x8068, 0xe1a00c40,  # asr     r0, r0, #24
              0x806c, 0xe1811002,  # orr     r1, r1, r2
              0x8070, 0xe19ccc06,  # orrs    ip, ip, r6, lsl #24
              0x8074, 0xe0022003,  # and     r2, r2, r3
              0x8078, 0xe21660ff,  # ands    r6, r6, #255 
              0x807c, 0xe1a032a2,  # lsr     r3, r2, #5
              0x8080, 0xe1a03213,  # lsl     r3, r3, r2
              0x8084, 0xe1a03103,  # lsl     r3, r3, #2
              0x8088, 0xe16f2f11,  # clz     r2, r1
              0x808c, 0xe7930100,  # ldr     r0, [r3, r0, lsl #2]
              0x8090, 0xe1c000d4,  # ldrd    r0, [r0, #4]
              0x8094, 0xe1d330b0,  # ldrh    r3, [r3]
              0x8098, 0xe1c230b0,  # strh    r3, [r2]
              0x809c, 0xe5d67000,  # ldrb    r7, [r6]
              0x80a0, 0x259fc050,  # ldrcs   ip, [pc, #80]
              0x80a4, 0xe1a00000,  # nop
              0x80a8, 0x05c32004,  # strbeq  r2, [r3, #4] 
              0x80ac, 0xe1a00000,  # nop
              0x80b0, 0xe0200391,  # mla     r0, r1, r3, r0
              0x80b4, 0xe0010190,  # mul     r1, r0, r1
              0x80b8, 0xe3a01902,  # mov      r1, #32768 (   0x8028, 0x8000)
              0x80bc, 0xe3a02015,  # mov      r2, #21 (      0x8028, 0x15)
              0x80c0, 0xe0854291,  # umull     r4, r5, r1, r2
              0x80c4, 0xe0a54291,  # umlal     r4, r5, r1, r2
              0x80c8, 0xe0c54192,  # smull     r4, r5, r2, r1
              0x80cc, 0xe0e54291,  # smlal     r4, r5, r1, r2  
              0x80d0, 0xe0954291,  # umulls    r4, r5, r1, r2
              0x80d4, 0xe0b54291,  # umlals    r4, r5, r1, r2
              0x80d8, 0xe0d54192,  # smulls    r4, r5, r2, r1
              0x80dc, 0xe0f54291,  # smlals    r4, r5, r1, r2                
              0x80e0, 0xe98d0006,  # stmib   sp, {r1, r2}
              0x80e4, 0xb8bd0010,  # poplt   {r4}
              0x80e8, 0xe1a00000]  # nop
              # need to load up lr
              #0x80ec, 0xe12fff1e,  # bx      lr
              #0x80f0, 0x012fff1e,  # bxeq    lr
              #0x80f4, 0x112fff1e]  # bxne    lr
    step_through_with_address(instr2)
    print("--- End of tests ---")
    
