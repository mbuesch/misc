#!/usr/bin/env pypy3
#
# Permission to use, copy, modify, and/or distribute this software for
# any purpose with or without fee is hereby granted.
#
# THE SOFTWARE IS PROVIDED “AS IS” AND THE AUTHOR DISCLAIMS ALL
# WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES
# OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE
# FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY
# DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN
# AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT
# OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#

import argparse
from math import ceil, sqrt

def isprime(n):
    if (not n % 2 and n != 2) or (not n % 3 and n != 3):
        return False
    for i in range(5, int(ceil(sqrt(n)) + 0.5) + 1, 6):
        if not n % i or not n % (i + 2):
            return False
    return True if n >= 2 else False

def nextprime(n, prev):
    if prev and n < 2:
        raise Exception("Error: Number is less than 2.")
    n = max(n, 2)
    if n == 2:
        return n
    if isprime(n):
        return n
    if n % 2 == 0:
        n += -1 if prev else 1
    while True:
        if isprime(n):
            return n
        n += -2 if prev else 2

if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Find the next (or previous) prime number, given a start number.")
    p.add_argument("-p", "--prev", action="store_true",
                   help="Find the previous prime instead of the next prime.")
    p.add_argument("number", type=int)
    args = p.parse_args()
    print(nextprime(args.number, args.prev))

# vim: ts=4 sw=4 expandtab
