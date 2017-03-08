""" Logging of output for emulator. """
import sys
from tkinter import *
from tkinter import tix as Tix

#from utilities import check_for_diffs
#from utilities.check_for_diffs import *


logfd = 0
logging_on = False
gui_enabled = False
log_widget = None


def logging_enabled():
    return logging_on

def enable_gui_logging(logw):
    global gui_enabled, log_widget
    gui_enabled = True
    log_widget = logw
    
def log_cmd(win, the_text, end='\n'):
    if the_text == "": 
        return
    if win is None:
        return
    win.pack(side=Tix.TOP, expand=1, fill=Tix.BOTH)
    win.text.insert(END, the_text+end)
    win.text.see('end')
    win.update()    



def start_logging(logfile):
    global logfd, logging_on
    try:
        logfd = open(logfile, mode = "w", encoding = "utf-8")
        # don't know why but this doesn't open logfd
        #with  open(logfile, mode = "w", encoding = "utf-8") as logfd:
        logging_on = True 
        #print("Log file open", file=logfd)
    except IOError:
        print("Unable to open file <{:s}>".format(logfile))
        logging_on = False
    # checks! with open as logfd etc. is log file already open etc.

def stop_logging():
    global logfd, logging_on
    if logging_on:
        logfd.close()
    else:
        log("No log file open.")
    logging_on = False

def log(dbg_output,  end='\n', echo_cmd = True):
    global logfd, logging_on
    if logging_on:
        print(dbg_output, end=end, file=logfd)
    if echo_cmd:
        if gui_enabled:
            log_cmd(log_widget, dbg_output, end)
            return
        print(dbg_output, end=end)

"""
import myDialog

def prompt_for_value(str):
    if log_widget == None:
        print(str)
        valid_input = False
        while not valid_input:
            result = input()
            try:
                val = int(result, 16)
                valid_input = True
                log(result, end = "\n")
            except ValueError:
                log("\nInvalid hex number {:s}, try again".format(result))        
        return result
    else:
        #log_cmd(log_widget, str, end = "")
        #return 1
        res = myDialog(log_widget)
        return res.first  
"""

if __name__ == '__main__':
    logfd = open('out1.log', 'w')
    print("A string - no end",                  file = logfd)
    print("A string - end=''",        end='',   file = logfd)
    print("A string - end=' '",       end=' ',  file = logfd)
    print("A string - end='newline'", end='\n', file = logfd)
    print("A string",                           file = logfd)
    logfd.close()
    
    start_logging("out2.log")
    log("A string - no end")
    log("A string - end=''",        end='')
    log("A string - end=' '",       end=' ')
    log("A string - end='newline'", end='\n')
    log("A string")
    stop_logging()
    
    logfd = sys.stdout
    print("A string - no end",                   file = logfd)
    print("A string - end= '' ",       end='',   file = logfd)
    print("A string - end= ' ' ",      end=' ',  file = logfd)
    print("A string - end= 'newline' ",end='\n', file = logfd)
    print("A string",                            file = logfd)  
    
    print("")
    
    log("A string - no end")
    log("A string - end= '' ",       end='')
    log("A string - end= ' ' ",      end=' ')
    log("A string - end= 'newline' ",end='\n')
    log("A string")
    

    
    """
    diff out1.log out2.log

    """