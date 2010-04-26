/*
 *   74HC4094 data sniffer
 *
 *   Copyright (C) 2010 Michael Buesch <mb@bu3sch.de>
 *
 *   This program is free software; you can redistribute it and/or
 *   modify it under the terms of the GNU General Public License
 *   version 2 as published by the Free Software Foundation.
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *   GNU General Public License for more details.
 */

#include "util.h"

#include <avr/io.h>
#include <avr/interrupt.h>

#include <stdint.h>
#include <string.h>


/* System configuration */
#define CPU_HZ		16000000

/* 74HC4094 pin connections */
#define LINE_PORT	PORTC
#define LINE_PIN	PINC
#define LINE_DDR	DDRC
#define LINE_CP		0
#define LINE_DATA	1
#define LINE_STROBE	2

/* UART config */
#define UART_BAUDRATE		115200
#define UART_U2X		0


static uint8_t shiftreg_size;
static uint8_t shiftreg[256];			/* The shiftregister state */
static uint8_t shiftreg_out[sizeof(shiftreg)];	/* The output buffers state */


static inline uint8_t get_cp(void)
{
	return !!(LINE_PIN & (1 << LINE_CP));
}

static inline uint8_t get_data(void)
{
	return !!(LINE_PIN & (1 << LINE_DATA));
}

static inline uint8_t get_strobe(void)
{
	return !!(LINE_PIN & (1 << LINE_STROBE));
}

static inline void shift_in_bit(uint8_t bit)
{
	uint8_t tmp, iterator;
	void *regptr;

	irq_disable();

	iterator = shiftreg_size;
	if (!iterator)
		goto out;
	regptr = shiftreg;

	__asm__ __volatile__(
"	clc					\n"
"	sbrc %[data_bit], 0			\n"
"	sec					\n"
"1:						\n"
"	ld %[tmp], Z				\n"
"	rol %[tmp]				\n"
"	st Z+, %[tmp]				\n"
"	dec %[i]				\n"
"	brne 1b					\n"
	: [tmp]			"=d" (tmp)
	, [regptr]		"=z" (regptr)
	, [i]			"=d" (iterator)
	: [data_bit]		"d" (bit)
	,			"1" (regptr)
	,			"2" (iterator)
	);
out:
	irq_enable();
}

static inline void outbuf_update(void)
{
	irq_disable();
	memcpy(shiftreg_out, shiftreg, shiftreg_size);
	irq_enable();
}

static void uart_tx(uint8_t byte)
{
	while (!(UCSRA & (1 << UDRE)));
	UDR = byte;
}

ISR(USART_RXC_vect)
{
	uint8_t new_size = UDR;
	uint8_t i;

	for (i = 0; i < shiftreg_size; i++)
		uart_tx(shiftreg_out[i]);

	if (shiftreg_size != new_size) {
		shiftreg_size = new_size;
		memset(shiftreg, 0, sizeof(shiftreg));
		memset(shiftreg_out, 0, sizeof(shiftreg_out));
	}
}

static void uart_init(void)
{
	/* Set baud rate */
	UBRRL = lo8((CPU_HZ / 16 / UART_BAUDRATE) * (UART_U2X ? 2 : 1));
	UBRRH = hi8((CPU_HZ / 16 / UART_BAUDRATE) * (UART_U2X ? 2 : 1))
		& ~(1 << URSEL);
	UCSRA = ((UART_U2X ? 1 : 0) << U2X);
	/* 8 Data bits, 1 Stop bit, No parity */
	UCSRC = (1 << URSEL) | (1 << UCSZ0) | (1 << UCSZ1);
	/* Enable transceiver */
	UCSRB = (1 << RXEN) | (1 << TXEN) | (1 << RXCIE);
}

int main(void)
{
	uint8_t reg_changed = 0;

	irq_disable();

	LINE_DDR = 0x00;
	LINE_PORT = ~((1 << LINE_CP) | (1 << LINE_DATA) | (1 << LINE_STROBE));

	uart_init();

	irq_enable();
	while (1) {
		if (get_cp()) {
			/* CP high pulse */
			shift_in_bit(get_data());
			while (get_cp()); /* Wait for falling edge */
			reg_changed = 1;
		}
		if (reg_changed && get_strobe()) {
			reg_changed = 0;
			outbuf_update();
		}
	}
}
