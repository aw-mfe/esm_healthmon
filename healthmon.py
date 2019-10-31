import dateparser
import json
import logging
import os
import sys
from configparser import ConfigParser, NoSectionError
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from msiempy.alarm import AlarmManager
from msiempy.event import EventManager, FieldFilter
from msiempy.device import DevTree



def monitor_esm(args):
    """Query for ESM alarms and check against the given time threshold.
    
    Arguments:
        window (str): Time window to query for alarms in ESM time format.
        threshold (int): Number of minutes not seeing an alarm before action.

    """
    if args.get('correlationID') == 'ALARMS':
        data = AlarmManager(time_range=args['window'], page_size=1).load_data()
    elif args.get('correlationID') == 'EVENTS':
        data = get_events(args['ds_id'], window=args['window'])

    try:
        args['last_time'] = convert_time(data[0]['Alert.LastTime'])
    except (IndexError, KeyError):
        print('Exception. Now checking Alarm Last time')
        try:
            args['last_time'] = convert_time(data[0]['triggeredDate'])
        except (IndexError, KeyError):
            args['delta_minutes'] = args['window']
            args['last_time'] = 'unknown'

    if not args.get('delta_minutes'):
        args = check_threshold(args)
    
    if args.get('delta_minutes'):
        args['shortDescription'] = 'McAfee ESM {correlationID} latest time outside of Threshold'.format(**args)
        args['description'] = fail_mesg(args)
    else:
        args['shortDescription'] = 'McAfee ESM {correlationID} latest time within Threshold'.format(**args)
        args['description'] = success_mesg(args)
    return args

def check_threshold(args):
    threshold = int(args['threshold'])
    args['threshold'] = str(threshold) + ' minutes'
    idle_time = calc_idle_time(threshold)
    td = idle_time - args['last_time']
    if idle_time < args['last_time']:
 #       print('')
#        print('idle', idle_time, '<' 'last', args['last_time'], 'idle-last=', idle_time - args['last_time'])
        print('')
    if idle_time > args['last_time']:
  #      print('')        
  #      print('idle', idle_time, '<' 'last', args['last_time'], 'idle-last=', idle_time - args['last_time'])
        print('')        
        args['delta_minutes'] = str(int(td.total_seconds() / 60)) + ' minutes'
    return args

def fail_mesg(args):
        return ('Device: {deviceName} has not seen {correlationID} for: {delta_minutes}. The threshold is '
                'set to: {threshold} and the last activity was generated at: {last_time}.'
                .format(**args))

def get_log(args):
        return 

def success_mesg(args):
    return ('--> {correlationID} within the threshold timme of {threshold}. '
                'Latest timestamp is: {last_time}'.format(**args))


def get_events(ds_id, window='LAST_HOUR'):
    """Returns most recent event for the given datasource ID
    
    Arguments:
        ds_id (str) -- datasource ID, aka IPSID 
    
    Keyword Arguments:
        window (str) -- time window to query data in minutes
                 (default: {'LAST_HOUR'})
    """
    events = EventManager(
            time_range=window,
            fields=['HostID', 'UserIDSrc'],
            order=('DESCENDING', 'LastTime'),
            filters=[FieldFilter('IPSID', ds_id, operator='EQUALS') ],
            limit=1000,
            max_query_depth=2)
    events.load_data()

    return events

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

def get_logger():
    logger = logging.getLogger('main')
    logger.setLevel(logging.ERROR)
    handler = logging.FileHandler('esm_heath.log')
    log_format = logging.Formatter('%(message)s')
    handler.setFormatter(log_format)
    logger.addHandler(handler)
    return logger

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
    if not Path(filename).is_file():
        print('Error: {} not found.'.format(filename))
        sys.exit()

    section = 'healthmon'
    c = ConfigParser()
    c.read(filename)
    if not c.has_section(section):
        print('Error: [{}] section required in ini file.'.format(section))
        sys.exit()

    print('Starting ESM Health Check. Current time: {}'
            .format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    

    if c.get(section, 'monitor_alarms').lower().startswith('t'):
        args = {}
        print('Checking alarms...')
        args['correlationID'] = 'ALARMS'
        args['deviceName'] = 'Primary ESM'
        args['window'] = c.get(section, 'alarm_window')
        args['threshold'] = c.get(section, 'alarm_threshold')
        mesg = monitor_esm(args)
        print('LOG', mesg)

    if c.get(section, 'monitor_queries').lower().startswith('t'):

        print('Checking devices...')

        for k, v in c[section].items(): 
            args = {}
            args['correlationID'] = 'EVENTS'
            args['window'] = c.get(section, 'event_window')
            if not k.startswith('query'): continue
            args['ds_id'], args['threshold'] = v.split(',')
            args['deviceName'] = device_name_from_id(args['ds_id'])
            # Adding mask to datasource ID. ERCs use /8.
            args['ds_id'] = ''.join([args['ds_id'], '/8'])
            mesg = monitor_esm(args)
            print('LOG', mesg['deviceName'], mesg['last_time'], datetime.now())
    

if __name__ == "__main__":
    try:
        logger = get_logger()
        main()
    except KeyboardInterrupt:
        print("Control-C Pressed, stopping...")
        sys.exit()
    