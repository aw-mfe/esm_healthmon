# ESM_Healthmon

## Introduction


ESM_Healthmon monitors ESM alarm and device operations by checking timestamps against defined thresholds. 

Background: The ESM has more robust health monitoring capabilities than ever, however, ESM_Healthmon came about after a unique situation where an ESM was unable to generate alerts due to the state it was in. This created the question "what could be implemented easily as a backup notification system when normal health notifications aren't occurring?". ESM_Healthmon addresses this by monitoring alarm and event timestamps.

## Alarms

Use Case: Your SOC is alarm driven. You've created a workflow that relies upon alarms firing and kicking off other actions. Alarms fire at a regular cadence and if that stopped it would indicate a problem. How can you quickly know if the alarms stop firing? 

## Events

Use Case: You have critical Receivers that you need to continously ensure are operating properly. One of them starts to become backlogged with events due to an EPS surge. The events continue to flow but the timestamps begin to slip further behind. How can you detect this fast enough to react in real time? 

## Operation

As mentioned, the ESM has health monitoring capabilities which have become further enhanced in 11.3.1 and later versions. ESM_Healthmon functionality is redundant with what the ESM already provides and should only be implemented in a scenario where the ESM alarms have already been enabled as the primary method of monitoring ESM health. 

ESM_Healthmon is meant to be run as a cron job/scheduled task at a regular interval. At each interval, it will query for a list of triggered alarms, check the timestamp on the most recent and ensure that it is within the configured time threshold for inactivity. This is equivalent to manually clicking on the alarms view in the ESM every 30 minutes and making sure an alarm has fired since last checked.

At each interval ESM_Healthmon will also query the ESM for the most recent events, check the timestamp and ensure that it is within the configured time threshold for inactivity. This is equivalent to using a View that showed the Last Time field and clicking on each Receiver in the Device Tree, looking at the most recent event, and making sure it's not older than expected. 

When ESM_Healthmon finds a timestamp outside of the threshold, it will output a message saying so. It is designed to be extended progmatically though, so from a python perspective, when the script runs, either a message is returned with a description of the problem or None is returned. In one implementation, if output is detected from the checks then that is passed to a script that inserts it into a ticketing system. 

## The Warning

As is the case with any automated activity against the ESM, there is a risk of overloading it and impacting operations. As mentioned, this script provides redundant monitoring to what already exists on the ESM and generally isn't needed.

At installation, the config file will be initialized with all of the Receivers listed. All of the Receivers probably don't need to be monitored so you will need to edit the healthmon.ini file and remove low traffic/priority Receivers.

If you have 40 Receivers and running this script at a 10 minute interval this will probably break something. If you can avoid adding the extra load of querying the database just to ensure things are working it's highly recommended. Set the intervals to as long as you can and only use this in corner cases.

ESM_Healthmon is not supported by McAfee so do be careful. 

## Installation

Python 3.5+ is required.

Download the files manually or:

```python
git clone https://github.com/andywalden/esm_healthmon
```
Best practice to use a virtual environment:

```python
cd esm_healthmon
virtualenv -ppython3 env
source env/bin/activate or env\Scripts\Activate.bat
pip install -r requirements.txt
```

One of the requirements is msiempy. It needs to be configured to talk to the ESM. To input host and credentials run:
python msiempy_setup.py 

After msiempy is configured ESM_Healthmon must be configured. To create an initial config file run:
python healthmon.py config

This creates the healthmon.ini file in the same directory. The generated config provides a template to customize to your use case. It includes options for the query windows and an entry for each Receiver device ID.


## Tuning

There are two config files used. The first is for msiempy and can be found in your home directory (~ or %APPDATA%) in .msiempy/conf.ini. Settings in this file include the ESM ip/hostname and credentials. The password is only obfuscated with base64 encoding so the file must be kept secure. There is a 'quiet' option that can be enabled to disable to loading bars displayed during queries that you may want to enable. See the [msiempy documentation](https://mfesiem.github.io/docs/msiempy/index.html#msiempy.NitroConfig) for more details.

The second config file is the heathmon.ini file in the local directory. For tuning, make sure that the alarm_window is appropriate for your environment. Also remove any non-critical query_<Receiver> lines to reduce the query activity. 


## TODO

 - Detailed Reference