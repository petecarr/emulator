import sys, os
import datetime
from datetime import datetime

sys.path.extend(['.', '..'])

# CCS version 4 generates executable files in TI-COFF format.
# CCS version 5 has moved to the ELF format. 
# This is a dump program to interpret the fields of a TI-COFF file.

text_start = 0
text_size = 0
text_fileptr = 0
data_start = 0
data_size = 0
data_fileptr = 0
string_ptr = 0

st_classes = {0: "C_NULL", 1: "C_AUTO", 2: "C_EXT", 3: "C_STAT",
        4:"C_REG", 5:"C_EXTREF", 6:"C_LABEL", 7:"C_ULABEL",
        8:"C_MOS", 9:"C_ARG", 10:"C_STRTAG", 11:"C_MOU",
        12:"C_UNTAG", 13:"C_TPDEF", 14:"C_USTATIC", 15:"C_ENTAG",
        20:"C_STATLAB", 21:"C_EXTLAB", 27:"C_VARARG",
        100:"C_BLOCK", 101:"C_FCN", 102:"C_EOS", 
        103:"C_FILE", 104:"C_LINE"
        }


def read_coff_header(hdr):
    """ Interpret a COFF header. """
    res = "---- COFF Header ----\n"
    magic = int.from_bytes(hdr[0:2], "little")
    res += "COFF version         = {:#x},{:d}\n".format(magic, magic)
    
    num_sects = int.from_bytes(hdr[2:4], "little")
    res += "Sector count         = {:d}\n".format(num_sects)
    
    vstamp = int.from_bytes(hdr[4:8], "little")
    timestamp = datetime.fromtimestamp(vstamp).strftime("%a %Y-%m-%d %H:%M:%S")  
    res += "Time stamp           = {:s} ({:x})\n".format(timestamp, vstamp)
    
    symtab_ptr = int.from_bytes(hdr[8:12], "little")
    sym_cnt = int.from_bytes(hdr[12:16], "little")
    res += "Symtab pointer       = {:x}\n".format(symtab_ptr)
    res += "Symbol count         = {:d}\n".format(sym_cnt) 
    
    opt_hdr_siz = int.from_bytes(hdr[16:18], "little")
    res += "Optional header size = {:d}\n".format(opt_hdr_siz)
    
    flags = int.from_bytes(hdr[18:20], "little")
    res += "Flags                = {:x}\n".format(flags)
    if flags & 1:
        res += "   F_RELFLG   - relocation info stripped\n"
    if flags & 2:
        res += "   F_EXEC     - file is relocatable\n"
    if flags & 4:
        res += "   F_LNNO     - line numbers stripped (tms430 only)\n"
    if flags & 8:
        res += "   F_LSYMS    - local symbols stripped\n"
    if flags & 0x100:
        res += "   F_LITTLE   - little endian target\n"
    if flags & 0x200:
        res += "   F_BIG      - big endian target\n"
    if flags & 0x1000:
        res += "   F_SYMMERGE - duplicate syms removed\n"
    
    target_id = int.from_bytes(hdr[20:22], "little")
    #res += "target_id       = {:x}\n".format(target_id))
    if target_id == 160:
        res += "MSP430 target\n" 
        
    return res, num_sects, symtab_ptr, sym_cnt
        
def get_name(image, index):
    """ Names are either 8 bytes or a zero integer followed by a pointer to a 
        string table entry. 
    """
    global string_ptr
    name = image[index:index+8]
    n1 = int.from_bytes(image[index:index+2], 'little')
    #print "n1 = {:x}".format(n1))
    if n1 == 0:
        #a1 = int.from_bytes(image[index:index+4], 'little')
        a2 = int.from_bytes(image[index+4:index+8], 'little')
        #print( 'String table ptr = {:x}'.format(a2))
        len = 0
        ptr = string_ptr+a2
        while int(image[ptr]) != 0:
            #res += int(image[ptr]))
            ptr+= 1
            #len+= 1
        name = image[string_ptr+a2:ptr] #+len]
    
    import locale      
    encoding = locale.getdefaultlocale()[1]          
    try: 
        name1 = name.decode(encoding).strip('\0')
        return name1
    except:
        return "Can't decode name"
            
def read_opt_header(opt_hdr):
    """ Interpret the fields of the COFF file optional header. """
    res = ""
    magic = int.from_bytes(opt_hdr[0:2], "little")
    res += "---- Optional header ----\n"
    res += " Magic number   = {:#x}\n".format(magic)    
    version = int.from_bytes(opt_hdr[2:4], "little")
    res += " Version        = {:d}\n".format(version)
    text_size = int.from_bytes(opt_hdr[4:8], "little")
    data_size = int.from_bytes(opt_hdr[8:12], "little")
    bss_size = int.from_bytes(opt_hdr[12:16], "little")
    res += " Text size      = {:#x}\n".format(text_size)
    res += " Data size      = {:#x}\n".format(data_size)
    res += " BSS size       = {:#x}\n".format(bss_size)    
    entry_point = int.from_bytes(opt_hdr[16:20], "little")
    res += " Entry_point    = {:#x}\n".format(entry_point)
    text_start = int.from_bytes(opt_hdr[20:24], "little")
    res += " Text_start     = {:#x}\n".format(text_start)  
    data_start = int.from_bytes(opt_hdr[24:28], "little")
    res += " Data_start     = {:#x}\n".format(data_start)
    return res
    
def read_section(num, image, index):
    """ Interpret a section entry in the COFF file. """
    global text_start, text_size, text_fileptr, data_start, data_size, data_fileptr
    res = ""
    s0 = 0
    name = get_name(image, index)
    
    res += "[{:2d}] {:20s}".format(num, name)
    sect = image[index:index+48]
    
    paddr = int.from_bytes(sect[s0+8:s0+12], 'little')
    vaddr = int.from_bytes(sect[s0+12:s0+16], 'little')
    siz  = int.from_bytes(sect[s0+16:s0+20], 'little')
    fo   = int.from_bytes(sect[s0+20:s0+24], 'little')
    rel   = int.from_bytes(sect[s0+24:s0+28], 'little')
    flg  = int.from_bytes(sect[s0+40:s0+41], 'little')
    #res += '  flags    = {:x}'.format(flg))
    if flg & 0x10:
        res += " STYP_COPY"
    if flg & 0x20:
        res += " STYP_TEXT"
        text_start = paddr
        text_size = siz
        text_fileptr = fo
    if flg & 0x40:
        res += " STYP_DATA"
        data_start = paddr
        data_size = siz
        data_fileptr = fo            
    if flg & 0x80:
        res += " STYP_BSS "    
 

  
    res += ' {:8x}'.format(paddr)
    res += ' {:8x}'.format(vaddr)
    res += ' {:6x}'.format(siz)
    res += ' {:6x}'.format(fo)
    if rel != 0:
        res += '  {:x}'.format(rel)
        relcnt   = int.from_bytes(sect[s0+24:s0+28], 'little')
        res += '  {:x}'.format(relcnt)  
 
    res += "\n"
    return res

def dump_coff(name):
    """ Interpret the fields of a TI-COFF file. Generated by CCS v4. """
    with open(name, 'rb') as f:
        img_bytes = (f.read())
        
        res, num_sects, symtab_ptr, sym_cnt = read_coff_header(img_bytes[0:22])
        
        global string_ptr
        fp = symtab_ptr
        string_ptr = fp + 18*sym_cnt       
        
        res += read_opt_header(img_bytes[22:50])
        res += "\n"
        res += "---- Section headers: ----\n"
        s0 = 50  # 0o62
        res += "There are {:d} section headers starting at offset {:#x}\n".format(num_sects, s0)
        res += "[Nr] Name                 Type      PhysAddr VirtAddr FileOffs Size \n"

        for i in range(1,num_sects+1):
            res += read_section(i, img_bytes, s0)
            s0 += 48
        global text_start, text_size, text_fileptr, data_start, data_size, data_fileptr 
        
        res += "\n"
        res += "---- .text ----\n"
        fp = text_fileptr
        cnt = 0
        for i in range(text_start, text_start+text_size, 2):
            text_data = int.from_bytes(img_bytes[fp:fp+2], 'little')
            if cnt == 0:
                res += "{:08x} ".format(i)
            res += "{:04x}".format(text_data)
            res += "  "
            cnt += 1
            if cnt == 8:
                res += "\n"
                cnt = 0
            fp += 2
        if cnt < 8:
            res += "\n"
         
        if data_size !=  0:   
            res += "---- .data ----\n"
            fp = data_fileptr
            cnt = 0
            for i in range(data_start, data_start+data_size, 2):
                data_data = int.from_bytes(img_bytes[fp:fp+2], 'little')
                if cnt == 0:
                    res += "{:08x} ".format(i)
                res += "{:04x}\n".format(data_data)
                res += "  "
                cnt += 1
                if cnt == 8:
                    res += "\n"
                    cnt = 0                
                fp += 2
            if cnt < 8:
                res += "\n"            
        else:
            res += "No .data\n"
            
        res += "---- Symbol table ----\n"
        res += "Contains {:d} entries:\n".format(sym_cnt)
        res += "  Num    Value   Section Class   Aux Name\n"
        fp = symtab_ptr
        aux = 0
        for i in range(sym_cnt):
            if aux > 0:
                aux -= 1
                # print out contents?
            else:
                name = get_name(img_bytes,fp)
                symval = int.from_bytes(img_bytes[fp+8:fp+12], 'little')
                sect = int.from_bytes(img_bytes[fp+12:fp+14], 'little')
                st_class = int(img_bytes[fp+16])
                aux = int(img_bytes[fp+17])
                res += "{:4d}: {:8x} ".format(i, symval)
                if sect == 0xffff:
                    res += "    N_ABS"
                else:
                    res += " {:8d}".format(sect)
                #resvd = int.from_bytes(img_bytes[fp+14:fp+16], 'little')
                #res += "Reserved h/w = {:x}".format(resvd))
                res += " {:8s}".format(st_classes[st_class])
                res += " {:2d}".format(aux)
                res += " {:20s}".format(name)
                res += "\n"
            fp += 18
    
        return res


     
if __name__ == '__main__':   
    name = "coff/HelloWorld.out"
    print(dump_coff(name))