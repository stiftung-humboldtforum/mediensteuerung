import logging
import os

# Configurable, not hardcoded (KALENDER-REDESIGN.md §1 A1); zoneinfo needs the
# tzdata package on slim images.
SCHEDULE_TZ = os.getenv('SCHEDULE_TZ', 'Europe/Berlin')

logger = logging.getLogger()
FORMAT = '%(asctime)s.%(msecs)03d:%(levelname)s:%(filename)s:%(lineno)s:%(funcName)s %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT,
                    datefmt='%y-%m-%d %H:%M:%S')
