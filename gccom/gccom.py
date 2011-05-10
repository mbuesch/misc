#!/usr/bin/env python
# vim: set fileencoding=UTF-8 :
"""
# Geocaching.com tool
# (c) Copyright 2010-2011 Michael Buesch
# Licensed under the GNU/GPL version 2 or later.
"""

import sys
import os
import getopt
import httplib
import htmllib
import cgi
import socket
import urllib
#import ssl
import re
import time
import sqlite3 as sql
import datetime

import geopy as geo
from geopy.distance import VincentyDistance as Distance


hostname = "www.geocaching.com"

guidRegex = r'\w{8,8}-\w{4,4}-\w{4,4}-\w{4,4}-\w{12,12}'
gcidRegex = r'GC\w\w\w\w\w?'
urlRegex = r'[\w\.\-:&%=\?/]+'
dateRegex = r'(?:\d\d/\d\d/\d\d\d\d)|' \
	    r'(?:\w+\s*\,\s*\w+\s*\d+\s*\,\s*\d+)'
coordRegex = r'([NSEOWnseow])\s+(\d+)\s*[^\w\d\s]*\s+([\d\.]+)\s*[^\w\d\s]*'
coordRegexRaw = coordRegex.replace('(', '').replace(')', '')


defaultHttpHeader = {
	"User-Agent" : "User-Agent: Mozilla/5.0 (Windows; U; " +\
		       "Windows NT 5.1; en-us; rv:1.9.0.10) Gecko/20051213 Firefox/1.5",
	"Accept" : "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
	"Accept-Language" : "en-us,en;q=0.5",
	"Accept-Charset" : "ISO-8859-1,utf-8;q=0.7,*;q=0.7",
	"Keep-Alive" : "300",
	"Connection" : "keep-alive",
}

def htmlEscape(string):
	return cgi.escape(string)

def htmlUnescape(string):
	p = htmllib.HTMLParser(None)
	p.save_bgn()
	p.feed(string)
	return p.save_end()

def gcStringToDate(string):
	# Convert a xx/xx/xxxx date to a datetime.date object.
	# May raise ValueError
	try:
		elements = string.split("/")
		return datetime.date(year=int(elements[2]),
				     month=int(elements[0]),
				     day=int(elements[1]))
	except (ValueError, IndexError):
		pass
	try:
		elements = string.replace(",", " ").split()
		weekday = elements[0].lower()
		monthname = elements[1].lower()
		month = {
			"january" : 1,
			"february" : 2,
			"march" : 3,
			"april" : 4,
			"may" : 5,
			"june" : 6,
			"july" : 7,
			"august" : 8,
			"september" : 9,
			"october" : 10,
			"november" : 11,
			"december" : 12,
		}[monthname]
		day = int(elements[2])
		year = int(elements[3])
		return datetime.date(year=year,
				     month=month,
				     day=day)
	except (ValueError, IndexError, KeyError):
		pass
	raise ValueError

class VerifiedHTTPSConnection(httplib.HTTPSConnection):
	def connect(self):
		sock = socket.create_connection((self.host, self.port),
						self.timeout)
		if self._tunnel_host:
			self.sock = sock
			self._tunnel()
		self.sock = ssl.wrap_socket(sock,
					    self.key_file,
					    self.cert_file,
					    cert_reqs=ssl.CERT_REQUIRED,
					    ca_certs="trusted_root_certs")

class GCException(Exception): pass

class GCPageStorage:
	def __init__(self, debug=0, enabled=True,
		     basePath=os.path.expanduser("~/.gccom")):
		self.debug = debug
		self.enabled = enabled
		self.databasePath = basePath + "/pagestorage.db"

		if not enabled:
			return

		try:
			os.mkdir(basePath)
		except (OSError), e:
			pass
		try:
			self.database = sql.connect(self.databasePath)
			self.database.text_factory = str
			c = self.database.cursor()
			c.execute("CREATE TABLE IF NOT EXISTS pages(path text, data text, time integer);")
		except (sql.Error), e:
			raise GCException("SQL database error: " + str(e))

	def __printDebug(self, string):
		if self.debug >= 2:
			print "PageStorage:", string

	def __isBlacklisted(self, path):
		if path.startswith("/login"):
			return True
		return False

	def __makeIndex(self, index):
		if index:
			return "___:INDEX:_" + str(index)
		return ""

	def store(self, path, data, index=None):
		if not self.enabled:
			return
		if self.__isBlacklisted(path):
			return
		path += self.__makeIndex(index)
		try:
			c = self.database.cursor()
			c.execute("INSERT INTO pages(path, data, time) "
				  "VALUES(?, ?, strftime('%s', 'now'));", (path, data))
		except (sql.Error), e:
			raise GCException("SQL database error: " + str(e))
		self.__printDebug("store " + path)

	def get(self, path, index=None):
		if not self.enabled:
			return None
		if self.__isBlacklisted(path):
			return None
		path += self.__makeIndex(index)
		try:
			c = self.database.cursor()
			c.execute("SELECT data FROM pages WHERE path=?", (path,))
			data = c.fetchone()
			if data:
				data = data[0]
				self.__printDebug("get " + path)
		except (sql.Error), e:
			raise GCException("SQL database error: " + str(e))
		return data

	def closeDatabase(self):
		if not self.enabled:
			return
		if 0: #TODO
			self.cleanDatabase()
		self.database.commit()
		self.database.close()
		self.__printDebug("Database closed")

	def cleanDatabase(self, ageMinutes=60*24):
		if not self.enabled:
			return
		try:
			ageMinutes = -abs(ageMinutes)
			self.__printDebug("Database cleanup (age %d minutes)..." % ageMinutes)
			c = self.database.cursor()
			c.execute("DELETE FROM pages WHERE time < "
				  "strftime('%s', 'now', '" + str(ageMinutes) + " minutes');")
		except (sql.Error), e:
			raise GCException("SQL database error: " + str(e))

class GCCacheInfo:
	TYPE_UNKNOWN		= -1
	TYPE_TRADITIONAL	= 0
	TYPE_MULTI		= 1
	TYPE_MYSTERY		= 2
	TYPE_EARTH		= 3
	TYPE_VIRTUAL		= 4
	TYPE_EVENT		= 5
	TYPE_LETTERBOXHYBRID	= 6
	TYPE_WHERIGO		= 7

	CONTAINER_UNKNOWN	= -1
	CONTAINER_NOTCHOSEN	= 0
	CONTAINER_MICRO		= 1
	CONTAINER_SMALL		= 2
	CONTAINER_REGULAR	= 3
	CONTAINER_LARGE		= 4
	CONTAINER_VIRTUAL	= 5
	CONTAINER_OTHER		= 6

	def __init__(self, gcID="", title="", cacheType=TYPE_UNKNOWN,
		     owner="", ownerURL="", container=CONTAINER_UNKNOWN,
		     difficulty=0.0, terrain=0.0,
		     country="", hiddenDate=None,
		     location=None):
		self.gcID = gcID
		self.title = title
		self.cacheType = cacheType
		self.owner = owner
		self.ownerURL = ownerURL
		self.container = container
		self.difficulty = difficulty
		self.terrain = terrain
		self.country = country
		self.hiddenDate = hiddenDate
		self.location = location

class GC:
	HTTPS_LOGIN	= 0
	HTTPS_FULL	= 1

	def __init__(self, user, password, predefinedCookie=None,
		     httpsMode=HTTPS_LOGIN, debug=0, storage=False):
		self.httpsMode = httpsMode
		self.debug = debug
		self.pageStorage = GCPageStorage(debug=debug, enabled=storage)
		if predefinedCookie:
			self.cookie = predefinedCookie
		else:
			self.cookie = self.__requestCookie()
			self.__login(user, password)

	def __printDebug(self, string):
		if self.debug:
			print string

	def __httpConnect(self, inLogin=False):
		if self.httpsMode == self.HTTPS_FULL or inLogin:
			return httplib.HTTPSConnection(hostname)
		return httplib.HTTPConnection(hostname)

	def __requestCookie(self):
		self.__printDebug("Requesting fresh cookie")
		http = self.__httpConnect(inLogin=True)
		http.request("GET", "/login/default.aspx")
		resp = http.getresponse()
		cookie = resp.getheader("set-cookie")
		if not cookie:
			raise GCException("Did not get a cookie")
		return cookie

	def getCookie(self):
		return self.cookie

	def __login(self, user, password):
		"Login the cookie"
		self.__printDebug("Logging into geocaching.com...")
		http = self.__httpConnect(inLogin=True)
		body = self.__getHiddenFormsUrlencoded("/login/default.aspx", inLogin=True) + "&" +\
			"ctl00%24SiteContent%24tbUsername=" + urllib.quote_plus(user) + "&" +\
			"ctl00%24SiteContent%24tbPassword=" + urllib.quote_plus(password) + "&" +\
			"ctl00%24SiteContent%24cbRememberMe=Checked&" +\
			"ctl00%24SiteContent%24btnSignIn=Login"
		header = defaultHttpHeader.copy()
		header["Host"] = hostname
		header["Cookie"] = self.cookie
		header["Content-Type"] = "application/x-www-form-urlencoded"
		header["Content-Length"] = str(len(body))
		http.request("POST", "/login/default.aspx?RESETCOMPLETE=Y",
			     body, header)
		resp = http.getresponse()
		if resp.read().find("combination does not match") >= 0:
			raise GCException("Invalid username and/or password")
		time.sleep(1) # Server doesn't like other requests right after login.
		self.__printDebug("Login success")

	def logout(self):
		"Logout the cookie"
		self.__printDebug("Logout from geocaching.com...")
		http = self.__httpConnect(inLogin=True)
		header = defaultHttpHeader.copy()
		header["Host"] = hostname
		header["Cookie"] = self.cookie
		http.request("GET", "/login/default.aspx?RESET=Y"
			"&amp;redir=http%3a%2f%2fwww.geocaching.com%2fseek%2fdefault.aspx%3f",
			     None, header)
		http.getresponse().read()
		http.request("GET", "/login/default.aspx?RESETCOMPLETE=Y"
			"&amp;amp;redir=http%3a%2f%2fwww.geocaching.com%2fseek%2fdefault.aspx%3f",
			     None, header)
		http.getresponse().read()
		self.__printDebug("Logout success")
		self.pageStorage.closeDatabase()

	@staticmethod
	def __removeChars(string, template):
		for t in template:
			string = string.replace(t, "")
		return string

	def __pageSanitize(self, page):
		"Sanitize a page path string"
		pageOrig = page
		page = page.strip()
		m = re.compile(r'^' + guidRegex + r'$').match(page)
		if m:
			# This is a GUID. Extend it to a valid page path.
			page = "/seek/cache_details.aspx?guid=" + page
		m = re.compile(r'^' + gcidRegex + r'$').match(page)
		if m:
			# This is a GC.... ID. Extend it to a valid page path.
			page = "/seek/cache_details.aspx?wp=" + page
		if page.startswith("http://"):
			page = page[7:].strip()
		if page.startswith("www."):
			page = page[4:].strip()
		if page.startswith("geocaching"):
			page = page[10:].strip()
		if page.startswith(".com"):
			page = page[4:].strip()
		page = page.strip()
		if not page.startswith("/"):
			raise GCException("Invalid page/guid identifier: %s" % pageOrig)
		return page

	def __getHiddenForms(self, page, inLogin=False):
		"Get all hidden forms on a page. Returns a list of tuples of (id, value)"
		p = self.getPage(page, inLogin=inLogin)
		return re.findall(r'<input\s+type="hidden"\s+name="\w*"\s+id="(\w+)"\s+value="([/%=\w\+]*)"\s*/>',
				  p, re.DOTALL)

	def __getHiddenFormsUrlencoded(self, page, omitForms=[], inLogin=False):
		"Get all hidden forms on a page. Returns an URL-encoded string"
		forms = []
		for (formId, formValue) in self.__getHiddenForms(page, inLogin=inLogin):
			if formId in omitForms:
				continue
			form = formId + "="
			if formValue:
				form += urllib.quote_plus(formValue)
			forms.append(form)
		return "&".join(forms)

	def getPage(self, page, inLogin=False):
		"Download a page. Returns the html code of the page."
		page = self.__pageSanitize(page)
		data = self.pageStorage.get(page)
		if data:
			return data
		http = self.__httpConnect(inLogin)
		header = defaultHttpHeader.copy()
		header["Host"] = hostname
		header["Cookie"] = self.cookie
		http.request("GET", page, None, header)
		resp = http.getresponse()
		data = resp.read()
		self.pageStorage.store(page, data)
		return data

	def getLOC(self, page):
		"Download the LOC file from a page"
		http = self.__httpConnect()
		body = self.__getHiddenFormsUrlencoded(page) + "&" +\
			"&ctl00%24ContentBody%24btnLocDL=LOC+Waypoint+File"
		header = defaultHttpHeader.copy()
		header["Host"] = hostname
		header["Cookie"] = self.cookie
		header["Content-Type"] = "application/x-www-form-urlencoded"
		header["Content-Length"] = str(len(body))
		http.request("POST", self.__pageSanitize(page), body, header)
		resp = http.getresponse().read()
		if resp.find("<waypoint>") < 0:
			raise GCException("Failed to download LOC file from " + page + resp)
		return resp

	def getGPX(self, page):
		"Download the GPX file from a page. (Needs account support)"
		http = self.__httpConnect()
		body = self.__getHiddenFormsUrlencoded(page) + "&" +\
			"&ctl00%24ContentBody%24btnGPXDL=GPX+eXchange+File"
		header = defaultHttpHeader.copy()
		header["Host"] = hostname
		header["Cookie"] = self.cookie
		header["Content-Type"] = "application/x-www-form-urlencoded"
		header["Content-Length"] = str(len(body))
		http.request("POST", self.__pageSanitize(page), body, header)
		resp = http.getresponse().read()
		if resp.find("<gpx") < 0:
			raise GCException("Failed to download GPX file from " + page)
		return resp

	def getCacheDetails(self, page):
		"Get cache detail information. Returns a GCCacheInfo instance."
		p = self.getPage(page)
		m = re.match(r'.*\((' + gcidRegex + r')\) was created by (.+) '
			     r'on \d\d/\d\d/\d\d\d\d\. '
			     r'It&#39;s a ([\w\s]+) size geocache, '
			     r'with difficulty of ([\d\.]+), '
			     r'terrain of ([\d\.]+)\. '
			     r'It&#39;s located in ([\w\s\-,&#;]+)\..*',
			     p, re.DOTALL)
		if not m:
			raise GCException("Cache detail information regex failed on " + page)
		try:
			containerMap = {
				"not chosen"	: GCCacheInfo.CONTAINER_NOTCHOSEN,
				"micro"		: GCCacheInfo.CONTAINER_MICRO,
				"small"		: GCCacheInfo.CONTAINER_SMALL,
				"regular"	: GCCacheInfo.CONTAINER_REGULAR,
				"large"		: GCCacheInfo.CONTAINER_LARGE,
				"virtual"	: GCCacheInfo.CONTAINER_VIRTUAL,
				"other"		: GCCacheInfo.CONTAINER_OTHER,
			}
			gcID = m.group(1)
			owner = htmlUnescape(m.group(2))
			container = containerMap[m.group(3).lower()]
			difficulty = float(m.group(4))
			terrain = float(m.group(5))
			country = htmlUnescape(m.group(6))
		except (ValueError, KeyError):
			raise GCException("Failed to parse cache detail information of " + page)
		startstr = '<meta name="og:title" content="'
		begin = p.find(startstr)
		if begin < 0:
			raise GCException("Failed to get cache title from " + page)
		begin += len(startstr)
		end = p.find('"', begin)
		if end < 0:
			raise GCException("Failed to get cache title from " + page)
		title = htmlUnescape(p[begin:end])
		m = re.match(r'.*<span class="minorCacheDetails">\s+'
			     r'Hidden\s*:\s*(' + dateRegex + r')\s*</span>.*',
			     p, re.DOTALL)
		if m:
			try:
				hiddenDate = gcStringToDate(m.group(1))
			except (ValueError):
				raise GCException("Failed to parse Hidden date of " + page)
		else:
			hiddenDate = None
		m = re.match(r'.*title="About Cache Types"><img src="' + urlRegex +\
			     r'" alt="([\w\s\-]+)".*',
			     p, re.DOTALL)
		if not m:
			raise GCException("Cachetype regex failed on " + page)
		try:
			typeMap = {
				"traditional cache"	: GCCacheInfo.TYPE_TRADITIONAL,
				"multi-cache"		: GCCacheInfo.TYPE_MULTI,
				"unknown cache"		: GCCacheInfo.TYPE_MYSTERY,
				"earthcache"		: GCCacheInfo.TYPE_EARTH,
				"virtual cache"		: GCCacheInfo.TYPE_VIRTUAL,
				"event cache"		: GCCacheInfo.TYPE_EVENT,
				"letterbox hybrid"	: GCCacheInfo.TYPE_LETTERBOXHYBRID,
				"wherigo cache"		: GCCacheInfo.TYPE_WHERIGO,
			}
			cacheType = typeMap[m.group(1).lower()]
		except (KeyError):
			raise GCException("Unknown cache type: " + m.group(1))
		m = re.match(r'.*<span class="minorCacheDetails">\s+'
			     r'[\w\s]+\s+by\s+<a href="(' +\
			     urlRegex + r')">.*',
			     p, re.DOTALL)
		if not m:
			raise GCException("Cacheowner-URL regex failed on " + page)
		ownerURL = m.group(1)
		m = re.match(r'.*<span id="ctl00_ContentBody_LatLon" style="font-weight:bold;">'
			     r'\s*' + coordRegex + r'\s*'
			     r'\s*' + coordRegex + r'\s*'
			     r'</span>.*',
			     p, re.DOTALL)
		if not m:
			raise GCException("Cache location regex failed on " + page)
		try:
			latDeg = float(m.group(2))
			latMin = float(m.group(3))
			lonDeg = float(m.group(5))
			lonMin = float(m.group(6))
			location = geo.Point(latDeg + latMin / 60,
					     lonDeg + lonMin / 60)
		except (ValueError):
			raise GCException("Cache location information parse failure for " + page)

		return GCCacheInfo(gcID=gcID, title=title, cacheType=cacheType,
				   owner=owner, ownerURL=ownerURL, container=container,
				   difficulty=difficulty, terrain=terrain,
				   country=country, hiddenDate=hiddenDate,
				   location=location)

	def getGuid(self, page):
		"Get the GUID for a page"
		p = self.getPage(page)
		m = re.compile(r'.*wid=(' + guidRegex + r').*', re.DOTALL).match(p)
		if not m:
			raise GCException("Failed to get cache GUID from " + page)
		guid = m.group(1).strip()
		return guid

	def setProfile(self, profileData):
		"Upload new public profile data to the account"
		page = "/account/editprofiledetails.aspx"
		http = self.__httpConnect()
		body = self.__getHiddenFormsUrlencoded(page) + "&" +\
			"ctl00%24ContentBody%24uxProfileDetails=" + urllib.quote_plus(profileData) + "&" +\
			"ctl00%24ContentBody%24uxSave=Save+Changes"
		header = defaultHttpHeader.copy()
		header["Host"] = hostname
		header["Cookie"] = self.cookie
		header["Content-Type"] = "application/x-www-form-urlencoded"
		header["Content-Length"] = str(len(body))
		http.request("POST", self.__pageSanitize(page), body, header)
		resp = http.getresponse().read()
		if resp.find('Object moved to <a href="/account/default.aspx"') < 0:
			raise GCException("Failed to upload profile data to the account")

	def getMyFoundCaches(self):
		p = self.getPage("/my/logs.aspx?s=1&lt=2")
		matches = re.findall(r'<td>\s*(\d\d/\d\d/\d\d\d\d)\s*</td>\s*'
			     r'<td>\s*'
			     r'(?:<span class="Strike OldWarning">)?'
			     r'<a href="http://www.geocaching.com/seek/cache_details.aspx'
			     r'\?guid=(' + guidRegex + r')"'
			     r'\s*class="ImageLink">',
			     p, re.DOTALL)
		return matches # (foundDate, foundGuid)

	def findCaches(self, NEpoint, SWpoint,
			     maxNrCaches=200):
		"Get a list of caches in a bounding frame"
		radius = round(Distance(NEpoint, SWpoint).miles / 2, 1)
		centerLat = NEpoint.latitude + (SWpoint.latitude - NEpoint.latitude) / 2
		centerLat = round(centerLat, 2)
		centerLatDegree = int(centerLat)
		centerLatMinutes = (centerLat - int(centerLat)) * 60
		centerLon = NEpoint.longitude + (SWpoint.longitude - NEpoint.longitude) / 2
		centerLon = round(centerLon, 2)
		centerLonDegree = int(centerLon)
		centerLonMinutes = (centerLon - int(centerLon)) * 60

		cachesList = []
		page = '/seek/nearest.aspx?' +\
			'lat_ns=1&' +\
			'lat_h=%d&' % centerLatDegree +\
			'lat_mmss=%.2f&' % centerLatMinutes +\
			'long_ew=1&' +\
			'long_h=%d&' % centerLonDegree +\
			'long_mmss=%.2f&' % centerLonMinutes +\
			'dist=%.1f&' % radius +\
			'submit8=Search'
		hiddenForms = self.__getHiddenFormsUrlencoded(page,
				omitForms=("__EVENTTARGET", "__EVENTARGUMENT"))
		http = self.__httpConnect()
		count = 0
		pageNr = 1
		while count < maxNrCaches:
			data = self.pageStorage.get(page, pageNr)
			if not data:
				# Nope, not in the storage. Fetch it.
				if pageNr == 1:
					body = ""
				else:
					body = "__EVENTTARGET=ctl00%24ContentBody%24pgrTop%24lbGoToPage_" +\
						str(pageNr) + "&" +\
						"__EVENTARGUMENT=" + "&" +\
						hiddenForms
				header = defaultHttpHeader.copy()
				header["Host"] = hostname
				header["Cookie"] = self.cookie
				header["Content-Type"] = "application/x-www-form-urlencoded"
				header["Content-Length"] = str(len(body))
				http.request("POST", self.__pageSanitize(page), body, header)
				data = http.getresponse().read()
				self.pageStorage.store(page, data, pageNr)
			regex = r'<a\s+href="/seek/cache_details\.aspx\?guid=(' + guidRegex +\
				r')"\s+class="lnk"><img\s+src='
			foundGuids = re.findall(regex, data, re.DOTALL)
			if not foundGuids:
				break
			count += len(foundGuids)
			cachesList.extend(foundGuids)
			pageNr += 1
		return cachesList[:maxNrCaches]

def printOutput(fileName, string):
	if not fileName:
		print string
		return
	try:
		file(fileName, "wb").write(string)
	except IOError, e:
		print "Failed to write file"
		print e

def fetchInput(fileName):
	try:
		if fileName:
			fd = file(fileName, "rb")
		else:
			fd = sys.stdin
		return fd.read()
	except IOError, e:
		print "Failed to read input"
		print e

def usage():
	print "Geocaching.com tool"
	print ""
	print "Usage: %s [OPTIONS]" % sys.argv[0]
	print ""
	print "-u|--user USER             The gc.com username"
	print "-p|--password PASS         The gc.com password"
	print "-H|--https MODE            0->HTTPS login (default), 1->full HTTPS"
	print "-f|--file FILE             Specify an output/input file. Default is stdout/stdin"
	print ""
	print "-c|--getcookie             Retrieve a logged-in cookie"
	print "-C|--usecookie COOKIE      Do not login but use COOKIE instead."
	print "                           COOKIE should be an already logged-in cookie."
	print "-L|--logout                Logout the cookie."
	print ""
	print "-P|--getpage PAGE          Download a random page from gc.com"
	print "-l|--getloc GUID           Download a LOC file"
	print "-g|--getgpx GUID           Download a GPX file (Need premium account)"
	print "-G|--getguid PAGE          Get the GUID for a page"
	print "-i|--getcacheid GUID       Get the GCxxxx cache ID"
	print ""
	print "-r|--setprofile            Upload the public account profile data."
	print ""
	print "-h|--help                  Print this help text"
	print ""
	print ""
	print "The GUID identifies a cache. The following formats are valid:"
	print "   12345678-1234-1234-1234-123456789123"
	print "   /seek/cache_details.aspx?guid=12345678-1234-1234-1234-123456789123"
	print "   http://www.geocaching.com/seek/cache_details.aspx?guid=12345678-1234-1234-1234-123456789123"
	print "Any geocaching.com URL can be used as PAGE identifier."
	print ""
	print ""
	print "EXAMPLE: Download a LOC file and display it on stdout. Also download the cache-page and save it to the file \"page.html\":"
	print "  gccom.py --getloc 12345678-1234-1234-1234-123456789123 --file page.html --getpage 12345678-1234-1234-1234-123456789123"
	print ""
	print "EXAMPLE: Using wget and gccom.py to download a whole page recursively while being logged in."
	print "   wget -rkl1 --no-cookies --header \"Cookie: $(gccom.py -u USER -p PASSWORD -c)\" http://www.geocaching.com/seek/cache_details.aspx?guid=12345678-1234-1234-1234-123456789123"

def main():
	actions = []

	opt_debug = 0
	opt_HTTPS = 0
	opt_user = None
	opt_password = None
	opt_cookie = None

	try:
		(opts, args) = getopt.getopt(sys.argv[1:],
			"hu:p:f:P:l:g:cC:Li:rH:G:",
			[ "help", "user=", "password=", "file=", "getpage=", "getloc=",
			  "getgpx=", "getcookie", "usecookie=", "logout", "getcacheid=", "getguid=",
			  "setprofile", "https=",
			  "debug", ])
	except getopt.GetoptError:
		usage()
		return 1
	currentFile = None
	for (o, v) in opts:
		if o in ("-h", "--help"):
			usage()
			return 0
		if o == "--debug":
			opt_debug += 1
		if o in ("-u", "--user"):
			opt_user = v
		if o in ("-p", "--password"):
			opt_password = v
		if o in ("-f", "--file"):
			if v.lower() == "stdout":
				v = None
			currentFile = v
		if o in ("-C", "--usecookie"):
			opt_cookie = v
		if o in ("-c", "--getcookie"):
			actions.append(["getcookie", None, currentFile])
		if o in ("-L", "--logout"):
			actions.append(["logout", v, currentFile])
		if o in ("-P", "--getpage"):
			actions.append(["getpage", v, currentFile])
		if o in ("-l", "--getloc"):
			actions.append(["getloc", v, currentFile])
		if o in ("-g", "--getgpx"):
			actions.append(["getgpx", v, currentFile])
		if o in ("-i", "--getcacheid"):
			actions.append(["getcacheid", v, currentFile])
		if o in ("-G", "--getguid"):
			actions.append(["getguid", v, currentFile])
		if o in ("-r", "--setprofile"):
			actions.append(["setprofile", None, currentFile])
		if o in ("-H", "--https"):
			try:
				opt_HTTPS = {
					0 : GC.HTTPS_LOGIN,
					1 : GC.HTTPS_FULL,
				}[v]
			except KeyError:
				print "Error: Invalid HTTPS mode selection"
				return 1
	if not actions:
		print "Error: No actions specified\n"
		usage()
		return 1
	if not opt_cookie:
		if not opt_user:
			opt_user = raw_input("Geocaching.com username: ")
		if not opt_password:
			opt_password = raw_input("Geocaching.com password: ")

	try:
		gc = GC(user=opt_user, password=opt_password,
			predefinedCookie=opt_cookie, httpsMode=opt_HTTPS,
			debug=opt_debug)

		autoLogout = True
		if opt_cookie:
			# Don't auto-logout, if the cookie was passed by --usecookie
			autoLogout = False

		for action in actions:
			request = action[0]
			value = action[1]
			fileName = action[2]

			if request == "getcookie":
				printOutput(fileName, gc.getCookie())
				autoLogout = False
			if request == "getpage":
				printOutput(fileName, gc.getPage(value))
			if request == "getloc":
				printOutput(fileName, gc.getLOC(value))
			if request == "getgpx":
				printOutput(fileName, gc.getGPX(value))
			if request == "getcacheid":
				printOutput(fileName, gc.getCacheDetails(value).gcID)
			if request == "getguid":
				printOutput(fileName, gc.getGuid(value))
			if request == "setprofile":
				gc.setProfile(fetchInput(fileName))
			if request == "logout":
				gc.logout()
				autoLogout = False
		if autoLogout:
			gc.logout()

	except GCException, e:
		print e
		return 1
	except socket.error, e:
		print "Socket error:"
		print e
		return 1
	except httplib.HTTPException, e:
		print "HTTP error:"
		print e.__class__
		return 1
	return 0

if __name__ == "__main__":
	sys.exit(main())
