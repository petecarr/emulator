# Path hack for access to utilities and siblings.
import sys, os
sys.path.insert(0, os.path.abspath('..'))

from utilities import  bit_fields, my_hex, check_for_diffs, unchecked_conversion
from utilities.bit_fields import *
from utilities.my_hex import *
from utilities.check_for_diffs import *
from utilities import logging
from utilities.logging import *

from arm.armcpu import cond, is_thumb32
from arm.armcpu import SPACES, ICOLUMN
from arm.armcpu import get_reg, get_fpreg, get_dfpreg, reg_list, get_sym
from arm.armcpu import get_It_suffices, ThumbExpandImm_Craw, ThumbExpandImm
from arm.armcpu import ZeroExtend12, ZeroExtend16, extend_sign, DisassImmShift

unpredictable = 'UNPREDICTABLE'
undefined = 'UNDEFINED'


#---------------------------------------------------------------------------
# Still looking for a nice way to do this. See line 39
def tab_to(res, new_column):
    res += SPACES[len(res):new_column] 
    return res, new_column

def thumb_1(offset, a_word, cond_code):
    """ move shifted register """
    res = ""
    column = 0
    opcode = get_field(a_word, 11, 12)
    rd = get_field(a_word, 0, 2)
    rs = get_field(a_word, 3, 5)
    offs = get_field(a_word, 6, 10)
    if opcode == 0:
        res += "lsl"
    elif opcode == 1:
        res += "lsr"
    elif opcode == 2:
        res += "asr"
    else:
        return thumb_2(offset, a_word, cond_code)
    #column = 3
    #res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res, column = tab_to(res, ICOLUMN)
    res += get_reg(rd) + ", " + get_reg(rs)
    if offs == 0:
        if opcode == 1 or opcode == 2:
            offs = 32
    res += ", #{0:d}".format(offs)
    return res

def thumb_2(offset, a_word, cond_code):
    """ add/subtract """
    res = ""
    column = 0
    opcode = get_field(a_word, 9, 10)
    rd = get_field(a_word, 0, 2)
    rs = get_field(a_word, 3, 5)
    offset = get_field(a_word, 6, 8)
    if opcode == 0:
        res += "add"
    elif opcode == 1:
        res += "sub"
    elif opcode == 2:
        if offset == 0:
            res += "mov"
        else:
            res += "add"
    elif opcode == 3:
        res += "sub"
    column = 3
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rd) + ", " + get_reg(rs)
    if testBit(a_word, 10):
        if opcode != 2 or offset != 0:
            res += ", #{:d}".format(offset)
    else:
        res += ", " +get_reg(offset)
    return res

def thumb_3(offset, a_word, cond_code):
    """ move/compare/add/subtract immediate """
    res = ""
    column = 0
    opcode = get_field(a_word, 11, 12)
    rd = get_field(a_word, 8, 10)
    offs = get_field(a_word, 0, 7)
    if opcode == 0:
        res += "mov"
    elif opcode == 1:
        res += "cmp"
    elif opcode == 2:
        res += "add"
    elif opcode == 3:
        res += "sub"
    column = 3
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rd) +  ", #{:d}".format(offs)
    return res

def thumb_4(offset, a_word, cond_code):
    """ ALU operations """
    res = ""
    column = 0
    opcode = get_field(a_word, 6, 9)
    rs = get_field(a_word, 3, 5)
    rd = get_field(a_word, 0, 2)
    # similar to dp_opcodes but not quite the same
    if opcode == 0:
        res += "and"
    elif opcode == 1:
        res += "eor"
    elif opcode == 2:
        res += "lsl"
    elif opcode == 3:
        res += "lsr"
    elif opcode == 4:
        res += "asr" 
    elif opcode == 5:
        res += "adc" 
    elif opcode == 6:
        res += "sbc"
    elif opcode == 7:
        res += "ror" 
    elif opcode == 8:
        res += "tst" 
    elif opcode == 9:
        res += "neg" 
    elif opcode == 10:
        res += "cmp" 
    elif opcode == 11:
        res += "cmn" 
    elif opcode == 12:
        res += "orr" 
    elif opcode == 13:
        res += "mul" 
    elif opcode == 14:
        res += "bic" 
    elif opcode == 15:
        res += "mvn" 
    column = 3
    # how does assembler distinguish orr from orrs, for example? (itstate)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rd) + ", " + get_reg(rs) 
    return res



def thumb_5(offset, a_word, cond_code):
    """ high register operations branch/exchange """
    res = ""
    opcode = get_field(a_word, 8, 9)
    msbd = get_field(a_word, 7, 7) << 3
    msbs = get_field(a_word, 6, 6) << 3
    rs = get_field(a_word, 3, 5) | msbs
    rd = get_field(a_word, 0, 2) | msbd
    if opcode == 0:
        res += "add"
    elif opcode == 1:
        res += "cmp"
    elif opcode == 2:
        if rs == 8  and rd == 8:
            res += "nop      ; == mov r8, r8"
            return res
        else:
            res += "mov"
    elif opcode == 3:
        if msbd == 0:
            res += "bx"
        else:
            res += "blx"
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    if opcode != 3:
        res += get_reg(rd) + ", "
    res += get_reg(rs)
    return res

def thumb_6(offset, a_word, cond_code):
    """ load word pc-relative """
    res = ""
    rd = get_field(a_word, 8, 10)
    val = get_field(a_word, 0, 7) << 2
    dest = val + 4 + (offset//4)*4   # if on odd halfword
    res += "ldr"
    column = 3
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rd) + ", [pc+" + "{:#x}] ;({:#x}, {:s})".format(val, 
                                                        dest, get_sym(dest))
    return res

def thumb_7(offset, a_word, cond_code):
    """ load/store with register offset """
    res = ""
    opcode = get_field(a_word, 10, 11)
    roffs = get_field(a_word, 6, 8)
    rb = get_field(a_word, 3, 5)
    rd = get_field(a_word, 0, 2)
    if opcode == 0:
        res += "str"
    elif opcode == 1:
        res += "strb"
    elif opcode == 2:
        res += "ldr"
    elif opcode == 3:
        res += "ldrb"
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rd) + ", [" + get_reg(rb) + ", " + get_reg(roffs) + "]"
    return res

def thumb_8(offset, a_word, cond_code):
    """ load/store sign extended byte/halfword """
    res = ""
    opcode = get_field(a_word, 10, 11)
    roffs = get_field(a_word, 6, 8)
    rb = get_field(a_word, 3, 5)
    rd = get_field(a_word, 0, 2)
    if opcode == 0:
        res += "strh"
    elif opcode == 1:
        res += "ldsb"
    elif opcode == 2:
        res += "ldrh"
    elif opcode == 3:
        res += "ldsh"
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rd) + ", [" + get_reg(rb) + ", " + get_reg(roffs) + "]"
    return res

def thumb_9(offset, a_word, cond_code):
    """ load/store with immediate offset """
    res = ""
    opcode = get_field(a_word, 11, 12)
    offs = get_field(a_word, 6, 10)
    if opcode < 2:
        offs  <<= 2
    rb = get_field(a_word, 3, 5)
    rd = get_field(a_word, 0, 2)
    if opcode == 0:
        res += "str"
    elif opcode == 1:
        res += "ldr"
    elif opcode == 2:
        res += "strb"
    elif opcode == 3:
        res += "ldrb"
    column =len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rd) + ", [" + get_reg(rb)
    if offs != 0:
        res += ", #{:#x}".format(offs)
    res += ']'
    return res

def thumb_10(offset, a_word, cond_code):
    """ load/store halfword """
    res = ""
    opcode = get_field(a_word, 11, 11)
    offs = get_field(a_word, 6, 10) << 1
    rb = get_field(a_word, 3, 5)
    rd = get_field(a_word, 0, 2)
    if opcode == 0:
        res += "strh"
    elif opcode == 1:
        res += "ldrh"
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rd) + ", [" + get_reg(rb)
    if (offs != 0):
        res += ", #{:#x}".format(offs)
    res += ']'    

    return res

def thumb_11(offset, a_word, cond_code):
    """ load/store sp-relative """
    res = ""
    if testBit(a_word, 11):
        res += "ldr"
    else:
        res += "str"
    rd = get_field(a_word, 8, 10)
    offs = get_field(a_word, 0, 7) << 2
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rd) + ", [sp"
    if (offs != 0):
        res += ", #{:#x}".format(offs)
    res += ']'    
    return res

def thumb_12(offset, a_word, cond_code):
    """ get relative address """
    res = "add"
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rd = get_field(a_word, 8, 10)
    res += get_reg(rd) + ", "
    if testBit(a_word, 11):
        res += 'sp, '
    else:
        res += 'pc, '
    offs = get_field(a_word, 0, 7)
    res += "#{0:#x}".format(offs)
    return res



def thumb_14(offset, a_word, cond_code):   # a hangover from an old spec
    """ push/pop registers """
    res = ""
    opcode = get_field(a_word, 11, 11)
    must_be = get_field(a_word, 9, 10)
    if must_be != 2:
        res += "invalid format for push/pop, {:#x}".format(a_word)
        return res
    pc_lr = get_field(a_word, 8, 8)
    rlist = get_field(a_word, 0, 7)
    if opcode == 0:
        res += "push"
    else:
        res += "pop"
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    if pc_lr == 1:
        if opcode == 0:
            rlist += 0x4000  # push r14 (lr)
        else:
            rlist += 0x8000  #  pop r15  (pc)
    res += reg_list(rlist)
    return res


def thumb_15(offset, a_word, cond_code):
    """ multiple load/store """
    res = ""
    opcode = get_field(a_word, 11, 11)
    rb = get_field(a_word, 8, 10)
    rlist = get_field(a_word, 0, 7)
    if opcode == 0:
        res += "stmia"
    else:
        res += "ldmia"
    column = len(res)
    if testBit(rlist, rb):
        wback = '!'
    else: 
        wback = ''
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rb) +wback +  ", " + reg_list(rlist)
    return res


def thumb16_cb_svc(offset, a_word, cond_code):
    """ conditional branch and svc"""
    res = ""
    opcode = get_field(a_word, 8, 11)
    offs = get_field(a_word, 0, 7)
    if testBit(offs, 7):
        offs  = (offs - 0x100)
    offs <<= 1
    if opcode <= 13:
        res += 'b'+cond(opcode)
    elif opcode == 14:
        return undefined  
    elif opcode == 15:
        return thumb16_misc_svc(offset, a_word, cond_code)
    res += '.n'  # narrow encoding, eg. 16 bits
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    dest = offset + 4 + offs
    res+="{0:#x} ;{1:s}".format(dest, get_sym(dest))    
    return res

#------------ 16 bit miscellaneous -------------------------------------

def thumb16_misc_svc(offset, a_word, cond_code):
    """ Supervisor call (previously software interrupt swi) """
    res = ""
    comment = get_field(a_word, 0, 7)
    res+= "svc"
    column = 3
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    res += "{0:#x}".format(comment)
    return res

def thumb16_misc_bkpt(offset, a_word, cond_code):
    """ breakpoint """
    res = ""
    comment = get_field(a_word, 0, 7)
    res+= "bkpt"
    column = 4
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += "{0:#x}".format(comment)
    return res

def thumb16_misc_pop(offset, h_word, cond_code):
    res = 'pop'
    column = 3
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rlist = (get_field(h_word, 8,8) << 15) | get_field(h_word, 0, 7)
    res += reg_list(rlist)
    return res

def thumb16_misc_push(offset, h_word, cond_code):
    res = 'push'
    column = 4
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rlist = (get_field(h_word, 8, 8) << 14) | get_field(h_word, 0, 7)
    res += reg_list(rlist)
    return res

def thumb16_misc_cb(offset, h_word, cond_code):
    res = 'cb'
    if get_field(h_word, 11, 11):
        res += 'nz'
    else:
        res += 'z'
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(get_field(h_word, 0, 2))
    dest = offset + 4 + ((get_field(h_word, 9, 9) << 7) | (
                          get_field(h_word, 3, 7) << 1))
    res += ', #{:#x} ;{:s}'.format(dest, get_sym(dest))  
    return res

def thumb16_misc_rev(offset, h_word, cond_code):
    res = 'rev'
    subopcode = get_field(h_word, 6, 7)
    if subopcode == 0:
        pass  # reverse byte order in 32 bit word
    elif subopcode == 1:
        res += '16' # reverse byte order in each halfword in 32 bit word
    elif subopcode == 3:
        res += 'sh' # reverse byte order in lower 16 bit hw and sign extends
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(get_field(h_word, 0, 2)) + ', ' + get_reg(get_field(h_word, 3, 5)) # rd, rm
    return res


def thumb16_misc_extend(offset, h_word, cond_code):
    res = ""
    subopcode = get_field(h_word, 6, 7)
    if subopcode == 0:
        res += 'sxth'
    elif subopcode == 1:
        res += 'sxtb'
    elif subopcode == 2:
        res += 'uxth'
    elif subopcode == 3:
        res += 'uxtb'
    column = len(res)          
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(get_field(h_word, 0, 2)) + ', ' + get_reg(
                   get_field(h_word, 3, 5)) # rd, rm 
    return res

def thumb16_misc_sub_sp_imm(offset, h_word, cond_code):
    res = 'sub'
    column = 3
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += 'sp, sp, #' + '{:#x}'.format(get_field(h_word, 0, 6))   
    return res

def thumb16_misc_add_sp_imm(offset, h_word, cond_code):
    res = 'add'
    column = 3
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += 'sp, sp, #' + '{:#x}'.format(get_field(h_word, 0, 6))   
    return res

def thumb16_misc_cps(offset, h_word, cond_code):
    """ Change processor state,  armv7-M """
    res = 'cps'
    if get_field(h_word, 4, 4):
        res += 'id'
    else:
        res += 'ie'
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    if get_field(h_word, 1, 1):
        res += 'i'
    if get_field(h_word, 0, 0):
        res += 'f'
    return res



def thumb16_misc_ifthen(offset, h_word):
    opa = get_field(h_word, 4, 7)
    opb = get_field(h_word, 0, 3)
    if opb != 0:
        res =  "it{:s}".format(get_It_suffices(opa&1, opb))
        column = len(res)
        res += SPACES[column:ICOLUMN]; column = ICOLUMN
        res += cond(opa)
        return res
    if opa == 0:
        """ nop 0xbf00 """
        return 'nop'    
    elif opa == 1:
        return 'yield'
    elif opa == 2:
        return 'wfe'
    elif opa == 3:
        return 'wfi'
    elif opa == 4:
        return 'sev'
    else:
        return 'unexpected if-then'
    
def thumb16_misc(offset, h_word, cond_code):
    res = ""
    opcode = get_field(h_word, 5, 11)
    op1 = get_field(h_word, 8, 11)
    if op1 == 0xf:
        res += thumb16_misc_ifthen(offset, h_word) 
    elif op1 == 0xe:
        res += thumb16_misc_bkpt(offset, h_word, cond_code)
    elif (op1 == 0xc) or (op1 == 0xd):
        res += thumb16_misc_pop(offset, h_word, cond_code)
    elif (op1 == 1) or (op1 == 3) or (op1 == 9) or (op1 == 0xb):
        res += thumb16_misc_cb(offset, h_word, cond_code)
    elif op1 == 2:
        res += thumb16_misc_extend(offset, h_word, cond_code)
    elif (op1 == 4) or (op1 == 5):
        res += thumb16_misc_push(offset, h_word, cond_code)
    elif op1 == 0xa:
        res += thumb16_misc_rev(offset, h_word, cond_code)
    elif (opcode & 0x7c) == 4:
        res += thumb16_misc_sub_sp_imm(offset, h_word, cond_code) 
    elif (opcode & 0x7c) == 0:
        res += thumb16_misc_add_sp_imm(offset, h_word, cond_code)
    elif opcode == 0x33:
        res += thumb16_misc_cps(offset, h_word, cond_code)
    
    return res

#-----------------------------------------------------------------------------        

def thumb16_branch(offset, a_word, cond_code):
    """ unconditional branch """
    res = ""
    column = 0
    res += "b"
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    # T2 format
    val = get_field(a_word, 0, 10) 
    val = extend_sign(val, 10)
    val <<= 1
    dest = offset + 4 + val
  
    res+="{0:#x} ;{1:s}".format(dest, get_sym(dest))
    return res


def thumb_19a(offset, a_word, cond_code): # I don't think we get here - thumb32
    """ long branch and link """
    res = ""
    column = 0
    next_opcode = get_field(a_word, 27, 31)
    if next_opcode != 31 and next_opcode != 29:
        res += "unidentified 19a"
        return res
    targ_addr = get_field(a_word, 0, 10) << 12
    targ_addr |= get_field(a_word, 16, 26) << 1
    if testBit(targ_addr, 22):   # extend_sign()?
        targ_addr = targ_addr - 0x800000
    targ_addr = offset + 4 + targ_addr

    res += "bl"
    if  not testBit(a_word, 28):
        res += 'x'
    
    column = len(res)   
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += "{0:#x} ;{:s}".format(targ_addr, get_sym(targ_addr))   # not complete
    return res

def thumb_19b(offset, a_word, cond_code): # I don't think we get here - thumb32
    """ long branch and link (part 2) """
    res = ""
    column = 0
    res = "Unidentified 19b"
    return res

#---------------------------------------------------------------------
#  32 bit Thumb stuff
#----------------------------------------------------------------------



#--------------Data processing modified immediate A6-15------------------

def t3_and(offset, a_word):
    res = ""
    setflags = False
    column = 3
    res += 'and'
    if get_field(a_word, 20, 20) :
        column +=1
        res += 's'
        setflags = True
    res += ".w"
    column += 2    
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    res +=  get_reg(rd) + ", " + get_reg(rn) + ", "
    
    imm32 = ThumbExpandImm_Craw(a_word)

    res += "#{0:#x}".format(imm32)
    return res

def t1_tst(offset, a_word, opcode):
    res = ""
    column = len(opcode)
    res += opcode
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    res +=  get_reg(rn) + ", "    
    imm32 = ThumbExpandImm_Craw(a_word)
    res += "#{0:#x}".format(imm32)    
    return res


def t1_immw_2reg(offset, a_word, opcode, wide_instr): 
    # opcode{s}{.w} rd,rn,#imm_c
    res = ""
    column = len(opcode)
    res += opcode
    setflags_bit= get_field(a_word, 20, 20)
    if setflags_bit != 0:
        res += 's'
        column += 1
    if wide_instr:
        res += '.w'
        column += 2
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    res +=  get_reg(rd) + ", " + get_reg(rn) + ", "   
    imm32 = ThumbExpandImm_Craw(a_word)
    res += "#{0:#x}".format(imm32)    
    return res  

def t2_immw_1reg(offset, a_word, opcode, wide_instr):  
    # opcode{s}{.w} rd,r#imm_c
    res = ""
    column = len(opcode)
    res += opcode
    setflags_bit= get_field(a_word, 20, 20)
    if setflags_bit != 0:
        res += 's'
        column += 1
    if wide_instr:
        res += '.w'
        column += 2
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rd = get_field(a_word, 8, 11)
    res +=  get_reg(rd) + ", "   
    imm32 = ThumbExpandImm_Craw(a_word)
    res += "#{0:#x}".format(imm32)    
    return res    
  
  
def t1_bic(offset, a_word):
    return t1_immw_2reg(offset, a_word, 'bic', False)

def t1_orr(offset, a_word):
    return t1_immw_2reg(offset, a_word, 'orr', False)

def t1_orn(offset, a_word):
    return t1_immw_2reg(offset, a_word, 'orn', False)

def t2_mov(offset, a_word):
    return t2_immw_1reg(offset, a_word, 'mov', True)
    
def t1_mvn(offset, a_word):   
    return t2_immw_1reg(offset, a_word, 'mvn', False)  # actually t1

def t1_eor(offset, a_word):
    return t1_immw_2reg(offset, a_word, 'eor', False)

def t3_const_2reg(offset, a_word, opcode, wide_instr):
    # so near to t3_and() just ThumbExpandImm{_C}
    # opcode{s}.w Rd, Rn, #const
    res = ""
    setflags = False
    column = len(opcode)
    res += opcode
    if get_field(a_word, 20, 20) :
        column +=1
        res += 's'
        setflags = True
    if wide_instr:
        res += ".w"
        column += 2    
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    res +=  get_reg(rd) + ", " + get_reg(rn) + ", "
    imm32 = ThumbExpandImm(a_word)
    res += "#{0:#x}".format(imm32)
      
    return res
    
def t3_add(offset, a_word):
    return t3_const_2reg(offset, a_word, 'add', True)

def t2_cmp(offset, a_word, opcode):  #opcode.w rn,#imm
    res = ""
    column = 0
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    res += get_reg(rn) + ", "
    imm32 = ThumbExpandImm(a_word)
    res += "#{0:#x}".format(imm32)
    return res

def t1_adc(offset, a_word):
    return t3_const_2reg(offset, a_word, 'adc', False)

def t1_sbc(offset, a_word):
    return t3_const_2reg(offset, a_word, 'sbc', False)

def t3_sub(offset, a_word):
    return t3_const_2reg(offset, a_word, 'sub', True)

def t2_rsb(offset, a_word):
    return t3_const_2reg(offset, a_word, 'rsb', True)

#---------------------------------------------------------------------------

def dp_modified_immediate(offset, a_word):
    res = ""
    op = get_field(a_word, 21, 24)
    rn = get_field(a_word, 16, 19)
    s_bit = get_field(a_word, 20, 20)
    rd = get_field(a_word, 8, 11)
    if (op == 0):
        if rd != 15:
            res += t3_and(offset, a_word)
        else:
            if s_bit == 1:
                res += t1_tst(offset, a_word, 'tst')
            else:
                res += unpredictable
    elif op == 1:
        res += t1_bic(offset, a_word)
    elif op == 2:
        if rn != 15:
            res += t1_orr(offset, a_word)
        else:
            res += t2_mov(offset, a_word)
    elif op == 3:
        if rn != 15:
            res += t1_orn(offset, a_word)
        else:
            res += t1_mvn(offset, a_word)       
    elif op == 4:
        if rd != 15:
            res += t1_eor(offset, a_word)
        else:
            if s_bit == 1:
                res += t1_tst(offset, a_word, 'teq')
            else:
                res += unpredictable
    elif op == 8:
        if rd != 15:
            res += t3_add(offset, a_word)
        else:
            if s_bit == 1:
                res += t2_cmp(offset, a_word, 'cmn')
            else:
                res += unpredictable        
    elif op == 10:
        res += t1_adc(offset, a_word)  
    elif op == 11:
        res += t1_sbc(offset, a_word) 
    elif op == 13:
        if rd != 15:
            res += t3_sub(offset, a_word)
        else:
            if s_bit == 1:   
                res += t2_cmp(offset, a_word, 'cmp.w')
            else:
                res += unpredictable
    elif op == 14:
        res += t2_rsb(offset, a_word)

    return res

#---------------------------------------------------------------------------
#-------------Data processing plain binary immediate A6-19------------------

def addw_12bit(offset, a_word):
    res = ""
    column = 3
    res += 'add'
    setflags_bit= get_field(a_word, 20, 20)
    if setflags_bit != 0:
        res += 's'
        column += 1
    res += 'w'
    column += 1
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    res +=  get_reg(rd) + ", " + get_reg(rn) + ", " 
    imm32 = ThumbExpandImm(a_word)
    res += "#{0:#x}".format(imm32)
    return res

def sub_12bit(offset, a_word):
    res = ""
    column = 3
    res += 'sub'
    setflags_bit= get_field(a_word, 20, 20)
    if setflags_bit != 0:
        res += 's'
        column += 1
    res += 'w'
    column += 1
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    res +=  get_reg(rd) + ", " + get_reg(rn) + ", " 
    imm32 = ThumbExpandImm(a_word)
    res += "#{0:#x}".format(imm32)
    return res
    

def t4_addw(a_word, offset): 
    res = ""
    column = 4
    res += 'addw'   
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    res +=  get_reg(rd) + ", " + get_reg(rn) + ", " 
    imm32 = ZeroExtend12(a_word)  # I can't see any difference from ThumbExpandImm
    res += "#{0:#x}".format(imm32)
    return res  

def t3_adr(offset, a_word):
    res = ""
    column = 5
    res += 'adr.w'   
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    res +=  get_reg(rd) + ", " 
    imm32 = ThumbExpandImm_Craw(a_word)
    imm32 += offset+4   # pc-relative
    res += "#{0:#x}".format(imm32)
    return res

def t2_subr(a_word, offset):
    # doc says adr to label before current instruction
    res = ""
    column = 5
    res += 'adr.w'   
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    res +=  get_reg(rd) + ", " 
    imm32 = ZeroExtend12(a_word)
    imm32 -= offset+4   # pc-relative  (but backwards)
    res += "#{0:#x}".format(imm32)
    return res
    

def t3_movw(offset, a_word):
    res = ""
    column = 4
    res += 'movw'
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    res +=  get_reg(rd) + ", "
    imm16  = ZeroExtend16(a_word)
    res += "#{0:#x}".format(imm16)
    return res

def t1_movt(offset, a_word):
    res = ""
    column = 4
    res += 'movt'
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    res +=  get_reg(rd) + ", "
    imm16  = ZeroExtend16(a_word)
    res += "#{0:#x}".format(imm16)
    return res 

def  t1_ssat(offset, a_word, opcode, signed):
    res = ""
    column = len(opcode)
    res += opcode
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    s_bit = get_field(a_word, 21, 21)
    imm = (get_field(a_word, 12, 14) << 2) | get_field(a_word, 6, 7)
    sat_imm = get_field(a_word, 0, 4)
    if signed:
        sat_imm += 1
    # I'm making a guess here that the doc is wrong
    res +=  get_reg(rd) + ", " + "#{0:d}".format(sat_imm) + get_reg(rn) 
    if (s_bit != 0) or (imm != 0):
        res += ", "
        shift_type = s_bit << 1
        if shift_type == 0:
            res += "lsl"
        else:
            res += "asr"
        res += "#{:d}".format(imm)
   
    return res
    
def  t1_ssat16(offset, a_word, opcode, signed):
    res = ""
    column = len(opcode)
    res += opcode
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    imm = (get_field(a_word, 12, 14) << 2) | get_field(a_word, 6, 7)
    sat_imm = get_field(a_word, 0, 3)
    if signed:
        sat_imm += 1
    # doc says imm always 0, do we use sat_imm? 
    res +=  get_reg(rd) + ", " + "#{0:d|".format(sat_imm) + get_reg(rn)
    return res 

def t1_bfic(offset, a_word, opcode):
    #opcode rd,rn,#lsb, #width  doc is inconsistent (says lsb for width)
    res = ""
    column = len(opcode)
    res += opcode
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    lsbit = (get_field(a_word, 12, 14) << 2) | get_field(a_word, 6, 7)
    msbit = get_field(a_word, 0, 3)
    res +=  get_reg(rd) + ", " + get_reg(rn) + "#{0:d}, #{1:d}".format(lsbit, msbit)
    return res     


def t1_usat(offset, a_word):
    return t1_ssat(offset, a_word, 'usat', signed = False)

def t1_usat16(offset, a_word):
    return t1_ssat16(offset, a_word, 'usat16', signed = False)

def t1_sbfx(offset, a_word, opcode, signed = True):
    res = ""
    column = len(opcode)
    res += opcode
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    lsbit = (get_field(a_word, 12, 14) << 2) | get_field(a_word, 6, 7)
    widthm1 = get_field(a_word, 0, 3) +1
    if signed:
        pass  # nothing in assembler 
    res +=  get_reg(rd) + ", " + get_reg(rn) +", " "#{0:d}, #{1:d}".format(
                                            lsbit, widthm1)
    return res     

#--------------------------------------------------------------------------

def dp_plain_binary_immediate(offset, a_word):
    res = ""
    op = get_field(a_word, 20, 24)
    rn = get_field(a_word, 16, 19)
    if (op == 0):
        if rn != 15:
            res += addw_12bit(offset, a_word)
        else:
            res += t3_adr(offset, a_word)
    elif op == 4:
        res += t3_movw(offset, a_word)
    elif op == 10:
        if rn != 15:
            res += sub_12bit(offset, a_word)
        else:
            res += t2_subr(a_word, offset) #doc says adr to label before current      
    elif op == 12:
        res += t1_movt(offset, a_word)
    elif (op == 16):
        res += t1_ssat(offset, a_word, 'ssat', signed = True)
    elif (op == 18):
        res += t1_ssat16(offset, a_word, 'ssat16', signed = True)
    elif op == 20:
        res += t1_sbfx(offset, a_word, 'sbfx', signed = True)
    elif op == 22:
        if rn != 15:
            res += t1_bfic(offset, a_word, 'bfi')
        else:
            res += t1_bfic(offset, a_word, 'bfc')
    elif op == 24:
        res += t1_ssat(offset, a_word, 'usat', signed = False)
    elif op == 26:
        res += t1_ssat16(offset, a_word, 'usat16', signed = False)
    elif op == 28:
        res += t1_sbfx(offset, a_word, 'ubfx', signed = False)    
    else:
        res += 'Unexpected 32 bit thumb instr'
    return res

#---------------------------------------------------------------------------
#-------------Data Processing shifted register A6-31------------------

def t2_shift_reg2(offset, a_word, opcode): #opcode.w rn,rm{,shift}
    res = ""
    column = 0
    res += opcode
    column = len(opcode)
    res += '.w'
    column += 2
    rn = get_field(a_word, 16, 19)
    imm3 = get_field(a_word, 12, 14)
    imm2 = get_field(a_word, 6, 7)
    type_bits = get_field(a_word, 4, 5)
    rm = get_field(a_word, 0, 3)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rn) + ", " + get_reg(rm) + ", "
    res += DisassImmShift(type_bits, (imm3 << 2) | imm2)
    return res 

def t2_shift_reg2s(offset, a_word, opcode):  #opcode{s}.w rn,rm{,shift}
    res = ""
    column = 0
    res += opcode
    column = len(opcode)
    s_bit = get_field(a_word, 20, 20)
    if s_bit: 
        res += 's'
        column += 1       
    res += '.w'
    column += 2
    rn = get_field(a_word, 16, 19)
    imm3 = get_field(a_word, 12, 14)
    imm2 = get_field(a_word, 6, 7)
    type_bits = get_field(a_word, 4, 5)
    rm = get_field(a_word, 0, 3)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rn) + ", " + get_reg(rm) + ", "
    res += DisassImmShift(type_bits, (imm3 << 2) | imm2)
    return res 

def t2_shift_reg2rdrms(offset, a_word, opcode): #opcode{s}.w rd,rm{,shift}
    res = ""
    column = 0
    res += opcode
    column = len(opcode)
    s_bit = get_field(a_word, 20, 20)
    if s_bit: 
        res += 's'
        column += 1       
    res += '.w'
    column += 2
    imm3 = get_field(a_word, 12, 14)
    rd = get_field(a_word, 8, 11)
    imm2 = get_field(a_word, 6, 7)
    type_bits = get_field(a_word, 4, 5)
    rm = get_field(a_word, 0, 3)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rd) + ", " + get_reg(rm) + ", "
    res += DisassImmShift(type_bits, (imm3 << 2) | imm2)
    return res 
    

def t3_shift_reg2(offset, a_word, opcode):   # is doc wrong? no mention of shift
    res = ""
    column = 0
    res += opcode
    column = len(opcode)
    s_bit = get_field(a_word, 20, 20)
    if s_bit: 
        res += 's'
        column += 1    
    res += '.w'
    column += 2
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rd = get_field(a_word, 8, 11)
    rm = get_field(a_word, 0, 3)
    res += get_reg(rd) + ", " + get_reg(rm)
    return res    

def t2_shift_reg3(offset, a_word, opcode): #opcode{s}.w rd,rn,rm{,shift}
    column = 0
    res = opcode
    column = len(opcode)
    s_bit = get_field(a_word, 20, 20)
    if s_bit: 
        res += 's'
        column += 1
    res += '.w'
    column += 2
    rn = get_field(a_word, 16, 19)
    rd = get_field(a_word, 8, 11)
    imm3 = get_field(a_word, 12, 14)
    imm2 = get_field(a_word, 6, 7)
    type_bits = get_field(a_word, 4, 5)
    rm = get_field(a_word, 0, 3)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rd) + ", " + get_reg(rn) + ", " + get_reg(rm) + ", "
    res += DisassImmShift(type_bits, (imm3 << 2) | imm2)
    return res


def t2_pkh_sr(offset, a_word):
    res = ""
    column = 0
    tb = get_field(a_word,4, 5)
    if tb == 0:
        opcode = 'pkhbt'
    elif tb == 2:
        opcode = 'pkhtb'
    # sign bit is 0, so OK
    return t2_shift_reg3(offset, a_word, opcode)


def dp_shifted_reg(offset, a_word):
    res = ""
    column = 0
    op = get_field(a_word, 21, 24)
    s_bit = get_field(a_word, 20, 20)
    rn = get_field(a_word, 16, 19)
    rd = get_field(a_word, 8, 11)
    if (op == 0):
        if rd != 15:
            res += t2_shift_reg3(offset, a_word, 'and')
        else:
            if s_bit == 1:
                res += t2_shift_reg2(offset, a_word, 'tst')
            else:
                res += unpredictable
    elif op == 1:
        res += t2_shift_reg3(offset, a_word, 'bic')
    elif op == 2:
        if rn != 15:
            res += t2_shift_reg3(offset, a_word, 'orr')
        else:
            res += t3_shift_reg2(offset, a_word, 'mov')
    elif op == 3:
        if rn != 15:
            res += t2_shift_reg3(offset, a_word, 'orn')
        else:
            res += t2_shift_reg2rdrms(offset, a_word, 'mvn')      
    elif op == 4:
        if rd != 15:
            res += t2_shift_reg3(offset, a_word, 'eor')
        else:
            if s_bit == 1:
                res += t2_shift_reg2(offset, a_word, 'teq')
            else:
                res += unpredictable
    elif (op == 6):
        res += t2_pkh_sr(offset, a_word)
    elif op == 8:
        if rd != 15:
            # supposedly rn == 13 (sp)  needs special casing (I don't see it)          
            res += t2_shift_reg3(offset, a_word, 'add')
        else:
            if s_bit == 1:
                res += t2_shift_reg2(offset, a_word, 'cmn')
            else:
                res += unpredictable        
    elif op == 10:
        res += t2_shift_reg3(offset, a_word, 'adc')  
    elif op == 11:
        res += t2_shift_reg3(offset, a_word, 'sbc')  
    elif op == 13:
        if rd != 15:
            # special case r13 (sp) ??
            res += t2_shift_reg3(offset, a_word, 'sub')
        else:
            if s_bit == 1:   
                res += t2_shift_reg2(offset, a_word, 'cmp')
            else:
                res += unpredictable
    elif op == 14:
        res += t2_shift_reg3(offset, a_word, 'rsb')

    return res

#---------------------------------------------------------------------------

def t32_msr(offset, a_word):
    res = 'msr'
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rn = get_field(a_word, 16, 19)
    mask = get_field(a_word, 10, 11)
    Sysm = get_field(a_word, 0, 7)
    
    if Sysm != 0:
        res += "{:#x}".format(Sysm)
    else:
        if (mask&2) == 2:
            res += 'apsr(31:27) = {:#x}'.format(Sysm)
    res +=  ', ' + get_reg(rn)
    return res

def t32_mrs(offset, a_word):
    res = 'mrs'
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN 
    rd = get_field(a_word, 8, 11)
    Sysm = get_field(a_word, 0, 7)
    res += get_reg(rd) + ', '
    if Sysm != 0:
        res += "{:#x}".format(Sysm)
    else:
        res += 'apsr(31:27) = {:#x}'.format(Sysm)
    return res
    
    

def t32_branch_cond(offset, a_word): # t3 encoding
    j1_bit = get_field(a_word, 13, 13)
    j2_bit = get_field(a_word, 11, 11) 
    s_bit =  get_field(a_word,  26, 26)
    imm11 =  get_field(a_word, 0, 10)        
    imm6 = get_field(a_word, 16, 21)
    
    imm32 = ((s_bit << 20) | (j1_bit << 19) | (j2_bit << 18) | 
             (imm6 << 12) | (imm11 << 1))
    if s_bit:
        imm32 = extend_sign(imm32, 20)
    res = 'b'
    cond_bits = get_field(a_word, 22, 25)
    if (cond_bits < 0xe):
        res += cond(cond_bits)        
    imm32 += offset+4   # pc-relative
    res += ".w"
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += "{:#x} ;{:s}".format(imm32, get_sym(imm32)) 
    return res

def t3_branch(offset, a_word):
    """Branches and miscellaneous control""" 
    res = ""
    column = 0
    op = get_field(a_word, 20, 26)
    op1 = get_field(a_word, 12, 14)
    op1_masked = get_field(a_word, 12, 14) & 0b101
    op2 = get_field(a_word, 8, 11)
    j1_bit = get_field(a_word, 13, 13)
    j2_bit = get_field(a_word, 11, 11)
    s_bit =  get_field(a_word,  26, 26)
    imm11 =  get_field(a_word, 0, 10)    

    if (op1_masked == 0):
        if (op & 0b0111000) == 0:
            res += t32_branch_cond(offset, a_word)
        elif op == 0b0111000:
            if (op2 & 3) == 0:
                res += t32_msr(offset, a_word)
            else:  # ?? system level?
                res += t32_msr(offset, a_word)
        elif op == 0b011101:
            res += t32_msr(offset, a_word)
        elif op == 0b0111010:
            res += "change processor state"
        elif op == 0b0111011:
            res += "Miscellaneous control"
        elif op == 0b0111100:
            # Bx Jazelle
            res += "BXJ"
            column = 3
            res += SPACES[column:ICOLUMN]; column = ICOLUMN 
            rm = get_field(a_word, 16, 19)
            res +=  get_reg(rm)   
        elif op == 0b0111101:
            res += "Exception return SUBS PC, LR etc"
        elif (op == 0b0111110) or (op == 0b0111111):
            res += t32_mrs(offset, a_word)
        elif op == 0b1111111:
            res += "SMC Secure Monitor call"
    elif (op1 == 2) & (op == 0x7f):
        res += undefined + " (FOR EVER)"
    elif (op1_masked) == 1:
        # branch
        if get_field(a_word, 12, 12) == 0:
            #T3. armv7-M manual is missing an explanation (7-R manual OK. A8-44)
            res += t32_branch_cond(offset, a_word)    
        else:
            #T4
            i1 = (~(j1_bit ^ s_bit)) &1
            i2 = (~(j2_bit ^ s_bit)) &1
            imm10 = get_field(a_word, 16, 25)
            imm32 = (s_bit<<24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (
                     imm11 << 1)
            if s_bit: 
                imm32 = extend_sign(imm32, 24)
            imm32 += offset+4   # pc-relative
            res += "b.w"
            column = 3
            res += SPACES[column:ICOLUMN]; column = ICOLUMN            
            res += "{:#x} ;{:s}".format(imm32, get_sym(imm32))
    elif (op1_masked) == 4:
        #res += "branch  with link and exchange"
        # not armv7-M
        i1 = (~(j1_bit ^ s_bit)) &1
        i2 = (~(j2_bit ^ s_bit)) &1
        imm10 = get_field(a_word, 16, 25)
        imm10L = imm11 >> 1
        imm32 = (s_bit << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) |  (
                 imm10L << 2)
        if s_bit: 
            imm32 = extend_sign(imm32, 24)
        imm32 += offset+4   # pc-relative
        res += "blx"
        column = 3
        res += SPACES[column:ICOLUMN]; column = ICOLUMN       
        res += "{:#x} ;{:s}".format(imm32, get_sym(imm32))  
    elif (op1_masked) == 5:
        #res += "branch with link"
        i1 = (~(j1_bit ^ s_bit)) & 1
        i2 = (~(j2_bit ^ s_bit)) & 1
        imm10 = get_field(a_word, 16, 25)
        imm32 = (s_bit << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (
                  imm11 << 1)
        if s_bit: 
            imm32 = extend_sign(imm32, 24)
        imm32 += offset+4   # pc-relative
        res += "bl"
        column = 2
        res += SPACES[column:ICOLUMN]; column = ICOLUMN        
        res += "{:#x} ;{:s}".format(imm32, get_sym(imm32))  
    
    return res

#-------------------------------------------------------------------------
def t32_lsm(offset, a_word, opcode):
    res = ""
    column = 0
    res += opcode
    column += len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    wback = get_field(a_word, 21, 21)
    r_list = get_field(a_word, 0, 15)
    res += get_reg(rn)
    column += 2
    if wback:
        res += '!'
    res += ', '
    res += reg_list(r_list)   
    return res
    
    
def t32_poppush(offset, a_word, opcode):
    res = ""
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    #rn = get_field(a_word, 16, 19)
    one_reg = get_field(a_word, 21, 21) == 0
    if one_reg:
        rt = get_field(a_word, 12, 15)
        r_list = 1 << rt
    else:
        r_list = get_field(a_word, 0, 15)
    #res += get_reg(rn) + ', '
    res += reg_list(r_list)   
    return res    
    

def t32_ls_multiple(offset, a_word):
    res = ""
    op = get_field(a_word, 23, 24)
    l_bit = get_field(a_word, 20, 20)
    w_rn = (get_field(a_word, 21, 21) << 4) | get_field(a_word, 16, 19)
    if op == 1:
        if l_bit == 0:
            res += t32_lsm(offset, a_word, 'stm.w')
        else:
            if w_rn != 29:
                res += t32_lsm(offset, a_word, 'ldm.w')
            else:
                res += t32_poppush(offset, a_word, 'pop.w')
    elif op == 2:
        if l_bit == 0:
            if w_rn != 29:
                res += t32_lsm(offset, a_word, 'stmdb')
            else:
                res += t32_poppush(offset, a_word, 'push.w')
                
        else:
            res += t32_lsm(offset, a_word, 'ldmdb')
        
    return res

def t32_strex(offset, a_word, opcode):
    res = ""
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    rt = get_field(a_word, 12, 15)
    rd = get_field(a_word, 8, 11)
    imm8 = get_field(a_word, 0, 7)
    res += get_reg(rd) + ', ' + get_reg(rt) + ', ' + get_reg(rn)
    if imm8 != 0:
        res += ",#{:d}".format(imm8*4)
    return res

def t32_ldrex(offset, a_word, opcode):
    res = ""
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    rt = get_field(a_word, 12, 15)
    imm8 = get_field(a_word, 0, 7)
    res += get_reg(rt) + ', [' + get_reg(rn)
    if imm8 != 0:
        res += ", #{:d}".format(imm8*4)
    res += ']'
    return res

def t32_strexb(offset, a_word, opcode):
    res = ""
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    rt = get_field(a_word, 12, 15)
    rd = get_field(a_word, 0, 3)
    res += get_reg(rd) + ', ' + get_reg(rt) + ', ' + get_reg(rn)
    return res

def t32_ldrexb(offset, a_word, opcode):
    res = ""
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    rt = get_field(a_word, 12, 15)
    res += get_reg(rt) + ', ' + get_reg(rn)
    return res

def t32_strd(offset, a_word, opcode):
    res = ""
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    rt = get_field(a_word, 12, 15)
    rt2 = get_field(a_word, 8, 11)
    imm8 = get_field(a_word, 0, 7)
    wback = get_field(a_word, 21, 21)
    upp = get_field(a_word, 23, 23)
    pre_index = get_field(a_word, 24, 24)
    res += get_reg(rt) + ', ' + get_reg(rt2) + ', [' + get_reg(rn)
    if imm8 != 0:
        if upp: 
            uppch = '+'
        else:
            uppch = '-'
        res += ", " + uppch + "#{:d}".format(imm8*4)
    res += ']'
    if wback:
        res += '!'
    if pre_index:
        res += '[pre-indexed]'
    else:
        res += '[post_indexed]'
    # TBD more to fix here
    return res

def t32_tbb(offset, a_word):
    res = ""
    rn = get_field(a_word, 16, 19)
    rm = get_field(a_word, 0, 3)
    borh = get_field(a_word, 4,4)
    if borh:
        res += 'tbh'
    else:
        res += 'tbb'
    column = 3
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(rn) + ', ' + get_reg(rm)
    return res    

def t32_ls_dual_excl_tb(offset, a_word):
    res = ""
    op1 = get_field(a_word, 23, 24)
    op2 = get_field(a_word, 20, 21)
    op3 = get_field(a_word, 4, 7)
    if op1 == 0:
        if op2 == 0:
            res += t32_strex(offset, a_word, 'strex')
        elif op2 == 1:
            res += t32_ldrex(offset, a_word, 'ldrex')
        elif (op2 == 2) or (((op1 & 2) == 2) and ((op2 & 1) == 0)):
            res += t32_strd(offset, a_word, 'strd')
        elif (op2 == 3) or (((op1 & 2) == 2) and ((op2 & 1) == 1)):
            res += t32_strd(offset, a_word, 'ldrd')
    elif op1 == 1:
        if op2 == 0:
            if op3 == 4:
                res += t32_strexb(offset, a_word, 'strexb')
            elif op3 == 5:
                res += t32_strexb(offset, a_word, 'strexh')
        elif op2 == 1:
            if op3 == 0:
                res += t32_tbb(offset, a_word)
            elif op3 == 1:
                res += t32_tbb(offset, a_word)
            elif op3 == 4:
                res += t32_ldrexb(offset, a_word, 'ldrexb')
            elif op3 == 5:
                res += t32_ldrexb(offset, a_word, 'ldrexh')
    return res
#--------------------------- Floating Point Instructions ---------------------

def get_fpreg(reg):
    return 's{:d}'.format(reg)

def get_dfpreg(reg):
    return 'd{:d}'.format(reg)

def fp_1_reg(a_word):
    sd = (get_field(a_word, 12, 15) <<1 ) | get_field(a_word, 22, 22)
    return get_fpreg(sd)

def fp_2_regs(a_word):
    sd = (get_field(a_word, 12, 15) <<1 ) | get_field(a_word, 22, 22)
    sm = (get_field(a_word,  0,  3) << 1) | get_field(a_word, 5, 5)
    return get_fpreg(sd) +', ' +get_fpreg(sm)


def fp_3_regs(a_word):
    sd = (get_field(a_word, 12, 15) <<1 ) | get_field(a_word, 22, 22)
    sn = (get_field(a_word, 16, 19) << 1) | get_field(a_word, 7, 7)
    sm = (get_field(a_word,  0,  3) << 1) | get_field(a_word, 5, 5)
    return get_fpreg(sd) +', ' +get_fpreg(sn) +', ' +get_fpreg(sm)

def t32_vml(offset, a_word):
    res = 'vml'
    if get_field(a_word, 6,6):
        res += 's'
    else:
        res += 'a'
    res += '.f32'
    column = 8
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += fp_3_regs(a_word)
    return res
    
def t32_vnml(offset, a_word):
    res = ''
    column = 0
    if get_field(a_word, 20, 21) == 2:
        res = 'vnmul.f32'
        column = 9
    else:
        res = 'vnml'
        if get_field(a_word, 6, 6) == 1:
            res += 'a'
        else:
            res += 's'
        res += '.f32'
        column = 9
    res += fp_3_regs(a_word)
    return res     
    

def t32_vmul(offset, a_word):
    res = 'vmul.f32'
    column = 8
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += fp_3_regs(a_word)
    return res    

def t32_vadd(offset, a_word, opcode):
    res = opcode
    column = len(opcode)
    res += '.f32'
    column += 4
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += fp_3_regs(a_word)
    return res

def vfp_expand_imm(imm8):
    imm = (imm8 & 0x3f) << 19
    if (imm8 & 0x40):
        imm |= 0x3f000000
    else:
        imm |= 0x40000000
    if imm8 & 0x80:
        imm |= 0x80000000
    return imm
    
    
def t32_vmov_imm(offset, a_word):
    res = 'vmov.f32'
    column = 8
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    sd = (get_field(a_word, 12, 15) <<1 ) | get_field(a_word, 22, 22)
    imm8 = vfp_expand_imm((get_field(a_word, 16, 19) << 4) | get_field(a_word, 0, 3))
    res += get_fpreg(sd) +', #{:#x}'.format(imm8) 
    res += ' ({:f})'.format(unchecked_conversion.convert_int_to_float(imm8))   
    return res

def t32_vmov(offset, a_word, opcode):
    res = opcode+'.f32'
    column = len(opcode) + 4
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += fp_2_regs(a_word)
    return res
    
def t32_vcvt(offset, a_word):
    res = 'vcvt'
    if get_field(a_word, 7, 7):
        res += 't'
    else:
        res += 'b'
    half_to_single =  not get_field(a_word, 16, 16)
    if half_to_single:
        res += '.f16.f32'
    else:
        res += '.f32.f16'
    column = 13
    res += ' '
    res += fp_2_regs(a_word)
    return res 

def t32_vcmp(offset, a_word):
    res = 'vcmp'
    column = 4
    if get_field(a_word, 7, 7):
        res += 'e'
        column += 1
    res += '.f32'
    column += 4
    res += ' '
    #res += SPACES[column:ICOLUMN]; column = ICOLUMN
    if get_field(a_word, 16, 16):
        res += fp_1_reg(a_word) + ', #0.0'
    else:
        res += fp_2_regs(a_word)
    return res     

def t32_vcvt_fi(offset, a_word):
    res = 'vcvt'
    column = 4
    to_int = get_field(a_word, 18, 18)
    
    signed = get_field(a_word, 7, 7)
    if to_int:
        roundit = get_field(a_word, 16, 18) == 1
    else:
        roundit = False
    if roundit:
        res += 'r'
        column += 1
    if signed:
        int_type = '.s32'
    else:
        int_type = '.u32'
    if to_int:
        res += '.f32'+int_type
    else:
        res += int_type + '.f32'  
    res += ' '+ fp_2_regs(a_word)
    return res
    
def t32_vcvt_ffx(offset, a_word):
    res = 'vcvt'
    column = 4
    to_fixed = get_field(a_word, 18, 18)
    unsigned = get_field(a_word, 16, 16)
    siz = get_field(a_word, 7, 7)
    imm5 = (get_field(a_word, 0, 3) << 1) | get_field(a_word, 5, 5)
    if siz:
        bit_size = 32
    else:
        bit_size = 16
    frac_bits = bit_size - imm5
    if frac_bits < 0:
        res += 'Error:fractional bits < 0'
        return res
    if to_fixed: # not an issue in disassembly
        round_val = True
    else:
        round_val = False
    if unsigned:
        int_type = '.u{:d}'.format(bit_size)
    else:
        int_type = '.s{:d}'.format(bit_size)
    if to_fixed:
        res += '.f32'+int_type
    else:
        res += int_type + '.f32'  
    res += ' '+ fp_2_regs(a_word) +', #{:d}'.format(frac_bits)
    return res

def t32_vmsr(offset, a_word):
    res = 'vmsr'
    column = 4
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += 'fpscr, '
    res += get_reg(get_field(a_word, 12, 15))
    return res

def t32_vmrs(offset, a_word):
    res = 'vmrs'
    column = 4
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(get_field(a_word, 12, 15)) + ', '
    res += 'fpscr'
    return res
    
def t32_fp_instr(offset, a_word):
    res = ""
    opc1 = get_field(a_word, 20, 23) & 0b1011
    opc2 = get_field(a_word, 16, 19)
    opc3 = get_field(a_word, 6, 7)
    if opc1 == 0:
        res += t32_vml(offset, a_word)
    elif opc1 == 1:
        res += t32_vnml(offset, a_word)
    elif opc1 == 2:
        if opc3&1 == 1:
            res += t32_vnml(offset, a_word)
        else:
            res += t32_vmul(offset, a_word)
    elif opc1 == 3:
        if opc3&1 == 1:
            opcode = 'vsub'
        else:
            opcode = 'vadd'
        res += t32_vadd(offset, a_word, opcode)
    elif opc1 == 8:
        res += t32_vadd(offset, a_word, 'vdiv')
    elif opc1 == 11:
        if opc3 == 0:
            res += t32_vmov_imm(offset, a_word)
        elif opc2 == 0:
            if opc3 == 1:
                res += t32_vmov(offset, a_word, 'vmov')
            elif opc3 == 3:
                res += t32_vmov(offset, a_word, 'vabs')
        elif opc2 == 1:
            if opc3 == 1:
                res += t32_vmov(offset, a_word, 'vneg')
            elif opc3 == 3:
                res += t32_vmov(offset, a_word, 'vsqrt')
        elif (opc2 & 0b0010) == 2:
            if (opc3 & 1) == 1:
                res += t32_vcvt(offset, a_word)
        elif (opc2 & 0b0100) == 4:
            if (opc3 & 1) == 1:
                res += t32_vcmp(offset, a_word)        
        elif (opc2 == 8): 
            if (opc3 & 1) == 1:
                res += t32_vcvt_fi(offset, a_word)
        elif((opc2 & 0b1010) == 0b1010):
            if (opc3 & 1) == 1:
                res += t32_vcvt_ffx(offset, a_word)
        elif((opc2 & 0b1100) == 0b1100):
            if (opc3 & 1) == 1:
                res += t32_vcvt_fi(offset, a_word)
        else:
            res += undefined
    else:
        res += undefined
    return res

def t32_fp_2reg_mov(offset, a_word):
    res = 'vmov'
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    to_arm_reg = get_field(a_word, 20, 20)
    rt = get_field(a_word, 12, 15)
    rt2 = get_field(a_word, 16, 19)
    dm = sm = (get_field(a_word,  0,  3) << 1) | get_field(a_word, 5, 5)
    if get_field(a_word, 8, 8):
        use_dbl = True
    else:
        use_dbl = False
    if use_dbl:
        fp_regs = get_dfpreg(dm)
    else:
        fp_regs = get_fpreg(sm) +', '  + get_fpreg(sm+1)
    core_regs = get_reg(rt) +', ' + get_reg(rt2)
    if to_arm_reg:
        res += core_regs +', ' + fp_regs
    else:
        res += fp_regs + ', ' + core_regs
    return res
 
def t32_vmov_reg_scalar(offset, a_word):
    res = 'vmov.32'
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rt = get_field(a_word, 12, 15)
    dreg = ((get_field(a_word, 7,7) << 5) | 
            (get_field(a_word, 16, 19) << 1) | 
             get_field(a_word, 21, 21))
    if get_field(a_word, 20, 20):
        res += get_reg(rt) + ', ' + get_dfpreg(dreg)
    else:
        res += get_dfpreg(dreg) + ', ' + get_reg(rt)
    return res

def t32_vmov_core_sp(offset, a_word):
    res = 'vmov'
    column = 4
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    to_arm_reg = get_field(a_word, 24, 24)
    rt = get_field(a_word, 12, 15)
    sn = (get_field(a_word, 16, 19) << 1) | get_field(a_word, 7, 7)
    if to_arm_reg:
        res += get_reg(rt) + ', ' + get_fpreg(sn)
    else:
        res += get_fpreg(sn) + ', ' + get_reg(rt)
    return res

def t32_vstr(offset, a_word):
    res = 'vstr'
    column = 4
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    double_reg = get_field(a_word, 8, 8)
    upp = get_field(a_word, 23, 23)
    sd = (get_field(a_word, 22, 22) << 4) | get_field(a_word, 12, 15)
    imm32 = get_field(a_word, 0, 7) << 2
    if double_reg:
        res += get_dfpreg(sd)
    else:
        res += get_fpreg(sd)
    res += ', [' + get_reg(rn)
    if imm32 != 0:
        res += '+'
        if not upp:
            res += '-'
        res += "{:d}".format(imm32)
    res += ']'
    return res
    
    
def t32_vldr(offset, a_word):
    res = 'vldr'
    column = 4
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    double_reg = get_field(a_word, 8, 8)
    upp = get_field(a_word, 23, 23)
    sd = (get_field(a_word, 22, 22) << 4) | get_field(a_word, 12, 15)
    imm32 = get_field(a_word, 0, 7) << 2
    if double_reg:
        res += get_dfpreg(sd)
    else:
        res += get_fpreg(sd)
    if rn != 15:
        res += ', [' + get_reg(rn)
        if imm32 != 0:
            res += '+'
            if not upp:
                res += '-'
            res += "{:d}".format(imm32)
        res += ']'
    else:
        dest = (offset/4)*4        
        res += '{:#x} ;{:s}'.format(dest, get_sym(dest))
    return res    
    
    
def t32_vpush(offset, a_word):
    return 'vpush'

def t32_vpop(offset, a_word):
        return 'vpop'
    
def t32_vstm(offset, a_word):
        return 'vstm'
    
def t32_vldm(offset, a_word):
        return 'vldm'

def t32_fp_load_store(offset, a_word):
    res = ""
    opcode = get_field(a_word, 20, 24)
    rn = get_field(a_word, 16, 19)
    # 64 bit transfer between ARM core and extension regs
    if opcode == 4 or opcode == 5:
        return t32_fp_2reg_mov(offset, a_word)
    if (opcode & 0b10011) == 0b10000:
        return t32_vstr(offset, a_word)
    elif (opcode & 0b10011) == 0b10001:
        return t32_vldr(offset, a_word)
    elif ((opcode & 0b11011) == 0b10010) and (rn == 13):
        return t32_vpush(offset, a_word)
    elif ((opcode & 0b11011) == 0b01011) and (rn == 13):
        return t32_vpop(offset, a_word) 
    elif (opcode & 1) == 0:
        return t32_vstm(offset, a_word)
    elif (opcode & 1) == 1:
        return t32_vldm(offset, a_word)
                      
    return undefined
    
def t32_32bit_xfer(offset, a_word):
    # 32 bit transfer between ARM core and extension regs
    lfield = get_field(a_word, 20, 20)
    cfield = get_field(a_word, 8, 8)
    afield = get_field(a_word, 21, 23)
    bfield = get_field(a_word, 5, 6)
    if lfield == 0:
        if (cfield == 1) and (bfield == 0):
            return t32_vmov_reg_scalar(offset, a_word) # scalar to core
        else:
            if afield == 0:
                return t32_vmov_core_sp(offset, a_word)
            elif afield == 7:
                return t32_vmsr(offset, a_word)  
    else:
        if (cfield == 1) and (bfield == 0):
            return t32_vmov_reg_scalar(offset, a_word) # core to scalar
        else:
            if afield == 0:
                return t32_vmov_core_sp(offset, a_word)
            elif afield == 7:
                return t32_vmrs(offset, a_word) 
    return ""
    
#----------------------------- End of FP instrs --------------

def t32_coproc1(offset, a_word):
    res = ""
    if get_field(a_word, 9, 11) == 5: # Floating point == coproc 10 and 11
        if get_field(a_word, 24, 25) == 2:
            if testBit(a_word, 4):
                return t32_32bit_xfer(offset, a_word)
            else:
                return t32_fp_instr(offset, a_word)
        if get_field(a_word, 25, 25) == 0:
            return t32_fp_load_store(offset, a_word)
    
    return res

def t32_str_reg(offset, a_word, opcode):
    res = ""
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19) 
    rm = get_field(a_word, 0, 3)
    imm2 = get_field(a_word, 4,5)
    rt = get_field(a_word, 12, 15)
    res += get_reg(rt) +', [' 
    res += get_reg(rn) +', ' +get_reg(rm)
    if imm2 != 0:
        res += ", lsl #{:d}".format(imm2)
    res += ']'
    return res

def t32_str_imm(offset, a_word, opcode):
    res = ""
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    rt = get_field(a_word, 12, 15)
    t3 = get_field(a_word, 23, 23)
    if t3:
        imm12 = get_field(a_word, 0, 12)
        res += get_reg(rt) +', [' 
        res += get_reg(rn)
        res += ", #{:#x}".format(imm12) 
        res += ']'
    else: 
        imm8= get_field(a_word, 0, 7)
        res += get_reg(rt) +', [' 
        res += get_reg(rn)
        wback = get_field(a_word, 8, 8)
        upp =    get_field(a_word, 9, 9)
        pre =    get_field(a_word, 10, 10)
        if imm8 != 0:
            if upp: res += ", "
            else:   res += ", -"
        
        res += "#{:#x}".format(imm8)
        res += ']'
        if wback: res += '!'
    return res

def t32_ssd(offset, a_word):
    res = ""
    op1 = get_field(a_word, 21, 23)
    op2_5 = get_field(a_word, 11, 11)
    if op1 == 0:
        if op2_5 == 0:
            res += t32_str_reg(offset, a_word, 'strb.w')
        else:
            res += t32_str_imm(offset, a_word, 'strb')
    elif op1 == 1:
        if op2_5 == 0:
            res += t32_str_reg(offset, a_word, 'strh.w')
        else:
            res += t32_str_imm(offset, a_word, 'strh')
    elif op1 == 2:
        if op2_5 == 0:
            res += t32_str_reg(offset, a_word, 'str.w')
        else:
            res += t32_str_imm(offset, a_word, 'str')
    elif op1 == 4:
        res += t32_str_imm(offset, a_word, 'strb.w')
    elif op1 == 5:
        res += t32_str_imm(offset, a_word, 'strh.w')
    elif op1 == 6:
        res += t32_str_imm(offset, a_word, 'str.w')
        
    return res


def t32_ldr_reg_lit(offset, a_word, opcode, pld=False):
    res = ""
    res += opcode
    column =len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    upp = get_field(a_word, 23, 23)
    rt = get_field(a_word, 12, 15)
    imm12 = get_field(a_word, 0, 11)
    if  not pld:
        res += get_reg(rt) + ', ['
    dest = offset + 4
    if upp: 
        dest += imm12
    else: 
        dest -= imm12    
    res += "#{:#x}] ;{:s}".format(dest, get_sym(dest))
    return res

def t32_ldr_reg(offset, a_word, opcode, pld = False):
    res = ""
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    
    rm = get_field(a_word, 0, 3)
    imm2 = get_field(a_word, 4,5)
    if not pld:
        rt = get_field(a_word, 12, 15)
        res += get_reg(rt) +', ' 
    res += get_reg(rn) +', ' +get_reg(rm)
    if imm2 != 0:
        res += ", lsl #{:d}".format(imm2)
    
    return res
    
def t32_ldrt(offset, a_word, opcode):
    res = ""
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    rt = get_field(a_word, 12, 15)
    imm8= get_field(a_word, 0, 7)
    res += get_reg(rt) +', [' +get_reg(rn)
    if imm8 != 0:
        res += ", #{:#x}".format(imm8)
    res += ']'
    return res

def t32_ldr_imm(offset, a_word, opcode, pld = False):
    res = ""
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    if not pld:
        rt = get_field(a_word, 12, 15)
    t3 = get_field(a_word, 23, 23)
    if t3: # or t2 for ldrh or t1 for ldrsh
        imm12 = get_field(a_word, 0, 12)
        if not pld: res += get_reg(rt) +', [' 
        res += get_reg(rn)
        if imm12 != 0:
            res += ", #{:#x}".format(imm12)
        res += ']'   
    else:  # t4  or t3 for ldrh  or t2 for ldrsh  
        imm8= get_field(a_word, 0, 7)
        if not pld: res += get_reg(rt) +', [' 
        res += get_reg(rn)
        wback = get_field(a_word, 8, 8)
        upp =    get_field(a_word, 9, 9)
        pre =    get_field(a_word, 10, 10)
        if imm8 != 0:
            if upp: res += ", "
            else:   res += ", -"
            res += "#{:#x}".format(imm8)
            res += ']'
            if (not pld) and wback: res += '!'
    return res


def t32_pld_imm_lit(offset, a_word, opcode):
    res = ""
    res += opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rn = get_field(a_word, 16, 19)
    upp =    get_field(a_word, 23,23)
    if rn == 15:
        dest = offset + 4
        imm12 = get_field(a_word, 0, 11)
        if upp: 
            dest += imm12
            res += ", "
        else:
            dest -= imm12
            res += ", -"
       
        res += ", #{:#x} ;{:s}".format(imm12, get_sym(dest))
    else: 
        res == get_reg(rn)
        if upp:
            imm12 = get_field(a_word, 0, 11)
            res += ", #{:#x} ;{:s}".format(imm12, get_sym(imm12))
        else:  
            imm8= get_field(a_word, 0, 7)
            res += ", #{:#x} ;{:s}".format(imm8, get_sym(imm8))
    return res    
    
    

def t32_lb(offset, a_word):
    res = ""
    op1 = get_field(a_word, 23, 24)
    op2 = get_field(a_word,  6, 11)
    rn =  get_field(a_word, 16, 19)
    rt =  get_field(a_word, 12, 15)
    if rt == 15:  # preload data
        if rn == 15:
            if op1 < 2:
                res += t32_ldr_reg_lit(offset, a_word, 'pld', pld=True)
            else:
                res += t32_pld_imm_lit(offset, a_word, 'pli')
        else:
            if op1 == 0:
                if op2 == 0:
                    res += t32_ldr_reg(offset, a_word, 'pld', pld = True)
                elif ((op2 & 0b110000) == 0b110000):
                    res += t32_ldr_imm(offset, a_word, 'pld', pld = True)
                else:
                    res += unpredictable
            elif op1 == 1:
                res += t32_ldr_imm(offset, a_word, 'pld', pld = True)
            elif op1 == 2:
                if op2 == 0:
                    res += t32_pld_imm_lit(offset, a_word, 'pli')
                elif ((op2 & 0b110000) == 0b110000):
                    res += t32_pld_imm_lit(offset, a_word, 'pli')
                else:
                    res += unpredictable

            elif op2 == 3:
                res += t32_pld_imm_lit(offset, a_word, 'pli')
    else:  #rt != 15
        if rn == 15:
            if op1 < 2:
                res += t32_ldr_reg_lit(offset, a_word, 'ldrb')
            else:
                res += t32_ldr_reg_lit(offset, a_word, 'ldrsb')
        else:        
            if (op1 == 0): 
                if (op2 == 0):
                    res += t32_ldr_reg(offset, a_word, 'ldrb.w')
                elif ((op2&0b100100) == 0b100100) or ((op2&0b110000) == 0b110000):
                    res += t32_ldr_imm(offset, a_word, 'ldrb')
                elif ((op2&0b111000) == 0b111000):
                    res += t32_ldrt(offset, a_word, 'ldrbt')
            elif (op1 == 1):
                res += t32_ldr_imm(offset, a_word, 'ldrb')
            elif (op1 == 2):
                if (op2 == 0):
                    res += t32_ldr_reg(offset, a_word, 'ldrsb.w')
                elif ((op2&0b100100) == 0b100100) or ((op2&0b110000) == 0b110000):
                    res += t32_ldr_imm(offset, a_word, 'ldrsb') 
                elif ((op2&0b111000) == 0b111000):
                    res += t32_ldrt(offset, a_word, 'ldrsbt')
            elif (op1 == 3):
                res += t32_ldr_imm(offset, a_word, 'ldrsb')
    return res



def t32_lh(offset, a_word):
    res = ""
    op1 = get_field(a_word, 23, 24)
    op2 = get_field(a_word,  6, 11)
    rn =  get_field(a_word, 16, 19)
    rt =  get_field(a_word, 12, 15)
    if rn == 15:
        if rt != 15:
            if op1 < 2:
                res += t32_ldr_reg_lit(offset, a_word, 'ldrh')
            else:
                res += t32_ldr_reg_lit(offset, a_word, 'ldrsh')
        else:
            res += unpredictable
    else:  #rn != 15
        if rt != 15:
            if (op1 == 0): 
                if (op2 == 0):
                    res += t32_ldr_reg(offset, a_word, 'ldrh.w')
                elif ((op1&0b100100) == 0b100100) or ((op2&0b110000) == 0b110000):
                    res += t32_ldr_imm(offset, a_word, 'ldrh')
                elif ((op2&0b111000) == 0b111000):
                    res += t32_ldrt(offset, a_word, 'ldrht')
            elif (op1 == 1):
                res += t32_ldr_imm(offset, a_word, 'ldrh')
            elif (op1 == 2):
                if (op2 == 0):
                    res += t32_ldr_reg(offset, a_word, 'ldrsh.w')
                elif ((op1&0b100100) == 0b100100) or ((op2&0b110000) == 0b110000):
                    res += t32_ldr_imm(offset, a_word, 'ldrsh') 
                elif ((op2&0b111000) == 0b111000):
                    res += t32_ldrt(offset, a_word, 'ldrsht')
            elif (op1 == 3):
                res += t32_ldr_imm(offset, a_word, 'ldrsh')
        else: # rt == 15
            if op1 == 1:
                res += 'nop'
            elif (op2 == 0) or ((op2 & 0b110000) == 0b110000):
                res += 'nop'
            else:
                res += unpredictable
    return res


def t32_lw(offset, a_word):
    res = ""
    op1 = get_field(a_word, 23, 24)
    op2 = get_field(a_word, 6, 11)
    rn =  get_field(a_word, 16, 19)
    if rn == 15:
        res += t32_ldr_reg_lit(offset, a_word, 'ldr.w')
    else:
        if op1 == 0:
            if op2 == 0:
                res += t32_ldr_reg(offset, a_word, 'ldr.w')
            elif ((op2 & 0b11100) == 0b111000):
                res += t32_ldrt(offset, a_word, 'ldrt')
            else:  # actually only 0b1xx1xx and 0b1100xx
                res += t32_ldr_imm(offset, a_word, 'ldr')
        elif op1 == 1:
            res += t32_ldr_imm(offset, a_word, 'ldr.w')
    return res

def t32_shift_reg(offset, a_word, opcode):
    res = opcode
    if testBit(a_word, 20):
        res += 's'
    res += '.w'
    column = len(res)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    rm = get_field(a_word, 0, 3)
    res += get_reg(rd) + ', ' + get_reg(rn) + ', ' + get_reg(rm)
    return res
 
def t32_extend_add(offset, a_word, opcode):
    res = opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    res += get_reg(rd) + ', '
    if rn != 15:
        res += get_reg(rn) + ', '
    rm = get_field(a_word, 0, 4)
    res += get_reg(rm) 
    rotate = get_field(a_word, 4, 5)
    if rotate != 0:
        rotate <<= 3
        res += ', ror #{:d}'.format(rotate)
    return res
        

def t32_dpr(offset, a_word):
    res = ""
    op1 = get_field(a_word, 20, 24)
    op2 = get_field(a_word, 4, 7)
    rn = get_field(a_word, 16, 19)
    if (op1 & 8) == 0:
        if op2 == 0:
            if op1 <= 1:
                opcode = 'lsl'
            elif op1 <= 3:
                opcode = 'lsr'
            elif op1 <= 5:
                opcode = 'asr'
            elif op1 <= 7:
                opcode = 'ror'
            res += t32_shift_reg(offset, a_word, opcode)
        else:
            if (op1 & 1) == 0:
                opcode = 's'
            else:
                opcode = 'u'
            opcode += 'xt'
            if rn != 15:
                opcode += 'a'
            if op1 <= 1:
                opcode += 'h'
            elif op1 <= 3:
                opcode += 'b16'
            elif op1 <= 5:
                opcode += 'b'
            else:
                opcode += '? unexpected '
            res += t32_extend_add(offset, a_word, opcode)
        
    else:
        if (op2 & 0xc) == 0:
            pass # parallel add and subtract
        elif (op2 & 0xc) == 4:
            pass #unsigned parallel add and subtract
        elif (op2 & 0xc) == 8:   # misc
            op11 = op1 & 3
            op21 = op2 & 3
            if op11 == 0: # qadd, qsub
                if op21 == 0:
                    opcode = 'qadd'
                elif op21 == 1:
                    opcode = 'qdadd'
                elif op21 == 2:
                    opcode = 'qsub'
                elif op21 == 3:
                    opcode = 'qdsub'
            elif op11 == 1: # rev
                if op21 == 0: 
                    opcode = 'rev.w'
                elif op21 == 1: 
                    opcode = 'rev16.w'
                elif op21 == 2: 
                    opcode = 'rbit'
                elif op21 == 3:
                    opcode = 'revsh.w'
            elif op11 == 2: 
                opcode = 'sel'
            elif op11 == 3:
                opcode = 'clz'
            res += opcode
            column = len(opcode)
            res += SPACES[column:ICOLUMN]; column = ICOLUMN
            rd = get_field(a_word, 8, 11)
            rn = get_field(a_word, 16, 19) # should be same as rm for clz and rev
            rm = get_field(a_word, 0, 3)
            res += get_reg(rd) + ', ' 
            if opcode != 'clz':
                res += get_reg(rn) + ', '
            res +=  get_reg(rm)                 
    return res

def t32_mul(offset, a_word, opcode):
    res = opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    rm = get_field(a_word, 0, 3)
    res += get_reg(rd) + ', ' + get_reg(rn) + ', ' + get_reg(rm)
    return res

def t32_mla(offset, a_word, opcode):
    res = opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rd = get_field(a_word, 8, 11)
    rn = get_field(a_word, 16, 19)
    rm = get_field(a_word, 0, 3)
    ra = get_field(a_word, 12, 15)
    res += (get_reg(rd) + ', ' + get_reg(rn) + ', ' + 
            get_reg(rm) + ', ' +get_reg(ra))  
    return res

tb = ['bb', 'bt', 'tb', 'tt']

def t32_mult(offset, a_word):
    res = ""
    op1 = get_field(a_word, 20, 22)
    op2 = get_field(a_word, 4, 5)
    ra = get_field(a_word, 12, 15)
    if op1 == 0:
        if op2 == 1:
            res += t32_mla(offset, a_word, 'mls')
        else: 
            if ra != 15:
                res += t32_mla(offset, a_word, 'mla')
            else:
                res += t32_mul(offset, a_word, 'mul')        
    elif op1 == 1:
        suff = tb[get_field(a_word, 4, 5)]
        if ra != 15:
            res += t32_mla(offset, a_word, 'smla'+suff)
        else:
            res += t32_mul(offset, a_word, 'smul'+suff)
    elif op1 == 2:
        suff = ''
        if get_field(a_word, 4, 4):
            suff = 'X'
        if ra != 15:
            res += t32_mla(offset, a_word, 'smlad'+suff)
        else:
            res += t32_mul(offset, a_word, 'smuad'+suff)
    elif op1 == 3:
        if get_field(a_word, 4, 4):
            suff = 'T'
        else:
            suff = 'B'
        if ra != 15:
            res += t32_mla(offset, a_word, 'smlaw'+suff)
        else:
            res += t32_mul(offset, a_word, 'smulw'+suff)
    elif op1 == 4:
        if get_field(a_word, 4, 4):
            suff = 'X'
        else:
            suff = ''
        if ra != 15:
            res += t32_mla(offset, a_word, 'smlsd'+suff)
        else:
            res += t32_mul(offset, a_word, 'smusd'+suff)
    elif op1 == 5:
        if get_field(a_word, 4, 4):
            suff = 'R'
        else:
            suff = ''
        if ra != 15:
            res += t32_mla(offset, a_word, 'smmla'+suff)
        else:
            res += t32_mul(offset, a_word, 'smmul'+suff)
    elif op1 == 6:
        if get_field(a_word, 4, 4):
            suff = 'R'
        else:
            suff = ''
        res += t32_mla(offset, a_word, 'smmls'+suff)

    elif op1 == 7:
        if ra != 15:
            res += t32_mla(offset, a_word, 'usada8')
        else:
            res += t32_mul(offset, a_word, 'usad8')
    else:
        res = undefined    
    return res

def t32_mull(offset, a_word, opcode):
    res = opcode
    column = len(opcode)
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    rdhi = get_field(a_word, 8, 11)
    rdlo = get_field(a_word, 12, 15)
    rn = get_field(a_word, 16, 19)
    rm = get_field(a_word, 0, 3)
    res += get_reg(rdlo) +', '+get_reg(rdhi) +', ' +get_reg(rn) +', ' +get_reg(rm)
    return res

def t32_lmult_div(offset, a_word):
    res = ""
    op1 = get_field(a_word, 20, 22)
    op2 = get_field(a_word, 4, 7)
    if op1 == 0:
        res += t32_mull(offset, a_word, 'smull')       
    elif op1 == 1:
        res += t32_mul(offset, a_word, 'sdiv')
    elif op1 == 2:
        res += t32_mull(offset, a_word, 'umull')      
    elif op1 == 3:
        res += t32_mul(offset, a_word, 'udiv')
    elif op1 == 4:
        if op2 == 0:
            res += t32_mull(offset, a_word, 'smlal')
        elif (op2&0b1100) == 0b1000:
            suff = tb[get_field(a_word, 4, 5)]
            res += t32_mull(offset, a_word, 'smlal'+suff)
        elif (op2&0b1110) == 0b1100:
            if get_field(a_word, 4, 4):
                suff = 'X'
            else:
                suff = ''
            res += t32_mull(offset, a_word, 'smlald'+suff)       
    elif op1 == 5:
        if get_field(a_word, 4, 4):
            suff = 'X'
        else:
            suff = ''
        res += t32_mull(offset, a_word, 'smlsld'+suff)
    elif op1 == 6:
        if op2 == 0:
            res += t32_mull(offset, a_word, 'umlal')
        elif op2 == 6:
            res += t32_mull(offset, a_word, 'umaal')
    else:
        res = undefined
            
    return res

def t32_coproc2(offset, a_word):
    op1 = get_field(a_word, 20, 25)
    op = testBit(a_word, 4)
    res = "Data ? "
    if op1 == 4:
        res += 'mcrr  NYI'
    elif op1 == 5:
        res += 'mrrc nYI'
    elif (op1 & 0b100000) == 0:
        if (op1 & 1) == 0:
            res += 'stc NYI'
        else:
            res += 'ldc NYI'      
    else:
        if op == 0:
            res += 'cdp NYI'
        elif (op1 & 1) == 0:
            res += 'mcr NYI'
        else:
            res += 'mrc NYI'
    return res


#--------------------------Thumb 32 instructions-------------------------

def thumb32(offset, a_word):
    res = ""
    column = 0
    op1 = get_field(a_word, 27, 28)
    op2 = get_field(a_word, 20, 26)
    op = get_field(a_word, 15, 15)
    if op1 == 1:
        if (op2 & 0b1100100) == 0:
            res += t32_ls_multiple(offset, a_word)
        elif (op2 & 0b1100100) == 0b100:
            res += t32_ls_dual_excl_tb(offset, a_word)
        elif (op2 & 0b1100000) == 0b0100000:
            res += dp_shifted_reg(offset, a_word)
        elif (op2 & 0b1000000) != 0:
            res += t32_coproc1(offset, a_word)
    elif op1 == 2:
        if  op == 0:
            if (op2 & 0b100000) == 0:
                res += dp_modified_immediate(offset, a_word)
            else:
                res += dp_plain_binary_immediate(offset, a_word)
                
        else: 
            res += t3_branch(offset, a_word)

    elif op1 == 3:
        if (op2 &0b1110001) == 0:
            res += t32_ssd(offset, a_word)
        elif (op2 &0b1110001) ==0b0010000:
            res += 'Data? or NYI' 
        elif (op2 & 0b1100111) == 1:
            res += t32_lb(offset, a_word)
        elif (op2 & 0b1100111) == 3:
            res += t32_lh(offset, a_word)       
        elif (op2 & 0b1100111) == 5:
            res += t32_lw(offset, a_word)          
        elif (op2 & 0b1100111) == 7:
            res += undefined  
        elif (op2 & 0b1110000) == 0b0100000:
            res += t32_dpr(offset, a_word)
        elif (op2 & 0b1111000) == 0b0110000:
            res += t32_mult(offset, a_word)
        elif (op2 & 0b1111000) == 0b0111000:
            res += t32_lmult_div(offset, a_word)
        elif (op2 & 0b1000000) != 0:
            res += t32_coproc2(offset, a_word)
    return res
    

def disass_thumb(offset, word):
    res = ""
    # there's been a little design disaster here; double reversal
    #h_word=int.from_bytes(a_word[0:2], 'little')
    #lo_word=int.from_bytes(a_word[2:4], 'little')
    #word= (h_word << 16 ) | lo_word  #int.from_bytes(a_word[0:4], 'little')
    cond_code = 0  # some work to do here
  
    h_word = word & 0xffff
    
    if is_thumb32(word):
        # TBD find out why this is needed
        rev_word = (word << 16) | (word >> 16)        
        res += thumb32(offset, rev_word)   #32-bit Thumb
        return res, 4

    if get_field(h_word, 13, 15) == 0: 
        res+= thumb_1(offset, h_word, cond_code)
    elif get_field(h_word, 11, 15) == 3:
        res+= thumb_2(offset, h_word, cond_code)
    elif get_field(h_word, 13, 15) == 1:
        res+= thumb_3(offset, h_word, cond_code)
    elif get_field(h_word, 10, 15) == 16:
        res+= thumb_4(offset, h_word, cond_code)
    elif get_field(h_word, 10, 15) == 17:
        res+= thumb_5(offset, h_word, cond_code)
    elif get_field(h_word, 11, 15) == 9:
        res+= thumb_6(offset, h_word, cond_code)
    elif get_field(h_word, 12, 15) == 5:
        if testBit(h_word, 9):
            res+= thumb_8(offset, h_word, cond_code)
        else:
            res+= thumb_7(offset, h_word, cond_code)
    elif get_field(h_word, 13, 15) == 3:
        res += thumb_9(offset, h_word, cond_code)
    elif get_field(h_word, 12, 15) == 8:
        res += thumb_10(offset, h_word, cond_code)
    elif get_field(h_word, 12, 15) == 9:
        res += thumb_11(offset, h_word, cond_code)
    elif get_field(h_word, 12, 15) == 10:
        res += thumb_12(offset, h_word, cond_code)
    elif get_field(h_word, 12, 15) == 0xb:
        res += thumb16_misc(offset, h_word, cond_code)         
    elif get_field(h_word, 12, 15) == 0xc:
        res += thumb_15(offset, h_word, cond_code)
    elif get_field(h_word, 12, 15) == 0xd:
        res += thumb16_cb_svc(offset, h_word, cond_code)
    elif get_field(h_word, 11, 15) == 28:
        res += thumb16_branch(offset, h_word, cond_code)  # unconditional branch
    elif get_field(h_word, 11, 15) == 30:
        res += thumb_19a(offset, h_word, cond_code)  # I think these are thumb32
    elif get_field(h_word, 11, 15) == 31 or get_field(h_word, 11, 15) == 29:
        res += thumb_19b(offset, h_word, cond_code)  # I think these are thumb32
        
    return res,2


#---------------------- Unit test support ----------------------------

def cmp(expected, code):
    hi_word=code&0xffff
    lo_word=code >> 16
    rev_code = (hi_word << 16) | lo_word

    res = ' '.join(disass_thumb(0, rev_code)[0].split())
    if res == '':
        print('no answer')
    else:
        if res == expected:
            print( "PASS : "+res)
        else:
            print("FAIL    : "+res)
            print("Expected: "+expected)        
     
    # TBD diff the fields or the strings and just output failures

if __name__ == '__main__':
    """ If you run this as a main program some unit testing is done. """
    print("*** dis_thumb.py module ***")
    # reversed the halfwords because of problem in disass_thumb
    cmp('and.w r1, r0, #0xf0000000',0xf0004170)
    cmp('cmp.w r1, #0xf0000000',    0xf1b14f70)
    cmp('mov.w r3, #0xf0',          0xf04f03f0)
    cmp('cmp.w r1, #0xffffffff',    0xf1b13fff)
    cmp('nop',                      0xbf00bf00)  
    cmp('itt cs',                   0xbf240000)
    cmp('ittee eq',                 0xbf070000)
    cmp('ittee cc',                 0xbf390000)
    cmp('ite pl',                   0xbf540000)
    cmp('str.w r2, [r0, #0x518]',   0xf8c02518)
    cmp('vstr s0, [sp]',            0xed8d0a00)
    cmp('beq.w 0x120 ;',            0xf000808e)
    cmp('ldmia r2!, {r2,r3}',       0xca0c0000)
    cmp('vmov s1, r0',              0xee000a90)  # disagrees with TI disassembly
    cmp('vmov r2, r3, d0',          0xEC532B10)
    cmp('asr.w r5, r1, r0',         0xfa41f500)
    cmp('rev.w r7, r8, r8',         0xfa98f788)
    cmp('pop {r2,r3,r4,r5,r6,pc}',  0xbd7c0000)
    cmp('push {r2,r3,r4,r5,r6,lr}', 0xb57c0000)
    cmp('sxth r1, r1',              0xb2090000)
    cmp('uxth r2, r2',              0xb2920000)
    cmp('ubfx r2, r0, #16, #5',     0xf3c04204)
    cmp('lsl r4, r0, #19',          0x04c40000)
    cmp('lsr r3, r3, #31',          0x0fdb0000)
    cmp('asr r0, r0',               0x41000000)
    cmp('ror r4, r4',               0x41e40000)
    cmp('clz r1, r1',               0xFAB1F181)  
    cmp('mvn r1, r1',               0x43C90000)   
    cmp('blx r6',                   0x47B00000)     
    cmp('cbnz r0, #0x6 ;',          0xb9080000)
    cmp('cbz r3, #0xa ;',           0xb11b0000)
    cmp('bmi.n 0x24 ;',             0xd4100000)
    cmp('ble.n -0x1c ;',            0xddf00000)
    cmp('bne.n 0x4 ;',              0xd1000000)

        
    cmp('ldrsh r2, [r4, #0x8]',     0xF9B42008) 
    cmp('rsb.w r1, r11, #0x8',      0xF1CB0108)
    cmp('pop.w {r4,r5,r6,r7,r8,r9,r10,r11,pc}', 0xE8BD8FF0)
    cmp('ldmia.w r5, {r0, r1}',     0xE8950003)
    cmp('ldmia.w r4, {r2,r3}',      0xE894000C)   
    cmp('ldmia r2!, {r2,r3}',       0xCA0C0000)
    cmp('push.w {r4,r5,r6,r7,r8,r9,r10,r11,lr}', 0xE92D4FF0)

    cmp('tst r0, #0x70000000',      0xf0104fe0)
    cmp('ldrb.w r6, [r0], #0x1!',   0xf8106b01)
    cmp('ldr.w r0, [r6, #-0x60]',   0xf8560c60)   
    cmp('VLD4.8 {D3[], D5[], D7[], D9[]}, [R3], R2', 0xf9833f22) # armv7-A/R
    cmp('mrs.W r4, APSR',           0xf3ef8400)
    cmp('msr.W SPSR_f, R4',         0xf3848800)
    cmp('bic.w r1, r1, #0xfe000000',0xf021417e) #bic r1, r1, #0x7e007e
    cmp('orr.w r0, r1, #0x2000000', 0xf0417000) #orr r0, r1, #0x0    


    
         
    
    