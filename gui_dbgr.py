import os, sys

from tkinter import *
from tkinter import tix as Tix
from tkinter.filedialog import askopenfilename
from tkinter import messagebox

import disassemble as das
import dbg
from elf.loadelf import  dump_elf
from coff.coff_print import dump_coff

from arch import machine
if machine == "ARM":
    from arm.emulate import ArmCpu
    from arm.armcpu import register_names, address_mask, visual_ccs, MEMADDR
    from arm.help import Help_Documentation
    KERNEL_IMAGE="project0.out"   #"kernel.img"
elif machine == "MSP430":
    from msp430.emulate import MSP430Cpu
    from msp430.msp430cpu import register_names, address_mask, visual_ccs, MEMADDR
    from msp430.help import Help_Documentation  
    KERNEL_IMAGE="msp430/metronome_430.out"
else:
    print("Need to specify a machine type in arch.py")
    sys.exit(-1)
    

from utilities import logging, load_files
from utilities.logging import enable_gui_logging, log
from utilities.load_files import file_exists, file_is_loadable, dump

#-------------------------------------------------------

Doc = Help_Documentation()


#--------------------------------------------------------



FG_COLOR=          'black'
BG_COLOR=          'wheat3'    # 'white'
FRAME_BG_COLOR=    'skyblue'
BREAK_COLOR =      'red'
REG_DIFF_COLOR =   'red'
PC_COLOR =         'blue'
SELECT_COLOR =     'green'
PANE_LABEL_COLOR=  'DarkOliveGreen4'  # 'skyblue' #'#62aa79'  
LABEL_FG_COLOR=    'black'
LOAD_BUTTON_COLOR ='steelblue'
GO_BUTTON_COLOR=   'darkgreen'
STOP_BUTTON_COLOR= 'red'
STEP_BUTTON_COLOR= 'darkgreen'
BREAK_BUTTON_COLOR='gray30'
QUIT_BUTTON_COLOR= 'red'

DEFAULT_PROMPT = u"> "

# Experimenting with bitmaps in buttons. Each pair of bytes should be swapped
# (if necessary) or the little-endian host will mess up the output.

def init_bitmap():
    return BitmapImage(foreground = 'red',
                       background = 'white',
                       data = """\
#define t_width 16
#define t_height 16
static unsigned char t_bits[] = {
    0xf0, 0x0f, 0xf8, 0x1f, 0xfc, 0x3f, 0xfe, 0x7f,
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
    0xfe, 0x7f, 0xfc, 0x3f, 0xf8, 0x1f, 0xf0, 0x0f
   };
""")

line=0.0

#----------------------------------------------------------------------------

def disassemble(filename):
    if filename != "":
        return das.disassemble(filename)
    else:
        if dbg.cpu is not None:
            return dbg.dump(dbg.cpu.memory, 
                            dbg.cpu.memory[0][MEMADDR], 
                            dbg.cpu.memory_bytes)
        else:
            return ""
        
def dumpelf(filename):
    if filename != "":
        if filename.endswith(".elf"):
            return dump_elf(filename)
        elif  filename.endswith(".out"):
            filetype = dbg.get_file_type(filename)
            if filetype == "elf":
                return dump_elf(filename)
            elif filetype == "coff":
                return dump_coff(filename)
        else:
            return disassemble("")
    else:
        return "" 
    
#------------------------------------------------------------------------------

def log_cmd(strng):
    """ Output to the log text widget and also, possibly, to a log file. """
    if dbgr.log_widget is not None:
        logging.log(strng)
        

#------------------------------------------------------------------------------ 

TCL_DONT_WAIT            = 1<<1
TCL_WINDOW_EVENTS        = 1<<2
TCL_FILE_EVENTS          = 1<<3
TCL_TIMER_EVENTS         = 1<<4
TCL_IDLE_EVENTS          = 1<<5
TCL_ALL_EVENTS           = 0


MODES = [
  ("Hex plus ascii", "HA"),
  ("Header dump (elf and coff only)", "OD"),
  ("Disassembly", "DA") 
  ]
#------------------------------------------------------------------------------

class Dbgr:
    """ The GUI debugger """
    def __init__(self, top):
        self.root = top
        self.exit = -1
            
        self.dir = None                            # script directory
        self.balloon = None                        # balloon widget
        self.useBalloons = Tix.StringVar()
        self.useBalloons.set('0')
        self.statusbar = None                      # status bar widget
        self.welmsg = None                         # Msg widget
        self.welfont = ''                          # font name
        self.welsize = ''                          # font size
        self.filename=""
        self.text_widget=None
        self.left_pane_label=None
        self.current_address = None
        self.current_selection = None
        self.cmd_entry = None
        self.cmd_entryPrompt = None
        self.cmd_prompt_len = 0
        self.answer_expected = False
        self.answer = None
        self.reg_widget=None
        self.log_widget=None
        self.which_display = StringVar()
        self.which_display.set("DA")               # hex and ascii   
        self.current_dump = 'Use File|Open to load file'

        #self.root.bind("<Key>", self.key)
        #self.root.bind("<Button-1>", self.callback) 
        #global img
        #img = init_bitmap()
        #self.bitmap = img      
        
        
    def build(self):
        root = self.root
        z = root.winfo_toplevel()
        z.wm_title(machine + ' Emulator')
        z.geometry('1000x900+10+10')
    
        self.balloon = Tix.Balloon(root)
    
        frame1 = self.MkMainMenu()
        frame3 = self.MkMainStatus() # MainDisplay refers to statusbar
        frame2 = self.MkMainDisplay()

        frame1.pack(side=TOP, fill=X)
        frame3.pack(side=BOTTOM,fill=X)
        frame2.pack(side=LEFT, fill=BOTH)

        self.balloon['statusbar'] = self.statusbar
        z.wm_protocol("WM_DELETE_WINDOW", lambda self=self: self.quit_cmd())
        
    def MkMainStatus(self):
        """ The statusbar at the base of the GUI debugger window. """
        top = self.root
        w = Tix.Frame(top, relief=Tix.RAISED, bd=1)
        self.statusbar = Tix.Label(w, relief=Tix.SUNKEN, bd=1)
        # Came from tixwidgets.py, despite being flagged as an unresolved attribute, you need
        # it to see the statusbar.
        self.statusbar.form(padx=2, pady=2, left=0, right='%100') # unresolved attribute appears to be necessary
        return w
    

    def MkMainMenu(self):
        """ The menus at the top of the GUI debugger window. """
        top = self.root
        w = Tix.Frame(top, bd=2, relief=RAISED)
        file = Tix.Menubutton(w, text='File', underline=0, takefocus=0)
        edit = Tix.Menubutton(w, text='Edit', underline=0, takefocus=0)
        debug =Tix.Menubutton(w, text='Debug',underline=0, takefocus=0)
        help_menu = Tix.Menubutton(w, text='Help', underline=0, takefocus=0)
        
        file.pack(side=LEFT)
        edit.pack(side=LEFT)
        debug.pack(side=LEFT)
        help_menu.pack(side=RIGHT)
        
        fm = Tix.Menu(file, tearoff=0)
        file['menu'] = fm
        em = Tix.Menu(edit, tearoff=0)
        edit['menu'] = em        
        dm = Tix.Menu(debug, tearoff=0)
        debug['menu'] = dm         
        hm = Tix.Menu(help_menu, tearoff=0)
        help_menu['menu'] = hm

        fm.add_command(label='Open', underline=1,
                    command = lambda self=self: self.load_cmd ())
        fm.add_command(label='Quit', underline=1,
                    command = lambda self=self: self.quit_cmd ())
        em.add_command(label = 'Copy', underline=1,
                    command = lambda self=self: self.doCopy(),
                    accelerator="Command-C")
        em.add_command(label = 'Select All', underline=1,
                    command = lambda self=self: self.doSelectAll(),
                    accelerator="Command-A")          
        dm.add_command(label='Start or Continue   F5', underline=1,
                    command = lambda self=self: self.go_cmd ())
        dm.add_command(label='Stop   F4', underline=1,
                    command = lambda self=self: self.stop_cmd ()) 
        dm.add_command(label='Step   F6', underline=1,
                    command = lambda self=self: self.stepi_cmd ())
        dm.add_command(label='Step Over F7', underline=1,
                    command = lambda self=self: self.stepo_cmd ())        
        dm.add_command(label='Set Break   F9', underline=1,
                    command = lambda self=self: self.break_cmd ())
        dm.add_command(label='Clear Break F10', underline=1,
                    command = lambda self=self: self.clear_break_cmd ())        
        
        hm.add_checkbutton(label='BalloonHelp', underline=0, command=ToggleHelp,
                           variable=self.useBalloons)
        hm.add_command(label='Command line help', underline=0, 
                       command=about_commands)
        hm.add_command(label='Acknowledgements', underline=0, 
                       command=acknowledgements)
        hm.add_command(label=machine + ' processor references', underline=0, 
                       command=references)
        hm.add_command(label=machine + ' instructions', underline=0, 
                       command=about_instructions)
        hm.add_command(label=machine + ' memory layout', underline=0, 
                       command=about_memory)
        hm.add_command(label='About ...', underline=0, 
                       command=about_display)
        
        return w
    
    
    def MkMainDisplay(self):
        top = self.root
        w = Tix.Frame(top, bd=2, relief=RAISED)
        w.config(bg=FRAME_BG_COLOR)
        
        pane = Tix.PanedWindow(w, orientation='horizontal')
    
        p1 = pane.add('wdmp', min=70, size=490)
        p2 = pane.add('wreglog', min=70)
        
        paneright = Tix.PanedWindow(p2, orientation='vertical')
        preg = paneright.add('wreg', min=70, size=390) 
        plog = paneright.add('wlog', min=70, size=390)
        pent = paneright.add('went', min=70, size=25)
        paneright.pack(side=RIGHT, fill = BOTH, expand=1)
        
        # Left hand pane
        
        wdmp = Tix.Frame(p1, bd=2, relief=FLAT)
        wdmp.pack(expand=1, fill=Tix.BOTH, padx=0, pady=0)
        msg1 = Label(wdmp, 
                    relief=Tix.FLAT,  anchor=Tix.N, 
                    text='Disassembly')
        msg1.config(bg=PANE_LABEL_COLOR, fg=LABEL_FG_COLOR, bd=3)
        msg1.pack(side=TOP, fill=X)
        self.left_pane_label = msg1
        win1 = Tix.ScrolledText(wdmp, scrollbar='auto')
        win1.text['wrap'] = 'none'
        #win1.vsb.config(troughcolor = 'gray90')  # ignored on windows, hsb is horizontal
        win1.text.insert(Tix.END, "Use menu item File|Open or Load button to\n")
        win1.text.insert(Tix.END, "select an img, elf or out file.")
        win1.pack(expand=1, fill=Tix.BOTH, padx=0, pady=0)
        self.text_widget = win1
        win1.text.config(foreground=FG_COLOR, background=BG_COLOR)
        win1.text.bind("<Button-1>", self.text_callback)
        win1.text.bind("<Key>", self.key)
        
        # Select disassembly or hex dump (and any other formats we want 
        # in the future) 
         
        for text, mode in MODES:
            rbtn = Radiobutton(wdmp, text=text,
                            variable=dbgr.which_display, value=mode, 
                            command=set_rb_mode)
            rbtn.config(indicatoron=1)  #1 is the default (0 is square buttons)
            rbtn.pack(anchor=W, side=BOTTOM, fill=Y) 

            set_rb_mode() 
            
        buttonframe = Frame(wdmp, borderwidth=2)
        buttonframe.pack(fill = BOTH, side = TOP, anchor=SE )

        borderwidth = 1
        # The row of buttons below the disassembly pane.   
        # Working from right to left.
        quit_btn = Tix.Button(buttonframe, text='Quit', command= self.quit_cmd)
        quit_btn.config(bg=QUIT_BUTTON_COLOR, fg='white', bd=borderwidth)
        qb = Tix.Balloon(self.root, statusbar=self.statusbar)
        qb.bind_widget(quit_btn, balloonmsg='Exit Emulator',
                      statusmsg='Press this button to quit.')
        quit_btn.pack(side=RIGHT)  
        
        listbreak_btn = Tix.Button(buttonframe, text='List Breaks', 
                                   command= self.list_breaks_cmd)
        listbreak_btn.config(bg=BREAK_BUTTON_COLOR, fg='white', bd=borderwidth)
        lbb = Tix.Balloon(self.root, statusbar=self.statusbar)
        lbb.bind_widget(listbreak_btn, balloonmsg='List breaks',
            statusmsg='Press this button to list breaks set.')
        listbreak_btn.pack(side=RIGHT)            
        
        break_btn = Tix.Button(buttonframe, text='Break', command= self.break_cmd)
        break_btn.config(bg=BREAK_BUTTON_COLOR, fg='white', bd=borderwidth)
        bb = Tix.Balloon(self.root, statusbar=self.statusbar)
        bb.bind_widget(break_btn, balloonmsg='Set a break',
            statusmsg='Press this button to set a break at the current selection.')
        break_btn.pack(side=RIGHT) 
        
        stepo_btn = Tix.Button(buttonframe, text='Step Over', command= self.stepo_cmd)
        stepo_btn.config(bg=STEP_BUTTON_COLOR, fg='white', bd=borderwidth)
        ob = Tix.Balloon(self.root, statusbar=self.statusbar)
        ob.bind_widget(stepo_btn, balloonmsg='Step over call',
            statusmsg='Press this button or the F7 key to step over a call.')
        stepo_btn.pack(side=RIGHT)        
            
        step_btn = Tix.Button(buttonframe, text='Step', command= self.stepi_cmd)
        step_btn.config(bg=STEP_BUTTON_COLOR, fg='white', bd=borderwidth)
        sb = Tix.Balloon(self.root, statusbar=self.statusbar)
        sb.bind_widget(step_btn, balloonmsg='Step one instruction',
                      statusmsg='Press this button or the F6 key to step.')
        step_btn.pack(side=RIGHT)
        
        
        stop_btn = Tix.Button(buttonframe, text='Stop', command= self.stop_cmd)
        stop_btn.config(bg=STOP_BUTTON_COLOR, fg='white', bd=borderwidth)
        stb = Tix.Balloon(self.root, statusbar=self.statusbar)
        stb.bind_widget(stop_btn, balloonmsg='Stop a program.',
           statusmsg='Press this button to stop program emulation.')
        stop_btn.pack(side=RIGHT)          
        
        go_btn = Tix.Button(buttonframe, text='Go', command= self.go_cmd)
        go_btn.config(bg=GO_BUTTON_COLOR, fg='white', bd=borderwidth)
        gb = Tix.Balloon(self.root, statusbar=self.statusbar)
        gb.bind_widget(go_btn, balloonmsg='Start a program.',
           statusmsg='Press this button to go.')
        go_btn.pack(side=RIGHT)         
        
        load_btn = Tix.Button(buttonframe, text='Load', command= self.load_cmd)
        load_btn.config(bg=LOAD_BUTTON_COLOR, fg='white', bd=borderwidth)
        lb = Tix.Balloon(self.root, statusbar=self.statusbar)
        lb.bind_widget(load_btn, balloonmsg='Load a program.',
           statusmsg='Press this button to select a program to load or reload.')
        load_btn.pack(side=RIGHT)        

        # Right hand pane
        
        # Registers. 
        wreg = Tix.Frame(preg, bd=2, relief=FLAT)
        wreg.pack(expand=1, fill=Tix.BOTH, padx=0, pady=0) 
        msg2 = Label(wreg, 
                    relief=Tix.FLAT,  anchor=Tix.N,
                    text='Registers')
        msg2.config(bg=PANE_LABEL_COLOR, fg=LABEL_FG_COLOR, bd=3)
        msg2.pack(side=TOP, fill=X)
        win2 = Text(wreg, height=40)
        win2.config(foreground=FG_COLOR, background=BG_COLOR)
        win2['wrap'] = 'none'
        win2.insert(Tix.END, dbg.show_regs())
        win2.pack(expand=1, fill=Tix.BOTH, padx=0, pady=0)
        self.reg_widget = win2
        
        # Command log.
        wlog = Tix.Frame(plog, bd=2, relief=FLAT)
        wlog.pack(expand=1, fill=Tix.BOTH, padx=0, pady=0) 
        msg3 = Label(wlog, 
                    relief=Tix.FLAT,  anchor=Tix.N,
                    text='Log')
        msg3.config(bg=PANE_LABEL_COLOR, fg=LABEL_FG_COLOR, bd=3)
        msg3.pack(side=TOP, fill=X)
   
        
        win3 = Tix.ScrolledText(wlog,  scrollbar='auto', height=400)
        win3.text['wrap'] = 'none'
        win3.text.insert(Tix.END, 'A log of results\n')
        win3.text.config(foreground=FG_COLOR, background=BG_COLOR)
        
        win3.pack(side=BOTTOM, expand=1, fill=Tix.BOTH, padx=0, pady=0)
        self.log_widget = win3
        # pass the widget into logging
        logging.enable_gui_logging(self.log_widget)
        
        # Command entry. 
        went = Frame(pent, bd=2, relief=FLAT)
        went.pack(expand=1, fill=Tix.BOTH, side = BOTTOM, padx=0, pady=0) 
        msg4 = Label(went, 
                    relief=Tix.FLAT,  anchor=Tix.N,
                    text='Enter commands here')
        msg4.config(bg=PANE_LABEL_COLOR, fg=LABEL_FG_COLOR, bd=3)
        msg4.pack(side=TOP, fill=X)
        m4b = Tix.Balloon(self.root, statusbar=self.statusbar)
        m4b.bind_widget(msg4, balloonmsg='Enter command line commands.',
                statusmsg='Enter commands, h for help.') 
        self.cmd_entryPrompt = StringVar()
        win4 = Entry(went, textvariable=self.cmd_entryPrompt)
        win4.bind('<Return>', self.command_entry)
        #win4.bind("<Key>", self.key)
        win4.bind("<Button-1>", self.callback) #self.command_entry)
       
        self.cmd_entryPrompt.set(DEFAULT_PROMPT)
        self.cmd_prompt_len = len(DEFAULT_PROMPT)
        self.cmd_entry = win4
        win4.pack(side = BOTTOM, expand=1, fill=Tix.BOTH, padx=0, pady=0)
        win4.config(foreground=FG_COLOR, background=BG_COLOR)

        pane.pack(side=Tix.TOP, padx=0, pady=0, fill=Tix.BOTH, expand=1)

        return w
       
    
    def highlight(self, line, color):
        """ Highlight a line of memory """
        tag_name = "line{:d}".format(int(line))
        tag_start = "{:d}.0".format(int(line))
        tag_end =   "{:d}.end".format(int(line))         
        self.text_widget.text.tag_add(tag_name, tag_start, tag_end)
        self.text_widget.text.tag_config(tag_name, foreground = color)
        self.text_widget.text.see(line+1.0)
        
    def get_line(self, addr):
        """ In the memory display, convert an address to a text line 
            (starts at 1.0)
        """
        lines = self.text_widget.text.get(1.0, END)
        lines = lines.splitlines(keepends=False)
        looking_for = "{:08x}".format(addr&address_mask)
        for line in range(len(lines)):
            if lines[line][0:8] == looking_for:
                return line+1.0
            
        return 0
    
    def get_addr(self, line):
        """ In the memory display, convert an address to a text line 
            (starts at 1.0)
        """
        ln = float(line)
        lines = self.text_widget.text.get(ln, ln+1.0)
        addr_lit = lines[0:8]
        if addr_lit[0] != '0': return None
        addr = int(lines[0:8], 16)
        return addr   
    
    
    def is_loaded(self):
        """ Has a program been loaded. """
        if dbg.cpu is not None:
            if dbg.cpu.loaded:
                return True
            
        log_cmd("Load program first.")
        return  False       
  
    
    def quit_cmd (self):
        """Quit our mainloop. It is up to you to call root.destroy() after."""
        self.exit = 0
        
    def prompt(self, prompt_string):
        print(prompt_string)  # temp until fixed
        self.cmd_entryPrompt.set(prompt_string)
        self.cmd_prompt_len = len(prompt_string)
        self.answer_expected = True
        self.cmd_entry.update()
        
    
        
    def go_cmd(self, args = None):
        """ Let the program run with no intervention. 
            Limited to 200 instructions unless command line override (g count). 
        """

        MAX_INSTRS = '200'
        global keep_running
        
        if not self.is_loaded(): return
        
        if args is None:
            args = [MAX_INSTRS]
        else:
            args.insert(0,'g')
        cnt = len(args)
        if False:
            dbg.go_cmd('g', cnt, args) 
            return
        else:
            if cnt == 1:
                self.current_address = dbg.cpu.pc
                instr_count = int(MAX_INSTRS)
            elif cnt >= 2:
                try:
                    instr_count = int(args[1])
                except ValueError:
                    log("Expected a decimal count - g count [from_address]") 
                    return
            if cnt == 2:
                self.current_address = dbg.cpu.pc  
            elif cnt >= 3:
                try:
                    from_address = int(args[2], base=16)       
                except ValueError:
                    log("Expected a hexadecimal address - g count [from_address]")
                    return   
                self.current_address = dbg.cpu.pc = from_address        
  
            log_cmd("Going from {:08x}".format(self.current_address))
       
            try:
                keep_running = True
                while keep_running:
                    for i in range(instr_count):
                        self.stepi_cmd()
                        program_counter = self.current_address & address_mask
                        if program_counter in dbg.cpu.breaks:
                            log("Breakpoint hit at {:08x}".format(program_counter))
                            return
                    if messagebox.askquestion ("g {:d} {:x} command".format(
                                            instr_count, self.current_address), 
                        "{:d} instructions executed\nContinue?".format(
                                                        instr_count)) == 'no':
                        return                    
                        
            except:
                log("Caught exception")
                raise
              
            keep_running = False
            
        
    def stop_cmd(self, dummy=None):
        """ Only any use to stop the go command. Currently it will stop in 
            MAX_INSTRS instructions anyway.
        """
        global keep_running
        if not self.is_loaded(): return  
        keep_running = False

    def stepi_cmd(self, dummy=None):
        """ Step instruction command. """
        global line
        if not self.is_loaded(): return
        line = self.get_line(dbg.cpu.pc)
        if  dbg.cpu.pc in dbg.cpu.breaks:
            self.highlight(line, BREAK_COLOR)
        else:
            self.highlight(line, FG_COLOR)
        
        self.current_address = dbg.cpu.stepi()
        SText_reset(self.reg_widget, dbg.show_regs())
        
        line = self.get_line(self.current_address)
        self.highlight(line, PC_COLOR)
        
    def stepo_cmd(self, dummy=None):
        """ Step over command. Puts a break after a bl and runs to it, 
            removing the break. """ 
        global line
        if not self.is_loaded(): return
        line = self.get_line(dbg.cpu.pc)
        if  dbg.cpu.pc in dbg.cpu.breaks:
            self.highlight(line, BREAK_COLOR)
        else:
            self.highlight(line, FG_COLOR)
        
        self.current_address = dbg.cpu.stepo()
        SText_reset(self.reg_widget, dbg.show_regs())
        
        line = self.get_line(self.current_address)
        self.highlight(line, PC_COLOR)

    def list_breaks_cmd(self, dummy=None):
        """ Lists breaks set. """
        if not self.is_loaded(): return  
        dbg.cpu.list_breaks()
        
    def get_address_arg(self, addr):
        got_addr = False
        if addr is not None:
            if isinstance(addr, list):
                if len(addr) > 0:
                    break_address = int(addr[0], 16)
                    got_addr = True  
            else:
                break_address = int(addr, 16)
                got_addr = True
        if not got_addr and self.current_selection is not None:
            break_address = self.current_selection
            got_addr = True

        if got_addr:
            return break_address
        else:
            return  None        

        
    def break_cmd(self, addr=None):
        """ Set a breakpoint. """
        # Needs selection
        if not self.is_loaded(): return 
        break_address = self.get_address_arg(addr)
        if break_address is None:
            return
        
        log("Set break at {:08x}".format(break_address))
        dbg.cpu.set_break(break_address)
        line = self.get_line(break_address)
        self.highlight(line, BREAK_COLOR)   
            
    def clear_break_cmd(self, addr=None):
        """ Clear a breakpoint. """
        if not self.is_loaded(): return 
        break_address = self.get_address_arg(addr)
        if break_address is None:
            return
        log("Clear break at {:08x}".format(break_address))
        if dbg.cpu.clear_break(break_address):
            line = self.get_line(break_address)
            self.highlight(line, FG_COLOR) 
        
    def fp_reg_display_cmd(self, args):
        """ Display one floating point register. """
        if not self.is_loaded(): return
        args.insert(0,'fr')
        cnt = len(args)
        dbg.fp_reg_display_cmd('fr', cnt, args)            
        
    def show_fp_regs_cmd(self, args):
        """ Display all floating point registers. """
        if not self.is_loaded(): return
        args.insert(0,'freg')
        cnt = len(args)
        dbg.show_fp_regs_cmd('freg', cnt, args)   
        
    def write_cmd(self, args):
        """ Write to memory, a register or a floating point register """
        if not self.is_loaded(): return
        args.insert(0,'w')
        cnt = len(args)
        dbg.write_cmd('w', cnt, args) 
        SText_reset(self.reg_widget, dbg.show_regs())
        
    def load(self, filename): 
        """ From the command line or from the button once the filename 
            is known.
        """
        if machine == "ARM":
            dbg.cpu = ArmCpu(filename)
        elif machine == "msp430":
            dbg.cpu = MSP430Cpu(filename)
            
        dbg.load_cmd("l", 2, ["l", filename])
            
        if self.text_widget is not None:
            if self.current_dump is not None:
                set_rb_mode()
            line = self.get_line(dbg.cpu.pc)
            self.highlight(line, PC_COLOR)            
        if self.reg_widget is not None:
            SText_reset(self.reg_widget, dbg.show_regs())
            
    def load_cmd(self, dummy=None):
        """ From the menu or the load button. """
        global line
        line = 1.0
        myfiletypes = [('elf, img and out files', '*.elf;*.img;*.out')]
        # default is all file types
        filename = askopenfilename(filetypes = myfiletypes) 
        #print("Open file is "+filename)
        self.filename = filename
        
        self.load(filename)

    def help_cmd(self, dummy=None):
        """ Command line help. """
        for line in dbg.help_lines:
            log(line)

    def dump_cmd(self,  args):
        """ Dump command. d hex_address1 hex_address2. """
        args.insert(0,'d')
        cnt = len(args)
        dbg.dump_cmd('d', cnt, args)
        
    def dumpx_cmd(self,  args):
        """ Dump command. dx hex_address1 hex_address2. """
        args.insert(0,'dx')
        cnt = len(args)
        dbg.dump_hex_cmd('dx', cnt, args)    

    def dumpx2_cmd(self,  args):
        """ Dump command. dx2 hex_address1 hex_address2. """
        args.insert(0,'dx2')
        cnt = len(args)
        dbg.dump_hex2_cmd('dx2', cnt, args) 
        
    def show_mem_cmd(self,  args):
        """ Internal command to show emulated memory chunks. """
        args.insert(0,'m')
        cnt = len(args)
        dbg.show_mem('m', cnt, args) 
        
    def call_stack_cmd(self,  args):
        """ cs command to show call stack. """
        args.insert(0,'cs')
        cnt = len(args)
        dbg.call_stack_cmd('cs', cnt, args)  
        
    def  script_cmd(self,  args):
        """ < command to read a script. """
        log("Scripting from GUI doesn't work right now")
        log("Use the command line debugger, dbg")
        args.insert(0,'<')
        cnt = len(args)
        dbg.script_cmd('<', cnt, args) 
        
    def  log_cmd(self,  args):
        """ > command to divert logging to a file. """
        args.insert(0,'>')
        cnt = len(args)
        dbg.log_cmd('>', cnt, args)     

    def pass_cmd(self, command):
        """ Pass through commands from the command line. """
        pass_cmds = {"g":self.go_cmd,    "h":self.help_cmd, "l":self.load_cmd,
                     "s":self.stepi_cmd, "o":self.stepo_cmd, 
                     "b":self.break_cmd, "c":self.clear_break_cmd, 
                     "cs":self.call_stack_cmd,
                     "d":self.dump_cmd,    "dx":self.dumpx_cmd,
                     "dx2":self.dumpx2_cmd, 
                     "m":self.show_mem_cmd,
                     "reg":dbg.show_regs,         "r":dbg.show_regs,
                     "freg":self.show_fp_regs_cmd,"fr":self.fp_reg_display_cmd,
                     "?":self.list_breaks_cmd,    "w":self.write_cmd, 
                     "<":self.script_cmd,         ">":self.log_cmd
                    }            
        cmd = command.strip()
        if len(cmd) == 0: return
        if cmd[0] == "q":
            self.quit_cmd()
        args = cmd.split()   # best not to use space sep or you get extra space args 

        if args[0] in dbg.cmds:
            if dbg.cpu is None:
                if args[0][0] == 'l':
                    if len(args) > 1:
                        filename= args[1]
                    else:
                        log("No filename supplied, using " + KERNEL_IMAGE)
                        filename = KERNEL_IMAGE
                    if file_is_loadable(filename):
                        self.filename = filename
                        self.load(filename)
                        return
                    
            if args[0][0] != 'r': 
                try:
                    pass_cmds[args[0]](args[1:]) 
                except KeyError:
                    # this one only happens when the pass_cmds don't match the dbg.cmds
                    log("Unsupported command.\n Try one of " + 
                     str(list(pass_cmds.keys()))) 
                    
            else:
                pass_cmds[args[0]]()  # r or reg
  
        else:
            log("Unsupported command.\n Try one of " + 
                     str(list(pass_cmds.keys())))        

            
    def getdumpfile(self):
        return self.filename
    
    def loop(self):
        """ The main loop. """
        import tkinter.messagebox, traceback
        while self.exit < 0:
            try:
                #while self.exit < 0:
                self.root.tk.dooneevent(TCL_ALL_EVENTS)
            except SystemExit:
                #print 'Exit'
                self.exit = 1
                break
            except KeyboardInterrupt:
                if messagebox.askquestion ('Interrupt', 'Really Quit?') == 'yes':
                    # self.tk.eval('exit')
                    return
                else:
                    pass
                continue
            except:
                t, v, tb = sys.exc_info()
                text = ""
                for line in traceback.format_exception(t,v,tb):
                    text += line + '\n'
                try: messagebox.showerror ('Error', text)
                except: pass
                # from tixwidgets.py example
                #tkinspect_quit (1)
                
                
    def key(self, event):
        """ Handle Function key commands and escape key. """
        if event.keysym == 'Escape':
            # Currently in the debug i/o window 
            if messagebox.askquestion ('Pressed Esc', 'Really Quit?') == 'yes':
                self.quit_cmd()
        elif event.keysym == 'F4':
            self.stop_cmd()                
        elif event.keysym == 'F5':
            self.go_cmd()
        elif event.keysym == 'F6':
            self.stepi_cmd()
        elif event.keysym == 'F7':
            self.stepo_cmd()        
        elif event.keysym == 'F9':
            self.break_cmd()
        elif event.keysym == 'F10':
            self.clear_break_cmd()
        elif event.keysym == 'Control_L':            
            self.doCopy()
            
        #elif (event.keycode == <Print>):  #doesn't work
            #print("Print")
        else:
            #print ("pressed", repr(event.keysym))
            #print ("pressed", repr(event.keycode))
            self.cmd_line_put(event.keysym)
            
    def copy(self, event=None):
        """ Need to copy from a text widget? """
        widget = self.text_widget.focus_get()
        if isinstance(widget, Text):        
            widget.clipboard_clear()
            text = widget.get("sel.first", "sel.last")
            widget.clipboard_append(text)
            
    def doCopy (self, evt=None):
        widget = self.text_widget.focus_get()
        if isinstance(widget, Entry):
            if widget.selection_present():
                widget.clipboard_clear()
                widget.clipboard_append(widget.selection_get())
        else:
            # works for Text, not for Entry (why?); fails quietly
            widget.tk.call('tk_textCopy', widget._w)    
    
    def doSelectAll(self, evt=None):
        widget = self.text_widget.focus_get()
        if isinstance(widget, Text):
            # the following commented-out code fails on MacPython
            # because the tk commands themselves aren't recognized;
            # hence I am not sure if the code is correct
            print ("Cannot yet 'Select All' in Text widgets")
            widget.tk.call('tk_textResetAnchor', widget._w, "1.0")
            #widget.tk_textResetAnchor("1.0")
            widget.tk_textSelectTo(END)
        elif isinstance(widget, Entry):
            widget.selection_range(0, END)
            #widget.selectForeground = BREAK_COLOR  #doesn't work
            widget.icursor(0)  
    
    def callback(self, event):
        self.root.focus_set()
        #print ("clicked in root at", event.x, event.y)
        #print("index = @{:d},{:d}".format(event.x, event.y))
        #index = "@{:d},{:d}".format(event.x, event.y)
        #if self.text_widget != None:
        #    print(self.text_widget.text.index(index))
            
    def text_callback(self, event):
        self.root.focus_set()
        #print ("clicked in text at", event.x, event.y)
        if not self.is_loaded(): return
        
        #print("index = @{:d},{:d}".format(event.x, event.y))
        index = "@{:d},{:d}".format(event.x, event.y)
        if self.text_widget is not None:
            index = self.text_widget.text.index(index)
            #print(index)
            line= index.split(".")
            l = str(line[0])+".0"
            #print(l)
            addr = self.get_addr(l)
            if addr is not None:
                self.current_selection = addr
            
    def command_entry(self, event):
        """ Command line entry in the GUI. Bottom right. """

        if self.cmd_entry is None:
            return
        self.cmd_entry.focus_set()        
        cmd = self.cmd_entry.get()
        command = cmd[self.cmd_prompt_len:]
        self.cmd_entry.delete(self.cmd_prompt_len, END)
        if self.answer_expected:
            print("response: " + command)
            self.answer = command
        else:
            print("Command is <"+command+">")
            self.pass_cmd(command)

        
    def cmd_line_put(self, keysym):
        if self.cmd_entry is None:
            return
        self.cmd_entry.focus_set() 
        self.cmd_entry.insert(END, keysym)
        
        pass
        


    def destroy (self):
        self.root.destroy() 
        
        
#-----------------------------------------------------------------------------



def ToggleHelp():  # doesn't work
    """ Toggle balloon help. """
    if dbgr.useBalloons.get() == '1':
        dbgr.balloon['state'] = 'both'
    else:
        dbgr.balloon['state'] = 'none'
        
def refresh_text():
    """ Replace highlights in text widget. """
    for addr in dbg.cpu.breaks:
        line=dbgr.get_line(addr)
        dbgr.highlight(line, BREAK_COLOR)
        
    line = dbgr.get_line(dbg.cpu.pc)
    dbgr.highlight(line, PC_COLOR)    



def make_tags(old_string, new_string, text_widget):
    """ Assuming the new string and the text widget are 
        substantially the same format 
    """
    lines = old_string.splitlines(keepends = False)
    new_lines=new_string.splitlines(keepends = False)
    here = 1.0
    tag_count = 0
    
    # the get routine appears to tack on an extra nl which causes an IndexError
    # if you compare using lengths

    leng = min(len(lines), len(new_lines))
    
    for i in range(leng):
        col = int(0)
        new_line = new_lines[int(here-1.0)]
        line = lines[i]
        if line != new_line:
            while col < len(line):
                while line[col] != ':':
                    col += 1
                    if col >= len(line): break
                col += 1   # now at the start of register contents
                if col >= len(line): break
                # 8 works for core regs reg_width but not for fp regs.
                ccol = col
                reg_width = 0
                if ccol < len(new_line):
                    while new_line[ccol] != ' ':
                        ccol+=1
                        reg_width += 1
                        if ccol >= len(new_line): break

                if line[col:col+reg_width] != new_line[col:col+reg_width]:
                    tag_count += 1
                    tag_start = "{:d}.{:02d}".format(int(here), col)
                    # What's the problem with 1.08 when we output 04x?
                    tag_end =   "{:d}.{:02d}".format(int(here), col+reg_width)   
                    tag_name = "tag{:d}".format(tag_count)
                    text_widget.tag_add(tag_name,
                                        tag_start, 
                                        tag_end)
                    #print("{:s} from {:s} to {:s}".format(tag_name, tag_start,
                    #                                      tag_end))
                    text_widget.tag_config(tag_name, foreground=REG_DIFF_COLOR)
                    #print(text_widget.dump(1.0, END, tag=True))
                col += reg_width
                if col >= len(line): break
        here += 1.0


def SText_reset(win, the_text):
    global dbgr
    if the_text == "": return
    if win is None: return
    if win == dbgr.reg_widget:
        w = win   # not scrolled
        old_contents = w.get(1.0, END)
    else:
        w = win.text  # is scrolled

    win.pack(side=Tix.TOP, expand=1, fill=Tix.BOTH)
    w.delete('1.0',END)
    w.insert('1.0', the_text)
    w.config(fg = FG_COLOR)
    if win == dbgr.text_widget:
        refresh_text()

    if win == dbgr.reg_widget:
        make_tags(old_contents, the_text, w)
        
    win.update()
   
   
def set_rb_mode():
    global dbgr
    mode = str(dbgr.which_display.get())
    file = dbgr.getdumpfile()
    if mode =="HA": 
        dbgr.current_dump = dump(file)
    elif mode == "OD":
        dbgr.current_dump = dumpelf(file)
    elif mode == "DA":
        dbgr.current_dump = disassemble("")
    if dbgr.text_widget is not None:
        SText_reset(dbgr.text_widget, dbgr.current_dump)
    # and change the header
    if dbgr.left_pane_label is not None:
        for mode_text, mode_code in MODES:
            if mode_code == mode:
                dbgr.left_pane_label['text'] = mode_text
                if file != "":
                    dbgr.left_pane_label['text'] += ' of <' + file + '>'
                
                return
        
        
def references():
    """ Help Menu entry. Architecture document references. """
    messagebox.showinfo(
        machine + " References", Doc.get("REF_DESCRIPTION"))    
    

def acknowledgements():
    """ Help Menu entry. Other peoples' software.. """
    messagebox.showinfo(
        "Acknowledgements",  Doc.get("ACKNOWLEDGEMENTS"))
        
def about_display():
    """ Help Menu entry. """
    messagebox.showinfo(
        "About " + machine + " Emulator", Doc.get("DESCRIPTION"))
    
def about_instructions():
    """ Help Menu entry. """
    messagebox.showinfo(
        machine + " Instructions", Doc.get("INSTRUCTIONS"))
    
def about_memory():
    """ Help Menu entry. """
    messagebox.showinfo(
        machine + " Memory Layout", Doc.get("MEMORY"))

       
def about_commands():
    """ Command line reference. """
    cmd = ""
    for line in dbg.help_lines:
        cmd += line+'\n'
    #cmd = cmd.replace('{}',' ')
    messagebox.showinfo("Line commands", cmd)   
    
#------------------------------------------------------------------------------
    
def RunMain(root):
    global dbgr

    dbgr = Dbgr(root)

    dbgr.build()
    dbgr.loop()
    dbgr.destroy()

if __name__ == '__main__':
    root = Tix.Tk()
    RunMain(root)
