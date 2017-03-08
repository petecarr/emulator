""" GPIO support in Broadcom BCM 2835 ARM (AKA raspberry pi) """

from utilities import  bit_fields
from utilities.bit_fields import *

GPIO_ADDRESS = 0x20200000
GPIO_BANK_SIZE = 0xb0

GPSEL0 = 0
GPSEL1 = 4
GPSEL2 = 8
GPSEL3 = 0xc
GPSEL4 = 0x10
GPSEL5 = 0x14

GPSET0 = 0x1C
GPSET1 = 0x20
# CLR means led is on
GPCLR0 = 0x28
GPCLR1 = 0x2c

GPLEV0 = 0x34
GPLEV1 = 0x38

# and many more concerned with rising and falling edge detects etc

def is_gpio(address):
    return (address >= GPIO_ADDRESS) and (
            address < (GPIO_ADDRESS + GPIO_BANK_SIZE))

#GPSELx fields
def fselx(pin_number):
    if pin_number <= 9:
        low_bit = pin_number*3
        return GPSEL0,low_bit,low_bit+2
    elif pin_number <= 19:
        low_bit = (pin_number -10)*3
        return GPSEL1, low_bit, low_bit+2 
    elif pin_number <= 29:
        low_bit = (pin_number -20)*3
        return GPSEL2, low_bit, low_bit+2 
    elif pin_number <= 39:
        low_bit = (pin_number -30)*3
        return GPSEL3, low_bit, low_bit+2 
    elif pin_number <= 49:
        low_bit = (pin_number -40)*3
        return GPSEL4, low_bit, low_bit+2
    elif pin_number <= 53:
        low_bit = (pin_number -50)*3
        return GPSEL5, low_bit, low_bit+2 
    else:
        return 0,0,0
    
def get_pin(value, start_pin, end_pin):
    val = value
    for pin_number in range(start_pin, end_pin):
        if testBit(val, 0) != 0:
            return "Select GPIO pin {:d}".format(pin_number)
        else:
            val >>=3
              
    return "Error in gpio module"

def output_set(level, value, start_pin, end_pin):
    val = value
    ret = ""
    for pin_number in range(start_pin, end_pin):
        if testBit(val, 0) != 0:
            ret+= "Pin number {:d} is {:s}\n".format(pin_number, level)
        val >>=1
    return ret   
        
    
def gpio_function(address, value):
    if address == GPIO_ADDRESS+GPSEL0:
        return get_pin(value, 0,10)
    elif address == GPIO_ADDRESS + GPSEL1:
        return get_pin(value, 10, 20)
    elif address == GPIO_ADDRESS + GPSEL2:
        return get_pin(value, 20, 30)
    elif address == GPIO_ADDRESS + GPSEL3:
        return get_pin(value, 30, 40)
    elif address == GPIO_ADDRESS + GPSEL4:
        return get_pin(value, 40, 50)    
    elif address == GPIO_ADDRESS + GPSEL5:
        return get_pin(value, 50, 53) 
    
    elif address == GPIO_ADDRESS + GPSET0:
        return  output_set("on (led off)", value, 0, 32)
    elif address == GPIO_ADDRESS + GPSET1:
        return output_set("on (led off)", value, 32, 54)
    
    elif address == GPIO_ADDRESS + GPCLR0:
        return output_set("off (led on)", value, 0, 32)
    elif address == GPIO_ADDRESS + GPCLR1:
        return output_set("off (led on)", value, 32, 54)    

# for TIVA, armv7-M     
def is_PLL(addr):
    if addr == 0x400fe060:
        return True
    elif addr == 0x400fe050:
        return True
    else:
        return False
    
def setup_PLL(addr):
    if addr == 0x400fe060:
        return 0x01ce1540
    elif addr == 0x400fe050:
        return 0x140
    else:
        return 0
    
    