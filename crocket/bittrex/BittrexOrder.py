from datetime import datetime
from decimal import Decimal

from utilities.constants import BittrexConstants, OrderStatus
from utilities.time import convert_bittrex_timestamp_to_datetime, utc_to_local


class BittrexOrder:

    def __init__(self,
                 market=None,
                 order_type=None,
                 target_price=0,
                 target_quantity=0,
                 base_quantity=0,
                 current_quantity=0,
                 open_time=None,
                 closed_time=None,
                 status=OrderStatus.UNEXECUTED.name,
                 uuid=None,
                 actual_price=0,
                 cost=0):

        self.market = market
        self.type = order_type
        self.target_price = target_price
        self.target_quantity = target_quantity
        self.base_quantity = base_quantity
        self.current_quantity = current_quantity
        self.status = status

        # Order information from Bittrex API
        self.uuid = uuid
        self.open_time = open_time
        self.closed_time = closed_time
        self.actual_price = actual_price
        self.cost = cost

    @staticmethod
    def create(order):
        """
        Create a BittrexOrder from an order
        :param order:
        :return:
        """

        new_order = BittrexOrder(market=order.get('market'),
                                 order_type=order.get('type'),
                                 target_quantity=order.get('target_quantity'),
                                 base_quantity=order.get('base_quantity'))

        return new_order

    def add_completed_order(self, order):
        """
        Add order data from Bittrex API response
        Ex:
        {'AccountId': None,
         'CancelInitiated': False,
         'Closed': '2017-12-23T05:00:55.42',
         'CommissionPaid': 2.52e-06,
         'CommissionReserveRemaining': 0.0,
         'CommissionReserved': 2.52e-06,
         'Condition': 'NONE',
         'ConditionTarget': None,
         'Exchange': 'BTC-RDD',
         'ImmediateOrCancel': False,
         'IsConditional': False,
         'IsOpen': False,
         'Limit': 7.4e-07,
         'Opened': '2017-12-23T05:00:55.28',
         'OrderUuid': '8f178b37-cb5c-4242-a329-35c22a612535',
         'Price': 0.00101084,
         'PricePerUnit': 7.4e-07,
         'Quantity': 1366.0,
         'QuantityRemaining': 0.0,
         'ReserveRemaining': 0.00101084,
         'Reserved': 0.00101084,
         'Sentinel': 'c3172e91-aac4-440a-b722-7c5142c5e9b0',
         'Type': 'LIMIT_BUY'}

        :param order_data: Bittrex order response
        :return:
        """

        self.status = OrderStatus.COMPLETED.name
        self.actual_price = Decimal(order.get('PricePerUnit')).quantize(BittrexConstants.DIGITS)

        try:
            self.closed_time = utc_to_local(convert_bittrex_timestamp_to_datetime(order.get('Closed')))
        # Closed is None when order is incomplete
        except TypeError:
            self.closed_time = datetime.now().astimezone(tz=None)

        order_type = order.get('Type')

        if order_type == 'LIMIT_BUY':
            self.cost = (Decimal(order.get('Price')) + Decimal(order.get('CommissionPaid'))).quantize(
                BittrexConstants.DIGITS)

            self.current_quantity = (Decimal(order.get('Quantity')) - Decimal(order.get('QuantityRemaining'))).quantize(
                BittrexConstants.DIGITS)

        elif order_type == 'LIMIT_SELL':
            self.cost = (Decimal(order.get('Price')) - Decimal(order.get('CommissionPaid'))).quantize(
                BittrexConstants.DIGITS)

    def update_uuid(self, uuid):
        """
        Update order UUID
        :param uuid:
        :return:
        """

        self.uuid = uuid

    def update_status(self, status):
        """
        Update order status
        :param status:
        :return:
        """

        self.status = status

    def update_target_price(self, price):
        """
        Update target price
        :param price:
        :return:
        """

        self.target_price = price