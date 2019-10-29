import dateparser
import json
import os
import sys
from configparser import ConfigParser, NoSectionError
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from msiempy.alarm import AlarmManager
from msiempy.event import EventManager, FieldFilter
from msiempy.device import DevTree

def monitor_alarms(window='LAST_HOUR', threshold=60):
    """Query for ESM alarms and check against the given time threshold.
    
    Arguments:
        window (str): Time window to query for alarms in ESM time format.
        threshold (int): Number of minutes not seeing an alarm before action.

    """
    try:
        latest_alarm = AlarmManager(time_range=window, page_size=1).load_data()[0]
    except IndexError:
        print('No alarms found for time window: {}'.format(window))
        return False

    idle_time = calc_idle_time(threshold)
    alarm_time = convert_time(latest_alarm['triggeredDate'])
    td = idle_time - alarm_time 
    delta_minutes = int(td.total_seconds() / 60)
    if idle_time < alarm_time:
        mesg = ('The ESM has not generated an alarm for {} minutes. The threshold is '
                'set to {} minutes and the last alarm was generated at: {}. Please '
                'investigate!\n'
                .format(delta_minutes, threshold, alarm_time))
        print(mesg)
        return mesg
    else:
        print(' - Alarms are within the threshold of {} minutes. Timestamp for last alarm: {}'
                .format(threshold, alarm_time))

def monitor_queries(qconf, window='LAST_HOUR'):
    """Runs a query for each of the datasource IDs
    
    Arguments:
        qconf (list of tuples): datasource_id,threshold
        datasource_id can be retrieved via get_devices()
    """
    for q in qconf:
        ds_id = q[0]
        ds_name = device_name_from_id(ds_id)
        print('Checking device: {}...'.format(ds_name))
        threshold = q[1]
        idle_time = calc_idle_time(threshold)
        last_time = convert_time(get_events(ds_id, window=window)['Alert.LastTime'])
        td = idle_time - last_time 
        delta_minutes = int(td.total_seconds() / 60)
        if idle_time < last_time:
            mesg = ('Device: {} has not received an event for {} minutes. The threshold is '
                    'set to {} minutes and the last event was generated at: {}. Please '
                    'investigate!\n'
                    .format(ds_name, delta_minutes, threshold, last_time))
            print(mesg)
            return mesg
        else:
            print('Device: - {} is within the event threshold of {} minutes. Timestamp for last event: {}'
                    .format(ds_name, threshold, last_time))

def get_events(ds_id, window='LAST_HOUR'):
    """Returns most recent event for the given datasource ID
    
    Arguments:
        ds_id (str) -- datasource ID, aka IPSID 
    
    Keyword Arguments:
        window (str) -- time window to query data in minutes
                 (default: {'LAST_HOUR'})
    """
    # Adding mask to datasource ID. ERCs use /8.
    ds_id = ds_id + '/8'
    events = EventManager(
            time_range=window,
            fields=['HostID', 'UserIDSrc'],
            filters=[FieldFilter('IPSID', ds_id, operator='EQUALS') ],
            limit=1,
            max_query_depth=2)
    events.load_data()

    return events[0]

def get_rec_ids():
    """Gets names and datasource IDs for all the Receivers.
    
    Returns:
        list of dicts -- name:id format
    """
    dt = build_devtree()
    return [(dev['name'], dev['ds_id']) for dev in dt if dev['desc_id'] == '2']

def device_name_from_id(device_id):
    """Returns device name for given device id"""
    dt = build_devtree()
    for d in dt:
        if d['ds_id'] == device_id:
            return d['name']

def calc_idle_time(minutes):
    minutes = timedelta(minutes=int(minutes))
    return datetime.now() - minutes

def convert_time(timestamp):
    return dateparser.parse(timestamp)

@lru_cache(maxsize=None)
def build_devtree():
    return DevTree()

def build_default_config():
    filename = 'healthmon.ini'
    c = ConfigParser(allow_no_value=True)
    print('Building default config...')
    c.add_section('healthmon')
    c.set('healthmon', '# Enable the monitoring of ESM Alarms: true or false')
    c.set('healthmon', 'monitor_alarms', 'true')
    c.set('healthmon', '# Time range to check queries. Must be ESM timeframe.')
    c.set('healthmon', 'alarm_window', 'LAST_HOUR')
    c.set('healthmon', '# Threshold is the max minutes an alarm has not fired before taking action.')
    c.set('healthmon', 'alarm_threshold', '30')
    c.set('healthmon', '#')
    c.set('healthmon', '# Enable the monitoring of event times: true or false')
    c.set('healthmon', 'monitor_queries', 'true')
    c.set('healthmon', 'event_window', 'LAST_HOUR')    
    c.set('healthmon', '# Format: query_<name> = <device_id>,<threshold>')
    c.set('healthmon', '# The key needs to start with "query"')
    c.set('healthmon', '# The threshold is the max age of events in minutes before taking action.')
    recs = get_rec_ids()
    for r in recs:
        key = 'query_' + r[0].lower().replace(' ', '_')
        val = r[1] + ',20'
        c.set('healthmon', key, val)
    if Path('healthmon.ini').is_file():
        prompt = input('The file healthmon.ini already exists. Overwrite? (y/n)')
        if prompt.lower().startswith('y'):
            with open(filename, 'w') as f:
                c.write(f)
            print('Config file written to: {}'.format(filename))
    sys.exit()

def get_dev_ids():
    """Returns list of tuples with format datasource (name, id)"""
    dt = build_devtree()
    return [(dev['name'], dev['ds_id']) for dev in dt]

def usage():
    print("""Usage: python healthmon.py 
    to run configured ESM checks.

python healthmon.py config
    to run config builder and create default config

python healthmon.py device_ids
    print a list datasource names and IDs

python healthmon.py help
    print this message
            """)
    sys.exit()

def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == 'config':
            build_default_config()
        if sys.argv[1] == 'device_ids':
            for device in get_dev_ids():
                print(device)
            sys.exit()
        helpwords = ['help', '-help', '-h', '--help']
        if sys.argv[1] in helpwords:
            usage()

    filename = 'healthmon.ini'
    section = 'healthmon'
    c = ConfigParser()
    c.read(filename)
    if not c.has_section(section):
        print('Error: [{}] section required in ini file.').format(section)
        sys.exit()
    print('Starting ESM Health Check. Current time: {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    if c.get(section, 'monitor_alarms').lower().startswith('t'):
        print('Checking alarms...')
        window = c.get(section, 'alarm_window')
        alarm_threshold = c.get(section, 'alarm_threshold')
        mesg = monitor_alarms(window=window, threshold=alarm_threshold)

    if c.get(section, 'monitor_queries').lower().startswith('t'):
        print('Checking query times...')
        window = c.get(section, 'event_window')
        queries = [(v.split(',')[0], v.split(',')[1])
                    for k, v in c[section].items() if k.startswith('query')]
        mesg = monitor_queries(queries, window=window)
    
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Control-C Pressed, stopping...")
        sys.exit()
    