import sys
import array
from utilities import my_hex, bit_fields, logging, scripting, unchecked_conversion
from utilities.bit_fields import *
from utilities.my_hex import *
from utilities.logging import *
from utilities.scripting import *

import math
from math import floor

from arch import machine

symdict = dict()
labels = []
section_addrs = dict()
section_bytes = dict()
das_strings = dict()
#-------------------------------------------------------------------------------

MEMADDR = 0
MEMSIZE = 1
MEMVALS = 2

#-------------------------------------------------------------------------------
  
   
register_names = {"r0":0,  "r1":1,  "r2":2,  "r3":3, 
                  "r4":4,  "r5":5,  "r6":6,  "r7":7, 
                  "r8":8,  "r9":9,  "r10":10,"r11":11, 
                  "r12":12,"r13":13,"r14":14,"r15":15,
                  "sr":2,  "sp":1,  "pc":0}
PC = 0
SP = 1
SR = 2

ccs = {'c':0, 'z':1,'n':2, 'gie':3,
       'cpuoff':4,'oscoff':5,'scg0':6, 'scg1':7, 'v':8}
 
address_mask = 0xfffe

# Addressing modes
# As/Ad  Mode               Syntax     Description
#00/0    Register mode      Rn         Register contents are operand
#01/1    Indexed mode       X(Rn)      (Rn + X) points to the operand. 
#                                      X is stored in the next word
#01/1    Symbolic mode      ADDR       (PC + X) points to the operand. 
#                                      X is stored in the next word
#                                      Indexed mode X(PC) is used.
#01/1    Absolute mode      &ADDR      The word following the instruction
#                                      contains the absolute address. 
#                                      X is stored in the next word. 
#                                      Indexed mode X(SR) used.
#10/-   Indirect register mode @Rn     Rn is used as a pointer to the operand.
#11/-   Indirect autoincrement @Rn+    Rn is used as a pointer to the operand. 
#                                      Rn is incremented afterwards by 1 for 
#                                      .B instructions and by 2 for .W 
#                                      instructions.
#11/-   Immediate mode         #N      The word following the instruction
#                                      contains the immediate constant N. 
#                                      Indirect autoincrement mode @pc+ is used.

# Constant Generators
#Register As Constant Remarks
#R2       00  -       Register Mode
#R2       01 (0)      Absolute address mode
#R2       10 00004    +4, bit processing
#R2       11 00008    +8, bit processing
#R3       00 00000    0, word processing
#R3       01 00000    +1
#R3       10 00002    +2, bit processing
#R3       11 FF, FFFF, FFFFF-1, word processing

# Opcode           S_Reg         Ad     B/W    As     D-Reg
# 4 MOV,  MOV.B
# 5 ADD,  ADD.B
# 6 ADDC, ADDC.B
# 7 SUBC, SUBC.B   (dst + ~src +C)
# 8 SUB,  SUB.B    (dst + ~src +1)
# 9 CMP,  CMP.B
# a DADD, DADD.B   (decimal)
# b BIT,  BIT.B    (src & dst)
# c BIC,  BIC.B    ( ~src & dst)
# d BIS,  BIS.B    ( == OR)
# e XOR,  XOR.B
# f AND,  AND.B

# Single operand (Format 2)
# ff80               0040     0030      000F
# Opcode             B/W      Ad        D/S-Reg
# 1000   RRC        (C-> MSB....LSB->C)
# 1040   RRC.B
# 1080   SWPB       (Swap bytes)
# 1100   RRA        (MSB->MSB ... LSB -> C)
# 1140   RRA.B
# 1180   SXT        (sign extend bit 7->)
# 1200   PUSH
# 1240   PUSH.B
# 1280   CALL
# 1300   RETI
#

# Jump
# e000                1c00           03ff
# Opcode              Condition      Offset
# 2000  JNE/JNZ       Z == 0         PC = PC +2 + extendSign(offset, 10) *2
# 2400  JEQ/JZ        Z == 1
# 2800  JNC           C == 0
# 2c00  JC            C == 1
# 3000  JN            N == 1
# 3400  JGE           (N ^ V) == 0
# 3800  JL            (N ^ V) == 1
# 3c00  JMP           1 == 1


dp_opcodes={4:"mov",  5:"add",  6:"addc",  7:"subc",
             8:"sub",  9:"cmp", 10:"dadd", 11:"bit",
            12:"bic", 13:"bis", 14:"xor", 15:"and"}
conds = {0:"ne", 1:"eq", 2:"nc", 3:"c", 4:"n", 5:"ge", 6:"l", 7:"mp"}
     
# sr (Status Register) bits
NBIT = 2
ZBIT = 1
CBIT = 0
VBIT = 8

#---------------------------------------------------------------------------
SPACES="                                                              "
ICOLUMN = 9   # Start column of register output
#---------------------------------------------------------------------------


def cond(value):
    """ Return a condition code name. """
    val=value & 0xf
    return conds[val]

def conditions_match(cond_code, sr):
    """ Does the condition in bits 10..12 of an instruction match the psr CCs """
    C= testBit(sr,0)
    Z= testBit(sr,1)
    N= testBit(sr,2)
    V= testBit(sr,8)
    
    if cond_code == 7:
        return True            # unconditional  jmp
    elif cond_code == 6:
        return (N ^ V) == 1    # less than  - jl
    elif cond_code == 5:
        return (N ^ V) == 0    # ge  -jge
    elif cond_code == 4:
        return N               # neg - jn
    elif cond_code == 3:
        return C               # carry - jc
    elif cond_code == 2:
        return not C           # not carry - jnc
    elif cond_code == 1:
        return Z               # equal - jeq/jz
    elif cond_code == 0:
        return not Z           # not equal - jne/jnz

# disassembler support

def get_reg(regno):
    """ Return a readable register number. """
    if   regno == 0: return "pc"
    elif regno == 1: return "sp"
    elif regno == 2: return "sr"
    else: return "r{:d}".format(regno)


def get_sym(addr):
    for index, item in enumerate(labels):
        if index == len(labels):
            return ""
        if item <= addr < labels[index+1]:
            diff = addr -item
            sym = symdict[item]
            if diff == 0:
                return "<{:s}>".format(sym)
            else:
                return "<{:s}>+#{:#x}".format(sym, diff)
    
    return ""


#------------------------------------------------------------------------------
# These are used in emulation
#------------------------------------------------------------------------------


    
def logical_cond(result, cond_code):
    if result == 0: cond_code = setBit(cond_code, ZBIT)
    else: cond_code = clearBit(cond_code, ZBIT)
    if result < 0: cond_code = setBit(cond_code, NBIT)
    else: cond_code = clearBit(cond_code, NBIT)
    cond_code = clearBit(cond_code, VBIT)
    return cond_code

""" complete rethink, needs size
def arith_cond(result, cond_code, carry):
    if result == 0: cond_code = setBit(cond_code, ZBIT)
    else: cond_code = clearBit(cond_code, ZBIT)
    if testBit(result, 15): cond_code = setBit(cond_code, NBIT)
    else: cond_code = clearBit(cond_code, NBIT) 
    if result.bit_length() > 16: cond_code = setBit(cond_code, VBIT) 
    if carry: cond_code = setBit(cond_code, CBIT)
    return cond_code
"""

def visual_ccs(psr):
    ccs = ''
    if testBit(psr, NBIT): ccs += 'n' 
    else: ccs+= '-'
    if testBit(psr, ZBIT): ccs += 'z' 
    else: ccs+= '-'
    if testBit(psr, CBIT): ccs += 'c' 
    else: ccs+= '-'
    if testBit(psr, VBIT): ccs += 'v' 
    else: ccs+= '-'
    return ccs

def log_result(val, psr = 0):
    if psr != 0:
        ccs = visual_ccs(psr)
        log("Result = {:#x}, CCS = {:s}".format(val, ccs))
    else:
        log("Result = {:#x}".format(val))
    return 

def log_cc(psr):
    ccs = visual_ccs(psr)    
    log("CCS = {:s}".format(ccs))
    return

def extend_sign(num, bit_size): 
    if testBit(num, bit_size-1):
        mask = (1 << (bit_size-1)) -1   # 7fffffff for bit_size==32
        num = -((-num)&mask)
    return num
    
""" # another way
def extend_sign(x, bits):
    m = 1 << (bits-1)
    x = x & ((1 << bits) -1)
    return (x ^ m) -m
"""

def ZeroExtend(a_word, bit): 
    mask = 0xffffffff >> (31-bit)
    return a_word & mask


def alignPC(addr, val):
    return (addr//val)*val


def CountLeadingZeroBits(word):
    for i in range(31, -1, -1):
        if testBit(word, i):
            return 31-i
    return 32

def rev8bits(x):
    """reverse bits in a byte"""
    x1 =    (x << 4)        | (x >> 4)
    x2 =   (x1 & 0x33) << 2 | (x1 & 0xcc) >> 2
    return (x2 & 0x55) << 1 | (x2 & 0xaa) >> 1

def rev32bits(x):
    """ reverse bits in a word """
    x1 = ((x  & 0x0000ffff) << 16)| ((x  & 0xffff0000) >> 16)
    #print("{:#x}".format(x1))
    x2 = ((x1 & 0x00ff00ff) << 8) | ((x1 & 0xff00ff00) >> 8)
    #print("{:#x}".format(x2))
    x3 = ((x2 & 0x0f0f0f0f) << 4) | ((x2 & 0xf0f0f0f0) >> 4)
    #print("{:#x}".format(x3))
    x4 = ((x3 & 0x33333333) << 2) | ((x3 & 0xcccccccc) >> 2)
    #print("{:#x}".format(x4))
    x5 = ((x4 & 0x55555555) << 1) | ((x4 & 0xaaaaaaaa) >> 1)
    return x5

def RoundTowardsZero(a, b):
    """ integer divide rounding towards zero """
    return -(-a // b) if (a < 0) ^ (b < 0) else a // b

def RoundDown(x):
    """ floor does the job """
    n = floor(x)
    return n



#------------------------------------------------------------------------------

if __name__ == '__main__':
    
    if machine != "MSP430":
        print("This file, msp430cpu.py, is for the msp430 only. Check arch.py")
        sys.exit(-1)      
    
    def test11(text, subr, param, expect):
        result = subr(param)
        if result != expect:
            if type(result) is int:
                print("Fail: {:s}: expect {:x}, got {:x}".format(text, expect, result))
            elif type(result) is float:
                print("Fail: {:s}: expect {:f}, got {:f}".format(text, expect, result))
        else:
            print("Pass: " +text)
            
    def test21(text, subr, param1, param2, expect):
        result = subr(param1, param2)
        if result != expect:
            print("Fail: {:s}: expect {:x}, got {:x}".format(text, expect, result))
        else:
            print("Pass: " +text)    
    
    test11("test11 pass case", rev32bits, 0x12345678, 0x1e6a2c48)
    test11("test11 expect fail case", rev32bits, 0x12345678, 0x1e6a2c49)
    test21("test21 expect fail case", RoundTowardsZero, 11, 3, 2)
    
    test11("rev32bits", rev32bits, 0x33333331, 0x8ccccccc)
    test11("rev32bits", rev32bits, 0xf333f333, 0xcccfcccf)
    test11("rev32bits", rev32bits, 0x11111111, 0x88888888)
    test11("rev32bits", rev32bits, 0x88888888, 0x11111111)
    test11("rev32bits", rev32bits, 0x88888188, 0x11811111)
    test11("rev32bits", rev32bits, 0xfec81248, 0x1248137f)
    
    test11("rev8bits", rev8bits, 0x12, 0x48)
    test11("rev8bits", rev8bits, 0x31, 0x8c)
    test11("rev8bits", rev8bits, 0xf3, 0xcf)
    test11("rev8bits", rev8bits, 0x1f, 0xf8)
    test11("rev8bits", rev8bits, 0x88, 0x11)
    test11("rev8bits", rev8bits, 0xab, 0xd5)   
    
    test11("CountLeadingZeroBits", CountLeadingZeroBits, 0, 32)
    test11("CountLeadingZeroBits", CountLeadingZeroBits, 3, 30)
    test11("CountLeadingZeroBits", CountLeadingZeroBits, 0xffff, 16)
    test11("CountLeadingZeroBits", CountLeadingZeroBits, 0xf0000000, 0)
    
     
    test21("RoundTowardsZero", RoundTowardsZero, 11, 3, 3)
    test21("RoundTowardsZero", RoundTowardsZero, -11, -3, 3)
    test21("RoundTowardsZero", RoundTowardsZero, -11, 3, -3)
    test21("RoundTowardsZero", RoundTowardsZero, 11, -3, -3)
    
    test11("RoundDown", RoundDown, 1.0, 1)
    test11("RoundDown", RoundDown, 1.0001, 1)
    test11("RoundDown", RoundDown, 1.5, 1)
    test11("RoundDown", RoundDown, 1.9999, 1)
    test11("RoundDown", RoundDown, -1.0, -1)
    test11("RoundDown", RoundDown, -1.0001, -2)
    test11("RoundDown", RoundDown, -1.1, -2)
    test11("RoundDown", RoundDown, -1.5, -2)    
