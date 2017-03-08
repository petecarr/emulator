""" Timer support in Broadcom BCM 2835 ARM (AKA raspberry pi) """

TIMER_ADDRESS = 0x20003000
TIMER_BANK_SIZE = 0x1c

TIMER_CS = 0
TIMER_COUNTER_LO = 4
TIMER_COUNTER_HI = 8
TIMER_COMPARE0 = 0xc
TIMER_COMPARE1 = 0x10
TIMER_COMPARE2 = 0x14
TIMER_COMPARE3 = 0x18

timer_cs = 0
timer_counter_lo = 0
timer_counter_hi = 0
timer_compare0 = 0
timer_compare1 = 0
timer_compare2 = 0
timer_compare3 = 0

def is_timer(address):
    return (address >= TIMER_ADDRESS) and (
            address < (TIMER_ADDRESS + TIMER_BANK_SIZE))

def get_timer_value(address):
    global timer_cs, timer_counter_lo, timer_counter_hi
    global timer_compare0,timer_compare1,timer_compare2,timer_compare3    
    if is_timer(address):
        offset = address - TIMER_ADDRESS
        if offset == TIMER_CS:
            return timer_cs
        elif offset == TIMER_COUNTER_LO:
            return timer_counter_lo
        elif offset == TIMER_COUNTER_HI:
            return timer_counter_hi
        elif offset == TIMER_COMPARE0:
            return timer_compare0
        elif offset == TIMER_COMPARE1:
            return timer_compare1
        elif offset == TIMER_COMPARE2:
            return timer_compare2
        elif offset == TIMER_COMPARE3:
            return timer_compare3
        else:
            return 0
    else:
        return 0
              

def set_timer_value(address, value):
    global timer_cs, timer_counter_lo, timer_counter_hi
    global timer_compare0,timer_compare1,timer_compare2,timer_compare3
    if is_timer(address):
        offset = address - TIMER_ADDRESS
        if offset == TIMER_CS:
            timer_cs = value
        elif offset == TIMER_COUNTER_LO:
            timer_counter_lo = value
        elif offset == TIMER_COUNTER_HI:
            timer_counter_hi = value
        elif offset == TIMER_COMPARE0:
            timer_compare0 = value
        elif offset == TIMER_COMPARE1:
            timer_compare1 = value
        elif offset == TIMER_COMPARE2:
            timer_compare2 = value
        elif offset == TIMER_COMPARE3:
            timer_compare3 = value
        else:
           return
    else:
        return
        
    
