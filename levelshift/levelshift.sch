EESchema Schematic File Version 2
LIBS:power
LIBS:device
LIBS:transistors
LIBS:conn
LIBS:linear
LIBS:regul
LIBS:74xx
LIBS:cmos4000
LIBS:adc-dac
LIBS:memory
LIBS:xilinx
LIBS:microcontrollers
LIBS:dsp
LIBS:microchip
LIBS:analog_switches
LIBS:motorola
LIBS:texas
LIBS:intel
LIBS:audio
LIBS:interface
LIBS:digital-audio
LIBS:philips
LIBS:display
LIBS:cypress
LIBS:siliconi
LIBS:opto
LIBS:atmel
LIBS:contrib
LIBS:valves
LIBS:am2d-0515dz
LIBS:levelshift-cache
EELAYER 25 0
EELAYER END
$Descr A4 11693 8268
encoding utf-8
Sheet 1 1
Title "Levelshifter"
Date ""
Rev "1.0"
Comp "Michael Buesch <m@bues.ch>"
Comment1 ""
Comment2 ""
Comment3 ""
Comment4 ""
$EndDescr
$Comp
L AM2D-0515DZ U3
U 1 1 576AE30F
P 6550 2000
F 0 "U3" H 6550 2250 60  0000 C CNN
F 1 "AM2D-0515DZ" H 6550 1750 60  0000 C CNN
F 2 "" H 6550 2000 60  0000 C CNN
F 3 "" H 6550 2000 60  0000 C CNN
	1    6550 2000
	1    0    0    -1  
$EndComp
$Comp
L 7805 U2
U 1 1 576AE389
P 3950 2000
F 0 "U2" H 4100 1804 50  0000 C CNN
F 1 "7806" H 3950 2200 50  0000 C CNN
F 2 "" H 3950 2000 50  0000 C CNN
F 3 "" H 3950 2000 50  0000 C CNN
	1    3950 2000
	1    0    0    -1  
$EndComp
$Comp
L D D1
U 1 1 576AE3C8
P 3050 1950
F 0 "D1" H 3050 2050 50  0000 C CNN
F 1 "4001" H 3050 1850 50  0000 C CNN
F 2 "" H 3050 1950 50  0000 C CNN
F 3 "" H 3050 1950 50  0000 C CNN
	1    3050 1950
	-1   0    0    1   
$EndComp
$Comp
L C_Small C2
U 1 1 576AE554
P 4500 2200
F 0 "C2" H 4510 2270 50  0000 L CNN
F 1 "0.1 µF" H 4510 2120 50  0000 L CNN
F 2 "" H 4500 2200 50  0000 C CNN
F 3 "" H 4500 2200 50  0000 C CNN
	1    4500 2200
	1    0    0    -1  
$EndComp
$Comp
L C_Small C1
U 1 1 576AE60D
P 3400 2200
F 0 "C1" H 3410 2270 50  0000 L CNN
F 1 "0.33 µF" H 3410 2120 50  0000 L CNN
F 2 "" H 3400 2200 50  0000 C CNN
F 3 "" H 3400 2200 50  0000 C CNN
	1    3400 2200
	1    0    0    -1  
$EndComp
Wire Wire Line
	3200 1950 3550 1950
Wire Wire Line
	3400 1950 3400 2100
Wire Wire Line
	4500 1950 4500 2100
Wire Wire Line
	3400 2300 3400 2450
Wire Wire Line
	3950 2450 3950 2250
Wire Wire Line
	4500 2450 4500 2300
Connection ~ 3950 2450
Connection ~ 3400 1950
Wire Wire Line
	1900 1950 2900 1950
Wire Wire Line
	1900 2050 2700 2050
Wire Wire Line
	2700 2050 2700 2450
Connection ~ 3400 2450
Connection ~ 4500 1950
Wire Wire Line
	6050 2050 5900 2050
Wire Wire Line
	5900 2050 5900 2450
Connection ~ 4500 2450
Text GLabel 9550 1650 2    60   Input ~ 0
+15V
Text GLabel 9550 2350 2    60   Input ~ 0
-15V
Text GLabel 6050 4100 2    60   Input ~ 0
+15V
Text GLabel 6050 4800 2    60   Input ~ 0
-15V
Text GLabel 8200 4000 2    60   Input ~ 0
+15V
Text GLabel 8200 4700 2    60   Input ~ 0
-15V
$Comp
L GND #PWR2
U 1 1 576AF283
P 9550 2000
F 0 "#PWR2" H 9550 1750 50  0001 C CNN
F 1 "GND" H 9550 1850 50  0000 C CNN
F 2 "" H 9550 2000 50  0000 C CNN
F 3 "" H 9550 2000 50  0000 C CNN
	1    9550 2000
	0    -1   -1   0   
$EndComp
$Comp
L R R1
U 1 1 576AF854
P 5250 4550
F 0 "R1" V 5330 4550 50  0000 C CNN
F 1 "10k" V 5250 4550 50  0000 C CNN
F 2 "" V 5180 4550 50  0000 C CNN
F 3 "" H 5250 4550 50  0000 C CNN
	1    5250 4550
	0    1    1    0   
$EndComp
Wire Wire Line
	6050 4800 6000 4800
Wire Wire Line
	6000 4800 6000 4750
Wire Wire Line
	6050 4100 6000 4100
Wire Wire Line
	6000 4100 6000 4150
Wire Wire Line
	8200 4000 8150 4000
Wire Wire Line
	8150 4000 8150 4050
Wire Wire Line
	8200 4700 8150 4700
Wire Wire Line
	8150 4700 8150 4650
Wire Wire Line
	5400 4550 5800 4550
Connection ~ 5700 4550
$Comp
L R R4
U 1 1 576AFF5D
P 7400 4450
F 0 "R4" V 7480 4450 50  0000 C CNN
F 1 "2.2k" V 7400 4450 50  0000 C CNN
F 2 "" V 7330 4450 50  0000 C CNN
F 3 "" H 7400 4450 50  0000 C CNN
	1    7400 4450
	0    1    1    0   
$EndComp
Connection ~ 7750 4450
Connection ~ 6500 4450
$Comp
L POT RV1
U 1 1 576B0711
P 4750 5900
F 0 "RV1" H 4750 5820 50  0000 C CNN
F 1 "47k" H 4750 5900 50  0000 C CNN
F 2 "" H 4750 5900 50  0000 C CNN
F 3 "" H 4750 5900 50  0000 C CNN
	1    4750 5900
	1    0    0    -1  
$EndComp
Text Label 2000 1950 0    39   ~ 0
PWR_7-24VDC
Text Label 2000 2050 0    39   ~ 0
PWR_GND
$Comp
L CONN_01X02 P1
U 1 1 576B0D12
P 1200 4500
F 0 "P1" H 1200 4650 50  0000 C CNN
F 1 "SIG_IN" V 1300 4500 50  0000 C CNN
F 2 "" H 1200 4500 50  0000 C CNN
F 3 "" H 1200 4500 50  0000 C CNN
	1    1200 4500
	-1   0    0    1   
$EndComp
$Comp
L CONN_01X02 P3
U 1 1 576B0E27
P 10550 4300
F 0 "P3" H 10550 4450 50  0000 C CNN
F 1 "SIG_OUT" V 10650 4300 50  0000 C CNN
F 2 "" H 10550 4300 50  0000 C CNN
F 3 "" H 10550 4300 50  0000 C CNN
	1    10550 4300
	1    0    0    -1  
$EndComp
$Comp
L GND #PWR1
U 1 1 576B1285
P 1950 4650
F 0 "#PWR1" H 1950 4400 50  0001 C CNN
F 1 "GND" H 1950 4500 50  0000 C CNN
F 2 "" H 1950 4650 50  0000 C CNN
F 3 "" H 1950 4650 50  0000 C CNN
	1    1950 4650
	1    0    0    -1  
$EndComp
Wire Wire Line
	1400 4550 1950 4550
Wire Wire Line
	9700 4250 10350 4250
Connection ~ 8750 4350
$Comp
L C_Small C5
U 1 1 576B2052
P 8350 1800
F 0 "C5" H 8360 1870 50  0000 L CNN
F 1 "10 nF" H 8360 1720 50  0000 L CNN
F 2 "" H 8350 1800 50  0000 C CNN
F 3 "" H 8350 1800 50  0000 C CNN
	1    8350 1800
	1    0    0    -1  
$EndComp
$Comp
L C_Small C6
U 1 1 576B20A3
P 8350 2200
F 0 "C6" H 8360 2270 50  0000 L CNN
F 1 "10 nF" H 8360 2120 50  0000 L CNN
F 2 "" H 8350 2200 50  0000 C CNN
F 3 "" H 8350 2200 50  0000 C CNN
	1    8350 2200
	1    0    0    -1  
$EndComp
Wire Wire Line
	7050 1900 7350 1900
Wire Wire Line
	7350 1900 7350 1650
Wire Wire Line
	7350 1650 9550 1650
Wire Wire Line
	8350 1650 8350 1700
Connection ~ 8350 1650
Wire Wire Line
	7050 2100 7350 2100
Wire Wire Line
	7350 2100 7350 2350
Wire Wire Line
	7350 2350 9550 2350
Wire Wire Line
	8350 2350 8350 2300
Connection ~ 8350 2350
Wire Wire Line
	7050 2000 9550 2000
Wire Wire Line
	8350 1900 8350 2100
Connection ~ 8350 2000
Wire Wire Line
	8550 4350 10350 4350
$Comp
L R R3
U 1 1 576C0E2E
P 6100 5150
F 0 "R3" V 6180 5150 50  0000 C CNN
F 1 "10k" V 6100 5150 50  0000 C CNN
F 2 "" V 6030 5150 50  0000 C CNN
F 3 "" H 6100 5150 50  0000 C CNN
	1    6100 5150
	0    1    1    0   
$EndComp
Wire Wire Line
	5950 5150 5700 5150
Wire Wire Line
	6250 5150 6500 5150
$Comp
L R R2
U 1 1 576C16A5
P 5250 4850
F 0 "R2" V 5330 4850 50  0000 C CNN
F 1 "10k" V 5250 4850 50  0000 C CNN
F 2 "" V 5180 4850 50  0000 C CNN
F 3 "" H 5250 4850 50  0000 C CNN
	1    5250 4850
	0    1    1    0   
$EndComp
Wire Wire Line
	5400 4850 5600 4850
Text GLabel 5100 5900 2    60   Input ~ 0
+15V
Text GLabel 4400 5900 0    60   Input ~ 0
-15V
Wire Wire Line
	4400 5900 4600 5900
Wire Wire Line
	4900 5900 5100 5900
Wire Wire Line
	4750 4850 5100 4850
$Comp
L CP_Small C7
U 1 1 576C2EF7
P 8900 1800
F 0 "C7" H 8910 1870 50  0000 L CNN
F 1 "100 µF / 25 V" H 8910 1720 50  0000 L CNN
F 2 "" H 8900 1800 50  0000 C CNN
F 3 "" H 8900 1800 50  0000 C CNN
	1    8900 1800
	1    0    0    -1  
$EndComp
$Comp
L CP_Small C8
U 1 1 576C3021
P 8900 2200
F 0 "C8" H 8910 2270 50  0000 L CNN
F 1 "100 µF / 25 V" H 8910 2120 50  0000 L CNN
F 2 "" H 8900 2200 50  0000 C CNN
F 3 "" H 8900 2200 50  0000 C CNN
	1    8900 2200
	1    0    0    -1  
$EndComp
Wire Wire Line
	8900 1650 8900 1700
Connection ~ 8900 1650
Wire Wire Line
	8900 2350 8900 2300
Connection ~ 8900 2350
Wire Wire Line
	8900 1900 8900 2100
Connection ~ 8900 2000
$Comp
L POT RV2
U 1 1 576C4979
P 8250 5900
F 0 "RV2" H 8250 5820 50  0000 C CNN
F 1 "4.7k" H 8250 5900 50  0000 C CNN
F 2 "" H 8250 5900 50  0000 C CNN
F 3 "" H 8250 5900 50  0000 C CNN
	1    8250 5900
	-1   0    0    1   
$EndComp
Wire Wire Line
	8250 6050 8250 6100
Wire Wire Line
	8450 6100 8450 5900
Wire Wire Line
	8750 5900 8400 5900
Connection ~ 8450 5900
Wire Wire Line
	7750 5900 8100 5900
Connection ~ 5600 4550
Wire Wire Line
	7550 4450 7950 4450
$Comp
L LM324 U1
U 1 1 576C6AA0
P 3700 4550
F 0 "U1" H 3750 4750 50  0000 C CNN
F 1 "LM324" H 3850 4350 50  0000 C CNN
F 2 "" H 3650 4650 50  0000 C CNN
F 3 "" H 3750 4750 50  0000 C CNN
	1    3700 4550
	1    0    0    -1  
$EndComp
$Comp
L LM324 U1
U 2 1 576C6B09
P 6100 4450
F 0 "U1" H 6150 4650 50  0000 C CNN
F 1 "LM324" H 6250 4250 50  0000 C CNN
F 2 "" H 6050 4550 50  0000 C CNN
F 3 "" H 6150 4650 50  0000 C CNN
	2    6100 4450
	1    0    0    -1  
$EndComp
$Comp
L LM324 U1
U 3 1 576C6B60
P 8250 4350
F 0 "U1" H 8300 4550 50  0000 C CNN
F 1 "LM324" H 8400 4150 50  0000 C CNN
F 2 "" H 8200 4450 50  0000 C CNN
F 3 "" H 8300 4550 50  0000 C CNN
	3    8250 4350
	1    0    0    -1  
$EndComp
Text GLabel 3650 4200 2    60   Input ~ 0
+15V
Text GLabel 3650 4900 2    60   Input ~ 0
-15V
Wire Wire Line
	3650 4200 3600 4200
Wire Wire Line
	3600 4200 3600 4250
Wire Wire Line
	3650 4900 3600 4900
Wire Wire Line
	3600 4900 3600 4850
Wire Wire Line
	4000 4550 5100 4550
Wire Wire Line
	4200 4550 4200 5150
Wire Wire Line
	4200 5150 3200 5150
Wire Wire Line
	3200 5150 3200 4650
Wire Wire Line
	3200 4650 3400 4650
Wire Wire Line
	7750 4450 7750 5900
Wire Wire Line
	8750 4350 8750 5900
Wire Wire Line
	7750 4250 7950 4250
Wire Wire Line
	7750 3600 7750 4250
Wire Wire Line
	6400 4450 7250 4450
Wire Wire Line
	5600 4850 5600 4550
Wire Wire Line
	4750 4850 4750 5750
Connection ~ 4200 4550
Wire Wire Line
	5700 4350 5800 4350
Wire Wire Line
	5700 3600 5700 4350
Wire Wire Line
	9700 3600 9700 4250
Wire Wire Line
	1950 3600 9700 3600
Connection ~ 7750 3600
Wire Wire Line
	1400 4450 3400 4450
Wire Wire Line
	1950 3600 1950 4650
Connection ~ 5700 3600
Connection ~ 1950 4550
Wire Wire Line
	8250 6100 8450 6100
Wire Wire Line
	5700 5150 5700 4550
Wire Wire Line
	6500 5150 6500 4450
$Comp
L CONN_01X03 P2
U 1 1 576DA1CE
P 1700 1950
F 0 "P2" H 1700 2150 50  0000 C CNN
F 1 "PWR_IN" V 1800 1950 50  0000 C CNN
F 2 "" H 1700 1950 50  0000 C CNN
F 3 "" H 1700 1950 50  0000 C CNN
	1    1700 1950
	-1   0    0    1   
$EndComp
Wire Wire Line
	1900 1850 2700 1850
Text Label 2000 1850 0    39   ~ 0
PWR_5VDC
$Comp
L D D3
U 1 1 576DA668
P 5350 1950
F 0 "D3" H 5350 2050 50  0000 C CNN
F 1 "4001" H 5350 1850 50  0000 C CNN
F 2 "" H 5350 1950 50  0000 C CNN
F 3 "" H 5350 1950 50  0000 C CNN
	1    5350 1950
	-1   0    0    1   
$EndComp
Wire Wire Line
	5900 2450 2700 2450
Wire Wire Line
	4350 1950 5200 1950
$Comp
L D D2
U 1 1 576DAA6B
P 5350 1550
F 0 "D2" H 5350 1650 50  0000 C CNN
F 1 "4001" H 5350 1450 50  0000 C CNN
F 2 "" H 5350 1550 50  0000 C CNN
F 3 "" H 5350 1550 50  0000 C CNN
	1    5350 1550
	-1   0    0    1   
$EndComp
Wire Wire Line
	5500 1950 6050 1950
Wire Wire Line
	5500 1550 5900 1550
Wire Wire Line
	5900 1550 5900 1950
Connection ~ 5900 1950
Wire Wire Line
	2700 1850 2700 1550
Wire Wire Line
	2700 1550 5200 1550
$Comp
L C_Small C3
U 1 1 576DB207
P 7800 1800
F 0 "C3" H 7810 1870 50  0000 L CNN
F 1 "22 pF" H 7810 1720 50  0000 L CNN
F 2 "" H 7800 1800 50  0000 C CNN
F 3 "" H 7800 1800 50  0000 C CNN
	1    7800 1800
	1    0    0    -1  
$EndComp
$Comp
L C_Small C4
U 1 1 576DB32F
P 7800 2200
F 0 "C4" H 7810 2270 50  0000 L CNN
F 1 "22 pF" H 7810 2120 50  0000 L CNN
F 2 "" H 7800 2200 50  0000 C CNN
F 3 "" H 7800 2200 50  0000 C CNN
	1    7800 2200
	1    0    0    -1  
$EndComp
Wire Wire Line
	7800 1650 7800 1700
Wire Wire Line
	7800 2350 7800 2300
Wire Wire Line
	7800 1900 7800 2100
Connection ~ 7800 2000
Connection ~ 7800 1650
Connection ~ 7800 2350
Text Label 1500 4450 0    39   ~ 0
SIG_IN
Text Label 1500 4550 0    39   ~ 0
SIG_GND
Text Label 10000 4350 0    39   ~ 0
SIG_OUT
Text Label 10000 4250 0    39   ~ 0
SIG_GND
$EndSCHEMATC
