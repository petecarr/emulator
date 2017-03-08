
# Help info for ARM processors.

class Help_Documentation:
    def __init__(self):

        self.DESCRIPTION = (
            "An emulator for a bare metal ARM cpu, "
        "originally targeted to the Raspberry Pi, a Broadcom BCM2835 system "
        "on a chip which contains a ARM1176JZFS cpu with floating point, "
        "running at 700Mhz or more, and a Videocore 4 GPU.\n"
        "Architecture is ARM v6 with 8-bit Java Byte Code, "
        "16-bit Thumb instruction set and 32-bit ARM instruction set "
        "support. Trust Zone security extensions are also present.\n\n"
        "Added Thumb2 support for Texas Instruments TIVA Launchpad.\n"
        "ARMv7-M Cortex M4 "
        "evaluation board with a TM4C123GH6PM processor (80MHz, 256kb Flash "
        "32kb SRAM, 2kb EEPROM. 16MHz main oscillator crystal and 32 KHz "
        "RTC crystal).\n"
        "ARMv7-M cpus only support Thumb2 instructions (16 and 32 bit).\n\n"
        "Warning: The emulation is incomplete.\n\n"
        "Author  Pete Carr.\n"
        "November 2012")

        self.REF_DESCRIPTION = (
            "DDI 0406B ARM Architecture Reference Manual \n"
            "          ARMv7-A and ARMv7-R edition\n"
            "DDI 0403D ARMv7-M Architecture Reference Manual\n"
            "DDI 0439D Cortex M4 Processor Technical Reference Manual\n"
            "DDI 0301H ARM1176jzf-s Technical Reference Manual\n"
            "Broadcom BCM2835 ARM Peripherals\n"
            )


        self.ACKNOWLEDGEMENTS = (
            "pyelftools: Eli Bendersky (eliben@gmail.com)\n"
            "effbot.org: tkinter information (2.x)\n"
            "zetcode.com: tkinter information\n"
            "diveintopython.net: python information (2.x)\n"
            "http://www.java2s.com/Code/Python/GUI-Tk : tk examples (2.x)\n"
            "www.raspberrypi.org/forum\n"
            "http://www.ti.com search for "
            "Getting_Started_with_the_TIVA C-Series LaunchPad\n"
            )
        
        self.INSTRUCTIONS = ("Not available yet\n")
        self.MEMORY =       ("Not available yet\n")
        
    def get(self, get_what):
        if get_what == "DESCRIPTION":
            return self.DESCRIPTION
        elif get_what == "REF_DESCRIPTION":
            return self.REF_DESCRIPTION
        elif get_what == "ACKNOWLEDGEMENTS":
            return self.ACKNOWLEDGEMENTS
        elif get_what == "INSTRUCTIONS":
            return self.INSTRUCTIONS
        elif get_what == "MEMORY":
            return self.MEMORY                
        else:
            return "Help requested unknown Documentation"