import dateparser
import json
import os
import sys
from configparser import ConfigParser, NoSectionError
from datetime import datetime, timedelta
from pathlib import Path

from msiempy.alarm import AlarmManager
from msiempy.event import EventManager
from msiempy.device import DevTree

def monitor_alarms(window='LAST_HOUR', threshold=60):
    """Query for ESM alarms and check against the threshold.
    
    Arguments:
        window (str): Time window to query for alarms in ESM time format.
        threshold (int): Number of minutes not seeing an alarm before action.

    Returns:

    """
    alarms = AlarmManager(time_range=window, page_size=1)
    alarms.load_data()

    alarm_time = dateparser.parse(alarms[0]['triggeredDate'])
    print(alarm_time)



def main():
    filename = 'healthmon.ini'
    section = 'healthmon'
    c = ConfigParser()
    c.read(filename)
    if not c.has_section(section):
        print('Error: [{}] section required in ini file.').format(section)
        sys.exit()
    print('Starting Health Check...')

    if c.get(section, 'monitor_alarms'):
        print('Checking alarms...')
        query_time = c.get(section, 'alarm_query_window') or 'LAST_HOUR'
        alarm_threshold = c.get(section, 'alarm_threshold') or 60
        print(query_time, alarm_threshold)
        monitor_alarms(window=query_time, threshold=alarm_threshold)

    if c.get(section, 'monitor_queries'):
        print('Checking query times...')
        queries = {k: v for k, v in c[section].items() if k.startswith('query')}
        print(queries)

    if c.get(section, 'monitor_datasources'):
        print('Checking datasources...')
        ds = {k: v for k, v in c[section].items() if k.startswith('ds')}
        print(ds)

    
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Control-C Pressed, stopping...")
        sys.exit()
    