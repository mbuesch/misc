#!/usr/bin/env python3
"""
#  Simple AVR disassembly postprocessor
#
#  Copyright (C) 2012 Michael Buesch <m@bues.ch>
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
import re
import getopt


LABEL_FMT = "L%04X"


def die(msg):
	sys.stderr.write(msg + "\n")
	sys.stderr.flush()
	sys.exit(1)

def generate_io_table(inc_file):
	# Parse the file and get the IO section
	in_io = False
	rawtab = []
	try:
		lines = open(inc_file, "r").readlines()
	except IOError as e:
		die("Failed to read INC-FILE '%s': %s" % (inc_file, str(e)))
	for line in lines:
		line = line.strip()
		if line.startswith("; ***** I/O REGISTER DEFINITIONS"):
			in_io = True
			continue
		if in_io:
			if line.startswith("; *****"):
				break # End of I/O section
			rawtab.append(line)
	r = re.compile(r"^\s*\.equ\s+(\w+)\s*=\s*(\w+)\s*$")
	tab = {}
	for raw in rawtab:
		m = r.match(raw)
		if not m:
			continue
		name, addr = m.group(1), m.group(2)
		if addr.startswith("0x"):
			addr = addr[2:]
		addr = int(m.group(2), 16)
		tab[addr] = name
	if not tab:
		die("Failed to parse INC-FILE")
	return tab

def ishex(s):
	for c in s:
		if c not in "0123456789abcdefABCDEF":
			return False
	return True

'''An AVR assembly instruction'''
class Insn:
	class StringErr(Exception): pass
	class StringIgnore(Exception): pass

	def __init__(self, insn_string):
		s = insn_string.split()
		if len(s) == 0 or s[0] == "...":
			raise Insn.StringIgnore()
		# Look for comments
		self.comment = None
		for i in range(0, len(s)):
			if s[i][0] != ";":
				continue
			try:
				self.comment = " ".join(s[i+1:])
			except IndexError as e:
				self.comment = ""
			if len(s[i]) > 1:
				self.comment = s[i][1:] + self.comment
			s = s[:i] # strip it off
			# Fix 0x0x breakage
			self.comment = self.comment.replace("0x0x", "0x")
			break
		if len(s) < 2:
			raise Insn.StringErr()
		# Remove opcodes
		while ishex(s[1]):
			s.pop(1)
		# Extract offset (2ab:)
		off = s[0]
		off = "0x" + off[:-1]
		self.offset = int(off, 16)
		# Extract insn string (jmp...)
		self.insn = s[1].lower()
		# Extract operands
		self.operands = []
		try:
			self.operands = s[2:]
		except IndexError as e: pass
		for i in range(0, len(self.operands)):
			# Strip commas from operands
			self.operands[i] = self.operands[i].replace(",", "")
			# Fix 0x0x breakage
			self.operands[i] = self.operands[i].replace("0x0x", "0x")
		self.callers = []
		self.jmpsources = []

	def get_full_string(self):
		'''Returns a full string of the instruction'''
		s = ""
		if self.callers:
			s += "\n; FUNCTION called by "
			i = 0
			for caller in self.callers:
				s += "0x%04X " % caller.get_offset()
				i += 1
				if i > 20:
					s += "\n; "
					i = 0
			s += "\n"
		s += (LABEL_FMT + ":\t%s\t") % (self.get_offset(), self.get_insn())
		first = True
		for o in self.get_operands():
			if not first:
				s += ", "
			first = False
			s += o
		comm = self.get_comment()
		if comm:
			s += "\t\t;" + comm
		if self.jmpsources:
			s += "\t; JUMPTARGET from "
			for jmpsrc in self.jmpsources:
				s += "0x%04X " % jmpsrc.get_offset()
		return s

	def get_offset(self):
		return self.offset

	def get_insn(self):
		return self.insn

	def set_insn(self, insn):
		self.insn = insn

	def get_operands(self):
		return self.operands

	def get_comment(self):
		return self.comment

	def add_caller(self, insn):
		self.callers.append(insn)

	def add_jmpsource(self, insn):
		self.jmpsources.append(insn)

	def __rewrite_jmp_targets(self):
		if self.get_insn() != "jmp" and self.get_insn() != "call":
			return
		operands = self.get_operands()
		if (len(operands) != 1):
			print("Error: more than one JMP/CALL operand")
			exit(1)
		operands[0] = LABEL_FMT % int(operands[0], 0)

	def __rewrite_rjmp_targets(self):
		operlist = self.get_operands()
		r = re.compile(r"^\.([\+-][0-9]+)")
		for i in range(0, len(operlist)):
			m = r.match(operlist[i])
			if not m:
				continue
			operlist[i] = LABEL_FMT % (self.get_offset() + int(m.group(1)) + 2)
			break

	def __rewrite_io_addrs(self, ioaddr_map):
		offsets = { "sts"  : (0, "mem"),
			    "lds"  : (1, "mem"),
			    "in"   : (1, "io"),
			    "out"  : (0, "io"),
			    "sbic" : (0, "io"),
			    "sbis" : (0, "io"),
			    "sbi"  : (0, "io"),
			    "cbi"  : (0, "io"), }
		try:
			(offset, optype) = offsets[self.get_insn()]
		except KeyError as e:
			return
		operands = self.get_operands()
		ioaddr = int(operands[offset], 0)
		if optype == "mem":
			if ioaddr < 0x20:
				print("Error: mem-op offset operand < 0x20")
				exit(1)
			if ioaddr < 0x60:
				ioaddr -= 0x20
		try:
			name = ioaddr_map[ioaddr]
		except KeyError as e:
			return
		if optype == "mem" and ioaddr < 0x60:
			name += " + 0x20"
		# Got a name for it. Reassign it.
		operands[offset] = name

	def __rewrite_special_registers(self):
		special_regs_tab = { 26 : "XL",
				     27 : "XH",
				     28 : "YL",
				     29 : "YH",
				     30 : "ZL",
				     31 : "ZH", }
		r = re.compile(r"^[rR]([0-9]+)$")
		operands = self.get_operands()
		for i in range(0, len(operands)):
			m = r.match(operands[i])
			if not m:
				continue
			regnum = int(m.group(1))
			try:
				name = special_regs_tab[regnum]
			except KeyError as e:
				continue
			operands[i] = name

	def __fix_raw_words(self):
		if self.get_insn() == ".word":
			self.set_insn(".dw")

	def rewrite(self, ioaddr_map):
		'''Rewrite the instruction to be better human readable'''
		self.__rewrite_jmp_targets()
		self.__rewrite_rjmp_targets()
		self.__rewrite_io_addrs(ioaddr_map)
		self.__rewrite_special_registers()
		self.__fix_raw_words()


def usage():
	print("avr-postproc [OPTIONS] INC-FILE")
	print("")
	print("INC-FILE is the assembly .inc file.")
	print("Objdump assembly is read from stdin.")
	print("Processed assembly is written to stdout.")
	print("")
	print("Options:")
	print(" -s|--start OFFSET   Start offset. Default 0.")
	print(" -e|--end OFFSET     End offset. Default all.")

def main():
	start_offset = 0
	stop_offset = -1

	try:
		(opts, args) = getopt.getopt(sys.argv[1:],
			"hs:e:",
			[ "help", "start=", "end=", ])
	except getopt.GetoptError as e:
		usage()
		return 1
	for (o, v) in opts:
		if o in ("-h", "--help"):
			usage()
			return 0
		if o in ("-s", "--start"):
			try:
				start_offset = int(v)
			except ValueError as e:
				die("--start is not a number")
		if o in ("-e", "--end"):
			try:
				stop_offset = int(v)
			except ValueError as e:
				die("--end is not a number")
	if len(args) != 1:
		die("INC-FILE not specified")

	inc_file = args[0]
	ioaddr_map = generate_io_table(inc_file)

	lines = sys.stdin.readlines()
	insns = []
	funcs = []

	# Parse the input and rewrite the
	# instructions to include symbolic names
	for line in lines:
		try:
			insn = Insn(line)
		except Insn.StringIgnore as e:
			continue
		except Insn.StringErr as e:
			print("ERROR: Could not parse line \"%s\"" % line)
			exit(1)
		if insn.get_offset() < start_offset:
			continue
		if stop_offset != -1 and insn.get_offset() >= stop_offset:
			break
		insn.rewrite(ioaddr_map)
		insns.append(insn)

	def get_insn_by_offset(offset):
		for insn in insns:
			if insn.get_offset() == offset:
				return insn
		print("Instruction with offset 0x%04X not found" % offset)
		return None

	for insn in insns:
		branch_insns = { "jmp"   : ("type_jmp", 0),
				 "rjmp"  : ("type_jmp", 0),
				 "brbs"  : ("type_jmp", 1),
				 "brbc"  : ("type_jmp", 1),
				 "breq"  : ("type_jmp", 0),
				 "brne"  : ("type_jmp", 0),
				 "brcs"  : ("type_jmp", 0),
				 "brcc"  : ("type_jmp", 0),
				 "brsh"  : ("type_jmp", 0),
				 "brlo"  : ("type_jmp", 0),
				 "brmi"  : ("type_jmp", 0),
				 "brpl"  : ("type_jmp", 0),
				 "brge"  : ("type_jmp", 0),
				 "brlt"  : ("type_jmp", 0),
				 "brhs"  : ("type_jmp", 0),
				 "brhc"  : ("type_jmp", 0),
				 "brts"  : ("type_jmp", 0),
				 "brtc"  : ("type_jmp", 0),
				 "brvs"  : ("type_jmp", 0),
				 "brvc"  : ("type_jmp", 0),
				 "brie"  : ("type_jmp", 0),
				 "brid"  : ("type_jmp", 0),
				 "call"  : ("type_call", 0),
				 "rcall" : ("type_call", 0), }
		insn_name = insn.get_insn()
		try:
			(jmptype, targetoper) = branch_insns[insn_name]
		except KeyError as e:
			continue
		tgt_offset = int(insn.get_operands()[targetoper][1:], 16)
		target = get_insn_by_offset(tgt_offset)
		if target:
			if jmptype == "type_jmp":
				target.add_jmpsource(insn)
			else:
				target.add_caller(insn)

	# Write the output
	sys.stdout.write('.include "' + inc_file.split("/")[-1] + '"\n')
	sys.stdout.write('\n')
	sys.stdout.write('.org 0x000\n')
	sys.stdout.write('\n')
	for insn in insns:
		s = insn.get_full_string()
		if not s:
			continue
		sys.stdout.write(s + "\n")

	return 0

if __name__ == "__main__":
	sys.exit(main())
