import sys, os

try:
    import arch
except ImportError:
    sys.path.extend(['.', '..'])
from arch import machine
if machine == "MSP430":
    from msp430 import msp430cpu, emulate
    from msp430.emulate import MSP430Cpu
    from msp430.msp430cpu import address_mask, section_addrs, section_bytes
elif machine == "ARM":
    pass
else:
    print("Need to specify MSP430 in arch.py")
    sys.exit(-1)
    
from utilities import logging
from utilities.logging import log    




#st_classes = {0: "C_NULL", 1: "C_AUTO 1", 2: "C_EXT 2", 3: "C_STAT 3",
#        4:"C_REG 4", 5:"C_EXTREF 5", 6:"C_LABEL 6", 7:"C_ULABEL 7",
#        8:"C_MOS 8", 9:"C_ARG 9", 10:"C_STRTAG 10", 11:"C_MOU 11",
#        12:"C_UNTAG 12", 13:"C_TPDEF 13", 14:"C_USTATIC 14", 15:"C_ENTAG 15",
#        20:"C_STATLAB 20", 21:"C_EXTLAB 21", 27:"C_VARARG  27",
#        100:"C_BLOCK 100", 101:"C_FCN 101", 102:"C_EOS 102", 
#        103:"C_FILE 103", 104:"C_LINE 104"
#        }

C_EXT = 2
C_STAT = 3


SECTION_OFFSET = 50
SECTION_SIZE = 48
SYMTAB_ENTRY_SIZE = 18
STRING_TABLE = -1

class COFF_Error(Exception):
    def __init__(self, value):
        self.value = value
      
    def __str__(self):
        return self.value

def read_coff_header(hdr):
    magic = int.from_bytes(hdr[0:2], "little")
    if magic != 0xc2:
        raise COFF_Error("Not a coff file\n")
    
    num_sects = int.from_bytes(hdr[2:4], "little")  
    symtab_ptr = int.from_bytes(hdr[8:12], "little")
    sym_cnt = int.from_bytes(hdr[12:16], "little") 
    entry_address = int.from_bytes(hdr[38:42], "little")
    return num_sects, symtab_ptr, sym_cnt, entry_address
        
def get_name(image, index): 
    global STRING_TABLE
    name = image[index:index+8]
    n1 = int.from_bytes(image[index:index+2], 'little')
    #print("n1 = {:x}".format(n1))
    if n1 == 0:
        #a1 = int.from_bytes(image[index:index+4], 'little')
        a2 = int.from_bytes(image[index+4:index+8], 'little')
        #print('String table ptr = {:x}'.format(a2))
        len = 0
        ptr = STRING_TABLE+a2
        while int(image[ptr]) != 0:
            #print(int(image[ptr]))
            ptr+= 1
            #len+= 1
        name = image[STRING_TABLE+a2:ptr] #+len]
    
    import locale      
    encoding = locale.getdefaultlocale()[1]          
    try: 
        name1 = name.decode(encoding).strip('\0')
        return name1
    except:
        return "Can't decode name"
            




def get_symbol_dictionary(img, symtab_ptr, symbol_count):
    """ Return a symbol table as a dictionary """
    symdict = dict() 

    stp = symtab_ptr
    aux = 0
    for i in range(symbol_count):
        if aux > 0:
            aux -= 1 
        else:
            name = get_name(img, stp)
            symval = int.from_bytes(img[stp+8:stp+12], 'little')
            
            #sect = int.from_bytes(img[stp+12:stp+14], 'little')
            #if sect == 0xffff:
            #    print("N_ABS  - Absolute value")
            #else:
            #    print("Section = {:d}".format(sect))
     
            st_class = int(img[stp+16])
            if name != "":
                if st_class == C_STAT or st_class == C_EXT:
                    if name[0] != '$':
                        symdict[symval] = name                
            
            aux = int(img[stp+17])
                   
        stp += SYMTAB_ENTRY_SIZE

     
       
                            
    return symdict 

def get_section(img, idx):
    section = img[idx:idx+SECTION_SIZE]
    return section

def get_section_type(sect):
    flgs = int.from_bytes(sect[40:41], 'little')
    return flgs

def get_section_name(sect):
    name = get_name(sect, 0)
    return name 

def is_loadable_section(section_type):
    if section_type & 0x20:  # .text
        return True
    elif section_type & 0x40: # .data
        return True
    # might want to handle .bss == 0x80
    else:
        return False
    
def get_section_data(img, section):
    section_start = int.from_bytes(section[8:12], 'little')
    section_size  = int.from_bytes(section[16:20], 'little')
    fileptr   = int.from_bytes(section[20:24], 'little') 
    return section_start, img[fileptr: fileptr+section_size]
    
            
def load_coff(filename, cpu):
    """ Load from .out file into emulated memory. """
    nulldict = dict()
    try:
        with open(filename, 'rb') as file:
            try:
                log("Loading from {:s}".format(filename))
                coffimage = file.read()
                if coffimage:       
                    nsec, symtab_ptr, sym_count, entry_address = read_coff_header(coffimage)
                    global STRING_TABLE
                    STRING_TABLE = symtab_ptr + SYMTAB_ENTRY_SIZE*sym_count 
                    section_index = SECTION_OFFSET
                    for idx in range(nsec):
                        section = get_section(coffimage, section_index)
                        section_type = get_section_type(section)
                        if is_loadable_section(section_type):
                            section_name = get_section_name(section)
                            #log("Loading from section {:s}".format(section_name))
                            addr, nbytes = get_section_data(coffimage, section)
                            if nbytes:
                                cpu.setup_memory(nbytes, addr) 
                                log("Loaded 0x{:x} bytes at 0x{:x} from section {:s}".format(
                                    len(nbytes), addr, section_name))
                                section_addrs[addr] = section_name
                                section_bytes[section_name] = len(nbytes) 
                        section_index += SECTION_SIZE
    
                    # should have itentry_address = coffheader['e_entry']
                    cpu.pc = entry_address & address_mask
         
                    return get_symbol_dictionary(coffimage, symtab_ptr, sym_count)
            except COFF_Error as ex:
                log("COFF error: {:s}\n".format(ex)) 
                return nulldict
                                
    except FileNotFoundError:
        log( "File <"+filename+"> not found." )
        return nulldict
     

     
if __name__ == '__main__':   
    name = "coff/HelloWorld.out"
    cpu=MSP430Cpu("")
    symdict = load_coff(name, cpu)
    print("Completed normally. Symdict is {:d} entries long".format(len(symdict)))