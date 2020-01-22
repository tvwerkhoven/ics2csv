from icalendar import Calendar, Event
import re, string

validlocs = ['nieuwegein', 'houten', 'everdingen', 'rietsuiker', 'driebergen']

with open('calendar.ics','rb') as g:
	gcal = Calendar.from_ical(g.read())
	for component in gcal.walk():
	    # Only look at events that are not cancelled, TRANSP:TRANSPARENT is cancelled
	    if component.name == 'VEVENT' and component.get('STATUS') is not "TRANSPARENT":
	    	# https://stackoverflow.com/questions/1276764/stripping-everything-but-alphanumeric-chars-from-a-string-in-python
	    	pattern = re.compile('[^\w ]+',re.UNICODE)
	    	names = pattern.sub('', component.get('SUMMARY')).split()
	    	driver = names[1]
	    	passengers = names[2:]
	    	# print(component.get('SUMMARY'))

	    	# Find location
	    	loc = component.get('LOCATION').lower()
	    	realloc = 'unknown'
	    	for v in validlocs:
	    		if v in loc:
	    			realloc = v
	    			break
	    	print("D: {}, P: {}, loc: {}".format(driver, ",".join(passengers), loc +'-'+realloc))

	    	print(component.get('DTSTART').dt.ctime())

	    	break
	    	# TRANSP:TRANSPARENT is cancelled
    # for i in component.walk():
    # 	print( i)
# g.close()