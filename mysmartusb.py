#!/usr/bin/env python3
"""
#  Copyright (C) 2012-2013 Michael Buesch <m@bues.ch>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License version 3
#  as published by the Free Software Foundation.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import sys
import getopt
try:
	from serial.serialposix import *
except ImportError:
	print("ERROR: pyserial module not available.")
	print("On Debian Linux please do:  apt-get install python3-serial")
	sys.exit(1)


def str2bool(string):
	if string.lower() in ("true", "on", "yes"):
		return True
	if string.lower() in ("false", "off", "no"):
		return False
	try:
		return bool(int(string))
	except ValueError as e:
		pass
	return False

def hexdump(data):
	ret = []
	for c in data:
		ret.append("%02X" % c)
	return "".join(ret)

class MySmartUsbError(Exception): pass

class MySmartUsb(object):
	PREFIX		= b"\xE6\xB5\xBA\xB9\xB2\xB3\xA9"

	MODE_PROG	= b'p'
	MODE_DATA	= b'd'
	MODE_QUIET	= b'q'

	def __init__(self, ttyDev, debug=False):
		self.debug = debug
		self.serial = Serial(ttyDev, 19200, 8, PARITY_NONE, 1)
		self.serial.flushInput()
		self.serial.flushOutput()

	def resetBoard(self):
		self.__sendCmd(b'r')

	def resetProg(self):
		self.__sendCmd(b'R')

	def power(self, on):
		self.__sendCmd(b'+' if on else b'-')

	def setMode(self, mode):
		self.__sendCmd(mode)

	def getStatus(self):
		self.__sendCmd(b'i')

	def close(self):
		self.serial.close()

	def __sendCmd(self, cmd):
		data = self.PREFIX + cmd
		if self.debug:
			print("Sending command: " + hexdump(data))
		self.serial.write(data)
		if cmd == b'R':
			return
		ret = self.serial.read(1)
		if ret == b"\x00" or ret == b"\x0D":
			ret = self.serial.read(5)
		else:
			ret += self.serial.read(4)
		if self.debug:
			print("Command returned: " + hexdump(ret))
		if ret[0:2] != b"\xF7\xB1":
			raise MySmartUsbError(
				"Invalid command return prefix: %02X%02X" %\
				(ret[0], ret[1]))
		if cmd != b'i' and ret[2] != ord(cmd):
			raise MySmartUsbError(
				"Invalid command return: %02X" %\
				(ret[2]))
		if ret[3:5] != b"\x0D\x0A":
			raise MySmartUsbError(
				"Invalid command return postfix: %02X%02X" %\
				(ret[3], ret[4]))

def usage():
	print("mysmartusb [OPTIONS] /dev/ttyUSBx")
	print("")
	print("Options:")
	print(" -r|--reset-board         Reset the board")
	print(" -R|--reset-prog          Reset the programmer")
	print(" -p|--power 1/0           Turn on board power on/off")
	print(" -m|--mode p/d/q          Enter progmode/datamode/quietmode")
	print("")
	print(" -D|--debug               Enable debugging")

def main():
	actions = []
	debug = False
	try:
		(opts, args) = getopt.getopt(sys.argv[1:],
			"hrRp:m:D",
			[ "help", "reset-board", "reset-prog", "prog=",
			  "mode=", "debug", ])
	except getopt.GetoptError:
		usage()
		return 1
	for (o, v) in opts:
		if o in ("-h", "--help"):
			usage()
			return 0
		if o in ("-r", "--reset-board"):
			actions.append( ("reset-board",) )
		if o in ("-R", "--reset-prog"):
			actions.append( ("reset-prog",) )
		if o in ("-p", "--power"):
			actions.append( ("power", str2bool(v)) )
		if o in ("-m", "--mode"):
			if v.lower() == "p":
				mode = MySmartUsb.MODE_PROG
			elif v.lower() == "d":
				mode = MySmartUsb.MODE_DATA
			elif v.lower() == "q":
				mode = MySmartUsb.MODE_QUIET
			else:
				print("Invalid mode: " + v)
				return 1
			actions.append( ("mode", mode) )
		if o in ("-D", "--debug"):
			debug = True
	if len(args) != 1:
		usage()
		return 1
	dev = args[0]

	try:
		msu = MySmartUsb(dev, debug)

		for action in actions:
			if action[0] == "reset-board":
				msu.resetBoard()
			elif action[0] == "reset-prog":
				msu.resetProg()
			elif action[0] == "power":
				msu.power(action[1])
			elif action[0] == "mode":
				msu.setMode(action[1])
			else:
				assert(0)
		msu.close()
	except MySmartUsbError as e:
		print("ERROR: " + str(e))
		return 1
	return 0

if __name__ == "__main__":
	sys.exit(main())
