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
import socket
import urllib
#import ssl
import re
import time
import sqlite3 as sql


hostname = "www.geocaching.com"

guidRegex = r'\w{8,8}-\w{4,4}-\w{4,4}-\w{4,4}-\w{12,12}'

defaultHttpHeader = {
	"User-Agent" : "User-Agent: Mozilla/5.0 (Windows; U; " +\
		       "Windows NT 5.1; en-us; rv:1.9.0.10) Gecko/20051213 Firefox/1.5",
	"Accept" : "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
	"Accept-Language" : "en-us,en;q=0.5",
	"Accept-Charset" : "ISO-8859-1,utf-8;q=0.7,*;q=0.7",
	"Keep-Alive" : "300",
	"Connection" : "keep-alive",
}


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
			c.execute("INSERT INTO pages VALUES(?, ?, strftime('%s', 'now'));", (path, data))
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

class GC:
	HTTPS_NONE	= 0
	HTTPS_LOGIN	= 1
	HTTPS_FULL	= 2

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
		if self.httpsMode == self.HTTPS_NONE or\
		   (self.httpsMode == self.HTTPS_LOGIN and not inLogin):
			return httplib.HTTPConnection(hostname)
		return httplib.HTTPSConnection(hostname)

	def __requestCookie(self):
		self.__printDebug("Requesting fresh cookie")
		http = self.__httpConnect(inLogin=True)
		http.request("GET", "/")
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
		body = self.__getHiddenFormsUrlencoded("/login/default.aspx") + "&" +\
			"ctl00%24ContentBody%24myUsername=" + urllib.quote_plus(user) + "&" +\
			"ctl00%24ContentBody%24myPassword=" + urllib.quote_plus(password) + "&" +\
			"ctl00%24ContentBody%24Button1=Login"
		header = defaultHttpHeader.copy()
		header["Host"] = hostname
		header["Cookie"] = self.cookie
		header["Content-Type"] = "application/x-www-form-urlencoded"
		header["Content-Length"] = str(len(body))
		http.request("POST", "/login/default.aspx?RESET=Y&redir=http%3a%2f%2fwww.geocaching.com%2fdefault.aspx",
			     body, header)
		resp = http.getresponse()
		if resp.read().find("combination does not match") >= 0:
			raise GCException("Invalid username and/or password")
		time.sleep(1) # Server doesn't like other requests right after login.
		self.__printDebug("Login success")

	def logout(self):
		"Logout the cookie"
		self.__printDebug("Logout from geocaching.com...")
		http = self.__httpConnect()
		header = defaultHttpHeader.copy()
		header["Host"] = hostname
		header["Cookie"] = self.cookie
		http.request("GET", "/login/default.aspx?RESET=Y&redir=http%3a%2f%2fwww.geocaching.com%2fdefault.aspx",
			     None, header)
		http.getresponse()
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

	def __getHiddenForms(self, page):
		"Get all hidden forms on a page. Returns a list of tuples of (id, value)"
		p = self.getPage(page)
		p = self.__removeChars(p, "\r\n")
		return re.findall(r'<input\s+type="hidden"\s+name="\w*"\s+id="(\w+)"\s+value="([/%=\w\+]*)"\s*/>', p)

	def __getHiddenFormsUrlencoded(self, page, omitForms=[]):
		"Get all hidden forms on a page. Returns an URL-encoded string"
		forms = []
		for (formId, formValue) in self.__getHiddenForms(page):
			if formId in omitForms:
				continue
			form = formId + "="
			if formValue:
				form += urllib.quote_plus(formValue)
			forms.append(form)
		return "&".join(forms)

	def getPage(self, page):
		"Download a page. Returns the html code of the page."
		page = self.__pageSanitize(page)
		data = self.pageStorage.get(page)
		if data:
			return data
		http = self.__httpConnect()
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

	def getCacheId(self, page):
		"Get the GCxxxx cache ID"
		p = self.getPage(page)
		p = self.__removeChars(p, "\r\n")
		m = re.compile(r'.*<title>\s*(GC\w+)\s.*</title>.*').match(p)
		if not m:
			raise GCException("Failed to get cache ID from " + page)
		id = m.group(1).strip()
		return id

	def getCacheTitle(self, page):
		"Get the cache title"
		p = self.getPage(page)
		startstr = '<meta name="og:title" content="'
		begin = p.find(startstr)
		if begin < 0:
			raise GCException("Failed to get cache title from " + page)
		begin += len(startstr)
		end = p.find('"', begin)
		if end < 0:
			raise GCException("Failed to get cache title from " + page)
		return p[begin:end]

	def getCacheLocation(self, page):
		"Get the location of a cache. Returns a tuple of (latitude, longitude)."
		p = self.getPage(page)
		p = self.__removeChars(p, "\r\n")
		m = re.compile(r'.*title="Other Conversions"\s+href="/wpt/\?' +
			       r'lat=([\d\.]+)&amp;lon=([\d\.]+)&amp;detail=.*').match(p)
		if not m:
			raise GCException("Failed to get cache location from " + page)
		try:
			lat = float(m.group(1))
			lng = float(m.group(2))
		except ValueError:
			raise GCException("Failed to convert cache location from " + page)
		return (lat, lng)

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
		if resp.find("Your Account Details") < 0:
			raise GCException("Failed to upload profile data to the account")

	def findCaches(self, centerLatitude, centerLongitude, radiusKM,
		       maxNrCaches=100):
		"Get a list of caches at position"
		centerLatitude = round(centerLatitude, 3)
		centerLongitude = round(centerLongitude, 3)
		radiusKM = round(radiusKM, 2)
		cachesList = []
		page = "/seek/nearest.aspx" + "?" +\
			"origin_lat=%f" % centerLatitude + "&" +\
			"origin_long=%f" % centerLongitude + "&" +\
			"dist=%f" % radiusKM + "&" +\
			"submit3=Search"
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
			data = self.__removeChars(data, "\r\n")
			if data.find("Distance Measured in Kilometers") < 0:
				raise GCException("findCaches(): distance not measured in km")
			regex = r'<a\s+href="/seek/cache_details\.aspx\?guid=(' + guidRegex +\
				r')"\s+class="lnk"><img\s+src='
			foundGuids = re.findall(regex, data)
			if not foundGuids:
				break
			count += len(foundGuids)
			cachesList.extend(foundGuids)
			pageNr += 1
		return cachesList[0:maxNrCaches]

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
	print "-H|--https MODE            0->HTTP, 1->HTTPS login (default), 2->full HTTPS"
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
	opt_HTTPS = GC.HTTPS_LOGIN
	opt_user = None
	opt_password = None
	opt_cookie = None

	try:
		(opts, args) = getopt.getopt(sys.argv[1:],
			"hu:p:f:P:l:g:cC:Li:rH:",
			[ "help", "user=", "password=", "file=", "getpage=", "getloc=",
			  "getgpx=", "getcookie", "usecookie=", "logout", "getcacheid=",
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
		if o in ("-r", "--setprofile"):
			actions.append(["setprofile", None, currentFile])
		if o in ("-H", "--https"):
			try:
				opt_HTTPS = {
					0 : GC.HTTPS_NONE,
					1 : GC.HTTPS_LOGIN,
					2 : GC.HTTPS_FULL,
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
				printOutput(fileName, gc.getCacheId(value))
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
