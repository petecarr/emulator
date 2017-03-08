""" disass(offset, word) """
# Path hack for access to utilities and siblings.
import sys, os
sys.path.insert(0, os.path.abspath('..'))

from utilities import  bit_fields, my_hex, check_for_diffs
from utilities.bit_fields import *
from utilities.my_hex import *
from utilities.check_for_diffs import *

from arm.armcpu import cond
from arm.armcpu import SPACES, ICOLUMN
from arm.armcpu import get_reg, get_fpreg, get_dfpreg, reg_list, get_sym
from arm.armcpu import dp_opcodes, das_strings

from arm.dis_thumb import disass_thumb



#----------------------------------------------------------------------------
""" Disassemble a word containing an ARMv7-A/R (arm) instruction.
    Output format mostly resembles  arm-none-eabi objdump output.
"""
#----------------------------------------------------------------------------


def get_imm(pos, value):
    """ Interpret the 12 bit offset - 4 bits for rotation of the 8 bits value"""
    if pos == 0: 
        return "#{0:d} (#{1:#x})".format(value, value)
    else:
        val = (value >> (pos*2)) | (value << (32-pos*2))
        return "#{0:d} (#{1:#x})".format(val, val)

   
def get_dest(offset, value):
    """ Interpret the destination address of a branch instruction."""
    val = value
    if testBit(val, 23):
        val = (val - 0x1000000)
    dest = offset+(val+2)*4
    return "{0:#x} ;{1:s}".format(dest, get_sym(dest))

def get_shift_type(value):
    """ Return the name of a shift code. """
    val = get_field(value,5,6)
    if   val == 0: return "lsl" 
    elif val == 1: return "lsr"
    elif val == 2: return "asr"
    elif val == 3: return "ror"
    
def data_processing(offset, word, cond_code):
    """ Disassemble the fields of a data processing instruction. """
    res = ""
    column = 0
    opcode = dp_opcodes[get_field(word, 21, 24)] 
    column+=3
    res+=opcode+cond(cond_code)
    if cond_code != 14: column +=2

    if testBit(word, 20): 
        if (opcode != "cmn") and (opcode != 
                      "cmp") and (opcode != 
                      "tst") and (opcode !=  
                      "teq"):        
            res+= "s"
            column +=1
            
    res += SPACES[column:ICOLUMN]; column = ICOLUMN

    # RD, no destination for test and compares
    if (opcode != "cmn") and (opcode != 
                  "cmp") and (opcode != 
                  "tst") and (opcode !=  
                  "teq"):
        res+=get_reg(get_field(word, 12, 15))+","
        column += 3  # not accurate but not ICOLUMN
    # <lhs>  no lhs for move
    if (opcode != "mov") and (opcode != "mvn"):
        if column > ICOLUMN: res+=" "
        res+=get_reg(get_field(word, 16, 19))+","
    # <rhs>
    if testBit(word, 25):
        res+= " " +get_imm(get_field(word,8,11), get_field(word, 0,7))
    else:
        # rm
        res+=" " +get_reg(get_field(word,0,3))
        if testBit(word, 4):  # reg shift
            res +=" "+get_shift_type(word) +" by "
            res +=    get_reg(get_field(word, 8, 11))
        else:                 # immediate shift
            shift_count = get_field(word, 7, 11)
            if get_shift_type(word) == "lsl":
                if shift_count != 0:
                    res+= ", lsl" + " #{:d}".format(shift_count)
            else:
                res+= ", " + get_shift_type(word)
                if shift_count == 0:
                    res+=" #32"
                else:
                    res+= " #{:d}".format(shift_count)
        
    return res

def count_leading_zeros(word, cond_code):
    """ clz instruction. """
    res = "clz"
    column = 3
    res+=cond(cond_code)
    if cond_code != 14: column +=2
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    # rd  (can't be r15)
    res+=get_reg(get_field(word, 12, 15))+", "
    # rm - rd gets # of leading zeros in rm  (not r15)
    res+=get_reg(get_field(word, 0, 3))
    return res
    
def swp(word, cond_code):
    """ swp instruction. Swap 2 values with no interruption. """
    res = "swp"
    column = 3
    if cond_code != 14: column+=2
    res+=cond(cond_code) 
    if testBit(word, 22): 
        res += 'b' 
        column += 1
    res += SPACES[column:ICOLUMN]
    # rd, rm, [rn] ; rd = [rn], [rn] = rm
    res += get_reg(get_field(word, 12, 15)) + ", "
    res += get_reg(get_field(word, 0, 3)) + ", ["
    res += get_reg(get_field(word, 16, 19)) + "]"
    return res

def mult(word, cond_code):
    """ Multiply and multiply with accumulate. (rd = rs*rm +rn) """
    res = ""
    column = 3
    if testBit(word, 21):
        res += "mla"
    else:
        res += "mul"
    if testBit(word, 20):
        res += 's'
        column += 1
    res+=cond(cond_code)
    if cond_code != 14: column +=2
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    #rd
    res += get_reg(get_field(word, 16, 19)) + ", "
    #rm
    res += get_reg(get_field(word, 0, 3)) + ", "
    #rs
    res += get_reg(get_field(word, 8, 11))
    if testBit(word, 21):
        #rn  accumulator
        res += ", " + get_reg(get_field(word, 12, 15))
    if testBit(word, 20):
        pass # will affect ccs
    return res

def mult_long(word, cond_code):
    """ Multiply with 64-bit result. Accumulate also supported. """
    # regular rdhi, rdlo = rm*rs
    # accumulate rdhi, rdlo = rm*rs + rdhi, rdlo
    # r15 not used
    res = ""
    column = 5
    if testBit(word, 22):
        res += "s"
    else:
        res += "u"
    if testBit(word, 21):
        res += "mlal"
    else:
        res += "mull"
    if testBit(word, 20):
        res += 's'
        column += 1    
    res+=cond(cond_code)
    if cond_code != 14: column +=2
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    #rdlo
    res += get_reg(get_field(word, 12, 15)) + ", "
    #rhi
    res += get_reg(get_field(word, 16, 19)) + ", "
    #rm
    res += get_reg(get_field(word, 0, 3))
    #rs 
    res += ", " + get_reg(get_field(word, 8, 11))
    if testBit(word, 20):
        pass # will affect ccs    
    return res

def single_data_transfer(word, cond_code):
    """ ldr(b) and str(b). Loading and storing registers from memory. """
    res = ""
    col = 0   
    write_address_back = False; force_nonp = False; load_mem = False
    immed = False if testBit(word, 25) else True

    if testBit(word, 24):
        pre = True
        write_address_back = True if testBit(word, 21) else False
    else:   # post
        pre = False
        write_address_back = True
        force_nonp = True if testBit(word, 21) else False

    add_to_base = True if testBit(word, 23) else False
     
    transfer_byte = True if testBit(word, 22) else False
 
    if testBit(word, 20):
        load_mem = True
        res += "ldr"  
        # also pld, prepare cache for load
    else:
        load_mem = False
        res += "str"
    column = 3
    if transfer_byte: res+="b"; column +=1
    res+=cond(cond_code)
    if cond_code != 14: column +=2
    if write_address_back and not pre: res+="T"; column +=1
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    # rd
    res+=get_reg(get_field(word, 12, 15))+", "
    column += 3  # not accurate but not ICOLUMN 

    # [rn + <expr>]
    res +="["+get_reg(get_field(word, 16,19))
    if immed:
        offset = get_field(word, 0,11)
        if offset != 0:
            if add_to_base:
                res+="+"
            else:   
                res+="-"
            res+="#{:d}".format(offset)

    else:  # register shifted by immediate as offset
        if add_to_base:
            res+="+"
        else:   
            res+="-"        
        # rm
        res+=" " +get_reg(get_field(word,0,3))        
        shift_count = get_field(word, 7, 11)
        if get_shift_type(word) == "lsl":
            if shift_count != 0:
                res+= ", lsl" + " #{:d}".format(shift_count)
        else:
            res+= ", " + get_shift_type(word)
            if shift_count == 0:
                res+=" #32"
            else:
                res+= " #{:d}".format(shift_count)
    res+="]"        
        
    return res

def single_data_transfer_hd(word, cond_code):
    """ Loads and stores of halfwords and doublewords. """
    res = ""
    col = 0  
    write_address_back = False; force_nonp = False; load_mem = False 
    if testBit(word, 24):
        pre = True
        write_address_back = True if testBit(word, 21) else False
    else:   # post
        pre = False
        # writeback always 0, but writeback always happens
        write_address_back = True
        force_nonp = True if testBit(word, 21) else False

    add_to_base = True if testBit(word, 23) else False

    if testBit(word, 22): 
        use_offset = True
        offset = get_field(word, 8, 11) << 4
        offset |= get_field(word, 0, 3)
    else: 
        use_offset = False
        rm = get_field(word, 0, 3)
    sh_bits = get_field(word, 5, 6)
    if sh_bits == 0:
        return "Error: swp instruction detected in wrong routine"    
    if testBit(word, 20):
        load_mem = True
        res += "ldr"
    else:
        if sh_bits == 2:
            load_mem = True
            res +="ldr"
        else:
            load_mem = False
            res += "str"
    column = 3 
    res+=cond(cond_code)
    if cond_code != 14: column +=2    

    column +=1
    if testBit(word, 20):
        if sh_bits == 1:
            res += "h"
        elif sh_bits == 2:
            res += "sb"
            column += 1
        elif sh_bits == 3:
            res += "sh"
            column += 1
    else:
        if sh_bits == 1:
            res += "h"
        elif sh_bits == 2:
            res += "d"
        elif sh_bits == 3:
            res += "d"       
    res += SPACES[column:ICOLUMN]; column = ICOLUMN
    res += get_reg(get_field(word, 12, 15)) + ", "
    # [rn + <expr>]
    res +="["+get_reg(get_field(word, 16,19))
    if add_to_base:
        addchr ="+"
    else:   
        addchr ="-"
    if use_offset:
        if offset != 0:
            res+= addchr + "#{:d}".format(offset)
    else:
        res += addchr + "[" + get_reg(rm) + "]"
    res+="]"  
    
    return res
    

def reg_list_see_armcpu(word):
    """ Return a register list of the form {rx,ry,..} according to bits 0..15"""
    res = ""
    regno = 0
    for regno in range(16):
        if testBit(word, regno):
            res+=get_reg(regno) 
            res += ","
    res_len = len(res)
    if res_len > 0 and res[res_len-1] == ",":
        res_len -=1
        
    return "{" + res[0:res_len] + "}"
    
    
def block_data_transfer(word, cond_code):
    """ LDM, STM variants. Special case pop and push if using sp. """
    res = ""
    base_reg = get_field(word, 16, 19)
    column = 0
    if cond_code != 14: column+=2
    control_bits = get_field(word, 20, 24)
    column += 3
    if (base_reg == 13):
        if (control_bits == 0b10010):
            column +=1
            res += "push"+cond(cond_code)+SPACES[column:ICOLUMN]
            return res + reg_list(word)
        elif (control_bits == 0b01011):
            res += "pop"+cond(cond_code)+SPACES[column:ICOLUMN]
            return res + reg_list(word) 
    # missing writeback info and R15 force user handling
    res += "ldm" if testBit(word, 20) else "stm"
    res += "i" if testBit(word, 23) else "d"
    res += "b" if testBit(word, 24) else "a"
    return res + SPACES[5:ICOLUMN] +get_reg(base_reg) + ", " + reg_list(word)

def branch(offset, word, cond_code):
    """ Branch/Branch and link. """
    # needs blx - but also needs Thumb
    res = ""
    column = 0
    if get_field(word, 28, 31) == 31:  # no conditions on this
        if testBit(word, 24):
            halfword_offset = 2
        else:
            halfword_offset = 0
        res += "blx"
        column = 3
        dest = get_dest(offset+halfword_offset, get_field(word, 0,23))       
        res += SPACES[column:ICOLUMN]+dest          
        res += ", Thumb=1"

        return res
    
    if testBit(word, 24):
        res+="bl"
        column = 2
    else:
        res+="b"
        column = 1
    if cond_code != 14: column+=2
    res+=cond(cond_code)+SPACES[column:ICOLUMN]+get_dest(offset, 
                                                    get_field(word, 0,23))    
    return res

def branch_exchange(offset, word, cond_code):
    """ Load pc from a register. Switch in and out of thumb mode using bit 0 """
    res = ""
    column = 2
    if cond_code != 14: column+=2
    if testBit(word, 5):
        res += "blx"
        column += 1
    else:
        res += "bx"
    res += cond(cond_code)+SPACES[column:ICOLUMN]+get_reg(
                                                    get_field(word, 0,3))
    return res

def coprocessor_data_transfer(word, cond_code):
    """ldc, stc instructions. """
    res = ""
    res += "ldc" if testBit(word, 20) else  "stc"
    column = 3 
    if testBit(word, 28):
        res += "2" 
        column+=1
    else: 
        res += cond(cond_code)
        column = len(res)
    if testBit(word, 22): res += "l"; column += 1
    res += SPACES[column:ICOLUMN]
    res += "p{:d}, ".format(get_field(word, 8, 11))   # pn proc number 
    res += "c{:d}, ".format(get_field(word, 12, 15))  # copr source/destd 
    res += "[r{:d} + 0x{:x}]".format(get_field(word, 16, 19), 
                                     get_field(word, 0,7)*4)
    return res

def swi_or_coproc(offset, word, cond_code):
    """ Software interrupt, or coprocessor instructions. """
    res = ""
    if testBit(word, 24): 
        return res +"swi" + SPACES[3:ICOLUMN] + "{0:#x}".format(
            get_field(word, 0, 23))
    if testBit(word, 4):    #mrc/mcr
        res += "mrc" if testBit(word, 20) else "mcr"  # mcr arm -> cop
        res += SPACES[3:ICOLUMN]
        res += "p{:d}, ".format(get_field(word, 8, 11))   # pn proc number
        res += "{:d}, ".format(get_field(word, 21, 23))   # cpopc opcode
        res += "r{:d}, ".format(get_field(word, 12, 15))  # rd  
        res += "c{:d}, ".format(get_field(word, 16, 19))  # source/dest creg 
    else: #cdp   
        if testBit(word, 28):
            res += "cdp2" 
            column = 4
        else:
            res += "cdp"
            column = 3
        res += SPACES[column:ICOLUMN]
        res += "p{:d}, ".format(get_field(word, 8, 11))   # pn proc number
        res += "{:d}, ".format(get_field(word, 20, 23))   # cpopc opcode
        res += "c{:d}, ".format(get_field(word, 12, 15))  # copr destd 
        res += "c{:d}, ".format(get_field(word, 16, 19))  # copr operand
    res += "c{:d} ".format(get_field(word, 0, 3))    # cop operand reg 
    if get_field(word, 5,7) != 0:
        res += ",{:d}".format(get_field(word, 5,7))
    return res    
    
def disass(offset, word, thumb_mode= False):
    """ Sort out the instruction categories and pass the word 
        to be disassembled to the corresponding routine.
    """
    if offset in das_strings:
        return das_strings[offset]  # cached    
    if thumb_mode: 
        das_strings[offset] = disass_thumb(offset, word)  # for 32 bit insts
        return das_strings[offset]
    
    res=""
    cond_code = get_field(word, 28, 31)
    ins_type = get_field(word, 25, 27)
    if ins_type == 0:
        if (word & 0x0fffff00) == 0x012fff00:
            res+= branch_exchange(offset, word, cond_code)
            das_strings[offset] = (res, 4)  # cache it
            return (res, 4 )       
        if testBit(word, 4) and testBit(word, 7):
            four_seven = get_field(word, 4, 7)
            if four_seven == 9:
                if (get_field(word, 22, 27) == 0): 
                    res += mult(word, cond_code)
                elif get_field(word, 23, 27) == 1:
                    res += mult_long(word, cond_code)
                elif get_field(word, 23, 27) == 2:
                    if (get_field(word, 20, 21) == 0):
                        res += swp(word, cond_code)
                    else:
                        res = "Unidentified instruction {:x}".format(word) 
            else:
                # ldrh, ldrd and stores
                res += single_data_transfer_hd(word, cond_code)
 
        else:  
            if (word & 0x0fff0ff0) == 0x016f0f10:
                res += count_leading_zeros(word, cond_code)
                das_strings[offset] = (res, 4)  # cache it
                return (res, 4 )           
            # a DP type with shift
            # if bit 25 is zero, operand 2 is a register (possibly shifted) 
            # if bit 4 is zero, 5,6 are shift type, 7-11 are shift count
            # if bit 4 is 1, bit 7 is zero, bit 5-6 are shift type 8-11 are 
            # shift reg.
            # So bits 4 and 7 cannot be both set
        
            res += data_processing(offset, word, cond_code)
    elif ins_type ==1:
        # rotate in 8-11, imm in 0-7
        res += data_processing(offset, word, cond_code)
        
    elif ins_type ==2 or ins_type == 3:
        res += single_data_transfer(word, cond_code)
    elif ins_type ==4:
        res += block_data_transfer(word, cond_code)
    elif ins_type ==5:
        res+= branch(offset, word, cond_code)
    elif ins_type ==6:
        res+=coprocessor_data_transfer(word, cond_code)
    elif ins_type ==7:
        res+= swi_or_coproc(offset, word, cond_code)
    else:
        res+="<undefined {:x}>".format(word)
    das_strings[offset] = (res, 4)  # cache it    
    return (res, 4)

def cmp(string1, string2):
    """ Compare two strings for unit testing. """
    if string1 == string2:
        print( "PASS : "+string1)
    else:
        print("FAIL    : "+string1)
        print("Expected: "+string2)



if __name__ == '__main__':
    """ If you run this as a main program some unit testing is done. """
    
    from arch import machine
    if machine != "ARM":
        import sys
        print("This file, arm/disass.py, is for the arm family only. Check arch.py")
        sys.exit(-1)     

    print("*** disass.py module ***")
 
    # This is not a program, just some random instructions pulled from images
    cmp(disass(0,      0xea0020ce) [0],  "b        0x8340 ;")
    cmp(disass(0x8488, 0x9afffffb) [0],  "bls      0x847c ;") 
    cmp(disass(0x8694, 0xebffffba) [0],  "bl       0x8584 ;")
    cmp(disass(0x802c, 0x8afffffb) [0],  "bhi      0x8020 ;")
    cmp(disass(4,      0xe3c1000f) [0],  "bic      r0, r1, #15 (#0xf)")
    cmp(disass(8,      0xe3550006) [0],  "cmp      r5, #6 (#0x6)")
    cmp(disass(12,     0xe1720001) [0],  "cmn      r2, r1")
    cmp(disass(16,     0xe3720001) [0],  "cmn      r2, #1 (#0x1)")
    cmp(disass(20,     0xe15b0000) [0],  "cmp      r11, r0")
    cmp(disass(24,     0xe3a0d902) [0],  "mov      sp, #32768 (#0x8000)")
    cmp(disass(28,     0xc3e06000) [0],  "mvngt    r6, #0 (#0x0)")
    cmp(disass(32,     0xe3300000) [0],  "teq      r0, #0 (#0x0)")
    cmp(disass(36,     0xe2810049) [0],  "add      r0, r1, #73 (#0x49)")
    cmp(disass(40,     0xe2522001) [0],  "subs     r2, r2, #1 (#0x1)")
    cmp(disass(44,     0xe2602000) [0],  "rsb      r2, r0, #0 (#0x0)")
    cmp(disass(48,     0xe0696006) [0],  "rsb      r6, r9, r6")
    cmp(disass(52,     0xe0692189) [0],  "rsb      r2, r9, r9, lsl #3")
    cmp(disass(56,     0xe1811002) [0],  "orr      r1, r1, r2")
    cmp(disass(60,     0xe19ccc06) [0],  "orrs     r12, r12, r6, lsl #24")
    cmp(disass(64,     0xe0022003) [0],  "and      r2, r2, r3")
    cmp(disass(68,     0xe21660ff) [0],  "ands     r6, r6, #255 (#0xff)") 
    cmp(disass(72,     0xe16f2f11) [0],  "clz      r2, r1")
    cmp(disass(76,     0xe1c000d4) [0],  "ldrd     r0, [r0+#4]")
    cmp(disass(80,     0xe1d330b0) [0],  "ldrh     r3, [r3]")
    cmp(disass(84,     0xe1c230b0) [0],  "strh     r3, [r2]")
    cmp(disass(88,     0xe5d67000) [0],  "ldrb     r7, [r6]")
    cmp(disass(92,     0x259fc050) [0],  "ldrcs    r12, [pc+#80]")
    cmp(disass(96,     0x05c32004) [0],  "strbeq   r2, [r3+#4]") 
    cmp(disass(100,    0xe0200391) [0],  "mla      r0, r1, r3, r0")
    cmp(disass(104,    0xe0010190) [0],  "mul      r1, r0, r1")
    cmp(disass(108,    0xe98d0006) [0],  "stmib    sp, {r1,r2}")
    cmp(disass(112,    0xb8bd0010) [0],  "poplt    {r4}")
    cmp(disass(116,    0xe12fff1e) [0],  "bx       lr")
    cmp(disass(120,    0x012fff1e) [0],  "bxeq     lr")
    cmp(disass(124,    0x112fff1e) [0],  "bxne     lr")
    cmp(disass(128,    0xe1421093) [0],  "swpb     r1, r3, [r2]")
    cmp(disass(132,    0xe1031092) [0],  "swp      r1, r2, [r3]") 
    print("------------ Low priority diffs ------------")
    cmp(disass(200,    0xe1a00000) [0],  "nop")
    cmp(disass(204,    0xe7831102) [0],  "str      r1, [r3, r2, lsl #2]")  
    cmp(disass(208,    0xe1b000c0) [0],  "asrs     r0, r0, #1")
    cmp(disass(212,    0xe1a00c40) [0],  "asr      r0, r0, #24")
    cmp(disass(216,    0xe1a032a2) [0],  "lsr      r3, r2, #5")
    cmp(disass(220,    0xe1a03213) [0],  "lsl      r3, r3, r2")
    cmp(disass(224,    0xe1a03103) [0],  "lsl      r3, r3, #2")   
    cmp(disass(228,    0xe7930100) [0],  "ldr      r0, [r3, r0, lsl #2]")    
    
    