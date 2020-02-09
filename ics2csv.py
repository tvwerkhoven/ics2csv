#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jan 21 21:28:10 2020

# About

Do carpool accounting for a group of carpoolers to determine who should drive 
when. Given an ICS file, parse event subjects reading out carpool 
appointments, then calculate accounting and report results as html page.

# Calendar events

Event subjects can contain two type of data:
1. Carpool appointment: "Carpool <driver> <passenger1> [passengerN]"
2. Balance transfer: "Transfer <creditor> <debtor> <amount in EUR>"

# Data structure

Events are parsed and stored in a OrderedDict. Although dicts are ordered 
since python3.7, OrderedDict gives us compatibility for all python3. See also
https://stackoverflow.com/questions/50872498/will-ordereddict-become-redundant-in-python-3-7

Example data:

<date> : {'type': 'carpool', 
    'driver': '<driver>', 
    'passengers': '<list of passengers>', 
    'location': '<carpool departure location>',
    'destination': '<calculated destination location>'
    }

<date> : {'type': 'transfer', 
    'creditor': '<person>', 
    'debtor': '<person>', 
    'amount': '<transfer amount in EUR>'
    }

"""

import argparse
import ast
from icalendar import Calendar
import re
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
import csv
import json
import datetime
from collections import OrderedDict

# config should contain
config = yaml.safe_load(open(r"./sample/carpool-anon.yaml"))
calfile = config['calfile']
validamlocs = config['validamlocs']
validpmlocs = config['validpmlocs']
defaultamloc = "UNKNOWN-EVERDINGEN"
defaultpmloc = "UNKNOWN-B7"

RE_TOPIC_SPLIT = re.compile('[^a-zA-Z]+')
def get_driver_passengers(topic):
    """
    From event topic (summary), get driver and passenger
    
    Expected syntax:
        'carpool([\W]+([\w]+))+'
    e.g.
        Carpool - Peter + Martin + Wolfgang
        carpool Peter    Martin Wolfgang
        carpool Peter, Martin, Wolfgang
        carpool Peter + Martin + Wolfgang +1 (+1 is dropped in accounting, guests are free)
        helloworld Peter+++Martin_,8123,,---Wolfgang

    Not OK:
        Peter Martin Wolfgang (lacks Carpool magic word)
        carpool PeterMartinWolfgang (cannot split names)
        carpool Peter, Martin Wu, Wolfgang (names must be one word only)
        carpool - Peter, Bart-Jan (names must be only alphanumeric, all other tokens are used as separator)
    """
    # Regexp pattern to strip non-alphanumeric characters
    # https://stackoverflow.com/questions/1276764/stripping-everything-but-alphanumeric-chars-from-a-string-in-python
    # Split topic by non-alphanumeric characters - https://docs.python.org/2/library/re.html
    names = RE_TOPIC_SPLIT.split(topic.lower(), re.UNICODE)

    # Remove empty hits in case string ends in non-alphanumeric char (e.g. 
    # space). Alternatively we could strip() the string using all 
    # non-alphanumeric charactere, but another regexp is probably slower
    names = list(filter(None, names))

    driver = names[1]
    passengers = names[2:]
        
    return [driver, passengers]

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
            # If valid location found, return immediately, we only accept 
            # one location match
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
        normed = [get_driver_passengers(c.get('SUMMARY')) +
                [get_location(c.get('LOCATION'),
                c.get('DTSTART')),c.get('DTSTART').dt] 
                    for c in gcal.walk() 
                        if (c.name == 'VEVENT' and 
                            c.get('TRANSP') != 'TRANSPARENT')]
    return normed

def carpool_account(lastevents, tripcost=16):
    """
    Given normalized ICS input (driver, passengers, departure location, 
    start time), distribute tripcost over driver and passenger.
    """

    balance = {}

    for driver, passengers, loc, time in lastevents:
        # print("d: {}, d: {}, p: {}".format(time, driver, ",".join(passengers)))
        npers = 1 + len(passengers)
        balance[driver] = balance.get(driver,0) + tripcost - tripcost/npers
        for p in passengers:
            balance[p] = balance.get(p,0) - tripcost/npers
    return balance

def export_as_html(lastevents, balance, htmltemplate='./web/index_templ.html', htmlfile='./web/index.html'):
    """
    Given normalized ICS input (driver, passengers, departure location, 
    start time), export results to HTML report for human review.
    """
    env = Environment(
        loader=FileSystemLoader('./'),
        autoescape=False
    )
    # select_autoescape(['html', 'xml'])

    template = env.get_template(htmltemplate)
    render = template.render(
        lastevents=lastevents,
        balance=balance)
        # activetop10=stats[30]['active']['allday'],
        # stats30daily=stats30daily,
        # stats30alltime=stats30alltime)

    with open(htmlfile, 'w') as fd:
        fd.write(render)

def update_csv(events, csvpath="./calendar.csv"):
    """
    After normalization, append to existing CSV, overwriting old data in csv
    with newer calendar data as follows:
        - All events in CSV older than the oldest event in ICS: keep
        - All events in CSV also in ICS: overwrite
    The rationale is that events might have been deleted in the calendar which
    we cannot detect from the ICS, so we simply overwrite everything from the
    ics.
    """
        
    # Read old file until we get new data
    try:
        with open(csvpath, "rt") as csvfd:
            spamreader = csv.reader(csvfd, delimiter=",", lineterminator = '\n')
            # Read data, use ast.literal_eval to convert stringified list back to Python list
            # https://stackoverflow.com/questions/1894269/convert-string-representation-of-list-to-list
            # TODO: ast.literal_eval could be slow code, maybe optimize later
            csvdata = [[r[0], ast.literal_eval(r[1])] + [r[2], datetime.datetime.strptime(r[3], "%Y-%m-%d %H:%M:%S%z")]
                for r in spamreader 
                if datetime.datetime.strptime(r[3], "%Y-%m-%d %H:%M:%S%z") < events[0][3]]
            # Prepend existing events to new data
            events = csvdata + events
    except FileNotFoundError:
        pass
    

    # Re-open file, truncate, write all data
    with open(csvpath, "w") as csvfd:
        spamwriter = csv.writer(csvfd, delimiter=",", lineterminator = '\n')
        spamwriter.writerows(events)

    return events

def find_dest(lastevents):
    """
    Given normalized ICS input (driver, passengers, departure location, 
    start time), find matching destination location by checking what is the 
    departure location of the next trip by the same driver.
    
    Typically a driver departs from location X in the morning, then departs
    from locaiton Y in the afternoon, meaning the trip was X->Y and Y->X.

    Plan:
    1.sort all events by date and add a unique ID (index nr)
    2.loop over events per day
    2a.what to do with first pm event? -> ideas for dbs storage
    3.Every day should contain even number of events (back/forth)
    4.find all the unique drivers and match location of events via driver
    5.link source/dest via added ID to the event
    
    """
    sorted_events =  sorted(lastevents, key=lambda event: event[3])
    number_days = sorted_events[-1][3] - sorted_events[0][3]
    number_days = number_days.days +2
    day_list = [sorted_events[0][3].date()-datetime.timedelta(days=1) + datetime.timedelta(days=x)
                for x in range(number_days)]
    #need to add unique tag to events in order to find them back later
    sorted_events = list(zip(sorted_events, range(len(sorted_events))))
    start_dest_pairs = []
    
    for day in day_list:
        events_on_day = [e for e in sorted_events if e[0][3].date() == day]
        drivers = set([event[0][0] for event in events_on_day])
        #Assume a driver only goes back/forth once a day
        for driver in drivers:
            carpool_set = [event for event in events_on_day if event[0][0]==driver]
            if len(carpool_set)==2:
                #most common back/forth
                startID, destID = carpool_set[0][1], carpool_set[1][1]
                start, dest = carpool_set[0][0][2], carpool_set[1][0][2]
                start_dest_pairs.append([startID, [start,dest]])
                start_dest_pairs.append([destID, [dest,start]])
            elif len(carpool_set)>2:
                #driver has logged >2 rides, not possible -> needs fix
                print(f'Driver {driver} more then 2 events on {day}')
                print(carpool_set)
            elif len(carpool_set)==1:
                #only one ride/day:
                #1. sloppy registration - send request to driver for fix?
                #2. only 1 ride was shared -> have to make assumptions on start/destination based on driver+passager
                print(f'Driver {driver} one event on {day}')
                print(carpool_set)
                                
    sorted_events = [list(event[0]) for event in sorted_events] # remove the IDs again and make mutable
    
    if len(start_dest_pairs) == len(sorted_events):
        print('All rides found!')
    else:
        print('{} missing destinations'.format(len(sorted_events)-len(start_dest_pairs)))
        #print([ID[0] for ID in start_dest_pairs])
        
    for ID, [start, dest] in start_dest_pairs:
        sorted_events[ID].append([start, dest])

    return sorted_events

# Parse commandline arguments
parser = argparse.ArgumentParser(description="Do carpool balance acocunting on properly-formatted calendar events (ics) using a csv file as intermediate cache for items no longer in calendar")
parser.add_argument("calfile", help="Calendar file to parse")
parser.add_argument("csvfile", help="CSV file to use as cache")
parser.add_argument("--htmltemplate", help="HTML template to use for export")
parser.add_argument("--htmlfile", help="HTML file to export template to")
# args = parser.parse_args()

##lastevents = normalize_ics(args.calfile)
# allevents = update_csv(lastevents, args.csvfile)
# balance = carpool_account(allevents)
# export_as_html(lastevents, balance, htmltemplate=args.htmltemplate, htmlfile=args.htmlfile)

# Interactive use with YAML file:
#lastevents = normalize_ics(calfile)
#lastevents = find_dest(lastevents)
#carpool_account_distance(lastevents)


def storedata(obj, file='./sample/calendar-anon2.json'):
    """
    Store dict of carpool data, convert datetime to string for 
    json compatibility
    """
    with open(file, 'w') as fd:
        json.dump({str(k):v for k,v in obj.items()}, fd, indent=1)

def loaddata(file):
    """
    Load carpool data json, convert str back to datetime
    """
    with open(file, 'r') as fd:
        events = json.load(fd)
    return OrderedDict({datetime.datetime.fromisoformat(k):v for k,v in events.items()})

print ("storedata")
print(events)
storedata(events, './sample/calendar-anon2.json')
print ("loaddata")
e = loaddata('./sample/calendar-anon2.json')
print(e == events)