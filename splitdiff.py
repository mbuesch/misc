#!/usr/bin/env python

import sys
import getopt


prefix = 1
inPreamble = True
inPatch = False
lineNr = 0
fileNr = 0
fd = None

def die(msg=None):
	if msg:
		sys.stderr.write(msg + "\n")
	sys.exit(1)

def out(data):
	fd.write(data)

try:
	(opts, args) = getopt.getopt(sys.argv[1:], "p:")
except getopt.GetoptError:
	usage()
	die()
for (o, v) in opts:
	if o in ("-p",):
		try:
			prefix = int(v)
			if prefix < 0:
				raise ValueError
		except ValueError:
			die("Invalid -p")

while 1:
	line = sys.stdin.readline()
	if not line:
		break
	lineNr += 1
	if line.startswith("diff ") or \
	   line.startswith("--- ") or \
	   line.startswith("+++ "):
		if inPreamble or inPatch:
			path = line.strip().split(" ")[-1]
			path = path.split("/")
			if len(path) <= prefix:
				die("Could not strip all prefix")
			path = path[prefix:]
			filename = "-".join(path)
			filename = "%03d-%s.diff" % (fileNr, filename)
			fileNr += 1
			if fd:
				fd.close()
			fd = file(filename, "w")
			out(line)
			inPreamble = False
			inPatch = False
			continue
		else:
			out(line)
			continue
	if line.startswith("index "):
		if not inPreamble:
			out(line)
		continue
	if line.startswith("\\ No newline at end of file") or \
	   line.startswith("old mode") or \
	   line.startswith("new mode") or \
	   line.startswith("new file mode ") or \
	   line.startswith("deleted file mode ") or \
	   line.startswith("+") or \
	   line.startswith("-") or \
	   line.startswith(" ") or \
	   line.startswith("@@ "):
		if not inPreamble:
			inPatch = True
			out(line)
		continue
	if not inPreamble:
		die("Parse error in line %d" % lineNr)

sys.exit(0)
