# ics2csv
Convert regularly named calendar events to parsed CSV, e.g. for carpool accounting

# Usage

Given calendar events with syntax:

    carpool <driver> <passenger1> [passenger2] [passenger3]

it will calculate carpool balance for all names occuring in the calendar events.

# Syntax

Calendar invites should adhere to syntax:

    carpool <driver> <passenger1> [passenger2] [passenger3]

or more specifically:

    ([\w]+)([\W]+([\w]+))+

Correct:

    Carpool - Peter + Martin + Wolfgang
    carpool Peter    Martin Wolfgang
    carpool Peter, Martin, Wolfgang
    carpool Peter + Martin + Wolfgang +1 (+1 is dropped in accounting, guests are free)
    helloworld Peter+++Martin_,8123,,---Wolfgang
    
Incorrect:
    
    Peter Martin Wolfgang (lacks Carpool magic word)
    carpool PeterMartinWolfgang (cannot split names)
    carpool Peter, Martin Wu, Wolfgang (names must be one word only)
    carpool - Peter, Bart-Jan (names must be only alphanumeric, all other tokens are used as separator)
