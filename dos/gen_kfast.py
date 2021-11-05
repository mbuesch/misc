#!/usr/bin/env python3
#
# Generate KFAST.COM DOS executable
# to maximize keyboard repeat rate and
# to minimize keyboard repeat delay.
#

with open("KFAST.COM", "bw") as f:
    # mov ax, 0305h
    f.write(b"\xB8\x05\x03")
    # mov bx, auto_repeat
    bh = 0  # 0, 1, 2, 3 -> 1/4, 1/2, 3/4, or 1 s delay
    bl = 0  # 0 .. 0x1F -> 30/s .. 2/s rate
    f.write(b"\xBB%c%c" % (bl, bh))
    # int 16h
    f.write(b"\xCD\x16")
    # mov ah, 4ch
    f.write(b"\xB4\x4C")
    # int 21h
    f.write(b"\xCD\x21")

# vim: ts=4 sw=4 expandtab
