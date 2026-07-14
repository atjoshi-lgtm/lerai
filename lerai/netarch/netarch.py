from pathlib import Path

from sqlalchemy.engine.url import URL
from sqlalchemy.engine import Engine
from sqlalchemy import create_engine
import inspect
import logging
import pandas as pd
import csv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
data_dir = PROJECT_ROOT / "lerai" / "data"


class NetarchConnection:
    """Class to handle Netarch connections."""

    def __init__(self, database="netopt"):
        """Initializes a Netarch Connection

        Args:
            database (str, optional): The database to be used.
            The connection will still have access to all other databases
            that the phpview account permits. Defaults to "netopt".
        """
        database_connection_url = URL.create(
            drivername="mysql+pymysql",
            host="data-ro.netarch.akamai.com",
            database=database,
            username="phpview",
        )
        self.netarch_engine = create_engine(url=database_connection_url)

    def get_engine(self) -> Engine:
        """Returns engine to be easily passed to the Panda's read_sql command.

        Returns:
            Engine: Netarch read only database's engine
        """
        return self.netarch_engine


class NetarchConnectionWrite:
    """Class to handle Netarch connections."""

    def __init__(self, cnf_path, database="netopt"):
        """Initializes a Netarch Connection

        Args:
            database (str, optional): The database to be used.
            The connection will still have access to all other databases
            that the phpview account permits. Defaults to "netopt".
        """
        host = "data-rw.netarch.akamai.com"

        self.netarch_engine = create_engine(
            url=f"mysql+pymysql://{host}?database={database}&read_default_file={cnf_path}"
        )

    def get_engine(self):
        return self.netarch_engine

def fetch_data_from_netarch(query, min_length):
    """ 
    Utility function to fetch data from netarch for the given query
    """

    netarch = NetarchConnection()
    data = pd.read_sql(query, netarch.get_engine())

    if data.shape[0] < min_length:
        func_name = inspect.currentframe().f_code.co_name # type: ignore
        msg = f"{func_name}: insufficient lines"
        logging.error(msg)
        raise RuntimeError(msg)

    return data

def fetch_metro_region_mapping(output_path=None):
    """
    Fetches the metro-region mapping from the netarch database.
    Returns a DataFrame with columns: metro_area, region_number
    """
    query = """
        select 
            case when A.REGION_NETWORK = 'FreeFlow' then 'FF' when A.REGION_NETWORK = 'ESSL' then 'ESSL' else '' end as network, 
            R.ECOR_NAME as ecor_name, 
            CAST(A.REGION_NUMBER as INT) as region, 
            A.REGION_NAME as region_name, 
            replace(
                replace(A.PRODUCT_SERVER_TYPE, ' ', '_'), 
                '_(NPI)', 
                ''
            ) as hw_category, 
            count(distinct A.PRIMARY_IP_ADDRESS) as servers, 
            DC.GEOCODE_METRO_AREA metro_area 
        from 
            CMN_INT.AK_ASSET_HW A 
            inner join CMN_INT.AK_DATA_CENTER DC on DC.DATA_CENTER_ID = A.DATA_CENTER_ID 
            inner join CMN_INT.AK_REGION R on R.REGION_NUMBER = A.REGION_NUMBER 
            inner join netopt.large_region_machine_suspension_info F on F.IP = A.PRIMARY_IP_ADDRESS 
            and F.Region = A.REGION_NUMBER 
            and F.Last_seen_unsuspended > 0 
        where 
            A.MACHINE_CLASS = 'Edge Server' 
            and A.REGION_NETWORK = 'FreeFlow' 
            and R.STATUS = 'Live' 
            and R.NETWORK = 'FreeFlow' 
            and R.REGION_USE_TYPE like 'LR_%%' 
        group by 
            A.REGION_NUMBER, 
            hw_category"""
    
    netarch = NetarchConnection()
    data = pd.read_sql(query, netarch.get_engine())
    
    # Save the DataFrame to a CSV file in the data directory.
    # All entries in CSV should be enclosed in double quotes to avoid issues with commas in the data.
    if output_path is None:
        output_path = data_dir / "metro_region.csv"
    data.to_csv(output_path, index=False, quoting=csv.QUOTE_ALL)

    return data

if __name__ == "__main__":
    print(fetch_metro_region_mapping())
    # Example usage
#     query = """
# select 
#     case when A.REGION_NETWORK = 'FreeFlow' then 'FF' when A.REGION_NETWORK = 'ESSL' then 'ESSL' else '' end as network, 
#     R.ECOR_NAME as ecor_name, 
#     CAST(A.REGION_NUMBER as INT) as region, 
#     A.REGION_NAME as region_name, 
#     replace(
#         replace(A.PRODUCT_SERVER_TYPE, ' ', '_'), 
#         '_(NPI)', 
#         ''
#     ) as hw_category, 
#     count(distinct A.PRIMARY_IP_ADDRESS) as servers, 
#     DC.GEOCODE_METRO_AREA metro_area 
# from 
#     CMN_INT.AK_ASSET_HW A 
#     inner join CMN_INT.AK_DATA_CENTER DC on DC.DATA_CENTER_ID = A.DATA_CENTER_ID 
#     inner join CMN_INT.AK_REGION R on R.REGION_NUMBER = A.REGION_NUMBER 
#     inner join netopt.large_region_machine_suspension_info F on F.IP = A.PRIMARY_IP_ADDRESS 
#     and F.Region = A.REGION_NUMBER 
#     and F.Last_seen_unsuspended > 0 
# where 
#     A.MACHINE_CLASS = 'Edge Server' 
#     and A.REGION_NETWORK = 'FreeFlow' 
#     and R.STATUS = 'Live' 
#     and R.NETWORK = 'FreeFlow' 
#     and R.REGION_USE_TYPE like 'LR_%%' 
# group by 
#     A.REGION_NUMBER, 
#     hw_category"""
#     min_length = 10
#     try:
#         data = fetch_data_from_netarch(query, min_length)
#         print(data)
#     except RuntimeError as e:
#         print(f"Error fetching data: {e}")
