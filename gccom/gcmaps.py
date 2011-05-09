#!/usr/bin/env python
"""
# Tiny Geocaching mapping tool
# (c) Copyright 2011 Michael Buesch
# Licensed under the GNU/GPL version 2 or later.
"""

import sys
import os
import time
import multiprocessing

from mapwidget import *
from geopy.distance import VincentyDistance as Distance

import gccom

#try:
#	import gps
#except (ImportError), e:
#	print "Please install the Python GPS library module."
#	print "On Debian Linux run: aptitude install python-gps"
#	sys.exit(1)

DEBUG			= 1

EVENT_TASKFINISHED	= QEvent.User + 0

CACHEICON_URL		= "http://www.geocaching.com/images/wpttypes/sm/2.gif"


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
		self.isRunning = True

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
		self.taskCounter += 1
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
		self.position = None
		self.cacheID = None
		self.title = None

	def __eq__(self, other):
		return self.guid == other.guid

	def __ne__(self, other):
		return not self.__eq__(other)

class GCMapWidget(MapWidget):
	TASKID_GETLIST		= 900
	TASKID_GETLOC		= 901
	TASKID_GETID		= 902
	TASKID_GETTITLE		= 903

	def __init__(self, gcsub, ctlWidget, parent=None):
		MapWidget.__init__(self, parent)
		self.gcsub = gcsub
		self.ctlWidget = ctlWidget

		self.details = {}
		self.currentCenter = None

		print "Fetching found caches..."
		taskContext = gcsub.executeSync(TaskContext("gccom.getMyFoundCaches()"))
		(found, exception) = taskContext.retval
		self.foundGuids = map(lambda (foundDate, foundGuid): foundGuid, found)
		print "done."

		self.connect(self, SIGNAL("initialized"), self.__basicInitFinished)
		self.connect(self, SIGNAL("mapChanged"), self.__updateCachesList)

		self.load()

	def __basicInitFinished(self):
		self.setCenter(geo.Point(50, 6.5))#FIXME
		self.setZoom(13)

	def __getDetails(self, guid):
		return self.details.get(guid, None)

	def __mayShowCache(self, guid):
		details = self.__getDetails(guid)
		if not details:
			return
		if not details.position or\
		   not details.cacheID or\
		   not details.title:
			return
		text = "%s - %s" % (details.cacheID, details.title)
		self.addMarker(guid, text, CACHEICON_URL, details.position)

	def gotCacheTitle(self, guid, title):
		details = self.__getDetails(guid)
		if not details:
			return
		details.title = title
		self.__mayShowCache(guid)

	def gotCacheID(self, guid, cacheID):
		details = self.__getDetails(guid)
		if not details:
			return
		details.cacheID = cacheID
		self.__mayShowCache(guid)

	def gotCacheLocation(self, guid, latlng):
		details = self.__getDetails(guid)
		if not details:
			return
		details.position = geo.Point(latlng[0], latlng[1])
		self.gcsub.execute(TaskContext("gccom.getCacheId(...)", (guid,),
				   userid=self.TASKID_GETID, userdata=guid))
		self.gcsub.execute(TaskContext("gccom.getCacheTitle(...)", (guid,),
				   userid=self.TASKID_GETTITLE, userdata=guid))

	def gotCachesList(self, guids):
		self.ctlWidget.setCacheListFetching(False)

		details = {}
		for guid in guids:
			if not self.ctlWidget.mustShowFound():
				# Filter my found caches
				if guid in self.foundGuids:
					continue
			details[guid] = CacheDetails(guid)

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
			self.details[d.guid] = d
			self.gcsub.execute(
				TaskContext("gccom.getCacheLocation(...)",
					    (d.guid,),
					    userid=self.TASKID_GETLOC,
					    userdata=d.guid))
		self.details = details

	def __updateCachesList(self, center, zoom, northEast, southWest):
		self.currentCenter = center
		self.currentZoom = zoom
		self.currentNorthEast = northEast
		self.currentSouthWest = southWest

		self.gcsub.cancelTasks( ("gccom.findCaches(...)",
					 "gccom.getCacheLocation(...)") )
		self.gcsub.execute(TaskContext("gccom.findCaches(...)",
					       (northEast, southWest),
					       userid=self.TASKID_GETLIST))

		self.ctlWidget.setNrTasksPending(self.gcsub.nrTasksPending())
		self.ctlWidget.setCacheListFetching(True)

	def triggerMapUpdate(self):
		if not self.currentCenter:
			return
		self.__updateCachesList(self.currentCenter, self.currentZoom,
					self.currentNorthEast, self.currentSouthWest)

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
			lat = "N %d* %.3f" %\
				(int(point.latitude),
				 (point.latitude - int(point.latitude)) * 60)
			lon = "E %d* %.3f" %\
				(int(point.longitude),
				 (point.longitude - int(point.longitude)) * 60)
			self.latInput.setText(lat)
			self.lonInput.setText(lon)

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
	def __init__(self, parent=None):
		QWidget.__init__(self, parent)
		self.setLayout(QGridLayout(self))
		self.mapWidget = None

		self.nrTasksPending = 0
		self.fetchingList = False

		self.showFound = QCheckBox("Show found geocaches", self)
		self.layout().addWidget(self.showFound, 0, 0)

		self.gotoButton = QPushButton("Go to...", self)
		self.layout().addWidget(self.gotoButton, 0, 1)

		self.status = QLabel(self)
		self.layout().addWidget(self.status, 1, 0)

		self.connect(self.showFound, SIGNAL("stateChanged(int)"),
			     self.__showFoundChanged)
		self.connect(self.gotoButton, SIGNAL("released()"),
			     self.__gotoPressed)

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

	def __showFoundChanged(self):
		self.mapWidget.triggerMapUpdate()

	def __gotoPressed(self):
		dlg = CoordEntryDialog(self.mapWidget.currentCenter,
				       "Go to location", self)
		if dlg.exec_() == QDialog.Accepted:
			coord = dlg.getCoord()
			self.mapWidget.setCenter(coord)

class MainWidget(QWidget):
	def __init__(self, gcsub, parent=None):
		QWidget.__init__(self, parent)
		self.setLayout(QGridLayout(self))
		self.gcsub = gcsub

		self.ctlWidget = ControlWidget(self)
		self.mapWidget = GCMapWidget(gcsub, self.ctlWidget, self)
		self.ctlWidget.mapWidget = self.mapWidget

		self.layout().addWidget(self.mapWidget, 0, 0)
		self.layout().addWidget(self.ctlWidget, 1, 0)

	def gcsubEvent(self):
		while True:
			self.ctlWidget.setNrTasksPending(self.gcsub.nrTasksPending())

			taskContext = self.gcsub.fetchRetval()
			if not taskContext:
				break
			(retval, exception) = taskContext.retval
			if exception:
				QMessageBox.critical(self, "Task failed",
						     "task: " + taskContext.name + "\n" + str(exception))
				continue
			if taskContext.userid == self.mapWidget.TASKID_GETLIST:
				self.mapWidget.gotCachesList(retval)
			elif taskContext.userid == self.mapWidget.TASKID_GETLOC:
				self.mapWidget.gotCacheLocation(guid=taskContext.userdata,
								latlng=retval)
			elif taskContext.userid == self.mapWidget.TASKID_GETID:
				self.mapWidget.gotCacheID(guid=taskContext.userdata,
							  cacheID=retval)
			elif taskContext.userid == self.mapWidget.TASKID_GETTITLE:
				self.mapWidget.gotCacheTitle(guid=taskContext.userdata,
							     title=retval)
			else:
				print taskContext.name
				assert(0)

class MainWindow(QMainWindow):
	def __init__(self, parent=None):
		QMainWindow.__init__(self, parent)
		self.setWindowTitle("Geocaching mapper")
		self.gcsub = GCSubprocess(self)
		self.__login()

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
		self.gcsub.executeSync(TaskContext("gccom.logout()"))
		self.gcsub.killThread()

	def __login(self):
		try:
			acc = file("account", "rb").read().split()
			user = acc[0]
			passwd = acc[1]
		except (IOError, IndexError), e:
			(user, ok) = QInputDialog.getText(self, "Geocaching.com username",
							  "Geocaching.com username",
							  mode=QLineEdit.Normal)
			if not user or not ok:
				return#XXX
			(passwd, ok) = QInputDialog.getText(self, "Geocaching.com password",
							    "Geocaching.com password for account %s" % user,
							    mode=QLineEdit.Password)
			if not passwd or not ok:
				return#XXX
		taskContext = self.gcsub.executeSync(
				TaskContext("login(...)", (str(user), str(passwd))))
		(retval, exception) = taskContext.retval
		if exception:
			QMessageBox.critical(self, "Geocaching.com login failed",
					     "Geocaching.com login failed:\n" + str(exception))
			raise exception

def main():
	app = QApplication(sys.argv)
	mainwnd = MainWindow()
	mainwnd.show()
	return app.exec_()

if __name__ == "__main__":
	try:
		sys.exit(main())
	except (gccom.GCException), e:
		print str(e)
