"""Set mapper address-space budget after exec has shed the large parent heap."""
import argparse
import os
import resource


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--address-space-bytes",type=int,required=True)
    p.add_argument("command",nargs=argparse.REMAINDER)
    a=p.parse_args();command=a.command
    if command and command[0]=="--":command=command[1:]
    if a.address_space_bytes<16*1024*1024 or not command:p.error("a positive bounded mapper command is required")
    resource.setrlimit(resource.RLIMIT_AS,(a.address_space_bytes,a.address_space_bytes))
    os.execvpe(command[0],command,os.environ)


if __name__=="__main__":main()
