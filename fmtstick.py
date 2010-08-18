#!/usr/bin/env python

import sys
import os
import re
import subprocess
from PyQt4.QtCore import *
from PyQt4.QtGui import *

SYSFS = "/sys"
DEVFS = "/dev"

DEVS_RE = (
	re.compile(r'^sd[a-z]$'),
)

FORMAT_CMDS = (
	"umount \"%s\"; true",
	"dd if=/dev/zero \"of=%s\" bs=1024 count=512",
	"mkfs.vfat \"%s\"",
)


def sysfsRead(*path):
	realpath = SYSFS + "/" + "/".join(path)
	try:
		return file(realpath, "r").read().strip()
	except IOError:
		return ""

class MainWidget(QWidget):
	def __init__(self, mainwnd):
		QWidget.__init__(self, mainwnd)
		self.mainwnd = mainwnd
		self.setLayout(QGridLayout(self))

		self.devNames = []
		self.selDevs = []

		self.devList = QListWidget(self)
		self.layout().addWidget(self.devList, 0, 0)

		self.formatButton = QPushButton("Format", self)
		self.formatButton.setEnabled(False)
		self.layout().addWidget(self.formatButton, 1, 0)

		self.scanTimerTrigger()
		self.scanTimer = QTimer(self)
		self.connect(self.scanTimer, SIGNAL("timeout()"),
			     self.scanTimerTrigger)
		self.scanTimer.start(500)

		self.connect(self.devList, SIGNAL("itemSelectionChanged()"),
			     self.devChanged)
		self.connect(self.formatButton, SIGNAL("pressed()"),
			     self.doFormat)

	def scanTimerTrigger(self):
		def sysfsBlockFilter(filename):
			if filename in (".", ".."):
				return False
			for regex in DEVS_RE:
				if regex.match(filename):
					break
			else:
				return False
			removable = sysfsRead("block", filename, "removable")
			if removable != "1":
				return False
			return True
		entries = os.listdir(SYSFS + "/block")
		entries = filter(sysfsBlockFilter, entries)
		if entries == self.devNames:
			return
		self.devList.clear()
		self.devNames = entries
		for entry in entries:
			name = ""
			media = sysfsRead("block", entry, "device/media")
			if media:
				name += media + " - "
			model = sysfsRead("block", entry, "device/model")
			if model:
				name += model + " - "
			name += entry
			item = QListWidgetItem(name)
			item.setData(Qt.UserRole, QVariant(entry))
			self.devList.addItem(item)

	def devChanged(self):
		sel = self.devList.selectedItems()
		self.selDevs = sel
		self.formatButton.setEnabled(bool(sel))

	def doFormat(self):
		if not self.selDevs:
			return
		self.formatButton.setEnabled(False)
		self.devList.setEnabled(False)
		for dev in self.selDevs:
			dev = str(dev.data(Qt.UserRole).toString())
			devnode = DEVFS + "/" + dev
			self.formatDevice(devnode)
		self.formatButton.setEnabled(True)
		self.devList.setEnabled(True)

	def formatDevice(self, devnode):
		# Only the first partition
		self.formatPartition(devnode + "1")

	def formatPartition(self, devnode):
		print "Formating %s ..." % devnode
		try:
			s = os.stat(devnode)
			if (s.st_mode & 060000) == 0:
				QMessageBox.critical(self, "Not a block device",
						     "%s is not a block device" % devnode)
				return
		except OSError:
			QMessageBox.critical(self, "Failed to stat",
					     "Failed to stat %s" % devnode)
			return
		for command in FORMAT_CMDS:
			cmd = command % devnode
			try:
				print "running command:", cmd
				self.mainwnd.statusBar().showMessage(cmd)
				QApplication.processEvents()
				process = subprocess.Popen(cmd, shell=True)
				if process.wait():
					raise OSError
			except OSError:
				QMessageBox.critical(self, "Formating failed",
						     "\"%s\" failed" % cmd)
				return
		self.mainwnd.statusBar().showMessage("")
		self.mainwnd.close()

class MainWindow(QMainWindow):
	def __init__(self, parent=None):
		QMainWindow.__init__(self, parent)
		self.setWindowTitle("Stickformat")
		self.setStatusBar(QStatusBar())
		self.setCentralWidget(MainWidget(self))

def main():
	app = QApplication(sys.argv)
	mainwnd = MainWindow()
	mainwnd.show()
	return app.exec_()

if __name__ == "__main__":
	sys.exit(main())
