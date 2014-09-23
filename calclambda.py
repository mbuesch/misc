#!/usr/bin/env python

import sys


try:
	factor = 0.97
	lowerMhz = float(sys.argv[1])
	upperMhz = float(sys.argv[2])
	if len(sys.argv) >= 4:
		factor = float(sys.argv[3])
except (IndexError, ValueError), e:
	print "Usage: %s LOWERMHZ UPPERMHZ [FACTOR]" % sys.argv[0]
	sys.exit(1)

centerMhz = (upperMhz - lowerMhz) / 2 + lowerMhz
centerHz = centerMhz * 1000000
c = 299792458 # m/sec

lambd = (float(c) / centerHz) * factor
lambd4 = lambd / 4
lambd4mm = lambd4 * 1000

print "%.1f < %.1f < %.1f  (* %.2f)   ==>   lambda/4 = %.1f mm" %\
	(lowerMhz, centerMhz, upperMhz, factor, lambd4mm)
