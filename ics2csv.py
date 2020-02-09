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
    'origin': '<carpool departure location>',
    'destination': '<calculated destination location>'
    }

<date> : {'type': 'transfer', 
    'creditor': '<person>', 
    'debtor': '<person>', 
    'amount': '<transfer amount in EUR>'
    }

"""

import argparse
from icalendar import Calendar
import re
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
import json
import datetime
from collections import OrderedDict

# Load config to parse data
config = yaml.safe_load(open(r"./sample/carpool-anon.yaml"))
CFG_CALFILE = config['calfile']
CFG_TRIPCOST = 16
CFG_VALIDAMLOCS = config['validamlocs']
CFG_VALIDPMLOCS = config['validpmlocs']
CFG_DEFAULTAMLOC = "UNKNOWN-EVERDINGEN"
CFG_DEFAULTPMLOC = "UNKNOWN-B7"

def normalize_ics(file='calendar.ics'):
    """
    Given ICS file, normalize for carpool accounting to fixed set of drivers, 
    times, locations.
    """
    events = OrderedDict()

    with open(file,'rb') as g:
        gcal = Calendar.from_ical(g.read())
        for c in gcal.walk():
            # Only look at events (name == 'VEVENT') that are not cancelled (STATUS != 'TRANSPARENT')
            # Get people from SUMMARY, get valid location from LOCATION/DTSTART
            if (c.name == 'VEVENT' and c.get('TRANSP') != 'TRANSPARENT'):
                events[c.get('DTSTART').dt] = icsparse_event(c)

    return events

# Regexps to use for splitting topics. Define global to allow re-use.
RE_TOPIC_SPLIT_CARPOOL = re.compile('[^a-zA-Z]+')
RE_TOPIC_SPLIT_TRANSFER = re.compile('[\W]+')

def icsparse_event(c):
    """
    Parse single calendar event
    """
    summary, location, time = c.get('SUMMARY'), c.get('LOCATION'), c.get('DTSTART')

    # Look for carpool match in first word
    event_type = summary.split()[0].lower()
    if ('carpool' in event_type):
        try:
            words = icsparse_event_topic_split(summary, RE_TOPIC_SPLIT_CARPOOL)
            driver, passengers = words[1], words[2:]
        except Exception as e:
            raise ValueError("Carpool event syntax not understood: {}".format(e))

        origin = icsparse_event_get_location(location, time)
        return {'type': 'carpool',
                'driver': driver,
                'passengers': passengers,
                'origin': origin,
                'tripcost': CFG_TRIPCOST}
    
    elif ('transfer' in event_type):
        try:
            words = icsparse_event_topic_split(summary, RE_TOPIC_SPLIT_TRANSFER)
            debtor, creditor, amount = words[1:]
        except:
            raise ValueError("Transfer event syntax not understood: {}".format(summary))
        return {'type': 'transfer',
                'debtor': debtor,
                'creditor': creditor,
                'amount': amount}
    else:
        raise ValueError("Event syntax not understood: {}".format(summary))

def icsparse_event_topic_split(topic, resplit):
    """
    From event topic (summary), split in words, e.g. to get driver and 
    passenger. Generalized (via resplit) to also work for other syntaxes.
    
    Expected carpool syntax:
        'carpool([\W]+([\w]+))+'
    e.g.
        'Carpool - Peter + Martin + Wolfgang   '
        'carpool Peter    Martin Wolfgang'
        'carpool Peter, Martin, Wolfgang  
        'carpool Peter + Martin + Wolfgang +1' (+1 is dropped in accounting, guests are free)
        'helloworld Peter+++Martin_,8123,,---Wolfgang'

    Not OK:
        Peter Martin Wolfgang (lacks Carpool magic word)
        carpool PeterMartinWolfgang (cannot split names)
        carpool Peter, Martin Wu, Wolfgang (names must be one word only)
        carpool - Peter, Bart-Jan (names must be only alphanumeric, all other tokens are used as separator)
    """

    # Regexp pattern to strip non-alphanumeric characters
    # https://stackoverflow.com/questions/1276764/stripping-everything-but-alphanumeric-chars-from-a-string-in-python
    # Split topic by non-alphanumeric characters - https://docs.python.org/2/library/re.html
    words = resplit.split(topic.lower(), re.UNICODE)

    # Remove empty hits in case string ends in non-alphanumeric char (e.g. 
    # space). Alternatively we could strip() the string using all 
    # non-alphanumeric charactere, but another regexp is probably slower
    # See also https://docs.python.org/3.5/library/re.html#re.split
    words = list(filter(None, words))

    # Return flat list of words. Split into driver/passengers or 
    # debtor/creditor elsewhere.
    return words

def icsparse_event_get_location(location, time):
    """
    From event location string, get validated carpool location
    """
    # Depending on time, we assume different locations
    if time.dt.hour < 12:
        validlocs = CFG_VALIDAMLOCS
        locdefault = CFG_DEFAULTAMLOC
    else:
        validlocs = CFG_VALIDPMLOCS
        locdefault = CFG_DEFAULTPMLOC

    # For each valid location, check if it's found in the actual location string
    loc = location.lower()
    for v in validlocs:
        if v in loc:
            # If valid location found, return immediately, we only accept 
            # one location match
            return v
    # If nothing found, return default location
    return locdefault

def carpool_account(allevents):
    """
    Given normalized ICS input, calculate account balance over time.

    For event type 'carpool', distribute tripcost equally over driver and passengers
    For event type 'transfer', transfer credit from debtor to creditor
    """
    balance = {}

    for k,v in allevents.items():
        if v['type'] == 'carpool':
            npers = 1 + len(v['passengers'])
            balance[v['driver']] = balance.get(v['driver'],0) + v['tripcost'] - v['tripcost']/npers
            for p in v['passengers']:
                balance[p] = balance.get(p,0) - v['tripcost']/npers
        if v['type'] == 'transfer':
            balance[v['creditor']] = balance.get(v['creditor'], 0) + v['amount']
            balance[v['debtor']] = balance.get(v['debtor'], 0) - v['amount']

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

def storedata(obj, file='./sample/calendar-anon.json'):
    """
    Store dict of carpool data, convert datetime to string for 
    json compatibility.
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

def updatedata(newevents, file='./sample/calendar-anon.json', maxage=30):
    """
    Given a dict of (possibly new) events, append to (possibly existing) JSON,
    overwriting old data as follows:
        - All events in file older than maxage days: keep
        - All events in file also in ICS: overwrite
    The rationale is that events might have been deleted in the calendar which
    we cannot detect from the ICS, so we simply overwrite everything from the
    ICS.
    """

    # @TODO set maxage to max(oldest event in events, maxage) in case events is very new

    allevents = OrderedDict()
    try:
        with open(file, "rt") as fd:
            e = json.load(fd)
            # Select only events older than 30d. Do not use time in comparison 
            # to ensure we only cut-off on whole days, else we could get 
            # partial data for one day
            n = datetime.date.today()
            for k,v in e.items():
                edate = datetime.datetime.fromisoformat(k)
                if ((n-edate.date()).days > maxage):
                    allevents[edate] = v

        # Now add back new events
        for k,v in newevents.items():
            if ((n-k.date()).days <= maxage):
                allevents[k] = v
    except FileNotFoundError:
        allevents = newevents
        pass

    # Re-open file, truncate, write all data
    storedata(allevents, file)

    return allevents


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
parser.add_argument("--calfile", help="Calendar file to parse", default=(CFG_CALFILE or None))
# parser.add_argument("csvfile", help="CSV file to use as cache")
parser.add_argument("--htmltemplate", help="HTML template to use for export")
parser.add_argument("--htmlfile", help="HTML file to export template to")
args = parser.parse_args()

newevents = normalize_ics(args.calfile)
allevents = updatedata(newevents)
balance = carpool_account(allevents)

# export_as_html(lastevents, balance, htmltemplate=args.htmltemplate, htmlfile=args.htmlfile)

# Interactive use with YAML file:
#lastevents = normalize_ics(calfile)
#lastevents = find_dest(lastevents)
#carpool_account_distance(lastevents)
