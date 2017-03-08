from ctypes import *

def convert(s):
    i = int(s, 16)                   # convert from hex to a Python int
    cp = pointer(c_int(i))           # make this into a c integer
    fp = cast(cp, POINTER(c_float))  # cast the int pointer to a float pointer
    return fp.contents.value         # dereference the pointer, get the float

def convert_int_to_float(i):
    cp = pointer(c_int(i))           # make this into a c integer
    fp = cast(cp, POINTER(c_float))  # cast the int pointer to a float pointer
    return fp.contents.value         # dereference the pointer, get the float

def convert_float_to_int(f):
    cp = pointer(c_float(f))         # make this into a c float
    ip = cast(cp, POINTER(c_int))    # cast the float pointer to an int pointer
    return ip.contents.value         # dereference the pointer, get the int

if __name__ == '__main__':
    """ If you run this as a main program some unit testing is done. """
    print(convert("40800000"))
    print(convert("3f800000"))
    print(convert("bf000000"))
    print(convert_int_to_float(0x40800000))
    print(convert_int_to_float(0xc0800000))
    print(convert_int_to_float(0x3f800000))
    print(convert_int_to_float(0x3f000000)) 
    print(convert_int_to_float(0xbf000000))
    print("{:#x}".format(convert_float_to_int(-0.5)))
    
    i =  0x41973333
    f = convert_int_to_float(i)
    print(f)
    print("Expect 18.899999618530273 ")
    print("{:8.4f}".format(f))
    print("Expect 18.9000")    