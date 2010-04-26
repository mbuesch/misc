#!/usr/bin/env python
"""
# timeshift.py
# Copyright (c) 2009 Michael Buesch <mb@bu3sch.de>
# Licensed under the GNU/GPL version 2 or later.
"""

import sys
import ConfigParser
import base64
from PyQt4.QtCore import *
from PyQt4.QtGui import *


# Shift types
SHIFT_EARLY		= 0
SHIFT_LATE		= 1
SHIFT_NIGHT		= 2
SHIFT_DAY		= 3

# Shift scheduling types
SHIFTSCHED_EARLY		= 0 # early only
SHIFTSCHED_LATE			= 1 # late only
SHIFTSCHED_NIGHT		= 2 # night only
SHIFTSCHED_DAY			= 3 # day only
SHIFTSCHED_EARLY_LATE		= 4 # early -> late -> early...
SHIFTSCHED_EARLY_NIGHT_LATE	= 5 # early -> night -> late -> early...

# Day attributes
DAYATTR_WORKDAY		= 1 << 0
DAYATTR_WEEKEND		= 1 << 1
DAYATTR_COMPTIME	= 1 << 2
DAYATTR_HOLIDAY		= 1 << 3
DAYATTR_SHORTTIME	= 1 << 4
DAYATTR_SHIFT_EARLY	= 1 << 5
DAYATTR_SHIFT_LATE	= 1 << 6
DAYATTR_SHIFT_NIGHT	= 1 << 7
DAYATTR_SHIFT_DAY	= 1 << 8
DAYATTR_FEASTDAY	= 1 << 9

DAYATTR_SHIFT_MASK	= DAYATTR_SHIFT_EARLY | DAYATTR_SHIFT_LATE |\
			  DAYATTR_SHIFT_NIGHT | DAYATTR_SHIFT_DAY

DAYATTR_TYPE_MASK	= DAYATTR_WORKDAY | DAYATTR_WEEKEND |\
			  DAYATTR_COMPTIME | DAYATTR_HOLIDAY |\
			  DAYATTR_SHORTTIME | DAYATTR_FEASTDAY


def QDateToId(qdate):
	"Convert a QDate object to a unique integer ID"
	return QDateTime(qdate).toTime_t()

def IdToQDate(id):
	"Convert a unique integer ID to a QDate object"
	return QDateTime.fromTime_t(id).date()


class TimeshiftException(Exception): pass

class EnhancedDialog(QDialog):
	def __init__(self, mainWidget):
		QDialog.__init__(self, mainWidget)
		self.mainWidget = mainWidget
		self.setWindowTitle("Erweitert")
		self.setLayout(QGridLayout())

		self.commentGroup = QGroupBox("Kommentar", self)
		self.commentGroup.setLayout(QGridLayout())
		self.layout().addWidget(self.commentGroup, 0, 0, 1, 2)

		self.comment = QTextEdit(self)
		self.commentGroup.layout().addWidget(self.comment, 0, 0)
		date = mainWidget.calendar.selectedDate()
		self.comment.document().setPlainText(mainWidget.getCommentFor(date))

		self.okButton = QPushButton("OK", self)
		self.layout().addWidget(self.okButton, 1, 0)
		self.connect(self.okButton, SIGNAL("released()"),
			     self.ok)

		self.cancelButton = QPushButton("Abbrechen", self)
		self.layout().addWidget(self.cancelButton, 1, 1)
		self.connect(self.cancelButton, SIGNAL("released()"),
			     self.cancel)

	def ok(self):
		date = self.mainWidget.calendar.selectedDate()
		old = self.mainWidget.getCommentFor(date)
		new = self.comment.document().toPlainText()
		if old != new:
			self.mainWidget.setCommentFor(date, new)
		self.accept()

	def cancel(self):
		self.reject()

class ManageDialog(QDialog):
	def __init__(self, mainWidget):
		QDialog.__init__(self, mainWidget)
		self.mainWidget = mainWidget
		self.setWindowTitle("Verwalten")
		self.setLayout(QGridLayout())

		self.fileGroup = QGroupBox("Datei", self)
		self.fileGroup.setLayout(QGridLayout())
		self.layout().addWidget(self.fileGroup, 0, 0)

		self.loadButton = QPushButton("Laden", self)
		self.fileGroup.layout().addWidget(self.loadButton, 0, 0)
		self.connect(self.loadButton, SIGNAL("released()"),
			     self.load)

		self.saveAsButton = QPushButton("Speichern unter...", self)
		self.fileGroup.layout().addWidget(self.saveAsButton, 1, 0)
		self.connect(self.saveAsButton, SIGNAL("released()"),
			     self.saveAs)

		self.saveButton = QPushButton("Speichern", self)
		self.fileGroup.layout().addWidget(self.saveButton, 2, 0)
		self.connect(self.saveButton, SIGNAL("released()"),
			     self.save)
		if not mainWidget.getFilename():
			self.saveButton.setEnabled(False)

		self.resetCalButton = QPushButton("Kalender loeschen", self)
		self.fileGroup.layout().addWidget(self.resetCalButton, 3, 0)
		self.connect(self.resetCalButton, SIGNAL("released()"),
			     self.resetCalendar)

		self.paramsGroup = QGroupBox("Parameter", self)
		self.paramsGroup.setLayout(QGridLayout())
		self.layout().addWidget(self.paramsGroup, 0, 2)

		l = QLabel("Regelarbeitszeit:", self)
		self.paramsGroup.layout().addWidget(l, 0, 0)
		self.workTime = QDoubleSpinBox(self)
		self.workTime.setMinimum(1.0)
		self.workTime.setMaximum(10.0)
		self.workTime.setSuffix(" h")
		self.workTime.setSingleStep(0.05)
		self.paramsGroup.layout().addWidget(self.workTime, 0, 1)

		l = QLabel("Schichtsystem:", self)
		self.paramsGroup.layout().addWidget(l, 1, 0)
		self.shiftSched = QComboBox(self)
		self.shiftSched.addItem("Nur Frueh", QVariant(SHIFTSCHED_EARLY))
		self.shiftSched.addItem("Nur Nacht", QVariant(SHIFTSCHED_NIGHT))
		self.shiftSched.addItem("Nur Spaet", QVariant(SHIFTSCHED_LATE))
		self.shiftSched.addItem("Nur Normal", QVariant(SHIFTSCHED_DAY))
		self.shiftSched.addItem("Frueh, Spaet", QVariant(SHIFTSCHED_EARLY_LATE))
		self.shiftSched.addItem("Frueh, Nacht, Spaet", QVariant(SHIFTSCHED_EARLY_NIGHT_LATE))
		self.paramsGroup.layout().addWidget(self.shiftSched, 1, 1)

		l = QLabel("Frueh Aufbau:", self)
		self.paramsGroup.layout().addWidget(l, 2, 0)
		self.earlyGain = QDoubleSpinBox(self)
		self.earlyGain.setMinimum(-10.0)
		self.earlyGain.setMaximum(10.0)
		self.earlyGain.setSuffix(" h")
		self.earlyGain.setSingleStep(0.05)
		self.paramsGroup.layout().addWidget(self.earlyGain, 2, 1)

		l = QLabel("Spaet Aufbau:", self)
		self.paramsGroup.layout().addWidget(l, 3, 0)
		self.lateGain = QDoubleSpinBox(self)
		self.lateGain.setMinimum(-10.0)
		self.lateGain.setMaximum(10.0)
		self.lateGain.setSuffix(" h")
		self.lateGain.setSingleStep(0.05)
		self.paramsGroup.layout().addWidget(self.lateGain, 3, 1)

		l = QLabel("Nacht Aufbau:", self)
		self.paramsGroup.layout().addWidget(l, 4, 0)
		self.nightGain = QDoubleSpinBox(self)
		self.nightGain.setMinimum(-10.0)
		self.nightGain.setMaximum(10.0)
		self.nightGain.setSuffix(" h")
		self.nightGain.setSingleStep(0.05)
		self.paramsGroup.layout().addWidget(self.nightGain, 4, 1)

		l = QLabel("Normal Aufbau:", self)
		self.paramsGroup.layout().addWidget(l, 5, 0)
		self.dayGain = QDoubleSpinBox(self)
		self.dayGain.setMinimum(-10.0)
		self.dayGain.setMaximum(10.0)
		self.dayGain.setSuffix(" h")
		self.dayGain.setSingleStep(0.05)
		self.paramsGroup.layout().addWidget(self.dayGain, 5, 1)

		self.resetParamsButton = QPushButton("Parameter ruecksetzen", self)
		self.paramsGroup.layout().addWidget(self.resetParamsButton, 6, 0, 1, 2)
		self.connect(self.resetParamsButton, SIGNAL("released()"),
			     self.resetParams)

		self.loadParams()
		self.connect(self.workTime, SIGNAL("valueChanged(double)"),
			     self.updateParams)
		self.connect(self.shiftSched, SIGNAL("currentIndexChanged(int)"),
			     self.updateParams)
		self.connect(self.earlyGain, SIGNAL("valueChanged(double)"),
			     self.updateParams)
		self.connect(self.lateGain, SIGNAL("valueChanged(double)"),
			     self.updateParams)
		self.connect(self.nightGain, SIGNAL("valueChanged(double)"),
			     self.updateParams)
		self.connect(self.dayGain, SIGNAL("valueChanged(double)"),
			     self.updateParams)

	def loadParams(self):
		self.workTime.setValue(self.mainWidget.workTime)
		index = self.shiftSched.findData(QVariant(self.mainWidget.shiftSched))
		if index >= 0:
			self.shiftSched.setCurrentIndex(index)
		self.earlyGain.setValue(self.mainWidget.earlyGain)
		self.lateGain.setValue(self.mainWidget.lateGain)
		self.nightGain.setValue(self.mainWidget.nightGain)
		self.dayGain.setValue(self.mainWidget.dayGain)

	def updateParams(self):
		mainWidget = self.mainWidget
		mainWidget.dirty = True
		mainWidget.workTime = self.workTime.value()
		index = self.shiftSched.currentIndex()
		mainWidget.shiftSched = self.shiftSched.itemData(index).toUInt()[0]
		mainWidget.earlyGain = self.earlyGain.value()
		mainWidget.lateGain = self.lateGain.value()
		mainWidget.nightGain = self.nightGain.value()
		mainWidget.dayGain = self.dayGain.value()
		mainWidget.recalculate()

	def resetParams(self):
		res = QMessageBox.question(self, "Alle Parameter ruecksetzen?",
					   "Wollen Sie wirklich alle Parameter auf die " +\
					   "Standardwerte zuruecksetzen?",
					   QMessageBox.Yes | QMessageBox.No)
		if res == QMessageBox.Yes:
			self.mainWidget.resetParams()
			self.loadParams()

	def load(self):
		self.mainWidget.loadFromFile()
		self.accept()

	def saveAs(self):
		self.mainWidget.saveToFile()
		self.accept()

	def save(self):
		self.mainWidget.doSaveToFile(self.mainWidget.getFilename())
		self.accept()

	def resetCalendar(self):
		res = QMessageBox.question(self, "Kalender loeschen?",
					   "Wollen Sie wirklich alle Kalendereintraege loeschen?",
					   QMessageBox.Yes | QMessageBox.No)
		if res == QMessageBox.Yes:
			self.mainWidget.resetCalendar()
			self.accept()

class Snapshot:
	def __init__(self, date, shift, accountValue):
		self.date = date
		self.shift = shift
		self.accountValue = accountValue

class SnapshotDialog(QDialog):
	def __init__(self, mainWidget, date, shift=None, accountValue=None):
		QDialog.__init__(self, mainWidget)
		self.setWindowTitle("Schnappschuss setzen")
		self.setLayout(QGridLayout())
		self.mainWidget = mainWidget
		self.date = date

		self.dateLabel = QLabel(date.toString("dd.MM.yyyy"), self)
		self.layout().addWidget(self.dateLabel, 0, 0)

		l = QLabel("Schicht:", self)
		self.layout().addWidget(l, 1, 0)
		self.shift = QComboBox(self)
		shiftSched = mainWidget.shiftSched
		if shiftSched == SHIFTSCHED_EARLY or \
		   shiftSched == SHIFTSCHED_EARLY_LATE or \
		   shiftSched == SHIFTSCHED_EARLY_NIGHT_LATE:
			self.shift.addItem("Frueh", QVariant(SHIFT_EARLY))
		if shiftSched == SHIFTSCHED_NIGHT or \
		   shiftSched == SHIFTSCHED_EARLY_NIGHT_LATE:
			self.shift.addItem("Nacht", QVariant(SHIFT_NIGHT))
		if shiftSched == SHIFTSCHED_LATE or \
		   shiftSched == SHIFTSCHED_EARLY_LATE or \
		   shiftSched == SHIFTSCHED_EARLY_NIGHT_LATE:
			self.shift.addItem("Spaet", QVariant(SHIFT_LATE))
		if shiftSched == SHIFTSCHED_DAY:
			self.shift.addItem("Normal", QVariant(SHIFT_DAY))
		self.layout().addWidget(self.shift, 1, 1)
		if shift is not None:
			index = self.shift.findData(QVariant(shift))
			if index >= 0:
				self.shift.setCurrentIndex(index)

		l = QLabel("Kontostand:", self)
		self.layout().addWidget(l, 2, 0)
		self.accountValue = QDoubleSpinBox(self)
		self.accountValue.setMinimum(-1000.0)
		self.accountValue.setMaximum(1000.0)
		self.accountValue.setValue(0.0)
		self.accountValue.setSuffix(" h")
		self.accountValue.setSingleStep(0.1)
		self.layout().addWidget(self.accountValue, 2, 1)
		if accountValue is not None:
			self.accountValue.setValue(accountValue)

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
		shift = self.shift.itemData(self.shift.currentIndex()).toInt()[0]
		value = self.accountValue.value()
		return Snapshot(self.date, shift, value)

class Calendar(QCalendarWidget):
	def __init__(self, mainWidget):
		QCalendarWidget.__init__(self, mainWidget)
		self.mainWidget = mainWidget

		self.setFirstDayOfWeek(Qt.Monday)
		self.connect(self, SIGNAL("selectionChanged()"),
			     self.selChanged)

	def paintCell(self, painter, rect, date):
		QCalendarWidget.paintCell(self, painter, rect, date)

		painter.save()

		mainWidget = self.mainWidget
		attrs = mainWidget.getAttributes(date)

		if mainWidget.dateHasSnapshot(date):
			pen = QPen(QColor("#007FFF"))
			pen.setWidth(5)
			painter.setPen(pen)
		else:
			painter.setPen(QPen(QColor("#000000")))
		painter.drawRect(rect.x(), rect.y(),
				 rect.width() - 1, rect.height() - 1)

		if mainWidget.dateHasComment(date):
			pen = QPen(QColor("#FF0000"))
			pen.setWidth(2)
			painter.setPen(pen)
			painter.drawRect(rect.x() + 3, rect.y() + 3,
					 rect.width() - 3 - 3, rect.height() - 3 - 3)

		lowerLeft = None
		lowerRight = None

		if attrs & DAYATTR_COMPTIME:
			lowerLeft = "Z"
		elif attrs & DAYATTR_HOLIDAY:
			lowerLeft = "U"
		elif attrs & DAYATTR_SHORTTIME:
			lowerLeft = "C"
		elif attrs & DAYATTR_FEASTDAY:
			lowerLeft = "F"
		elif attrs & DAYATTR_WORKDAY:
			lowerLeft = "A"

		if attrs & DAYATTR_SHIFT_EARLY:
			lowerRight = "F"
		elif attrs & DAYATTR_SHIFT_LATE:
			lowerRight = "S"
		elif attrs & DAYATTR_SHIFT_NIGHT:
			lowerRight = "N"
		elif attrs & DAYATTR_SHIFT_DAY:
			lowerRight = "O"

		font = painter.font()
		font.setBold(True)
		painter.setFont(font)

		if lowerLeft:
			painter.setPen(QPen(QColor("#FF0000")))
			painter.drawText(rect.x() + 4, rect.y() + rect.height() - 4, lowerLeft)

		if lowerRight:
			painter.setPen(QPen(QColor("#304F7F")))
			metrics = QFontMetrics(painter.font())
			painter.drawText(rect.x() + rect.width() - metrics.width(lowerRight) - 4,
					 rect.y() + rect.height() - 4,
					 lowerRight)

		painter.restore()

	def selChanged(self):
		self.mainWidget.recalculate()

	def redraw(self):
		self.hide()
		self.show()

class MainWidget(QWidget):
	def __init__(self, parent=None):
		QWidget.__init__(self, parent)

		self.setFocusPolicy(Qt.StrongFocus)
		self.setLayout(QGridLayout())

		self.calendar = Calendar(self)
		self.layout().addWidget(self.calendar, 0, 0, 7, 3)
		self.connect(self.calendar, SIGNAL("selectionChanged()"),
			     self.recalculate)

		self.compTimeButton = QPushButton("(Z)eitausgl.", self)
		self.layout().addWidget(self.compTimeButton, 0, 4)
		self.connect(self.compTimeButton, SIGNAL("released()"),
			     self.setCompensatoryTime)

		self.holidayButton = QPushButton("(U)rlaub", self)
		self.layout().addWidget(self.holidayButton, 1, 4)
		self.connect(self.holidayButton, SIGNAL("released()"),
			     self.setHoliday)

		self.feastdayButton = QPushButton("(F)eiertag", self)
		self.layout().addWidget(self.feastdayButton, 2, 4)
		self.connect(self.feastdayButton, SIGNAL("released()"),
			     self.setFeastday)

		self.shortTimeWorkButton = QPushButton("(C)Kurzarb.", self)
		self.layout().addWidget(self.shortTimeWorkButton, 3, 4)
		self.connect(self.shortTimeWorkButton, SIGNAL("released()"),
			     self.setShortTimeWork)

		self.workOverrideButton = QPushButton("(A)nwesend", self)
		self.layout().addWidget(self.workOverrideButton, 4, 4)
		self.connect(self.workOverrideButton, SIGNAL("released()"),
			     self.workOverride)

		self.earlyOverrideButton = QPushButton("(F)rueh", self)
		self.layout().addWidget(self.earlyOverrideButton, 0, 5)
		self.connect(self.earlyOverrideButton, SIGNAL("released()"),
			     self.earlyOverride)

		self.nightOverrideButton = QPushButton("(N)acht", self)
		self.layout().addWidget(self.nightOverrideButton, 1, 5)
		self.connect(self.nightOverrideButton, SIGNAL("released()"),
			     self.nightOverride)

		self.lateOverrideButton = QPushButton("(S)spaet", self)
		self.layout().addWidget(self.lateOverrideButton, 2, 5)
		self.connect(self.lateOverrideButton, SIGNAL("released()"),
			     self.lateOverride)

		self.dayOverrideButton = QPushButton("N(O)rmal", self)
		self.layout().addWidget(self.dayOverrideButton, 3, 5)
		self.connect(self.dayOverrideButton, SIGNAL("released()"),
			     self.dayOverride)

		self.manageButton = QPushButton("Verwalten", self)
		self.layout().addWidget(self.manageButton, 7, 0)
		self.connect(self.manageButton, SIGNAL("released()"),
			     self.doManage)

		self.snapshotButton = QPushButton("Schnappschuss", self)
		self.layout().addWidget(self.snapshotButton, 7, 1)
		self.connect(self.snapshotButton, SIGNAL("released()"),
			     self.doSnapshot)

		self.enhancedButton = QPushButton("Erweitert", self)
		self.layout().addWidget(self.enhancedButton, 7, 2)
		self.connect(self.enhancedButton, SIGNAL("released()"),
			     self.doEnhanced)

		self.output = QLabel(self)
		self.output.setAlignment(Qt.AlignHCenter)
		self.output.setFrameShape(QFrame.Panel)
		self.output.setFrameShadow(QFrame.Raised)
		self.layout().addWidget(self.output, 8, 0, 1, 6)

		self.__resetParams()
		self.__resetCalendar()
		self.recalculate()
		self.dirty = False

		if len(sys.argv) == 2:
			self.doLoadFromFile(sys.argv[1])

	def __resetParams(self):
		self.workTime = 7.0
		self.shiftSched = SHIFTSCHED_EARLY_NIGHT_LATE
		self.earlyGain = 0.8
		self.lateGain = 0.85
		self.nightGain = 1.2
		self.dayGain = 1.0

	def resetParams(self):
		self.__resetParams()
		self.recalculate()
		self.calendar.redraw()

	def __resetCalendar(self):
		self.snapshots = {}
		self.attributes = {}
		self.comments = {}
		self.setFilename(None)

	def resetCalendar(self):
		self.__resetCalendar()
		self.recalculate()
		self.calendar.redraw()

	def doLoadFromFile(self, filename):
		try:
			p = ConfigParser.SafeConfigParser()
			p.read((filename,))

			ver = p.getint("PARAMETERS", "fileversion")
			verExpected = 1
			if ver != verExpected:
				raise TimeshiftException(
					"Dateiversion unbekannt (ist %d, soll %d)" %\
					(ver, verExpected))

			self.__resetParams()
			self.__resetCalendar()

			self.workTime = p.getfloat("PARAMETERS", "workTime")
			self.earlyGain = p.getfloat("PARAMETERS", "earlyGain")
			self.lateGain = p.getfloat("PARAMETERS", "lateGain")
			self.nightGain = p.getfloat("PARAMETERS", "nightGain")
			try:
				self.dayGain = p.getfloat("PARAMETERS", "dayGain")
				self.shiftSched = p.getint("PARAMETERS", "shiftSchedule")
			except (ConfigParser.Error), e:
				pass # Fileversion compatibility

			for attr in p.options("ATTRIBUTES"):
				date = QDate.fromString(attr, Qt.ISODate)
				self.__setAttributes(date, p.getint("ATTRIBUTES", attr))

			for snap in p.options("SNAPSHOTS"):
				date = QDate.fromString(snap, Qt.ISODate)
				string = p.get("SNAPSHOTS", snap)
				try:
					elems = string.split(",")
					shift = int(elems[0])
					accountValue = float(elems[1])
				except (IndexError, ValueError):
					raise TimeshiftException("Datei defekt")
				snapshot = Snapshot(date, shift, accountValue)
				self.__setSnapshot(snapshot)

			try:
				for comm in p.options("COMMENTS"):
					date = QDate.fromString(comm, Qt.ISODate)
					comment = p.get("COMMENTS", comm)
					comment = base64.standard_b64decode(comment)
					comment = comment.decode("utf-8")
					comment = QString(comment)
					self.setCommentFor(date, comment)
			except (ConfigParser.Error), e:
				pass # Fileversion compatibility

			self.dirty = False
			self.setFilename(filename)
			self.recalculate()
			self.calendar.redraw()

		except (ConfigParser.Error, TimeshiftException), e:
			QMessageBox.critical(self, "Laden fehlgeschlagen",
					     "Laden fehlgeschlagen:\n" +\
					     e.message)

	def loadFromFile(self):
		if self.dirty:
			if not self.askSaveToFile():
				return
		fn = QFileDialog.getOpenFileName(self, "Laden", "",
						 "Timeshift Dateien (*.tms)\n" +\
						 "Alle Dateien (*)")
		if fn:
			self.doLoadFromFile(fn)

	def doSaveToFile(self, filename):
		try:
			fd = file(filename, "w+b")

			fd.write("[PARAMETERS]\r\n")
			fd.write("fileversion=1\r\n")
			fd.write("workTime=%f\r\n" % self.workTime)
			fd.write("shiftSchedule=%d\r\n" % self.shiftSched)
			fd.write("earlyGain=%f\r\n" % self.earlyGain)
			fd.write("lateGain=%f\r\n" % self.lateGain)
			fd.write("nightGain=%f\r\n" % self.nightGain)
			fd.write("dayGain=%f\r\n" % self.dayGain)

			fd.write("\r\n[ATTRIBUTES]\r\n")
			for attrKey in self.attributes:
				attr = self.attributes[attrKey]
				date = IdToQDate(attrKey)
				fd.write("%s=%d\r\n" % (date.toString(Qt.ISODate), attr))

			fd.write("\r\n[SNAPSHOTS]\r\n")
			for snapKey in self.snapshots:
				snapshot = self.snapshots[snapKey]
				date = IdToQDate(snapKey)
				shift = snapshot.shift
				value = snapshot.accountValue
				fd.write("%s=%d,%f\r\n" % (date.toString(Qt.ISODate), shift, value))

			fd.write("\r\n[COMMENTS]\r\n")
			for commentKey in self.comments:
				comment = self.comments[commentKey]
				comment = comment.toUtf8()
				comment = unicode(comment, "utf-8").encode("utf-8")
				comment = base64.standard_b64encode(comment)
				date = IdToQDate(commentKey)
				fd.write("%s=%s\r\n" % (date.toString(Qt.ISODate), comment))

			self.dirty = False
			self.setFilename(filename)
		except (IOError), e:
			QMessageBox.critical(self, "Speichern fehlgeschlagen",
					     "Speichern fehlgeschlagen:\n" +\
					     e.strerror)
			return False
		return True

	def saveToFile(self):
		fn = QFileDialog.getSaveFileName(self, "Speichern", "",
						 "Timeshift Dateien (*.tms)")
		if not fn:
			return True
		if not str(fn).endswith(".tms"):
			fn += ".tms"
		return self.doSaveToFile(fn)

	def setFilename(self, filename):
		suffix = None
		if filename:
			fi = QFileInfo(filename)
			suffix = fi.fileName()
		self.parent().setTitleSuffix(suffix)
		self.filename = filename

	def getFilename(self):
		return self.filename

	def dateHasComment(self, date):
		return QDateToId(date) in self.comments

	def getCommentFor(self, date):
		try:
			return self.comments[QDateToId(date)]
		except KeyError:
			return ""

	def setCommentFor(self, date, text):
		if text:
			self.comments[QDateToId(date)] = text
		else:
			self.comments.pop(QDateToId(date), None)
		self.dirty = True

	def doEnhanced(self):
		dlg = EnhancedDialog(self)
		dlg.exec_()

	def doManage(self):
		dlg = ManageDialog(self)
		dlg.exec_()

	def __removeSnapshot(self, date):
		self.snapshots.pop(QDateToId(date), None)
		self.dirty = True

	def removeSnapshot(self, date):
		self.__removeSnapshot(date)
		self.recalculate()
		self.calendar.redraw()

	def __setSnapshot(self, snapshot):
		self.snapshots[QDateToId(snapshot.date)] = snapshot
		self.dirty = True

	def doSnapshot(self):
		date = self.calendar.selectedDate()
		snapshot = self.getSnapshotFor(date)
		shift = None
		accountValue = None
		if snapshot is None:
			# Calculate the account state w.r.t. the
			# last shapshot.
			snapshot = self.__findSnapshot(date)
			if snapshot:
				(shift, unused, startOfTheDay, endOfTheDay) = self.__calcAccountState(snapshot, date)
				accountValue = startOfTheDay
		else:
			# We already have a snapshot on that day. Modify it.
			shift = snapshot.shift
			accountValue = snapshot.accountValue
		dlg = SnapshotDialog(self, date,
				     shift, accountValue)
		if dlg.exec_():
			self.__setSnapshot(dlg.getSnapshot())
			self.recalculate()

	def dateHasSnapshot(self, date):
		return QDateToId(date) in self.snapshots

	def getSnapshotFor(self, date):
		try:
			return self.snapshots[QDateToId(date)]
		except (KeyError):
			return None

	def __setAttributes(self, date, attributes):
		if attributes:
			self.attributes[QDateToId(date)] = attributes
		else:
			self.attributes.pop(QDateToId(date), None)

	def setAttributes(self, date, attributes):
		self.__setAttributes(date, attributes)
		self.dirty = True
		self.recalculate()
		self.calendar.redraw()

	def getAttributes(self, date):
		try:
			return self.attributes[QDateToId(date)]
		except (KeyError):
			return 0

	def toggleAttribute(self, date, mask, attribute):
		attrs = self.getAttributes(date)
		if attrs & attribute:
			attrs &= ~mask
		else:
			attrs &= ~mask
			attrs |= attribute
		self.setAttributes(date, attrs)

	def setShortTimeWork(self):
		date = self.calendar.selectedDate()
		self.toggleAttribute(date, DAYATTR_TYPE_MASK,
				     DAYATTR_SHORTTIME)

	def setCompensatoryTime(self):
		date = self.calendar.selectedDate()
		self.toggleAttribute(date, DAYATTR_TYPE_MASK,
				     DAYATTR_COMPTIME)

	def setHoliday(self):
		date = self.calendar.selectedDate()
		self.toggleAttribute(date, DAYATTR_TYPE_MASK,
				     DAYATTR_HOLIDAY)

	def setFeastday(self):
		date = self.calendar.selectedDate()
		self.toggleAttribute(date, DAYATTR_TYPE_MASK,
				     DAYATTR_FEASTDAY)

	def workOverride(self):
		date = self.calendar.selectedDate()
		weekday = date.dayOfWeek()
		if weekday >= 6:
			self.toggleAttribute(date, DAYATTR_TYPE_MASK,
					     DAYATTR_WORKDAY)

	def earlyOverride(self):
		date = self.calendar.selectedDate()
		self.toggleAttribute(date, DAYATTR_SHIFT_MASK,
				     DAYATTR_SHIFT_EARLY)

	def nightOverride(self):
		date = self.calendar.selectedDate()
		self.toggleAttribute(date, DAYATTR_SHIFT_MASK,
				     DAYATTR_SHIFT_NIGHT)

	def lateOverride(self):
		date = self.calendar.selectedDate()
		self.toggleAttribute(date, DAYATTR_SHIFT_MASK,
				     DAYATTR_SHIFT_LATE)

	def dayOverride(self):
		date = self.calendar.selectedDate()
		self.toggleAttribute(date, DAYATTR_SHIFT_MASK,
				     DAYATTR_SHIFT_DAY)

	def __nextShift(self, shift):
		# Returns the shift next to "shift"
		if self.shiftSched == SHIFTSCHED_EARLY:
			return SHIFT_EARLY
		if self.shiftSched == SHIFTSCHED_LATE:
			return SHIFT_LATE
		if self.shiftSched == SHIFTSCHED_NIGHT:
			return SHIFT_NIGHT
		if self.shiftSched == SHIFTSCHED_DAY:
			return SHIFT_DAY
		if self.shiftSched == SHIFTSCHED_EARLY_LATE:
			if shift == SHIFT_EARLY:
				return SHIFT_LATE
			elif shift == SHIFT_LATE:
				return SHIFT_EARLY
		if self.shiftSched == SHIFTSCHED_EARLY_NIGHT_LATE:
			if shift == SHIFT_EARLY:
				return SHIFT_NIGHT
			elif shift == SHIFT_LATE:
				return SHIFT_EARLY
			elif shift == SHIFT_NIGHT:
				return SHIFT_LATE
		return shift

	def __findSnapshot(self, date):
		# Find a snapshot relative to "date".
		# Searches backwards in time
		snapshot = None
		for key in self.snapshots:
			s = self.snapshots[key]
			if s.date <= date:
				if snapshot is None or s.date >= snapshot.date:
					snapshot = s
		return snapshot

	def __calcAccountState(self, snapshot, endDate):
		date = snapshot.date
		shift = snapshot.shift
		startOfTheDay = snapshot.accountValue
		endOfTheDay = startOfTheDay
		while True:
			assert(date <= endDate)
			attrs = self.getAttributes(date)
			weekday = date.dayOfWeek()

			if weekday >= 1 and weekday <= 5:
				attrs |= DAYATTR_WORKDAY
			else:
				attrs |= DAYATTR_WEEKEND

			if attrs & DAYATTR_SHIFT_EARLY:
				currentShift = SHIFT_EARLY
			elif attrs & DAYATTR_SHIFT_LATE:
				currentShift = SHIFT_LATE
			elif attrs & DAYATTR_SHIFT_NIGHT:
				currentShift = SHIFT_NIGHT
			elif attrs & DAYATTR_SHIFT_DAY:
				currentShift = SHIFT_DAY
			else:
				# Standard shift schedule
				currentShift = shift

			if attrs & DAYATTR_COMPTIME:
				# Compensatory time day
				endOfTheDay -= self.workTime
			elif attrs & DAYATTR_HOLIDAY or attrs & DAYATTR_FEASTDAY:
				# Holidays, yay!
				pass
			elif attrs & DAYATTR_SHORTTIME:
				# Shorttime work
				pass
			elif attrs & DAYATTR_WORKDAY:
				# Workday as usual
				if currentShift == SHIFT_EARLY:
					endOfTheDay += self.earlyGain
				elif currentShift == SHIFT_LATE:
					endOfTheDay += self.lateGain
				elif currentShift == SHIFT_NIGHT:
					endOfTheDay += self.nightGain
				elif currentShift == SHIFT_DAY:
					endOfTheDay += self.dayGain
				else:
					assert(0)

			if date == endDate:
				break
			date = date.addDays(1)
			if date.dayOfWeek() == 1: # Monday
				shift = self.__nextShift(shift)
			startOfTheDay = endOfTheDay

		return (shift, currentShift, startOfTheDay, endOfTheDay)

	def recalculate(self):
		selDate = self.calendar.selectedDate()

		# First find the next snapshot.
		snapshot = self.__findSnapshot(selDate)
		if not snapshot:
			dateString = selDate.toString("dd.MM.yyyy")
			self.output.setText("Kein Schnappschuss vor dem %s gesetzt" %\
					    dateString)
			return

		# Then calculate the account
		(shift, currentShift, startOfTheDay, endOfTheDay) = self.__calcAccountState(snapshot, selDate)

		if currentShift == SHIFT_EARLY:
			shift = "Fruehschicht"
		elif currentShift == SHIFT_LATE:
			shift = "Spaetschicht"
		elif currentShift == SHIFT_NIGHT:
			shift = "Nachtschicht"
		elif currentShift == SHIFT_DAY:
			shift = "Normalschicht"
		else:
			assert(0)
		dateString = selDate.toString("dd.MM.yyyy")
		self.output.setText("Konto in Std am %s (%s):  Beginn: %.2f  Ende: %.2f" %\
			(dateString, shift, startOfTheDay, endOfTheDay))

	def keyPressEvent(self, e):
		if e.modifiers() & Qt.ShiftModifier:
			if e.key() == Qt.Key_F:
				self.earlyOverride()
				e.accept()
			if e.key() == Qt.Key_N:
				self.nightOverride()
				e.accept()
			if e.key() == Qt.Key_S:
				self.lateOverride()
				e.accept()
			if e.key() == Qt.Key_O:
				self.dayOverride()
				e.accept()
		else:
			if e.key() == Qt.Key_Z:
				self.setCompensatoryTime()
				e.accept()
			if e.key() == Qt.Key_U:
				self.setHoliday()
				e.accept()
			if e.key() == Qt.Key_F:
				self.setFeastday()
				e.accept()
			if e.key() == Qt.Key_C:
				self.setShortTimeWork()
				e.accept()
			if e.key() == Qt.Key_A:
				self.workOverride()
				e.accept()

	def askSaveToFile(self):
		res = QMessageBox.question(self, "Ungespeicherte Daten",
					   "Es existieren ungespeicherte Daten.\n" +\
					   "Jetzt speichern?",
					   QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
		if res == QMessageBox.Cancel:
			return False
		if res == QMessageBox.Yes:
			if self.getFilename():
				return self.doSaveToFile(self.getFilename())
			return self.saveToFile()
		return True

	def shutdown(self):
		if not self.dirty:
			return True
		return self.askSaveToFile()

class MainWindow(QMainWindow):
	def __init__(self, parent=None):
		QMainWindow.__init__(self, parent)
		self.setTitleSuffix(None)

		self.setCentralWidget(MainWidget(self))

	def setTitleSuffix(self, suffix):
		title = "Zeitkontoberechnung"
		if suffix:
			title += " - " + suffix
		self.setWindowTitle(title)

	def closeEvent(self, e):
		if not self.centralWidget().shutdown():
			e.ignore()

def main(argv):
	app = QApplication(argv)
	mainwnd = MainWindow()
	mainwnd.show()
	return app.exec_()

if __name__ == "__main__":
	sys.exit(main(sys.argv))
