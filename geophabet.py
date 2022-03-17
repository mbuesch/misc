#!/usr/bin/env python3
"""
# Convert words into numbers, geocaching-like
# Copyright (c) 2009-2022 Michael Buesch <m@bues.ch>
# Licensed under the
# GNU General Public license version 2 or (at your option) any later version
"""

import sys

def convertChar(c):
    c = ord(c)
    if c >= ord('a') and c <= ord('z'):
        base = ord('a')
    elif c >= ord('A') and c <= ord('Z'):
        base = ord('A')
    else:
        return "UNK" # unknown
    return c - base + 1

def convertString(string):
    string = string.replace(" ", "")
    res = ""
    for c in string:
        if res:
            res += ", "
        res += "%s=%s" % (c, str(convertChar(c)))
    return res

def main(argv):
    while 1:
        try:
            string = input("ABC> ")
        except (EOFError, KeyboardInterrupt):
            break
        if not string:
            break
        print(convertString(string))

if __name__ == "__main__":
    sys.exit(main(sys.argv))

# vim: ts=4 sw=4 expandtab
