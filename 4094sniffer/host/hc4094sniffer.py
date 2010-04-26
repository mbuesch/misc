#!/usr/bin/env python
"""
 *   74HC4094 data sniffer
 *
 *   Copyright (C) 2010 Michael Buesch <mb@bu3sch.de>
 *
 *   This program is free software; you can redistribute it and/or
 *   modify it under the terms of the GNU General Public License
 *   version 2 as published by the Free Software Foundation.
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *   GNU General Public License for more details.
"""

import getopt
import sys
import time
try:
	from serial.serialposix import *
except ImportError:
	print "ERROR: pyserial module not available."
	print "On Debian Linux please do:  apt-get install python-serial"
	sys.exit(1)


# Serial port config
SERIAL_BAUDRATE			= 115200
SERIAL_BYTESIZE			= 8
SERIAL_PARITY			= PARITY_NONE
SERIAL_STOPBITS			= 1


class SnifferException(Exception): pass

class Sniffer:
	def __init__(self, tty, shiftregSize):
		try:
			self.serial = Serial(tty, SERIAL_BAUDRATE,
					     SERIAL_BYTESIZE, SERIAL_PARITY,
					     SERIAL_STOPBITS)
			self.size = shiftregSize
			self.reset()
		except (SerialException, OSError, IOError), e:
			raise SnifferException(str(e))

	def reset(self):
		try:
			self.serial.read(self.serial.inWaiting())
			self.__doRead() # Discard result
		except (SerialException, OSError, IOError), e:
			raise SnifferException(str(e))

	def __doRead(self):
			msg = "%c" % self.size
			self.serial.write(msg)
			time.sleep(0.1)
			return self.serial.read(self.serial.inWaiting())

	def read(self):
		try:
			data = self.__doRead()
			if len(data) != self.size:
				raise SnifferException(
					"Unexpected data length. Is %d, expected %d" %\
					(len(data), self.size))
			return data
		except (SerialException, OSError, IOError), e:
			raise SnifferException(str(e))

def dumpMem(mem):
	def toAscii(char):
		if char >= 32 and char <= 126:
			return chr(char)
		return "."

	ascii = ""
	for i in range(0, len(mem)):
		if i % 16 == 0 and i != 0:
			sys.stdout.write("  " + ascii + "\n")
			ascii = ""
		if i % 16 == 0:
			sys.stdout.write("0x%04X:  " % i)
		c = ord(mem[i])
		sys.stdout.write("%02X" % c)
		if (i % 2 != 0):
			sys.stdout.write(" ")
		ascii += toAscii(c)
	sys.stdout.write("  " + ascii + "\n\n")

def usage():
	print "Usage: %s TTY SHIFTREG_SIZE" % sys.argv[0]

def main(argv):
	try:
		tty = argv[1]
		shiftregSize = int(argv[2])
	except (IndexError, ValueError), e:
		usage()
		sys.exit(1)

	try:
		s = Sniffer(tty, shiftregSize)
		data = s.read()
		dumpMem(data)
	except (SnifferException), e:
		print e.message

if __name__ == "__main__":
	sys.exit(main(sys.argv))
