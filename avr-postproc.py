#!/usr/bin/env python3
"""
#  Simple AVR disassembly postprocessor
#
#  Copyright (C) 2012-2014 Michael Buesch <m@bues.ch>
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

def ishex(s):
	for c in s:
		if c not in "0123456789abcdefABCDEF":
			return False
	return True

def eff_linelen(s):
	'''Get effective line length (Tabs => 8 characters).'''
	count = 0
	for c in s:
		if c == '\t':
			count = (count + 8) // 8 * 8
		if c == '\n':
			count = 0
		else:
			count += 1
	return count

def pad_to_length(s, target_len):
	'''Pad a string up to the specified effective length.'''
	slen = eff_linelen(s)
	if slen >= target_len:
		return s
	return s + ' ' * (target_len - slen)

def fix_twos_complement(val, nrBits):
	sign = 1 << nrBits
	mask = (sign << 1) - 1
	val &= mask
	if val & sign:
		return -((~val + 1) & mask)
	return val

class IncFile(object):
	'''A parsed INC-file.'''

	equ_re = re.compile(r"^\s*\.equ\s+(\w+)\s*=\s*(\w+)\s*(?:;.*)?")
	flash_end_re = re.compile(r"^\s*\.equ\s+FLASHEND\s*=\s*(\w+)\s*(?:;.*)?")

	def __init__(self, inc_file_path):
		self.ioaddr_map = {}
		self.irq_map = {}
		self.irq_vectors_size = None
		self.flash_size = None
		in_io = False
		in_irq = False
		try:
			lines = open(inc_file_path, "r").readlines()
		except IOError as e:
			die("Failed to read INC-FILE '%s': %s" % (inc_file_path, str(e)))
		for line in lines:
			line = line.strip()
			if "I/O REGISTER DEFINITIONS" in line:
				in_io = True
				continue
			if "INTERRUPT VECTORS" in line:
				in_irq = True
				continue
			if line.startswith("; *****"):
				in_io = False
				in_irq = False
				continue
			if in_io:
				self.__parse_iomap_entry(line)
			elif in_irq:
				self.__parse_irqmap_entry(line)
			else:
				m = self.flash_end_re.match(line)
				if m:
					try:
						end = int(m.group(1), 16)
						self.flash_size = end + 1
						self.flash_size *= 2 # To bytes
					except ValueError:
						pass
		if not self.flash_size:
			die("Failed to get FLASHEND from INC-FILE")
		self.flash_mask = self.flash_size - 1
		if not self.ioaddr_map:
			die("Failed to parse I/O-map from INC-FILE")
		if not self.irq_map or not self.irq_vectors_size:
			die("Failed to parse IRQ-map from INC-FILE")
		if 0 not in self.irq_map:
			self.irq_map[0] = "RESET"

	# Parse one I/O map entry
	def __parse_iomap_entry(self, line):
		m = self.equ_re.match(line)
		if not m:
			return
		name, addr = m.group(1), m.group(2)
		if addr.startswith("0x"):
			addr = addr[2:]
		try:
			addr = int(addr, 16)
		except ValueError:
			die("Failed to convert I/O map address: %s" % line)
		self.ioaddr_map[addr] = name

	# Parse one IRQ map entry
	def __parse_irqmap_entry(self, line):
		m = self.equ_re.match(line)
		if not m:
			return
		name, addr = m.group(1), m.group(2)
		if name == "INT_VECTORS_SIZE":
			try:
				self.irq_vectors_size = int(addr, 10)
				self.irq_vectors_size *= 2 # To byte size
			except ValueError:
				die("Failed to parse IRQ map size: %s" %\
				    line)
			return
		if not name.endswith("addr"):
			return
		if addr.startswith("0x"):
			addr = addr[2:]
		try:
			addr = int(addr, 16)
		except ValueError:
			die("Failed to convert IRQ map address: %s" % line)
		addr *= 2 # To byte address
		self.irq_map[addr] = name

class Insn(object):
	'''An AVR assembly instruction'''

	class StringErr(Exception): pass
	class StringIgnore(Exception): pass

	def __init__(self, insn_string):
		# Check whether this is an instruction line.
		m = re.match(r'^\s*[0-9a-fA-F]+:\s+', insn_string)
		if not m:
			raise Insn.StringIgnore()
		# Look for comments
		self.comment = ""
		if ';' in insn_string:
			i = insn_string.index(';')
			self.comment = insn_string[i+1:].strip()
			# Strip it off
			insn_string = insn_string[:i]
			# Fix 0x0x breakage
			self.comment = self.comment.replace("0x0x", "0x")
		s = insn_string.split()
		if len(s) < 2:
			raise Insn.StringErr()
		# Remove opcodes
		while len(s[1]) == 2 and ishex(s[1]):
			s.pop(1)
		# Extract offset (2ab:)
		try:
			off = s[0]
			off = "0x" + off[:-1]
			self.offset = int(off, 16)
			self.offset_label = None
		except TypeError:
			die("Failed to extract insn offset")
		# Extract insn string (jmp...)
		self.insn = s[1].lower()
		# Extract operands
		self.operands = []
		try:
			self.operands = s[2:]
		except IndexError as e:
			pass
		for i, op in enumerate(self.operands):
			# Strip commas from operands
			op = self.operands[i] = op.replace(",", "")
			# Fix 0x0x breakage
			op = self.operands[i] = op.replace("0x0x", "0x")
		self.callers = []
		self.jmpsources = []

	def get_full_string(self, inc_file):
		'''Returns a full string of the instruction'''

		max_vect = inc_file.irq_vectors_size - 2
		is_irq_handler = any(s.get_offset() <= max_vect
				     for s in self.jmpsources)

		s = ""

		# Show CALLers
		if self.callers:
			s += "\n; FUNCTION called by "
			c = []
			pfx = ""
			for i, caller in enumerate(self.callers):
				c.append(pfx + caller.get_offset_string())
				if i != 0 and \
				   (i + 1) % 6 == 0 and \
				   i != len(self.callers) - 1:
					pfx = "\n;\t\t"
				else:
					pfx = ""
			s += ", ".join(c)
			s += "\n"

		# Show IRQ vector jump sources
		if is_irq_handler and not self.callers:
			s += "\n"
		if is_irq_handler:
			# This is jumped to from IRQ vectors.
			s += "; IRQ handler for "
			s += ", ".join(s.get_offset_string()
				       for s in self.jmpsources)
			s += "\n"

		# Dump the instruction string
		s += self.get_offset_string() + ":"
		s = pad_to_length(s, 10)
		s += self.get_insn()
		if self.get_operands():
			s = pad_to_length(s, 18)
			s += ", ".join(self.get_operands())

		# Add the comment string
		comm = self.get_comment()
		if comm or self.jmpsources:
			s = pad_to_length(s, 35)
			s += ";"
		if comm:
			s += comm
			if self.jmpsources:
				s += " / "

		# Add the (R)JMP sources
		if self.jmpsources:
			nonirq_jmpsrcs = [ s for s in self.jmpsources
					   if s.get_offset() > max_vect ]
			if nonirq_jmpsrcs:
				s += "JUMPTARGET from "
				s += ", ".join(s.get_offset_string()
					       for s in nonirq_jmpsrcs)
		return s

	def get_offset(self):
		return self.offset

	def get_offset_label(self):
		return self.offset_label

	def get_offset_string(self):
		label = self.get_offset_label()
		if label:
			return label
		return LABEL_FMT % self.get_offset()

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

	def __rewrite_irq_label(self, inc_file):
		offset = self.get_offset()
		if offset >= inc_file.irq_vectors_size:
			return
		try:
			label = inc_file.irq_map[offset]
		except KeyError:
			return
		if label.endswith("addr"):
			label = label[:-4]
		label = "L_" + label
		self.offset_label = label

	def __rewrite_jmp_targets(self, inc_file):
		if self.get_insn() != "jmp" and self.get_insn() != "call":
			return
		operands = self.get_operands()
		if len(operands) != 1:
			die("Error: more than one JMP/CALL operand")
		operands[0] = LABEL_FMT % int(operands[0], 0)

	def __rewrite_rjmp_targets(self, inc_file):
		operlist = self.get_operands()
		r = re.compile(r"^\.([\+-][0-9]+)")
		for i in range(0, len(operlist)):
			m = r.match(operlist[i])
			if not m:
				continue
			offs = fix_twos_complement(int(m.group(1)), 12) + 2
			offs = (self.get_offset() + offs) & inc_file.flash_mask
			operlist[i] = LABEL_FMT % offs
			break

	def __rewrite_io_addrs(self, inc_file):
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
			name = inc_file.ioaddr_map[ioaddr]
		except KeyError as e:
			return
		if optype == "mem" and ioaddr < 0x60:
			name += " + 0x20"
		# Got a name for it. Reassign it.
		operands[offset] = name

	def __rewrite_special_registers(self, inc_file):
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

	def __fix_raw_words(self, inc_file):
		if self.get_insn() == ".word":
			self.set_insn(".dw")

	def rewrite(self, inc_file):
		'''Rewrite the instruction to be better human readable'''
		self.__rewrite_irq_label(inc_file)
		self.__rewrite_jmp_targets(inc_file)
		self.__rewrite_rjmp_targets(inc_file)
		self.__rewrite_io_addrs(inc_file)
		self.__rewrite_special_registers(inc_file)
		self.__fix_raw_words(inc_file)


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

	inc_file_path = args[0]
	inc_file = IncFile(inc_file_path)

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
			die("ERROR: Could not parse line \"%s\"" % line)
		if insn.get_offset() < start_offset:
			continue
		if stop_offset != -1 and insn.get_offset() > stop_offset:
			break
		insn.rewrite(inc_file)
		insns.append(insn)

	def get_insn_by_offset(offset):
		for insn in insns:
			if insn.get_offset() == offset:
				return insn
		print("; Postproc error: Instruction with "
		      "offset 0x%04X not found" % offset)
		return None

	# Annotate jump sources
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
	sys.stdout.write('.include "' + inc_file_path.split("/")[-1] + '"\n')
	sys.stdout.write('\n')
	sys.stdout.write('.org 0x000\n')
	sys.stdout.write('\n')
	for insn in insns:
		s = insn.get_full_string(inc_file)
		if not s:
			continue
		sys.stdout.write(s + "\n")

	return 0

if __name__ == "__main__":
	sys.exit(main())
