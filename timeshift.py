#!/usr/bin/env python
"""
# timeshift.py
# Copyright (c) 2009-2010 Michael Buesch <mb@bu3sch.de>
# Licensed under the GNU/GPL version 2 or later.
"""

import sys
import os
import errno
import ConfigParser
import base64
from PyQt4.QtCore import *
from PyQt4.QtGui import *


MAX_SHIFTCONFIG_ITEMS	= 1024

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


def floatEqual(f0, f1):
	return abs(f0 - f1) < 0.001

def QDateToId(qdate):
	"Convert a QDate object to a unique integer ID"
	return QDateTime(qdate).toTime_t()

def IdToQDate(id):
	"Convert a unique integer ID to a QDate object"
	return QDateTime.fromTime_t(id).date()

def QStringToBase64(qstring):
	if type(qstring) != type(QString()):
		qstring = QString(qstring)
	qstring = qstring.toUtf8()
	unistr = unicode(qstring, "utf-8").encode("utf-8")
	b64str = base64.standard_b64encode(unistr)
	return b64str

def base64ToQString(b64str):
	unistr = base64.standard_b64decode(b64str)
	unistr = unistr.decode("utf-8")
	qstring = QString(unistr)
	return qstring

class TsException(Exception): pass

class TimeSpinBox(QDoubleSpinBox):
	def __init__(self, parent, val=0.0, minVal=0.0, maxVal=10.0,
		     step=0.05, prefix=None, suffix="h"):
		QDoubleSpinBox.__init__(self, parent)
		self.setMinimum(minVal)
		self.setMaximum(maxVal)
		self.setValue(val)
		self.setSingleStep(step)
		if suffix:
			self.setSuffix(" " + suffix)
		if prefix:
			self.setPrefix(prefix + " ")

class ShiftConfigItem:
	def __init__(self, name, shift, workTime, breakTime, attendanceTime):
		self.name = name
		self.shift = shift
		self.workTime = workTime
		self.breakTime = breakTime
		self.attendanceTime = attendanceTime

defaultShiftConfig = [
	ShiftConfigItem("Montag",     SHIFT_DAY, 7.0, 0.5, 8.5),
	ShiftConfigItem("Dienstag",   SHIFT_DAY, 7.0, 0.5, 8.5),
	ShiftConfigItem("Mittwoch",   SHIFT_DAY, 7.0, 0.5, 8.5),
	ShiftConfigItem("Donnerstag", SHIFT_DAY, 7.0, 0.5, 8.5),
	ShiftConfigItem("Freitag",    SHIFT_DAY, 7.0, 0.5, 8.5),
	ShiftConfigItem("Samstag",    SHIFT_DAY, 0.0, 0.5, 0.0),
	ShiftConfigItem("Sonntag",    SHIFT_DAY, 0.0, 0.0, 0.0),
]

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
		count = 1
		for cfg in self.mainWidget.shiftConfig:
			name = "%d (%s)" % (count, cfg.name)
			count += 1
			self.itemList.addItem(name)
		if self.mainWidget.shiftConfig:
			self.itemList.setCurrentRow(0)
			currentItem = self.mainWidget.shiftConfig[0]
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
		item.shift = self.shiftCombo.itemData(index).toInt()[0]
		item.workTime = self.workTime.value()
		item.breakTime = self.breakTime.value()
		item.attendanceTime = self.attendanceTime.value()
		self.mainWidget.dirty = True

	def itemChanged(self, row):
		if row >= 0:
			self.loadItem(self.mainWidget.shiftConfig[row])

	def updateCurrentItem(self):
		if self.updateBlocked:
			return
		index = self.itemList.currentRow()
		if index < 0:
			return
		self.updateItem(self.mainWidget.shiftConfig[index])
		name = "%d (%s)" % (index + 1, self.mainWidget.shiftConfig[index].name)
		self.itemList.item(index).setText(name)

	def addItem(self):
		if len(self.mainWidget.shiftConfig) >= MAX_SHIFTCONFIG_ITEMS:
			return
		index = self.itemList.currentRow()
		if index < 0:
			index = 0
		else:
			index += 1
		item = defaultShiftConfig[:][0]
		item.name = "Unbenannt"
		self.mainWidget.shiftConfig.insert(index, item)
		self.loadConfig()
		self.itemList.setCurrentRow(index)
		self.mainWidget.dirty = True

	def removeItem(self):
		index = self.itemList.currentRow()
		if index < 0:
			return
		res = QMessageBox.question(self, "Eintrag loeschen?",
					   "'%s' loeschen?" % self.itemList.item(index).text(),
					   QMessageBox.Yes | QMessageBox.No)
		if res != QMessageBox.Yes:
			return
		self.mainWidget.shiftConfig.pop(index)
		self.loadConfig()
		if index >= self.itemList.count() and index > 0:
			index -= 1
		self.itemList.setCurrentRow(index)
		self.mainWidget.dirty = True

class EnhancedDialog(QDialog):
	def __init__(self, mainWidget):
		QDialog.__init__(self, mainWidget)
		self.mainWidget = mainWidget
		self.setWindowTitle("Erweitert")
		self.setLayout(QGridLayout())

		self.dayInfo = QLabel(self)#TODO
		self.layout().addWidget(self.dayInfo, 0, 0, 1, 2)

		self.commentGroup = QGroupBox("Kommentar", self)
		self.commentGroup.setLayout(QGridLayout())
		self.layout().addWidget(self.commentGroup, 1, 0, 1, 2)

		self.comment = QTextEdit(self)
		self.commentGroup.layout().addWidget(self.comment, 0, 0)
		date = mainWidget.calendar.selectedDate()
		self.comment.document().setPlainText(mainWidget.getCommentFor(date))

		self.okButton = QPushButton("OK", self)
		self.layout().addWidget(self.okButton, 2, 0)
		self.connect(self.okButton, SIGNAL("released()"),
			     self.ok)

		self.cancelButton = QPushButton("Abbrechen", self)
		self.layout().addWidget(self.cancelButton, 2, 1)
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

		self.schedConfButton = QPushButton("Schichtkonfig", self)
		self.fileGroup.layout().addWidget(self.schedConfButton, 4, 0)
		self.connect(self.schedConfButton, SIGNAL("released()"),
			     self.doShiftConfig)

		self.paramsGroup = QGroupBox("Parameter", self)
		self.paramsGroup.setLayout(QGridLayout())
		self.layout().addWidget(self.paramsGroup, 0, 2)

		#TODO holiday

		self.resetParamsButton = QPushButton("Parameter ruecksetzen", self)
		self.paramsGroup.layout().addWidget(self.resetParamsButton, 6, 0, 1, 2)
		self.connect(self.resetParamsButton, SIGNAL("released()"),
			     self.resetParams)

		self.loadParams()

	def loadParams(self):
		pass#TODO

	def updateParams(self):
		mainWidget = self.mainWidget
		mainWidget.dirty = True
		#TODO
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

	def doShiftConfig(self):
		dlg = ShiftConfigDialog(self.mainWidget)
		dlg.exec_()
		self.mainWidget.recalculate()
		#FIXME need to fixup (kill?) snapshots that have an out-of-range shiftConfigIndex
		self.accept()

class Snapshot:
	def __init__(self, date, shiftConfigIndex, accountValue):
		self.date = date
		self.shiftConfigIndex = shiftConfigIndex
		self.accountValue = accountValue

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
		assert(mainWidget.shiftConfig)
		index = 0
		for cfg in mainWidget.shiftConfig:
			name = "%d (%s)" % (index + 1, cfg.name)
			self.shiftConfig.addItem(name, QVariant(index))
			index += 1
		self.layout().addWidget(self.shiftConfig, 1, 1)
		index = self.shiftConfig.findData(QVariant(shiftConfigIndex))
		if index >= 0:
			self.shiftConfig.setCurrentIndex(index)

		l = QLabel("Kontostand:", self)
		self.layout().addWidget(l, 2, 0)
		self.accountValue = QDoubleSpinBox(self)
		self.accountValue.setMinimum(-1000.0)
		self.accountValue.setMaximum(1000.0)
		self.accountValue.setValue(accountValue)
		self.accountValue.setSuffix(" h")
		self.accountValue.setSingleStep(0.1)
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
		shiftConfigIndex = self.shiftConfig.itemData(index).toInt()[0]
		value = self.accountValue.value()
		return Snapshot(self.date, shiftConfigIndex, value)

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

		dtype = self.mainWidget.getDayType(date)
		typeLetter = {
			DTYPE_DEFAULT		: None,
			DTYPE_COMPTIME		: "Z",
			DTYPE_HOLIDAY		: "U",
			DTYPE_SHORTTIME		: "C",
			DTYPE_FEASTDAY		: "F",
		}
		lowerLeft = typeLetter[dtype]

		lowerRight = None
		try:
			shiftOverride = self.mainWidget.shiftOverrides[QDateToId(date)]
			shiftLetter = {
				SHIFT_EARLY	: "F",
				SHIFT_LATE	: "S",
				SHIFT_NIGHT	: "N",
				SHIFT_DAY	: "O",
			}
			lowerRight = shiftLetter[shiftOverride]
		except (KeyError):
			pass

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
		self.shiftConfig = defaultShiftConfig[:]

	def resetParams(self):
		self.__resetParams()
		self.recalculate()
		self.calendar.redraw()

	def __resetCalendar(self):
		self.snapshots = {}
		self.daytypeOverrides = {}
		self.shiftOverrides = {}
		self.workTimeOverrides = {}
		self.breakTimeOverrides = {}
		self.attendanceTimeOverrides = {}
		self.comments = {}
		self.setFilename(None)

	def resetCalendar(self):
		self.__resetCalendar()
		self.recalculate()
		self.calendar.redraw()

	def __genShiftCfgWeek(self, shift, workTime, workGain, breakTime):
		attendanceTime = workTime + breakTime + workGain
		shiftcfg = [
			ShiftConfigItem("Montag", shift, workTime, breakTime, attendanceTime),
			ShiftConfigItem("Dienstag", shift, workTime, breakTime, attendanceTime),
			ShiftConfigItem("Mittwoch", shift, workTime, breakTime, attendanceTime),
			ShiftConfigItem("Donnerstag", shift, workTime, breakTime, attendanceTime),
			ShiftConfigItem("Freitag", shift, workTime, breakTime, attendanceTime),
			ShiftConfigItem("Samstag", shift, 0.0, breakTime, 0.0),
			ShiftConfigItem("Sonntag", shift, 0.0, 0.0, 0.0),
		]
		return shiftcfg

	def __parseFile_ver1(self, p):
		# ver1 compat import layer
		defaultBreakTime = 0.5
		workTime = p.getfloat("PARAMETERS", "workTime")
		shiftcfgEarly = self.__genShiftCfgWeek(SHIFT_EARLY, workTime,
					p.getfloat("PARAMETERS", "earlyGain"),
					defaultBreakTime)
		shiftcfgLate = self.__genShiftCfgWeek(SHIFT_LATE, workTime,
					p.getfloat("PARAMETERS", "lateGain"),
					defaultBreakTime)
		shiftcfgNight = self.__genShiftCfgWeek(SHIFT_NIGHT, workTime,
					p.getfloat("PARAMETERS", "nightGain"),
					defaultBreakTime)
		shiftcfgDay = self.__genShiftCfgWeek(SHIFT_DAY, workTime,
					p.getfloat("PARAMETERS", "dayGain"),
					defaultBreakTime)
		earlyIndex = None
		lateIndex = None
		nightIndex = None
		dayIndex = None
		shiftSched = p.getint("PARAMETERS", "shiftSchedule")
		if shiftSched == 0: # early only
			self.shiftConfig = shiftcfgEarly[:]
			earlyIndex = 0
		elif shiftSched == 1: # late only
			self.shiftConfig = shiftcfgLate[:]
			lateIndex = 0
		elif shiftSched == 2: # night only
			self.shiftConfig = shiftcfgNight[:]
			nightIndex = 0
		elif shiftSched == 3: # day only
			self.shiftConfig = shiftcfgDay[:]
			dayIndex = 0
		elif shiftSched == 4: # early->late
			self.shiftConfig = shiftcfgEarly[:]
			self.shiftConfig.extend(shiftcfgLate[:])
			earlyIndex = 0
			lateIndex = 7
		elif shiftSched == 5: # early->night->late
			self.shiftConfig = shiftcfgEarly[:]
			self.shiftConfig.extend(shiftcfgNight[:])
			self.shiftConfig.extend(shiftcfgLate[:])
			earlyIndex = 0
			nightIndex = 7
			lateIndex = 14
		else:
			raise TsException("Unknown shift schedule")

		for dateString in p.options("SNAPSHOTS"):
			date = QDate.fromString(dateString, Qt.ISODate)
			payload = p.get("SNAPSHOTS", dateString)
			try:
				elems = payload.split(",")
				shift = int(elems[0])
				accountValue = float(elems[1])
			except (IndexError, ValueError):
				raise TsException("Datei defekt (snapshot)")
			dayOfWeek = date.dayOfWeek() - 1
			shiftConfigIndexMap = {
				SHIFT_EARLY	: earlyIndex,
				SHIFT_LATE	: lateIndex,
				SHIFT_NIGHT	: nightIndex,
				SHIFT_DAY	: dayIndex,
			}
			try:
				shiftConfigIndex = shiftConfigIndexMap[shift]
				if shiftConfigIndex is None:
					raise ValueError
			except (IndexError, ValueError):
				raise TsException("Datei defekt (snapshot shift)")
			shiftConfigIndex += dayOfWeek
			snapshot = Snapshot(date, shiftConfigIndex, accountValue)
			self.__setSnapshot(snapshot)

		for dateString in p.options("ATTRIBUTES"):
			date = QDate.fromString(dateString, Qt.ISODate)
			attrs = p.getint("ATTRIBUTES", dateString)
			if attrs & (1 << 2):
				self.setDayType(date, DTYPE_COMPTIME)
			if attrs & (1 << 3):
				self.setDayType(date, DTYPE_HOLIDAY)
			if attrs & (1 << 4):
				self.setDayType(date, DTYPE_SHORTTIME)
			if attrs & (1 << 9):
				self.setDayType(date, DTYPE_FEASTDAY)
			if attrs & (1 << 5):
				self.setShiftOverride(date, SHIFT_EARLY)
			if attrs & (1 << 6):
				self.setShiftOverride(date, SHIFT_LATE)
			if attrs & (1 << 7):
				self.setShiftOverride(date, SHIFT_NIGHT)
			if attrs & (1 << 8):
				self.setShiftOverride(date, SHIFT_DAY)

		for comm in p.options("COMMENTS"):
			date = QDate.fromString(comm, Qt.ISODate)
			comment = base64ToQString(p.get("COMMENTS", comm))
			self.setCommentFor(date, comment)

	def __readOverrides(self, p, dateDict, section, floatFormat):
		for date in p.options(section):
			payload = p.get(section, date)
			try:
				if floatFormat:
					payload = float(payload)
				else:
					payload = int(payload)
			except (ValueError):
				raise TsException("Datei defekt")
			dateDict[QDateToId(QDate.fromString(date, Qt.ISODate))] = payload

	def __parseFile_ver2(self, p):
		self.shiftConfig = []
		for count in range(0, MAX_SHIFTCONFIG_ITEMS):
			try:
				name = p.get("SHIFTCONFIG", "name%d" % count)
			except (ConfigParser.Error), e:
				break
			shift = p.getint("SHIFTCONFIG", "shift%d" % count)
			workTime = p.getfloat("SHIFTCONFIG", "workTime%d" % count)
			breakTime = p.getfloat("SHIFTCONFIG", "breakTime%d" % count)
			attendanceTime = p.getfloat("SHIFTCONFIG", "attendanceTime%d" % count)
			self.shiftConfig.append(
				ShiftConfigItem(name=base64ToQString(name),
						shift=shift,
						workTime=workTime, breakTime=breakTime,
						attendanceTime=attendanceTime)
			)
			count += 1

		for snap in p.options("SNAPSHOTS"):
			date = QDate.fromString(snap, Qt.ISODate)
			string = p.get("SNAPSHOTS", snap)
			try:
				elems = string.split(",")
				shiftConfigIndex = int(elems[0])
				accountValue = float(elems[1])
			except (IndexError, ValueError):
				raise TsException("Datei defekt")
			snapshot = Snapshot(date, shiftConfigIndex, accountValue)
			self.__setSnapshot(snapshot)

		self.__readOverrides(p, self.daytypeOverrides, "DAYTYPE_OVERRIDES", False)
		self.__readOverrides(p, self.shiftOverrides, "SHIFT_OVERRIDES", False)
		self.__readOverrides(p, self.workTimeOverrides, "WORKTIME_OVERRIDES", True)
		self.__readOverrides(p, self.breakTimeOverrides, "BREAKTIME_OVERRIDES", True)
		self.__readOverrides(p, self.attendanceTimeOverrides, "ATTENDANCETIME_OVERRIDES", True)

		for comm in p.options("COMMENTS"):
			date = QDate.fromString(comm, Qt.ISODate)
			comment = base64ToQString(p.get("COMMENTS", comm))
			self.setCommentFor(date, comment)

	def doLoadFromFile(self, filename):
		try:
			p = ConfigParser.SafeConfigParser()
			p.read((filename,))

			ver = p.getint("PARAMETERS", "fileversion")
			if ver == 1:
				parser = self.__parseFile_ver1
			elif ver == 2:
				parser = self.__parseFile_ver2
			else:
				raise TsException("Dateiversion nicht unterstuetzt")

			self.__resetParams()
			self.__resetCalendar()

			parser(p)

			self.dirty = False
			self.setFilename(filename)
			self.recalculate()
			self.calendar.redraw()

		except (ConfigParser.Error, TsException), e:
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

	def __writeOverrides(self, fd, dateDict, section, floatFormat):
		fd.write("\r\n[%s]\r\n" % section)
		for date in dateDict:
			payload = dateDict[date]
			if floatFormat:
				fmt = "%s=%f\r\n"
			else:
				fmt = "%s=%d\r\n"
			fd.write(fmt % (IdToQDate(date).toString(Qt.ISODate),
					payload))

	def doSaveToFile(self, filename):
		for i in range(0, 128):
			tmpFilename = "%s.tmp%d" % (filename, i)
			try:
				os.stat(tmpFilename)
			except (OSError), e:
				if e.errno == errno.ENOENT:
					break
		else:
			QMessageBox.critical(self, "Speichern fehlgeschlagen",
					     "Speichern fehlgeschlagen:\n" +\
					     "Tmp file error")
			return False
		try:
			fd = file(tmpFilename, "w+b")

			fd.write("[PARAMETERS]\r\n")
			fd.write("fileversion=2\r\n")

			fd.write("\r\n[SHIFTCONFIG]\r\n")
			count = 0
			for cfg in self.shiftConfig:
				fd.write("name%d=%s\r\n" % (count, QStringToBase64(cfg.name)))
				fd.write("shift%d=%d\r\n" % (count, cfg.shift))
				fd.write("workTime%d=%f\r\n" % (count, cfg.workTime))
				fd.write("breakTime%d=%f\r\n" % (count, cfg.breakTime))
				fd.write("attendanceTime%d=%f\r\n" % (count, cfg.attendanceTime))
				count += 1

			fd.write("\r\n[SNAPSHOTS]\r\n")
			for snapKey in self.snapshots:
				snapshot = self.snapshots[snapKey]
				date = IdToQDate(snapKey)
				shift = snapshot.shiftConfigIndex
				value = snapshot.accountValue
				fd.write("%s=%d,%f\r\n" % (date.toString(Qt.ISODate), shift, value))

			self.__writeOverrides(fd, self.daytypeOverrides, "DAYTYPE_OVERRIDES", False)
			self.__writeOverrides(fd, self.shiftOverrides, "SHIFT_OVERRIDES", False)
			self.__writeOverrides(fd, self.workTimeOverrides, "WORKTIME_OVERRIDES", True)
			self.__writeOverrides(fd, self.breakTimeOverrides, "BREAKTIME_OVERRIDES", True)
			self.__writeOverrides(fd, self.attendanceTimeOverrides, "ATTENDANCETIME_OVERRIDES", True)

			fd.write("\r\n[COMMENTS]\r\n")
			for commentKey in self.comments:
				comment = QStringToBase64(self.comments[commentKey])
				date = IdToQDate(commentKey)
				fd.write("%s=%s\r\n" % (date.toString(Qt.ISODate), comment))

			fd.flush()
			fd.close()
			os.rename(tmpFilename, filename)

			self.dirty = False
			self.setFilename(filename)
		except (IOError), e:
			QMessageBox.critical(self, "Speichern fehlgeschlagen",
					     "Speichern fehlgeschlagen:\n" +\
					     e.strerror)
			try:
				os.unlink(tmpFilename)
			except (IOError):
				pass
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
		if not self.shiftConfig:
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
			snapshot = self.__findSnapshot(date)
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
			self.recalculate()

	def dateHasSnapshot(self, date):
		return QDateToId(date) in self.snapshots

	def getSnapshotFor(self, date):
		try:
			return self.snapshots[QDateToId(date)]
		except (KeyError):
			return None

	def overrideChanged(self):
		if self.overrideChangeBlocked or not self.shiftConfig:
			return
		date = self.calendar.selectedDate()
		shiftConfigIndex = self.__getShiftConfigIndexForDate(date)
		if shiftConfigIndex < 0:
			return #FIXME should disable controls, so that this does not happen.
		shiftConfigItem = self.shiftConfig[shiftConfigIndex]

		# Day type
		index = self.typeCombo.currentIndex()
		self.setDayType(date, self.typeCombo.itemData(index).toInt()[0])

		# Shift override
		index = self.shiftCombo.currentIndex()
		shift = self.shiftCombo.itemData(index).toInt()[0]
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

		self.calendar.redraw()

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

	def __getShiftConfigIndexForDate(self, date):
		# Find the shift config index that's valid for the date.
		# May return -1 on error.
		snapshot = self.__findSnapshot(date)
		if not snapshot:
			return -1
		daysBetween = snapshot.date.daysTo(date)
		assert(daysBetween >= 0)
		index = snapshot.shiftConfigIndex
		index += daysBetween
		index %= len(self.shiftConfig)
		return index

	def getDayType(self, date):
		try:
			return self.daytypeOverrides[QDateToId(date)]
		except (KeyError):
			return DTYPE_DEFAULT

	def setDayType(self, date, dtype):
		if dtype == DTYPE_DEFAULT:
			self.daytypeOverrides.pop(QDateToId(date), None)
		else:
			self.daytypeOverrides[QDateToId(date)] = dtype
		self.dirty = True

	def setShiftOverride(self, date, shift):
		if shift is None:
			self.shiftOverrides.pop(QDateToId(date), None)
		else:
			self.shiftOverrides[QDateToId(date)] = shift
		self.dirty = True

	def __getRealShift(self, date, shiftConfigItem):
		try: # Check for override
			return self.shiftOverrides[QDateToId(date)]
		except (KeyError): # Use standard schedule
			return shiftConfigItem.shift

	def setWorkTimeOverride(self, date, workTime):
		if workTime is None:
			self.workTimeOverrides.pop(QDateToId(date), None)
		else:
			self.workTimeOverrides[QDateToId(date)] = workTime
		self.dirty = True

	def __getRealWorkTime(self, date, shiftConfigItem):
		try: # Check for override
			return self.workTimeOverrides[QDateToId(date)]
		except (KeyError): # Use standard schedule
			return shiftConfigItem.workTime

	def setBreakTimeOverride(self, date, breakTime):
		if breakTime is None:
			self.breakTimeOverrides.pop(QDateToId(date), None)
		else:
			self.breakTimeOverrides[QDateToId(date)] = breakTime
		self.dirty = True

	def __getRealBreakTime(self, date, shiftConfigItem):
		try: # Check for override
			return self.breakTimeOverrides[QDateToId(date)]
		except (KeyError): # Use standard schedule
			return shiftConfigItem.breakTime

	def setAttendanceTimeOverride(self, date, attendanceTime):
		if attendanceTime is None:
			self.attendanceTimeOverrides.pop(QDateToId(date), None)
		else:
			self.attendanceTimeOverrides[QDateToId(date)] = attendanceTime
		self.dirty = True

	def __getRealAttendanceTime(self, date, shiftConfigItem):
		try: # Check for override
			return self.attendanceTimeOverrides[QDateToId(date)]
		except (KeyError): # Use standard schedule
			return shiftConfigItem.attendanceTime

	def __calcAccountState(self, snapshot, endDate):
		date = snapshot.date
		shiftConfigIndex = snapshot.shiftConfigIndex
		startOfTheDay = snapshot.accountValue
		endOfTheDay = startOfTheDay
		while True:
			assert(date <= endDate)

			shiftConfigItem = self.shiftConfig[shiftConfigIndex]
			currentShift = self.__getRealShift(date, shiftConfigItem)
			workTime = self.__getRealWorkTime(date, shiftConfigItem)
			breakTime = self.__getRealBreakTime(date, shiftConfigItem)
			attendanceTime = self.__getRealAttendanceTime(date, shiftConfigItem)

			dtype = self.getDayType(date)
			if dtype == DTYPE_DEFAULT:
				if attendanceTime:
					endOfTheDay += attendanceTime
					endOfTheDay -= workTime
					endOfTheDay -= breakTime
			elif dtype == DTYPE_COMPTIME:
				endOfTheDay -= workTime
			elif dtype == DTYPE_HOLIDAY:
				pass#TODO calc holidays
			elif dtype == DTYPE_FEASTDAY:
				pass # no change
			elif dtype == DTYPE_SHORTTIME:
				pass # no change
			else:
				assert(0)

			if date == endDate:
				break
			date = date.addDays(1)
			shiftConfigIndex += 1
			if shiftConfigIndex >= len(self.shiftConfig):
				shiftConfigIndex = 0
			startOfTheDay = endOfTheDay

		return (shiftConfigIndex, startOfTheDay, endOfTheDay)

	def recalculate(self):
		selDate = self.calendar.selectedDate()

		if not self.shiftConfig:
			self.output.setText("Kein Schichtsystem konfiguriert")
			return

		# First find the next snapshot.
		snapshot = self.__findSnapshot(selDate)
		if not snapshot:
			dateString = selDate.toString("dd.MM.yyyy")
			self.output.setText("Kein Schnappschuss vor dem %s gesetzt" %\
					    dateString)
			return

		# Then calculate the account state
		(shiftConfigIndex, startOfTheDay, endOfTheDay) = self.__calcAccountState(snapshot, selDate)

		shiftConfigItem = self.shiftConfig[shiftConfigIndex]
		dtype = self.getDayType(selDate)
		shift = self.__getRealShift(selDate, shiftConfigItem)
		workTime = self.__getRealWorkTime(selDate, shiftConfigItem)
		breakTime = self.__getRealBreakTime(selDate, shiftConfigItem)
		attendanceTime = self.__getRealAttendanceTime(selDate, shiftConfigItem)

		self.overrideChangeBlocked = True
		self.typeCombo.setCurrentIndex(self.typeCombo.findData(QVariant(dtype)))
		self.shiftCombo.setCurrentIndex(self.shiftCombo.findData(QVariant(shift)))
		self.workTime.setValue(workTime)
		self.breakTime.setValue(breakTime)
		self.attendanceTime.setValue(attendanceTime)
		self.overrideChangeBlocked = False

		dateString = selDate.toString("dd.MM.yyyy")
		self.output.setText("Konto in Std am %s (shiftcfg %d):  Beginn: %.2f  Ende: %.2f" %\
			(dateString, shiftConfigIndex + 1, startOfTheDay, endOfTheDay))

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
		title = "Zeitkonto"
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
