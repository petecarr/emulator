""" disassembled_string, extra_halfwords  = disass(offset, half_words) """
# Path hack for access to utilities and siblings.
import sys, os
sys.path.insert(0, os.path.abspath('..'))

#from utilities import  bit_fields, my_hex, check_for_diffs
from utilities.bit_fields import *
#from utilities.my_hex import *
#from utilities.check_for_diffs import *

from msp430.msp430cpu import conds
from msp430.msp430cpu import SPACES, ICOLUMN, PC, SR  #, SP
from msp430.msp430cpu import get_reg, get_sym, das_strings
from msp430.msp430cpu import extend_sign, dp_opcodes

   

#----------------------------------------------------------------------------

#    Disassemble a word containing an msp430 instruction.

#----------------------------------------------------------------------------
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
#11/-   Immediate mode      #N         The word following the instruction
#                                      contains the immediate constant N. 
#                                      Indirect autoincrement mode @PC+ is used.

# Constant Generators
#Register As Constant Remarks
#R2       00  -       Register Mode
#R2       01 (0)      Absolute address mode
#R2       10 00004    +4, bit processing
#R2       11 00008    +8, bit processing
#R3       00 00000    0, word processing
#R3       01 00000    +1
#R3       10 00002    +2, bit processing
#R3       11 FF, FFFF, FFFFF -1, word processing

def get_dest(dest):
    """ Interpret the destination address of a jump or symbolic instruction."""
    return "{0:#x} ;{1:s}".format(dest, get_sym(dest))
    
def get_full_address(offset, words, mode, reg, one_op = False):
    # Mode is 2 bits, constant generation is supported
    res = ""
    extr = 0

    if mode == 0:
        if reg == 3:
            res += '#0'  # constant generation
        else:        
            res += get_reg(reg)
    elif mode == 1:
        if reg == PC:  # symbolic mode
            extr += 1
            dest = offset + 2 + words[extr]
            res += get_dest(dest)
        elif reg == SR:  # absolute mode
            extr += 1
            res += '&' + '{:#x}'.format(words[extr])
        elif reg == 3:
            res += '#1'   # constant generation
        else:    # indexed mode
            extr += 1
            res += '{:#x}'.format(words[extr]) +'(' + get_reg(reg) + ')'
    elif mode == 2:  # indirect register mode
        if reg == SR:
            res += '#4'   # constant generation
        elif reg == 3:
            res += '#2'   # constant generation
        else:
            res += '@' + get_reg(reg)
    elif mode == 3:
        if reg == PC:  # immediate mode
            extr += 1
            if one_op:
                res += get_dest(words[extr])
            else:
                res += '#' + '{:#x}'.format(words[extr])            
        elif reg == SR:
            res += '#8'  # constant generation
        elif reg == 3:
            res += '#-1'
        else:  # indirect autoincrement mode
            res += '@' + get_reg(reg) + '+'
    return res, extr

def get_dst2_addr(offset, words):
    """ Single operand, format 2 instructions. """
    a_dst = get_field(words[0], 4, 5) 
    dst_reg = get_field(words[0], 0, 3)
    return get_full_address(offset, words, a_dst, dst_reg, one_op = True)

def get_dst_addr(offset, words, extr = 0):
    """ Dual operand destination. Restricted formats. No consts. """
    res = ""
    a_dst = get_field(words[0], 7, 7) 
    dst_reg = get_field(words[0], 0, 3)
    if a_dst == 0:
        res += get_reg(dst_reg)
    elif a_dst == 1:
        extr += 1
        if dst_reg == PC:   # symbolic mode
            dest = offset + 2 + words[extr]
            res += get_dest(dest)
        elif dst_reg == SR:  # absolute mode
            res += '&' + '{:#x}'.format(words[extr])
        else:                # indexed mode
            res += '{:#x}'.format(words[extr]) +'(' + get_reg(dst_reg) + ')'
    return res, extr


def get_src_addr(offset, words):
    """ Dual operands src operand. """
    a_src = get_field(words[0], 4, 5) 
    src_reg = get_field(words[0], 8, 11)
    return get_full_address(offset, words, a_src, src_reg, one_op = False)

  

def dual_operands(offset, words):
    """ Format 1. Dual operands, opcodes 4-15 - src and dst """
    # F000             0F00          0080   0040   0030   000F
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
    
    res = ""
    opcode = words[0] >> 12
    if opcode >= 4:
        res += dp_opcodes[opcode]
    else:
        res += "<unexpected opcode {:x}>".format(opcode)
        return res, 0
    if testBit(words[0], 6):
        res += '.b'
    else:
        res += '.w'
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    tmp_res, extr1 = get_src_addr(offset, words)
    res += tmp_res + ', '
    tmp_res, extr2 = get_dst_addr(offset, words, extr1)
    res += tmp_res
    return res, extr2

def jumps(offset, words):
    """ Conditional jump instructions. Opcodes 2 and 3 """
    # 2000  JNE/JNZ       Z == 0         PC = PC +2 + extendSign(offset, 10) *2
    # 2400  JEQ/JZ        Z == 1
    # 2800  JNC           C == 0
    # 2c00  JC            C == 1
    # 3000  JN            N == 1
    # 3400  JGE           (N ^ V) == 0
    # 3800  JL            (N ^ V) == 1
    # 3c00  JMP           1 == 1    
    res = ""
 
    relative_offset = extend_sign(words[0] & 0x3ff, 10) *2
    dest = offset + 2 + relative_offset
    cond = get_field(words[0], 10, 12)
    res += 'j' + conds[cond]

    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_dest(dest)
    
    return res

def single_operand(offset, words):
    """ Format 2. Single operand. Opcode 1. """
    # Opcode            B/W  Ad   Rdst
    # FF80              0040 0030 000F
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
    res = ""
    if testBit(words[0], 6):
        borw = '.b'
    else:
        borw = ''
    opcode = words[0] & 0xff80
    if opcode == 0x1000:
        res += 'rrc' + borw
    elif opcode == 0x1080:
        res += 'swpb'
    elif opcode == 0x1100:
        res += 'rra' + borw
    elif opcode == 0x1180:
        res += 'sxt'
    elif opcode == 0x1200:
        res += 'push' + borw
    elif opcode == 0x1280:
        res += 'call'
    elif opcode == 0x1300:
        res += 'reti'
        return res, 0
    else:
        res += "<unexpected opcode {:x}>".format(opcode)
        return res, 0
       
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    tmp_res, extr = get_dst2_addr(offset, words)
    res += tmp_res
    return res, extr    
    
def disass(offset, words, dummy = False):
    """ Sort out the instruction categories and pass the word 
        to be disassembled to the corresponding routine.
    """
    res=""
    if offset in das_strings:
        return das_strings[offset]  # cached
    ins_type = get_field(words[0], 12, 15)
    extr = 0   # extra halfwords
 
    if ins_type == 1:          # format 2
        tmp_res, extr = single_operand(offset, words)
    elif ins_type == 2 or ins_type == 3:
        tmp_res = jumps(offset, words)
    elif 4 <= ins_type <= 15:  #  format 1
        tmp_res, extr = dual_operands(offset, words)
    else:
        tmp_res ="<undefined {:x}>".format(words[0])
        
    res += tmp_res
    das_strings[offset] = (res, 2+ extr*2)  # cache it
    # I think these are not needed
    #if extr >= 1:
    #    das_strings[offset+2] = ("", 2)
    #if extr >= 2:
    #    das_strings[offset+4] = ("", 2)
    return (res, 2+ extr*2)

def cmp(string1, string2):
    """ Compare two strings for unit testing. """
    if string1 == string2:
        print( "PASS : "+string1)
    else:
        print("FAIL    : "+string1)
        print("Expected: "+string2)



if __name__ == '__main__':
    # If you run this as a main program some unit testing is done.
    
    from arch import machine
    if machine != "MSP430":
        import sys
        print("This file, msp430/disass.py, is for the msp430 only. Check arch.py\n")
        quit()     

    print("*** disass.py module ***")


    # This is not a program, just some random instructions pulled from images
    cmp(disass(0,      [0x120A, 0, 0]) [0],    "push     r10")
    cmp(disass(8,      [0x124A, 0, 0]) [0],    "push.b   r10")
    cmp(disass(14,     [0x4A0C])  [0],         "mov.w    r10, r12")
    cmp(disass(16,     [0x4A4C])  [0],         "mov.b    r10, r12")
    cmp(disass(18,     [0x4C1A, 0xFB86]) [0],  "mov.w    0xfb86(r12), r10")
    cmp(disass(22,     [0x4C5A, 0xFB86]) [0],  "mov.b    0xfb86(r12), r10")
    cmp(disass(26,     [0x403C, 0x00B4]) [0],  "mov.w    #0xb4, r12")
    cmp(disass(30,     [0x407C, 0x00B4]) [0],  "mov.b    #0xb4, r12") 
    cmp(disass(34,     [0x453A]) [0],          "mov.w    @r5+, r10")
    cmp(disass(36,     [0x457A]) [0],          "mov.b    @r5+, r10")
    cmp(disass(38,     [0x433f]) [0],          "mov.w    #-1, r15")
    cmp(disass(40,     [0x437f]) [0],          "mov.b    #-1, r15")
    cmp(disass(42,     [0x430f]) [0],          "mov.w    #0, r15")
    cmp(disass(44,     [0x434f]) [0],          "mov.b    #0, r15")
    cmp(disass(46,     [0x431f]) [0],          "mov.w    #1, r15")
    cmp(disass(48,     [0x435f]) [0],          "mov.b    #1, r15") 
    cmp(disass(50,     [0x4323]) [0],          "mov.w    #2, r3")
    cmp(disass(52,     [0x4363]) [0],          "mov.b    #2, r3") 
    cmp(disass(54,     [0x422f]) [0],          "mov.w    #4, r15")
    cmp(disass(56,     [0x426f]) [0],          "mov.b    #4, r15") 
    cmp(disass(58,     [0x4232]) [0],          "mov.w    #8, sr")
    cmp(disass(60,     [0x4272]) [0],          "mov.b    #8, sr")    
    cmp(disass(62,     [0x40b2, 0x5a80, 0x0120])[0],  "mov.w    #0x5a80, &0x120")
    cmp(disass(68,     [0x40f2, 0x5a80, 0x0120])[0],  "mov.b    #0x5a80, &0x120")
    cmp(disass(74,     [0x5A0C])  [0],          "add.w    r10, r12")
    cmp(disass(76,     [0x5A4C])  [0],          "add.b    r10, r12")
    cmp(disass(78,     [0x6f0b]) [0],           "addc.w   r15, r11")
    cmp(disass(80,     [0x6f4b]) [0],           "addc.b   r15, r11")
    cmp(disass(82,     [0x8e09])  [0],          "sub.w    r14, r9")
    cmp(disass(84,     [0x7e49])  [0],          "subc.b   r14, r9")
    cmp(disass(86,     [0xf0f2, 0x003f, 0x0023]) [0], "and.b    #0x3f, &0x23")
    cmp(disass(92,     [0x90B2, 0x0024, 0x0208]) [0], "cmp.w    #0x24, &0x208")
    cmp(disass(98,     [0xa698, 0x0024, 0x0208]) [0], "dadd.w   0x24(r6), 0x208(r8)")
    cmp(disass(104,    [0xa6d8, 0x0024, 0x0208]) [0], "dadd.b   0x24(r6), 0x208(r8)")
    cmp(disass(110,    [0xe2e2, 0x0021]) [0],  "xor.b    #4, &0x21")
    cmp(disass(114,    [0x2012]) [0],  "jne      0x98 ;")
    cmp(disass(116,    [0x280C]) [0],  "jnc      0x8e ;")
    cmp(disass(118,    [0x240C]) [0],  "jeq      0x90 ;")
    cmp(disass(120,    [0x2c10]) [0],  "jc       0x9a ;")
    cmp(disass(122,    [0x3c02]) [0],  "jmp      0x80 ;")
    cmp(disass(124,    [0x1300]) [0],  "reti")
    cmp(disass(126,    [0x12B0, 0xF958]) [0],  "call     0xf958 ;")
    cmp(disass(130,    [0x12b0, 0x000a]) [0],  "call     0xa ;")
    cmp(disass(134,    [0x12af]) [0],  "call     @r15")
    cmp(disass(136,    [0x128f]) [0],  "call     r15")
    cmp(disass(138,    [0x1290, 0x0600]) [0],  "call     0x68c ;")

    cmp(disass(142,    [0x100d]) [0],  "rrc      r13")
    cmp(disass(144,    [0x104d]) [0],  "rrc.b    r13")
    cmp(disass(146,    [0x1084]) [0],  "swpb     r4")
    cmp(disass(148,    [0x1190, 0x0800]) [0],  "sxt      0x896 ;")
    
    cmp(disass(152,    [0xb0b2, 0xff80, 0x0022]) [0],"bit.w    #0xff80, &0x22")
    cmp(disass(158,    [0xb0f2, 0xff80, 0x0023]) [0],"bit.b    #0xff80, &0x23")
    cmp(disass(164,    [0xc392, 0x0020]) [0],        "bic.w    #1, &0x20")
    cmp(disass(168,    [0xc3d2, 0x0021]) [0],        "bic.b    #1, &0x21")
    cmp(disass(172,    [0xd4a2, 0x0024]) [0],        "bis.w    @r4, &0x24")
    cmp(disass(176,    [0xd3d2, 0x0021]) [0],        "bis.b    #1, &0x21")
   

    print("------------ Low priority diffs ------------")

    cmp(disass(300,    [0x413A]) [0],    "pop.w    r10")
    cmp(disass(302,    [0x5c0c]) [0],    "rla.w    r12")
    cmp(disass(304,    [0x4130]) [0],    "ret")
    cmp(disass(306,    [0xd232]) [0],    "eint")
    cmp(disass(308,    [0xe33f]) [0],    "inv.w    r15")
    cmp(disass(310,    [0x5392, 0x0208]) [0],  "inc.w    &0x208")
    cmp(disass(314,    [0x9382, 0x0208])  [0],  "tst.w    &0x208")