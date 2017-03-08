""" Video support in Broadcom BCM 2835 ARM (AKA raspberry pi)"""
""" 
Info from Alex Chadwick  
http://www.cl.cam.ac.uk/freshers/raspberrypi/tutorials/os/screen01.html

Address	 Bytes	 Name	 Description	                 Read / Write
2000B880 4	 Read	 Receiving mail.                 R
2000B890 4	 Poll	 Receive without retrieving.	 R
2000B894 4	 Sender	 Sender information.	         R
2000B898 4	 Status	 Information.	                 R
2000B89C 4	 Configuration	 Settings.	         RW
2000B8A0 4	 Write	 Sending mail.	                         W

Status, 0 in bit 31 ready to write 
        0 in bit 30 ready to read
Read or write format 0-3 - mailbox number
                    4-31 - data
"""
"""
Ideally we want to interpret frame buffers, colors well enough 
to color a tkinter canvas """

from utilities import  bit_fields
from utilities.bit_fields import *

MBOX_ADDRESS = 0x2000B880
MBOX_BANK_SIZE = 0x24

MBOX_READ   = 0
MBOX_POLL   = 0x10
MBOX_SENDER = 0x14
MBOX_STATUS = 0x18
MBOX_CONFIG = 0x1c
MBOX_WRITE  = 0x20

mbox_read   = 0
mbox_poll   = 0
mbox_sender = 0
mbox_status = 0
mbox_config = 0
mbox_write  = 0


def is_mbox(address):
    return (address >= MBOX_ADDRESS) and (
            address < (MBOX_ADDRESS + MBOX_BANK_SIZE))

def get_mbox_value(address):
    global mbox_read,mbox_poll,mbox_sender,mbox_status,mbox_config,mbox_write
    if is_mbox(address):
        offset = address - MBOX_ADDRESS
        if offset == MBOX_READ:
            return mbox_read
        elif offset == MBOX_POLL:
            return mbox_poll
        elif offset == MBOX_SENDER:
            return mbox_sender
        elif offset == MBOX_STATUS:
            return mbox_status
        elif offset == MBOX_CONFIG:
            return mbox_config
        elif offset == MBOX_WRITE:
            return mbox_write
        else:
            return 0
    else:
        return 0
              

def set_mbox_value(address, value):
    global mbox_read,mbox_poll,mbox_sender,mbox_status,mbox_config,mbox_write

    if is_mbox(address):
        offset = address - MBOX_ADDRESS
        if offset == MBOX_READ:
            mbox_read = value
        elif offset == MBOX_POLL:
            mbox_poll = value
        elif offset == MBOX_SENDER:
            mbox_sender = value
        elif offset == MBOX_STATUS:
            mbox_status = value
        elif offset == MBOX_CONFIG:
            mbox_config = value
        elif offset == MBOX_WRITE:
            mbox_write = value
        else:
           return
    else:
        return
        
    