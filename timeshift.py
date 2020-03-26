#!/usr/bin/env python3
"""
# timeshift - Simple work time scheduler
# Copyright (c) 2009-2020 Michael Buesch <m@bues.ch>
# Licensed under the GNU/GPL version 2 or later.
"""

import sys
import base64
import sqlite3 as sql

try:
	# Try to use PySide
	raise ImportError #FIXME
	from PySide2.QtCore import *
	from PySide2.QtGui import *
	from PySide2.QtWidgets import *
	usingPySide = True
except (ImportError) as e:
	# PyQt4 fallback
	from PyQt5.QtCore import *
	from PyQt5.QtGui import *
	from PyQt5.QtWidgets import *
	usingPySide = False

# Shift types
SHIFT_DEFAULT		= -1 # (not DB ABI)
SHIFT_EARLY		= 0
SHIFT_LATE		= 1
SHIFT_NIGHT		= 2
SHIFT_DAY		= 3

# Day type overrides
DTYPE_DEFAULT		= 0 # (not DB ABI)
DTYPE_COMPTIME		= 1
DTYPE_HOLIDAY		= 2
DTYPE_FEASTDAY		= 3
DTYPE_SHORTTIME		= 4

# Day flags
DFLAG_UNCERTAIN		= (1 << 0)
DFLAG_ATTENDANT		= (1 << 1)


def toBase64(string):
	return base64.standard_b64encode(
		string.encode("UTF-8", "ignore")).decode("UTF-8", "ignore")

def fromBase64(b64str):
	return base64.standard_b64decode(
		b64str.encode("UTF-8", "ignore")).decode("UTF-8", "ignore")

class Wrapper(object): # Must not be QObject derived.
	__slots__ = ( "obj", )
	def __init__(self, obj):
		self.obj = obj

def floatEqual(f0, f1):
	return abs(f0 - f1) < 0.001

def QDateToId(qdate):
	"Convert a QDate object to a unique integer ID"
	return QDateTime(qdate).toTime_t()

def IdToQDate(id):
	"Convert a unique integer ID to a QDate object"
	return QDateTime.fromTime_t(int(id)).date()

class TsException(Exception): pass

class ICal(QObject):
	"Simple iCalendar parser"

	class Event(QObject):
		def __init__(self):
			QObject.__init__(self)
			self.props = { }

		def addProp(self, prop):
			self.props[prop.name] = prop

		def getProp(self, name):
			try:
				return self.props[name]
			except (KeyError) as e:
				return None

		def getDateRange(self):
			# Returns a list of QDate objects
			start = self.getProp("DTSTART")
			if not start:
				raise TsException("No DTSTART property")
			end = self.getProp("DTEND")
			if not end:
				dur = self.getProp("DURATION")
				if not dur:
					return [ start.toQDate() ]
				raise TsException("TODO: DURATION property "
					"not implemented, yet.")
			ret, date = [], start.toQDate()
			while date < end.toQDate():
				ret.append(date)
				date = date.addDays(1)
			return ret

	class Prop(QObject):
		def __init__(self, name, params, value):
			QObject.__init__(self)
			self.name = name
			self.params = params
			self.value = value

		def toQDate(self):
			date = QDate.fromString(self.value, Qt.ISODate)
			if date.isValid():
				return date
			date = QDate.fromString(self.value, "yyyyMMdd")
			if date.isValid():
				return date
			raise TsException("Date property '%s' "
				"format error" % self.name)

	def __init__(self):
#		QObject.__init__(self)
		pass

	def getEvents(self):
		return self.__events

	def __parseParams(self, params):
		# Returns a list of tuples: (paramName, paramValue)
		ret = []
		for param in params:
			p = param.split('=')
			if len(p) != 2:
				raise TsException("Invalid parameter '%s'" % param)
			p[0] = p[0].upper()
			ret.append(tuple(p))
		return ret

	def __unknown(self, propName, value):
		print("ical: Ignoring unexpected '%s:%s'" %\
		      (propName, value))

	def parseICal(self, data):
		self.__events = []
		inCalendar = False
		curEvent = None
		for line in data.splitlines():
			if not line.strip():
				continue
			vstart = line.find(':')
			value = line[vstart+1:]
			prop = line[:vstart].split(';')
			propName = prop[0].strip().upper()
			try:
				propParams = prop[1:]
			except (IndexError) as e:
				propParams = []
			propParams = self.__parseParams(propParams)
			if not inCalendar:
				if propName == "BEGIN" and\
				   value.strip().upper() == "VCALENDAR":
					inCalendar = True
					continue
				self.__unknown(propName, value)
				continue
			if not curEvent:
				if propName in ("METHOD", "PRODID", "VERSION"):
					continue
				if propName == "BEGIN" and\
				   value.strip().upper() == "VEVENT":
					curEvent = self.Event()
					continue
				if propName == "END" and\
				   value.strip().upper() == "VCALENDAR":
					curEvent = None
					inCalendar = False
					continue
				self.__unknown(propName, value)
				continue
			if propName == "END" and\
			   value.strip().upper() == "VEVENT":
				self.__events.append(curEvent)
				curEvent = None
				continue
			curEvent.addProp(self.Prop(propName, propParams, value))

class ICalImport(ICal):
	class Opts(QObject):
		def __init__(self, setShift, setDayType):
			QObject.__init__(self)
			self.setShift = setShift
			self.setDayType = setDayType

	def __init__(self, widget, db):
		ICal.__init__(self)
		self.widget = widget
		self.db = db

	def importICal(self, data, opts):
		self.parseICal(data)
		for event in self.getEvents():
			summary = event.getProp("SUMMARY")
			if not summary:
				raise TsException(
					"Event does not have SUMMARY attribute")
			for date in event.getDateRange():
				self.__doImport(event, date, opts)

	def __doImport(self, event, date, opts):
		if opts.setDayType != DTYPE_DEFAULT:
			newDType = opts.setDayType
			curDType = self.db.getDayTypeOverride(date)
			if curDType is not None and\
			   curDType != newDType:
				yes = self.__question(date,
					"Has day-type override",
					date.toString() + ": "
					"Already has day type. Override?")
				if not yes:
					newDType = curDType
			if curDType != newDType:
				self.db.setDayTypeOverride(date, newDType)
		if opts.setShift != SHIFT_DEFAULT:
			newShift = opts.setShift
			curShift = self.db.getShiftOverride(date)
			if curShift is not None and\
			   curShift != newShift:
				yes = self.__question(date,
					"Has shift override",
					date.toString() + ": "
					"Already has shift. Override?")
				if not yes:
					newShift = curShift
			if curShift != newShift:
				self.db.setShiftOverride(date, newShift)
		summary = event.getProp("SUMMARY").value
		newComment = summary
		curComment = self.db.getComment(date)
		if curComment and\
		   curComment != newComment:
			yes = self.__question(date, "Comment exists",
				"A comment exists:\n'" + curComment +\
				"'\n\nAppend '%s'?" % summary)
			if yes:
				newComment = curComment + '\n' + summary
			else:
				newComment = curComment
		if curComment != newComment:
			self.db.setComment(date, newComment)

	def __question(self, date, caption, text):
		res = QMessageBox.question(self.widget,
			date.toString() + ": " + caption,
			text,
			QMessageBox.Yes | QMessageBox.No |\
			QMessageBox.Cancel)
		if res & QMessageBox.Cancel:
			raise TsException("Cancelled")
		return bool(res & QMessageBox.Yes)

class ICalImportDialog(QDialog, ICalImport):
	def __init__(self, parent, db):
		QDialog.__init__(self, parent)
		ICalImport.__init__(self, self, db)

		self.setWindowTitle("iCalendar Import")
		self.setLayout(QGridLayout())

		self.modGroup = QGroupBox("Tagesoptionen pro ical-event setzen")
		self.modGroup.setLayout(QGridLayout())
		self.layout().addWidget(self.modGroup, 0, 0)

		self.typeCombo = DayTypeComboBox(self)
		self.modGroup.layout().addWidget(self.typeCombo, 0, 0)

		self.shiftCombo = ShiftComboBox(self, defaultShift=True)
		self.modGroup.layout().addWidget(self.shiftCombo, 1, 0)

		self.fileButton = QPushButton("iCal Datei Import")
		self.layout().addWidget(self.fileButton, 1, 0)
		self.fileButton.released.connect(self.fileImport)

	def fileImport(self):
		ret = QFileDialog.getOpenFileName(self, "iCalendar Datei", "",
			"iCalendar Dateien (*.ics);;"
			"Alle Dateien (*)")
		if usingPySide:
			fn, selFilter = ret
		else:
			fn = ret
		if not fn:
			return
		self.__fileImport(fn)
		self.accept()

	def __fileImport(self, filename):
		try:
			fd = open(filename, "rb")
			data = fd.read()
			fd.close()
		except (IOError) as e:
			QMessageBox.critical(self,
				"iCal Laden fehlgeschlagen",
				"Laden fehlgeschlagen:\n" + str(e))
			return
		opts = ICalImport.Opts(
			setShift = self.shiftCombo.selectedShift(),
			setDayType = self.typeCombo.selectedDayType()
		)
		try:
			self.importICal(data, opts)
		except (TsException) as e:
			QMessageBox.critical(self,
				"iCal Import fehlgeschlagen",
				"Import fehlgeschagen:\n" + str(e))

class DayTypeComboBox(QComboBox):
	def __init__(self, parent=None):
		QComboBox.__init__(self, parent)
		self.addItem("---", DTYPE_DEFAULT)
		self.addItem("Zeitausgleich", DTYPE_COMPTIME)
		self.addItem("Urlaub", DTYPE_HOLIDAY)
		self.addItem("Feiertag", DTYPE_FEASTDAY)
		self.addItem("Kurzarbeit", DTYPE_SHORTTIME)

	def selectedDayType(self):
		return self.itemData(self.currentIndex())

class ShiftComboBox(QComboBox):
	def __init__(self, parent=None, shortNames=False, defaultShift=False):
		QComboBox.__init__(self, parent)
		sfx = "" if shortNames else "schicht"
		if defaultShift:
			self.addItem("Regulaere Schicht", SHIFT_DEFAULT)
		self.addItem("Frueh" + sfx, SHIFT_EARLY)
		self.addItem("Nacht" + sfx, SHIFT_NIGHT)
		self.addItem("Spaet" + sfx, SHIFT_LATE)
		self.addItem("Normal" + sfx, SHIFT_DAY)

	def selectedShift(self):
		return self.itemData(self.currentIndex())

class ShiftConfigItem(QObject):
	def __init__(self, name, shift, workTime, breakTime, attendanceTime):
		QObject.__init__(self)
		self.name = name
		self.shift = shift
		self.workTime = workTime
		self.breakTime = breakTime
		self.attendanceTime = attendanceTime

	@staticmethod
	def toBytes(item):
		return ";".join(
			(	toBase64(item.name),
				str(item.shift),
				str(item.workTime),
				str(item.breakTime),
				str(item.attendanceTime),
			)
		).encode("UTF-8", "ignore")

	@staticmethod
	def fromBytes(b):
		string = b.decode("UTF-8", "ignore")
		elems = string.split(";")
		try:
			return ShiftConfigItem(
				fromBase64(elems[0]),
				int(elems[1], 10),
				float(elems[2]),
				float(elems[3]),
				float(elems[4])
			)
		except (IndexError, ValueError) as e:
			raise TsException("ShiftConfigItem.fromBytes() "
					  "invalid string: " + string)

class Preset(QObject):
	def __init__(self, name, dayType, shift, workTime, breakTime, attendanceTime):
		QObject.__init__(self)
		self.name = name
		self.dayType = dayType
		self.shift = shift
		self.workTime = workTime
		self.breakTime = breakTime
		self.attendanceTime = attendanceTime

	@staticmethod
	def toBytes(preset):
		return ";".join(
			(	toBase64(preset.name),
				str(preset.dayType),
				str(preset.shift),
				str(preset.workTime),
				str(preset.breakTime),
				str(preset.attendanceTime),
			)
		).encode("UTF-8", "ignore")

	@staticmethod
	def fromBytes(b):
		string = b.decode("UTF-8", "ignore")
		elems = string.split(";")
		try:
			return Preset(
				fromBase64(elems[0]),
				int(elems[1], 10),
				int(elems[2], 10),
				float(elems[3]),
				float(elems[4]),
				float(elems[5])
			)
		except (IndexError, ValueError) as e:
			raise TsException("Preset.fromBytes() "
					  "invalid string: " + string)

class Snapshot(QObject):
	def __init__(self, date, shiftConfigIndex, accountValue,
		     holidaysLeft):
		QObject.__init__(self)
		self.date = date
		self.shiftConfigIndex = shiftConfigIndex
		self.accountValue = accountValue
		self.holidaysLeft = holidaysLeft

	@staticmethod
	def toBytes(snapshot):
		return ";".join(
			(	str(QDateToId(snapshot.date)),
				str(snapshot.shiftConfigIndex),
				str(snapshot.accountValue),
				str(snapshot.holidaysLeft),
			)
		).encode("UTF-8", "ignore")

	@staticmethod
	def fromBytes(b):
		string = b.decode("UTF-8", "ignore")
		elems = string.split(";")
		if len(elems) == 3:
			elems.append("0") # Holidays. db-v1 compat
		try:
			return Snapshot(
				IdToQDate(int(elems[0], 10)),
				int(elems[1], 10),
				float(elems[2]),
				int(elems[3], 10)
			)
		except (IndexError, ValueError) as e:
			raise TsException("Snapshot.fromBytes() "
					  "invalid string: " + string)

class TsDatabase(QObject):
	INMEM		= ":memory:"
	VERSION		= 2
	COMPAT_VERSIONS	= ( 1, 2 )

	sql.register_adapter(QDate, QDateToId)
	sql.register_converter("QDate", IdToQDate)

	sql.register_adapter(ShiftConfigItem, ShiftConfigItem.toBytes)
	sql.register_converter("ShiftConfigItem", ShiftConfigItem.fromBytes)

	sql.register_adapter(Preset, Preset.toBytes)
	sql.register_converter("Preset", Preset.fromBytes)

	sql.register_adapter(Snapshot, Snapshot.toBytes)
	sql.register_converter("Snapshot", Snapshot.fromBytes)

	TAB_params	= "params(name TEXT, data TEXT)"
	TAB_dayflags	= "dayFlags(date QDate, value INTEGER)"
	TAB_ovr_daytype	= "override_dayType(date QDate, value TEXT)"
	TAB_ovr_shift	= "override_shift(date QDate, value TEXT)"
	TAB_ovr_worktm	= "override_workTime(date QDate, value TEXT)"
	TAB_ovr_brtm	= "override_breakTime(date QDate, value TEXT)"
	TAB_ovr_atttm	= "override_attendanceTime(date QDate, value TEXT)"
	TAB_snaps	= "snapshots(date QDate, snapshot Snapshot)"
	TAB_comments	= "comments(date QDate, comment TEXT)"
	TAB_shconf	= "shiftConfig(idx INTEGER, item ShiftConfigItem)"
	TAB_presets	= "presets(idx INTEGER, preset Preset)"

	def __init__(self):
		QObject.__init__(self)
		self.commitTimer = QTimer(self)
		self.commitTimer.setSingleShot(True)
		self.commitTimer.timeout.connect(self.__commitTimerTimeout)
		self.__reset()
		self.open(self.INMEM)

	def __del__(self):
		self.conn.close()

	def __sqlError(self, exception):
		msg = "SQL error: " + str(exception)
		print(msg)
		import traceback
		traceback.print_stack()
		raise TsException(msg)

	def __reset(self):
		self.conn = None
		self.filename = None
		self.cachedShiftConfig = None

	def __close(self):
		if not self.conn:
			return
		try:
			if not self.isInMemory():
				print("Closing database...")
				self.commit()
				self.conn.cursor().execute("VACUUM;")
				self.commit()
			self.conn.close()
			self.__reset()
		except (sql.Error) as e:
			self.__sqlError(e)

	def close(self):
		self.__close()
		self.open(self.INMEM)

	def open(self, filename):
		try:
			self.__close()
			self.conn = sql.connect(str(filename),
				detect_types=sql.PARSE_DECLTYPES)
			self.filename = filename
			if not self.isInMemory():
				self.__checkDatabaseVersion()
			self.__initTables(self.conn)
			if self.isInMemory():
				self.__setDatabaseVersion()
		except (sql.Error) as e:
			self.__sqlError(e)

	def __setDatabaseVersion(self):
		try:
			self.__setParameter("dbVersion", self.VERSION)
		except (sql.Error) as e:
			self.__sqlError(e)

	def __checkDatabaseVersion(self):
		try:
			dbVer = int(self.__getParameter("dbVersion"), 10)
			if dbVer not in self.COMPAT_VERSIONS:
				raise TsException("Unsupported database "
					"version v%d" % dbVer)
			if dbVer < self.VERSION:
				print("Converting database from "
				      "v%d to v%d" % (dbVer, self.VERSION))
				# Convert all snapshots.
				for snapshot in self.getAllSnapshots():
					self.setSnapshot(snapshot.date,
							 snapshot)
				# Remove "HolidaysPerYear" parameter.
				self.__setParameter("HolidaysPerYear", None)
				# Update DB version
				self.__setDatabaseVersion()
		except (sql.Error) as e:
			self.__sqlError(e)
		except (ValueError) as e:
			raise TsException("Invalid database version info")

	def getFilename(self):
		return self.filename

	def isInMemory(self):
		return self.filename == self.INMEM

	def commit(self):
		try:
			self.conn.commit()
		except (sql.Error) as e:
			self.__sqlError(e)

	def __commitTimerTimeout(self):
		print("Committing database...")
		self.commit()

	def scheduleCommit(self, msec=5000):
		self.commitTimer.start(msec)

	def __initTables(self, conn):
		script = (
			"CREATE TABLE IF NOT EXISTS %s;" % self.TAB_params,
			"CREATE TABLE IF NOT EXISTS %s;" % self.TAB_dayflags,
			"CREATE TABLE IF NOT EXISTS %s;" % self.TAB_ovr_daytype,
			"CREATE TABLE IF NOT EXISTS %s;" % self.TAB_ovr_shift,
			"CREATE TABLE IF NOT EXISTS %s;" % self.TAB_ovr_worktm,
			"CREATE TABLE IF NOT EXISTS %s;" % self.TAB_ovr_brtm,
			"CREATE TABLE IF NOT EXISTS %s;" % self.TAB_ovr_atttm,
			"CREATE TABLE IF NOT EXISTS %s;" % self.TAB_snaps,
			"CREATE TABLE IF NOT EXISTS %s;" % self.TAB_comments,
			"CREATE TABLE IF NOT EXISTS %s;" % self.TAB_shconf,
			"CREATE TABLE IF NOT EXISTS %s;" % self.TAB_presets,
		)
		conn.cursor().executescript("\n".join(script))
		conn.commit()

	def resetDatabase(self):
		self.conn.cursor().executescript("""
			DROP TABLE IF EXISTS params;
			DROP TABLE IF EXISTS dayFlags;
			DROP TABLE IF EXISTS override_dayType;
			DROP TABLE IF EXISTS override_shift;
			DROP TABLE IF EXISTS override_workTime;
			DROP TABLE IF EXISTS override_breakTime;
			DROP TABLE IF EXISTS override_attendanceTime;
			DROP TABLE IF EXISTS snapshots;
			DROP TABLE IF EXISTS comments;
			DROP TABLE IF EXISTS shiftConfig;
			DROP TABLE IF EXISTS presets;
		""")
		self.conn.commit()
		self.conn.cursor().execute("VACUUM;")
		self.conn.commit()
		self.__initTables(self.conn)
		self.__setDatabaseVersion()
		self.conn.commit()

	def __cloneTab(self, sourceCursor, targetCursor, tabSignature):
		tabName = tabSignature.split("(")[0].strip()
		columns = tabSignature.split("(")[1].split(")")[0]
		columns = [ c.split()[0] for c in columns.split(",") ]
		columns = ", ".join(columns)
		targetCursor.execute("DROP TABLE IF EXISTS %s;" % tabName)
		targetCursor.execute("CREATE TABLE %s;" % tabSignature)
		sourceCursor.execute("SELECT %s FROM %s;" % (columns, tabName))
		for rowData in sourceCursor.fetchall():
			valTmpl = ", ".join("?" * len(columns.split(",")))
			targetCursor.execute("INSERT INTO %s(%s) VALUES(%s);" %\
				(tabName, columns, valTmpl),
				rowData)

	def clone(self, target):
		try:
			cloneconn = sql.connect(str(target),
				detect_types=sql.PARSE_DECLTYPES)
			for tabSignature in (self.TAB_params, self.TAB_dayflags,
					     self.TAB_ovr_daytype, self.TAB_ovr_shift,
					     self.TAB_ovr_worktm, self.TAB_ovr_brtm,
					     self.TAB_ovr_atttm, self.TAB_snaps,
					     self.TAB_comments, self.TAB_shconf,
					     self.TAB_presets):
				self.__cloneTab(sourceCursor=self.conn.cursor(),
						targetCursor=cloneconn.cursor(),
						tabSignature=tabSignature)
			cloneconn.commit()
			cloneconn.cursor().execute("VACUUM;")
			cloneconn.commit()
			cloneconn.close()
		except (sql.Error) as e:
			self.__sqlError(e)

	def __setParameter(self, param, value):
		try:
			c = self.conn.cursor()
			c.execute("DELETE FROM params WHERE name=?;", (str(param),))
			if value is not None:
				c.execute("INSERT INTO params(name, data) VALUES(?, ?);",
					  (str(param), str(value)))
			self.scheduleCommit()
		except (sql.Error) as e:
			self.__sqlError(e)

	def __getParameter(self, param):
		try:
			c = self.conn.cursor()
			c.execute("SELECT data FROM params WHERE name=?;", (param,))
			value = c.fetchone()
			if value:
				return value[0]
			return None
		except (sql.Error) as e:
			self.__sqlError(e)

	def setDayFlags(self, date, value):
		try:
			c = self.conn.cursor()
			c.execute("DELETE FROM dayFlags WHERE date=?;", (date,))
			c.execute("INSERT INTO dayFlags(date, value) VALUES(?, ?);",
				  (date, int(value) & 0xFFFFFFFF))
			self.scheduleCommit()
		except (sql.Error) as e:
			self.__sqlError(e)

	def getDayFlags(self, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT value FROM dayFlags WHERE date=?;", (date,))
			value = c.fetchone()
			if not value:
				return 0
			return int(value[0]) & 0xFFFFFFFF
		except (sql.Error) as e:
			self.__sqlError(e)

	def __setOverride(self, table, date, value):
		try:
			c = self.conn.cursor()
			c.execute("DELETE FROM %s WHERE date=?;" % table, (date,))
			if value is not None:
				c.execute("INSERT INTO %s(date, value) VALUES(?, ?);" % table,
					  (date, str(value)))
			self.scheduleCommit()
		except (sql.Error) as e:
			self.__sqlError(e)

	def __getOverride(self, table, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT value FROM %s WHERE date=?;" % table, (date,))
			value = c.fetchone()
			if value:
				return value[0]
			return None
		except (sql.Error) as e:
			self.__sqlError(e)

	def __hasOverride(self, table, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT COUNT(*) FROM %s WHERE date=?;" % table, (date,))
			value = c.fetchone()
			if value:
				return value[0] > 0
			return False
		except (sql.Error) as e:
			self.__sqlError(e)

	def setDayTypeOverride(self, date, daytype):
		self.__setOverride("override_dayType", date, daytype)

	def hasDayTypeOverride(self, date):
		return self.__hasOverride("override_dayType", date)

	def getDayTypeOverride(self, date):
		try:
			return int(self.__getOverride("override_dayType", date), 10)
		except (ValueError, TypeError) as e:
			return None

	def findDayTypeDates(self, daytype, beginDate, endDate):
		# Find all dates with the specified "daytype" between
		# "beginDate" and "endDate".
		# XXX: Currently unused.
		try:
			c = self.conn.cursor()
			c.execute("""
				SELECT date FROM override_dayType WHERE
				(value=? AND date>=? AND date<=?);
			""", (daytype, beginDate, endDate))
			dates = c.fetchall()
			return [ d[0] for d in dates ]
		except (ValueError, TypeError) as e:
			return None

	def setShiftOverride(self, date, shift):
		self.__setOverride("override_shift", date, shift)

	def hasShiftOverride(self, date):
		return self.__hasOverride("override_shift", date)

	def getShiftOverride(self, date):
		try:
			return int(self.__getOverride("override_shift", date), 10)
		except (ValueError, TypeError) as e:
			return None

	def setWorkTimeOverride(self, date, workTime):
		self.__setOverride("override_workTime", date, workTime)

	def hasWorkTimeOverride(self, date):
		return self.__hasOverride("override_workTime", date)

	def getWorkTimeOverride(self, date):
		try:
			return float(self.__getOverride("override_workTime", date))
		except (ValueError, TypeError) as e:
			return None

	def setBreakTimeOverride(self, date, breakTime):
		self.__setOverride("override_breakTime", date, breakTime)

	def hasBreakTimeOverride(self, date):
		return self.__hasOverride("override_breakTime", date)

	def getBreakTimeOverride(self, date):
		try:
			return float(self.__getOverride("override_breakTime", date))
		except (ValueError, TypeError) as e:
			return None

	def setAttendanceTimeOverride(self, date, attendanceTime):
		self.__setOverride("override_attendanceTime", date, attendanceTime)

	def hasAttendanceTimeOverride(self, date):
		return self.__hasOverride("override_attendanceTime", date)

	def getAttendanceTimeOverride(self, date):
		try:
			return float(self.__getOverride("override_attendanceTime", date))
		except (ValueError, TypeError) as e:
			return None

	def setShiftConfigItems(self, items):
		self.cachedShiftConfig = items
		try:
			c = self.conn.cursor()
			c.execute("DROP TABLE IF EXISTS shiftConfig;")
			c.execute("CREATE TABLE %s;" % self.TAB_shconf)
			for (index, item) in enumerate(items):
				c.execute("INSERT INTO shiftConfig(idx, item) VALUES(?, ?);",
					  (index, item))
			self.scheduleCommit()
		except (sql.Error) as e:
			self.__sqlError(e)

	def getShiftConfigItems(self):
		if self.cachedShiftConfig is not None:
			return self.cachedShiftConfig
		try:
			c = self.conn.cursor()
			c.execute("CREATE TABLE IF NOT EXISTS %s;" % self.TAB_shconf)
			c.execute('SELECT item FROM shiftConfig ORDER BY "idx";')
			items = c.fetchall()
			items = [ i[0] for i in items ]
			self.cachedShiftConfig = items
			return items
		except (sql.Error) as e:
			self.__sqlError(e)

	def setPresets(self, presets):
		try:
			c = self.conn.cursor()
			c.execute("DROP TABLE IF EXISTS presets;")
			c.execute("CREATE TABLE %s;" % self.TAB_presets)
			for (index, preset) in enumerate(presets):
				c.execute("INSERT INTO presets(idx, preset) VALUES(?, ?);",
					  (index, preset))
			self.scheduleCommit()
		except (sql.Error) as e:
			self.__sqlError(e)

	def getPresets(self):
		try:
			c = self.conn.cursor()
			c.execute("CREATE TABLE IF NOT EXISTS %s;" % self.TAB_presets)
			c.execute('SELECT preset FROM presets ORDER BY "idx";')
			presets = c.fetchall()
			return [ p[0] for p in presets ]
		except (sql.Error) as e:
			self.__sqlError(e)

	def setSnapshot(self, date, snapshot):
		try:
			c = self.conn.cursor()
			c.execute("DELETE FROM snapshots WHERE date=?;", (date,))
			if snapshot is not None:
				c.execute("INSERT INTO snapshots(date, snapshot) VALUES(?, ?);",
					  (date, snapshot))
			self.scheduleCommit()
		except (sql.Error) as e:
			self.__sqlError(e)

	def hasSnapshot(self, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT COUNT(*) FROM snapshots WHERE date=?;", (date,))
			value = c.fetchone()
			if value:
				return value[0] > 0
			return False
		except (sql.Error) as e:
			self.__sqlError(e)

	def getSnapshot(self, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT snapshot FROM snapshots WHERE date=?;", (date,))
			snapshot = c.fetchone()
			if snapshot:
				snapshot = snapshot[0]
			return snapshot
		except (sql.Error) as e:
			self.__sqlError(e)

	def getAllSnapshots(self):
		try:
			c = self.conn.cursor()
			c.execute("SELECT snapshot FROM snapshots;")
			snapshots = c.fetchall()
			return [ s[0] for s in snapshots ]
		except (sql.Error) as e:
			self.__sqlError(e)

	def findSnapshotForDate(self, date):
		# Get the snapshot that is active for a certain date.
		try:
			c = self.conn.cursor()
			c.execute("SELECT snapshot FROM snapshots WHERE date<=? "
				  "ORDER BY date DESC", (date,))
			snapshot = c.fetchone()
			if snapshot:
				return snapshot[0]
			return None
		except (sql.Error) as e:
			self.__sqlError(e)

	def setComment(self, date, comment):
		try:
			c = self.conn.cursor()
			c.execute("DELETE FROM comments WHERE date=?;", (date,))
			if comment:
				c.execute("INSERT INTO comments(date, comment) VALUES(?, ?);",
					  (date, str(comment)))
			self.scheduleCommit()
		except (sql.Error) as e:
			self.__sqlError(e)

	def hasComment(self, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT COUNT(*) FROM comments WHERE date=?;", (date,))
			value = c.fetchone()
			if value:
				return value[0] > 0
			return False
		except (sql.Error) as e:
			self.__sqlError(e)

	def getComment(self, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT comment FROM comments WHERE date=?;", (date,))
			comment = c.fetchone()
			if comment:
				comment = comment[0]
			return comment
		except (sql.Error) as e:
			self.__sqlError(e)

class TimeSpinBox(QDoubleSpinBox):
	def __init__(self, parent, val=0.0, minVal=0.0, maxVal=24.0,
		     step=0.1, decimals=2, prefix=None, suffix="h"):
		QDoubleSpinBox.__init__(self, parent)
		self.setDecimals(decimals)
		self.setMinimum(minVal)
		self.setMaximum(maxVal)
		self.setValue(val)
		self.setSingleStep(step)
		self.setAccelerated(True)
		self.setKeyboardTracking(False)
		if suffix:
			self.setSuffix(" " + suffix)
		if prefix:
			self.setPrefix(prefix + " ")

class DaySpinBox(QSpinBox):
	def __init__(self, parent, val=0, minVal=0, maxVal=365,
		     step=1, prefix=None, suffix="Tage"):
		QSpinBox.__init__(self, parent)
		self.setMinimum(minVal)
		self.setMaximum(maxVal)
		self.setValue(val)
		self.setSingleStep(step)
		if suffix:
			self.setSuffix(" " + suffix)
		if prefix:
			self.setPrefix(prefix + " ")

class ShiftConfigDialog(QDialog):
	def __init__(self, mainWidget):
		QDialog.__init__(self, mainWidget)
		self.mainWidget = mainWidget
		self.setWindowTitle("Schichtkonfiguration")
		self.setLayout(QGridLayout())

		self.itemList = QListWidget(self)
		self.layout().addWidget(self.itemList, 0, 0, 10, 2)

		self.addButton = QPushButton("Neu", self)
		self.layout().addWidget(self.addButton, 11, 0)

		self.removeButton = QPushButton("Loeschen", self)
		self.layout().addWidget(self.removeButton, 11, 1)

		label = QLabel("Name", self)
		self.layout().addWidget(label, 0, 2)
		self.nameEdit = QLineEdit(self)
		self.layout().addWidget(self.nameEdit, 0, 3)

		label = QLabel("Schicht", self)
		self.layout().addWidget(label, 1, 2)
		self.shiftCombo = ShiftComboBox(self, shortNames=True)
		self.layout().addWidget(self.shiftCombo, 1, 3)

		label = QLabel("Arbeitszeit", self)
		self.layout().addWidget(label, 2, 2)
		self.workTime = TimeSpinBox(self)
		self.layout().addWidget(self.workTime, 2, 3)

		label = QLabel("Pausenzeit", self)
		self.layout().addWidget(label, 3, 2)
		self.breakTime = TimeSpinBox(self)
		self.layout().addWidget(self.breakTime, 3, 3)

		label = QLabel("Anwesenheit", self)
		self.layout().addWidget(label, 4, 2)
		self.attendanceTime = TimeSpinBox(self)
		self.layout().addWidget(self.attendanceTime, 4, 3)

		self.updateBlocked = False
		self.loadConfig()

		self.itemList.currentRowChanged.connect(self.itemChanged)
		self.addButton.released.connect(self.addItem)
		self.removeButton.released.connect(self.removeItem)

		self.nameEdit.textChanged.connect(self.updateCurrentItem)
		self.shiftCombo.currentIndexChanged.connect(self.updateCurrentItem)
		self.workTime.valueChanged.connect(self.updateCurrentItem)
		self.breakTime.valueChanged.connect(self.updateCurrentItem)
		self.attendanceTime.valueChanged.connect(self.updateCurrentItem)

	def setInputEnabled(self, enable):
		self.removeButton.setEnabled(enable)
		self.nameEdit.setEnabled(enable)
		self.shiftCombo.setEnabled(enable)
		self.workTime.setEnabled(enable)
		self.breakTime.setEnabled(enable)
		self.attendanceTime.setEnabled(enable)

	def loadConfig(self):
		self.itemList.clear()
		shiftConfig = self.mainWidget.db.getShiftConfigItems()
		count = 1
		for cfg in shiftConfig:
			name = "%d \"%s\"" % (count, cfg.name)
			count += 1
			self.itemList.addItem(name)
		if shiftConfig:
			self.itemList.setCurrentRow(0)
			currentItem = shiftConfig[0]
		else:
			currentItem = None
		self.loadItem(currentItem)
		self.setInputEnabled(currentItem is not None)

	def loadItem(self, item=None):
		self.updateBlocked = True
		self.nameEdit.clear()
		self.shiftCombo.setCurrentIndex(0)
		self.workTime.setValue(0.0)
		self.breakTime.setValue(0.0)
		self.attendanceTime.setValue(0.0)
		if item:
			self.nameEdit.setText(item.name)
			index = self.shiftCombo.findData(item.shift)
			self.shiftCombo.setCurrentIndex(index)
			self.workTime.setValue(item.workTime)
			self.breakTime.setValue(item.breakTime)
			self.attendanceTime.setValue(item.attendanceTime)
		self.updateBlocked = False

	def updateItem(self, item):
		item.name = self.nameEdit.text()
		index = self.shiftCombo.currentIndex()
		item.shift = self.shiftCombo.itemData(index)
		item.workTime = self.workTime.value()
		item.breakTime = self.breakTime.value()
		item.attendanceTime = self.attendanceTime.value()

	def itemChanged(self, row):
		if row >= 0:
			shiftConfig = self.mainWidget.db.getShiftConfigItems()
			self.loadItem(shiftConfig[row])

	def updateCurrentItem(self):
		if self.updateBlocked:
			return
		index = self.itemList.currentRow()
		if index < 0:
			return
		shiftConfig = self.mainWidget.db.getShiftConfigItems()
		self.updateItem(shiftConfig[index])
		self.mainWidget.db.setShiftConfigItems(shiftConfig)
		name = "%d \"%s\"" % (index + 1, shiftConfig[index].name)
		self.itemList.item(index).setText(name)

	def addItem(self):
		shiftConfig = self.mainWidget.db.getShiftConfigItems()
		index = self.itemList.currentRow()
		if index < 0:
			index = 0
		else:
			index += 1
		item = ShiftConfigItem("Unbenannt", SHIFT_DAY, 7.0, 0.75, 8.0)
		shiftConfig.insert(index, item)
		self.mainWidget.db.setShiftConfigItems(shiftConfig)
		self.loadConfig()
		self.itemList.setCurrentRow(index)

	def removeItem(self):
		index = self.itemList.currentRow()
		if index < 0:
			return
		for snapshot in self.mainWidget.db.getAllSnapshots():
			if snapshot.shiftConfigIndex >= self.itemList.count() - 1:
				dateString = snapshot.date.toString("dd.MM.yyyy")
				QMessageBox.critical(self, "Eintrag wird verwendet",
					"Der Eintrag wird von einem Schnappschuss (%s) verwendet. "
					"Loeschen nicht moeglich." % dateString)
				return
		res = QMessageBox.question(self, "Eintrag loeschen?",
					   "'%s' loeschen?" % self.itemList.item(index).text(),
					   QMessageBox.Yes | QMessageBox.No)
		if res != QMessageBox.Yes:
			return
		shiftConfig = self.mainWidget.db.getShiftConfigItems()
		shiftConfig.pop(index)
		self.mainWidget.db.setShiftConfigItems(shiftConfig)
		self.loadConfig()
		if index >= self.itemList.count() and index > 0:
			index -= 1
		self.itemList.setCurrentRow(index)

class EnhancedDialog(QDialog):
	def __init__(self, mainWidget):
		QDialog.__init__(self, mainWidget)
		self.mainWidget = mainWidget

		date = mainWidget.calendar.selectedDate()
		dayFlags = mainWidget.db.getDayFlags(date)

		self.setWindowTitle("Erweitert")
		self.setLayout(QGridLayout())

		self.commentGroup = QGroupBox("Kommentar", self)
		self.commentGroup.setLayout(QGridLayout())
		self.layout().addWidget(self.commentGroup, 0, 0)

		self.comment = QTextEdit(self)
		self.commentGroup.layout().addWidget(self.comment, 0, 0)
		self.comment.document().setPlainText(mainWidget.getCommentFor(date))

		self.flagsGroup = QGroupBox("Tagesoptionen", self)
		self.flagsGroup.setLayout(QGridLayout())
		self.layout().addWidget(self.flagsGroup, 1, 0)

		self.uncertainCheckBox = QCheckBox("Unbestaetigt", self)
		self.flagsGroup.layout().addWidget(self.uncertainCheckBox, 0, 0)
		cs = Qt.Checked if dayFlags & DFLAG_UNCERTAIN else Qt.Unchecked
		self.uncertainCheckBox.setCheckState(cs)

		self.attendantCheckBox = QCheckBox("Anwesenheitsmarker", self)
		self.flagsGroup.layout().addWidget(self.attendantCheckBox, 1, 0)
		cs = Qt.Checked if dayFlags & DFLAG_ATTENDANT else Qt.Unchecked
		self.attendantCheckBox.setCheckState(cs)

		self.uncertainCheckBox.stateChanged.connect(self.__flagCheckBoxChanged)
		self.attendantCheckBox.stateChanged.connect(self.__flagCheckBoxChanged)

	def __flagCheckBoxChanged(self, newState):
		self.commitAndAccept()

	def closeEvent(self, e):
		self.commitAndAccept()

	def commitAndAccept(self):
		self.commit()
		self.accept()

	def commit(self):
		date = self.mainWidget.calendar.selectedDate()

		dayFlags = oldDayFlags = self.mainWidget.getDayFlags(date)
		for checkBox, flag in ((self.uncertainCheckBox, DFLAG_UNCERTAIN),
				       (self.attendantCheckBox, DFLAG_ATTENDANT)):
			dayFlags &= ~flag
			dayFlags |= flag if checkBox.checkState() == Qt.Checked else 0
		if dayFlags != oldDayFlags:
			self.mainWidget.setDayFlags(date, dayFlags)
			if dayFlags & DFLAG_ATTENDANT:
				# Automatically reset day type, if attendant flag was set.
				self.mainWidget.setDayType(date, DTYPE_DEFAULT)

		old = self.mainWidget.getCommentFor(date)
		new = self.comment.document().toPlainText()
		if old != new:
			self.mainWidget.setCommentFor(date, new)

		self.mainWidget.recalculate()

class ManageDialog(QDialog):
	def __init__(self, mainWidget):
		QDialog.__init__(self, mainWidget)
		self.mainWidget = mainWidget
		self.setWindowTitle("Verwalten")
		self.setLayout(QGridLayout())

		self.fileGroup = QGroupBox("Datei", self)
		self.fileGroup.setLayout(QGridLayout())
		self.layout().addWidget(self.fileGroup, 0, 0)

		self.setDbButton = QPushButton("Datenbank waehlen", self)
		self.fileGroup.layout().addWidget(self.setDbButton, 0, 0)
		self.setDbButton.released.connect(self.loadDatabase)

		self.resetCalButton = QPushButton("Kalender loeschen", self)
		self.fileGroup.layout().addWidget(self.resetCalButton, 1, 0)
		self.resetCalButton.released.connect(self.resetCalendar)

		self.schedConfButton = QPushButton("Schichtkonfig", self)
		self.fileGroup.layout().addWidget(self.schedConfButton, 2, 0)
		self.schedConfButton.released.connect(self.doShiftConfig)

		self.icalButton = QPushButton("iCalendar import", self)
		self.fileGroup.layout().addWidget(self.icalButton, 3, 0)
		self.icalButton.released.connect(self.icalImport)

	def loadDatabase(self):
		self.mainWidget.loadDatabase()
		self.accept()

	def resetCalendar(self):
		res = QMessageBox.question(self, "Kalender loeschen?",
					   "Wollen Sie wirklich alle Kalendereintraege "
					   "und Parameter loeschen?",
					   QMessageBox.Yes | QMessageBox.No)
		if res == QMessageBox.Yes:
			self.mainWidget.resetState()
			self.accept()

	def doShiftConfig(self):
		dlg = ShiftConfigDialog(self.mainWidget)
		dlg.exec_()
		self.mainWidget.worldUpdate()
		self.accept()

	def icalImport(self):
		dlg = ICalImportDialog(self.mainWidget, self.mainWidget.db)
		dlg.exec_()
		self.mainWidget.worldUpdate()
		self.accept()

class PresetDialog(QDialog):
	def __init__(self, mainWidget):
		QDialog.__init__(self, mainWidget)
		self.setWindowTitle("Vorgaben")
		self.setLayout(QGridLayout())
		self.mainWidget = mainWidget

		self.presetList = QListWidget(self)
		self.layout().addWidget(self.presetList, 0, 0, 4, 2)

		self.addButton = QPushButton("Neu", self)
		self.layout().addWidget(self.addButton, 4, 0)

		self.removeButton = QPushButton("Loeschen", self)
		self.layout().addWidget(self.removeButton, 4, 1)

		self.commitButton = QPushButton("Vorgabe uebernehmen", self)
		self.layout().addWidget(self.commitButton, 5, 0, 1, 2)

		self.nameEdit = QLineEdit(self)
		self.layout().addWidget(self.nameEdit, 0, 2)

		self.typeCombo = DayTypeComboBox(self)
		self.layout().addWidget(self.typeCombo, 1, 2)

		self.shiftCombo = ShiftComboBox(self)
		self.layout().addWidget(self.shiftCombo, 2, 2)

		self.workTime = TimeSpinBox(self, prefix="Arb.zeit")
		self.layout().addWidget(self.workTime, 3, 2)

		self.breakTime = TimeSpinBox(self, prefix="Pause")
		self.layout().addWidget(self.breakTime, 4, 2)

		self.attendanceTime = TimeSpinBox(self, prefix="Anwes.")
		self.layout().addWidget(self.attendanceTime, 5, 2)

		self.presetChangeBlocked = False

		self.loadPresets()
		self.presetSelectionChanged()

		self.presetList.currentRowChanged.connect(self.presetSelectionChanged)
		self.presetList.itemDoubleClicked.connect(self.commitPressed)
		self.addButton.released.connect(self.addPreset)
		self.removeButton.released.connect(self.removePreset)
		self.commitButton.released.connect(self.commitPressed)

		self.nameEdit.textChanged.connect(self.presetChanged)
		self.typeCombo.currentIndexChanged.connect(self.presetChanged)
		self.shiftCombo.currentIndexChanged.connect(self.presetChanged)
		self.workTime.valueChanged.connect(self.presetChanged)
		self.breakTime.valueChanged.connect(self.presetChanged)
		self.attendanceTime.valueChanged.connect(self.presetChanged)

	def __addPreset(self, preset):
		item = QListWidgetItem(preset.name)
		item.setData(Qt.UserRole, Wrapper(preset))
		self.presetList.addItem(item)

	def loadPresets(self):
		date = self.mainWidget.calendar.selectedDate()
		shiftConfigItem = self.mainWidget.getShiftConfigItemForDate(date)
		assert(shiftConfigItem)
		self.presetList.clear()
		self.__addPreset( # index0 => special for reset
			Preset(name="--- zuruecksetzen ---",
				dayType=DTYPE_DEFAULT,
				shift=shiftConfigItem.shift,
				workTime=shiftConfigItem.workTime,
				breakTime=shiftConfigItem.breakTime,
				attendanceTime=shiftConfigItem.attendanceTime
			)
		)
		for preset in self.mainWidget.db.getPresets():
			self.__addPreset(preset)
		self.presetList.setCurrentRow(0)

	def applyPreset(self, preset):
		mainWidget = self.mainWidget
		index = mainWidget.typeCombo.findData(preset.dayType)
		mainWidget.typeCombo.setCurrentIndex(index)
		index = mainWidget.shiftCombo.findData(preset.shift)
		mainWidget.shiftCombo.setCurrentIndex(index)
		mainWidget.workTime.setValue(preset.workTime)
		mainWidget.breakTime.setValue(preset.breakTime)
		mainWidget.attendanceTime.setValue(preset.attendanceTime)

	def __enableEdit(self, enable):
		self.nameEdit.setEnabled(enable)
		self.typeCombo.setEnabled(enable)
		self.shiftCombo.setEnabled(enable)
		self.workTime.setEnabled(enable)
		self.breakTime.setEnabled(enable)
		self.attendanceTime.setEnabled(enable)

	def presetSelectionChanged(self):
		index = self.presetList.currentRow()
		self.__enableEdit(index > 0)
		self.removeButton.setEnabled(index > 0)
		self.commitButton.setEnabled(index >= 0)
		item = self.presetList.currentItem()
		if not item:
			return
		preset = item.data(Qt.UserRole).obj
		self.presetChangeBlocked = True
		self.nameEdit.setText(preset.name)
		index = self.typeCombo.findData(preset.dayType)
		self.typeCombo.setCurrentIndex(index)
		index = self.shiftCombo.findData(preset.shift)
		self.shiftCombo.setCurrentIndex(index)
		self.workTime.setValue(preset.workTime)
		self.breakTime.setValue(preset.breakTime)
		self.attendanceTime.setValue(preset.attendanceTime)
		self.presetChangeBlocked = False

	def __updatePresetItem(self, preset):
		preset.name = self.nameEdit.text()
		index = self.typeCombo.currentIndex()
		preset.dayType = self.typeCombo.itemData(index)
		index = self.shiftCombo.currentIndex()
		preset.shift = self.shiftCombo.itemData(index)
		preset.workTime = self.workTime.value()
		preset.breakTime = self.breakTime.value()
		preset.attendanceTime = self.attendanceTime.value()

	def presetChanged(self):
		if self.presetChangeBlocked:
			return
		row = self.presetList.currentRow()
		if row <= 0:
			return
		item = self.presetList.item(row)
		item.setText(self.nameEdit.text())
		self.__updatePresetItem(item.data(Qt.UserRole).obj)
		presets = self.mainWidget.db.getPresets()
		self.__updatePresetItem(presets[row - 1])
		self.mainWidget.db.setPresets(presets)

	def addPreset(self):
		presets = self.mainWidget.db.getPresets()
		index = self.presetList.currentRow()
		if index <= 0:
			index = 1
		else:
			index += 1
		date = self.mainWidget.calendar.selectedDate()
		shiftConfigItem = self.mainWidget.getShiftConfigItemForDate(date)
		preset = Preset(name="Unbenannt",
				dayType=DTYPE_DEFAULT,
				shift=shiftConfigItem.shift,
				workTime=shiftConfigItem.workTime,
				breakTime=shiftConfigItem.breakTime,
				attendanceTime=shiftConfigItem.attendanceTime
			)
		presets.insert(index - 1, preset)
		self.mainWidget.db.setPresets(presets)
		self.loadPresets()
		self.presetList.setCurrentRow(index)

	def removePreset(self):
		index = self.presetList.currentRow()
		if index <= 0:
			return
		res = QMessageBox.question(self, "Vorgabe loeschen?",
					   "'%s' loeschen?" % self.presetList.item(index).text(),
					   QMessageBox.Yes | QMessageBox.No)
		if res != QMessageBox.Yes:
			return
		presets = self.mainWidget.db.getPresets()
		presets.pop(index - 1)
		self.mainWidget.db.setPresets(presets)
		self.loadPresets()
		if index >= self.presetList.count() and index > 0:
			index -= 1
		self.presetList.setCurrentRow(index)

	def commitPressed(self):
		item = self.presetList.currentItem()
		if item:
			preset = item.data(Qt.UserRole).obj
			self.applyPreset(preset)
			self.accept()

class SnapshotDialog(QDialog):
	def __init__(self, mainWidget, accountState):
		QDialog.__init__(self, mainWidget)
		self.setWindowTitle("Schnappschuss setzen")
		self.setLayout(QGridLayout())
		self.mainWidget = mainWidget
		self.date = accountState.date

		self.dateLabel = QLabel(self.date.toString("dddd, dd.MM.yyyy"), self)
		self.layout().addWidget(self.dateLabel, 0, 0)

		l = QLabel("Startschicht:", self)
		self.layout().addWidget(l, 1, 0)
		self.shiftConfig = QComboBox(self)
		shiftConfig = mainWidget.db.getShiftConfigItems()
		assert(shiftConfig)
		for index, cfg in enumerate(shiftConfig):
			name = "%d \"%s\"" % (index + 1, cfg.name)
			self.shiftConfig.addItem(name, index)
		self.layout().addWidget(self.shiftConfig, 1, 1)
		index = self.shiftConfig.findData(accountState.shiftConfigIndex)
		if index >= 0:
			self.shiftConfig.setCurrentIndex(index)

		l = QLabel("Zeitkontostand:", self)
		self.layout().addWidget(l, 2, 0)
		self.accountValue = TimeSpinBox(self,
				val=accountState.accountAtStartOfDay,
				minVal=-1000.0, maxVal=1000.0,
				step=0.1, decimals=1)
		self.layout().addWidget(self.accountValue, 2, 1)

		l = QLabel("Urlaubsstand:", self)
		self.layout().addWidget(l, 3, 0)
		self.holidays = DaySpinBox(self,
				val=accountState.holidaysAtStartOfDay)
		self.layout().addWidget(self.holidays, 3, 1)

		self.removeButton = QPushButton("Schnappschuss loeschen", self)
		self.layout().addWidget(self.removeButton, 4, 0, 1, 2)
		self.removeButton.released.connect(self.removeSnapshot)
		if not mainWidget.dateHasSnapshot(self.date):
			self.removeButton.hide()

		self.okButton = QPushButton("Setzen", self)
		self.layout().addWidget(self.okButton, 5, 0)
		self.okButton.released.connect(self.ok)

		self.cancelButton = QPushButton("Abbrechen", self)
		self.layout().addWidget(self.cancelButton, 5, 1)
		self.cancelButton.released.connect(self.cancel)

	def ok(self):
		self.accept()

	def cancel(self):
		self.reject()

	def removeSnapshot(self):
		res = QMessageBox.question(self, "Schnappschuss loeschen?",
					   "Wollen Sie den Schnappschuss wirklich loeschen?",
					   QMessageBox.Yes | QMessageBox.No)
		if res == QMessageBox.Yes:
			self.mainWidget.removeSnapshot(self.date)
			self.reject()

	def getSnapshot(self):
		index = self.shiftConfig.currentIndex()
		shiftConfigIndex = self.shiftConfig.itemData(index)
		accValue = self.accountValue.value()
		holidaysLeft = self.holidays.value()
		return Snapshot(self.date, shiftConfigIndex,
				accValue, holidaysLeft)

class Calendar(QCalendarWidget):
	def __init__(self, mainWidget):
		self.__initPens()
		QCalendarWidget.__init__(self, mainWidget)
		self.mainWidget = mainWidget

		self.setFirstDayOfWeek(Qt.Monday)

		self.today = QDate.currentDate()
		self.armTodayTimer()

	def todayTimer(self):
		self.today = self.today.addDays(1)
		self.setSelectedDate(self.today)
		self.armTodayTimer()
		self.redraw()

	def armTodayTimer(self):
		tomorrow = QDateTime(self.today)
		tomorrow = tomorrow.addDays(1)
		secs = QDateTime.currentDateTime().secsTo(tomorrow)
		QTimer.singleShot(secs * 1000, self.todayTimer)

	def __initPens(self):
		self.snapshotPen = QPen(QColor("#007FFF"))
		self.snapshotPen.setWidth(5)

		self.framePen = QPen(QColor("#006400"))
		self.framePen.setWidth(1)

		self.todayPen = QPen(QColor("#006400"))
		self.todayPen.setWidth(6)

		self.commentPen = QPen(QColor("#FF0000"))
		self.commentPen.setWidth(2)

		self.overridesPen = QPen(QColor("#9F9F9F"))
		self.overridesPen.setWidth(5)

		self.centerPen = QPen(QColor("#007FFF"))
		self.centerPen.setWidth(1)

		self.lowerLeftPen = QPen(QColor("#FF0000"))
		self.lowerLeftPen.setWidth(1)

		self.lowerRightPen = QPen(QColor("#304F7F"))
		self.lowerRightPen.setWidth(1)

	typeLetter = {
		DTYPE_DEFAULT		: None,
		DTYPE_COMPTIME		: "Z",
		DTYPE_HOLIDAY		: "U",
		DTYPE_SHORTTIME		: "C",
		DTYPE_FEASTDAY		: "F",
	}

	shiftLetter = {
		SHIFT_EARLY	: "F",
		SHIFT_LATE	: "S",
		SHIFT_NIGHT	: "N",
		SHIFT_DAY	: "O",
	}

	def paintCell(self, painter, rect, date):
		QCalendarWidget.paintCell(self, painter, rect, date)
		painter.save()

		mainWidget, font = self.mainWidget, painter.font()
		db = mainWidget.db
		rx, ry, rw, rh = rect.x(), rect.y(), rect.width(), rect.height()
		dayFlags = db.getDayFlags(date)

		font.setBold(True)
		painter.setFont(font)

		if mainWidget.dateHasSnapshot(date):
			painter.setPen(self.snapshotPen)
		else:
			painter.setPen(self.framePen)
		painter.drawRect(rx, ry, rw - 1, rh - 1)

		if date == self.today:
			painter.setPen(self.todayPen)
			for (x, y) in ((3, 3), (rw - 3, 3),
				       (3, rh - 3),
				       (rw - 3, rh - 3)):
				painter.drawPoint(rx + x, ry + y)

		if mainWidget.dateHasComment(date):
			painter.setPen(self.commentPen)
			painter.drawRect(rx + 3, ry + 3, rw - 3 - 3, rh - 3 - 3)

		if mainWidget.dateHasTimeOverrides(date):
			painter.setPen(self.overridesPen)
			painter.drawPoint(rx + rw - 8, ry + 8)

		text = self.typeLetter[mainWidget.getDayType(date)]
		if not text:
			if dayFlags & DFLAG_ATTENDANT:
				text = "A"
		if text:
			painter.setPen(self.lowerLeftPen)
			painter.drawText(rx + 4, ry + rh - 4, text)

		shiftOverride = db.getShiftOverride(date)
		if shiftOverride is not None:
			text = self.shiftLetter[shiftOverride]
			painter.setPen(self.lowerRightPen)
			metrics = QFontMetrics(painter.font())
			painter.drawText(rx + rw - metrics.width(text) - 4,
					 ry + rh - 4,
					 text)

		if dayFlags & DFLAG_UNCERTAIN:
			text = "???"
			painter.setPen(self.centerPen)
			metrics = QFontMetrics(painter.font())
			painter.drawText(rx + rw // 2 - metrics.width(text) // 2,
					 ry + rh // 2 + metrics.height() // 2,
					 text)

		painter.restore()

	def redraw(self):
		if self.isVisible():
			self.hide()
			self.show()

class AccountState(QObject):
	"Calculated account state."

	def __init__(self, date, shiftConfigIndex=0,
		     accountAtStartOfDay=0.0, accountAtEndOfDay=0.0,
		     holidaysAtStartOfDay=0, holidaysAtEndOfDay=0):
		QObject.__init__(self)
		self.date = date
		self.shiftConfigIndex = shiftConfigIndex
		self.accountAtStartOfDay = accountAtStartOfDay
		self.accountAtEndOfDay = accountAtEndOfDay
		self.holidaysAtStartOfDay = holidaysAtStartOfDay
		self.holidaysAtEndOfDay = holidaysAtEndOfDay

class MainWidget(QWidget):
	def __init__(self, parent=None):
		QWidget.__init__(self, parent)

		self.setFocusPolicy(Qt.StrongFocus)
		self.setLayout(QGridLayout())

		self.worldUpdateTimer = QTimer(self)
		self.worldUpdateTimer.setSingleShot(True)
		self.worldUpdateTimer.timeout.connect(self.__worldUpdateTimerTimeout)

		self.calendar = Calendar(self)
		self.layout().addWidget(self.calendar, 0, 0, 5, 3)

		self.typeCombo = DayTypeComboBox(self)
		self.layout().addWidget(self.typeCombo, 0, 4)

		self.shiftCombo = ShiftComboBox(self)
		self.layout().addWidget(self.shiftCombo, 1, 4)

		self.workTime = TimeSpinBox(self, prefix="Arb.zeit")
		self.layout().addWidget(self.workTime, 2, 4)

		self.breakTime = TimeSpinBox(self, prefix="Pause")
		self.layout().addWidget(self.breakTime, 3, 4)

		self.attendanceTime = TimeSpinBox(self, prefix="Anwes.")
		self.layout().addWidget(self.attendanceTime, 4, 4)

		self.presetButton = QPushButton("Vorgaben", self)
		self.layout().addWidget(self.presetButton, 5, 4)
		self.presetButton.released.connect(self.doPresets)

		self.calendar.selectionChanged.connect(self.recalculate)
		self.typeCombo.currentIndexChanged.connect(self.overrideChanged)
		self.shiftCombo.currentIndexChanged.connect(self.overrideChanged)
		self.workTime.valueChanged.connect(self.overrideChanged)
		self.breakTime.valueChanged.connect(self.overrideChanged)
		self.attendanceTime.valueChanged.connect(self.overrideChanged)
		self.overrideChangeBlocked = False

		self.manageButton = QPushButton("Verwalten", self)
		self.layout().addWidget(self.manageButton, 5, 0)
		self.manageButton.released.connect(self.doManage)

		self.snapshotButton = QPushButton("Schnappschuss", self)
		self.layout().addWidget(self.snapshotButton, 5, 1)
		self.snapshotButton.released.connect(self.doSnapshot)

		self.enhancedButton = QPushButton("Erweitert", self)
		self.layout().addWidget(self.enhancedButton, 5, 2)
		self.enhancedButton.released.connect(self.doEnhanced)

		self.output = QLabel(self)
		self.output.setAlignment(Qt.AlignHCenter)
		self.output.setFrameShape(QFrame.Panel)
		self.output.setFrameShadow(QFrame.Raised)
		self.layout().addWidget(self.output, 8, 0, 1, 6)

		self.db = TsDatabase()
		self.resetState()

	def shutdown(self):
		self.db.close()

	def resetState(self):
		self.db.resetDatabase()
		self.worldUpdate()

	def worldUpdate(self):
		self.updateTitle()
		self.recalculate()
		self.calendar.redraw()

	def __worldUpdateTimerTimeout(self):
		self.worldUpdate()

	def scheduleWorldUpdate(self, msec=1000):
		self.worldUpdateTimer.start(msec)

	def doLoadDatabase(self, filename):
		try:
			fi = QFileInfo(filename)
			if not fi.exists() and self.db.isInMemory():
				# Clone the in-memory DB to the new file
				self.db.clone(filename)
			self.db.open(filename)
			self.worldUpdate()
		except (TsException) as e:
			QMessageBox.critical(self, "Laden fehlgeschlagen",
					     "Laden fehlgeschlagen:\n" + str(e))
			return False
		return True

	def loadDatabase(self):
		fn = QFileDialog.getSaveFileName(self, "Datenbank laden", "",
						 "Timeshift Dateien (*.tmd *.tms *.tmz);;"
						 "Alle Dateien (*)",
						 "", QFileDialog.DontConfirmOverwrite |
						     QFileDialog.DontUseNativeDialog)
		if usingPySide:
			fn = fn[0]
		if fn:
			self.doLoadDatabase(fn)

	def updateTitle(self):
		if self.db.isInMemory():
			suffix = "<in memory>"
		else:
			fi = QFileInfo(self.db.getFilename())
			suffix = fi.fileName()
		self.parent().setTitleSuffix(suffix)

	def dateHasComment(self, date):
		return self.db.hasComment(date)

	def getCommentFor(self, date):
		comment = self.db.getComment(date)
		return comment if comment else ""

	def setCommentFor(self, date, text):
		self.db.setComment(date, text)

	def doEnhanced(self):
		dlg = EnhancedDialog(self)
		dlg.exec_()

	def doManage(self):
		dlg = ManageDialog(self)
		dlg.exec_()

	def doPresets(self):
		dlg = PresetDialog(self)
		dlg.exec_()

	def __removeSnapshot(self, date):
		self.db.setSnapshot(date, None)

	def removeSnapshot(self, date):
		self.__removeSnapshot(date)
		self.worldUpdate()

	def __setSnapshot(self, snapshot):
		self.db.setSnapshot(snapshot.date, snapshot)

	def doSnapshot(self):
		if not self.db.getShiftConfigItems():
			QMessageBox.critical(self, "Kein Schichtsystem",
					     "Kein Schichtsystem konfiguriert")
			return
		date = self.calendar.selectedDate()
		snapshot = self.getSnapshotFor(date)
		accState = AccountState(date)
		if snapshot is None:
			# Calculate the account state w.r.t. the
			# last shapshot.
			snapshot = self.db.findSnapshotForDate(date)
			if snapshot:
				accState = self.__calcAccountState(
					snapshot, date)
		else:
			# We already have a snapshot on that day. Modify it.
			accState.shiftConfigIndex = snapshot.shiftConfigIndex
			accState.accountAtStartOfDay = snapshot.accountValue
			accState.holidaysAtStartOfDay = snapshot.holidaysLeft
		dlg = SnapshotDialog(self, accState)
		if dlg.exec_():
			self.__setSnapshot(dlg.getSnapshot())
			self.worldUpdate()

	def dateHasSnapshot(self, date):
		return self.db.hasSnapshot(date)

	def getSnapshotFor(self, date):
		return self.db.getSnapshot(date)

	def overrideChanged(self):
		if self.overrideChangeBlocked or not self.db.getShiftConfigItems():
			return
		date = self.calendar.selectedDate()
		shiftConfigItem = self.getShiftConfigItemForDate(date)
		assert(shiftConfigItem)

		# Day type
		index = self.typeCombo.currentIndex()
		self.setDayType(date, self.typeCombo.itemData(index))

		# Shift override
		index = self.shiftCombo.currentIndex()
		shift = self.shiftCombo.itemData(index)
		if shift == shiftConfigItem.shift:
			shift = None
		self.setShiftOverride(date, shift)

		# Work time override
		workTime = self.workTime.value()
		if floatEqual(workTime, shiftConfigItem.workTime):
			workTime = None
		self.setWorkTimeOverride(date, workTime)

		# Break time override
		breakTime = self.breakTime.value()
		if floatEqual(breakTime, shiftConfigItem.breakTime):
			breakTime = None
		self.setBreakTimeOverride(date, breakTime)

		# Attendance time override
		attendanceTime = self.attendanceTime.value()
		if floatEqual(attendanceTime, shiftConfigItem.attendanceTime):
			attendanceTime = None
		self.setAttendanceTimeOverride(date, attendanceTime)

		self.scheduleWorldUpdate()

	def getShiftConfigIndexForDate(self, date):
		# Find the shift config index that's valid for the date.
		# May return -1 on error.
		snapshot = self.db.findSnapshotForDate(date)
		if not snapshot:
			return -1
		daysBetween = snapshot.date.daysTo(date)
		assert(daysBetween >= 0)
		index = snapshot.shiftConfigIndex
		index += daysBetween
		index %= len(self.db.getShiftConfigItems())
		return index

	def getShiftConfigItemForDate(self, date):
		index = self.getShiftConfigIndexForDate(date)
		if index >= 0:
			return self.db.getShiftConfigItems()[index]
		return None

	def enableOverrideControls(self, enable):
		self.typeCombo.setEnabled(enable)
		self.shiftCombo.setEnabled(enable)
		self.workTime.setEnabled(enable)
		self.breakTime.setEnabled(enable)
		self.attendanceTime.setEnabled(enable)
		self.presetButton.setEnabled(enable)

	def getDayType(self, date):
		dtype = self.db.getDayTypeOverride(date)
		return dtype if dtype is not None else DTYPE_DEFAULT

	def setDayType(self, date, dtype):
		dtype = dtype if dtype != DTYPE_DEFAULT else None
		self.db.setDayTypeOverride(date, dtype)
		if dtype:
			# Automatically clear attendant flag, if a dtype is set.
			self.setDayFlags(date, self.getDayFlags(date) & ~DFLAG_ATTENDANT)

	def getDayFlags(self, date):
		return self.db.getDayFlags(date)

	def setDayFlags(self, date, newFlags):
		self.db.setDayFlags(date, newFlags)

	def setShiftOverride(self, date, shift):
		self.db.setShiftOverride(date, shift)

	def getRealShift(self, date, shiftConfigItem):
		shift = self.db.getShiftOverride(date)
		return shift if shift is not None else shiftConfigItem.shift

	def setWorkTimeOverride(self, date, workTime):
		self.db.setWorkTimeOverride(date, workTime)

	def getRealWorkTime(self, date, shiftConfigItem):
		time = self.db.getWorkTimeOverride(date)
		return time if time is not None else shiftConfigItem.workTime

	def setBreakTimeOverride(self, date, breakTime):
		self.db.setBreakTimeOverride(date, breakTime)

	def getRealBreakTime(self, date, shiftConfigItem):
		time = self.db.getBreakTimeOverride(date)
		return time if time is not None else shiftConfigItem.breakTime

	def setAttendanceTimeOverride(self, date, attendanceTime):
		self.db.setAttendanceTimeOverride(date, attendanceTime)

	def getRealAttendanceTime(self, date, shiftConfigItem):
		time = self.db.getAttendanceTimeOverride(date)
		return time if time is not None else shiftConfigItem.attendanceTime

	def dateHasTimeOverrides(self, date):
		return self.db.hasAttendanceTimeOverride(date) or\
		       self.db.hasWorkTimeOverride(date) or\
		       self.db.hasBreakTimeOverride(date)

	def __calcAccountState(self, snapshot, endDate):
		shiftConfig = self.db.getShiftConfigItems()
		nrShiftConfigs = len(shiftConfig)
		state = AccountState(
			date = snapshot.date,
			shiftConfigIndex = snapshot.shiftConfigIndex,
			accountAtStartOfDay = snapshot.accountValue,
			accountAtEndOfDay = snapshot.accountValue,
			holidaysAtStartOfDay = snapshot.holidaysLeft,
			holidaysAtEndOfDay = snapshot.holidaysLeft
		)
		assert(state.date <= endDate)
		while True:
			shiftConfigItem = shiftConfig[state.shiftConfigIndex]
			currentShift = self.getRealShift(state.date, shiftConfigItem)
			workTime = self.getRealWorkTime(state.date, shiftConfigItem)
			breakTime = self.getRealBreakTime(state.date, shiftConfigItem)
			attendanceTime = self.getRealAttendanceTime(state.date, shiftConfigItem)

			dtype = self.getDayType(state.date)
			if dtype == DTYPE_DEFAULT:
				if attendanceTime > 0.001:
					state.accountAtEndOfDay += attendanceTime
					state.accountAtEndOfDay -= workTime
					state.accountAtEndOfDay -= breakTime
			elif dtype == DTYPE_COMPTIME:
				state.accountAtEndOfDay -= workTime
			elif dtype == DTYPE_HOLIDAY:
				state.holidaysAtEndOfDay -= 1
			elif dtype in (DTYPE_FEASTDAY, DTYPE_SHORTTIME):
				pass # no change
			else:
				assert(0)

			if state.date == endDate:
				break
			state.date = state.date.addDays(1)
			state.shiftConfigIndex = (state.shiftConfigIndex + 1) % nrShiftConfigs
			state.accountAtStartOfDay = state.accountAtEndOfDay
			state.holidaysAtStartOfDay = state.holidaysAtEndOfDay
		return state

	def recalculate(self):
		selDate = self.calendar.selectedDate()
		shiftConfig = self.db.getShiftConfigItems()

		if not shiftConfig:
			self.output.setText("Kein Schichtsystem konfiguriert")
			self.enableOverrideControls(False)
			return

		# First find the next snapshot.
		snapshot = self.db.findSnapshotForDate(selDate)
		if not snapshot:
			dateString = selDate.toString("dd.MM.yyyy")
			self.output.setText("Kein Schnappschuss vor dem %s gesetzt" %\
					    dateString)
			self.enableOverrideControls(False)
			return

		self.enableOverrideControls(True)

		# Then calculate the account state
		accState = self.__calcAccountState(snapshot, selDate)

		shiftConfigItem = shiftConfig[accState.shiftConfigIndex]
		dtype = self.getDayType(selDate)
		shift = self.getRealShift(selDate, shiftConfigItem)
		workTime = self.getRealWorkTime(selDate, shiftConfigItem)
		breakTime = self.getRealBreakTime(selDate, shiftConfigItem)
		attendanceTime = self.getRealAttendanceTime(selDate, shiftConfigItem)

		self.overrideChangeBlocked = True
		self.typeCombo.setCurrentIndex(self.typeCombo.findData(dtype))
		self.shiftCombo.setCurrentIndex(self.shiftCombo.findData(shift))
		self.workTime.setValue(workTime)
		self.breakTime.setValue(breakTime)
		self.attendanceTime.setValue(attendanceTime)
		self.overrideChangeBlocked = False

		dateString = selDate.toString("dd.MM.yyyy")
		self.output.setText("Konto am %s:  Beginn: %.1f  Ende: %.1f  Urlaub: %d" %\
			(dateString, round(accState.accountAtStartOfDay, 1),
			 round(accState.accountAtEndOfDay, 1),
			 accState.holidaysAtEndOfDay))

class MainWindow(QMainWindow):
	def __init__(self, parent=None):
		QMainWindow.__init__(self, parent)
		self.titleSuffix = None
		self.__updateTitle()

		self.setCentralWidget(MainWidget(self))

	def loadDatabase(self, filename):
		return self.centralWidget().doLoadDatabase(filename)

	def __updateTitle(self):
		title = "Zeitkonto"
		if self.titleSuffix:
			title += " - " + self.titleSuffix
		self.setWindowTitle(title)

	def setTitleSuffix(self, suffix):
		self.titleSuffix = suffix
		self.__updateTitle()

	def closeEvent(self, e):
		self.centralWidget().shutdown()

def main(argv):
	print("Using PySide: %s" % usingPySide)
	app = QApplication(argv)
	mainwnd = MainWindow()
	if len(argv) == 2:
		if not mainwnd.loadDatabase(argv[1]):
			return 1
	mainwnd.show()
	return app.exec_()

if __name__ == "__main__":
	sys.exit(main(sys.argv))
