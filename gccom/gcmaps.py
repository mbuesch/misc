#!/usr/bin/env python
# vim: set fileencoding=UTF-8 :
"""
# Tiny Geocaching mapping tool
# (c) Copyright 2011 Michael Buesch
# Licensed under the GNU/GPL version 2 or later.
"""

import sys
import os
import time
import multiprocessing
import re
import getopt

from mapwidget import *
from geopy.distance import VincentyDistance as Distance

import gccom

try:
	import gps
except (ImportError), e:
	gps = None

DEBUG			= 1

EVENT_TASKFINISHED	= QEvent.User + 0

CACHECOUNT_LIMIT	= 200	# 200 is gc.com max
BASEDIR			= os.getcwd()
CACHEICON_URL		= "file://%s/icons/trad.png" % BASEDIR
GPSICON_URL		= "file://%s/icons/gps.png" % BASEDIR

useWebProxy		= True
useGPS			= True


def printDebug(message):
	if DEBUG:
		print message

def printVerbose(message):
	if DEBUG >= 2:
		print message

def replaceAll(string, chars, by):
	def __replace(c):
		if c in chars:
			return by
		return c
	return "".join(map(__replace, string))

def parseCoord(string):
	string = replaceAll(str(string), "NEO*\'\"", "")
	values = string.split()
	try:
		if len(values) == 3:
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
			return None
	except ValueError:
		return None
	return degree

def formatCoord(prefix, degree):
	return "%s %d* %.3f" %\
		(prefix,
		 int(degree),
		 (degree - int(degree)) * 60)

class GpsWrapper:
	def __init__(self):
		if gps is None or not useGPS:
			self.g = None
		else:
			self.g = gps.gps()
			self.g.poll()
			self.g.stream()

	def present(self):
		return self.g is not None

	def getPos(self):
		self.g.poll()
		fix = self.g.fix
		if abs(fix.latitude) < 0.0001 and abs(fix.longitude) < 0.0001:
			return None
		return geo.Point(fix.latitude, fix.longitude)

class TaskContext:
	def __init__(self, name, parameters=(),
		     userid=None, userdata=None):
		self.name = name
		self.parameters = parameters
		self.userid = userid
		self.userdata = userdata
		self.sync = False
		self.taskID = None
		self.retval = None

	def __eq__(self, other):
		return self.taskID == other

	def __ne__(self, other):
		return not self.__eq__(other)

class GCSubprocessWorker:
	def __init__(self):
		self.gccom = None

	def run(self, task, parameters):
		# This runs in the subprocess

		task = task.strip()
		if task.endswith(")"): # strip (...) suffix
			task = task[:task.rfind("(")]
		# Create parameter string list
		paramList = []
		for i in range(0, len(parameters)):
			paramList.append("parameters[%d]" % i)

		retval = None
		exception = None
		try:
			if task.startswith("gccom."):
				task = task[6:]
				commandCode = "self.gccom.%s(%s)" % (task, ", ".join(paramList))
				retval = eval(commandCode)
			elif task == "login":
				(user, passwd) = parameters
				self.gccom = gccom.GC(user=user, password=passwd,
						      debug=DEBUG, storage=True)
				retval = True
			elif task == "logout":
				self.gccom.logout()
				self.gccom = None
			else:
				assert(0)
		except (gccom.GCException), exception:
			pass
		return (retval, exception)

class GCSubprocess(QObject):
	def __init__(self, mainWindow):
		QObject.__init__(self)
		self.mainWindow = mainWindow

		self.taskCounter = 0
		self.queuedTasks = []

		self.pollTimer = QTimer(self)
		self.connect(self.pollTimer, SIGNAL("timeout()"), self.__poll)

		self.event = multiprocessing.Event()
		(self.asyncConn, childAsyncConn) = multiprocessing.Pipe()
		(self.syncConn, childSyncConn) = multiprocessing.Pipe()
		(self.revokeConn, childRevokeConn) = multiprocessing.Pipe()
		self.process = multiprocessing.Process(target=self.__subprocess,
						       args=(self.event,
							     childSyncConn,
							     childAsyncConn,
							     childRevokeConn))
		self.process.start()
		self.isOnline = False
		self.isRunning = True

	def login(self, parentWidget):
		if self.isOnline:
			return
		try:
			acc = file("account", "rb").read().split()
			user = acc[0]
			passwd = acc[1]
		except (IOError, IndexError), e:
			(user, ok) = QInputDialog.getText(parentWidget, "Geocaching.com username",
							  "Geocaching.com username",
							  mode=QLineEdit.Normal)
			if not user or not ok:
				raise gccom.GCException("No login name given")
			(passwd, ok) = QInputDialog.getText(parentWidget, "Geocaching.com password",
							    "Geocaching.com password for account %s" % user,
							    mode=QLineEdit.Password)
			if not passwd or not ok:
				raise gccom.GCException("No login password given")
		taskContext = self.executeSync(
				TaskContext("login(...)", (str(user), str(passwd))))
		(retval, exception) = taskContext.retval
		if exception:
			QMessageBox.critical(parentWidget, "Geocaching.com login failed",
					     "Geocaching.com login failed:\n" + str(exception))
			raise exception
		self.isOnline = True

	def logout(self):
		if self.isOnline:
			self.executeSync(TaskContext("logout"))
			self.isOnline = False

	def online(self):
		return self.isOnline

	def nrTasksPending(self):
		return len(self.queuedTasks)

	def __startTask(self, taskContext, sync):
		if not self.queuedTasks:
			self.pollTimer.start(100)
		self.queuedTasks.append(taskContext)
		if sync:
			self.syncConn.send(taskContext)
		else:
			self.asyncConn.send(taskContext)
		self.event.set()

	def __fetchTaskRetval(self, connection, wait):
		if wait: # Blocking
			connection.poll(None)
		else: # Nonblocking
			if not connection.poll(0):
				return None
		taskContext = connection.recv()
		try:
			self.queuedTasks.remove(taskContext)
		except ValueError:
			return None # Already revoked
		if not self.queuedTasks:
			self.pollTimer.stop()
		return taskContext

	def __poll(self):
		if self.asyncConn.poll(0):
			QApplication.postEvent(self.mainWindow,
					       QEvent(EVENT_TASKFINISHED))

	def __newTaskID(self):
		taskID = self.taskCounter
		self.taskCounter = (self.taskCounter + 1) & 0x7FFFFFFF
		return taskID

	def executeSync(self, taskContext):
		taskID = self.__newTaskID()
		taskContext.taskID = taskID
		taskContext.sync = True
		self.__startTask(taskContext, True)
		taskContext = self.__fetchTaskRetval(connection=self.syncConn,
						     wait=True)
		return taskContext

	def execute(self, taskContext):
		taskID = self.__newTaskID()
		taskContext.taskID = taskID
		taskContext.sync = False
		self.__startTask(taskContext, False)

	def cancelTasks(self, cancelTaskNames):
		revokeIDs = []
		for taskContext in self.queuedTasks:
			if taskContext.sync:
				continue
			if taskContext.name not in cancelTaskNames:
				continue
			revokeIDs.append(taskContext.taskID)
		for revokeID in revokeIDs:
			self.revokeConn.send(revokeID)
			self.event.set()
			self.queuedTasks.remove(revokeID)

	def killThread(self):
		if self.isRunning:
			self.execute(TaskContext("exit"))
			self.process.join()
			self.isRunning = False

	@staticmethod
	def __subprocess(event, syncConn, asyncConn, revokeConn):
		worker = GCSubprocessWorker()
		revokeIDs = []
		while True:
			if not syncConn.poll(0) and\
			   not asyncConn.poll(0) and\
			   not revokeConn.poll(0):
				event.wait() # Block
				event.clear()

			while syncConn.poll(0):
				taskContext = syncConn.recv()
				taskContext.retval  = worker.run(taskContext.name,
								 taskContext.parameters)
				syncConn.send(taskContext)

			while revokeConn.poll(0):
				taskID = revokeConn.recv()
				revokeIDs.append(taskID)

			if asyncConn.poll(0):
				taskContext = asyncConn.recv()
				if taskContext.taskID in revokeIDs:
					continue
				if taskContext.name == "exit":
					break
				taskContext.retval = worker.run(taskContext.name,
								taskContext.parameters)
				asyncConn.send(taskContext)
			else:
				revokeIDs = []
		for conn in (syncConn, asyncConn, revokeConn):
			conn.close()

	def fetchRetval(self):
		taskContext = self.__fetchTaskRetval(connection=self.asyncConn,
						     wait=False)
		return taskContext

class CacheDetails:
	def __init__(self, guid):
		self.guid = guid
		self.info = None

	def __eq__(self, other):
		return self.guid == other.guid

	def __ne__(self, other):
		return not self.__eq__(other)

class GCMapWidget(MapWidget):
	TASKID_GETLIST		= 900
	TASKID_GETINFO		= 901

	def __init__(self, gcsub, ctlWidget, statusBar, parent=None):
		MapWidget.__init__(self, parent, useLocalSquid=useWebProxy)
		self.gcsub = gcsub
		self.ctlWidget = ctlWidget
		self.statusBar = statusBar

		self.details = {}
		self.currentCenter = None
		self.foundGuids = []
		self.customPoints = []

		self.connect(self, SIGNAL("initialized"), self.__basicInitFinished)
		self.connect(self, SIGNAL("mapChanged"), self.__updateCachesList)

		self.load()

		self.gps = GpsWrapper()
		self.myGpsPos = None
		if self.gps.present():
			self.gpstimer = QTimer(self)
			self.connect(self.gpstimer, SIGNAL("timeout()"), self.__gpsTimer)
			self.gpstimer.start(3000)

	def fetchFoundCachesSync(self):
		self.statusBar.message("Fetching found caches...")
		QApplication.processEvents()
		taskContext = self.gcsub.executeSync(TaskContext("gccom.getMyFoundCaches()"))
		QApplication.processEvents()
		(found, exception) = taskContext.retval
		self.foundGuids = map(lambda (foundDate, foundGuid): foundGuid, found)
		self.statusBar.message("done.", 3000)

	def __gpsTimer(self):
		if not self.gps.present():
			return
		posMarkerID = "__MYPOS__"
		pos = self.gps.getPos()
		prevPos = self.myGpsPos
		self.myGpsPos = pos
		if pos is not None:
			if prevPos is None:
				self.statusBar.message("Acquired GPS fix", 3000)
			else:
				if pos == prevPos:
					return
		else:
			if prevPos is not None:
				self.statusBar.message("Lost GPS fix!", 10000)
		self.removeMarker(posMarkerID)
		if pos is not None:
			self.addMarker(posMarkerID, "GPS position -- %s" % str(pos),
				       GPSICON_URL, pos)

	def gotoGpsFix(self):
		if self.myGpsPos is None:
			return False
		self.setCenter(self.myGpsPos)
		return True

	def __basicInitFinished(self):
		self.setCenter(geo.Point(50, 6.5))
		self.setZoom(13)

	def __getDetails(self, guid):
		return self.details.get(guid, None)

	def __addCache(self, details):
		text = "%s - %s" % (details.info.gcID, details.info.title)
		self.addMarker(details.guid, text, CACHEICON_URL, details.info.location)

	def gotCacheInfo(self, guid, info):
		details = self.__getDetails(guid)
		if not details:
			return
		details.info = info
		self.__addCache(details)

	def gotCachesList(self, guids):
		self.ctlWidget.setCacheListFetching(False)

		if len(guids) >= CACHECOUNT_LIMIT:
			self.statusBar.message(
				"WARNING: Cache count limit of %d caches reached. "
				"Zoom in, please." %\
				CACHECOUNT_LIMIT, 20000)
		else:
			self.statusBar.message()

		details = {}
		# Add caches from the list to the details
		for guid in guids:
			if not self.ctlWidget.mustShowFound():
				# Filter my found caches
				if guid in self.foundGuids:
					continue
			details[guid] = CacheDetails(guid)
		# Add custom points to the details
		for (i, point) in enumerate(self.customPoints):
			guid = "custom-%f-%f" % (point.latitude, point.longitude)
			title = "\n%s\n%s" % (formatCoord("N", point.latitude),
					      formatCoord("E", point.longitude))
			d = CacheDetails(guid)
			d.info = gccom.GCCacheInfo(gcID="Custom_%d" % i,
						   title=title,
						   location=point)
			details[guid] = d

		# Remove outdated markers
		removeGuids = filter(lambda guid: guid not in details,
				     self.details)
		for guid in removeGuids:
			self.removeMarker(guid)
			self.details.pop(guid)

		# Add new markers, which aren't there already.
		newDetails = {}
		for guid in details:
			if guid not in self.details.keys():
				newDetails[guid] = details[guid]
		for d in newDetails.values():
			if d.guid.startswith("custom"):
				# Got all information. Add it now.
				self.__addCache(d)
				continue
			# Fetch remaining information
			self.details[d.guid] = d
			self.gcsub.execute(
				TaskContext("gccom.getCacheDetails(...)", (d.guid,),
					    userid=self.TASKID_GETINFO, userdata=d.guid))
		self.details = details

	def __updateCachesList(self, center, zoom, northEast, southWest):
		self.currentCenter = center
		self.currentZoom = zoom
		self.currentNorthEast = northEast
		self.currentSouthWest = southWest

		if self.gcsub.online():
			self.gcsub.cancelTasks( ("gccom.findCaches(...)",
						 "gccom.getCacheDetails(...)") )
			self.gcsub.execute(TaskContext("gccom.findCaches(...)",
						       (northEast, southWest, CACHECOUNT_LIMIT),
						       userid=self.TASKID_GETLIST))

			self.ctlWidget.setNrTasksPending(self.gcsub.nrTasksPending())
			self.ctlWidget.setCacheListFetching(True)
		else:
			self.gotCachesList([])

	def triggerMapUpdate(self):
		if not self.currentCenter:
			return
		self.__updateCachesList(self.currentCenter, self.currentZoom,
					self.currentNorthEast, self.currentSouthWest)

	def getCustomPoints(self):
		return self.customPoints

	def setCustomPoints(self, points):
		self.customPoints = points
		self.triggerMapUpdate()

class CoordListDialog(QDialog):
	def __init__(self, points=[], title=None, parent=None):
		QDialog.__init__(self, parent)
		if title:
			self.setWindowTitle(title)
		self.setLayout(QGridLayout(self))

		self.points = points

		self.pointList = QTextEdit(self)
		text = [ "# Example:",
			 "# N 50 12.345   E 006 12.345\n\n" ]
		for point in points:
			text.append(formatCoord("N", point.latitude) + "   " +\
				    formatCoord("E", point.longitude))
		self.pointList.setPlainText("\n".join(text))
		self.layout().addWidget(self.pointList, 0, 0, 1, 2)

		self.okButton = QPushButton("&Ok")
		self.layout().addWidget(self.okButton, 1, 0)

		self.cancelButton = QPushButton("&Cancel")
		self.layout().addWidget(self.cancelButton, 1, 1)

		self.connect(self.okButton, SIGNAL("released()"), self.__ok)
		self.connect(self.cancelButton, SIGNAL("released()"), self.__cancel)

	def getPoints(self):
		return self.points

	def __invalidCoord(self, message):
		QMessageBox.critical(self, "Invalid coordinate", message)

	def __ok(self):
		text = self.pointList.toPlainText()
		points = []
		for line in str(text).splitlines():
			line = line.strip()
			if not line or line.startswith("#"):
				continue
			found = re.findall(gccom.coordRegex, line, re.DOTALL)
			lat = None
			lon = None
			for (d, deg, minu) in found:
				d = d.upper()
				if d in "NS": # latitude
					lat = parseCoord("%s %s %s" % (d, deg, minu))
				elif d in "WEO": # longitude
					lon = parseCoord("%s %s %s" % (d, deg, minu))
				else:
					self.__invalidCoord(line + ":\nInvalid coordinates")
					return
			if lat is None:
				self.__invalidCoord(line + ":\nLatitude missing or invalid")
				return
			if lon is None:
				self.__invalidCoord(line + ":\nLongitude missing or invalid")
				return
			points.append(geo.Point(lat, lon))
		self.points = points
		self.accept()

	def __cancel(self):
		self.reject()

class CoordEntryDialog(QDialog):
	def __init__(self, point=None, title=None, parent=None):
		QDialog.__init__(self, parent)
		if title:
			self.setWindowTitle(title)
		self.setLayout(QGridLayout(self))

		self.point = point

		label = QLabel("Latitude:", self)
		self.layout().addWidget(label, 0, 0)
		self.latInput = QLineEdit(self)
		self.layout().addWidget(self.latInput, 0, 1)

		label = QLabel("Longitude:", self)
		self.layout().addWidget(label, 1, 0)
		self.lonInput = QLineEdit(self)
		self.layout().addWidget(self.lonInput, 1, 1)

		self.okButton = QPushButton("&Ok")
		self.layout().addWidget(self.okButton, 2, 0)

		self.cancelButton = QPushButton("&Cancel")
		self.layout().addWidget(self.cancelButton, 2, 1)

		if point:
			self.latInput.setText(formatCoord("N", point.latitude))
			self.lonInput.setText(formatCoord("E", point.longitude))

		self.connect(self.okButton, SIGNAL("released()"), self.__ok)
		self.connect(self.cancelButton, SIGNAL("released()"), self.__cancel)

	def __ok(self):
		lat = parseCoord(self.latInput.text())
		lon = parseCoord(self.lonInput.text())
		if lat is None or lon is None:
			QMessageBox.critical(self, "Input error",
				"Input value error: The coordinates are invalid")
			return
		self.point = geo.Point(lat, lon)
		self.accept()

	def __cancel(self):
		self.reject()

	def getCoord(self):
		return self.point

class ControlWidget(QWidget):
	def __init__(self, parent, gcsub):
		QWidget.__init__(self, parent)
		self.setLayout(QGridLayout(self))
		self.gcsub = gcsub
		self.mapWidget = None

		self.nrTasksPending = 0
		self.fetchingList = False

		self.enableGccom = QCheckBox("Enable geocaching.com", self)
		self.layout().addWidget(self.enableGccom, 0, 0)

		self.showFound = QCheckBox("Show found geocaches", self)
		self.layout().addWidget(self.showFound, 1, 0)

		self.gotoButton = QPushButton("Go to...", self)
		self.layout().addWidget(self.gotoButton, 0, 1)

		self.gotoGpsButton = QPushButton("Go to GPS", self)
		self.layout().addWidget(self.gotoGpsButton, 0, 2)

		self.customLocButton = QPushButton("Custom locations...", self)
		self.layout().addWidget(self.customLocButton, 0, 3)

		self.status = QLabel(self)
		self.layout().addWidget(self.status, 2, 0, 1, 3)

		self.__enableGccomChanged()

		self.connect(self.enableGccom, SIGNAL("stateChanged(int)"),
			     self.__enableGccomChanged)
		self.connect(self.showFound, SIGNAL("stateChanged(int)"),
			     self.__showFoundChanged)
		self.connect(self.gotoButton, SIGNAL("released()"),
			     self.__gotoPressed)
		self.connect(self.gotoGpsButton, SIGNAL("released()"),
			     self.__gotoGpsPressed)
		self.connect(self.customLocButton, SIGNAL("released()"),
			     self.__customLocPressed)

	def __updateStatus(self):
		pending = ""
		if self.nrTasksPending:
			pending = "Pending geocaching.com requests: %d" % self.nrTasksPending
		fetching = ""
		if self.fetchingList:
			fetching = "Fetching cache list..."
		self.status.setText(pending + "\n" + fetching)

	def setNrTasksPending(self, count):
		self.nrTasksPending = count
		self.__updateStatus()

	def setCacheListFetching(self, running):
		self.fetchingList = running
		self.__updateStatus()

	def mustShowFound(self):
		return self.showFound.checkState() == Qt.Checked

	def __enableGccomChanged(self):
		on = (self.enableGccom.checkState() == Qt.Checked)
		self.showFound.setEnabled(on)
		try:
			if on:
				self.gcsub.login(self)
				if self.mapWidget:
					self.mapWidget.fetchFoundCachesSync()
			else:
				self.gcsub.logout()
			if self.mapWidget:
				self.mapWidget.triggerMapUpdate()
		except (gccom.GCException), e:
			QMessageBox.critical(self, "GC.COM failed",
				str(e))
			self.enableGccom.setCheckState(Qt.Unchecked)

	def __showFoundChanged(self):
		self.mapWidget.triggerMapUpdate()

	def __gotoPressed(self):
		dlg = CoordEntryDialog(self.mapWidget.currentCenter,
				       "Go to location", self)
		if dlg.exec_() == QDialog.Accepted:
			coord = dlg.getCoord()
			self.mapWidget.setCenter(coord)

	def __gotoGpsPressed(self):
		if not self.mapWidget.gotoGpsFix():
			QMessageBox.critical(self, "No GPS fix",
				"Failed to go to GPS fix")

	def __customLocPressed(self):
		dlg = CoordListDialog(self.mapWidget.getCustomPoints(),
				      "Custom locations", self)
		if dlg.exec_() == QDialog.Accepted:
			self.mapWidget.setCustomPoints(dlg.getPoints())

class MainWidget(QWidget):
	def __init__(self, gcsub, parent=None):
		QWidget.__init__(self, parent)
		self.setLayout(QGridLayout(self))
		self.gcsub = gcsub
		self.statusBar = parent.statusBar()

		self.ctlWidget = ControlWidget(self, gcsub)
		self.mapWidget = GCMapWidget(gcsub, self.ctlWidget,
					     self.statusBar, self)
		self.ctlWidget.mapWidget = self.mapWidget

		self.layout().addWidget(self.mapWidget, 0, 0)
		self.layout().addWidget(self.ctlWidget, 1, 0)

	def gcsubEvent(self):
		if not self.gcsub.online():
			return
		while True:
			self.ctlWidget.setNrTasksPending(self.gcsub.nrTasksPending())

			taskContext = self.gcsub.fetchRetval()
			if not taskContext:
				break
			(retval, exception) = taskContext.retval
			if exception:
				print "Task failed: ", str(exception)
				self.statusBar.message("WARNING: task failed: " +\
						       taskContext.name)
				continue
			if taskContext.userid == self.mapWidget.TASKID_GETLIST:
				self.mapWidget.gotCachesList(retval)
			elif taskContext.userid == self.mapWidget.TASKID_GETINFO:
				self.mapWidget.gotCacheInfo(guid=taskContext.userdata,
							    info=retval)
			else:
				print taskContext.name
				assert(0)

class StatusBar(QStatusBar):
	def __init__(self, parent=None):
		QStatusBar.__init__(self, parent)

	def message(self, message="", timeout=-1):
		if timeout < 0:
			timeout = 5000
		self.showMessage(message, timeout)

class MainWindow(QMainWindow):
	def __init__(self, parent=None):
		QMainWindow.__init__(self, parent)
		self.setWindowTitle("Geocaching mapper")
		self.gcsub = GCSubprocess(self)

		self.setStatusBar(StatusBar(self))
		self.setCentralWidget(MainWidget(self.gcsub, self))

	def event(self, e):
		if e.type() == EVENT_TASKFINISHED:
			mainWidget = self.centralWidget()
			if mainWidget:
				mainWidget.gcsubEvent()
			e.accept()
			return True
		return QMainWindow.event(self, e)

	def closeEvent(self, e):
		self.gcsub.logout()
		self.gcsub.killThread()

def wmHintsWorkaround(wnd):
	from ctypes import cast, POINTER, cdll, c_void_p, c_int, c_uint, c_long, Structure
	import sip

	class XWMHints(Structure):
		_fields_ = [	("flags", c_long),
				("input", c_int),
				("a", c_int),
				("b", c_int),
				("c", c_int),
				("d", c_int),
				("e", c_int),
				("f", c_int),
				("g", c_int),
		]

	libX11 = cdll.LoadLibrary("libX11.so")

	XGetWMHints = libX11.XGetWMHints
	XGetWMHints.argtypes = (c_void_p, c_uint)
	XGetWMHints.restype = POINTER(XWMHints)

	XAllocWMHints = libX11.XAllocWMHints
	XAllocWMHints.restype = POINTER(XWMHints)

	XSetWMHints = libX11.XSetWMHints
	XSetWMHints.argtypes = (c_void_p, c_uint, c_void_p)

	XSetInputFocus = libX11.XSetInputFocus
	XSetInputFocus.argtypes = (c_void_p, c_uint, c_uint, c_uint)

	print QX11Info.display()
	display = c_void_p(sip.unwrapinstance(QX11Info.display()))
	window = wnd.winId()
	print "WND", window
	hints = XGetWMHints(display, window)
	if not hints:
		hints = XAllocWMHints()
	hints[0].flags |= 1
	hints[0].input = 0xFFFFFFFF
	res = XSetWMHints(display, window, hints)
	print res

	print XSetInputFocus(display, window, 2, 0)

def usage():
	print "%s [OPTIONS]" % sys.argv[0]
	print ""
	print " -h|--help           Print this help text"
	print " -n|--noproxy        Do not use proxy server"
	print " -g|--nogps          Do not use GPSd"

def main():
	global useWebProxy
	global useGPS

	try:
		(opts, args) = getopt.getopt(sys.argv[1:],
			"hng",
			[ "help", "noproxy", "nogps", ])
	except getopt.GetoptError:
		usage()
		return 1
	for (o, v) in opts:
		if o in ("-h", "--help"):
			usage()
			return 0
		if o in ("-n", "--noproxy"):
			useWebProxy = False
		if o in ("-g", "--nogps"):
			useGPS = False

	app = QApplication(sys.argv)
	mainwnd = MainWindow()
	mainwnd.show()
#	wmHintsWorkaround(mainwnd)
	return app.exec_()

if __name__ == "__main__":
	try:
		sys.exit(main())
	except (gccom.GCException), e:
		print str(e)
