#!/usr/bin/env python
"""
# rotate - Copyright (c) 2009 Michael Buesch <mb@bu3sch.de>
# Licensed under the
# GNU General Public license version 2 or (at your option) any later version
"""

import sys
import getopt


def rotateChar(c, count):
		count %= 26
		c = ord(c)
		if c >= ord('a') and c <= ord('z'):
			start = ord('a')
			end = ord('z')
		elif c >= ord('A') and c <= ord('Z'):
			start = ord('A')
			end = ord('Z')
		else: # Do not rotate
			return chr(c)
		c += count
		if (c < start):
			c = end - (start - c - 1)
		elif (c > end):
			c = start + (c - end - 1)
		assert(c >= start and c <= end)
		return chr(c)

def rotateString(string, count):
	s = ""
	for c in string:
		s += rotateChar(c, count)
	return s

def test():
	count = 0
	for i in range(-100, 101):
		s = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ123456789!@#$%^&*()_+|~"
		if (rotateString(rotateString(s, i), -i) != s):
			print "Selftest FAILED at", i
			return 1
		count += 1
	print count, "selftests passed"
	return 0

def usage():
	print "Usage: %s [OPTIONS]" % sys.argv[0]
	print ""
	print "-h|--help           Print this help text"
	print "-c|--count COUNT    Rotate by COUNT"
	print "-s|--string STR     Rotate STR (no prompt)"
	print "-f|--file FILE      Rotate the contents of FILE"

def main(argv):
	opt_count = 13
	opt_string = None
	opt_file = None

	try:
		(opts, args) = getopt.getopt(argv[1:],
			"hc:s:f:t",
			[ "help", "count=", "string=", "test", ])
		for (o, v) in opts:
			if o in ("-h", "--help"):
				usage()
				return 0
			if o in ("-c", "--count"):
				opt_count = int(v)
			if o in ("-s", "--string"):
				opt_string = v
			if o in ("-f", "--file"):
				opt_file = v
			if o in ("-t", "--test"):
				return test()
	except (getopt.GetoptError, ValueError):
		usage()
		return 1

	if opt_file:
		try:
			data = file(opt_file, "r").read()
		except IOError, e:
			print "Failed to read file:", e.strerror
			return 1
		sys.stdout.write(rotateString(data, opt_count))
		return 0

	if opt_string:
		print rotateString(opt_string, opt_count)
	else:
		while 1:
			try:
				string = raw_input("rot> ")
			except (EOFError, KeyboardInterrupt):
				break
			if not string:
				break
			print rotateString(string, opt_count)

	return 0

if __name__ == "__main__":
	sys.exit(main(sys.argv))

# vim: ts=4
