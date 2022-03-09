#!/usr/bin/env python3
#
#  This code is Public Domain.
#  Permission to use, copy, modify, and/or distribute this software for any
#  purpose with or without fee is hereby granted.
#
#  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
#  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
#  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
#  SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER
#  RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
#  NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE
#  USE OR PERFORMANCE OF THIS SOFTWARE.

import pikepdf
import multiprocessing
import sys
import pathlib
from datetime import datetime, timedelta

class PwIteratorPLZ:
    def __init__(self):
        self.plz = 1000

    def __iter__(self):
        return self

    def __next__(self):
        plz = self.plz
        if plz >= 99999:
            raise StopIteration()
        self.plz += 1
        return f"{plz:05}"

class PwIteratorBirthday:
    def __init__(self):
        now = datetime.now()
        self.date = now
        self.enddate = now - timedelta(days=(120 * 365))

    def __iter__(self):
        return self

    def __next__(self):
        date = self.date
        if date <= self.enddate:
            raise StopIteration()
        self.date -= timedelta(days=1)
        return f"{date.day:02}.{date.month:02}.{date.year:04}"

def testit(password):
    try:
        with pikepdf.open(infile, password=password) as pdf:
            pdf.save(outfile)
        return password
    except pikepdf.PasswordError:
        return None
    assert False

infile = pathlib.Path(sys.argv[1])
outfile = infile.with_stem(infile.stem + ".DECRYPTED")

iterators = (
    PwIteratorBirthday,
    PwIteratorPLZ,
)

for iterator in iterators:
    with multiprocessing.Pool() as pool:
        for pw in pool.imap(testit, iterator(), 128):
            if pw is not None:
                pool.terminate()
                print(f"The PDF has been decrypted to: {outfile}")
                print(f"The password is: {pw}")
                sys.exit(0)
print("Password not found :(")
sys.exit(1)

# vim: ts=4 sw=4 expandtab
