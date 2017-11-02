from datetime import datetime, timedelta, timezone
from decimal import Decimal
from getpass import getpass
from json import load as json_load
from logging import FileHandler, Formatter, StreamHandler, getLogger
from os import environ
from os.path import join
from sys import exit
from time import sleep

from requests.exceptions import ConnectionError
from utilities.passcode import AESCipher

from bittrex.bittrex2 import Bittrex
from sql.sql import Database
from utilities.credentials import get_credentials


# ==============================================================================
# Functions
# ==============================================================================

def format_time(datetime_to_format, time_format="%Y-%m-%d %H:%M:%S.%f"):
    """
    Format datetime to string.
    Ex: 2017-09-22 12:28:22
    :return:
    """
    return datetime_to_format.strftime(time_format)


def convert_bittrex_timestamp_to_datetime(timestamp, time_format="%Y-%m-%dT%H:%M:%S.%f"):
    try:
        converted_datetime = datetime.strptime(timestamp, time_format)
    except ValueError:
        converted_datetime = datetime.strptime('{}.0'.format(timestamp), time_format)

    return converted_datetime


def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


def filter_bittrex_markets(markets, base_coin):
    """
    Filter all Bittrex markets using a base currency.
    :param markets: All bittrex markets
    :param base_coin: Base currency
    :return: (list)
    """
    return [x.get('MarketName') for x in markets.get('result')
            if x.get('BaseCurrency') == base_coin and x.get('IsActive')]


def format_bittrex_entry(data):
    """
    Format data object (summary per interval) into SQL row format.
    :param data: Summary of market per interval
    :return: (list) tuples
    """

    formatted_entries = []

    formatted_entries.append(('time', data.get('time')))
    formatted_entries.append(('price', data.get('price')))
    formatted_entries.append(('wprice', data.get('wprice')))
    formatted_entries.append(('basevolume', data.get('basevolume')))
    formatted_entries.append(('buyorder', data.get('buyorder')))
    formatted_entries.append(('sellorder', data.get('sellorder')))

    return formatted_entries


def calculate_metrics(data, start_datetime, digits=8):
    """
    Calculate metrics.
    :param data: (list(dict)) Buy/sell orders over an interval
    :param start_datetime: Start of interval
    :param digits: (int) Number of decimal places
    :return:
    """
    decimal_places = Decimal(10) ** (digits * -1)

    volume = 0
    buy_order = 0
    sell_order = 0
    price = 0
    price_volume_weighted = 0
    formatted_time = format_time(utc_to_local(convert_bittrex_timestamp_to_datetime(start_datetime)),
                                 "%Y-%m-%d %H:%M:%S")

    if data and isinstance(data[0], dict):
        p, v, o = map(list, zip(*[(x.get('Price'), x.get('Total'), x.get('OrderType')) for x in data]))

        volume = sum(v)
        buy_order = sum([1 for x in o if x == 'BUY'])
        sell_order = len(o) - buy_order

        price = (sum([Decimal(x).quantize(decimal_places) for x in p]) / len(p)).quantize(decimal_places)
        price_volume_weighted = (sum(
            [Decimal(x).quantize(decimal_places) * Decimal(y) for x, y in zip(p, v)]) / Decimal(sum(v))).quantize(
            decimal_places)

    metrics = {'volume': volume,
               'buy_order': buy_order,
               'sell_order': sell_order,
               'price': price,
               'price_volume_weighted': price_volume_weighted,
               'time': formatted_time}

    return metrics


def get_interval_index(entries, target_datetime, interval):
    """
    Get index of start and stop positions of interval from a list of data entries.
    :param entries: (list(dict))
    :param target_datetime: (datetime) Start of interval
    :param interval: (int) Seconds between data points
    :return:
    """
    timestamp_list = [convert_bittrex_timestamp_to_datetime(x.get('TimeStamp')) for x in entries]

    stop_index = len([x for x in timestamp_list if x > target_datetime])
    start_index = len([x for x in timestamp_list if (x - target_datetime).total_seconds() > interval])

    return start_index, stop_index


# ==============================================================================
# Initialize logger
# ==============================================================================
logger = getLogger('crocket')

logger.setLevel(10)

fh = FileHandler(
    '/var/tmp/crocket.{:%Y:%m:%d:%H:%M:%S}.log'.format(datetime.now()))
fh.setFormatter(Formatter('%(asctime)s:%(name)s:%(levelname)s: %(message)s'))
logger.addHandler(fh)

sh = StreamHandler()
sh.setFormatter(Formatter('%(levelname)s: %(message)s'))
logger.addHandler(sh)

logger.info('Initialized logger.')


# ==============================================================================
# Environment variables
# ==============================================================================

HOME_DIRECTORY_PATH = environ['HOME']
CREDENTIALS_FILE_PATH = join(HOME_DIRECTORY_PATH, '.credentials.json')

BITTREX_CREDENTIALS_PATH = join(HOME_DIRECTORY_PATH, 'bittrex_credentials.json')

HOSTNAME = 'localhost'
DATABASE_NAME = 'BITTREX2'

BASE_COIN = 'BTC'

# Data polling settings

sleep_time = 30 # seconds
interval = 60 # seconds

# ==============================================================================
# Run
# ==============================================================================

logger.debug('Starting CRocket ....................')

# Key to decrypt SQL credentials (username/password) from file
KEY = getpass('Enter decryption key: ')

cipher = AESCipher(KEY)

encrypted_username, encrypted_passcode = \
    map(str.encode, get_credentials(CREDENTIALS_FILE_PATH))

USERNAME = getpass('Enter username: ')

if cipher.decrypt(encrypted_username) != USERNAME:

    logger.debug('Username does not match encrypted username ...')
    exit(1)

PASSCODE = getpass('Enter passcode: ')

if cipher.decrypt(encrypted_passcode) != PASSCODE:

    logger.debug('Passcode does not match encrypted passcode ...')
    exit(1)

logger.debug('Successfully entered credentials ...')

# Load key/secret for bittrex API
with open(BITTREX_CREDENTIALS_PATH, 'r') as f:
    BITTREX_CREDENTIALS = json_load(f)

# Initialize database
db = Database(hostname=HOSTNAME,
              username=USERNAME,
              password=PASSCODE,
              database_name=DATABASE_NAME,
              logger=logger)

# Initialize Bittrex object
bittrex = Bittrex(api_key=BITTREX_CREDENTIALS.get('key'),
                  api_secret=BITTREX_CREDENTIALS.get('secret'),
                  api_version='v1.1')

# Get all markets on Bittrex
# bittrex_markets = bittrex.get_markets()
# MARKETS = filter_bittrex_markets(bittrex_markets, BASE_COIN)

MARKETS = ['BTC-CLUB']

# Create table for each market if doesn't exist
for market in MARKETS:
    db.create_price_table(market)

market = MARKETS[0]

constant = 0

initial_market_history = bittrex.get_market_history(market).get('result')

working_list = initial_market_history
current_datetime = convert_bittrex_timestamp_to_datetime(initial_market_history[0].get('TimeStamp'))

sleep(sleep_time)

try:

    while True:

        try:
            market_history = bittrex.get_market_history(market).get('result')
            last_id = working_list[0].get('Id')

            index = [x.get('Id') for x in market_history].index(last_id)

            working_list = market_history[:index] + working_list

            latest_datetime = convert_bittrex_timestamp_to_datetime(working_list[0].get('TimeStamp'))

            if (latest_datetime - current_datetime).total_seconds() > interval:

                start, stop = get_interval_index(working_list, current_datetime, interval)
                metrics = calculate_metrics(working_list[start:stop], current_datetime)

                working_list = working_list[:start]
                current_datetime = current_datetime + timedelta(seconds=interval)

                constant = 0

            elif constant > 2:

                start, stop = get_interval_index(working_list, current_datetime, interval)
                new_metrics = calculate_metrics(working_list[start:stop],
                                                current_datetime)  # All metrics should be 0

                metrics['volume'] = new_metrics.get('volume')
                metrics['buy_order'] = new_metrics.get('buy_order')
                metrics['sell_order'] = new_metrics.get('sell_order')
                metrics['time'] = new_metrics.get('time')

                working_list = working_list[:start]
                current_datetime = current_datetime + timedelta(seconds=interval)

            else:
                constant += 1
                logger.debug('Latest data point within interval. Skipping metrics generation.')

            # Set dynamic sleep time based on order volume
            if index < 30:
                sleep_time = 60
            else:
                sleep_time = 30

        except ValueError:
            logger.debug('Latest ID in working list not found in latest market history. Adding all latest market history to working list.')

            working_list = market_history + working_list

            start, stop = get_interval_index(working_list, current_datetime, interval)

            metrics = calculate_metrics(working_list, current_datetime)
            current_datetime = current_datetime + timedelta(seconds=interval)

            sleep_time = 30

        formatted_entry = format_bittrex_entry(metrics)
        db.insert_query(market, formatted_entry)

        sleep(sleep_time)

        # TODO: At midnight of every day - check and delete if any data past 30 days

except (KeyboardInterrupt, ConnectionError) as e:
    logger.debug('Error: {}. Exiting ...'.format(e))

db.close()
exit(0)