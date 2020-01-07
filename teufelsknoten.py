#!/usr/bin/env python3

from __future__ import print_function
import numpy as np
import itertools
import sys


class Stick(object):
	XPAR = 0
	YPAR = 1
	ZPAR = 2

	def __init__(self, name, array):
		self.name = name
		self.array = np.asarray(array)

	@property
	def dir(self):
		if len(self.array) > 2:
			return self.ZPAR
		elif len(self.array[0]) > 2:
			return self.YPAR
		return self.XPAR

	def rot(self, axis, n=1):
		if n == 0:
			return self
		if axis == 0: # X
			newArray = np.rot90(self.array, n, (0, 1))
		elif axis == 1: # Y
			newArray = np.rot90(self.array, n, (0, 2))
		elif axis == 2: # Z
			newArray = np.rot90(self.array, n, (1, 2))
		return self.__class__(self.name, newArray)

	def __genXZRotations(self):
		self.rotX = self.rot(0)
		self.rotZ = self.rot(2)

	def __genBasicRotations(self):
		self.basicRotations = []
		for rotY in (0, 1, 2, 3):
			for rotX in (0, 2):
				r = self.rot(0, rotX).rot(1, rotY)
				for other in self.basicRotations:
					if np.array_equal(other.array, r.array):
						break
				else:
					r.__genXZRotations()
					self.basicRotations.append(r)

	def genRotations(self):
		self.__genXZRotations()
		self.rotX.__genBasicRotations()
		self.rotZ.__genBasicRotations()
		self.__genBasicRotations()

	def __str__(self):
		if self.dir == self.XPAR:
			ret = [ self.name + " " ]
			for y in range(2):
				if y > 0:
					ret.append(" " * (len(self.name) + 1))
				for x in range(16):
					if x <= 5 or x >= 10:
						ret.append("=")
					else:
						xx = x - 6
						if self.array[0][y][xx] and\
						   self.array[1][y][xx]:
							ret.append("#")
						elif self.array[0][y][xx]:
							ret.append("@")
						elif self.array[1][y][xx]:
							ret.append("*")
						else:
							ret.append(" ")
				ret.append("\n")
		elif self.dir == self.YPAR:
			ret = [ self.name + "\n" ]
			for y in range(16):
				for x in range(2):
					if y <= 5 or y >= 10:
						ret.append("=")
					else:
						yy = y - 6
						if self.array[0][yy][x] and\
						   self.array[1][yy][x]:
							ret.append("#")
						elif self.array[0][yy][x]:
							ret.append("@")
						elif self.array[1][yy][x]:
							ret.append("*")
						else:
							ret.append(" ")
				ret.append("\n")
		else:
			ret = [ self.name + " " ]
			for y in range(2):
				if y > 0:
					ret.append(" " * (len(self.name) + 1))
				ret.append("|")
				for x in range(2):
					s = np.sum(self.array, 0)
					ret.append(str(s[y][x]))
				ret.append("|\n")
		return "".join(ret)

	def __repr__(self):
		return repr(self.array).replace("array", "Stick")

	def __hash__(self):
		return hash(self.name)

	def __eq__(self, other):
		return self.name == other.name

	def __ne__(self, other):
		return self.name != other.name

class Solution(object):
	def __init__(self, a, b, c, d, e, f):
		self.a = a
		self.b = b
		self.c = c
		self.d = d
		self.e = e
		self.f = f

	def rot(self, axis):
		new = self.__class__(self.a, self.b, self.c, self.d, self.e, self.f)
		new.a = new.a.rot(axis, 2)
		new.b = new.b.rot(axis, 2)
		new.c = new.c.rot(axis, 2)
		new.d = new.d.rot(axis, 2)
		new.e = new.e.rot(axis, 2)
		new.f = new.f.rot(axis, 2)
		if axis == 0:
			new.c, new.d = new.d, new.c
			new.e, new.f = new.f, new.e
		elif axis == 1:
			new.a, new.b = new.b, new.a
			new.c, new.d = new.d, new.c
		elif axis == 2:
			new.a, new.b = new.b, new.a
			new.e, new.f = new.f, new.e
		return new

	def __eq_exact(self, other):
		return np.array_equal(self.a.array, other.a.array) and\
		       np.array_equal(self.b.array, other.b.array) and\
		       np.array_equal(self.c.array, other.c.array) and\
		       np.array_equal(self.d.array, other.d.array) and\
		       np.array_equal(self.e.array, other.e.array) and\
		       np.array_equal(self.f.array, other.f.array)

	def __eq__(self, other):
		sx = self
		#FIXME this is wrong
		for x in range(2):
			if x > 0:
				sx = sx.rot(0)
			sy = sx
			for y in range(2):
				if y > 0:
					sy = sy.rot(1)
				sz = sy
				for z in range(2):
					if z > 0:
						sz = sz.rot(2)
					if sz.__eq_exact(other):
						return True
		return False

	def __ne__(self, other):
		return not self.__eq__(other)

	def __str__(self):
		a, b, c, d, e, f = self.a, self.b, self.c, self.d, self.e, self.f
		ret = "a=%s, b=%s, c=%s, d=%s e=%s f=%s\n" % (
			a.name, b.name, c.name, d.name, e.name, f.name)

		lines = []
		for lineA, lineB in zip(str(a).splitlines(), str(b).splitlines()):
			lines.append(lineA + "   " + lineB)

		ret += "\n".join(lines) + "\n\n"
		ret += "\n".join((str(c), str(d), str(e), str(f)))
		return ret

s1 = Stick("s1", (
		(  (1, 1),
		   (1, 1),
		   (1, 1),
		   (1, 1),  ),
		(  (1, 1),
		   (1, 1),
		   (1, 1),
		   (1, 1),  ),  ))

s2 = Stick("s2", (
		(  (0, 0),
		   (0, 0),
		   (0, 0),
		   (0, 0),  ),
		(  (1, 1),
		   (1, 1),
		   (1, 1),
		   (1, 1),  ),  ))

s3 = Stick("s3", (
		(  (1, 0),
		   (0, 0),
		   (0, 0),
		   (1, 1),  ),
		(  (1, 0),
		   (1, 0),
		   (1, 1),
		   (1, 1),  ),  ))

s4 = Stick("s4", (
		(  (0, 1),
		   (0, 0),
		   (0, 0),
		   (1, 1),  ),
		(  (0, 1),
		   (0, 1),
		   (1, 1),
		   (1, 1),  ),  ))

s5 = Stick("s5", (
		(  (0, 0),
		   (0, 0),
		   (0, 0),
		   (0, 0),  ),
		(  (1, 1),
		   (0, 1),
		   (0, 1),
		   (1, 1),  ),  ))

s6 = Stick("s6", (
		(  (0, 1),
		   (0, 0),
		   (0, 0),
		   (0, 1),  ),
		(  (0, 1),
		   (1, 1),
		   (1, 1),
		   (0, 1),  ),  ))

sticks = {s1, s2, s3, s4, s5, s6}
for s in sticks:
	s.genRotations()

emptyPlaneXY = np.asarray(
	(
		(  (0, 0, 0, 0),
		   (0, 0, 0, 0),
		   (0, 0, 0, 0),
		   (0, 0, 0, 0),  ),
	)
)
emptyPlaneYZ = np.rot90(emptyPlaneXY, 1, (0, 2))
emptyPlaneXZ = np.rot90(emptyPlaneXY, 1, (0, 1))

cornersXY = np.asarray(
	(
		(  (1, 0, 0, 1),
		   (0, 0, 0, 0),
		   (0, 0, 0, 0),
		   (1, 0, 0, 1),  ),
		(  (1, 0, 0, 1),
		   (0, 0, 0, 0),
		   (0, 0, 0, 0),
		   (1, 0, 0, 1),  ),
	)
)
cornersYZ = np.rot90(cornersXY, 1, (0, 2))
cornersXZ = np.rot90(cornersXY, 1, (0, 1))


def processZPlane(a, b, c, d, cRot, dRot, abcd):
	remainingSticks = sticks - {a, b, c, d}
	for _e, _f in itertools.permutations(remainingSticks, 2):

		for e in _e.basicRotations:
			eRot = e.rotX
			for f in _f.basicRotations:
				fRot = f.rotX

				ef = np.hstack((eRot.array, fRot.array))
				if np.any(ef - cornersYZ < 0):
					continue # At least one corner is not filled.

				efFilled = np.dstack((emptyPlaneYZ, ef, emptyPlaneYZ))

				abcdef = abcd + efFilled
				if not np.any(abcdef > 1):
					yield Solution(a, b, cRot, dRot, eRot, fRot)

def processXYPlane():
	for _a, _b, _c, _d in itertools.permutations(sticks, 4):

		for a in _a.basicRotations:
			for b in _b.basicRotations:
				ab = np.dstack((a.array, b.array))
				if np.any(ab - cornersXY < 0):
					continue # At least one corner is not filled.

				for c in _c.basicRotations:
					cRot = c.rotZ
					for d in _d.basicRotations:
						dRot = d.rotZ

						cd = np.vstack((cRot.array, dRot.array))
						if np.any(cd - cornersXZ < 0):
							continue # At least one corner is not filled.

						abFilled = np.vstack((emptyPlaneXY, ab, emptyPlaneXY))
						cdFilled = np.hstack((emptyPlaneXZ, cd, emptyPlaneXZ))

						abcd = abFilled + cdFilled
						if np.any(abcd > 1):
							continue # This one collides in the XY plane already.

						yield from processZPlane(a, b, c, d, cRot, dRot, abcd)

solutions = []
for solution in processXYPlane():
	for otherSolution in solutions:
		if solution == otherSolution:
			break # We have that one already
	else:
		solutions.append(solution)

print("Found %s solution(s).\n" % len(solutions))
for i, solution in enumerate(solutions):
	print("Solution #%d: %s" % (i + 1, solution))
