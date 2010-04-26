#!/usr/bin/env python
"""
# Geoconv - Coordinate converter
# Copyright (c) 2009 Michael Buesch <mb@bu3sch.de>
# Licensed under the GNU/GPL version 2 or later.
"""

import sys

def usage():
	print "Usage: %s  00 00 00,  00 00.000,  00.000, ..." % sys.argv[0]

def main(argv):
	args = " ".join(argv[1:])
	args = args.split(',')

	if not args:
		usage()
		return 1
	for arg in args:
		arg = arg.replace('N', '')
		arg = arg.replace('E', '')
		arg = arg.replace('O', '')
		arg = arg.replace('*', '')
		arg = arg.replace('\'', '')
		arg = arg.replace('\"', '')
		try:
			# Parse the input value and convert to fractional degrees
			values = arg.split()
			if len(values) == 0:
				print "" # empty line
				continue
			elif len(values) == 3:
				# 00 00 00		(degree, minutes, seconds)
				degree = float(values[0])
				minutes = float(values[1])
				seconds = float(values[2])
				degree = degree + (minutes / 60) + (seconds / 3600)
			elif len(values) == 2:
				# 00 00.000		(degree, fractional minutes)
				degree = float(values[0])
				minutes = float(values[1])
				degree = degree + (minutes / 60)
			elif len(values) == 1:
				# 00.000		(factional degrees)
				degree = float(values[0])
			else:
				usage()
				return 1
		except ValueError:
			usage()
			return 1
		# Print the result in various formats
		minutes = (degree - int(degree)) * 60
		seconds = (minutes - int(minutes)) * 60
		print "%08.4f*    %03.0f* %06.3f\'    %03.0f* %02.0f\' %02.0f\"" %\
			(degree,
			 float(int(degree)), minutes,
			 float(int(degree)), float(int(minutes)), seconds)
	return 0

if __name__ == "__main__":
	sys.exit(main(sys.argv))

# vim: ts=4
