# Path hack.
import sys, os
sys.path.insert(0, os.path.abspath('..'))

#import cProfile
#import math

#import array
#from utilities import  bit_fields, logging, unchecked_conversion
#from utilities.bit_fields import *
#from utilities.logging import *

#from msp430 import  msp430cpu
from msp430.msp430cpu import *

#from msp430 import disass
from msp430.disass import disass


# Maximum number of instructions to let the go command emulate. 
MAX_INSTRS = 200

#-------------------------------------------------------------------------------


class Code_Error(Exception):
    def __init__(self, value):
        self.value = value
      
    def __str__(self):
        return self.value
   

def log_unpredictable(word):
    log("Unpredictable instruction {:#x}".format(word))
    

def log_undefined():    
    log("Undefined instruction")

#-----------------------------------------------------------------
    
class MSP430Cpu:

    
    def __init__(self, filename):
        self.memory_bytes = 0
        self.memory = []
        self.RAM_start = 0x200
        self.RAM_values = \
                     [[0x20, "P1IN"],
                      [0x21, "P1OUT"],
                      [0x22, "P1DIR"],  # Direction
                      [0x23, "P1IFG"],  # Interrupt Flag
                      [0x24, "P1IES"],  # Interrupt Edge Selec
                      [0x25, "P1IE"],   # Interrupt Enable
                      [0x26, "P1SEL"],  # Port Select
                      [0x27, "P1REN"],  # Resistor Enable
                      [0x41, "P1SEL2"]
                    ]
        

        self.loaded = False
        
        self.filename = filename
        self.format = "img"
         
        self.pc = 0  # note separate, only 15 in self.registers
        self.registers = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
   
        self.setflags = False
    
        self.call_stack = []
   
        self.break_count = 0
        self.breaks = []
        
        self.cycles = 0

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
        next_addr = addr+instr_size
        return next_addr

    
    def setup_memory(self, membytes, addr = 0):
        Max_Memsize = 0x10000
        
        self.loaded = False
        byte_count = len(membytes) # +len(membytes)%4  no - must leave a gap if there is one
        chunk_count = len(self.memory)
        chunk = 0
        if chunk_count == 0:
            self.memory.append([0, Max_Memsize, bytearray(Max_Memsize)])

        if addr < Max_Memsize:
            if byte_count > (Max_Memsize-addr):
                byte_count = Max_Memsize-addr
           
            self.memory[chunk][MEMVALS][addr:addr+byte_count] = membytes[0:byte_count]
         # tbd fix this e000+.text size  
        self.memory_bytes = addr+byte_count-1  #self.get_last_address()
        self.loaded = True            
        
 

    def read_reg(self, regno):
        """ Read from a register """
        if regno == 0: return self.pc
        return self.registers[regno]
    
    def write_reg(self, regno, val):
        """ Write to a register """
        if regno == 0: 
            self.pc = val  
            return
        self.registers[regno] = val
         
    
    #--------------------------------------------------------------------------
    

    
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
                
    #-------------------------------------------------------------------
    # Start of a future I/O package
                

    
    def get_i(self, startaddr):
        return self.memory[0][startaddr] #NYI
    
      
    def read_io_memory(self, startaddr, count):
 
       # i = self.get_i(startaddr)
        i = 0
        if i is not None:
            val = self.memory[0][MEMVALS][startaddr:startaddr+count]
            #log("Reading {:s}, {:s}".format(self.RAM_values[i], val))
            return val
 
        return None
    
    def write_io_memory(self, startaddr, count, values):
        self.memory[0][MEMVALS][startaddr:startaddr+count] = bytearray(values.to_bytes(count, 'little'))
        return
    
    #-------------------------------------------------------------------
        
    def read_memory(self, startaddr, count):
        """ Read memory called from instruction decoding not dump command """
        if not self.loaded:
            log("Load program first")
            return -1
   
        if startaddr < self.RAM_start:
            return self.read_io_memory(startaddr, count)
 
        chunk = 0
        while chunk < len(self.memory):
            chunk_start = self.memory[chunk][MEMADDR]
            chunk_end = chunk_start + self.memory[chunk][MEMSIZE]
            if startaddr+count < chunk_start: return None
            if chunk_start <= startaddr < chunk_end:
                offset = startaddr - chunk_start
                return self.memory[chunk][MEMVALS][offset:offset+count]
            chunk += 1 
                            
        #log("Address not found <{:x}>".format(startaddr))
        return None
    
    def read_memory_int(self, startaddr, count, signed = False):       
        mbytes = self.read_memory(startaddr, count)
        if mbytes is None: return 0
        if mbytes == -1: return 0
        return int.from_bytes(mbytes[0:count], 'little', signed = signed)
  

    def write_memory(self, startaddr, count, values):
        """ Write to memory. """
        if not self.loaded:
            log("Load program first")
            return -1
        if count > 8 :
            log("Sorry, only counts of <= 8 supported in write memory")
            return 0
  
        
        op_mask = (1 << (8*count)) -1
        values &= op_mask
        
        if startaddr < self.RAM_start:
            return self.write_io_memory(startaddr, count, values)        
       
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
     
        membytes = values.to_bytes(count, 'little')
        self.setup_memory(membytes, startaddr)
    
    def stepi(self):
        """ Advance the emulation by a single instruction """
        if not self.loaded:
            log("Load program first")
            return
        # This is the only place that emulate is called
        # Keep it that way or move the following into emulate.
       
        instrs = [0,0,0]
        instrs[0] = self.read_memory_int((self.pc & address_mask), 2)
        instrs[1] = self.read_memory_int((self.pc+2 & address_mask), 2)
        instrs[2] = self.read_memory_int((self.pc+4 & address_mask), 2)

        return self.emulate(instrs)
    
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
        
    def go(self, count = MAX_INSTRS, addr = -1):
        """ Let it go for count instructions or until a break is hit """ 
        if not self.loaded:
            log("Load program first")
            return        
        try:
            if addr != -1:
                self.pc = addr
            while True:
                log("Going from {:08x}".format(self.pc))
                for i in range(count):
                    self.stepi()
                    program_counter = self.pc & address_mask
                    if program_counter in self.breaks:
                        log("Breakpoint hit at {:08x}".format(program_counter))
                        return
                msg = "{:d} instructions executed, continue (y/n)? >".format(
                                                                count)
                log(msg)
                #print(msg, end="")
                ans = input()
                if ans[0] == 'n':
                    return
                    
        except:
            log("Caught exception")
    
    def halt(self):
        pass
        

 
    
    #--------------------------------------------------------------------    
  
    
    def write_single_dst(self, word, op_size, operand):
        """ Single operand format """
        # update self.pc if necessary
        pc_updated = False
        a_dst = get_field(word, 4, 5) 
        dst_reg = get_field(word, 0, 3)
        if op_size == 1:
            op_mask = 0xff
        else:
            op_mask = 0xffff 
        operand &= op_mask
        if a_dst == 0:        
            self.write_reg(dst_reg, operand)
            if dst_reg == PC:
                pc_updated = True
        elif a_dst == 1:
            if dst_reg == PC:  # symbolic mode
                offset = self.pc
                self.pc += 2
                next_loc = self.read_memory_int(self.pc, 2)
                dest = offset + 2 + next_loc
                self.write_memory(dest, op_size, operand)
            elif dst_reg == SR:  # absolute mode
                self.pc += 2
                next_loc = self.read_memory_int(self.pc, 2)
                self.write_memory(next_loc, op_size, operand)
            else:    # indexed mode
                dst = self.read_reg(dst_reg)
                self.pc += 2
                offset = self.read_memory_int(self.pc, 2)
                dst += offset
                self.write_memory(dst, op_size, operand)
        elif a_dst == 2:  # indirect register mode
                dst = self.read_reg(dst_reg)
                self.write_memory(dst, op_size, operand)
        elif a_dst == 3:
            if dst_reg == PC:  # immediate mode
                self.pc += 2
                dst = self.read_memory_int(self.pc, 2)
                self.write_memory(dst, op_size, operand)
            else:  # indirect autoincrement mode
                dst = self.read_reg(dst_reg)
                self.write_reg(dst_reg, dst+op_size)
                if dst_reg == PC:
                    pc_updated = True
                self.write_memory(dst, op_size, operand) 
        return pc_updated
        
    def read_single_src(self, word, op_size):
        """ Single operand format """
        # update self.pc if necessary
        a_dst = get_field(word, 4, 5) 
        dst_reg = get_field(word, 0, 3)
        if op_size == 1:
            op_mask = 0xff
        else:
            op_mask = 0xffff
        if a_dst == 0:
            if dst_reg == 3:
                dst = 0  # constant generation
            else:        
                dst = self.read_reg(dst_reg)
        elif a_dst == 1:
            if dst_reg == PC:  # symbolic mode
                offset = self.pc
                self.pc += 2
                next_loc = self.read_memory_int(self.pc, 2)
                dest = offset + 2 + next_loc
                dst = self.read_memory_int(dest, op_size)
            elif dst_reg == SR:  # absolute mode
                self.pc += 2
                dst = self.read_memory_int(self.pc, op_size)
            elif dst_reg == 3:
                dst = 1   # constant generation
            else:    # indexed mode
                dst = self.read_reg(dst_reg)
                self.pc += 2
                offset = self.read_memory_int(self.pc, 2)
                dst += offset
                dst = self.read_memory_int(dst, op_size) 
        elif a_dst == 2:  # indirect register mode
            if dst_reg == SR:
                dst = 4   # constant generation
            elif dst_reg == 3:
                dst = 2   # constant generation
            else:
                dst = self.read_reg(dst_reg)
                dst = self.read_memory_int(dst, op_size)
        elif a_dst == 3:
            if dst_reg == PC:  # immediate mode
                self.pc += 2
                dst = self.read_memory_int(self.pc, 2)
            elif dst_reg == SR:
                dst = 8  # constant generation
            elif dst_reg == 3:
                dst = -1
            else:  # indirect autoincrement mode
                dst = self.read_reg(dst_reg)
                self.write_reg(dst_reg, dst+op_size)
                dst = self.read_memory_int(dst, op_size) 
        dst &= op_mask
        return dst
    
    def write_dual_dst(self, word, op_size, val):
        """ Dual operand format """
        pc_updated = False
        a_dst = get_field(word, 7, 7) 
        dst_reg = get_field(word, 0, 3)
        if a_dst == 0:
            self.write_reg(dst_reg, val)
            if dst_reg == PC:
                pc_updated = True
        elif a_dst == 1:
            self.cycles += 1
            if dst_reg == PC:  # symbolic mode
                offset = self.pc
                self.pc += 2
                next_loc = self.read_memory_int(self.pc, 2)
                dest = offset + 2 + next_loc
                self.write_memory(dest, op_size, val)
            elif dst_reg == SR:  # absolute mode
                self.pc += 2
                next_loc = self.read_memory_int(self.pc, 2)
                self.write_memory(next_loc, op_size, val)
            else:    # indexed mode
                dst = self.read_reg(dst_reg)
                self.pc += 2
                offset = self.read_memory_int(self.pc, 2)
                dst += offset
                self.write_memory(dst, op_size, val)
        return pc_updated
 
    
    def read_dual_src(self, word, op_size):
        """ Dual operand format """
        a_src = get_field(word, 4, 5) 
        src_reg = get_field(word, 8, 11)
        if a_src == 0:
            if src_reg == 3:
                src = 0  # constant generation
            else:  
                self.cycles += 1
                src = self.read_reg(src_reg)
        elif a_src == 1:
            if src_reg == PC:  # symbolic mode
                self.cycles += 3
                offset = self.pc
                self.pc += 2
                next_loc = self.read_memory_int(self.pc, 2)
                dest = offset + 2 + next_loc
                src = self.read_memory_int(dest, op_size)
            elif src_reg == SR:  # absolute mode
                self.cycles += 3
                self.pc += 2
                src = self.read_memory_int(self.pc, op_size)
            elif src_reg == 3:
                src = 1   # constant generation
            else:    # indexed mode
                self.cycles += 3
                src = self.read_reg(src_reg)
                self.pc += 2
                offset = self.read_memory_int(self.pc, 2)
                src += offset
                src = self.read_memory_int(src, op_size) 
        elif a_src == 2:  # indirect register mode
            if src_reg == SR:
                src = 4   # constant generation
            elif src_reg == 3:
                src = 2   # constant generation
            else: 
                self.cycles += 2                
                src = self.read_reg(src_reg)
                src = self.read_memory_int(src, op_size)
        elif a_src == 3:
            if src_reg == PC:  # immediate mode
                self.cycles += 2                
                self.pc += 2
                src = self.read_memory_int(self.pc, 2)
            elif src_reg == SR:
                src = 8  # constant generation
            elif src_reg == 3:
                src = -1
            else:  # indirect autoincrement mode
                self.cycles += 2                
                src = self.read_reg(src_reg)
                self.write_reg(src_reg, src+op_size)
                src = self.read_memory_int(src, op_size)
        return src    

    
    def read_dual_dst(self, word, op_size):
        """ Dual operand format """
        # update self.pc in the write back, not here
        a_dst = get_field(word, 7, 7) 
        dst_reg = get_field(word, 0, 3)
        if a_dst == 0:
            dst = self.read_reg(dst_reg)
            if dst_reg == PC:
                self.cycles += 1
            else:
                # unless a_src == 1
                a_src = get_field(word, 4, 5)
                if a_src != 1:
                    self.cycles += 1
        elif a_dst == 1:
            self.cycles += 1
            if dst_reg == PC:  # symbolic mode
                offset = self.pc
                next_loc = self.read_memory_int(self.pc+2, 2)
                dest = offset + 2 + next_loc
                dst = self.read_memory_int(dest, op_size)
            elif dst_reg == SR:  # absolute mode
                dst = self.read_memory_int(self.pc+2, op_size)
            else:
                dst = self.read_reg(dst_reg)
                offset = self.read_memory_int(self.pc+2, 2)
                dst += offset
                dst = self.read_memory_int(dst, op_size)        
        return dst    # return address as well
    
    # Format 1 (dual operand cycles)
    # Note, no write dst for mov, bit and cmp  (CPUX ???)
    #   \d  Read src  Rm   PC   X(Rm)  ADDR  &ADDR
    #  s Rn 1         0     1   2+1    2+1   2+1    (read dst+ write dst)
    #   @Rn 2         0     1   2+1    2+1   2+1
    #  @Rn+ 2         0     1   2+1    2+1   2+1
    #    #N 2         0     1   2+1    2+1   2+1
    # x(Rn) 3         0     0   2+1    2+1   2+1
    # x(PC) 3         0     0   2+1    2+1   2+1   ADDR
    # x(SR) 3         0     0   2+1    2+1   2+1   &ADDR
        
        
    def do_dual_operand(self, word):
        """ Emulate dual operand (Format 1) instructions. """
        opcode = (word >> 12) & 0xf
     
        if testBit(word, 6):
            op_size = 1
        else:
            op_size = 2

        src = self.read_dual_src(word, op_size)
        dst = self.read_dual_dst(word, op_size)
        status_reg = self.read_reg(SR)
        # operate
        write_back = True
        update_status = True
        # a DADD, DADD.B   (decimal)
        # b BIT,  BIT.B    (src & dst)
        # c BIC,  BIC.B    ( ~src & dst)
        # d BIS,  BIS.B    ( == OR)
        # e XOR,  XOR.B
        # f AND,  AND.B 
        if opcode == 4: # mov
            dst = src
            update_status = False
            if word == 0x4130:  # ret, == mov @sp+, pc
                if len(self.call_stack) > 0:
                    self.call_stack.pop()            
        elif opcode == 5: # add
            dst += src
        elif opcode == 6: # addc
            dst += src
            cbit = testBit(status_reg, CBIT)
            dst += cbit
        elif opcode == 7: # subc
            dst += ~src
            cbit = testBit(status_reg, CBIT)
            dst += cbit
        elif opcode == 8: # sub
            dst -= src
        elif opcode == 9: # cmp
            dst = dst - src
            write_back = False
        elif opcode == 10: # dadd
            cbit = testBit(status_reg, CBIT)
            tmp = dst
            res = [0,0,0,0]
            for i in range(op_size*2):
                res[i] = (tmp&0xf) + (src&0xf) + cbit
                if res[i] > 10:
                    res[i] = res[i] -10
                    cbit = 1
                else:
                    cbit = 0
                tmp >>= 4
                src >>= 4
            dst = 0
            for i in range(op_size*2-1, -1, -1):
                dst <<= 4
                dst |= res[i]
                
                
        elif opcode == 11: # bit
            write_back = False
            dst &= src
        elif opcode == 12: # bic
            dst = dst & (~src)
            # SR unchanged
        elif opcode == 13: # bis
            dst |= src
            # Note: SR unchanged
        elif opcode == 14: # xor
            dst ^= src
        elif opcode == 15: # and
            dst &= src
            
        pc_updated = False
        if write_back:   
            pc_updated = self.write_dual_dst(word, op_size, dst)
        else:  # cater for mov and bit etc with 
            a_dst = get_field(word, 7, 7)
            if a_dst == 1:
                self.pc += 2
            
        if update_status:
            # C <= not Z (not true for cmp)
            if dst != 0:
                status_reg = setBit(status_reg, CBIT)
            else:
                status_reg = clearBit(status_reg, CBIT)            
            status_reg = clearBit(status_reg, VBIT)
            self.write_reg(SR, logical_cond(dst, status_reg))
        else:
            status_reg = 0
        log_result(dst, status_reg)
        if not pc_updated: 
            self.pc += 2  # but what if pc was written to ?
        return self.pc   
    
    def do_jump(self, word):
        """ Emulate jump instructions. """
        self.cycles += 2  # all of them
        opcode = word & 0xfc00
        relative_offset = extend_sign(word & 0x3ff, 10) *2
        dest = self.pc + 2 + relative_offset
    
        if opcode == 0x3c00: # unconditional jmp
            self.pc = dest
            return self.pc
        
        cond_code = (word >> 10) & 7
        status_reg = self.read_reg(SR)
        if conditions_match(cond_code, status_reg):
            self.pc = dest
        else:
            self.pc += 2
        return self.pc
    
    def do_single_operand(self, word):
        """ Emulate single operand (format 2) instructions. """
        # TBD
        # cycle counts are wrong here
        #
        if testBit(word, 6):
            op_size = 1
        else:
            op_size = 2
            
        operand = self.read_single_src(word, op_size)
        opcode = word & 0xff80
        
        if opcode == 0x1000:  #  rrc - rotate right through carry
            self.cycles += 3
            status_reg = self.read_reg(SR)
            c_bit = testBit(status_reg, CBIT)
            if testBit(operand, 0):
                status_reg = setBit(status_reg, CBIT)
            else:
                status_reg = clearBit(status_reg, CBIT)
            self.write_reg(SR, status_reg)  
            operand //= 2
            if c_bit:
                if op_size == 1:
                    or_with = 0x80
                elif op_size == 2:
                    or_with = 0x8000
                operand |= or_with
            else:
                if op_size == 1:
                    and_with = 0x7f
                elif op_size == 2:
                    and_with = 0x7fff
                operand &= and_with                
            self.write_single_dst(word, op_size, operand)
            status_reg = clearBit(status_reg, VBIT)
            self.write_reg(SR, logical_cond(operand, status_reg))
            log_result(operand, status_reg)
            self.pc += 2
    
        elif opcode == 0x1080:  # swpb, swap bytes
            self.cycles += 3
            tmp = (operand >> 8) & 0xff
            operand = (operand & 0xff) << 8
            operand |= tmp
            self.write_single_dst(word, 1, operand)
            log_result(operand)
            self.pc += 2
            
        elif opcode == 0x1100: # rra 
            self.cycles += 3
            status_reg = self.read_reg(SR)
            c_bit = testBit(status_reg, CBIT)
            if testBit(operand, 0):
                status_reg = setBit(status_reg, CBIT)
            else:
                status_reg = clearBit(status_reg, CBIT)
            self.write_reg(SR, status_reg)             
            operand //= 2
            if op_size == 1:
                operand &= 0x7f
                operand = extend_sign(operand, 7)
            elif op_size == 2:
                operand &= 0x7fff
                operand = extend_sign(operand, 15)
                     
            self.write_single_dst(word, op_size, operand)
            log_result(operand, status_reg)
            self.pc += 2
          
        elif opcode == 0x1180:  # sxt - sign extend
            self.cycles += 3
            operand &= 0xff
            operand = extend_sign(operand, 8)
            self.write_single_dst(word, 2, operand)
            status_reg = self.read_reg(SR)           
            # C <= not Z
            if operand != 0:
                status_reg = setBit(status_reg, CBIT)
            else:
                status_reg = clearBit(status_reg, CBIT)            
            status_reg = clearBit(status_reg, VBIT)
            self.write_reg(SR, logical_cond(operand, status_reg))
            log_result(operand, status_reg)
            self.pc += 2
            
        elif opcode == 0x1200:  # push
            self.cycles += 4
            stack_pointer = self.read_reg(SP)
            stack_pointer -= 2   # always 2
            self.write_reg(SP, stack_pointer)
            self.write_memory(stack_pointer, op_size, operand)
            log("pushed {:x} to {:x}".format(operand, stack_pointer))
            self.pc += 2
            
        elif opcode == 0x1280:  # call
            self.cycles += 5
            stack_pointer = self.read_reg(SP)
            stack_pointer -= 2   # always 2
            self.write_reg(SP, stack_pointer)
            self.write_memory(stack_pointer, 2, self.pc+2)
            self.call_stack.append([self.pc, operand])
            self.pc = operand
            
        elif opcode == 0x1300:  # reti
            self.cycles += 4
            stack_pointer = self.read_reg(SP)
            tos = self.read_memory_int(stack_pointer, 2)
            self.write_reg(SR, tos)            
            stack_pointer += 2
            self.write_reg(SP, stack_pointer) 
            tos = self.read_memory_int(stack_pointer, 2)
            self.write_reg(PC, tos)
            stack_pointer = self.read_reg(SP)
            stack_pointer += 2
            self.write_reg(SP, stack_pointer)
            # status bits restored with SR
            if len(self.call_stack) > 0:
                self.call_stack.pop()            
        return self.pc
    
    def emulate(self, words):
        """ Emulate a single instruction. Updates and returns self.pc """
        
        # Log disassembly for the instruction and check the condition codes 
  
        addr = self.pc & address_mask
        log("{:08x}  ".format(addr), end = "")
        
        res, instr_size = disass(addr,  words) 
        log(res)
        
        ins_type = get_field(words[0], 12, 15)
     
        if ins_type == 1:          # format 2
            self.pc = self.do_single_operand(words[0])
        elif ins_type == 2 or ins_type == 3:
            self.pc = self.do_jump(words[0])
        elif 4 <= ins_type <= 15:  #  format 1
            self.pc  = self.do_dual_operand(words[0])
        else:
            log("<undefined {:x}>".format(words[0]))
            self.pc += 2
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
   
            

def do_steps(cpu, last_addr):

    while cpu.pc < last_addr:
        instr = cpu.read_memory_int(cpu.pc, 2)
        if instr == 0: 
            log("Zero instr, ending")
            return
        log("------instr = {:#x} ------".format(instr))
        cycles0 = cpu.cycles
        cpu.pc = cpu.stepi()
        log("     {:d} cycles ----".format(cpu.cycles-cycles0))
      

def step_through(cpu, instr_block):
    cpu.pc = addr = 0xe000
    for i in range(len(instr_block)):
        instr = instr_block[i]
        siz = 2
        instr = instr & 0xffff  
        cpu.setup_memory(instr.to_bytes(siz, 'little'), addr)
        addr += siz
    #show_mem(cpu)   

    cpu.loaded = True
    do_steps(cpu, addr)
    log("========= {:d} total cycles ========\n".format(cpu.cycles))

def step_through_with_address(cpu, instr_block):
    """ addresses are discontiguous. can only handle 16 bit instrs """
    addr = 0xe000
    for i in range(len(instr_block)):
        if (i %2) == 0:
            addr = instr_block[i]
            instr = instr_block[i+1]
    
            siz = 2
            instr = instr & 0xffff  
            cpu.setup_memory(instr.to_bytes(siz, 'little'), addr)
    #show_mem(cpu)
    cpu.pc = instr_block[0]
    cpu.loaded = True
    do_steps(cpu, cpu.get_last_address())
    log("========= {:d} total cycles ========\n".format(cpu.cycles))
    
if __name__ == '__main__':
    log("*** msp430cpu.py ***")
    
    def unit_test():
        cpu=MSP430Cpu("")
        # This is not a program, just some random instructions pulled from an image
        # TBD write a program that actually sets up valid inputs and outputs and
        # checks them. See asm_test.
        instr_block = [
            0x4031,  0x2000, # 0  mov #2000, sp
            0x12B0, # 4, call e00a
            0xe00a, # 6
            0x3c01, # 8 jmp pc+4
            0x4130, #  a ret, mov.w    @sp+, pc
            
            0xb0f2, 0xff80, 0x1000, # c bit.b #0xff80, &0x1000
            0x403d, 0x00ff,         #mov.w    #0xff, r13
            0xb6ed, 0xff80,         # 12 bit.b @R6, #0ff80(R13)
            0x100d,                 # rrc r13
            0x4314,                 # mov.w    #1, r4
            0x1084,                 # swpb r4
            0x120A,                 # push     r10
            0x124A,                 # push.b   r10
            0x403a, 0x5aa5,         #mov.w    #0x5aa5, r12
            0x4A0C,                 #mov.w    r10, r12
            0x4A4C,                 #mov.b    r10, r12
            0x4C1A, 0xFB86,  #mov.w    0xfb86(r12), r10
            0x4C5A, 0xFB86,  #mov.b    0xfb86(r12), r10
            0x403C, 0x00B4,  #mov.w    #0xb4, r12
            0x407C, 0x00B4,  #mov.b    #0xb4, r12 
            0x453A,          #mov.w    @r5+, r10
            0x457A,          #mov.b    @r5+, r10
            0x433f,          #mov.w    #-1, r15
            0x437f,          #mov.b    #-1, r15
            0x430f,          #mov.w    #0, r15
            0x434f,          #mov.b    #0, r15
            0x431f,          #mov.w    #1, r15
            0x435f,          #mov.b    #1, r15 
            0x4323,          #mov.w    #2, r3
            0x4363,          #mov.b    #2, r3 
            0x422f,          #mov.w    #4, r15
            0x426f,          #mov.b    #4, r15 
            0x4232,          #mov.w    #8, sr
            0x4272,          #mov.b    #8, sr    
            0x40b2, 0x5a80, 0x0120,  #mov.w    #0x5a80, &0x120
            0x40f2, 0x5a80, 0x0120,  #mov.b    #0x5a80, &0x120
            0x5A0C,          #add.w    r10, r12
            0x5A4C,          #add.b    r10, r12
            0x6f0b,           #addc.w   r15, r11
            0x6f4b,           #addc.b   r15, r11
            0x8e09,          #sub.w    r14, r9
            0x7e49,          #subc.b   r14, r9
            0xf0f2, 0x003f, 0x0023, #and.b    #0x3f, &0x23
            0x90B2, 0x0024, 0x0208, #cmp.w    #0x24, &0x208
            0xa698, 0x0024, 0x0208, #dadd.w   0x24(r6), 0x208(r8)
            0xa6d8, 0x0024, 0x0208, #dadd.b   0x24(r6), 0x208(r8)
            0xe2e2, 0x0021,         #xor.b    #4, &0x21
    
            0x2001,  #jne      0x04 ;  pc +4
            0x2801,  #jnc      0x04 ;
            0x27ff,  #jeq      0xff ; pc (not satisfied - we hope)
            0x2c00,  #jc       0x02 ;
            0x3c01,  #jmp      0x04 ;
            0x3c01,  #jmp      0x04 ;
            0x3ffe,  #jmp      -0x02 ;
            
        
            0x100d,          #rrc      r13
            0x104d,          #rrc.b    r13
            0x108d,          #swpb     r13
            0x1190, 0x0800,  #sxt      0x802 ;
            
            0xb0b2, 0xff80, 0x0022,#bit.w    #0xff80, &0x22
            0xb0f2, 0xff80, 0x0023,#bit.b    #0xff80, &0x23
            0xc392, 0x0020,        #bic.w    #1, &0x20
            0xc3d2, 0x0021,        #bic.b    #1, &0x21
            0xd4a2, 0x0024,        #bis.w    @r4, &0x24
            0xd3d2, 0x0021         #bis.b    #1, &0x21
    
            
        ]
        step_through(cpu, instr_block)
        das_strings.clear()
        cpu=MSP430Cpu("")
    
        instr1 = [
        0x120A,      # push     r10
        0x4A0C,      # mov.w    r10, r12
        0x4003,      # mov.w    pc, r3
        
        0xd3d2, 0x0021   #bis.b    #1, &0x21
        
        ]  
        step_through(cpu, instr1)
        
        cpu=MSP430Cpu("")
    
        instr2 = [0x8000,  0x12B0,        # call 8340
                  0x8002,  0x8340,        # 
                  0x8340, 0x6f0b,         # addc.w   r15, r11
                 
                  0x8342, 0x1084,         #swpb     r4
                  0x8344, 0x403f,         # mov #834c, R15
                  0x8346, 0x834c, 
                  0x8348, 0x128f,         #call     R15 ;
                  0x834c, 0x1300,         #reti
                  0x0, 0x0
                  ]
        step_through_with_address(cpu, instr2)
        
    #cProfile.run('unit_test()')
    unit_test()
    log("--- End of tests ---")
    
