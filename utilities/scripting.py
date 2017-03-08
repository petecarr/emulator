#from utilities import logging
#from utilities.logging import log
# replace print with log once I figure this out - put them in same file?

scriptfd = 0
scripting_on = False

def scripting_enabled():
    return scripting_on

def start_script(filename):
    global scriptfd, scripting_on
    try:
        scriptfd = open(filename, mode = "r", encoding = "utf-8")
        #with  open(filename, "r", encoding = "utf-8") as scriptfd:
        scripting_on = True       
        print("Reading commands from {:s}".format(filename))
    except FileNotFoundError:
        print("Script file <"+filename+"> not found." )
        scripting_on = False
    
def stop_scripting():
    global scriptfd, scripting_on
    if scripting_on:
        scriptfd.close()
    else:
        print ("Supply a script file name")
    scripting_on = False
    
def from_script():
    global scriptfd, scripting_on
    res = scriptfd.readline(80)
    if res == "":
        print("End of script file, closing")
        scripting_on = False
        scriptfd.close()
        return res
    if res[len(res)-1] == '\n':
        return res[0:len(res)-1]
        
    return res