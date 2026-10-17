# Status report 4: does splitting the canceller into small cells change its noise? (2026-10-17)

*Plain-language. Simulation only. Technical detail: [`../afe-architecture.md`](../afe-architecture.md) §39.*

## The question
The steady-current canceller will be a real digital-to-analog converter made of many small
identical transistor "cells" switched on or off. Earlier I *argued* that splitting one big
cancelling transistor into many cells would not change its noise, but I had not tested it.

## What I did
Added an option to the simulator that builds the canceller as n separate cells, each with its
own small resistor in its source, and compared the pulse-path noise with a single big transistor
of the same total area and the same voltage drop.

## Result
| Case | Split into cells | One big device |
|---|---|---|
| 16 cells, 1 µA | 3.5 pA | 3.5 pA |
| 4 cells, 1 µA | 5.5 pA | 5.5 pA |
| 4 cells, 100 nA | 1.5 pA | 1.5 pA |

They match exactly. So the number of cells can be chosen for accuracy and switching glitches;
noise depends only on the total transistor area that is switched on and on the resistor drop
(about 0.3 V).

## Limits of this check
Real cells differ slightly from one another (mismatch), which affects the accuracy of the
converter but is not part of this noise result. Switching of cells, glitches and the
sigma-delta fine part were not simulated. The transistor noise model is still not compared with
real silicon.

## What is still open
Relay-attack decision and a proper cryptographic pattern generator; actual converter circuit
(switches, current steps); digital power and layout area; wideband bandwidth (63 kHz vs 480 kHz).
