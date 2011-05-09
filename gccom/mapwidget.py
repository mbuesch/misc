#!/usr/bin/env python
#
# Google-Maps QT4 widget
#
# Copyright (c) 2011 Michael Buesch <m@bues.ch>
#

import geopy as geo
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtWebKit import *


googleMapsHtmlCode = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
	"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html>
<head>
<meta name="viewport" content="initial-scale=1.0, user-scalable=no" />
<meta http-equiv="content-type" content="text/html; charset=UTF-8"/>
<style type="text/css">
	html { height: 100% }
	body { height: 100%; margin: 0px; padding: 0px }
	#map_canvas { height: 100% }
</style>
<title></title>

<script type="text/javascript"
	src="http://maps.google.com/maps/api/js?sensor=false">
</script>

<script type="text/javascript">
	function initialize() {
		var mapOptions = {
			zoom: 15,
			center: new google.maps.LatLng(0, 0),
			mapTypeId: google.maps.MapTypeId.ROADMAP,
		}
		markers = new Object();
		map = new google.maps.Map(document.getElementById("map_canvas"), mapOptions);
		google.maps.event.addListener(map, "bounds_changed", callback.boundsChanged);
		google.maps.event.addListener(map, "zoom_changed", callback.zoomChanged);
		google.maps.event.addListener(map, "idle", callback.idle);
		callback.initialized();
	}

	function getCenter() {
		return new Array(map.getCenter().lat(), map.getCenter().lng());
	}

	function setCenter(lat, lng) {
		map.panTo(new google.maps.LatLng(lat, lng));
	}

	function getNorthEast() {
		return new Array(map.getBounds().getNorthEast().lat(),
				 map.getBounds().getNorthEast().lng());
	}

	function getSouthWest() {
		return new Array(map.getBounds().getSouthWest().lat(),
				 map.getBounds().getSouthWest().lng());
	}

	function getZoom() {
		return map.getZoom();
	}

	function setZoom(zoom) {
		map.setZoom(zoom);
	}

	function removeMarkers() {
		for (i in markers) {
			markers[i].setMap(null);
		}
		delete markers;
		markers = new Object();
	}

	function removeMarker(id) {
		markers[id].setMap(null);
		delete markers[id];
	}

	function addMarker(id, title, iconUrl, lat, lng) {
		var markerOptions = {
			flat: true,
			position: new google.maps.LatLng(lat, lng),
			visible: true,
			map: map,
			optimized: false,
			icon: iconUrl,
			title: title,
		}
		var markerObj = new google.maps.Marker(markerOptions);
		markers[id] = markerObj
	}
</script>

</head>
<body onload="initialize()">
	<div id="map_canvas"></div>
</body>
</html>
"""

class MapWidgetCallback(QObject):
	def __init__(self, mapWidget):
		QObject.__init__(self)
		self.mapWidget = mapWidget

	@pyqtSignature("")
	def initialized(self):
		self.mapWidget.emit(SIGNAL("initialized"))

	@pyqtSignature("")
	def idle(self):
		self.mapWidget.emit(SIGNAL("idle"))

	@pyqtSignature("")
	def boundsChanged(self):
		self.mapWidget.mapChangeCallback()

	@pyqtSignature("")
	def zoomChanged(self):
		self.mapWidget.mapChangeCallback()

class MapWidget(QWebView):
	__pyqtSignals__ = (
		"initialized",
		"idle",
		"mapChanged",
	)

	def __init__(self, parent=None):
		QWebView.__init__(self, parent)

		self.callbackObj = MapWidgetCallback(self)
		self.connect(self, SIGNAL("javaScriptWindowObjectCleared()"),
			     self.__loadJsObjects)
		self.__loadJsObjects()

	def load(self):
		self.setHtml(googleMapsHtmlCode)

	def __loadJsObjects(self):
		frame = self.page().mainFrame()
		frame.addToJavaScriptWindowObject("callback", self.callbackObj)

	def __sanitizeString(self, string):
		allowedChars = "abcdefghijklmnopqrstuvwxyz" \
			       "ABCDEFGHIJKLMNOPQRSTUVWXYZ" \
			       "0123456789" \
			       "\\!$%()[]{}=?:.,;/-_+*#"
		def convchar(c):
			o = ord(c)
			if o <= 127:
				return c
			return "\\u00%02X" % o
		def filterchar(c):
			if c in allowedChars:
				return c
			if c.isspace():
				return " "
			return ""
		string = string.replace("\\", "\\\\")
		string = string.decode("UTF-8")
		string = "".join(map(convchar, string))
		string = "".join(map(filterchar, string))
		return string

	def mapChangeCallback(self):
		mainFrame = self.page().mainFrame()
		center = mainFrame.evaluateJavaScript("getCenter()").toPyObject()
		if center is None:
			return
		center = geo.Point(center[0], center[1])
		zoom = mainFrame.evaluateJavaScript("getZoom()").toPyObject()
		if zoom is None:
			return
		northEast = mainFrame.evaluateJavaScript("getNorthEast()").toPyObject()
		if northEast is None:
			return
		northEast = geo.Point(northEast[0], northEast[1])
		southWest = mainFrame.evaluateJavaScript("getSouthWest()").toPyObject()
		if southWest is None:
			return
		southWest = geo.Point(southWest[0], southWest[1])

		self.emit(SIGNAL("mapChanged"), center, zoom, northEast, southWest)

	def setCenter(self, point):
		js = 'setCenter(%f, %f);' % (point.latitude, point.longitude)
		self.page().mainFrame().evaluateJavaScript(js)

	def setZoom(self, zoom):
		js = 'setZoom(%d);' % zoom
		self.page().mainFrame().evaluateJavaScript(js)

	def removeMarkers(self):
		js = 'removeMarkers();'
		self.page().mainFrame().evaluateJavaScript(js)

	def removeMarker(self, markerID):
		js = 'removeMarker("%s");' % str(markerID)
		self.page().mainFrame().evaluateJavaScript(js)

	def addMarker(self, markerID, text, iconurl, point):
		js = 'addMarker("%s", "%s", "%s", %f, %f);' %\
			(str(markerID),
			 self.__sanitizeString(text),
			 self.__sanitizeString(iconurl),
			 point.latitude, point.longitude)
		self.page().mainFrame().evaluateJavaScript(js)
