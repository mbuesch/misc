/* Simple LD_PRELOAD library to force stdout/stderr into line-buffered mode.
 * This file is released to the Public Domain. */

#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>

#define TARGET_MODE	_IOLBF


static int (*libc_setvbuf)(FILE *stream, char *buf, int mode, size_t size);
static int in_stdiobufhack;

int setvbuf(FILE *stream, char *buf, int mode, size_t size)
{
	if (in_stdiobufhack)
		return 0;
	in_stdiobufhack = 1;

	if (!libc_setvbuf)
		libc_setvbuf = dlsym(RTLD_NEXT, "setvbuf");
	if (!libc_setvbuf) {
		fprintf(stderr, "stdiobufhack: Did not find libc setvbuf()\n");
		exit(1);
	}

	if (stream == stdout || stream == stderr)
		mode = TARGET_MODE;

	in_stdiobufhack = 0;

	return libc_setvbuf(stream, buf, mode, size);
}

static void __attribute__((__constructor__)) stdiobufhack_ctor(void)
{
	setvbuf(stdout, NULL, TARGET_MODE, 1024);
	setvbuf(stderr, NULL, TARGET_MODE, 1024);
}
