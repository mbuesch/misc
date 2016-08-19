# Project name
NAME			:= example

# Project source files
SRCS			:= main.c
GEN_SRCS		:=

# Bootloader source files
BOOT_SRCS		:=
BOOT_GEN_SRCS		:=
BOOT_OFFSET		:= 0x7000

# CPU speed, in Hz
F_CPU			:= 16000000UL

# Project fuse bits
LFUSE			:= 0xA0
HFUSE			:= 0xD8
EFUSE			:=

# Architecture configuration
GCC_ARCH		:= atmega32
AVRDUDE_ARCH		:= m32
FUNC_STACK_LIMIT	:= 32

# Programmer selection.
# Values can be:  avrisp2, mysmartusb
PROGRAMMER		:= avrisp2

# Instrumentation
INSTRUMENT_FUNC		:=
BOOT_INSTRUMENT_FUNC	:=

# Additional compiler flags
CFLAGS			:=
LDFLAGS			:=
SPARSEFLAGS		:=
BOOT_CFLAGS		:=
BOOT_LDFLAGS		:=
BOOT_SPARSEFLAGS	:=

# Additional "clean" and "distclean" target files
CLEAN_FILES		:=
DISTCLEAN_FILES		:=


include ../avrmakelib.mk
