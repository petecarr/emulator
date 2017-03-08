import os

def check_for_diffs(res, old_file, new_file, replace=False):
    """ Take a program output and look for differences from a previous run. """
    """ Replace the old output if required.  Else: delete the new file. """
    
    save_file = os.path.join(os.getcwd(),new_file)
    with open(save_file, "w") as sf:
        sf.write(res)
        sf.close()
    old_save_file = os.path.join(os.getcwd(), old_file)
    try:
        with open(old_save_file, "r") as osf:
            try:
                with open(save_file, "r") as sf:
                    line_number = 1
                    change_count = 0
                    line = osf.readline()
                    nline = sf.readline()
                    while line:
                        if line != nline:
                            print("Difference on line {:d}".format(line_number))
                            print("Old: " + line)
                            print("New: " + nline)
                            change_count += 1
                        line = osf.readline()
                        nline = sf.readline()
                        line_number +=1
            
                sf.close()
                if change_count == 0:
                    print("No changes")
                else:
                    print("{:d} changes".format(change_count))
            except FileNotFoundError:
                print("No new file to compare with " + save_file)
        osf.close() 
    except FileNotFoundError:
        print("No old file to compare with " + old_save_file) 
    
    if replace:    
        try:
            os.remove(old_save_file)
            
        except OSError:
            print("Unable to remove " + old_save_file)
    
        try:
            os.rename(save_file, old_save_file)
        except OSError:
            print("Unable to rename " + save_file + " to " + old_save_file)
    else:
        try:
            os.remove(save_file)
                    
        except OSError:
            print("Unable to remove " + save_file)        