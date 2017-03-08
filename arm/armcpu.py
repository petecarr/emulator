import array
from utilities import my_hex, bit_fields, logging, scripting, unchecked_conversion
from utilities.bit_fields import *
from utilities.my_hex import *
from utilities.logging import *
from utilities.scripting import *
 
from arm import gpio, timer, video
from arm.gpio import *
from arm.timer import *
from arm.video import *

import math
from math import floor


symdict = dict()
labels = []
section_addrs = dict()
section_bytes = dict()
das_strings = dict()
#-------------------------------------------------------------------------------

MEMADDR = 0
MEMSIZE = 1
MEMVALS = 2

HIGH_MEMORY_START = 0x40000000   # on chip peripheral address space
SRAM_START = 0x20000000

#-------------------------------------------------------------------------------

register_names = {"r0":0,  "r1":1,  "r2":2,  "r3":3, 
                  "r4":4,  "r5":5,  "r6":6,  "r7":7, 
                  "r8":8,  "r9":9,  "r10":10,"r11":11, 
                  "r12":12,"r13":13,"r14":14,"r15":15,
                  "sp":13, "lr":14, "pc":15}
PC = 15
LR = 14
SP = 13

# TBD: In ARMv7-A there are private copies of registers r3_svc and r14_svc and also 
# r13_irq and r14_irq and
# r8_fiq-r14_fiq
ccs = {'n':31, 'z':30,'c':29,'v':28,'irq':27,'fiq':26,'s1':1,'s0':0}
processor_modes = {'user':0,'fiq':1,'irq':2,'svc':3}
address_mask = 0x1ffffffe

ins_types = { 0:"DP_M", 1:"DP", 2:"SDT", 3:"SDT", 4:"BDT", 5:"BR",
              6:"UND", 7:"COP_SWI"}
dp_opcodes={ 0:"and",  1:"eor",  2:"sub",  3:"rsb",
             4:"add",  5:"adc",  6:"sbc",  7:"rsc",
             8:"tst",  9:"teq", 10:"cmp", 11:"cmn",
            12:"orr", 13:"mov", 14:"bic", 15:"mvn"}
conds={0:"eq", 1:"ne", 2:"cs", 3:"cc", 4:"mi", 5:"pl", 6:"vs", 7:"vc",
       8:"hi", 9:"ls",10:"ge",11:"lt",12:"gt",13:"le",14:"",15:"nv"}
# apsr  (Application Program Status Register) bits
NBIT = 31
ZBIT = 30
CBIT = 29
VBIT = 28
QBIT = 27   # saturation (multiply overflowed, ssat, usat)

# cpsr (Current Processor Status Register) bits
#          not v7-M
JBIT= 24   # Jazelle
EBIT=9     # endianness, 0 little, 1 big
ADISABLEBIT = 8
IRQDISABLEBIT = 7
FIQDISABLEBIT=6
THUMBBIT = 5
# CPSR Modes (bits 4-0)  armv7-A, not armv7-M
MODE_USER = 16
MODE_FIQ = 17
MODE_IRQ = 18
MODE_SWI = 19
MODE_ABORT = 23
MODE_UNDEF = 27
MODE_SYSTEM = 31

# EPSR bits  armv7-M
TBIT = 24
# ICI/IT nyi

# SIMD Greater than or equal flags, eg SEL instruction
GE0 = 16
GE1 = 17
GE2 = 18
GE3 = 19
#---------------------------------------------------------------------------
SPACES="                                                              "
ICOLUMN = 9   # Start column of register output
#---------------------------------------------------------------------------


def cond(value):
    """ Return a condition code name. """
    val=value & 0xf
    return conds[val]

def conditions_match(cond_code, psr):
    """ Does the condition in bits 28..31 of an instruction match the psr CCs """
    N=True if testBit(psr,31) else False
    Z=True if testBit(psr,30) else False
    C=True if testBit(psr,29) else False
    V=True if testBit(psr,28) else False
    if cond_code == 15:
        return False            #nv
    elif cond_code == 14:
        return True             #al
    elif cond_code == 13:
        return Z or (N!=V)      #le  
    elif cond_code == 12:
        return (not Z) and (N==V) #gt
    elif cond_code == 11:
        return N != V           #lt
    elif cond_code == 10:
        return N == V           #ge
    elif cond_code == 9:
        return Z or (not C)     #ls (lower or same)
    elif cond_code == 8:
        return (not Z) and C    #hi
    elif cond_code == 7:
        return not V            #vc
    elif cond_code == 6:
        return V                #vs
    elif cond_code == 5:
        return not N            #pl
    elif cond_code == 4:
        return N                #mi
    elif cond_code == 3:
        return not C            #cc (lo)
    elif cond_code == 2:
        return C                #cs
    elif cond_code == 1:
        return not Z            #ne
    elif cond_code == 0:
        return Z                #eq

# disassembler support

def get_reg(regno):
    """ Return a readable register number. """
    if   regno == 15: return "pc"
    elif regno == 14: return "lr"
    elif regno == 13: return "sp"
    else: return "r{:d}".format(regno)


def get_fpreg(reg):
    return 's{:d}'.format(reg)

def get_dfpreg(reg):
    return 'd{:d}'.format(reg)
    
def reg_list(word):
    """ Return a register list of the form {rx,ry,..} according to bits 0..15"""
    res = ""
    for regno in range(16):
        if testBit(word, regno):
            res+=get_reg(regno) 
            res += ","
    res_len = len(res)
    if res_len > 0 and res[res_len-1] == ",":
        res_len -=1
        
    return "{" + res[0:res_len] + "}"

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

fc_true =  ('', 'eee', 'ee', 'eet', 'e', 'ete', 'et', 'ett', '',
                'tee', 'te', 'tet', 't', 'tte', 'tt', 'ttt')
fc_false = ('', 'ttt', 'tt', 'tte', 't', 'tet', 'te', 'tee', '',
                'ett', 'et', 'ete', 'e', 'eet', 'ee', 'eee')

def get_It_suffices(firstcond, mask):  # Table A7-3
    # mask != 0
    fc0 = firstcond & 1
    if fc0:
        return fc_true[mask]
    else:
        return fc_false[mask]
     

def vfp_expand_imm(imm8):
    imm = (imm8 & 0x3f) << 19
    if imm8 & 0x40:
        imm |= 0x3f000000
    else:
        imm |= 0x40000000
    if imm8 & 0x80:
        imm |= 0x80000000
    return imm

#------------------------------------------------------------------------------
# These are used in emulation
#------------------------------------------------------------------------------

def is_thumb32(word):
    # assume we already know it's thumb
    return (get_field(word, 13, 15) == 7) and (get_field(word, 11, 12) != 0)

def get_imm(pos, value):
    """ Interpret the 12 bit offset - 4 bits for rotation of the 8 bit value"""
    if pos == 0: 
        return value
    else:
        val = (value >> (pos*2)) | (value << (32-pos*2))
        return val
    
def get_dest(offset, value):
    """ Interpret the destination address of a branch instruction."""
    val = value
    if testBit(val, 23):
        val =(val - 0x1000000)
    return offset+(val+2)*4

def get_shift_type(value):
    """ Return the value of the shift code. """
    val = get_field(value,5,6)
    return val

    
def logical_cond(result, cond_code):
    if result == 0: cond_code = setBit(cond_code, ZBIT)
    else: cond_code = clearBit(cond_code, ZBIT)
    if testBit(result, 31): cond_code = setBit(cond_code, NBIT)
    else: cond_code = clearBit(cond_code, NBIT) 
    return cond_code


def arith_cond(result, cond_code, carry):
    if result == 0: cond_code = setBit(cond_code, ZBIT)
    else: cond_code = clearBit(cond_code, ZBIT)
    if testBit(result, 31): cond_code = setBit(cond_code, NBIT)
    else: cond_code = clearBit(cond_code, NBIT) 
    if result.bit_length() > 32: cond_code = setBit(cond_code, VBIT) 
    if carry: cond_code = setBit(cond_code, CBIT)
    return cond_code

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
    if testBit(psr, QBIT): ccs += 'q'  
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

def ZeroExtend12(a_word):
    imm32  = get_field(a_word, 26, 26) << 11
    imm32 |= get_field(a_word, 12, 14) << 8
    imm32 |= get_field(a_word, 0, 7)
    return imm32

def ZeroExtend16(a_word):
    imm32 = get_field(a_word, 16, 19) << 12
    imm32 |= get_field(a_word, 26, 26) << 11
    imm32 |= get_field(a_word, 12, 14) << 8
    imm32 |= get_field(a_word, 0, 7)
    return imm32


def ror_c(x, n, shift):
    m = shift % n
    result = (x >> m) | (x << n-m)
    carry_out = get_field(result, n-1, n-1)
    return result, carry_out

def rrx_c(val, bitsize, carry_in):
    mask = (1<< bitsize) -1
    result = (val << 1) & mask
    if carry_in:
        result += 1
    return result


def ThumbExpandImm_Craw(a_word):
    i = get_field(a_word, 26, 26)
    imm3 = get_field(a_word, 12, 14)
    imm8 = get_field(a_word, 0, 7)
    a = get_field(a_word, 7,7)
    iimm3a = (i << 4) | (imm3 << 1) | a
    if iimm3a <= 1:
        imm32 = imm8
    elif iimm3a <= 3:
        imm32 = (imm8 << 16) | imm8
    elif iimm3a <= 5:
        imm32 = (imm8 << 24) | (imm8 << 8) 
    elif iimm3a <= 7:
        imm32 = (imm8 << 24) | (imm8 << 16) | (imm8 << 8) | imm8
    elif iimm3a >= 8:
        imm32 = (imm8 | 0x80) << (32 - iimm3a) 

    return  imm32


def ThumbExpandImm_C(imm12):
    imm10_11 = get_field(imm12, 10, 11)
    imm8 = get_field(imm12, 0, 7)
    if imm10_11 == 0:
        imm8_9 = get_field(imm12, 8, 9)
        if imm8_9 == 0:
            imm32 = imm8   # same as ZeroExtend(imm12, 7)
        elif imm8_9 == 1:
            imm32 = (imm8 << 16) | imm8
        elif imm8_9 == 2:
            imm32 = (imm8 << 24) | (imm8<<8)
        elif imm8_9 == 3:
            imm32 = (imm8 << 24) | (imm8 << 16) | (imm8 << 8) | imm8        
    else:
        imm32 = 0x80 | get_field(imm12, 0, 6)
        (imm32, carry_out) = ror_c(imm32, 32, get_field(imm12, 7, 11))

    return  imm32

def ThumbExpandImm(a_word):
    imm32  = get_field(a_word, 26, 26) << 11
    imm32 |= get_field(a_word, 12, 14) << 8
    imm32 |= get_field(a_word, 0, 7)
    return ThumbExpandImm_C(imm32)

def alignPC(addr, val):
    return (addr//val)*val

class SRType: #(Enum):
    LSL = 0
    LSR = 1
    ASR = 2
    ROR = 3
    RRX = 4
    
def DisassImmShift(shift_type, imm5):  
    """ Disassemble support for immediate shift """
    shift_count = imm5
    if shift_type == 0: # lsl
        shift_count = '{:d}'.format(imm5)
        sh_type = 'lsl'
    elif shift_type == 1:  # lsr
        if shift_count == 0:
            shift_count = '32'
        else:
            shift_count = '{:d}'.format(imm5)
        sh_type = 'lsr'
    elif shift_type == 2:  # asr
        if shift_count == 0:
            shift_count = '32' 
        else:
            shift_count = '{:d}'.format(imm5)
        sh_type = 'asr'
    elif shift_type == 3:   # ror, rrx
        if shift_count == 0:
            shift_count = '1' # rrx
            sh_type = 'rrx'
        else:
            shift_count = '{:d}'.format(imm5)
            sh_type = 'ror'
    return sh_type +' #' + shift_count

def DisassRegShift(shift_type):
    """ Disassemble support for reg shift """
    if shift_type == 0:    
        return 'lsl'
    elif shift_type == 1:  
        return 'lsr'
    elif shift_type == 2:  
        return 'asr'
    elif shift_type == 3:  
        return 'ror'
    return 'Invalid shift type'
    

def DecodeImmShift(shift_type, imm5):  
    """ Expand out the shift and count into shift_t and shift_n """
    shift_count = imm5
    if shift_type == 0: # lsl
        shift_count = imm5
        sh_type = SRType.LSL
    elif shift_type == 1:  # lsr
        if shift_count == 0:
            shift_count = 32
        else:
            shift_count = imm5
        sh_type = SRType.LSR
    elif shift_type == 2:  # asr
        if shift_count == 0:
            shift_count = 32 
        else:
            shift_count = imm5
        sh_type = SRType.ASR
    elif shift_type == 3:   # ror, rrx
        if shift_count == 0:
            shift_count = 1 # rrx
            sh_type = SRType.RRX
        else:
            shift_count = imm5
            sh_type = SRType.ROR
    return sh_type, shift_count

def DecodeRegShift(shift_type):
    if shift_type == 0:    
        return SRType.LSL
    elif shift_type == 1:  
        return SRType.LSR
    elif shift_type == 2:  
        return SRType.ASR
    elif shift_type == 3:  
        return SRType.ROR
    return 0

def Shift_C(sh_type, val, shift_count, psr):
    """ Do a shift based on the output of DecodeImmShift """
    if shift_count == 0:
        return val, psr
    else:
        if sh_type == SRType.LSL:  # lsl_c
            result = (val << shift_count) & 0xffffffff
            carry_out = testBit(val, (32-shift_count))
        elif sh_type == SRType.LSR: # lsr_c
            result = val >> shift_count
            carry_out = testBit(val, (shift_count-1)) 
        elif sh_type == SRType.ASR:  # asr_c
            result = val >> shift_count
            result = extend_sign(result, (31-shift_count))
            carry_out = testBit(val, (shift_count-1)) 
        elif sh_type == SRType.ROR:
            (result, carry_out) = ror_c(val, 32, shift_count)
        elif sh_type == SRType.RRX:
            carry_in = testBit(psr, CBIT)
            (result, carry_out) = rrx_c(val, 32, carry_in)        
        if carry_out:
            psr = setBit(psr, CBIT)
        else:
            psr = clearBit(psr, CBIT)
    return result, psr

def Shift(value, sh_type, shift_count, carry_in):
    """ As Shift_C but no setflags output """
    result, dont_care = Shift_C(value, sh_type, shift_count, carry_in)
    return result
     

def SignedSatQ(val, sat):
    satval = (1 << sat) -1
    lo_satval = (1<< sat)
    if val > satval:
        result = satval
        saturated = True
    elif val < -lo_satval:
        result = lo_satval
        saturated = True
    else:
        result = val
        saturated = False
    return result, saturated

def UnsignedSatQ(val, sat):
    satval = (1 << sat) -1
    if val > satval:
        result = satval
        saturated = True
    elif val < 0:
        result = 0
        saturated = True
    else:
        result = val
        saturated = False
    return result, saturated
        
def SignedSat(val, sat):
    (result, dontcare) = SignedSatQ(val, sat)
    return result

def UnsignedSat(val, sat):
    (result, dontcare) = UnsignedSatQ(val, sat)
    return result 

def SatQ(val, sat, unsigned):
    if unsigned:
        return UnsignedSatQ(val, sat)
    else:
        return SignedSatQ(val, sat)    

def Sat(val, sat, unsigned):
    if unsigned:
        result = UnsignedSat(val, sat)
    else:
        result = SignedSat(val, sat)
    return result

def AddWithCarry(vala, valb, psr):
    """ Add 2 integers with carry. """
    #Derived from pseudocode in DDI0403D A2-43. Pseudocode in comments
    carry_in = testBit(psr, CBIT)
    #unsigned_sum = UInt(vala) + UInt(valb) + UInt(carry_in)
    un_sum = (vala & 0xffffffff) + (valb & 0xffffffff) + carry_in
    #signed_sum   = vala + valb + carry_in
    sign_sum = vala + valb + carry_in
    #result       = unsigned_sum<N-1:0>;  # same value as signed_sum<N-1:0>
    result = un_sum & 0xffffffff
    if testBit(un_sum, 31): 
        sign_result = un_sum - (2<<32)
    else:
        sign_result = un_sum
    #carry_out    = if UInt(result) == unsigned_sum then 0 else 1
    if result == un_sum: 
        psr = clearBit(psr, CBIT)
    else: 
        psr = setBit(psr, CBIT)
    #overflow     = if SInt(result) == signed_sum then 0 else 1
    if sign_result == sign_sum: 
        psr = clearBit(psr, VBIT)
    else: 
        psr = setBit(psr, VBIT)
 
    return result, psr


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
    if x >= 0:
        n = floor(x)
    else:
        n = floor(x)
    return n

#------------------------ FP support ------------------------------
# SBIT = 31      0x80000000
# EXP = 23..30   0x7f800000
# FRACT = 0..22  0x007fffff

# Halfword FP format 
# SBIT = 15       0x8000
# EXP = 10-14     0x7c00
# FRACT = 0-9     0x03ff
# seeeeeffffffffff

# fpscr bits
AHP = 26
DN = 25
FZ = 24
UFC = 3

"""

FPAdd()
FPDiv()
FPMul()
FPMulAdd()
FPSqrt()
FPSub()

"""

def log_float_result(val, psr = 0):
    """ val is a real. If you provide the psr, outputs condition codes """
    ccs_str = ""
    if psr != 0:
        ccs = ''
        if testBit(psr, NBIT): ccs += 'n' 
        else: ccs+= '-'
        if testBit(psr, ZBIT): ccs += 'z' 
        else: ccs+= '-'
        if testBit(psr, CBIT): ccs += 'c' 
        else: ccs+= '-'
        if testBit(psr, VBIT): ccs += 'v' 
        else: ccs+= '-'
        if testBit(psr, QBIT): ccs += 'q'  
        else: ccs+= '-'
        ccs_str = ", fp CCS = {:s}".format(ccs)
 
    log("Result = {:#f} ({:#x}){:s}".format(
                  val, unchecked_conversion.convert_float_to_int(val), ccs_str))
    return 

def log_raw_float_result(val, psr = 0):
    """ val is an integer as stored in memory or registers """
    ccs_str = ""
    if psr != 0:
        ccs = ''
        if testBit(psr, NBIT): ccs += 'n' 
        else: ccs+= '-'
        if testBit(psr, ZBIT): ccs += 'z' 
        else: ccs+= '-'
        if testBit(psr, CBIT): ccs += 'c' 
        else: ccs+= '-'
        if testBit(psr, VBIT): ccs += 'v' 
        else: ccs+= '-'
        if testBit(psr, QBIT): ccs += 'q'  
        else: ccs+= '-'
 
        
        ccs_str = ", fp CCS = {:s}".format(ccs)    
    log("Result = {:#f} ({:#x}){:s}".format(
            unchecked_conversion.convert_int_to_float(val), val, ccs_str))
 
    return 

def log_raw_dfloat_result(val1, val2, psr = 0):
    """ val1, val2 are integers """
    ccs_str = ""
    if psr != 0:
        ccs = ''
        if testBit(psr, NBIT): ccs += 'n' 
        else: ccs+= '-'
        if testBit(psr, ZBIT): ccs += 'z' 
        else: ccs+= '-'
        if testBit(psr, CBIT): ccs += 'c' 
        else: ccs+= '-'
        if testBit(psr, VBIT): ccs += 'v' 
        else: ccs+= '-'
        if testBit(psr, QBIT): ccs += 'q'  
        else: ccs+= '-'
        ccs_str = ", fp CCS = {:s}".format(ccs)
        
    val = ((val1&0xffffffff) << 32) | (val2&0xffffffff)
    log("Result = {:#f} ({:#x}){:s}".format(
            unchecked_conversion.convert_int_to_float(val), val, ccs_str))  # tbd not tested
 
    return 


# these operate on the ints that are stored in the registers
# once in memory, we are using floats (reals)

def StandardFPSCRValue(fpscr):
    #return '00000' : FPSCR<26> : '11000000000000000000000000';
    return (fpscr & 0x08000000)| 0x06000000


#from enum import Enum
class FPType: #(Enum):
    Nonzero = 0
    Zero = 1
    Infinity = 2
    QNaN = 3
    SNaN = 4
    
def get_FPtype(val):
    if val == FPType.Nonzero:
        return "Nonzero"
    elif val == FPType.Zero:
        return "Zero"
    elif val == FPType.Infinity:
        return "Infinity"
    elif val == FPType.QNaN:
        return "QNaN"
    elif val == FPType.SNaN:
        return "SNaN"
    else:
        return "Invalid FPType"

class FPExc: #(Enum):
    InvalidOp = 0
    DivideByZero = 1
    Overflow = 2
    Underflow = 3
    Inexact = 4
    InputDenorm = 7

def FPProcessException(exception, fpscr_val):
    # Get appropriate FPSCR bit numbers
    if exception == FPExc.InvalidOp:
        log("Invalid FP operand")
        enable = 8   
        cumul = 0
    elif exception == FPExc.DivideByZero:
        log("FP Divide by zero")
        enable = 9   
        cumul = 1
    elif exception == FPExc.Overflow:
        log("Fp overflow")
        enable = 10
        cumul = 2
    elif exception == FPExc.Underflow:
        log("FP underflow")
        enable = 11  
        cumul = 3
    elif exception == FPExc.Inexact: 
        log("FP inexact")
        enable = 12  
        cumul = 4
    elif exception == FPExc.InputDenorm: 
        log("FP input denormalized")
        enable = 15  
        cumul = 7
    if testBit(fpscr_val, enable) :
        log("IMPLEMENTATION_DEFINED floating-point trap handling")
    else:
        fpscr_val = setBit(fpscr_val, cumul)
    return  # fpscr_val  need a way to access the fpscr

def FPZero(sign, bitcount):
    if not sign: 
        return 0
    if bitcount == 16:
        if sign:
            return 0x8000
    elif bitcount == 32:
        if sign:
            return 0x80000000
    else:
        return 0
        
def FPInfinity(sign, bitcount):
    if bitcount == 16:
        if sign:
            return 0xfc00
        else:
            return 0x7c00
    elif bitcount == 32:
        if sign:
            return 0xff800000
        else:
            return 0x7f800000
    else:
        return 0  
    
def FPMaxNormal(sign,  N):
    if N == 16 :
        return (sign<<15)| 0x7bff
    else:
        return (sign<<31)| 0x7f7fffff
    
def FPDefaultNaN(bitcount):
    if bitcount == 16:
        return 0x7e00
    elif bitcount == 32:
        return 0x7fc00000
    else:
        return 0 
    
def FPNeg(word):
    if word.bit_length() <= 32:
        return word^0x80000000
    elif word.bit_length() <= 64:
        return word^0x8000000000000000

def FPAbs(word):
    if word.bit_length() <= 32:
        return word&0x7fffffff
    elif word.bit_length() <= 64:
        return word&0x7fffffffffffffff
    

# The fpscr_val argument supplies FPSCR control bits. Status information is
# updated directly in the FPSCR where appropriate.
#def FPRound(real result, integer N, fpscr_val):
def FPRound(result, N, fpscr_val):
    if result == FPZero(0, N) or result == FPZero(1, N):
        return result
    # Obtain format parameters - minimum exponent, numbers of exponent and fraction bits.
    if N == 16:
        minimum_exp = -14
        E = 5
        F = 10
    else:  # N == 32
        minimum_exp = -126
        E = 8
        F = 23
    # Split value into sign, unrounded mantissa and exponent.
    if result < 0.0:
        sign = 1  
        mantissa = -result
    else:
        sign = 0
        mantissa = result
    exponent = 0
    while mantissa < 1.0:
        mantissa = mantissa * 2.0  
        exponent = exponent - 1
    while mantissa >= 2.0 :
        mantissa = mantissa / 2.0  
        exponent = exponent + 1
    # Deal with flush-to-zero.
    if testBit(fpscr_val, 24) and (N != 16) and (exponent < minimum_exp):
        result = FPZero(sign, N)
        fpscr_val = setBit(fpscr_val, UFC) # Flush-to-zero never generates a trapped exception
    else:
        # Start creating the exponent value for the result. Start by biasing the 
        # actual exponent so that the minimum exponent becomes 1, lower values 0 
        # (indicating possible underflow).
        biased_exp = max(exponent - minimum_exp + 1, 0)
        if biased_exp == 0 : 
            mantissa = mantissa // 2**(minimum_exp - exponent)
        # Get the unrounded mantissa as an integer, and the units in last place
        # rounding error.
        int_mant = math.floor(mantissa * 2**F) # < 2**F if biased_exp == 0, >= 2^F if not
        error = (mantissa * (2**F)) - int_mant
        # Underflow occurs if exponent is too small before rounding, and result
        # is inexact or the Underflow exception is trapped.
        if (biased_exp == 0) and ((error != 0.0) or testBit(fpscr_val, 11)):
            FPProcessException(FPExc.Underflow, fpscr_val)
        # Round result according to rounding mode.
        round_mode = get_field(fpscr_val, 22, 23)
        if round_mode == 0: # Round to Nearest (rounding to even if exactly halfway)
                round_up = (error > 0.5) or ((error == 0.5) and testBit(int_mant, 0))
                overflow_to_inf = True
        elif round_mode == 1:  # Round towards Plus Infinity
                round_up = (error != 0.0) and (sign == 0)
                overflow_to_inf = (sign == 0)
        elif round_mode == 2:   # Round towards Minus Infinity
                round_up = (error != 0.0) and (sign == 1)
                overflow_to_inf = (sign == 1)
        elif round_mode == 3:  # Round towards Zero
                round_up = False
                overflow_to_inf = False
        if round_up:
            int_mant = int_mant + 1
            if int_mant == 2**F :     # Rounded up from denormalized to normalized
                biased_exp = 1
            if int_mant == 2**(F+1) : # Rounded up to next exponent
                biased_exp = biased_exp + 1
                int_mant = int_mant // 2 
            # Deal with overflow and generate result.
            if N != 16 or testBit(fpscr_val,26) == 0: # Single, double or IEEE half precision
                if biased_exp >= 2**E - 1 :
                    if overflow_to_inf: 
                        result = FPInfinity(sign, N) 
                    else: 
                        result = FPMaxNormal(sign, N)
                    FPProcessException(FPExc.Overflow, fpscr_val)
                    error = 1.0  # Ensure that an Inexact exception occurs
                else:
                    result = ((sign<<(N-1)) | 
                              ((biased_exp&((2**E)-1))<<23) |
                               int_mant&((2**F)-1))
                    result = unchecked_conversion.convert_int_to_float(result)
            else:            # Alternative half precision
                if biased_exp >= 2**E :
                    result = (sign << (N-1)) | 0x7fff
                    FPProcessException(FPExc.InvalidOp, fpscr_val)
                    error = 0.0  # Ensure that an Inexact exception does not occur
                else:
                    result = ((sign<<(N-1)) | 
                              ((biased_exp&((2**E)-1))<<10) | 
                              int_mant&((2**F)-1))
                    result = unchecked_conversion.convert_int_to_float(result)
            # Deal with Inexact exception.
            if error != 0.0:
                FPProcessException(FPExc.Inexact, fpscr_val)
    return result     


def FPUnpack(fpval, fpscr_val):
    """ Given the integer representation of a FP number, get the type, sign and 
        real value.
    """
    N = fpval.bit_length()
    if N <= 16: 
        N = 16  # 0x7xxx gets 15
    else: 
        N = 32 # 0x7xxxxxxx gets 31 (which works by accident)
    
    if N == 16 :
        sign = get_field(fpval, 15, 15)
        exp =  get_field(fpval, 10, 14)
        frac = get_field(fpval, 0, 9)
        if exp == 0:
            # Produce zero if value is zero
            if frac == 0:
                fptype = FPType.Zero
                value = 0.0
            else:
                fptype = FPType.Nonzero
                value = 2**(-14) * ((frac&0x3ff) * 2**(-10))
        elif (exp == 0x1f) and (testBit(fpscr_val, 26) == 0): 
            # Infinity or NaN in IEEE format
            if frac == 0 :
                fptype = FPType.Infinity
                value = 65504.0 # 2**1000000 going to wait a long time for Python to do this
            else:
                if testBit(frac, 9): 
                    fptype = FPType.QNaN
                else: 
                    fptype = FPType.SNaN
                value = 0.0
        else:
            fptype = FPType.Nonzero
            value = (1<<((exp&0x1f)-15)) * (1.0 + (frac&0x3ff) * 2**(-10))
    else:  # N == 32
        sign = get_field(fpval, 31, 31)
        exp  = get_field(fpval, 23, 30)
        frac = get_field(fpval, 0, 22)
        if exp == 0:
            # Produce zero if value is zero or flush-to-zero is selected.
            if frac == 0 or testBit(fpscr_val, 24):
                fptype = FPType.Zero
                value = 0.0
                if frac != 0:  # Denormalized input flushed to zero
                    FPProcessException(FPExc.InputDenorm, fpscr_val)
            else:
                fptype = FPType.Nonzero
                value = 2**(-126) * (frac & 0x7fffff) * (2**-23)
        elif exp == 0xff:
            if frac == 0:
                fptype = FPType.Infinity
                value = 3.403e38 # 2**1000000
            else:
                if testBit(frac, 22) : 
                    fptype = FPType.QNaN
                else: 
                    fptype = FPType.SNaN
                value = 0.0
        else:
            fptype = FPType.Nonzero
            value = 2**((exp&0xff)-127) * (1.0 + (frac & 0x7fffff) * 2**(-23))
    if sign == 1: 
        value = -value
    return (fptype, sign, value)

def FPCompare(op1, op2, quiet_nan_exc, fpscr_val):
    #assert N IN {32,64};
    #fpscr_val = if fpscr_controlled then FPSCR else StandardFPSCRValue()
    (type1,sign1,value1) = FPUnpack(op1, fpscr_val)
    (type2,sign2,value2) = FPUnpack(op2, fpscr_val)
    if (type1==FPType.SNaN) or (type1==FPType.QNaN) or (
        type2==FPType.SNaN) or (type2==FPType.QNaN):
        fpscr_val = set_field(fpscr_val, 0b0011, 28,31)  # nzcv unordered
        if (type1==FPType.SNaN) or (type2==FPType.SNaN) or quiet_nan_exc:
            FPProcessException(FPExc.InvalidOp, fpscr_val)
    else:
        # All non-NaN cases can be evaluated on the values produced by FPUnpack()
        if value1 == value2 :
            fpscr_val = set_field(fpscr_val, 0b0110, 28,31)  # nzcv equal
        elif value1 < value2 :
            fpscr_val = set_field(fpscr_val, 0b1000, 28,31) # nzcv  lt
        else:  # value1 > value2
            fpscr_val = set_field(fpscr_val, 0b0010, 28,31) # nzcv  gt
            
    return fpscr_val

def FPHalfToSingle(operand, fpscr, fpscr_controlled):
    """ Convert 16-bit to 32 bit FP """
    if fpscr_controlled: fpscr_val = fpscr 
    else: fpscr_val = StandardFPSCRValue(fpscr)
    (fptype,sign,value) = FPUnpack(operand, fpscr_val)
    if (fptype == FPType.SNaN) | (fptype == FPType.QNaN):
        if testBit(fpscr_val, 25): # DN bit set
            result = FPDefaultNaN(32)
        else:
            if sign == 1:
                result = 0x1ff
            else:
                result = operand & 0x1ff
                # Zeros(13)
        if fptype == FPType.SNaN:
            FPProcessException(FPExc.InvalidOp, fpscr_val)
    elif fptype == FPType.Infinity:
        result = FPInfinity(sign, 32)
    elif fptype == FPType.Zero:
        result = FPZero(sign, 32)
    else:
        result = FPRound(value, 32, fpscr_val) # Rounding will be exact
    return result, fpscr_val


def FPSingleToHalf(operand, fpscr, fpscr_controlled):
    """ Convert 32 bit to 16 bit FP """
    if fpscr_controlled : fpscr_val = fpscr
    else: fpscr_val = StandardFPSCRValue(fpscr)
    (fptype,sign,value) = FPUnpack(operand, fpscr_val)
    if fptype == FPType.SNaN or fptype == FPType.QNaN:
        if testBit(fpscr_val, 26) :     # AH bit set
            result = FPZero(sign, 16)
        elif testBit(fpscr_val, 25):  # DN bit set
            result = FPDefaultNaN(16)
        else:
            result = (sign << 31) | 0x7e000000 | get_field(operand, 13, 21)
        if (fptype == FPType.SNaN) or testBit(fpscr_val, 26):
            FPProcessException(FPExc.InvalidOp, fpscr_val)
        elif fptype == FPType.Infinity :
            if testBit(fpscr_val, 26) : # AH bit set
                result = (sign << 15) | 0x7fff
                FPProcessException(FPExc.InvalidOp, fpscr_val)
            else:
                result = FPInfinity(sign, 16)
        elif fptype == FPType.Zero:
            result = FPZero(sign, 16)
    else:
        result = FPRound(value, 16, fpscr_val)
    return result , fpscr_val   


def FPToFixed(operand, M, fraction_bits, unsigned, round_towards_zero, 
                   fpscr, fpscr_controlled):
    """ Floating point to fixed point """
    if N != 32 and N != 64:
        log("FixedToFP called with a bit size of {:d}".format(N))
        return 0.0    

    if fpscr_controlled : 
        fpscr_val = fpscr
    else: 
        fpscr_val = StandardFPSCRValue(fpscr)
    if round_towards_zero : 
        fpscr_val = setBit(fpscr_val, 22)
        fpscr_val = setBit(fpscr_val, 23)
     
    fptype,sign,value = FPUnpack(operand, fpscr_val)
    
    # For NaNs and infinities, FPUnpack() has produced a value that will round to the
    # required result of the conversion. Also, the value produced for infinities will
    # cause the conversion to overflow and signal an Invalid Operation floating-point
    # exception as required. NaNs must also generate such a floating-point exception.
    if fptype == FPType.SNaN or fptype == FPType.QNaN :
        FPProcessException(FPExc.InvalidOp, fpscr_val)
    # Scale value by specified number of fraction bits, then start rounding to an integer
    # and determine the rounding error.
    value = value * (2**fraction_bits)
    int_result = RoundDown(value)
    error = value - int_result
    # Apply the specified rounding mode.
    round_mode = get_field(fpscr_val, 22, 23)
    if round_mode == 0:  # Round to Nearest (rounding to even if exactly halfway)
        round_up = (error > 0.5) or ((error == 0.5) and testBit(int_result, 0))
    elif round_mode == 1:  # Round towards Plus Infinity
        round_up = (error != 0.0)
    elif round_mode == 2:  # Round towards Minus Infinity
        round_up = FALSE
    elif round_mode == 3:  #/ Round towards Zero
        round_up = (error != 0.0) and (int_result < 0)
    if round_up :
        int_result = int_result + 1
    # Bitstring result is the integer result saturated to the destination size, with
    # saturation indicating overflow of the conversion (signaled as an Invalid
    # Operation floating-point exception).  
    (result, overflow) = SatQ(int_result, M, unsigned)
    if overflow:
        FPProcessException(FPExc.InvalidOp, fpscr_val)
    elif error != 0:
        FPProcessException(FPExc.Inexact, fpscr_val)
    return result, fpscr_val 
        
def FixedToFP(operand, N, fraction_bits, unsigned, round_to_nearest, 
              fpscr, fpscr_controlled):
    """ Fixed point to floating point """
    if N != 32 and N != 64:
        log("FixedToFP called with a bit size of {:d}".format(N))
        return 0.0
    if fpscr_controlled : 
        fpscr_val = fpscr
    else: 
        fpscr_val = StandardFPSCRValue(fpscr)
    if round_to_nearest :
        fpscr_val = clearBit(fpscr_val, 22)
        fpscr_val = clearBit(fpscr_val, 23)
     
    if unsigned:
        int_operand = operand & ((2**N)-1) 
    else: 
        int_operand =extend_sign(operand, N)
    real_operand = int_operand / 2**fraction_bits
    if real_operand == 0.0:
        result = FPZero(0, N)
    else:
        result = FPRound(real_operand, N, fpscr_val)
    return result, fpscr_val  

#------------------------------------------------------------------------------

if __name__ == '__main__':
    
    from arch import machine
    if machine != "ARM":
        print("This file, armcpu.py, is for the arm family only. Check arch.py")
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
    test11("test11 fail case", rev32bits, 0x12345678, 0x1e6a2c49)
    test21("test21 fail case", RoundTowardsZero, 11, 3, 2)
    
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

    
    # Educational
    test11("FPDefaultNaN 16 bits", FPDefaultNaN, 16, 0x7e00)
    test11("FPDefaultNaN 32 bits", FPDefaultNaN, 32, 0x7fc00000)

    
    print("16 bit Nan {:f}".format(unchecked_conversion.convert_int_to_float(
                                   FPDefaultNaN(16))))
    print("32 bit Nan {:f}".format(unchecked_conversion.convert_int_to_float(
                                   FPDefaultNaN(32))))
    
    #print("abs(-1.0) {:f}".format(FPAbs(-1.0)))  # nonono
    test11("FPAbs", FPAbs, 0xbf800000, 0x3f800000)
    test11("FPNeg", FPNeg, 0xbf800000, 0x3f800000)
    test11("FPNeg", FPNeg, 0x42f6e979, 0xc2f6e979)
    print("neg(123.456) {:f}".format(unchecked_conversion.convert_int_to_float(
                           FPNeg(0x42f6e979)))) 
    
    print("16 bit - infinity {:f}".format(
        unchecked_conversion.convert_int_to_float(FPInfinity(True, 16))))
    print("16 bit + infinity {:f}".format(
        unchecked_conversion.convert_int_to_float(FPInfinity(False, 16))))    
    print("32 bit - infinity {:f}".format(
        unchecked_conversion.convert_int_to_float(FPInfinity(1, 32))))
    print("32 bit + infinity {:f}".format(
        unchecked_conversion.convert_int_to_float(FPInfinity(0,32))))   
    
    
    def do_AWC(vala, valb, psr):
        carry_in = testBit(psr, CBIT) 
        result, psr = AddWithCarry(vala, valb, psr)
        carry_out = testBit(psr, CBIT)
        overflow =  testBit(psr, VBIT)
        print("{:x} + {:x} with C={:d} => {:d} ({:x}), C={:d}, V={:d}".format(
               vala, valb, carry_in, result, result, carry_out, overflow))
         
    print("---AddWithCarry---")
    psr = 0
    do_AWC(0x1000, 0x1000, psr)
    psr = setBit(psr, CBIT)
    do_AWC(0x1000, 0x1000, psr)
    psr = 0
    do_AWC(0x1000, -0x1000, psr)
    psr = setBit(psr, CBIT)
    do_AWC(0x1000, -0x1000, psr)
    psr = 0
    do_AWC(0x1000, -0xfff, psr)
    psr = setBit(psr, CBIT)
    do_AWC(0x1000, -0xfff, psr) 
    psr = 0
    do_AWC(0x1000, -0x1001, psr)
    psr = setBit(psr, CBIT)
    do_AWC(0x1000, -0x1001, psr)
    psr = 0
    do_AWC(0x40000000, 0x40000000, psr)
    do_AWC(0x40000000, -0x40000000, psr)
    do_AWC(-0x40000000, -0x40000000, psr)
    # Just trying subtraction as described in the Manual, a + ~B +Carry
    # 16-1
    psr = setBit(psr, CBIT)
    do_AWC(0x10, 0xfffffffe, psr)
    psr = 0
    do_AWC(0x10, 0xfffffffe, psr)
    
    def do_FPUnpack(fpval, exp_type, psr):
        (fptype, sign, value) = FPUnpack(fpval, psr)
        print("Expect {:s} :type is {:8s}, sign is {:d}, val is {:f}".format(
            get_FPtype(exp_type), get_FPtype(fptype), sign, value))
       
    print("---FPUnpack---")   
    do_FPUnpack(0xffff,      FPType.QNaN, psr = 0)
    do_FPUnpack(0xffffffff,  FPType.QNaN, psr = 0)
    do_FPUnpack(0,           FPType.Zero, psr= 0)
    do_FPUnpack(0x3fc00000,  FPType.Nonzero, psr= 0)
    do_FPUnpack(0xbfc00000,  FPType.Nonzero, psr= 0)
    do_FPUnpack(0x3e00,  FPType.Nonzero, psr= 0)
    do_FPUnpack(0xbe00,  FPType.Nonzero, psr= 0)    
    do_FPUnpack(0x8000,      FPType.Zero, 0)      # FPZero
    do_FPUnpack(FPZero(0, 32),FPType.Zero, 0)
    do_FPUnpack(0x80000000,   FPType.Zero, 0)  # FPZero
    do_FPUnpack(0x7fc00000,   FPType.QNaN, 0)  # QNaN
    do_FPUnpack(FPDefaultNaN(32),FPType.QNaN, 0)
    do_FPUnpack(0x7e00,          FPType.QNaN, 0)      # QNaN
    do_FPUnpack(0x7d00,          FPType.SNaN, 0)      # SNaN
    do_FPUnpack(0xfd00,          FPType.SNaN, 0)      # SNaN
    do_FPUnpack(0x7fa00000,      FPType.SNaN, 0)      # SNaN
    do_FPUnpack(0xffa00000,      FPType.SNaN, 0)      # SNaN    
    do_FPUnpack(0x7f7fffff,      FPType.Nonzero, 0)   # MaxNormal
    do_FPUnpack(FPMaxNormal(1, 32), FPType.Nonzero, 0)
    do_FPUnpack(0x7bff, FPType.Nonzero, 0)      # MaxNormal
    do_FPUnpack(0xfc00, FPType.Infinity, 0)      # FPInfinity
    do_FPUnpack(0x7c00, FPType.Infinity,0)
    do_FPUnpack(0xff800000, FPType.Infinity,0)
    do_FPUnpack(FPInfinity(1, 32), FPType.Infinity, 0)
    do_FPUnpack(0x7f800000, FPType.Infinity, 0)
    
    def do_FPRound(val, n, psr):
        result = FPRound(val, n, psr)
        print("{:f}, rounded gets {:f}".format(val,  result))
    
    print("---FPRound---")   
    do_FPRound(1.9, 32, 0)
    do_FPRound(-1.9, 32, 0)
    do_FPRound(2.666666666, 32, 0)
    do_FPRound(2666666666666.7, 32, 0)
    do_FPRound(-266666666666.7, 32, 0)
    
    
    def do_dbl_convert(val):
        fpscr = 0
        res0 = unchecked_conversion.convert_float_to_int(val)
        res1, fpscr = FPSingleToHalf(res0, fpscr, fpscr_controlled = False)
        res2 = unchecked_conversion.convert_float_to_int(res1)
        res3, fpscr = FPHalfToSingle(res2, fpscr, fpscr_controlled = False)
        if val == res3:
            print("Pass: val = {:f}".format(val))
        else:
            print("Fail: {:f} becomes {:f} after double convert".format(val, res3))
            diff = res3 - val
            print("difference = {:.8f}".format(diff))
     
    print("---Convert single to half then back to single---")   
    do_dbl_convert(1.5)
    do_dbl_convert(-1.5)
    do_dbl_convert(2.66667) 
    do_dbl_convert(-2.666667)
    do_dbl_convert(65504.0) 
    do_dbl_convert(-65504.0) 
    do_dbl_convert(FPZero(0, 32))
    do_dbl_convert(FPDefaultNaN(32))
    
    
    # so many more tests to write