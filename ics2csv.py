#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Tue Jan 21 21:28:10 2020

@author: twerkhov
"""

from icalendar import Calendar
import re
import yaml

# config should contain
config = yaml.safe_load(open("utrechtcarpool.yaml"))
calfile = config['calfile']
validamlocs = config['validamlocs']
validpmlocs = config['validpmlocs']

def get_driver_passengers(topic):
    """
    From event topic (summary), get driver and passenger
    
    Expected syntax:
        '(carpool)([\W]+([\w]+))+'
    e.g.
        Carpool - Peter + Martin + Wolfgang
        carpool Peter    Martin Wolfgang
        carpool Peter, Martin, Wolfgang
    
    Not OK:
        Peter Martin Wolfgang (lacks Carpool magic word)
        carpool PeterMartinWolfgang (cannot split names)
        carpool Peter, Martin Wu, Wolfgang (names must be one word only)
        carpool - Peter, Bart-Jan (names must be only alphanumeric, all other tokens are used as separator)
    """
    # Regexp pattern to strip non-alphanumeric characters
    # https://stackoverflow.com/questions/1276764/stripping-everything-but-alphanumeric-chars-from-a-string-in-python
    # Split topic by non-alphanumeric characters - https://docs.python.org/2/library/re.html
    names = re.split('\W+',topic.lower(), re.UNICODE)
    driver = names[1]
    passengers = names[2:]
    
    return (driver, passengers)

def get_location(location, time):
    """
    From event location string, get validated carpool location
    """
    # Depending on time, we assume different locations
    if time.dt.hour < 12:
        validlocs = validamlocs
        locdefault = "UNKNOWN-EVERDINGEN"
    else:
        validlocs = validpmlocs
        locdefault = "UNKNOWN-B7"

    # For each valid location, check if it's found in the actual location string
    loc = location.lower()
    for v in validlocs:
        if v in loc:
            # If valid location found, return immediately
            return v
    # If nothing found, return default location
    return locdefault

def normalize_ics(file='calendar.ics'):
    """
    Given ICS file, normalize for carpool accounting to fixed set of drivers, times, locations.
    """
    with open(file,'rb') as g:
        gcal = Calendar.from_ical(g.read())
        # Only look at events (name == 'VEVENT') that are not cancelled (STATUS != 'TRANSPARENT')
        # Get people from SUMMARY, get valid location from LOCATION/DTSTART
        normed = [(get_driver_passengers(c.get('SUMMARY')),
                get_location(c.get('LOCATION'),
                c.get('DTSTART')),c.get('DTSTART').dt) 
                    for c in gcal.walk() 
                        if (c.name == 'VEVENT' and 
                            c.get('TRANSP') != 'TRANSPARENT')]
    return normed

def carpool_account(normics, tripcost=80):
    """
    Given normalized ICS input (driver, passengers, departure location, 
    start time), distribute tripcost over driver and passenger.
    """

    balance = {}

    for driverpass, loc, time in normics:
        print (driverpass)
        # Unpack driver and passengers
        driver, passengers = driverpass
        npers = 1 + len(passengers)
        balance[driver] = balance.get(driver,0) + tripcost - tripcost/npers
        for p in passengers:
            balance[p] = balance.get(p,0) - tripcost/npers
    print (balance)


def find_dest(normics):
    """
    Given normalized ICS input (driver, passengers, departure location, 
    start time), find matching destination location by checking what is the 
    departure location of the next trip by the same driver.
    
    Typically a driver departs from location X in the morning, then departs
    from locaiton Y in the afternoon, meaning the trip was X->Y and Y->X.
    """
    pass

normics = normalize_ics(calfile)
carpacc = carpool_account(normics)

# matchedics = find_dest(normics)
# carpool_account_distance(normics)
