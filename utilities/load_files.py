from os import path, getcwd

def file_exists(filename):
    """ This is supposed to be the Python way. Could use os routines. """
    try:
        with open(filename) as f:
            f.close()
            return True
    except IOError:
        return False 
    
def file_is_loadable(filename):
    """ Does the file exist and is it an image or ELF file. """
    if not file_exists(filename): return False
    extension = path.splitext(filename)[1][1:].strip()
    if extension == "img" or extension == "elf" or extension =="out":
        return True
    else: 
        return False
    

# a default for testing
#KERNEL_IMAGE="msp430/HelloWorld.out"  # a legacy coff file
KERNEL_IMAGE="msp430/metronome_430.out"  # an elf file
#KERNEL_IMAGE="kernel.img"

CHUNK_SIZE=16

filename=path.join(getcwd(),KERNEL_IMAGE)
#print("Filename is <"+filename+">")

def char_repr(membytes):
    ret = ""
    for i in range(len(membytes)):
        if 32 <= membytes[i] <= 127:
            bchar = chr(membytes[i])
            if bchar.isprintable():
                ret += bchar
            else:
                ret += '.'
        else:
            ret += '.'
    return ret
    
    
def my_hex(membytes):
    # so many methods and none seem to do this
    hexasc = "0123456789abcdef"
    ret=""
    for i in range(len(membytes)):
        b = membytes[i]
        ret += hexasc[int(b//16)]
        ret += hexasc[int(b & 15)]
    return ret
    
def dump(filename):
    """ dump - A straight hex dump of an img file. """
    #   Four hex words with char equivalent to the right, output to stdout.
    
    if filename == "":
        return ""
    res = ""
    gap = 0
    try:
        with open(filename, "rb") as kernel:
            offset = 0
            membytes = kernel.read(CHUNK_SIZE)
            while membytes:
                
                if membytes != bytearray(CHUNK_SIZE):
                    if gap > 0:
                        res += "*** gap of {:d} bytes\n".format(gap)
                    res += "{:08x} ".format(offset)
                    for i in range(0,len(membytes),4):
                        reversed_bytes=bytearray(4)
                        if len(membytes)-i < 4:
                            #print("Partial line length= {0}", len(bytes)-i)
                            k = 3
                            for j in range(len(membytes)-1,i,-1):   #Error here
                                reversed_bytes[k] = membytes[j]
                                k = k-1
                            
                        else:
                            reversed_bytes = (membytes[i+3],membytes[i+2],
                                              membytes[i+1],membytes[i])
                        res += my_hex(reversed_bytes)+" "
                        
                    res += char_repr(membytes) +"\n"
                    gap = 0
                else:
                    gap += CHUNK_SIZE
                offset += CHUNK_SIZE
                membytes = kernel.read(CHUNK_SIZE)
    except:
        pass
    return res

if __name__ == '__main__':
    print(dump(filename))    