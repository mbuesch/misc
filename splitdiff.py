inPreamble = True
inPatch = False
	if line.startswith("diff ") or \
	   line.startswith("--- ") or \
	   line.startswith("+++ "):
		if inPreamble or inPatch:
			path = line.strip().split(" ")[-1]
			path = path.split("/")
			if len(path) <= prefix:
				die("Could not strip all prefix")
			path = path[prefix:]
			filename = "-".join(path)
			filename = "%03d-%s.diff" % (fileNr, filename)
			fileNr += 1
			if fd:
				fd.close()
			fd = file(filename, "w")
			out(line)
			inPreamble = False
			inPatch = False
			continue
		else:
			out(line)
			continue
	if line.startswith("index "):
		if not inPreamble:
			out(line)
	if line.startswith("\\ No newline at end of file") or \
	   line.startswith("deleted file mode ") or \
	   line.startswith("+") or \
	   line.startswith("-") or \
	   line.startswith(" ") or \
	   line.startswith("@@ "):
		if not inPreamble:
			inPatch = True
	if not inPreamble:
		die("Parse error in line %d" % lineNr)