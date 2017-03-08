import os
from utilities import my_hex, bit_fields, check_for_diffs
from utilities.bit_fields import *
from utilities.my_hex import *
from utilities.check_for_diffs import *

from arm import disass


KERNEL_IMAGE="examples\\screen04.kernel.img"


#----------------------------------------------------------------------------

def disassemble(filename):
    """ Disassemble the whole file into a string. """
    # Not called from dbg or gui_dbgr
    res=""
    gap = 0
    try:
        with open(filename, "rb") as kernel:
            offset = 0
            membytes = kernel.read(4)
            while membytes:
                if membytes != bytearray(4):
                    if gap > 0:
                        res +=("*** gap of {:d} bytes\n".format(gap))
                    res +=("%08x "%offset) 
                    bytesarr = bytearray(4)
                    for i in range(len(membytes)):
                        bytesarr[i] = membytes[i]
                    if len(membytes) != 4:
                        for i in range(len(membytes),4):
                            bytesarr[i] = 0 
                    word = int.from_bytes(bytesarr, 'little')      
                    res +=(my_hex(bytesarr)+"  ") 
                    (tmp, instr_size) = disass.disass(offset, word)
                    res += tmp+"\n"
                    gap = 0
                    offset += instr_size
                else:
                    gap += 4   
                    offset += 4
                membytes = kernel.read(4)
             
        kernel.close()
        return res
    except FileNotFoundError:
        return "File <"+filename+"> not found."

    
if __name__ == '__main__': 
    filename=os.path.join(os.getcwd(),KERNEL_IMAGE)
    res = "Filename is <"+filename+">\n"    
    res += disassemble(filename)
    printing = True
    if printing:
        print(res)
    else:
        check_for_diffs(res, "examples\\screen04.disass.txt", "TMP.txt", replace=False)
