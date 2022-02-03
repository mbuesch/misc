#!/usr/bin/env python3
"""
 *   74HC4094 data sniffer
 *
 *   Copyright (C) 2010-2022 Michael Buesch <m@bues.ch>
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
	from serial import *
except ImportError:
	print("ERROR: pyserial module not available.", file=sys.stderr)
	print("On Debian Linux please do:  apt-get install python3-serial", file=sys.stderr)
	sys.exit(1)


# Serial port config
SERIAL_BAUDRATE		= 115200
SERIAL_BYTESIZE		= 8
SERIAL_PARITY		= PARITY_NONE
SERIAL_STOPBITS		= 1


class SnifferException(Exception):
	pass

class Sniffer:
	def __init__(self, tty, numShiftregs):
		try:
			self.serial = Serial(tty, SERIAL_BAUDRATE,
					     SERIAL_BYTESIZE, SERIAL_PARITY,
					     SERIAL_STOPBITS)
			self.size = numShiftregs
			self.reset()
		except (SerialException, OSError, IOError) as e:
			raise SnifferException(str(e))

	def reset(self):
		try:
			self.serial.read(self.serial.inWaiting())
			self.__doRead() # Discard result
		except (SerialException, OSError, IOError) as e:
			raise SnifferException(str(e))

	def __doRead(self):
		msg = b"%c" % self.size
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
		except (SerialException, OSError, IOError) as e:
			raise SnifferException(str(e))

def toAscii(char):
	assert(isinstance(char, int))
	if char >= 32 and char <= 126:
		return chr(char)
	return "."

def dumpMem(mem):
	assert(isinstance(mem, (bytes, bytearray)))
	ascii = ""
	for i in range(len(mem)):
		if i % 16 == 0 and i != 0:
			print("  " + ascii + "\n", end='')
			ascii = ""
		if i % 16 == 0:
			print("0x%04X:  " % i, end='')
		c = mem[i]
		print("%02X" % c, end='')
		if (i % 2 != 0):
			print(" ", end='')
		ascii += toAscii(c)
	print("  " + ascii + "\n")

def usage():
	print("Usage: %s TTY NUM_SHIFTREGS" % sys.argv[0], file=sys.stderr)

def main(argv):
	try:
		tty = argv[1]
		numShiftregs = int(argv[2])
	except (IndexError, ValueError) as e:
		usage()
		return 1
	try:
		s = Sniffer(tty, numShiftregs)
		data = s.read()
		dumpMem(data)
	except SnifferException as e:
		print(str(e), file=sys.stderr)
	return 0

if __name__ == "__main__":
	sys.exit(main(sys.argv))
