""" Bit and field handling in integers. """



#----------------------------------------------------------------------------

def testBit(int_type, offset):
    """ Return 1 if bit at 2**offset is 1. """
    mask = 1 << offset
    return(int_type & mask) != 0

def setBit(int_type, offset):
    """ Set bit at 2**offset. """
    mask = 1 << offset
    return(int_type | mask)

def clearBit(int_type, offset):
    """ Clear bit at 2**offset. """
    mask = ~(1 << offset)
    return(int_type & mask)


def toggleBit(int_type, offset):
    """ Invert bit at 2**offset. """
    mask = 1 << offset
    return(int_type ^ mask)

#----------------------------------------------------------------------------


def get_field(value, startbit, endbit):
    """ Extract data from startbit to endbit from 32 bit integer value. """
    if 32 > endbit >= startbit >= 0:
        val = value >> startbit
        mask = (1 << (endbit-startbit+1)) -1
        return val & mask 
    else:
        raise ValueError

def set_field(value, newfield, startbit, endbit):
    """ Insert data from startbit to endbit into 32 bit integer value. """
    if 32 > endbit >= startbit >= 0:
        val  = newfield<<startbit
        mask = ((1 << (endbit-startbit+1)) -1)<<startbit
        val = val & mask
        return (value & ~mask) |val
    else:
        raise ValueError    

if  __name__ == '__main__': 
    
    # Change this into a unit_test section eventuially
    k = 0x28
    print ("Expect 5: %08x"%get_field(k, 3, 5))
    
    k = 0xff
    k = set_field(k,6, 3,5)
    print ("Expect f7:  %08x"%k)
    
    try:
        k =set_field(k,6,5,3)
    except ValueError:
        print("Bad Argument to set_field (as expected)")