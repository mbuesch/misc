#!/usr/bin/env python
"""
# timeshift - Simple work time scheduler
# Copyright (c) 2009-2012 Michael Buesch <m@bues.ch>
# Licensed under the GNU/GPL version 2 or later.
"""

import sys
import os
import errno
import base64
import sqlite3 as sql
import traceback

try:
	# Try to use PySide
	raise ImportError #XXX disabled
	from PySide.QtCore import *
	from PySide.QtGui import *
	usingPySide = True
except (ImportError), e:
	# PyQt4 fallback
	from PyQt4.QtCore import *
	from PyQt4.QtGui import *
	usingPySide = False

# Shift types
SHIFT_EARLY		= 0
SHIFT_LATE		= 1
SHIFT_NIGHT		= 2
SHIFT_DAY		= 3

# Day type overrides
DTYPE_DEFAULT		= 0
DTYPE_COMPTIME		= 1
DTYPE_HOLIDAY		= 2
DTYPE_FEASTDAY		= 3
DTYPE_SHORTTIME		= 4

# Day flags
DFLAG_UNCERTAIN		= (1 << 0)
DFLAG_ATTENDANT		= (1 << 1)


# Compat layer
if usingPySide:
	QVariant = lambda obj: obj
	qvariantToPy = lambda variant: variant

	def QStringToBase64(string):
		return base64.standard_b64encode(string)

	def base64ToQString(b64str):
		return base64.standard_b64decode(b64str)
else: # PyQT4
	qvariantToPy = lambda variant: variant.toPyObject()

	def QStringToBase64(qstring):
		if not isinstance(qstring, QString):
			qstring = QString(qstring)
		unistr = unicode(qstring.toUtf8(), "utf-8").encode("utf-8")
		return base64.standard_b64encode(unistr)

	def base64ToQString(b64str):
		unistr = base64.standard_b64decode(b64str).decode("utf-8")
		return QString(unistr)

def floatEqual(f0, f1):
	return abs(f0 - f1) < 0.001

def QDateToId(qdate):
	"Convert a QDate object to a unique integer ID"
	return QDateTime(qdate).toTime_t()

def IdToQDate(id):
	"Convert a unique integer ID to a QDate object"
	return QDateTime.fromTime_t(int(id)).date()

class TsException(Exception): pass

class ShiftConfigItem(object):
	def __init__(self, name, shift, workTime, breakTime, attendanceTime):
		self.name = name
		self.shift = shift
		self.workTime = workTime
		self.breakTime = breakTime
		self.attendanceTime = attendanceTime

	@staticmethod
	def toString(item):
		return ";".join(
			(	QStringToBase64(item.name),
				str(item.shift),
				str(item.workTime),
				str(item.breakTime),
				str(item.attendanceTime),
			)
		)

	@staticmethod
	def fromString(string):
		elems = string.split(";")
		try:
			return ShiftConfigItem(
				base64ToQString(elems[0]),
				int(elems[1]),
				float(elems[2]),
				float(elems[3]),
				float(elems[4])
			)
		except (IndexError, ValueError), e:
			raise TsException("ShiftConfigItem.fromString() "
					  "invalid string: " + str(string))

class Preset(object):
	def __init__(self, name, dayType, shift, workTime, breakTime, attendanceTime):
		self.name = name
		self.dayType = dayType
		self.shift = shift
		self.workTime = workTime
		self.breakTime = breakTime
		self.attendanceTime = attendanceTime

	@staticmethod
	def toString(preset):
		return ";".join(
			(	QStringToBase64(preset.name),
				str(preset.dayType),
				str(preset.shift),
				str(preset.workTime),
				str(preset.breakTime),
				str(preset.attendanceTime),
			)
		)

	@staticmethod
	def fromString(string):
		elems = string.split(";")
		try:
			return Preset(
				base64ToQString(elems[0]),
				int(elems[1]),
				int(elems[2]),
				float(elems[3]),
				float(elems[4]),
				float(elems[5])
			)
		except (IndexError, ValueError), e:
			raise TsException("Preset.fromString() "
					  "invalid string: " + str(string))

class Snapshot(object):
	def __init__(self, date, shiftConfigIndex, accountValue):
		self.date = date
		self.shiftConfigIndex = shiftConfigIndex
		self.accountValue = accountValue

	@staticmethod
	def toString(snapshot):
		return ";".join(
			(	str(QDateToId(snapshot.date)),
				str(snapshot.shiftConfigIndex),
				str(snapshot.accountValue),
			)
		)

	@staticmethod
	def fromString(string):
		elems = string.split(";")
		try:
			return Snapshot(
				IdToQDate(int(elems[0])),
				int(elems[1]),
				float(elems[2])
			)
		except (IndexError, ValueError), e:
			raise TsException("Snapshot.fromString() "
					  "invalid string: " + str(string))

class TsDatabase(QObject):
	INMEM = ":memory:"
	VERSION = 1

	if not usingPySide:
		sql.register_adapter(QString, lambda s: str(s))

	sql.register_adapter(QDate, QDateToId)
	sql.register_converter("QDate", IdToQDate)

	sql.register_adapter(ShiftConfigItem, ShiftConfigItem.toString)
	sql.register_converter("ShiftConfigItem", ShiftConfigItem.fromString)

	sql.register_adapter(Preset, Preset.toString)
	sql.register_converter("Preset", Preset.fromString)

	sql.register_adapter(Snapshot, Snapshot.toString)
	sql.register_converter("Snapshot", Snapshot.fromString)

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
		self.connect(self.commitTimer, SIGNAL("timeout()"),
			     self.__commitTimerTimeout)
		self.__reset()
		self.open(self.INMEM)

	def __del__(self):
		self.conn.close()

	def __sqlError(self, exception):
		msg = "SQL error: " + str(exception)
		print(msg)
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
				c = self.conn.cursor()
				c.execute("VACUUM;")
				self.commit()
			self.conn.close()
			self.__reset()
		except (sql.Error), e:
			self.__sqlError(e)

	def close(self):
		self.__close()
		self.open(self.INMEM)

	def open(self, filename):
		try:
			self.__close()
			self.conn = sql.connect(unicode(filename),
				detect_types=sql.PARSE_DECLTYPES)
			self.filename = filename
			if not self.isInMemory():
				self.__checkDatabaseVersion()
			self.__initTables(self.conn)
			if self.isInMemory():
				self.__setDatabaseVersion()
		except (sql.Error), e:
			self.__sqlError(e)

	def __setDatabaseVersion(self):
		try:
			self.__setParameter("dbVersion", self.VERSION)
		except (sql.Error), e:
			self.__sqlError(e)

	def __checkDatabaseVersion(self):
		try:
			dbVer = int(self.__getParameter("dbVersion"))
			if dbVer != self.VERSION:
				raise TsException(
					"Unsupported database version")
		except (sql.Error), e:
			self.__sqlError(e)
		except (ValueError), e:
			raise TsException("Invalid database version info")

	def getFilename(self):
		return self.filename

	def isInMemory(self):
		return self.filename == self.INMEM

	def commit(self):
		try:
			self.conn.commit()
		except (sql.Error), e:
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
			VACUUM;
		""")
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
			cloneconn = sql.connect(unicode(target),
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
			cloneconn.cursor().execute("VACUUM;")
			cloneconn.commit()
			cloneconn.close()
		except (sql.Error), e:
			self.__sqlError(e)

	def __setParameter(self, param, value):
		try:
			c = self.conn.cursor()
			c.execute("DELETE FROM params WHERE name=?;", (str(param),))
			if value is not None:
				c.execute("INSERT INTO params(name, data) VALUES(?, ?);",
					  (str(param), str(value)))
			self.scheduleCommit()
		except (sql.Error), e:
			self.__sqlError(e)

	def __getParameter(self, param):
		try:
			c = self.conn.cursor()
			c.execute("SELECT data FROM params WHERE name=?;", (param,))
			value = c.fetchone()
			if value:
				return value[0]
			return None
		except (sql.Error), e:
			self.__sqlError(e)

	def setDayFlags(self, date, value):
		try:
			c = self.conn.cursor()
			c.execute("DELETE FROM dayFlags WHERE date=?;", (date,))
			c.execute("INSERT INTO dayFlags(date, value) VALUES(?, ?);",
				  (date, int(value) & 0xFFFFFFFF))
			self.scheduleCommit()
		except (sql.Error), e:
			self.__sqlError(e)

	def getDayFlags(self, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT value FROM dayFlags WHERE date=?;", (date,))
			value = c.fetchone()
			if not value:
				return 0
			return int(value[0]) & 0xFFFFFFFF
		except (sql.Error), e:
			self.__sqlError(e)

	def setHolidaysPerYear(self, count):
		self.__setParameter("holidaysPerYear", count)

	def getHolidaysPerYear(self):
		try:
			return int(self.__getParameter("HolidaysPerYear"))
		except (ValueError, TypeError), e:
			return 30

	def __setOverride(self, table, date, value):
		try:
			c = self.conn.cursor()
			c.execute("DELETE FROM %s WHERE date=?;" % table, (date,))
			if value is not None:
				c.execute("INSERT INTO %s(date, value) VALUES(?, ?);" % table,
					  (date, str(value)))
			self.scheduleCommit()
		except (sql.Error), e:
			self.__sqlError(e)

	def __getOverride(self, table, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT value FROM %s WHERE date=?;" % table, (date,))
			value = c.fetchone()
			if value:
				return value[0]
			return None
		except (sql.Error), e:
			self.__sqlError(e)

	def __hasOverride(self, table, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT COUNT(*) FROM %s WHERE date=?;" % table, (date,))
			value = c.fetchone()
			if value:
				return value[0] > 0
			return False
		except (sql.Error), e:
			self.__sqlError(e)

	def setDayTypeOverride(self, date, daytype):
		self.__setOverride("override_dayType", date, daytype)

	def hasDayTypeOverride(self, date):
		return self.__hasOverride("override_dayType", date)

	def getDayTypeOverride(self, date):
		try:
			return int(self.__getOverride("override_dayType", date))
		except (ValueError, TypeError), e:
			return None

	def findDayTypeDates(self, daytype, beginDate, endDate):
		# Find all dates with the specified "daytype" between
		# "beginDate" and "endDate".
		try:
			c = self.conn.cursor()
			c.execute("""
				SELECT date FROM override_dayType WHERE
				(value=? AND date>=? AND date<=?);
			""", (daytype, beginDate, endDate))
			dates = c.fetchall()
			return [ d[0] for d in dates ]
		except (ValueError, TypeError), e:
			return None

	def setShiftOverride(self, date, shift):
		self.__setOverride("override_shift", date, shift)

	def hasShiftOverride(self, date):
		return self.__hasOverride("override_shift", date)

	def getShiftOverride(self, date):
		try:
			return int(self.__getOverride("override_shift", date))
		except (ValueError, TypeError), e:
			return None

	def setWorkTimeOverride(self, date, workTime):
		self.__setOverride("override_workTime", date, workTime)

	def hasWorkTimeOverride(self, date):
		return self.__hasOverride("override_workTime", date)

	def getWorkTimeOverride(self, date):
		try:
			return float(self.__getOverride("override_workTime", date))
		except (ValueError, TypeError), e:
			return None

	def setBreakTimeOverride(self, date, breakTime):
		self.__setOverride("override_breakTime", date, breakTime)

	def hasBreakTimeOverride(self, date):
		return self.__hasOverride("override_breakTime", date)

	def getBreakTimeOverride(self, date):
		try:
			return float(self.__getOverride("override_breakTime", date))
		except (ValueError, TypeError), e:
			return None

	def setAttendanceTimeOverride(self, date, attendanceTime):
		self.__setOverride("override_attendanceTime", date, attendanceTime)

	def hasAttendanceTimeOverride(self, date):
		return self.__hasOverride("override_attendanceTime", date)

	def getAttendanceTimeOverride(self, date):
		try:
			return float(self.__getOverride("override_attendanceTime", date))
		except (ValueError, TypeError), e:
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
		except (sql.Error), e:
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
		except (sql.Error), e:
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
		except (sql.Error), e:
			self.__sqlError(e)

	def getPresets(self):
		try:
			c = self.conn.cursor()
			c.execute("CREATE TABLE IF NOT EXISTS %s;" % self.TAB_presets)
			c.execute('SELECT preset FROM presets ORDER BY "idx";')
			presets = c.fetchall()
			return [ p[0] for p in presets ]
		except (sql.Error), e:
			self.__sqlError(e)

	def setSnapshot(self, date, snapshot):
		try:
			c = self.conn.cursor()
			c.execute("DELETE FROM snapshots WHERE date=?;", (date,))
			if snapshot is not None:
				c.execute("INSERT INTO snapshots(date, snapshot) VALUES(?, ?);",
					  (date, snapshot))
			self.scheduleCommit()
		except (sql.Error), e:
			self.__sqlError(e)

	def hasSnapshot(self, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT COUNT(*) FROM snapshots WHERE date=?;", (date,))
			value = c.fetchone()
			if value:
				return value[0] > 0
			return False
		except (sql.Error), e:
			self.__sqlError(e)

	def getSnapshot(self, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT snapshot FROM snapshots WHERE date=?;", (date,))
			snapshot = c.fetchone()
			if snapshot:
				snapshot = snapshot[0]
			return snapshot
		except (sql.Error), e:
			self.__sqlError(e)

	def getAllSnapshots(self):
		try:
			c = self.conn.cursor()
			c.execute("SELECT snapshot FROM snapshots;")
			snapshots = c.fetchall()
			return [ s[0] for s in snapshots ]
		except (sql.Error), e:
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
		except (sql.Error), e:
			self.__sqlError(e)

	def setComment(self, date, comment):
		try:
			c = self.conn.cursor()
			c.execute("DELETE FROM comments WHERE date=?;", (date,))
			if comment:
				c.execute("INSERT INTO comments(date, comment) VALUES(?, ?);",
					  (date, unicode(comment)))
			self.scheduleCommit()
		except (sql.Error), e:
			self.__sqlError(e)

	def hasComment(self, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT COUNT(*) FROM comments WHERE date=?;", (date,))
			value = c.fetchone()
			if value:
				return value[0] > 0
			return False
		except (sql.Error), e:
			self.__sqlError(e)

	def getComment(self, date):
		try:
			c = self.conn.cursor()
			c.execute("SELECT comment FROM comments WHERE date=?;", (date,))
			comment = c.fetchone()
			if comment:
				comment = comment[0]
			return comment
		except (sql.Error), e:
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
		self.shiftCombo = QComboBox(self)
		self.shiftCombo.addItem("Frueh", QVariant(SHIFT_EARLY))
		self.shiftCombo.addItem("Nacht", QVariant(SHIFT_NIGHT))
		self.shiftCombo.addItem("Spaet", QVariant(SHIFT_LATE))
		self.shiftCombo.addItem("Normal", QVariant(SHIFT_DAY))
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

		self.connect(self.itemList, SIGNAL("currentRowChanged(int)"),
			     self.itemChanged)
		self.connect(self.addButton, SIGNAL("released()"),
			     self.addItem)
		self.connect(self.removeButton, SIGNAL("released()"),
			     self.removeItem)

		self.connect(self.nameEdit, SIGNAL("textChanged(QString)"),
			     self.updateCurrentItem)
		self.connect(self.shiftCombo, SIGNAL("currentIndexChanged(int)"),
			     self.updateCurrentItem)
		self.connect(self.workTime, SIGNAL("valueChanged(double)"),
			     self.updateCurrentItem)
		self.connect(self.breakTime, SIGNAL("valueChanged(double)"),
			     self.updateCurrentItem)
		self.connect(self.attendanceTime, SIGNAL("valueChanged(double)"),
			     self.updateCurrentItem)

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
			index = self.shiftCombo.findData(QVariant(item.shift))
			self.shiftCombo.setCurrentIndex(index)
			self.workTime.setValue(item.workTime)
			self.breakTime.setValue(item.breakTime)
			self.attendanceTime.setValue(item.attendanceTime)
		self.updateBlocked = False

	def updateItem(self, item):
		item.name = self.nameEdit.text()
		index = self.shiftCombo.currentIndex()
		item.shift = qvariantToPy(self.shiftCombo.itemData(index))
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
		item = ShiftConfigItem("Unbenannt", SHIFT_DAY, 7.0, 0.5, 8.5)
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

		self.connect(self.uncertainCheckBox, SIGNAL("stateChanged(int)"),
			     self.__flagCheckBoxChanged)
		self.connect(self.attendantCheckBox, SIGNAL("stateChanged(int)"),
			     self.__flagCheckBoxChanged)

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
		self.connect(self.setDbButton, SIGNAL("released()"),
			     self.loadDatabase)

		self.resetCalButton = QPushButton("Kalender loeschen", self)
		self.fileGroup.layout().addWidget(self.resetCalButton, 1, 0)
		self.connect(self.resetCalButton, SIGNAL("released()"),
			     self.resetCalendar)

		self.schedConfButton = QPushButton("Schichtkonfig", self)
		self.fileGroup.layout().addWidget(self.schedConfButton, 2, 0)
		self.connect(self.schedConfButton, SIGNAL("released()"),
			     self.doShiftConfig)

		self.paramsGroup = QGroupBox("Parameter", self)
		self.paramsGroup.setLayout(QGridLayout())
		self.layout().addWidget(self.paramsGroup, 0, 2)

		self.holidays = QSpinBox(self)
		self.holidays.setMinimum(0)
		self.holidays.setMaximum(1024)
		self.holidays.setSingleStep(1)
		self.holidays.setAccelerated(True)
		self.holidays.setPrefix("Urlaub/a = ")
		self.holidays.setSuffix(" Tage")
		self.paramsGroup.layout().addWidget(self.holidays, 0, 0, 1, 2)

		self.loadParams()

		self.connect(self.holidays, SIGNAL("valueChanged(int)"),
			     self.updateParams)

	def loadParams(self):
		mainWidget = self.mainWidget
		self.holidays.setValue(mainWidget.db.getHolidaysPerYear())

	def updateParams(self):
		mainWidget = self.mainWidget
		mainWidget.db.setHolidaysPerYear(self.holidays.value())
		mainWidget.worldUpdate()

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

		self.typeCombo = QComboBox(self)
		self.typeCombo.addItem("---", QVariant(DTYPE_DEFAULT))
		self.typeCombo.addItem("Zeitausgleich", QVariant(DTYPE_COMPTIME))
		self.typeCombo.addItem("Urlaub", QVariant(DTYPE_HOLIDAY))
		self.typeCombo.addItem("Feiertag", QVariant(DTYPE_FEASTDAY))
		self.typeCombo.addItem("Kurzarbeit", QVariant(DTYPE_SHORTTIME))
		self.layout().addWidget(self.typeCombo, 1, 2)

		self.shiftCombo = QComboBox(self)
		self.shiftCombo.addItem("Fruehschicht", QVariant(SHIFT_EARLY))
		self.shiftCombo.addItem("Nachtschicht", QVariant(SHIFT_NIGHT))
		self.shiftCombo.addItem("Spaetschicht", QVariant(SHIFT_LATE))
		self.shiftCombo.addItem("Normalschicht", QVariant(SHIFT_DAY))
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

		self.connect(self.presetList, SIGNAL("currentRowChanged(int)"),
			     self.presetSelectionChanged)
		self.connect(self.addButton, SIGNAL("released()"),
			     self.addPreset)
		self.connect(self.removeButton, SIGNAL("released()"),
			     self.removePreset)
		self.connect(self.commitButton, SIGNAL("released()"),
			     self.commitPressed)

		self.connect(self.nameEdit, SIGNAL("textChanged(QString)"),
			     self.presetChanged)
		self.connect(self.typeCombo, SIGNAL("currentIndexChanged(int)"),
			     self.presetChanged)
		self.connect(self.shiftCombo, SIGNAL("currentIndexChanged(int)"),
			     self.presetChanged)
		self.connect(self.workTime, SIGNAL("valueChanged(double)"),
			     self.presetChanged)
		self.connect(self.breakTime, SIGNAL("valueChanged(double)"),
			     self.presetChanged)
		self.connect(self.attendanceTime, SIGNAL("valueChanged(double)"),
			     self.presetChanged)

	def __addPreset(self, preset):
		item = QListWidgetItem(preset.name)
		item.setData(Qt.UserRole, QVariant(preset))
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
		index = mainWidget.typeCombo.findData(QVariant(preset.dayType))
		mainWidget.typeCombo.setCurrentIndex(index)
		index = mainWidget.shiftCombo.findData(QVariant(preset.shift))
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
		preset = qvariantToPy(item.data(Qt.UserRole))
		self.presetChangeBlocked = True
		self.nameEdit.setText(preset.name)
		index = self.typeCombo.findData(QVariant(preset.dayType))
		self.typeCombo.setCurrentIndex(index)
		index = self.shiftCombo.findData(QVariant(preset.shift))
		self.shiftCombo.setCurrentIndex(index)
		self.workTime.setValue(preset.workTime)
		self.breakTime.setValue(preset.breakTime)
		self.attendanceTime.setValue(preset.attendanceTime)
		self.presetChangeBlocked = False

	def __updatePresetItem(self, preset):
		preset.name = self.nameEdit.text()
		index = self.typeCombo.currentIndex()
		preset.dayType = qvariantToPy(self.typeCombo.itemData(index))
		index = self.shiftCombo.currentIndex()
		preset.shift = qvariantToPy(self.shiftCombo.itemData(index))
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
		self.__updatePresetItem(qvariantToPy(item.data(Qt.UserRole)))
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
			preset = qvariantToPy(item.data(Qt.UserRole))
			self.applyPreset(preset)
			self.accept()

class SnapshotDialog(QDialog):
	def __init__(self, mainWidget, date, shiftConfigIndex=0, accountValue=0.0):
		QDialog.__init__(self, mainWidget)
		self.setWindowTitle("Schnappschuss setzen")
		self.setLayout(QGridLayout())
		self.mainWidget = mainWidget
		self.date = date

		self.dateLabel = QLabel(date.toString("dddd, dd.MM.yyyy"), self)
		self.layout().addWidget(self.dateLabel, 0, 0)

		l = QLabel("Startschicht:", self)
		self.layout().addWidget(l, 1, 0)
		self.shiftConfig = QComboBox(self)
		shiftConfig = mainWidget.db.getShiftConfigItems()
		assert(shiftConfig)
		index = 0
		for cfg in shiftConfig:
			name = "%d \"%s\"" % (index + 1, cfg.name)
			self.shiftConfig.addItem(name, QVariant(index))
			index += 1
		self.layout().addWidget(self.shiftConfig, 1, 1)
		index = self.shiftConfig.findData(QVariant(shiftConfigIndex))
		if index >= 0:
			self.shiftConfig.setCurrentIndex(index)

		l = QLabel("Kontostand:", self)
		self.layout().addWidget(l, 2, 0)
		self.accountValue = TimeSpinBox(self, val=accountValue,
				minVal=-1000.0, maxVal=1000.0,
				step=0.1, decimals=1)
		self.layout().addWidget(self.accountValue, 2, 1)

		self.removeButton = QPushButton("Schnappschuss loeschen", self)
		self.layout().addWidget(self.removeButton, 3, 0, 1, 2)
		self.connect(self.removeButton, SIGNAL("released()"),
			     self.removeSnapshot)
		if not mainWidget.dateHasSnapshot(date):
			self.removeButton.hide()

		self.okButton = QPushButton("Setzen", self)
		self.layout().addWidget(self.okButton, 4, 0)
		self.connect(self.okButton, SIGNAL("released()"),
			     self.ok)

		self.cancelButton = QPushButton("Abbrechen", self)
		self.layout().addWidget(self.cancelButton, 4, 1)
		self.connect(self.cancelButton, SIGNAL("released()"),
			     self.cancel)

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
		shiftConfigIndex = qvariantToPy(self.shiftConfig.itemData(index))
		value = self.accountValue.value()
		return Snapshot(self.date, shiftConfigIndex, value)

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
			painter.drawText(rx + rw / 2 - metrics.width(text) / 2,
					 ry + rh / 2 + metrics.height() / 2,
					 text)

		painter.restore()

	def redraw(self):
		if self.isVisible():
			self.hide()
			self.show()

class MainWidget(QWidget):
	def __init__(self, parent=None):
		QWidget.__init__(self, parent)

		self.setFocusPolicy(Qt.StrongFocus)
		self.setLayout(QGridLayout())

		self.worldUpdateTimer = QTimer(self)
		self.worldUpdateTimer.setSingleShot(True)
		self.connect(self.worldUpdateTimer, SIGNAL("timeout()"),
			     self.__worldUpdateTimerTimeout)

		self.calendar = Calendar(self)
		self.layout().addWidget(self.calendar, 0, 0, 5, 3)

		self.typeCombo = QComboBox(self)
		self.typeCombo.addItem("---", QVariant(DTYPE_DEFAULT))
		self.typeCombo.addItem("Zeitausgleich", QVariant(DTYPE_COMPTIME))
		self.typeCombo.addItem("Urlaub", QVariant(DTYPE_HOLIDAY))
		self.typeCombo.addItem("Feiertag", QVariant(DTYPE_FEASTDAY))
		self.typeCombo.addItem("Kurzarbeit", QVariant(DTYPE_SHORTTIME))
		self.layout().addWidget(self.typeCombo, 0, 4)

		self.shiftCombo = QComboBox(self)
		self.shiftCombo.addItem("Fruehschicht", QVariant(SHIFT_EARLY))
		self.shiftCombo.addItem("Nachtschicht", QVariant(SHIFT_NIGHT))
		self.shiftCombo.addItem("Spaetschicht", QVariant(SHIFT_LATE))
		self.shiftCombo.addItem("Normalschicht", QVariant(SHIFT_DAY))
		self.layout().addWidget(self.shiftCombo, 1, 4)

		self.workTime = TimeSpinBox(self, prefix="Arb.zeit")
		self.layout().addWidget(self.workTime, 2, 4)

		self.breakTime = TimeSpinBox(self, prefix="Pause")
		self.layout().addWidget(self.breakTime, 3, 4)

		self.attendanceTime = TimeSpinBox(self, prefix="Anwes.")
		self.layout().addWidget(self.attendanceTime, 4, 4)

		self.presetButton = QPushButton("Vorgaben", self)
		self.layout().addWidget(self.presetButton, 5, 4)
		self.connect(self.presetButton, SIGNAL("released()"),
			     self.doPresets)

		self.connect(self.calendar, SIGNAL("selectionChanged()"),
			     self.recalculate)
		self.connect(self.typeCombo, SIGNAL("currentIndexChanged(int)"),
			     self.overrideChanged)
		self.connect(self.shiftCombo, SIGNAL("currentIndexChanged(int)"),
			     self.overrideChanged)
		self.connect(self.workTime, SIGNAL("valueChanged(double)"),
			     self.overrideChanged)
		self.connect(self.breakTime, SIGNAL("valueChanged(double)"),
			     self.overrideChanged)
		self.connect(self.attendanceTime, SIGNAL("valueChanged(double)"),
			     self.overrideChanged)
		self.overrideChangeBlocked = False

		self.manageButton = QPushButton("Verwalten", self)
		self.layout().addWidget(self.manageButton, 5, 0)
		self.connect(self.manageButton, SIGNAL("released()"),
			     self.doManage)

		self.snapshotButton = QPushButton("Schnappschuss", self)
		self.layout().addWidget(self.snapshotButton, 5, 1)
		self.connect(self.snapshotButton, SIGNAL("released()"),
			     self.doSnapshot)

		self.enhancedButton = QPushButton("Erweitert", self)
		self.layout().addWidget(self.enhancedButton, 5, 2)
		self.connect(self.enhancedButton, SIGNAL("released()"),
			     self.doEnhanced)

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
		except (TsException), e:
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
		shiftConfigIndex = 0
		accountValue = 0.0
		if snapshot is None:
			# Calculate the account state w.r.t. the
			# last shapshot.
			snapshot = self.db.findSnapshotForDate(date)
			if snapshot:
				(shiftConfigIndex, startOfTheDay, endOfTheDay) = self.__calcAccountState(snapshot, date)
				accountValue = startOfTheDay
		else:
			# We already have a snapshot on that day. Modify it.
			shiftConfigIndex = snapshot.shiftConfigIndex
			accountValue = snapshot.accountValue
		dlg = SnapshotDialog(self, date,
				     shiftConfigIndex, accountValue)
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
		self.setDayType(date, qvariantToPy(self.typeCombo.itemData(index)))

		# Shift override
		index = self.shiftCombo.currentIndex()
		shift = qvariantToPy(self.shiftCombo.itemData(index))
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
		date = snapshot.date
		shiftConfigIndex = snapshot.shiftConfigIndex
		startOfTheDay = snapshot.accountValue
		endOfTheDay = startOfTheDay
		assert(date <= endDate)
		while True:
			shiftConfigItem = shiftConfig[shiftConfigIndex]
			currentShift = self.getRealShift(date, shiftConfigItem)
			workTime = self.getRealWorkTime(date, shiftConfigItem)
			breakTime = self.getRealBreakTime(date, shiftConfigItem)
			attendanceTime = self.getRealAttendanceTime(date, shiftConfigItem)

			dtype = self.getDayType(date)
			if dtype == DTYPE_DEFAULT:
				if attendanceTime > 0.001:
					endOfTheDay += attendanceTime
					endOfTheDay -= workTime
					endOfTheDay -= breakTime
			elif dtype == DTYPE_COMPTIME:
				endOfTheDay -= workTime
			elif dtype in (DTYPE_HOLIDAY, DTYPE_FEASTDAY, DTYPE_SHORTTIME):
				pass # no change
			else:
				assert(0)

			if date == endDate:
				break
			date = date.addDays(1)
			shiftConfigIndex = (shiftConfigIndex + 1) % nrShiftConfigs
			startOfTheDay = endOfTheDay
		return (shiftConfigIndex, startOfTheDay, endOfTheDay)

	def __holidaysLeft(self, date):
		beginDate = QDate(date.year(), 1, 1)
		dates = self.db.findDayTypeDates(DTYPE_HOLIDAY, beginDate, date)
		return self.db.getHolidaysPerYear() - len(dates)

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
		(shiftConfigIndex, startOfTheDay, endOfTheDay) = self.__calcAccountState(snapshot, selDate)
		holidaysLeft = self.__holidaysLeft(selDate)

		shiftConfigItem = shiftConfig[shiftConfigIndex]
		dtype = self.getDayType(selDate)
		shift = self.getRealShift(selDate, shiftConfigItem)
		workTime = self.getRealWorkTime(selDate, shiftConfigItem)
		breakTime = self.getRealBreakTime(selDate, shiftConfigItem)
		attendanceTime = self.getRealAttendanceTime(selDate, shiftConfigItem)

		self.overrideChangeBlocked = True
		self.typeCombo.setCurrentIndex(self.typeCombo.findData(QVariant(dtype)))
		self.shiftCombo.setCurrentIndex(self.shiftCombo.findData(QVariant(shift)))
		self.workTime.setValue(workTime)
		self.breakTime.setValue(breakTime)
		self.attendanceTime.setValue(attendanceTime)
		self.overrideChangeBlocked = False

		dateString = selDate.toString("dd.MM.yyyy")
		self.output.setText("Konto am %s:  Beginn: %.1f  Ende: %.1f  Urlaub: %d" %\
			(dateString, round(startOfTheDay, 1),
			 round(endOfTheDay, 1), holidaysLeft))

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
