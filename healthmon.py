import dateparser
import json
import logging
import os
import sys
from configparser import ConfigParser, NoSectionError
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import pytz

from msiempy.alarm import AlarmManager
from msiempy.event import EventManager, FieldFilter
from msiempy.device import DevTree, ESM
from nitro_timezones import nitro_tz


class HealthMon(object):
#    def __init__(self, args):
#        self.esm_time = args.get('current_time') or datetime.now()
#        self.monitor_esm(args)

    def monitor_esm(self, args):
        """Query for ESM alarms and check against the given time threshold.
        
        Arguments:
            window (str): Time window to query for alarms in ESM time format.
            threshold (int): Number of minutes not seeing an alarm before action.

        """
        self.esm_time = args.get('current_time') or datetime.now()
        
        if args.get('correlationID') == 'ALARMS':
            data = AlarmManager(time_range=args['window'], page_size=1).load_data()
        elif args.get('correlationID') == 'EVENTS':
            data = self.get_events(args['ds_id'], window=args['window'])

        try:
            args['last_time'] = self.convert_time(data[0]['Alert.LastTime'])
        except (IndexError, KeyError):
            try:
                args['last_time'] = self.convert_time(data[0]['triggeredDate'])

            except (IndexError, KeyError):
                args['delta_minutes'] = args['window']
                args['last_time'] = 'unknown'

        if not args.get('delta_minutes'):
            args = self.check_threshold(args)
        
        if args.get('delta_minutes'):
            args['shortDescription'] = 'McAfee ESM {correlationID} latest time outside of Threshold'.format(**args)
            args['description'] = self.fail_mesg(args)
        else:
            args['shortDescription'] = 'McAfee ESM {correlationID} latest time within Threshold'.format(**args)
            args['description'] = self.success_mesg(args)
        return args

    def check_threshold(self, args):
        threshold = int(args['threshold'])
        args['threshold'] = str(threshold) + ' minutes'
        args['then'] = self.calc_idle_time(threshold)
        args['last_time'] = args['user_tz'].localize(args['last_time'])
        td = args['then'] - args['last_time']
        args['delta_minutes'] = str(int(td.total_seconds() / 60)) + ' minutes'
        if args['then'] > args['last_time']:
            args['SEND_ALARM'] = True
        return args

    def fail_mesg(self, args):
            return ('Device: {deviceName} has not seen {correlationID} for: {delta_minutes}. The threshold is '
                    'set to: {threshold} and the last activity was generated at: {last_time}.'
                    .format(**args))

    def success_mesg(self, args):
        return ('--> {correlationID} within the threshold timme of {threshold}. '
                    'Latest timestamp is: {last_time}'.format(**args))


    def get_events(self, ds_id, window='LAST_HOUR'):
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
                order=('ASCENDING', 'LastTime'),
                filters=[FieldFilter('IPSID', ds_id, operator='EQUALS') ],
                limit=1,
                max_query_depth=1)
        events.load_data()
        return events

    def get_rec_ids(self):
        """Gets names and datasource IDs for all the Receivers.
        
        Returns:
            list of dicts -- name:id format
        """
        dt = self.build_devtree()
        return [(dev['name'], dev['ds_id']) for dev in dt if dev['desc_id'] in ['2','13']]

    def device_name_from_id(self, device_id):
        """Returns device name for given device id"""
        dt = self.build_devtree()
        for d in dt:
            if d['ds_id'] == device_id:
                return d['name']

    def calc_idle_time(self, minutes):
        minutes = timedelta(minutes=int(minutes))
        return self.esm_time - minutes

    @staticmethod
    def convert_time(timestamp):
        return dateparser.parse(timestamp)

    def get_dev_ids(self):
        """Returns list of tuples with format datasource (name, id)"""
        dt = self.build_devtree()
        return [(dev['name'], dev['ds_id']) for dev in dt]

    @lru_cache(maxsize=None)
    def build_devtree(self):
        return DevTree()
        
    def build_default_config(self):
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
        recs = self.get_rec_ids()
        if not recs:
            print('It appears this ESM does not have any Receivers. Query config will be disabled.')
            c.set('healthmon', 'monitor_queries', 'false')
        else:
            for r in recs:
                key = 'query_' + r[0].lower().replace(' ', '_')
                val = r[1] + ',20'
                c.set('healthmon', key, val)

        if Path(filename).is_file():
            prompt = input('The file healthmon.ini already exists. Overwrite? (y/n)')
            if prompt.lower().startswith('y'):
                self.write_file(filename, c)
        else:
            self.write_file(filename, c)

    def write_file(self, filename, data):
        with open(filename, 'w') as f:
            data.write(f)
        print('Config file written to: {}'.format(filename))

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
    handler = logging.FileHandler('esm_health.log')
    log_format = logging.Formatter('%(message)s')
    handler.setFormatter(log_format)
    logger.addHandler(handler)
    return logger

def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == 'config':
            hm = HealthMon()
            hm.build_default_config()
            sys.exit()
        if sys.argv[1] == 'device_ids':
            hm = HealthMon()
            for device in hm.get_dev_ids():
                print(device)
            sys.exit()
        helpwords = ['help', '-help', '-h', '--help']
        if sys.argv[1] in helpwords:
            usage()


    filename = 'healthmon.ini'
    if not Path(filename).is_file():
        print('Error: {} not found.'.format(filename))
        print('Run "python healthmon.py config" to create one.')
        sys.exit()

    section = 'healthmon'
    c = ConfigParser()
    c.read(filename)
    if not c.has_section(section):
        print('Error: [{}] section required in ini file.'.format(section))
        sys.exit()

    esm = ESM()
    esm_time = HealthMon.convert_time(esm.time())
    timezones = esm.tz_offsets()
    for tz_id in timezones:
        if tz_id[0] == esm.nitro.user_tz_id:
            iso_tz_id = nitro_tz.get(tz_id[0])
            user_tz = pytz.timezone(iso_tz_id)
            esm_time = esm_time.replace(tzinfo=pytz.utc).astimezone(user_tz)

    print('Starting ESM Health Check. ESM Time: {}'
            .format(esm_time.strftime('%Y-%m-%d %H:%M:%S')))
    
    if c.get(section, 'monitor_alarms').lower().startswith('t'):
        print('Checking alarms...')
        hm = HealthMon()
        args = {}
        args['user_tz'] = user_tz
        args['current_time'] = esm_time
        args['correlationID'] = 'ALARMS'
        args['deviceName'] = 'Primary ESM'
        args['window'] = c.get(section, 'alarm_window')
        args['threshold'] = c.get(section, 'alarm_threshold')
        mesg = hm.monitor_esm(args)
        if args.get('SEND_ALARM'):
            print('ALARM', mesg)
            print('')


    if c.get(section, 'monitor_queries').lower().startswith('t'):
        print('Checking devices...')
        for k, v in c[section].items(): 
            hm = HealthMon()
            args = {}
            args['user_tz'] = user_tz            
            args['current_time'] = esm_time
            args['correlationID'] = 'EVENTS'
            args['window'] = c.get(section, 'event_window'
            )
            if not k.startswith('query'): continue
            args['ds_id'], args['threshold'] = v.split(',')
            args['deviceName'] = hm.device_name_from_id(args['ds_id'])
            print('Checking device: {}'.format(args['deviceName']))
            # Adding mask to datasource ID. ERCs use /8.
            args['ds_id'] = ''.join([args['ds_id'], '/8'])
            mesg = hm.monitor_esm(args)
            if args.get('SEND_ALARM'):
                print('ALARM {} Device time: {} behind Threshold time: {}'.format(mesg['deviceName'], mesg['last_time'], args['then']))
                print('')

if __name__ == "__main__":
    try:
        logger = get_logger()
        main()
    except KeyboardInterrupt:
        print("Control-C Pressed, stopping...")
        sys.exit()
    