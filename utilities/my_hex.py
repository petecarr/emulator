
def my_hex(bytes):
    """ Return an 8 char hex interpretation of a 32 bit little endian word. """
    # so many methods and none seem to do this
    hexasc = "0123456789abcdef"
    ret=""
    for i in reversed(range(len(bytes))):
        b = bytes[i]
        ret += hexasc[int(b>>4)]
        ret += hexasc[int(b & 15)]
    return ret
