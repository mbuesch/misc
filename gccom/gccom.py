#!/usr/bin/env python
"""
# Geocaching.com tool
# Public Domain
"""

import sys
import getopt
import httplib
import socket
import urllib
import ssl
import re
import time

opt_debug = False
opt_useHTTPS = True


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

def httpConnect():
	if opt_useHTTPS:
		return httplib.HTTPSConnection(hostname)
	return httplib.HTTPConnection(hostname)

def printDebug(string):
	if opt_debug:
		print string

class GCException(Exception): pass

class GC:
	def __init__(self, user, password, predefinedCookie=None):
		if predefinedCookie:
			self.cookie = predefinedCookie
		else:
			self.cookie = self.__requestCookie()
			self.__login(user, password)

	def __requestCookie(self):
		printDebug("Requesting fresh cookie")
		http = httpConnect()
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
		printDebug("Logging into geocaching.com...")
		http = httpConnect()
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
		printDebug("Login success")

	def logout(self):
		"Logout the cookie"
		printDebug("Logout from geocaching.com...")
		http = httpConnect()
		header = defaultHttpHeader.copy()
		header["Host"] = hostname
		header["Cookie"] = self.cookie
		http.request("GET", "/login/default.aspx?RESET=Y&redir=http%3a%2f%2fwww.geocaching.com%2fdefault.aspx",
			     None, header)
		http.getresponse()
		printDebug("Logout success")

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

	def __getHiddenFormsUrlencoded(self, page):
		"Get all hidden forms on a page. Returns an URL-encoded string"
		forms = []
		for (formId, formValue) in self.__getHiddenForms(page):
			form = formId + "="
			if formValue:
				form += urllib.quote_plus(formValue)
			forms.append(form)
		return "&".join(forms)

	def getPage(self, page):
		"Download a page. Returns the html code of the page."
		http = httpConnect()
		header = defaultHttpHeader.copy()
		header["Host"] = hostname
		header["Cookie"] = self.cookie
		http.request("GET", self.__pageSanitize(page), None, header)
		resp = http.getresponse()
		return resp.read()

	def getLOC(self, page):
		"Download the LOC file from a page"
		http = httpConnect()
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
		http = httpConnect()
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

	def setProfile(self, profileData):
		"Upload new public profile data to the account"
		page = "/account/editprofiledetails.aspx"
		http = httpConnect()
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
	print "-H|--http                  Use HTTP instead of HTTPS"
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

	global opt_debug
	global opt_useHTTPS
	opt_user = None
	opt_password = None
	opt_cookie = None

	try:
		(opts, args) = getopt.getopt(sys.argv[1:],
			"hu:p:f:P:l:g:cC:Li:rH",
			[ "help", "user=", "password=", "file=", "getpage=", "getloc=",
			  "getgpx=", "getcookie", "usecookie=", "logout", "getcacheid=",
			  "setprofile", "http",
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
			opt_debug = True
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
		if o in ("-H", "--http"):
			opt_useHTTPS = False;
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
		gc = GC(opt_user, opt_password, opt_cookie)

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
